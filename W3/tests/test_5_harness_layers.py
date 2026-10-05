"""
Unit tests specifically targeting the 5 Harness Layers (kiến trúc chuẩn Architecture):
- Lớp 1: Đạt mục tiêu (GoalValidatorLayer) -> Trả kết quả (Kết A)
- Lớp 2: Hết ngân sách (BudgetLimitLayer) -> Log và báo người (Kết B)
- Lớp 3: Phát hiện lặp (LoopDetectorLayer) -> Log và báo người (Kết C)
- Lớp 4: Bế tắc & Ràng buộc (StallDetectorLayer) -> Log và báo người (Kết D)
- Lớp 5: Cần con người (HumanApprovalLayer) -> Chờ phê duyệt (Kết E)
"""
import pytest
from models.constraints import UserConstraints
from models.trace import PermissionLevel
from models.handoff import HandoffStatus
from harness.layer1_goal import GoalValidatorLayer
from harness.layer2_budget import BudgetLimitLayer
from harness.layer3_loop import LoopDetectorLayer
from harness.layer4_stall import StallDetectorLayer
from harness.layer5_human import HumanApprovalLayer
from mock_service.database import mock_db


@pytest.fixture
def sample_constraints():
    return UserConstraints(
        origin="SGN",
        destination="HAN",
        departure_date="2026-10-15",
        max_budget=2000000.0,
        passenger_name="Tien Vo"
    )


# -------------------------------------------------------------
# LỚP 1: ĐẠT MỤC TIÊU (Kết A)
# -------------------------------------------------------------
def test_layer1_goal_validator(sample_constraints):
    mock_db.reset()
    layer1 = GoalValidatorLayer(sample_constraints)

    # 1. Hallucination check
    done, msg, _ = layer1.verify("NON_EXISTENT_CODE")
    assert not done
    assert "không tồn tại" in msg or "does not exist" in msg

    # 2. Booked but unpaid
    book_res = mock_db.book_seat("VN122", "12A", "Tien Vo")
    code = book_res["booking"]["booking_code"]
    done, msg, _ = layer1.verify(code)
    assert not done
    assert "confirmed" in msg

    # 3. Fully paid and confirmed -> Kết A
    mock_db.pay_booking(code)
    done, msg, details = layer1.verify(code)
    assert done is True
    assert details["status"] == "confirmed"
    assert details["payment"] == "paid"
    assert "Kết A" in msg


# -------------------------------------------------------------
# LỚP 2: HẾT NGÂN SÁCH (Kết B)
# -------------------------------------------------------------
def test_layer2_budget_limits():
    layer2 = BudgetLimitLayer(max_steps=3, max_tokens=100, max_replans=2)

    # Step limits
    ok1, _ = layer2.record_step()
    assert ok1 is True
    ok2, _ = layer2.record_step()
    assert ok2 is True
    ok3, msg = layer2.record_step()
    assert ok3 is False
    assert "Kết B" in msg or "Step budget exhausted" in msg

    # Replan limit
    layer2.reset()
    assert layer2.record_replan()[0] is True
    assert layer2.record_replan()[0] is True
    ok_rep, rep_msg = layer2.record_replan()
    assert ok_rep is False
    assert "Vượt quá" in rep_msg


# -------------------------------------------------------------
# LỚP 3: PHÁT HIỆN LẶP (Kết C)
# -------------------------------------------------------------
def test_layer3_loop_detector():
    layer3 = LoopDetectorLayer(window=5, repeat_k=2)

    # 1. Action loop
    verdict, _ = layer3.check_action("check_seat", {"flight_id": "VN122"})
    assert verdict is None
    verdict, msg = layer3.check_action("check_seat", {"flight_id": "VN122"})
    assert verdict == "LOOP"
    assert "Kết C" in msg

    # 2. Polling exception for get_booking
    layer3.reset()
    # Call 1 & 2 for get_booking allowed because threshold is repeat_k + 1 (3)
    v1, _ = layer3.check_action("get_booking", {"booking_code": "BK001"})
    v2, _ = layer3.check_action("get_booking", {"booking_code": "BK001"})
    assert v1 is None
    assert v2 is None

    # 3. Observation error loop (3 consecutive identical errors)
    layer3.reset()
    err_res = {"status": "error", "error": "seat_not_found"}
    layer3.check_observation("check_seat", err_res)
    layer3.check_observation("check_seat", err_res)
    v_obs, msg_obs = layer3.check_observation("check_seat", err_res)
    assert v_obs == "LOOP"
    assert "3 lần" in msg_obs


