"""
Unit tests for Mock Flight Tools.
"""
import pytest
from mock_service.database import mock_db
from mock_service.tools import (
    search_flights,
    check_seat,
    book_seat,
    pay_booking,
    get_booking,
    cancel_booking,
    TOOL_PERMISSIONS,
)
from models.trace import PermissionLevel


def setup_function():
    mock_db.reset()


def test_tool_permissions_configuration():
    assert TOOL_PERMISSIONS["search_flights"] == PermissionLevel.READ
    assert TOOL_PERMISSIONS["check_seat"] == PermissionLevel.READ
    assert TOOL_PERMISSIONS["get_booking"] == PermissionLevel.READ
    assert TOOL_PERMISSIONS["book_seat"] == PermissionLevel.WRITE
    assert TOOL_PERMISSIONS["pay_booking"] == PermissionLevel.HUMAN_APPROVAL
    assert TOOL_PERMISSIONS["cancel_booking"] == PermissionLevel.HUMAN_APPROVAL


def test_search_flights_found():
    result = search_flights.invoke({"origin": "SGN", "destination": "HAN", "date": "2026-10-15"})
    assert result["status"] == "ok"
    assert result["count"] > 0
    assert any(f["flight_id"] == "VN122" for f in result["flights"])


def test_search_flights_not_found():
    result = search_flights.invoke({"origin": "SGN", "destination": "HAN", "date": "2099-01-01"})
    assert result["status"] == "ok"
    assert result["count"] == 0
    assert result["flights"] == []


def test_check_seat_available():
    result = check_seat.invoke({"flight_id": "VN122"})
    assert result["status"] == "ok"
    assert result["seats_available"] > 0
    assert len(result["seats"]) > 0


def test_check_specific_seat():
    result = check_seat.invoke({"flight_id": "VN122", "seat_number": "12A"})
    assert result["status"] == "ok"
    assert result["seat_number"] == "12A"
    assert result["is_available"] is True


def test_book_seat_success():
    result = book_seat.invoke({"flight_id": "VN122", "seat_number": "12A", "passenger_name": "Tien Vo"})
    assert result["status"] == "ok"
    booking = result["booking"]
    assert booking["booking_code"] == "BK001"
    assert booking["status"] == "pending_payment"
    assert booking["payment"] == "unpaid"


def test_pay_booking_success():
    book_res = book_seat.invoke({"flight_id": "VN122", "seat_number": "12A", "passenger_name": "Tien Vo"})
    code = book_res["booking"]["booking_code"]

    pay_res = pay_booking.invoke({"booking_code": code, "payment_method": "credit_card"})
    assert pay_res["status"] == "ok"
    assert pay_res["booking"]["status"] == "confirmed"
    assert pay_res["booking"]["payment"] == "paid"


def test_cancel_booking():
    book_res = book_seat.invoke({"flight_id": "VN122", "seat_number": "12A", "passenger_name": "Tien Vo"})
    code = book_res["booking"]["booking_code"]

    cancel_res = cancel_booking.invoke({"booking_code": code, "reason": "Change of plans"})
    assert cancel_res["status"] == "ok"
    assert cancel_res["booking"]["status"] == "cancelled"
