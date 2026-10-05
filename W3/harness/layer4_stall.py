"""
LỚP 4 HARNESS: BẾ TẮC & BẢO VỆ RÀNG BUỘC (STALL & GOAL DRIFT DETECTOR)
Theo Sơ đồ Quyết định kiến trúc chuẩn (Kết D: đổi hướng, vẫn 1/2 ràng buộc) & kiến trúc chuẩn, 1806.

Nhiệm vụ & Các Case đặc biệt:
- Case 1 (Đo đại lượng tiến triển): Theo dõi tiến trình bài toán qua 5 mốc (0.0 -> 0.25 -> 0.5 -> 0.75 -> 1.0).
  Nếu tiến độ đứng yên suốt stall_n vòng liên tiếp mặc dù agent đổi tool liên tục -> Báo động BẾ TẮC (Kết D).
- Case 2 (Chống Quên Yêu Cầu - Goal Drift, kiến trúc chuẩn):
  CONSTRAINTS = Constraints(date="2026-10-07", depart_before="12:00", max_price=2_000_000).
  Kiểm tra if not CONSTRAINTS.is_ok(flight) trước khi book -> Trả về {'status': 'denied'} nếu sai giờ, sai ngày, sai điểm đến.
- Case 3 (Xử lý chuỗi rỗng / không có chuyến, kiến trúc chuẩn):
  Phân biệt rõ {"status": "ok", "flights": []} (thật sự không có chuyến) vs {"status": "error", "error": "timeout"}.
"""
from typing import Dict, Any, Optional, Tuple
from models.constraints import UserConstraints
from mock_service.database import mock_db


class StallDetectorLayer:
    """Lớp 4 Harness: Phát hiện bế tắc và bảo vệ ràng buộc gốc chống Goal Drift (Kết D)."""

    STAGE_INIT = 0.0
    STAGE_SEARCHED = 0.25
    STAGE_SEAT_CHECKED = 0.50
    STAGE_BOOKED = 0.75
    STAGE_PAID = 1.00

    def __init__(self, constraints: UserConstraints, stall_n: int = 4, stall_threshold: Optional[int] = None):
        self.constraints = constraints
        self.stall_n = stall_threshold if stall_threshold is not None else stall_n
        self.current_progress: float = self.STAGE_INIT
        self.last_progress: Optional[float] = None
        self.stall_count: int = 0

    def reset(self):
        self.current_progress = self.STAGE_INIT
        self.last_progress = None
        self.stall_count = 0

    def validate_constraints(self, tool_name: str, args: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Case đặc biệt 2: Chống Quên Yêu Cầu (Goal Drift - kiến trúc chuẩn).
        Kiểm tra trước khi thực thi tool: chặn agent đổi hướng sai lệch điểm đến, ngày hoặc ngân sách.
        """
        if tool_name == "search_flights":
            origin = args.get("origin", "").upper()
            dest = args.get("destination", "").upper()
            date = args.get("date", "")

            if origin != self.constraints.origin.upper():
                return False, f"Chệch mục tiêu ban đầu: Điểm đi '{origin}' khác yêu cầu '{self.constraints.origin}' (Origin mismatch, violates constraint - kiến trúc chuẩn)."
            if dest != self.constraints.destination.upper():
                return False, f"Chệch mục tiêu ban đầu: Điểm đến '{dest}' khác yêu cầu '{self.constraints.destination}' (Destination mismatch, Destination violates constraint - kiến trúc chuẩn)."
            if date != self.constraints.departure_date:
                return False, f"Chệch mục tiêu ban đầu: Ngày bay '{date}' khác ngày yêu cầu '{self.constraints.departure_date}' (Date mismatch, Date violates constraint - kiến trúc chuẩn)."

        elif tool_name == "book_seat":
            flight_id = args.get("flight_id")
            passenger_name = args.get("passenger_name", "")
            seat_number = args.get("seat_number")

            flight = mock_db.flights.get(flight_id)
            if not flight:
                return False, f"Chuyến bay '{flight_id}' không tồn tại trong hệ thống (Flight '{flight_id}' does not exist in inventory)."

            # Dùng CONSTRAINTS.is_ok(flight) theo đúng kiến trúc chuẩn
            if not self.constraints.is_ok(flight.to_summary()):
                check_res = self.constraints.validate_flight(flight.to_summary())
                violations = "; ".join(check_res.violations)
                return False, f"Từ chối hành động: Chuyến bay {flight_id} không thỏa mãn ràng buộc (Flight violates constraints: {violations})."

            # Kiểm tra giá ghế cụ thể so với ngân sách
            seat = next((s for s in flight.seats if s.seat_number == seat_number), None)
            if seat and seat.price > self.constraints.max_budget:
                return False, f"Ghế {seat_number} giá {seat.price:,.0f} VND vượt ngân sách (Seat {seat_number} price {seat.price:,.0f} VND exceeds budget {self.constraints.max_budget:,.0f} VND)."

            if self.constraints.passenger_name and passenger_name and passenger_name != self.constraints.passenger_name:
                return False, f"Tên hành khách '{passenger_name}' không khớp yêu cầu '{self.constraints.passenger_name}' (Passenger name does not match requested passenger)."

        elif tool_name == "pay_booking":
            booking_code = args.get("booking_code")
            booking = mock_db.bookings.get(booking_code)
            if booking and booking.price > self.constraints.max_budget:
                return False, f"Booking price {booking.price:,.0f} VND exceeds user budget {self.constraints.max_budget:,.0f} VND"

        return True, None

    def update_progress(self, tool_name: str, args: Dict[str, Any], observation: Dict[str, Any]) -> float:
        """Cập nhật đại lượng tiến độ bài toán dựa trên kết quả tool."""
        if observation.get("status") != "ok":
            return self.current_progress

        if tool_name == "search_flights":
            flights = observation.get("flights", [])
            if flights and self.current_progress < self.STAGE_SEARCHED:
                self.current_progress = self.STAGE_SEARCHED

        elif tool_name == "check_seat":
            seats_avail = observation.get("seats_available", 0)
            if seats_avail > 0 and self.current_progress < self.STAGE_SEAT_CHECKED:
                self.current_progress = self.STAGE_SEAT_CHECKED

        elif tool_name == "book_seat":
            booking = observation.get("booking", {})
            if booking.get("booking_code") and self.current_progress < self.STAGE_BOOKED:
                self.current_progress = self.STAGE_BOOKED

        elif tool_name == "pay_booking":
            booking = observation.get("booking", {})
            if booking.get("status") == "confirmed" and booking.get("payment") == "paid":
                self.current_progress = self.STAGE_PAID

        return self.current_progress

    # Aliases for compatibility
    update_from_tool = update_progress
    validate_tool_call = validate_constraints

    def check_stall(self, tool_name: Optional[str] = None, args: Optional[Dict[str, Any]] = None, raw_result: Optional[Dict[str, Any]] = None) -> Tuple[bool, Optional[str]]:
        """
        Case đặc biệt 1: Kiểm tra bế tắc tiến trình (kiến trúc chuẩn & 1388).
        Nếu progress đứng yên qua stall_n vòng -> Trả về (True, message).
        """
        if self.last_progress is not None and self.current_progress <= self.last_progress:
            self.stall_count += 1
        else:
            self.stall_count = 0

        self.last_progress = self.current_progress

        if self.stall_count >= self.stall_n:
            return True, f"Phát hiện bế tắc: Tiến độ đứng yên tại mốc {self.current_progress} qua {self.stall_count} vòng đổi hướng liên tiếp (Kết D: bế tắc)."

        return False, None

