"""
Lớp 5: Cần con người (Human Approval & 30s Handoff Layer)
Theo kiến trúc chuẩn (Decision Diagram of 5 Termination Conditions - Kết E) và kiến trúc chuẩn, 1000+:
- "Cần con người: vé không hoàn, vượt hạn mức -> Chờ phê duyệt"
- Bước 0 (Trước khi gọi tool): Kiểm tra quyền (Least Privilege & Sensitive Action Protection).
- Nếu tool thuộc nhóm HUMAN_APPROVAL (pay_booking, cancel_booking) mà chưa có phê duyệt -> Dừng, tạo gói bàn giao 30 giây (30-second Handoff Package).
- Chặn các tool ngoài whitelist (Fail-Closed).
"""
from typing import Dict, Any, Optional, Callable, Tuple, List
from models.trace import PermissionLevel
from models.handoff import HumanHandoffRequest, HandoffStatus
from mock_service.tools import TOOL_PERMISSIONS


import re

DATE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class HumanApprovalLayer:
    """
    Lớp 5: Cần con người (Human Approval & Least Privilege).
    Xử lý:
    1. Phân quyền chặt chẽ (Least Privilege whitelist): READ, WRITE, HUMAN_APPROVAL.
    2. Kiểm tra Schema & Whitelist (Fail-Closed đối với tool trái phép).
    3. Hành động nhạy cảm tài chính / không thể hoàn tác (pay_booking, cancel_booking).
    4. Kiểm tra vé không hoàn / vượt hạn mức cần người duyệt.
    5. Gói bàn giao 30 giây (30-second Handoff Package): Trạng thái, Lý do, Việc đã làm, Quyết định cụ thể.
    """
    def __init__(
        self,
        permissions: Optional[Dict[str, PermissionLevel]] = None,
        human_approval_callback: Optional[Callable[[str, Dict[str, Any]], bool]] = None,
        auto_approve_human_actions: bool = False,
    ):
        self.permissions: Dict[str, PermissionLevel] = permissions or dict(TOOL_PERMISSIONS)
        self.human_approval_callback = human_approval_callback
        self.auto_approve_human_actions = auto_approve_human_actions
        self.approved_actions: set = set()
        self.completed_actions: List[str] = []

    def reset(self):
        self.approved_actions.clear()
        self.completed_actions.clear()

    def record_completed_action(self, action_summary: str):
        """Ghi nhận hành động đã hoàn thành cho ngữ cảnh bàn giao 30 giây."""
        self.completed_actions.append(action_summary)

    def grant_approval(self, action_key: str):
        """Cấp quyền phê duyệt cho một action cụ thể (vd: 'pay_booking:BK001')."""
        self.approved_actions.add(action_key)

    @property
    def allowed_tools(self) -> set:
        """Tập hợp các công cụ được cấp phép trong whitelist."""
        return set(self.permissions.keys())

    def is_tool_registered(self, tool_name: str) -> bool:
        """Kiểm tra tool có nằm trong whitelist được cấp phép không."""
        return tool_name in self.permissions

    def validate_schema(self, tool_name: str, args: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Kiểm tra schema tham số tool theo Least Privilege & Fail-Closed."""
        if not self.is_tool_registered(tool_name):
            return False, f"Unauthorized tool: '{tool_name}' is not in the registered toolset."

        if tool_name == "search_flights":
            origin = args.get("origin")
            dest = args.get("destination")
            date = args.get("date")
            if not origin or not isinstance(origin, str) or len(origin.strip()) != 3:
                return False, "Parameter 'origin' must be a valid 3-letter IATA code."
            if not dest or not isinstance(dest, str) or len(dest.strip()) != 3:
                return False, "Parameter 'destination' must be a valid 3-letter IATA code."
            if not date or not isinstance(date, str) or not DATE_REGEX.match(date.strip()):
                return False, "Parameter 'date' must be in YYYY-MM-DD format."

        elif tool_name in ("check_seat", "book_seat"):
            if not args.get("flight_id") or not isinstance(args.get("flight_id"), str):
                return False, "Parameter 'flight_id' is required and must be non-empty."
            if tool_name == "book_seat":
                if not args.get("seat_number") or not isinstance(args.get("seat_number"), str):
                    return False, "Parameter 'seat_number' is required."
                if not args.get("passenger_name") or not isinstance(args.get("passenger_name"), str):
                    return False, "Parameter 'passenger_name' is required."

        elif tool_name in ("pay_booking", "get_booking", "cancel_booking"):
            if not args.get("booking_code") or not isinstance(args.get("booking_code"), str):
                return False, "Parameter 'booking_code' is required."

        return True, None

    validate_call = validate_schema


    def check_permission(self, tool_name: str, args: Dict[str, Any]) -> Tuple[bool, Optional[PermissionLevel], Optional[str]]:
        """
        Kiểm tra quyền trước khi gọi tool (Bước 0 trong kiến trúc chuẩn).
        Returns:
            (is_permitted, permission_level, error_or_reason)
        """
        if not self.is_tool_registered(tool_name):
            return False, None, f"Tool '{tool_name}' không nằm trong whitelist được cấp phép (Least Privilege violation)."

        perm = self.permissions[tool_name]

        # READ and WRITE don't require human approval by default
        if perm in (PermissionLevel.READ, PermissionLevel.WRITE):
            return True, perm, None

        if perm == PermissionLevel.HUMAN_APPROVAL:
            code = args.get("booking_code", "UNKNOWN")
            action_key = f"{tool_name}:{code}"

            # Check if already approved or auto-approved
            if action_key in self.approved_actions or self.auto_approve_human_actions:
                return True, perm, None

            # Check callback if provided
            if self.human_approval_callback:
                if self.human_approval_callback(tool_name, args):
                    self.approved_actions.add(action_key)
                    return True, perm, None

            # Must wait for human approval (Kết E: Chờ phê duyệt)
            reason = f"Hành động '{tool_name}' cho mã đặt chỗ '{code}' yêu cầu con người phê duyệt."
            return False, perm, reason

        return False, perm, f"Trạng thái phân quyền không xác định cho tool '{tool_name}'."

    def create_30s_handoff(
        self,
        status: HandoffStatus,
        reason: str,
        pending_action: Optional[str] = None,
        booking_info: Optional[Dict[str, Any]] = None,
        required_decision: Optional[str] = None,
    ) -> HumanHandoffRequest:
        """
        Tạo Gói bàn giao 30 giây (Human Handoff Package theo kiến trúc chuẩn):
        1. Trạng thái hiện tại
        2. Lý do cần người
        3. Dữ liệu ngữ cảnh: Tóm tắt những gì đã làm đến giờ
        4. Hành động đang chờ & Lựa chọn quyết định cụ thể
        """
        info = booking_info or {}
        decision = required_decision

        if not decision:
            if status == HandoffStatus.HUMAN_APPROVAL_REQUIRED:
                booking_code = info.get("booking_code", "UNKNOWN")
                price = info.get("price", info.get("total_price", "N/A"))
                price_str = f"{price:,.0f} VND" if isinstance(price, (int, float)) else str(price)
                decision = (
                    f"Bạn có đồng ý thực hiện '{pending_action}' cho vé {booking_code} "
                    f"với số tiền {price_str}? "
                    f"[1: Đồng ý thanh toán | 2: Huỷ bỏ giữ chỗ | 3: Tìm chuyến bay khác]"
                )
            elif status == HandoffStatus.BUDGET_EXCEEDED:
                decision = "Hết ngân sách thực thi. Bạn có muốn cấp thêm lượt gọi hay dừng lại xem xét?"
            elif status == HandoffStatus.LOOP_DETECTED:
                decision = "Phát hiện vòng lặp thao tác. Bạn có muốn đổi tiêu chí tìm kiếm hay huỷ tác vụ?"
            elif status == HandoffStatus.STALL_DETECTED:
                decision = "Agent bế tắc/vi phạm ràng buộc. Bạn có muốn nới lỏng ràng buộc hay chỉ định chuyến bay?"
            elif status == HandoffStatus.UNAUTHORIZED_ACTION:
                decision = f"Cảnh báo bảo mật: Agent cố gọi tool không được phép '{pending_action}'. Cần xem xét chính sách."
            else:
                decision = "Vui lòng xem xét thông tin và đưa ra chỉ dẫn để agent tiếp tục."

        return HumanHandoffRequest(
            status=status,
            reason=reason,
            completed_actions=list(self.completed_actions),
            pending_action=pending_action,
            relevant_booking_information=info,
            required_human_decision=decision,
        )

    # Alias for compatibility
    create_handoff = create_30s_handoff

