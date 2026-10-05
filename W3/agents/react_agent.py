"""
Design 1: ReAct Agent (Reason -> Act -> Observe -> Reason -> ...)
Dynamic decision-making after every tool observation.
Supports both live LLM and mock deterministic execution.
"""
import json
import re
from typing import Dict, Any, List
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from agents.base_agent import BaseAgent
from mock_service.tools import get_all_tools


class ReActAgent(BaseAgent):
    def __init__(self, harness, model_name=None, temperature=0.0, use_mock_llm=False):
        super().__init__(harness=harness, model_name=model_name, temperature=temperature, use_mock_llm=use_mock_llm)
        self.tools = get_all_tools()
        if self.llm:
            self.llm_with_tools = self.llm.bind_tools(self.tools)
        else:
            self.llm_with_tools = None

    def run(self, user_prompt: str) -> Dict[str, Any]:
        """Executes ReAct reasoning loop."""
        if self.use_mock_llm or self.openai_client is None:
            return self._run_heuristic(user_prompt)
        return self._run_live(user_prompt)

    def _run_live(self, user_prompt: str) -> Dict[str, Any]:
        is_uit = "uit.edu.vn" in (self.base_url or "")
        if is_uit:
            system_content = self.build_system_prompt() + """
You operate in a strict ReAct loop.
To call a tool, respond ONLY with a single valid JSON object formatted exactly as:
{"thought": "concise reasoning", "action": "tool_name", "action_input": {"param": "value"}}

When you have completed all tasks (or cannot proceed), respond with:
{"thought": "concise reasoning", "final_answer": "summary of booking or outcome"}
Do NOT wrap your JSON in conversational markdown explanations.
"""
        else:
            system_content = self.build_system_prompt() + """
You operate in a strict ReAct loop.
Before calling any tool, provide a concise Thought explaining why you chose this action and how it satisfies constraints.
When calling tools, inspect the observation. If a flight is unavailable or over budget, adapt and check other flights.
Never invent flight IDs or prices. Once you have booked and paid, summarize the booking.
"""
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_prompt}
        ]

        final_content = ""
        while not self.harness.is_terminated:
            budget_ok, budget_err = self.harness.budget_manager.check_budget()
            if not budget_ok:
                self.harness.is_terminated = True
                break

            if is_uit:
                msg = self.invoke_openai_with_retry(messages, tools=None)
                raw_text = msg.content or ""
                final_content = raw_text

                # Parse JSON action
                json_match = re.search(r"\{.*\}", raw_text, re.DOTALL)
                action_data = None
                if json_match:
                    try:
                        action_data = json.loads(json_match.group(0))
                    except Exception:
                        pass

                if action_data and "thought" in action_data:
                    self.harness.record_thought(action_data["thought"])
                elif raw_text:
                    self.harness.record_thought(raw_text)

                if action_data and action_data.get("action"):
                    tool_name = action_data["action"]
                    tool_args = action_data.get("action_input", {})
                    if isinstance(tool_args, str):
                        try:
                            tool_args = json.loads(tool_args)
                        except Exception:
                            tool_args = {}
                    observation = self.harness.execute_tool(tool_name, tool_args)
                    messages.append({"role": "assistant", "content": raw_text})
                    messages.append({
                        "role": "user",
                        "content": f"Observation for {tool_name}: {json.dumps(observation, ensure_ascii=False)}"
                    })
                    if self.harness.is_terminated:
                        break
                else:
                    break
            else:
                msg = self.invoke_openai_with_retry(messages, tools=self.openai_tools)

                if msg.content:
                    final_content = msg.content
                    self.harness.record_thought(msg.content)

                tool_calls = getattr(msg, "tool_calls", None)
                if not tool_calls:
                    break

                # Preserve thought_signature and extra_content in tool_calls for Gemini API
                assistant_msg = {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [tc.model_dump() for tc in tool_calls]
                }
                messages.append(assistant_msg)

                for tc in tool_calls:
                    tool_name = tc.function.name
                    args = json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else tc.function.arguments
                    tool_call_id = tc.id

                    observation = self.harness.execute_tool(tool_name, args)

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": json.dumps(observation, ensure_ascii=False)
                    })

                    if self.harness.is_terminated:
                        break

        is_done, reason, details = self.harness.check_is_complete()

        return {
            "agent": "ReAct",
            "completed": is_done,
            "completion_reason": reason,
            "details": details,
            "handoff": self.harness.active_handoff,
            "metrics": self.harness.get_metrics(),
            "final_message": final_content,
        }


    def _run_heuristic(self, user_prompt: str) -> Dict[str, Any]:
        """Heuristic ReAct loop for zero-token deterministic verification and fast tests."""
        c = self.harness.constraints
        self.harness.budget_manager.record_tokens(350)

        # Step 1: Reason & Search
        self.harness.record_thought(f"Searching flights from {c.origin} to {c.destination} on {c.departure_date}.")
        search_res = self.harness.execute_tool("search_flights", {
            "origin": c.origin,
            "destination": c.destination,
            "date": c.departure_date
        })

        # Check if search encountered transient timeout (e.g. TC05)
        if search_res.get("status") == "error" and search_res.get("error") == "timeout":
            self.harness.record_thought("Search timed out. Retrying search_flights.")
            self.harness.budget_manager.record_retry()
            search_res = self.harness.execute_tool("search_flights", {
                "origin": c.origin,
                "destination": c.destination,
                "date": c.departure_date
            })

        if self.harness.is_terminated or search_res.get("status") != "ok":
            is_done, reason, details = self.harness.check_is_complete()
            return {"agent": "ReAct", "completed": is_done, "completion_reason": reason, "details": details, "handoff": self.harness.active_handoff, "metrics": self.harness.get_metrics()}

        flights = search_res.get("flights", [])
        if not flights:
            self.harness.record_thought("No flights found matching criteria. Stopping.")
            is_done, reason, details = self.harness.check_is_complete()
            return {"agent": "ReAct", "completed": is_done, "completion_reason": "No flights found", "details": details, "handoff": self.harness.active_handoff, "metrics": self.harness.get_metrics()}

        # Filter flights by budget
        valid_flights = [f for f in flights if f.get("price", 9e9) <= c.max_budget]
        if not valid_flights:
            self.harness.record_thought("All available flights exceed user's maximum budget. Aborting.")
            is_done, reason, details = self.harness.check_is_complete()
            return {"agent": "ReAct", "completed": is_done, "completion_reason": "All flights exceed budget", "details": details, "handoff": self.harness.active_handoff, "metrics": self.harness.get_metrics()}

        # Step 2: Check seats iteratively (dynamic adaptation on unavailable seats)
        booked_code = None
        for candidate in valid_flights:
            f_id = candidate["flight_id"]
            self.harness.record_thought(f"Checking seat availability for candidate flight {f_id}.")
            seat_res = self.harness.execute_tool("check_seat", {"flight_id": f_id})

            if self.harness.is_terminated:
                break

            if seat_res.get("status") == "ok" and seat_res.get("seats_available", 0) > 0:
                seats = seat_res.get("seats", [])
                chosen_seat = seats[0]["seat_number"] if seats else "12A"

                # Step 3: Book seat
                self.harness.record_thought(f"Flight {f_id} has available seat {chosen_seat}. Booking seat for {c.passenger_name}.")
                book_res = self.harness.execute_tool("book_seat", {
                    "flight_id": f_id,
                    "seat_number": chosen_seat,
                    "passenger_name": c.passenger_name
                })

                if self.harness.is_terminated:
                    break

                if book_res.get("status") == "ok":
                    booked_code = book_res["booking"]["booking_code"]

                    # Step 4: Pay booking
                    self.harness.record_thought(f"Booking {booked_code} created. Requesting payment confirmation.")
                    pay_res = self.harness.execute_tool("pay_booking", {
                        "booking_code": booked_code,
                        "payment_method": "credit_card"
                    })
                    break
            else:
                self.harness.record_thought(f"Flight {f_id} is unavailable or full. Trying next flight candidate.")

        is_done, reason, details = self.harness.check_is_complete()
        return {
            "agent": "ReAct",
            "completed": is_done,
            "completion_reason": reason,
            "details": details,
            "handoff": self.harness.active_handoff,
            "metrics": self.harness.get_metrics(),
            "final_message": f"ReAct concluded with reason: {reason}",
        }
