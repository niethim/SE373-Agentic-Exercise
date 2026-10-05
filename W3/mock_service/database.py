"""
In-memory mock database for flights, seats, and bookings.
Supports resetting and scenario-specific condition simulation.
"""
from typing import Dict, List, Optional, Any
from copy import deepcopy
from datetime import datetime
from models.flight import Flight, Seat, Booking, PaymentReceipt


DEFAULT_FLIGHTS_DATA = [
    {
        "flight_id": "VN122",
        "airline": "Vietnam Airlines",
        "origin": "SGN",
        "destination": "HAN",
        "departure_date": "2026-10-15",
        "departure_time": "08:10",
        "arrival_time": "10:20",
        "price": 1350000.0,
        "seats_available": 3,
        "seats": [
            {"seat_number": "12A", "class_type": "Economy", "price": 1350000.0, "is_available": True},
            {"seat_number": "12B", "class_type": "Economy", "price": 1350000.0, "is_available": True},
            {"seat_number": "14C", "class_type": "Economy", "price": 1350000.0, "is_available": True},
        ]
    },
    {
        "flight_id": "VJ198",
        "airline": "Vietjet Air",
        "origin": "SGN",
        "destination": "HAN",
        "departure_date": "2026-10-15",
        "departure_time": "09:30",
        "arrival_time": "11:35",
        "price": 1650000.0,
        "seats_available": 2,
        "seats": [
            {"seat_number": "05A", "class_type": "Economy", "price": 1650000.0, "is_available": True},
            {"seat_number": "05B", "class_type": "Economy", "price": 1650000.0, "is_available": True},
        ]
    },
    {
        "flight_id": "QH118",
        "airline": "Bamboo Airways",
        "origin": "SGN",
        "destination": "HAN",
        "departure_date": "2026-10-15",
        "departure_time": "15:40",
        "arrival_time": "17:45",
        "price": 1640000.0,
        "seats_available": 2,
        "seats": [
            {"seat_number": "10A", "class_type": "Economy", "price": 1640000.0, "is_available": True},
            {"seat_number": "10B", "class_type": "Economy", "price": 1640000.0, "is_available": True},
        ]
    },
    {
        "flight_id": "VN134",
        "airline": "Vietnam Airlines",
        "origin": "SGN",
        "destination": "HAN",
        "departure_date": "2026-10-15",
        "departure_time": "18:20",
        "arrival_time": "20:25",
        "price": 2350000.0,
        "seats_available": 4,
        "seats": [
            {"seat_number": "08A", "class_type": "Economy", "price": 2350000.0, "is_available": True},
            {"seat_number": "08B", "class_type": "Economy", "price": 2350000.0, "is_available": True},
        ]
    },
    {
        "flight_id": "VN210",
        "airline": "Vietnam Airlines",
        "origin": "SGN",
        "destination": "DAD",
        "departure_date": "2026-10-07",
        "departure_time": "07:45",
        "arrival_time": "09:10",
        "price": 1750000.0,
        "seats_available": 2,
        "seats": [
            {"seat_number": "04A", "class_type": "Economy", "price": 1750000.0, "is_available": True},
            {"seat_number": "04B", "class_type": "Economy", "price": 1750000.0, "is_available": True},
        ]
    },
    {
        "flight_id": "VJ604",
        "airline": "Vietjet Air",
        "origin": "SGN",
        "destination": "DAD",
        "departure_date": "2026-10-07",
        "departure_time": "11:15",
        "arrival_time": "12:40",
        "price": 1320000.0,
        "seats_available": 2,
        "seats": [
            {"seat_number": "06A", "class_type": "Economy", "price": 1320000.0, "is_available": True},
        ]
    }
]


