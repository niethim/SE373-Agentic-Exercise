"""
Mock flight tools complying with Section 4 of plan.md.
Includes LangChain tool definitions and permission bindings.
"""
from typing import Optional, Dict, Any, List
from langchain_core.tools import tool
from models.trace import PermissionLevel
from mock_service.database import mock_db


TOOL_PERMISSIONS: Dict[str, PermissionLevel] = {
    "search_flights": PermissionLevel.READ,
    "check_seat": PermissionLevel.READ,
    "get_booking": PermissionLevel.READ,
    "book_seat": PermissionLevel.WRITE,
    "pay_booking": PermissionLevel.HUMAN_APPROVAL,
    "cancel_booking": PermissionLevel.HUMAN_APPROVAL,
}


@tool
def search_flights(origin: str, destination: str, date: str) -> Dict[str, Any]:
    """
    Search available flights between origin and destination on a specific date.
    Args:
        origin: 3-letter IATA code, e.g., 'SGN'.
        destination: 3-letter IATA code, e.g., 'HAN'.
        date: Departure date in 'YYYY-MM-DD' format, e.g., '2026-10-15'.
    """
    return mock_db.search_flights(origin=origin, destination=destination, date=date)


@tool
def check_seat(flight_id: str, seat_number: Optional[str] = None) -> Dict[str, Any]:
    """
    Check seat availability and pricing for a given flight.
    Args:
        flight_id: The flight number, e.g., 'VN122'.
        seat_number: Optional specific seat number, e.g., '12A'. If omitted, returns all available seats.
    """
    return mock_db.check_seat(flight_id=flight_id, seat_number=seat_number)


@tool
def book_seat(flight_id: str, seat_number: str, passenger_name: str) -> Dict[str, Any]:
    """
    Reserve a seat on a flight for a passenger. Returns a booking code with status 'pending_payment'.
    Args:
        flight_id: The flight number, e.g., 'VN122'.
        seat_number: Selected seat, e.g., '12A'.
        passenger_name: Passenger full name, e.g., 'Tien Vo'.
    """
    return mock_db.book_seat(flight_id=flight_id, seat_number=seat_number, passenger_name=passenger_name)


@tool
def pay_booking(booking_code: str, payment_method: str = "credit_card") -> Dict[str, Any]:
    """
    Execute payment for an existing booking code. Requires human approval before invocation.
    Args:
        booking_code: The booking code, e.g., 'BK001'.
        payment_method: Payment method, e.g., 'credit_card'.
    """
    return mock_db.pay_booking(booking_code=booking_code, payment_method=payment_method)


@tool
def get_booking(booking_code: str) -> Dict[str, Any]:
    """
    Retrieve current status and details of an existing booking.
    Args:
        booking_code: The booking code, e.g., 'BK001'.
    """
    return mock_db.get_booking(booking_code=booking_code)


@tool
def cancel_booking(booking_code: str, reason: str = "User requested") -> Dict[str, Any]:
    """
    Cancel an existing booking. Requires human approval before invocation.
    Args:
        booking_code: The booking code, e.g., 'BK001'.
        reason: Justification for cancellation.
    """
    return mock_db.cancel_booking(booking_code=booking_code, reason=reason)


TOOL_REGISTRY: Dict[str, Any] = {
    "search_flights": search_flights,
    "check_seat": check_seat,
    "book_seat": book_seat,
    "pay_booking": pay_booking,
    "get_booking": get_booking,
    "cancel_booking": cancel_booking,
}


def get_all_tools() -> List[Any]:
    """Returns a list of all registered LangChain tool objects."""
    return list(TOOL_REGISTRY.values())
