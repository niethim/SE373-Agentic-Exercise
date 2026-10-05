"""
Pydantic data models for flight booking domain.
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class Seat(BaseModel):
    seat_number: str
    class_type: str = "Economy"
    price: float
    is_available: bool = True


class Flight(BaseModel):
    flight_id: str
    airline: str
    origin: str
    destination: str
    departure_date: str  # YYYY-MM-DD
    departure_time: str  # HH:MM
    arrival_time: str    # HH:MM
    price: float
    seats_available: int
    seats: List[Seat] = Field(default_factory=list)

    def to_summary(self) -> Dict[str, Any]:
        """Data minimization: return only necessary summary information."""
        return {
            "flight_id": self.flight_id,
            "airline": self.airline,
            "origin": self.origin,
            "destination": self.destination,
            "departure_date": self.departure_date,
            "departure_time": self.departure_time,
            "arrival_time": self.arrival_time,
            "price": self.price,
            "seats_available": self.seats_available,
        }


class Booking(BaseModel):
    booking_code: str
    flight_id: str
    seat_number: str
    passenger_name: str
    price: float
    status: str = "pending_payment"  # pending_payment, confirmed, cancelled
    payment: str = "unpaid"           # unpaid, paid, refunded
    created_at: str = ""

    def to_safe_dict(self) -> Dict[str, Any]:
        """Returns clean booking details without leaking secrets."""
        return {
            "booking_code": self.booking_code,
            "flight_id": self.flight_id,
            "seat_number": self.seat_number,
            "passenger_name": self.passenger_name,
            "price": self.price,
            "status": self.status,
            "payment": self.payment,
        }


class PaymentReceipt(BaseModel):
    transaction_id: str
    booking_code: str
    amount: float
    payment_method: str
    status: str = "success"  # success, failed
    timestamp: str = ""
