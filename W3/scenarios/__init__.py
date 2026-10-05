"""
Scenarios package containing test cases TC01 to TC08 defined in Section 9 of plan.md.
"""
from scenarios.test_scenarios import (
    TestCase,
    get_scenario,
    get_all_scenarios,
    TC01_NORMAL_BOOKING,
    TC02_FIRST_FLIGHT_UNAVAILABLE,
    TC03_ALL_EXCEED_BUDGET,
    TC04_NO_MATCHING_FLIGHT,
    TC05_TOOL_TIMEOUT_RETRY,
    TC06_PAYMENT_APPROVAL_REQUIRED,
    TC07_REPEATED_LOOP,
    TC08_INVALID_BOOKING,
)

__all__ = [
    "TestCase",
    "get_scenario",
    "get_all_scenarios",
    "TC01_NORMAL_BOOKING",
    "TC02_FIRST_FLIGHT_UNAVAILABLE",
    "TC03_ALL_EXCEED_BUDGET",
    "TC04_NO_MATCHING_FLIGHT",
    "TC05_TOOL_TIMEOUT_RETRY",
    "TC06_PAYMENT_APPROVAL_REQUIRED",
    "TC07_REPEATED_LOOP",
    "TC08_INVALID_BOOKING",
]
