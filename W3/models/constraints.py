"""
Structured user constraints representation and validation logic.
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ConstraintValidationResult(BaseModel):
    is_valid: bool
    violations: List[str] = Field(default_factory=list)


class UserConstraints(BaseModel):
    origin: str
    destination: str
    departure_date: str                 # Format: YYYY-MM-DD
    max_budget: float                   # Maximum price in VND
    preferred_time_before: Optional[str] = None  # e.g., "12:00"
    preferred_time_after: Optional[str] = None   # e.g., "06:00"
    passenger_name: str = "Tien Vo"

    def validate_flight(self, flight_dict: Dict[str, Any]) -> ConstraintValidationResult:
        """
        Validates if a flight satisfies all user constraints.
        Enforces Global Security Rule 8: Protect User Constraints.
        """
        violations = []
        origin = flight_dict.get("origin", "").upper()
        destination = flight_dict.get("destination", "").upper()
        date = flight_dict.get("departure_date", "")
        time = flight_dict.get("departure_time", "")
        price = float(flight_dict.get("price", 0))

        if origin != self.origin.upper():
            violations.append(f"Origin mismatch: requested '{self.origin}', got '{origin}'")
        if destination != self.destination.upper():
            violations.append(f"Destination mismatch: requested '{self.destination}', got '{destination}'")
        if date != self.departure_date:
            violations.append(f"Date mismatch: requested '{self.departure_date}', got '{date}'")
        if price > self.max_budget:
            violations.append(f"Price exceeds budget: {price:,.0f} VND > budget {self.max_budget:,.0f} VND")
        if self.preferred_time_before and time > self.preferred_time_before:
            violations.append(f"Flight departs after requested cutoff: {time} > {self.preferred_time_before}")
        if self.preferred_time_after and time < self.preferred_time_after:
            violations.append(f"Flight departs before requested time: {time} < {self.preferred_time_after}")

        return ConstraintValidationResult(
            is_valid=len(violations) == 0,
            violations=violations
        )

    def is_ok(self, flight_dict: Dict[str, Any]) -> bool:
        """Alias matching kiến trúc chuẩn: if not CONSTRAINTS.is_ok(flight): return {'status': 'denied'}"""
        return self.validate_flight(flight_dict).is_valid


# Alias matching kiến trúc chuẩn
Constraints = UserConstraints
