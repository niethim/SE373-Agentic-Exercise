"""
Harness package strictly implementing kiến trúc chuẩn (Decision Diagram of 5 Termination Conditions):
- Lớp 1: Đạt mục tiêu (GoalValidatorLayer) -> Trả kết quả (Kết A)
- Lớp 2: Hết ngân sách (BudgetLimitLayer) -> Log và báo người (Kết B)
- Lớp 3: Phát hiện lặp (LoopDetectorLayer) -> Log và báo người (Kết C)
- Lớp 4: Bế tắc & Ràng buộc (StallDetectorLayer) -> Log và báo người (Kết D)
- Lớp 5: Cần con người (HumanApprovalLayer) -> Chờ phê duyệt (Kết E)
"""
from harness.base import Harness
from harness.trace_logger import TraceLogger

# 5 Main Harness Layers (kiến trúc chuẩn)
from harness.layer1_goal import GoalValidatorLayer
from harness.layer2_budget import BudgetLimitLayer
from harness.layer3_loop import LoopDetectorLayer
from harness.layer4_stall import StallDetectorLayer
from harness.layer5_human import HumanApprovalLayer

# Aliases for backward compatibility
CompletionValidator = GoalValidatorLayer
BudgetManager = BudgetLimitLayer
LoopDetector = LoopDetectorLayer
ConstraintManager = StallDetectorLayer
ProgressMonitor = StallDetectorLayer
PermissionManager = HumanApprovalLayer
HandoffManager = HumanApprovalLayer

__all__ = [
    "Harness",
    "TraceLogger",
    "GoalValidatorLayer",
    "BudgetLimitLayer",
    "LoopDetectorLayer",
    "StallDetectorLayer",
    "HumanApprovalLayer",
    # Legacy aliases
    "CompletionValidator",
    "BudgetManager",
    "LoopDetector",
    "ConstraintManager",
    "ProgressMonitor",
    "PermissionManager",
    "HandoffManager",
]
