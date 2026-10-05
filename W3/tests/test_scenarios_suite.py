"""
Automated test suite verifying TC01 through TC08 across agents and harness.
"""
import pytest
from scenarios.test_scenarios import (
    TC01_NORMAL_BOOKING,
    TC02_FIRST_FLIGHT_UNAVAILABLE,
    TC03_ALL_EXCEED_BUDGET,
    TC04_NO_MATCHING_FLIGHT,
    TC05_TOOL_TIMEOUT_RETRY,
    TC06_PAYMENT_APPROVAL_REQUIRED,
    TC07_REPEATED_LOOP,
    TC08_INVALID_BOOKING,
)
from harness.base import Harness
from agents.react_agent import ReActAgent
from agents.plan_execute_agent import PlanThenExecuteAgent
from agents.hybrid_agent import HybridAgent
from mock_service.database import mock_db
from models.handoff import HandoffStatus


def test_tc01_normal_booking_react():
    tc = TC01_NORMAL_BOOKING
    tc.setup()
    harness = Harness(constraints=tc.constraints, agent_name="ReAct", auto_approve_human_actions=tc.auto_approve_human_actions)
    agent = ReActAgent(harness=harness, use_mock_llm=True)
    res = agent.run(tc.prompt)
    assert res["completed"] is True
    assert res["details"]["status"] == "confirmed"
    assert res["details"]["payment"] == "paid"


def test_tc02_first_flight_unavailable_react_and_hybrid():
    tc = TC02_FIRST_FLIGHT_UNAVAILABLE
    tc.setup()
    # ReAct should adapt dynamically and pick alternative flight
    harness_react = Harness(constraints=tc.constraints, agent_name="ReAct", auto_approve_human_actions=tc.auto_approve_human_actions)
    agent_react = ReActAgent(harness=harness_react, use_mock_llm=True)
    res_react = agent_react.run(tc.prompt)
    assert res_react["completed"] is True
    assert res_react["details"]["flight_id"] != "VN122"  # Adapted to alternative flight

    # Hybrid should also adapt via replanning
    tc.setup()
    harness_hybrid = Harness(constraints=tc.constraints, agent_name="Hybrid", auto_approve_human_actions=tc.auto_approve_human_actions)
    agent_hybrid = HybridAgent(harness=harness_hybrid, use_mock_llm=True)
    res_hybrid = agent_hybrid.run(tc.prompt)
    assert res_hybrid["completed"] is True
    assert res_hybrid["metrics"].replan_count >= 1

    # Plan-then-Execute (static) fails to adapt when first flight is unavailable
    tc.setup()
    harness_pe = Harness(constraints=tc.constraints, agent_name="PlanThenExecute", auto_approve_human_actions=tc.auto_approve_human_actions)
    agent_pe = PlanThenExecuteAgent(harness=harness_pe, use_mock_llm=True)
    res_pe = agent_pe.run(tc.prompt)
    assert res_pe["completed"] is False  # Shows architectural limitation of static planning!


def test_tc03_all_flights_exceed_budget():
    tc = TC03_ALL_EXCEED_BUDGET
    tc.setup()
    harness = Harness(constraints=tc.constraints, agent_name="ReAct", auto_approve_human_actions=tc.auto_approve_human_actions)
    agent = ReActAgent(harness=harness, use_mock_llm=True)
    res = agent.run(tc.prompt)
    assert res["completed"] is False
    assert len(mock_db.bookings) == 0  # No illegal booking created
    assert harness.get_metrics().constraint_satisfied is True


def test_tc04_no_matching_flight():
    tc = TC04_NO_MATCHING_FLIGHT
    tc.setup()
    harness = Harness(constraints=tc.constraints, agent_name="ReAct", auto_approve_human_actions=tc.auto_approve_human_actions)
    agent = ReActAgent(harness=harness, use_mock_llm=True)
    res = agent.run(tc.prompt)
    assert res["completed"] is False
    assert len(mock_db.bookings) == 0  # 0 hallucinated bookings


def test_tc05_tool_timeout_retry():
    tc = TC05_TOOL_TIMEOUT_RETRY
    tc.setup()
    harness = Harness(constraints=tc.constraints, agent_name="ReAct", auto_approve_human_actions=tc.auto_approve_human_actions)
    agent = ReActAgent(harness=harness, use_mock_llm=True)
    res = agent.run(tc.prompt)
    assert res["completed"] is True
    assert harness.budget_manager.retries_count >= 1


def test_tc06_payment_requires_approval():
    tc = TC06_PAYMENT_APPROVAL_REQUIRED
    tc.setup()
    harness = Harness(constraints=tc.constraints, agent_name="ReAct", auto_approve_human_actions=False)
    agent = ReActAgent(harness=harness, use_mock_llm=True)
    res = agent.run(tc.prompt)
    assert res["completed"] is False
    assert res["handoff"] is not None
    assert res["handoff"].status == HandoffStatus.HUMAN_APPROVAL_REQUIRED
    assert "pay_booking" in res["handoff"].pending_action


def test_tc07_repeated_tool_call_loop():
    tc = TC07_REPEATED_LOOP
    tc.setup()
    harness = Harness(constraints=tc.constraints, agent_name="ReAct")
    # Simulate repeated call to trigger loop detector at repeat_k=3
    harness.execute_tool("check_seat", {"flight_id": "VN122"})
    harness.execute_tool("check_seat", {"flight_id": "VN122"})
    harness.execute_tool("check_seat", {"flight_id": "VN122"})
    assert harness.loops_detected >= 1
    assert harness.active_handoff is not None
    assert harness.active_handoff.status == HandoffStatus.LOOP_DETECTED


def test_tc08_invalid_booking_fail_closed():
    tc = TC08_INVALID_BOOKING
    tc.setup()
    harness = Harness(constraints=tc.constraints, agent_name="ReAct")
    # Attempt booking on non-existent flight
    res = harness.execute_tool("book_seat", {"flight_id": "VN999", "seat_number": "12A", "passenger_name": "Tien Vo"})
    assert res["status"] == "error"
    assert "Flight 'VN999' does not exist" in res["hint"]
    assert len(mock_db.bookings) == 0
