"""
Integration tests for the three Agent designs:
- ReActAgent
- PlanThenExecuteAgent
- HybridAgent
Runs deterministically with Harness verification.
"""
import pytest
from models.constraints import UserConstraints
from harness.base import Harness
from agents.react_agent import ReActAgent
from agents.plan_execute_agent import PlanThenExecuteAgent
from agents.hybrid_agent import HybridAgent
from mock_service.database import mock_db


@pytest.fixture
def standard_constraints():
    return UserConstraints(
        origin="SGN",
        destination="HAN",
        departure_date="2026-10-15",
        max_budget=2000000.0,
        passenger_name="Tien Vo"
    )


def test_react_agent_execution(standard_constraints):
    mock_db.reset("TC01")
    harness = Harness(
        constraints=standard_constraints,
        agent_name="ReActAgent",
        auto_approve_human_actions=True
    )
    agent = ReActAgent(harness=harness, use_mock_llm=True)

    result = agent.run("Book a flight from SGN to HAN on 2026-10-15 under 2,000,000 VND for passenger Tien Vo.")

    assert result["completed"] is True
    assert result["details"]["status"] == "confirmed"
    assert result["details"]["payment"] == "paid"
    assert result["metrics"].total_tool_calls >= 4


def test_plan_execute_agent_execution(standard_constraints):
    mock_db.reset("TC01")
    harness = Harness(
        constraints=standard_constraints,
        agent_name="PlanThenExecuteAgent",
        auto_approve_human_actions=True
    )
    agent = PlanThenExecuteAgent(harness=harness, use_mock_llm=True)

    result = agent.run("Book a flight from SGN to HAN on 2026-10-15 under 2,000,000 VND for passenger Tien Vo.")

    assert result["completed"] is True
    assert result["details"]["status"] == "confirmed"
    assert result["details"]["payment"] == "paid"
    assert result["metrics"].total_tool_calls >= 4


def test_hybrid_agent_execution(standard_constraints):
    mock_db.reset("TC01")
    harness = Harness(
        constraints=standard_constraints,
        agent_name="HybridAgent",
        auto_approve_human_actions=True
    )
    agent = HybridAgent(harness=harness, use_mock_llm=True)

    result = agent.run("Book a flight from SGN to HAN on 2026-10-15 under 2,000,000 VND for passenger Tien Vo.")

    assert result["completed"] is True
    assert result["details"]["status"] == "confirmed"
    assert result["details"]["payment"] == "paid"
    assert result["metrics"].total_tool_calls >= 4