class FlightDatabase:
    def __init__(self):
        self.flights: Dict[str, Flight] = {}
        self.bookings: Dict[str, Booking] = {}
        self.payments: Dict[str, PaymentReceipt] = {}
        self.booking_counter: int = 1
        self.payment_counter: int = 1
        self.simulated_errors: Dict[str, Any] = {}
        self.reset()

    def reset(self, scenario_id: Optional[str] = None):
        """Resets the in-memory database to clean initial state."""
        self.flights.clear()
        self.bookings.clear()
        self.payments.clear()
        self.booking_counter = 1
        self.payment_counter = 1
        self.simulated_errors.clear()

        # Load flights
        for data in deepcopy(DEFAULT_FLIGHTS_DATA):
            seats = [Seat(**s) for s in data["seats"]]
            flight = Flight(
                flight_id=data["flight_id"],
                airline=data["airline"],
                origin=data["origin"],
                destination=data["destination"],
                departure_date=data["departure_date"],
                departure_time=data["departure_time"],
                arrival_time=data["arrival_time"],
                price=data["price"],
                seats_available=data["seats_available"],
                seats=seats
            )
            self.flights[flight.flight_id] = flight

        # Apply scenario-specific mutations if specified
        if scenario_id == "TC02":
            # TC02: First flight VN122 is unavailable/fully booked
            if "VN122" in self.flights:
                self.flights["VN122"].seats_available = 0
                for seat in self.flights["VN122"].seats:
                    seat.is_available = False

        elif scenario_id == "TC05":
            # TC05: Transient timeout on first search attempt
            self.simulated_errors["search_flights_remaining_failures"] = 1

    def search_flights(self, origin: str, destination: str, date: str) -> Dict[str, Any]:
        # Check simulated failures
        if self.simulated_errors.get("search_flights_remaining_failures", 0) > 0:
            self.simulated_errors["search_flights_remaining_failures"] -= 1
            return {
                "status": "error",
                "error": "timeout",
                "hint": "Network timeout occurred while contacting airline inventory. Please retry."
            }

        matches = []
        for flight in self.flights.values():
            if (
                flight.origin.upper() == origin.upper()
                and flight.destination.upper() == destination.upper()
                and flight.departure_date == date
            ):
                matches.append(flight.to_summary())

        # Sort matches by price ascending
        matches.sort(key=lambda x: x["price"])
        return {
            "status": "ok",
            "count": len(matches),
            "flights": matches
        }

    def check_seat(self, flight_id: str, seat_number: Optional[str] = None) -> Dict[str, Any]:
        flight = self.flights.get(flight_id)
        if not flight:
            return {
                "status": "error",
                "error": "flight_not_found",
                "hint": f"Flight '{flight_id}' does not exist in inventory."
            }

        if flight.seats_available <= 0:
            return {
                "status": "ok",
                "flight_id": flight_id,
                "seats_available": 0,
                "message": "Flight is fully booked.",
                "seats": []
            }

        if seat_number:
            seat = next((s for s in flight.seats if s.seat_number == seat_number), None)
            if not seat:
                return {
                    "status": "error",
                    "error": "seat_not_found",
                    "hint": f"Seat '{seat_number}' does not exist on flight '{flight_id}'."
                }
            return {
                "status": "ok",
                "flight_id": flight_id,
                "seat_number": seat.seat_number,
                "class_type": seat.class_type,
                "price": seat.price,
                "is_available": seat.is_available
            }

        # Return available seats
        available_seats = [
            {"seat_number": s.seat_number, "class_type": s.class_type, "price": s.price, "is_available": s.is_available}
            for s in flight.seats if s.is_available
        ]
        return {
            "status": "ok",
            "flight_id": flight_id,
            "seats_available": len(available_seats),
            "seats": available_seats
        }

    def book_seat(self, flight_id: str, seat_number: str, passenger_name: str) -> Dict[str, Any]:
        flight = self.flights.get(flight_id)
        if not flight:
            return {
                "status": "error",
                "error": "flight_not_found",
                "hint": f"Flight '{flight_id}' does not exist."
            }

        seat = next((s for s in flight.seats if s.seat_number == seat_number), None)
        if not seat:
            return {
                "status": "error",
                "error": "seat_not_found",
                "hint": f"Seat '{seat_number}' does not exist on flight '{flight_id}'."
            }

        if not seat.is_available:
            return {
                "status": "error",
                "error": "seat_unavailable",
                "hint": f"Seat '{seat_number}' is already occupied or reserved."
            }

        # Reserve seat
        seat.is_available = False
        flight.seats_available = max(0, flight.seats_available - 1)

        booking_code = f"BK{self.booking_counter:03d}"
        self.booking_counter += 1

        booking = Booking(
            booking_code=booking_code,
            flight_id=flight_id,
            seat_number=seat_number,
            passenger_name=passenger_name,
            price=seat.price,
            status="pending_payment",
            payment="unpaid",
            created_at=datetime.now().isoformat()
        )
        self.bookings[booking_code] = booking

        return {
            "status": "ok",
            "message": "Seat reserved successfully. Payment required to confirm.",
            "booking": booking.to_safe_dict()
        }

    def pay_booking(self, booking_code: str, payment_method: str = "credit_card") -> Dict[str, Any]:
        booking = self.bookings.get(booking_code)
        if not booking:
            return {
                "status": "error",
                "error": "booking_not_found",
                "hint": f"Booking code '{booking_code}' does not exist."
            }

        if booking.status == "confirmed" and booking.payment == "paid":
            return {
                "status": "ok",
                "message": "Booking is already paid and confirmed.",
                "booking": booking.to_safe_dict()
            }

        if booking.status == "cancelled":
            return {
                "status": "error",
                "error": "booking_cancelled",
                "hint": f"Cannot pay for cancelled booking '{booking_code}'."
            }

        # Process payment
        tx_id = f"TX{self.payment_counter:04d}"
        self.payment_counter += 1

        booking.payment = "paid"
        booking.status = "confirmed"

        receipt = PaymentReceipt(
            transaction_id=tx_id,
            booking_code=booking_code,
            amount=booking.price,
            payment_method=payment_method,
            status="success",
            timestamp=datetime.now().isoformat()
        )
        self.payments[tx_id] = receipt

        return {
            "status": "ok",
            "message": "Payment successful. Booking confirmed.",
            "transaction_id": tx_id,
            "booking": booking.to_safe_dict()
        }

    def get_booking(self, booking_code: str) -> Dict[str, Any]:
        booking = self.bookings.get(booking_code)
        if not booking:
            return {
                "status": "error",
                "error": "booking_not_found",
                "hint": f"Booking code '{booking_code}' not found."
            }
        return {
            "status": "ok",
            "booking": booking.to_safe_dict()
        }

    def cancel_booking(self, booking_code: str, reason: str = "User requested") -> Dict[str, Any]:
        booking = self.bookings.get(booking_code)
        if not booking:
            return {
                "status": "error",
                "error": "booking_not_found",
                "hint": f"Booking code '{booking_code}' not found."
            }

        if booking.status == "cancelled":
            return {
                "status": "ok",
                "message": "Booking is already cancelled.",
                "booking": booking.to_safe_dict()
            }

        # Release seat
        flight = self.flights.get(booking.flight_id)
        if flight:
            seat = next((s for s in flight.seats if s.seat_number == booking.seat_number), None)
            if seat:
                seat.is_available = True
                flight.seats_available += 1

        booking.status = "cancelled"
        if booking.payment == "paid":
            booking.payment = "refunded"

        return {
            "status": "ok",
            "message": f"Booking {booking_code} cancelled. Reason: {reason}",
            "booking": booking.to_safe_dict()
        }


# Global singleton instance for mock database
mock_db = FlightDatabase()
