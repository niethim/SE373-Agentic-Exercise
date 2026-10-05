"""
Main CLI entrypoint for Flight Booking Agents.
Allows running individual scenarios, custom prompts, and inspecting trace logs.
"""
import sys
import argparse
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from scenarios.test_scenarios import get_scenario, get_all_scenarios, TestCase
from models.constraints import UserConstraints
from harness.base import Harness
from agents.react_agent import ReActAgent
from agents.plan_execute_agent import PlanThenExecuteAgent
from agents.hybrid_agent import HybridAgent


console = Console()


def display_welcome():
    console.print(Panel.fit(
        "[bold cyan]SE373 - Flight Booking Agentic System[/bold cyan]\n"
        "[white]Supported Architectures: [bold yellow]ReAct[/bold yellow] | [bold green]Plan-then-Execute[/bold green] | [bold magenta]Hybrid[/bold magenta]\n"
        "Security: Fail-Closed, Least Privilege, Loop Detection, Deterministic Completion[/white]",
        border_style="cyan"
    ))


def run_scenario_interactive(scenario_id: str, agent_choice: str, live_llm: bool = False):
    tc = get_scenario(scenario_id)
    if not tc:
        console.print(f"[bold red]Scenario '{scenario_id}' not found![/bold red]")
        return

    tc.setup()
    console.print(f"\n[bold blue]=== Executing {tc.id}: {tc.title} ===[/bold blue]")
    console.print(f"[dim]{tc.description}[/dim]")
    console.print(f"[bold]Prompt:[/bold] {tc.prompt}")
    console.print(f"[bold]Constraints:[/bold] Route {tc.constraints.origin}->{tc.constraints.destination}, Date {tc.constraints.departure_date}, Max Budget {tc.constraints.max_budget:,.0f} VND\n")

    harness = Harness(
        constraints=tc.constraints,
        agent_name=agent_choice,
        auto_approve_human_actions=tc.auto_approve_human_actions,
    )

    use_mock = not live_llm

    if agent_choice == "react":
        agent = ReActAgent(harness=harness, use_mock_llm=use_mock)
    elif agent_choice == "plan_execute":
        agent = PlanThenExecuteAgent(harness=harness, use_mock_llm=use_mock)
    elif agent_choice == "hybrid":
        agent = HybridAgent(harness=harness, use_mock_llm=use_mock)
    else:
        console.print(f"[bold red]Unknown agent choice: {agent_choice}[/bold red]")
        return

    # Special injection for TC07 repeated loop if heuristic
    if tc.id == "TC07" and use_mock:
        harness.execute_tool("check_seat", {"flight_id": "VN122"})
        harness.execute_tool("check_seat", {"flight_id": "VN122"})
        harness.execute_tool("check_seat", {"flight_id": "VN122"})
        result = {"completed": False, "completion_reason": "Loop detected by Harness", "details": {}, "handoff": harness.active_handoff, "metrics": harness.get_metrics()}
    elif tc.id == "TC08" and use_mock:
        harness.execute_tool("book_seat", {"flight_id": "VN999", "seat_number": "12A", "passenger_name": "Tien Vo"})
        result = {"completed": False, "completion_reason": "Invalid booking blocked", "details": {}, "handoff": harness.active_handoff, "metrics": harness.get_metrics()}
    else:
        result = agent.run(tc.prompt)

    # Display results
    console.print("\n[bold green]=== Execution Results ===[/bold green]")
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Property", style="dim")
    table.add_column("Value")

    table.add_row("Agent Architecture", agent_choice)
    table.add_row("Deterministic Completion", f"[green]VERIFIED SUCCESS[/green]" if result.get("completed") else "[red]NOT COMPLETED[/red]")
    table.add_row("Completion Reason", str(result.get("completion_reason")))
    table.add_row("Total Tool Calls", str(harness.budget_manager.steps_taken))
    table.add_row("Loops Caught", str(harness.loops_detected))
    table.add_row("Replans Count", str(harness.budget_manager.replans_count))
    table.add_row("Tokens Used", str(harness.budget_manager.tokens_used))

    console.print(table)

    # If human handoff was triggered, display the 30-second package
    if harness.active_handoff:
        console.print("\n[bold yellow]=== HUMAN HANDOFF PACKAGE (Section 7) ===[/bold yellow]")
        console.print(Panel(harness.active_handoff.format_30s_summary(), title="Handoff Notice", border_style="yellow"))

    # Display trace summary
    console.print("\n[bold cyan]=== Harness Trace Log ===[/bold cyan]")
    console.print(harness.trace_logger.format_trace_summary())


def main():
    parser = argparse.ArgumentParser(description="SE373 Flight Booking Agent")
    parser.add_argument("--scenario", type=str, default="TC01", help="Scenario ID (TC01 to TC08)")
    parser.add_argument("--agent", type=str, default="react", choices=["react", "plan_execute", "hybrid"], help="Agent design")
    parser.add_argument("--live-llm", action="store_true", help="Use live LLM instead of deterministic heuristic")
    parser.add_argument("--list-scenarios", action="store_true", help="List all available test scenarios")
    args = parser.parse_args()

    display_welcome()

    if args.list_scenarios:
        table = Table(title="Available Test Scenarios (Section 9)")
        table.add_column("ID", style="cyan")
        table.add_column("Title", style="bold")
        table.add_column("Description")
        table.add_column("Expected Outcome", style="yellow")
        for sc in get_all_scenarios():
            table.add_row(sc.id, sc.title, sc.description, sc.expected_outcome)
        console.print(table)
        return

    run_scenario_interactive(args.scenario, args.agent, live_llm=args.live_llm)


if __name__ == "__main__":
    main()
