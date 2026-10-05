"""
Mock service package for flight database and tools.
"""
from mock_service.database import FlightDatabase, mock_db
from mock_service.tools import (
    search_flights,
    check_seat,
    book_seat,
    pay_booking,
    get_booking,
    cancel_booking,
    TOOL_PERMISSIONS,
    TOOL_REGISTRY,
    get_all_tools,
)

__all__ = [
    "FlightDatabase",
    "mock_db",
    "search_flights",
    "check_seat",
    "book_seat",
    "pay_booking",
    "get_booking",
    "cancel_booking",
    "TOOL_PERMISSIONS",
    "TOOL_REGISTRY",
    "get_all_tools",
]
