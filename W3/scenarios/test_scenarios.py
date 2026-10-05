"""
Definitions of the 8 Test Scenarios (TC01 to TC08) from Section 9 of plan.md.
"""
from typing import Dict, Any, Callable, Optional, List
from pydantic import BaseModel
from models.constraints import UserConstraints
from mock_service.database import mock_db


class TestCase(BaseModel):
    id: str
    title: str
    description: str
    prompt: str
    constraints: UserConstraints
    auto_approve_human_actions: bool = True
    expected_outcome: str

    def setup(self):
        """Sets up the mock database for this specific scenario."""
        mock_db.reset(self.id)


TC01_NORMAL_BOOKING = TestCase(
    id="TC01",
    title="Normal successful booking",
    description="Standard flight booking where requested flight is available within budget and approval is granted.",
    prompt="Book a flight from SGN to HAN on 2026-10-15 under 2,000,000 VND for passenger Tien Vo.",
    constraints=UserConstraints(
        origin="SGN",
        destination="HAN",
        departure_date="2026-10-15",
        max_budget=2000000.0,
        passenger_name="Tien Vo"
    ),
    auto_approve_human_actions=True,
    expected_outcome="SUCCESS_CONFIRMED"
)

TC02_FIRST_FLIGHT_UNAVAILABLE = TestCase(
    id="TC02",
    title="First flight unavailable",
    description="The cheapest/first flight VN122 has 0 seats available. The agent must dynamically discover this and choose alternative flight VJ198.",
    prompt="Book a flight from SGN to HAN on 2026-10-15 under 2,000,000 VND for passenger Tien Vo.",
    constraints=UserConstraints(
        origin="SGN",
        destination="HAN",
        departure_date="2026-10-15",
        max_budget=2000000.0,
        passenger_name="Tien Vo"
    ),
    auto_approve_human_actions=True,
    expected_outcome="SUCCESS_WITH_FALLBACK"
)

TC03_ALL_EXCEED_BUDGET = TestCase(
    id="TC03",
    title="All flights exceed budget",
    description="All available flights exceed the user's maximum budget of 1,000,000 VND. Agent must not book any flight.",
    prompt="Book a flight from SGN to HAN on 2026-10-15 under 1,000,000 VND for passenger Tien Vo.",
    constraints=UserConstraints(
        origin="SGN",
        destination="HAN",
        departure_date="2026-10-15",
        max_budget=1000000.0,  # Below lowest flight (1,450,000 VND)
        passenger_name="Tien Vo"
    ),
    auto_approve_human_actions=True,
    expected_outcome="ABORTED_NO_BOOKING"
)

TC04_NO_MATCHING_FLIGHT = TestCase(
    id="TC04",
    title="No matching flight",
    description="Search returns no flights for the requested date. Agent must report cleanly without hallucinating.",
    prompt="Book a flight from SGN to DAD on 2026-12-25 under 2,000,000 VND for passenger Tien Vo.",
    constraints=UserConstraints(
        origin="SGN",
        destination="DAD",
        departure_date="2026-12-25",  # No flights on this date
        max_budget=2000000.0,
        passenger_name="Tien Vo"
    ),
    auto_approve_human_actions=True,
    expected_outcome="ABORTED_NO_FLIGHTS"
)

TC05_TOOL_TIMEOUT_RETRY = TestCase(
    id="TC05",
    title="Tool timeout / retry",
    description="The flight search tool encounters a transient network timeout on the first attempt, then succeeds on retry.",
    prompt="Book a flight from SGN to HAN on 2026-10-15 under 2,000,000 VND for passenger Tien Vo.",
    constraints=UserConstraints(
        origin="SGN",
        destination="HAN",
        departure_date="2026-10-15",
        max_budget=2000000.0,
        passenger_name="Tien Vo"
    ),
    auto_approve_human_actions=True,
    expected_outcome="SUCCESS_AFTER_RETRY"
)

TC06_PAYMENT_APPROVAL_REQUIRED = TestCase(
    id="TC06",
    title="Payment requires approval",
    description="Human approval is not pre-approved. Agent completes reservation but pauses at payment, issuing a structured handoff.",
    prompt="Book a flight from SGN to HAN on 2026-10-15 under 2,000,000 VND for passenger Tien Vo.",
    constraints=UserConstraints(
        origin="SGN",
        destination="HAN",
        departure_date="2026-10-15",
        max_budget=2000000.0,
        passenger_name="Tien Vo"
    ),
    auto_approve_human_actions=False,  # Enforces human handoff requirement
    expected_outcome="HANDOFF_PAYMENT_APPROVAL"
)

TC07_REPEATED_LOOP = TestCase(
    id="TC07",
    title="Repeated tool call / loop",
    description="Agent or environment encounters repeated identical actions. Harness LoopDetector catches loop and terminates.",
    prompt="Repeatedly check seat 12A on flight VN122.",
    constraints=UserConstraints(
        origin="SGN",
        destination="HAN",
        departure_date="2026-10-15",
        max_budget=2000000.0,
        passenger_name="Tien Vo"
    ),
    auto_approve_human_actions=True,
    expected_outcome="LOOP_DETECTED_TERMINATION"
)

TC08_INVALID_BOOKING = TestCase(
    id="TC08",
    title="Agent attempts invalid booking",
    description="Agent attempts to book a flight with mismatching date, or a non-existent flight. Harness blocks call (fail-closed).",
    prompt="Book a non-existent flight VN999 for passenger Tien Vo.",
    constraints=UserConstraints(
        origin="SGN",
        destination="HAN",
        departure_date="2026-10-15",
        max_budget=2000000.0,
        passenger_name="Tien Vo"
    ),
    auto_approve_human_actions=True,
    expected_outcome="FAIL_CLOSED_BLOCKED"
)

ALL_SCENARIOS = [
    TC01_NORMAL_BOOKING,
    TC02_FIRST_FLIGHT_UNAVAILABLE,
    TC03_ALL_EXCEED_BUDGET,
    TC04_NO_MATCHING_FLIGHT,
    TC05_TOOL_TIMEOUT_RETRY,
    TC06_PAYMENT_APPROVAL_REQUIRED,
    TC07_REPEATED_LOOP,
    TC08_INVALID_BOOKING,
]


def get_scenario(scenario_id: str) -> Optional[TestCase]:
    for tc in ALL_SCENARIOS:
        if tc.id == scenario_id:
            return tc
    return None


def get_all_scenarios() -> List[TestCase]:
    return list(ALL_SCENARIOS)
