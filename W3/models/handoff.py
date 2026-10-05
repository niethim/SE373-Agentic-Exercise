"""
Models for Human Handoff as defined in Section 7 of plan.md.
Provides 30-second decision-ready handoff packages.
"""
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class HandoffStatus(str, Enum):
    HUMAN_APPROVAL_REQUIRED = "HUMAN_APPROVAL_REQUIRED"
    UNRECOVERABLE_ERROR = "UNRECOVERABLE_ERROR"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    LOOP_DETECTED = "LOOP_DETECTED"
    STALL_DETECTED = "STALL_DETECTED"
    UNAUTHORIZED_ACTION = "UNAUTHORIZED_ACTION"
    COMPLETED = "COMPLETED"


class HandoffReason(str, Enum):
    PAYMENT_APPROVAL = "Payment requires explicit human approval."
    CANCELLATION_APPROVAL = "Cancellation requires explicit human approval."
    PRICE_OVER_BUDGET = "All candidate flights exceed the user's maximum budget."
    NO_FLIGHTS_FOUND = "No available flights match origin, destination, and date."
    MAX_STEPS_REACHED = "Execution step budget has been exhausted."
    LOOP_PREVENTED = "Repeated tool calls detected; loop terminated."
    STALL_PREVENTED = "Agent made no progress over consecutive turns."
    UNAUTHORIZED_TOOL = "Agent attempted to call an unregistered or forbidden tool."
    CONSTRAINT_VIOLATION = "Proposed action violates strict user constraints."


class HumanHandoffRequest(BaseModel):
    status: HandoffStatus
    reason: str
    completed_actions: List[str] = Field(default_factory=list)
    pending_action: Optional[str] = None
    relevant_booking_information: Dict[str, Any] = Field(default_factory=dict)
    required_human_decision: str

    def format_30s_summary(self) -> str:
        """
        Formats a clean human-readable handoff message that can be answered in 30 seconds.
        """
        lines = [
            "=" * 50,
            f"Status: {self.status.value}",
            f"Reason: {self.reason}",
            f"Completed Actions: {', '.join(self.completed_actions) if self.completed_actions else 'None'}",
            f"Pending Action: {self.pending_action or 'None'}",
            "Relevant Booking Information:",
        ]
        for k, v in self.relevant_booking_information.items():
            lines.append(f"  - {k}: {v}")
        lines.append(f"Required Human Decision: {self.required_human_decision}")
        lines.append("=" * 50)
        return "\n".join(lines)
