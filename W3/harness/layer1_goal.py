"""
LỚP 1 HARNESS: ĐẠT MỤC TIÊU (GOAL & COMPLETION VALIDATOR)
Theo Sơ đồ Quyết định kiến trúc chuẩn (Kết A: vé confirmed, đã trả tiền).

Nhiệm vụ & Các Case đặc biệt:
- Case 1 (Deterministic Completion): Kiểm tra khách quan bằng code trên CSDL thật:
  booking exists AND status == 'confirmed' AND payment == 'paid' AND price <= budget AND đúng ngày/lộ trình.
- Case 2 (Chống Model tự nhận xong): Tuyệt đối không cho dừng nếu model tự xưng 'DONE' mà DB chưa xác nhận.
- Case 3 (Chống Bịa đặt - Hallucination, kiến trúc chuẩn): Đối chiếu chéo mã vé, giá, thông tin chuyến bay
  với dữ liệu thật trả về từ Mock Database.
"""
from typing import Tuple, Dict, Any, Optional
from models.constraints import UserConstraints
from mock_service.database import mock_db


class GoalValidatorLayer:
    """Lớp 1 Harness: Kiểm chứng khách quan Đạt mục tiêu (Kết A)."""

    def __init__(self, constraints: UserConstraints):
        self.constraints = constraints

    def reset(self):
        """Reset validation state."""
        pass


    def verify(self, booking_code: Optional[str]) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Kiểm tra 5 tiêu chí hoàn thành bằng code (kiến trúc chuẩn):
        1. Booking tồn tại trong CSDL
        2. status == 'confirmed'
        3. payment == 'paid'
        4. Chuyến bay khớp ràng buộc người dùng (origin, destination, date, depart_before)
        5. Giá vé <= ngân sách tối đa
        """
        if not booking_code:
            return False, "Chưa có mã đặt chỗ (booking_code).", {}

        booking = mock_db.bookings.get(booking_code)
        if not booking:
            # Case đặc biệt: Model tự chế mã booking không có trong CSDL (Hallucination)
            return False, f"Mã đặt chỗ '{booking_code}' không tồn tại trong hệ thống (Booking '{booking_code}' does not exist in database).", {}

        details = booking.to_safe_dict()

        # Kiểm tra trạng thái xác nhận
        if booking.status != "confirmed":
            return False, f"Trạng thái booking là '{booking.status}', chưa được xác nhận (Booking status is '{booking.status}', expected 'confirmed').", details

        # Kiểm tra trạng thái thanh toán
        if booking.payment != "paid":
            return False, f"Trạng thái thanh toán là '{booking.payment}', chưa thanh toán (Booking payment status is '{booking.payment}', expected 'paid').", details

        # Kiểm tra ngân sách
        if booking.price > self.constraints.max_budget:
            return False, f"Giá vé ({booking.price:,.0f} VND) vượt ngân sách tối đa ({self.constraints.max_budget:,.0f} VND).", details

        # Đối chiếu dữ liệu chuyến bay thực tế
        flight = mock_db.flights.get(booking.flight_id)
        if not flight:
            return False, f"Chuyến bay '{booking.flight_id}' không có trong kho vé.", details

        flight_dict = flight.to_summary()
        check_result = self.constraints.validate_flight(flight_dict)
        if not check_result.is_valid:
            violations_str = "; ".join(check_result.violations)
            return False, f"Chuyến bay vi phạm ràng buộc: {violations_str}", details

        # Kiểm tra tên hành khách
        if self.constraints.passenger_name and booking.passenger_name != self.constraints.passenger_name:
            return False, f"Tên hành khách '{booking.passenger_name}' không khớp '{self.constraints.passenger_name}'.", details

        return True, "Tiêu chí hoàn thành (Kết A: vé confirmed, đã trả tiền) được kiểm chứng thành công bằng code.", details

    # Alias for compatibility
    verify_completion = verify

