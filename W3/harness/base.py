"""
Base Harness implementation coordinating exactly 5 Harness Layers
following kiến trúc chuẩn (Decision Diagram of 5 Termination Conditions) and kiến trúc chuẩn (Execution Checklist):

  - Lớp 1: Đạt mục tiêu (GoalValidatorLayer) -> Trả kết quả (Kết A)
  - Lớp 2: Hết ngân sách (BudgetLimitLayer) -> Log và báo người (Kết B)
  - Lớp 3: Phát hiện lặp (LoopDetectorLayer) -> Log và báo người (Kết C)
  - Lớp 4: Bế tắc & Ràng buộc (StallDetectorLayer) -> Log và báo người (Kết D)
  - Lớp 5: Cần con người (HumanApprovalLayer) -> Chờ phê duyệt (Kết E)
"""
import time
from typing import Dict, Any, Optional, Tuple, Callable
from models.constraints import UserConstraints
from models.handoff import HumanHandoffRequest, HandoffStatus, HandoffReason
from models.trace import AgentExecutionMetrics, PermissionLevel
from mock_service.tools import TOOL_REGISTRY
from mock_service.database import mock_db

from harness.layer1_goal import GoalValidatorLayer
from harness.layer2_budget import BudgetLimitLayer
from harness.layer3_loop import LoopDetectorLayer
from harness.layer4_stall import StallDetectorLayer
from harness.layer5_human import HumanApprovalLayer
from harness.trace_logger import TraceLogger


