"""
Trace, permissions, and metrics models for the Harness and Agent execution.
"""
from enum import Enum
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field


class PermissionLevel(str, Enum):
    READ = "READ"
    WRITE = "WRITE"
    HUMAN_APPROVAL = "HUMAN_APPROVAL"


class ToolCallProposal(BaseModel):
    proposal_id: str
    tool_name: str
    args: Dict[str, Any]
    timestamp: str


class ToolExecutionResult(BaseModel):
    proposal_id: str
    tool_name: str
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0


class TraceEvent(BaseModel):
    step_id: int
    agent_type: str
    event_type: str  # THOUGHT, PROPOSED_ACTION, HARNESS_CHECK, TOOL_RESULT, HANDOFF, ERROR, COMPLETION
    content: Any
    timestamp: str
    sensitive_redacted: bool = True


class AgentExecutionMetrics(BaseModel):
    agent_name: str
    scenario_id: str
    success: bool = False
    constraint_satisfied: bool = False
    total_steps: int = 0
    total_tool_calls: int = 0
    elapsed_time_sec: float = 0.0
    tokens_used: int = 0
    replan_count: int = 0
    loop_detected_count: int = 0
    unauthorized_blocked_count: int = 0
    handoff_triggered: bool = False
    handoff_status: Optional[str] = None
    booking_code: Optional[str] = None
    notes: str = ""