# -------------------------------------------------------------
# LỚP 4: BẾ TẮC & RÀNG BUỘC (Kết D)
# -------------------------------------------------------------
def test_layer4_stall_and_constraints(sample_constraints):
    mock_db.reset()
    layer4 = StallDetectorLayer(sample_constraints, stall_threshold=2)

    # 1. Goal drift check (Destination mismatch)
    ok_dest, err_dest = layer4.validate_constraints("search_flights", {"origin": "SGN", "destination": "DAD", "date": "2026-10-15"})
    assert not ok_dest
    assert "Destination mismatch" in err_dest or "Chệch mục tiêu" in err_dest

    # 2. Budget constraint check
    ok_budget, err_budget = layer4.validate_constraints("book_seat", {"flight_id": "VN134", "seat_number": "08A", "passenger_name": "Tien Vo"})
    assert not ok_budget
    assert "exceeds budget" in err_budget

    # 3. Stall detection (progress doesn't advance for stall_threshold steps)
    layer4.update_progress("search_flights", {}, {"status": "ok", "flights": [{"flight_id": "VN122"}]})
    is_stall1, _ = layer4.check_stall()
    assert is_stall1 is False
    is_stall2, _ = layer4.check_stall()
    assert is_stall2 is False
    is_stall3, msg_stall = layer4.check_stall()
    assert is_stall3 is True
    assert "Kết D" in msg_stall



# -------------------------------------------------------------
# LỚP 5: CẦN CON NGƯỜI (Kết E)
# -------------------------------------------------------------
def test_layer5_human_approval():
    layer5 = HumanApprovalLayer(auto_approve_human_actions=False)

    # 1. Least privilege whitelist check
    ok_reg, err_reg = layer5.validate_schema("unauthorized_shell_tool", {})
    assert not ok_reg
    assert "Unauthorized tool" in err_reg

    # 2. Schema check (invalid date format)
    ok_schema, err_schema = layer5.validate_schema("search_flights", {"origin": "SGN", "destination": "HAN", "date": "15/10/2026"})
    assert not ok_schema
    assert "YYYY-MM-DD" in err_schema

    # 3. Sensitive action requires approval (Kết E)
    is_perm, level, perm_err = layer5.check_permission("pay_booking", {"booking_code": "BK001"})
    assert is_perm is False
    assert level == PermissionLevel.HUMAN_APPROVAL

    # 4. 30-Second Handoff Package generation
    handoff = layer5.create_30s_handoff(
        status=HandoffStatus.HUMAN_APPROVAL_REQUIRED,
        reason=perm_err,
        pending_action="pay_booking(BK001)",
        booking_info={"booking_code": "BK001", "price": 1850000}
    )
    assert handoff.status == HandoffStatus.HUMAN_APPROVAL_REQUIRED
    assert "185,000" in handoff.required_human_decision or "1,850,000" in handoff.required_human_decision
    assert "[1: Đồng ý thanh toán | 2: Huỷ bỏ giữ chỗ | 3: Tìm chuyến bay khác]" in handoff.required_human_decision


# -------------------------------------------------------------
# AUDIT & TRACE LOGGER
# -------------------------------------------------------------
def test_trace_logger_redaction():
    from harness.trace_logger import redact_sensitive_data
    text = "Payment with card 4111-2222-3333-4444 and secret token sk-1234567890123456789012"
    redacted = redact_sensitive_data(text)
    assert "4111" not in redacted
    assert "[REDACTED_CARD]" in redacted
    assert "[REDACTED_API_KEY]" in redacted

