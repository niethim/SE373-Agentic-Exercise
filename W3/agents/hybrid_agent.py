"""
Design 3: Hybrid Agent (Plan -> Execute N Steps -> Observe -> Re-plan if necessary)
Combines structured planning with adaptive dynamic replanning upon encountering obstacles.
Supports both live LLM and mock deterministic execution.
"""
import json
import re
from typing import Dict, Any, List, Optional
from langchain_core.messages import SystemMessage, HumanMessage
from agents.base_agent import BaseAgent


class HybridAgent(BaseAgent):
    def __init__(self, harness, model_name=None, temperature=0.0, chunk_size: int = 2, use_mock_llm: bool = False):
        super().__init__(harness=harness, model_name=model_name, temperature=temperature, use_mock_llm=use_mock_llm)
        self.chunk_size = chunk_size

    def create_plan(self, prompt: str, current_state: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Generates or updates the step plan given current progress."""
        c = self.harness.constraints
        if self.use_mock_llm or self.llm is None:
            self.harness.budget_manager.record_tokens(320)
            if current_state and current_state.get("replan_for_flight"):
                alt_flight = current_state["replan_for_flight"]
                self.harness.record_thought(f"Replanning: flight 1 was full; switching to alternative flight {alt_flight}.")
                return [
                    {"step": 1, "tool": "check_seat", "args": {"flight_id": alt_flight}},
                    {"step": 2, "tool": "book_seat", "args": {"flight_id": alt_flight, "seat_number": "$SELECTED_SEAT", "passenger_name": c.passenger_name}},
                    {"step": 3, "tool": "pay_booking", "args": {"booking_code": "$BOOKING_CODE"}},
                ]
            return [
                {"step": 1, "tool": "search_flights", "args": {"origin": c.origin, "destination": c.destination, "date": c.departure_date}},
                {"step": 2, "tool": "check_seat", "args": {"flight_id": "$BEST_FLIGHT_ID"}},
                {"step": 3, "tool": "book_seat", "args": {"flight_id": "$BEST_FLIGHT_ID", "seat_number": "$SELECTED_SEAT", "passenger_name": c.passenger_name}},
                {"step": 4, "tool": "pay_booking", "args": {"booking_code": "$BOOKING_CODE"}},
            ]

        state_context = f"\nCurrent context: {json.dumps(current_state)}" if current_state else ""
        system_content = self.build_system_prompt() + f"""
You are a Hybrid Flight Booking Agent that produces executable JSON plans.
Generate a JSON array of remaining steps to accomplish the booking safely.
{state_context}

Available Tools:
search_flights, check_seat, book_seat, pay_booking, get_booking, cancel_booking.

Return ONLY a JSON array of steps:
[
  {{"step": 1, "tool": "search_flights", "args": {{"origin": "{c.origin}", "destination": "{c.destination}", "date": "{c.departure_date}"}}, "description": "Search available flights"}}
]
"""
        messages = [
            SystemMessage(content=system_content),
            HumanMessage(content=prompt)
        ]

        response = self.invoke_llm_with_retry(self.llm, messages)
        raw = response.content.strip()
        self.harness.record_thought(f"Hybrid Plan Generation:\n{raw}")

        json_match = re.search(r"\[.*\]", raw, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except Exception:
                pass

        return [
            {"step": 1, "tool": "search_flights", "args": {"origin": c.origin, "destination": c.destination, "date": c.departure_date}},
            {"step": 2, "tool": "check_seat", "args": {"flight_id": "$BEST_FLIGHT_ID"}},
            {"step": 3, "tool": "book_seat", "args": {"flight_id": "$BEST_FLIGHT_ID", "seat_number": "$SELECTED_SEAT", "passenger_name": c.passenger_name}},
            {"step": 4, "tool": "pay_booking", "args": {"booking_code": "$BOOKING_CODE"}},
        ]

    def resolve_args(self, args: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        resolved = {}
        for k, v in args.items():
            if isinstance(v, str):
                if v == "$BEST_FLIGHT_ID":
                    resolved[k] = context.get("flight_id", "VN122")
                elif v == "$SELECTED_SEAT":
                    resolved[k] = context.get("seat_number", "12A")
                elif v == "$BOOKING_CODE":
                    resolved[k] = context.get("booking_code", "")
                else:
                    resolved[k] = v
            else:
                resolved[k] = v
        return resolved

    def run(self, user_prompt: str) -> Dict[str, Any]:
        """Executes Hybrid workflow: Plan -> Execute N Steps -> Observe -> Re-plan if necessary."""
        context: Dict[str, Any] = {}
        current_plan = self.create_plan(user_prompt)

        while current_plan and not self.harness.is_terminated:
            budget_ok, _ = self.harness.budget_manager.check_budget()
            if not budget_ok:
                self.harness.is_terminated = True
                break

            batch = current_plan[:self.chunk_size]
            current_plan = current_plan[self.chunk_size:]
            needs_replan = False
            replan_prompt = ""

            for step in batch:
                if self.harness.is_terminated:
                    break

                tool_name = step.get("tool", "")
                raw_args = step.get("args", {})
                resolved_args = self.resolve_args(raw_args, context)

                obs = self.harness.execute_tool(tool_name, resolved_args)

                if obs.get("status") == "error":
                    # Tool encountered error (e.g. timeout)
                    needs_replan = True
                    replan_prompt = f"Tool '{tool_name}' failed with '{obs.get('error')}': {obs.get('hint')}. Replan next actions."
                    self.harness.record_thought(f"Anomaly observed in step '{tool_name}'. Triggering adaptive replan.")
                    break

                elif tool_name == "search_flights":
                    flights = obs.get("flights", [])
                    if not flights:
                        self.harness.record_thought("No flights found on search. Stopping gracefully.")
                        self.harness.is_terminated = True
                        break

                    candidates = [
                        f for f in flights
                        if f.get("price", 9e9) <= self.harness.constraints.max_budget
                    ]
                    if not candidates:
                        self.harness.record_thought("All flights exceed budget. Aborting booking.")
                        self.harness.is_terminated = True
                        break

                    context["candidates"] = candidates
                    context["flight_id"] = candidates[0]["flight_id"]
                    context["flight_price"] = candidates[0]["price"]

                elif tool_name == "check_seat":
                    if obs.get("seats_available", 0) == 0:
                        needs_replan = True
                        # Find alternative candidate
                        remaining = [c for c in context.get("candidates", []) if c["flight_id"] != resolved_args.get("flight_id")]
                        if remaining:
                            alt = remaining[0]["flight_id"]
                            context["replan_for_flight"] = alt
                            context["flight_id"] = alt
                            replan_prompt = f"Flight {resolved_args.get('flight_id')} is full. Replan to switch to {alt}."
                        else:
                            self.harness.record_thought("No alternate flights have seats. Aborting.")
                            self.harness.is_terminated = True
                            break
                        break
                    else:
                        seats = obs.get("seats", [])
                        if seats:
                            context["seat_number"] = seats[0]["seat_number"]
                        elif obs.get("seat_number"):
                            context["seat_number"] = obs.get("seat_number")

                elif tool_name == "book_seat":
                    b = obs.get("booking", {})
                    if b.get("booking_code"):
                        context["booking_code"] = b.get("booking_code")

            if needs_replan and not self.harness.is_terminated:
                replan_ok, _ = self.harness.budget_manager.record_replan()
                if not replan_ok:
                    self.harness.is_terminated = True
                    break

                self.harness.trace_logger.log("REPLAN_TRIGGERED", {"reason": replan_prompt, "context": context})
                current_plan = self.create_plan(replan_prompt, current_state=context)

        is_done, reason, details = self.harness.check_is_complete()

        return {
            "agent": "Hybrid",
            "completed": is_done,
            "completion_reason": reason,
            "details": details,
            "handoff": self.harness.active_handoff,
            "metrics": self.harness.get_metrics(),
            "final_message": f"Hybrid agent finished with status: {reason}",
        }