class Harness:
    """
    Orchestrates the 5 Harness Layers to provide foolproof guardrails around any agent architecture.
    """
    def __init__(
        self,
        constraints: UserConstraints,
        agent_name: str = "Agent",
        max_steps: int = 12,
        max_tokens: int = 25000,
        timeout_seconds: float = 120.0,
        auto_approve_human_actions: bool = False,
        human_approval_callback: Optional[Callable[[str, Dict[str, Any]], bool]] = None,
    ):
        self.constraints = constraints
        self.agent_name = agent_name

        # 5 CORE HARNESS LAYERS (kiến trúc chuẩn)
        self.layer1_goal = GoalValidatorLayer(constraints)
        self.layer2_budget = BudgetLimitLayer(
            max_steps=max_steps,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds
        )
        self.layer3_loop = LoopDetectorLayer(window=6, repeat_k=3)
        self.layer4_stall = StallDetectorLayer(constraints=constraints, stall_threshold=4)
        self.layer5_human = HumanApprovalLayer(
            human_approval_callback=human_approval_callback,
            auto_approve_human_actions=auto_approve_human_actions,
        )
        self.trace_logger = TraceLogger(agent_name=agent_name)

        # Backward compatibility aliases
        self.completion_validator = self.layer1_goal
        self.budget_manager = self.layer2_budget
        self.loop_detector = self.layer3_loop
        self.constraint_manager = self.layer4_stall
        self.progress_monitor = self.layer4_stall
        self.permission_manager = self.layer5_human
        self.handoff_manager = self.layer5_human
        self.tool_validator = self.layer5_human

        # State tracking
        self.is_terminated: bool = False
        self.active_handoff: Optional[HumanHandoffRequest] = None
        self.current_booking_code: Optional[str] = None
        self.unauthorized_attempts: int = 0
        self.loops_detected: int = 0
        self.is_completed: bool = False

    def reset(self):
        """Resets all 5 harness layers for a fresh run."""
        self.layer1_goal.reset()
        self.layer2_budget.reset()
        self.layer3_loop.reset()
        self.layer4_stall.reset()
        self.layer5_human.reset()
        self.trace_logger.reset()
        self.is_terminated = False
        self.active_handoff = None
        self.current_booking_code = None
        self.unauthorized_attempts = 0
        self.loops_detected = 0
        self.is_completed = False

    def record_thought(self, thought: str):
        """Logs the agent's internal reasoning/plan."""
        self.trace_logger.log("THOUGHT", thought)

    def execute_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        The central gateway through which ALL tool calls must pass.
        Implements kiến trúc chuẩn (5 Outcomes) & kiến trúc chuẩn (Checklist Order):

          TRƯỚC KHI CHẠY TOOL:
            - Lớp 5 (Cần con người / Least Privilege): Whitelist, Schema check & Sensitive action permission.
            - Lớp 4 (Bế tắc & Ràng buộc): Goal Drift check trước khi gọi tool.
            - Lớp 3 (Phát hiện lặp): Action loop check ((tool, args) lặp k lần).

          THỰC THI TOOL -> Observation:
            - Gọi mock service, log telemetry.

          SAU KHI CÓ OBSERVATION:
            - Bước 1: Lớp 1 (Đạt mục tiêu) -> Trả kết quả (Kết A).
            - Bước 2: Lớp 3 (Phát hiện lặp) -> Log và báo người (Kết C).
            - Bước 3: Lớp 4 (Bế tắc) -> Log và báo người (Kết D).
            - Bước 4: Lớp 2 (Hết ngân sách) -> Log và báo người (Kết B).
        """
        if self.is_terminated:
            return {
                "status": "error",
                "error": "execution_terminated",
                "hint": "Harness has halted execution due to termination conditions."
            }

        self.trace_logger.log("PROPOSED_ACTION", {"tool": tool_name, "args": args})

        # -------------------------------------------------------------
        # TRƯỚC KHI CHẠY TOOL
        # -------------------------------------------------------------
        # 1. LỚP 5: CẦN CON NGƯỜI - Least Privilege, Schema & Permission Check
        valid_schema, schema_err = self.layer5_human.validate_schema(tool_name, args)
        if not valid_schema:
            self.unauthorized_attempts += 1
            self.trace_logger.log("HARNESS_SECURITY_BLOCK", {
                "rule": "Lớp 5 (Least Privilege / Schema Check)",
                "tool": tool_name,
                "error": schema_err
            })
            return {
                "status": "error",
                "error": "unauthorized_or_invalid_tool",
                "hint": f"Call blocked by Harness: {schema_err}"
            }

        # Kiểm tra quyền thực thi (pay_booking, cancel_booking cần phê duyệt)
        is_permitted, perm_level, perm_err = self.layer5_human.check_permission(tool_name, args)
        if not is_permitted:
            self.trace_logger.log("HARNESS_PERMISSION_CHECK", {
                "rule": "Lớp 5 (Human Approval Required)",
                "permission_level": perm_level.value if perm_level else "UNKNOWN",
                "tool": tool_name,
                "status": "HUMAN_APPROVAL_REQUIRED"
            })
            self.is_terminated = True
            self.active_handoff = self.layer5_human.create_30s_handoff(
                status=HandoffStatus.HUMAN_APPROVAL_REQUIRED,
                reason=perm_err or HandoffReason.PAYMENT_APPROVAL.value,
                pending_action=f"{tool_name}({args})",
                booking_info=self._get_current_booking_info(args.get("booking_code")),
            )
            return {
                "status": "approval_required",
                "error": "human_approval_required",
                "hint": perm_err
            }

        # 2. LỚP 4: BẾ TẮC & RÀNG BUỘC - Goal Drift Protection
        valid_constraints, constraint_err = self.layer4_stall.validate_tool_call(tool_name, args)
        if not valid_constraints:
            self.trace_logger.log("HARNESS_CONSTRAINT_BLOCK", {
                "rule": "Lớp 4 (Goal Drift / Constraint Protection)",
                "tool": tool_name,
                "error": constraint_err
            })
            return {
                "status": "error",
                "error": "constraint_violation",
                "hint": f"Call violates user constraints: {constraint_err}"
            }

        # 3. LỚP 3: PHÁT HIỆN LẶP - Action Loop Check
        is_loop, loop_msg = self.layer3_loop.check_action_loop(tool_name, args)
        if is_loop:
            self.loops_detected += 1
            self.is_terminated = True
            self.active_handoff = self.layer5_human.create_30s_handoff(
                status=HandoffStatus.LOOP_DETECTED,
                reason=loop_msg,
                pending_action=f"{tool_name}({args})",
                booking_info=self._get_current_booking_info(),
            )
            self.trace_logger.log("TERMINATION", {"reason": "LOOP_DETECTED", "details": loop_msg})
            return {"status": "error", "error": "loop_detected", "hint": loop_msg}

        # -------------------------------------------------------------
        # THỰC THI TOOL
        # -------------------------------------------------------------
        tool_fn = TOOL_REGISTRY[tool_name]
        start_t = time.time()
        try:
            raw_result = tool_fn.invoke(args)
            if not isinstance(raw_result, dict):
                raw_result = {"status": "ok", "result": raw_result}
        except Exception as exc:
            raw_result = {
                "status": "error",
                "error": "tool_execution_exception",
                "hint": f"Tool raised exception: {str(exc)}"
            }

        elapsed_ms = (time.time() - start_t) * 1000.0

        # Cập nhật tiến độ ở Lớp 4 & Ghi nhận hành động đã làm ở Lớp 5
        new_progress = self.layer4_stall.update_from_tool(tool_name, args, raw_result)
        if raw_result.get("status") == "ok":
            action_desc = f"{tool_name} -> Thành công"
            if tool_name == "book_seat" and "booking" in raw_result:
                self.current_booking_code = raw_result["booking"].get("booking_code")
                action_desc = f"book_seat -> {self.current_booking_code}"
            elif tool_name == "pay_booking":
                action_desc = f"pay_booking -> {args.get('booking_code')} Confirmed"
            self.layer5_human.record_completed_action(action_desc)

        self.trace_logger.log("TOOL_OBSERVATION", {
            "tool": tool_name,
            "success": raw_result.get("status") == "ok",
            "progress": new_progress,
            "latency_ms": round(elapsed_ms, 2),
            "data": raw_result
        })

        # -------------------------------------------------------------
        # SAU KHI CÓ OBSERVATION (Checklist kiến trúc chuẩn)
        # -------------------------------------------------------------
        # BƯỚC 1: LỚP 1 - ĐẠT MỤC TIÊU (Kết A: Trả kết quả)
        if self.current_booking_code or args.get("booking_code"):
            code_to_check = self.current_booking_code or args.get("booking_code")
            is_done, reason, details = self.layer1_goal.verify_completion(code_to_check)
            if is_done:
                self.is_completed = True
                self.is_terminated = True
                self.trace_logger.log("COMPLETION_VERIFIED", {
                    "booking_code": code_to_check,
                    "details": details,
                    "reason": reason
                })
                return raw_result

        # BƯỚC 2: LỚP 3 - PHÁT HIỆN LẶP (Kết C: Log và báo người)
        obs_loop, obs_details = self.layer3_loop.check_observation_loop(tool_name, raw_result)
        if obs_loop:
            self.loops_detected += 1
            self.is_terminated = True
            self.active_handoff = self.layer5_human.create_30s_handoff(
                status=HandoffStatus.LOOP_DETECTED,
                reason=obs_details,
                pending_action=f"{tool_name}({args})",
                booking_info=self._get_current_booking_info(),
            )
            self.trace_logger.log("TERMINATION", {"reason": "OBSERVATION_LOOP", "details": obs_details})
            return raw_result

        # BƯỚC 3: LỚP 4 - BẾ TẮC (Kết D: Log và báo người)
        is_stalled, stall_msg = self.layer4_stall.check_stall(tool_name, args, raw_result)
        if is_stalled:
            self.is_terminated = True
            self.active_handoff = self.layer5_human.create_30s_handoff(
                status=HandoffStatus.STALL_DETECTED,
                reason=stall_msg,
                pending_action=f"{tool_name}({args})",
                booking_info=self._get_current_booking_info(),
            )
            self.trace_logger.log("TERMINATION", {"reason": "STALL_DETECTED", "details": stall_msg})
            return raw_result

        # BƯỚC 4: LỚP 2 - HẾT NGÂN SÁCH (Kết B: Log và báo người - Kiểm tra cuối cùng)
        budget_ok, budget_msg = self.layer2_budget.record_step()
        if not budget_ok:
            self.is_terminated = True
            self.active_handoff = self.layer5_human.create_30s_handoff(
                status=HandoffStatus.BUDGET_EXCEEDED,
                reason=budget_msg,
                pending_action=f"{tool_name}({args})",
                booking_info=self._get_current_booking_info(),
            )
            self.trace_logger.log("TERMINATION", {"reason": "BUDGET_EXCEEDED", "details": budget_msg})

        return raw_result

    def check_is_complete(self) -> Tuple[bool, str, Dict[str, Any]]:
        """Invokes deterministic completion validator on current booking."""
        return self.layer1_goal.verify_completion(self.current_booking_code)

    def get_metrics(self, scenario_id: str = "custom") -> AgentExecutionMetrics:
        """Calculates final execution metrics for benchmark and evaluation."""
        is_done, _, _ = self.layer1_goal.verify_completion(self.current_booking_code)

        # Check constraint satisfaction
        booking = mock_db.bookings.get(self.current_booking_code) if self.current_booking_code else None
        constraint_satisfied = False
        if booking:
            flight = mock_db.flights.get(booking.flight_id)
            if flight:
                validation = self.constraints.validate_flight(flight.to_summary())
                constraint_satisfied = validation.is_valid and booking.price <= self.constraints.max_budget
        elif not booking:
            # If no booking was made, no constraints were violated
            constraint_satisfied = True

        return AgentExecutionMetrics(
            agent_name=self.agent_name,
            scenario_id=scenario_id,
            success=self.is_completed,
            constraint_satisfied=constraint_satisfied,
            total_steps=self.layer2_budget.steps_taken,
            total_tool_calls=len([e for e in self.trace_logger.events if e.event_type == "PROPOSED_ACTION"]),
            elapsed_time_sec=round(self.layer2_budget.get_elapsed_time(), 2),
            tokens_used=self.layer2_budget.tokens_used,
            replan_count=self.layer2_budget.replans_count,
            loop_detected_count=self.loops_detected,
            unauthorized_blocked_count=self.unauthorized_attempts,
            handoff_triggered=self.active_handoff is not None,
            handoff_status=self.active_handoff.status.value if self.active_handoff else None,
            booking_code=self.current_booking_code,
        )

    def _get_current_booking_info(self, booking_code: Optional[str] = None) -> Dict[str, Any]:
        code = booking_code or self.current_booking_code
        if code and code in mock_db.bookings:
            return mock_db.bookings[code].to_safe_dict()
        return {}
