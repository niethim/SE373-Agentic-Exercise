"""
Design 2: Plan-then-Execute Agent (Plan -> Validate Plan -> Step by Step Execution)
Creates the full plan upfront, validates it, and executes sequentially.
Supports both live LLM and mock deterministic execution.
"""
import json
import re
from typing import Dict, Any, List, Optional, Tuple
from langchain_core.messages import SystemMessage, HumanMessage
from agents.base_agent import BaseAgent


PLAN_SYSTEM_PROMPT = """
You are a Plan-then-Execute Flight Booking Agent.
Your task is to analyze the user request and generate a STRICT JSON PLAN upfront.

Rules for planning:
1. Output ONLY a valid JSON array of steps. No markdown code blocks, no text before or after.
2. Each step must have:
   - "step": integer (1, 2, 3...)
   - "tool": tool name ("search_flights", "check_seat", "book_seat", "pay_booking")
   - "args": dictionary of arguments
   - "description": brief explanation
3. Use placeholder notation for values produced by earlier steps:
   - "$BEST_FLIGHT_ID": the lowest price flight ID meeting constraints found from search_flights
   - "$SELECTED_SEAT": available seat number from check_seat
   - "$BOOKING_CODE": booking_code returned by book_seat
"""


class PlanThenExecuteAgent(BaseAgent):
    def __init__(self, harness, model_name=None, temperature=0.0, use_mock_llm=False):
        super().__init__(harness=harness, model_name=model_name, temperature=temperature, use_mock_llm=use_mock_llm)

    def generate_plan(self, user_prompt: str) -> List[Dict[str, Any]]:
        """Phase 1: Generate plan upfront with LLM or deterministic template."""
        c = self.harness.constraints
        if self.use_mock_llm or self.llm is None:
            self.harness.budget_manager.record_tokens(300)
            self.harness.record_thought("Generating static upfront plan for flight booking.")
            return [
                {"step": 1, "tool": "search_flights", "args": {"origin": c.origin, "destination": c.destination, "date": c.departure_date}, "description": "Search available flights"},
                {"step": 2, "tool": "check_seat", "args": {"flight_id": "$BEST_FLIGHT_ID"}, "description": "Check seat availability"},
                {"step": 3, "tool": "book_seat", "args": {"flight_id": "$BEST_FLIGHT_ID", "seat_number": "$SELECTED_SEAT", "passenger_name": c.passenger_name}, "description": "Book seat"},
                {"step": 4, "tool": "pay_booking", "args": {"booking_code": "$BOOKING_CODE"}, "description": "Pay booking"},
            ]

        system_content = self.build_system_prompt() + "\n" + PLAN_SYSTEM_PROMPT
        messages = [
            SystemMessage(content=system_content),
            HumanMessage(content=f"Create execution plan for: {user_prompt}")
        ]

        response = self.invoke_llm_with_retry(self.llm, messages)
        raw_text = response.content.strip()
        self.harness.record_thought(f"Generated Initial Plan:\n{raw_text}")

        json_match = re.search(r"\[.*\]", raw_text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except Exception:
                pass

        return [
            {"step": 1, "tool": "search_flights", "args": {"origin": c.origin, "destination": c.destination, "date": c.departure_date}, "description": "Search available flights"},
            {"step": 2, "tool": "check_seat", "args": {"flight_id": "$BEST_FLIGHT_ID"}, "description": "Check seat availability"},
            {"step": 3, "tool": "book_seat", "args": {"flight_id": "$BEST_FLIGHT_ID", "seat_number": "$SELECTED_SEAT", "passenger_name": c.passenger_name}, "description": "Book seat"},
            {"step": 4, "tool": "pay_booking", "args": {"booking_code": "$BOOKING_CODE"}, "description": "Pay booking"},
        ]

    def validate_plan(self, plan: List[Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
        """Phase 2: Harness validates plan structure and tools before execution."""
        if not isinstance(plan, list) or len(plan) == 0:
            return False, "Plan is empty or invalid format."

        for item in plan:
            tool_name = item.get("tool")
            if tool_name not in self.harness.tool_validator.allowed_tools:
                return False, f"Plan contains unauthorized tool: '{tool_name}'."

        self.harness.trace_logger.log("PLAN_VALIDATED", {"step_count": len(plan), "valid": True})
        return True, None

    def resolve_placeholders(self, args: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Resolves dynamic runtime placeholders from previous steps."""
        resolved = {}
        for k, v in args.items():
            if isinstance(v, str):
                if v == "$BEST_FLIGHT_ID":
                    resolved[k] = context.get("best_flight_id", "VN122")
                elif v == "$SELECTED_SEAT":
                    resolved[k] = context.get("selected_seat", "12A")
                elif v == "$BOOKING_CODE":
                    resolved[k] = context.get("booking_code", "")
                else:
                    resolved[k] = v
            else:
                resolved[k] = v
        return resolved

    def run(self, user_prompt: str) -> Dict[str, Any]:
        """Executes Plan-then-Execute lifecycle."""
        # 1. Plan
        plan = self.generate_plan(user_prompt)

        # 2. Validate Plan
        valid_plan, err = self.validate_plan(plan)
        if not valid_plan:
            return {
                "agent": "Plan-then-Execute",
                "completed": False,
                "completion_reason": f"Plan validation failed: {err}",
                "details": {},
                "handoff": self.harness.active_handoff,
                "metrics": self.harness.get_metrics(),
                "final_message": f"Execution halted due to invalid plan: {err}",
            }

        # 3. Execute Step 1 -> Step 2 -> ...
        context: Dict[str, Any] = {}

        for step_info in plan:
            if self.harness.is_terminated:
                break

            tool_name = step_info.get("tool", "")
            raw_args = step_info.get("args", {})
            resolved_args = self.resolve_placeholders(raw_args, context)

            obs = self.harness.execute_tool(tool_name, resolved_args)

            # Process outputs into context
            if obs.get("status") == "ok":
                if tool_name == "search_flights":
                    flights = obs.get("flights", [])
                    if not flights:
                        self.harness.record_thought("No flights found on search. Static plan stops.")
                        break

                    # Pick lowest price under budget
                    valid_c = [f for f in flights if f.get("price", 9e9) <= self.harness.constraints.max_budget]
                    if valid_c:
                        # Static plan takes the top flight regardless of seat availability until checked
                        context["best_flight_id"] = valid_c[0]["flight_id"]
                    else:
                        self.harness.record_thought("All flights exceed budget. Static plan stops.")
                        break

                elif tool_name == "check_seat":
                    if obs.get("seats_available", 0) == 0:
                        # In Plan-then-Execute, static plan fails if flight is full because it does not replan
                        self.harness.record_thought(f"Flight {resolved_args.get('flight_id')} is fully booked. Static plan cannot adapt and halts.")
                        break

                    seats = obs.get("seats", [])
                    if seats:
                        context["selected_seat"] = seats[0]["seat_number"]
                    elif obs.get("seat_number"):
                        context["selected_seat"] = obs.get("seat_number")

                elif tool_name == "book_seat":
                    booking = obs.get("booking", {})
                    if booking.get("booking_code"):
                        context["booking_code"] = booking.get("booking_code")
            else:
                self.harness.record_thought(f"Step {step_info.get('step')} failed with: {obs.get('error')}. Plan execution halted.")
                break

        is_done, reason, details = self.harness.check_is_complete()

        return {
            "agent": "Plan-then-Execute",
            "completed": is_done,
            "completion_reason": reason,
            "details": details,
            "handoff": self.harness.active_handoff,
            "metrics": self.harness.get_metrics(),
            "final_message": f"Plan-then-Execute finished with status: {reason}",
        }
