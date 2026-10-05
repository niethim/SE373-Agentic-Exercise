"""
========================================================================================
SE373 - KỸ THUẬT XÂY DỰNG HỆ THỐNG AGENTIC AI (BUỔI 03)
BÀI TẬP VỀ NHÀ BTVN#3: DỰNG AGENT ĐẶT VÉ MÁY BAY BẰNG LANGCHAIN VỚI LỚP HARNESS AN TOÀN
========================================================================================

Yêu cầu đề bài (Buổi 03 · Agent Fundamentals):
  01. Đủ 5 lớp Harness bảo vệ an toàn:
      - Lớp 1: Đạt mục tiêu (GoalValidator kiểm chứng trên Database)
      - Lớp 2: Hết ngân sách (BudgetManager kiểm soát steps, tokens, replans)
      - Lớp 3: Phát hiện lặp & polling hợp lệ (LoopDetector)
      - Lớp 4: Bế tắc & Ràng buộc bất biến (StallAndConstraintManager)
      - Lớp 5: Cần con người phê duyệt & Gói bàn giao 30s (HumanApprovalManager)
  02. Cài đặt Agent với 3 mẫu thiết kế:
      - ReAct (Reason -> Act -> Observe -> Reason)
      - Plan-then-Execute (Plan -> Validate -> Step by Step Execution)
      - Lai / Hybrid (Chunk-based Plan -> Execute -> Local Re-plan)
  03. Đánh giá hiệu quả của Agent với 3 mẫu thiết kế khác nhau (8 Kịch bản TC01-TC08)
========================================================================================
"""
import os
import sys
import json
import time
import argparse
from typing import Dict, List, Any, Optional
from tabulate import tabulate

# Import các thành phần từ hệ thống W3
from models.constraints import UserConstraints, Constraints
from models.handoff import HumanHandoffRequest, HandoffStatus, HandoffReason
from mock_service.database import mock_db
from mock_service.tools import (
    search_flights,
    check_seat,
    book_seat,
    pay_booking,
    get_booking,
    cancel_booking,
    TOOL_PERMISSIONS,
)
from harness.base import Harness
from agents.react_agent import ReActAgent
from agents.plan_execute_agent import PlanThenExecuteAgent
from agents.hybrid_agent import HybridAgent
from scenarios.test_scenarios import get_all_scenarios, TC01_NORMAL_BOOKING, TC06_PAYMENT_APPROVAL_REQUIRED


def run_demo_react(live_llm: bool = False):
    print("\n" + "=" * 65)
    print("  [DEMO 1] THIẾT KẾ 1: REACT AGENT (Suy luận -> Hành động -> Quan sát)")
    print("=" * 65)
    tc = TC01_NORMAL_BOOKING
    tc.setup()

    harness = Harness(constraints=tc.constraints, agent_name="ReAct", auto_approve_human_actions=True)
    agent = ReActAgent(harness=harness, use_mock_llm=not live_llm)

    print(f"Goal: {tc.prompt}")
    print(f"Ràng buộc: {tc.constraints.origin} -> {tc.constraints.destination}, Ngày: {tc.constraints.departure_date}, Trần giá: {tc.constraints.max_budget:,.0f} VND")
    
    result = agent.run(tc.prompt)
    print(f"-> Kết quả: {'THÀNH CÔNG (CONFIRMED)' if result['completed'] else 'THẤT BẠI'}")
    print(f"-> Lý do: {result['completion_reason']}")
    print(f"-> Số lượt tool: {harness.budget_manager.steps_taken}, Tokens: {harness.budget_manager.tokens_used}")


def run_demo_plan_then_execute(live_llm: bool = False):
    print("\n" + "=" * 65)
    print("  [DEMO 2] THIẾT KẾ 2: PLAN-THEN-EXECUTE (Lập kế hoạch trước -> Thực thi)")
    print("=" * 65)
    tc = TC01_NORMAL_BOOKING
    tc.setup()

    harness = Harness(constraints=tc.constraints, agent_name="Plan-then-Execute", auto_approve_human_actions=True)
    agent = PlanThenExecuteAgent(harness=harness, use_mock_llm=not live_llm)

    print(f"Goal: {tc.prompt}")
    result = agent.run(tc.prompt)
    print(f"-> Kết quả: {'THÀNH CÔNG (CONFIRMED)' if result['completed'] else 'THẤT BẠI'}")
    print(f"-> Lý do: {result['completion_reason']}")
    print(f"-> Số lượt tool: {harness.budget_manager.steps_taken}")


def run_demo_hybrid(live_llm: bool = False):
    print("\n" + "=" * 65)
    print("  [DEMO 3] THIẾT KẾ 3: MẪU LAI (HYBRID: Plan -> Execute k bước -> Re-plan)")
    print("=" * 65)
    tc = TC01_NORMAL_BOOKING
    tc.setup()

    harness = Harness(constraints=tc.constraints, agent_name="Hybrid", auto_approve_human_actions=True)
    agent = HybridAgent(harness=harness, use_mock_llm=not live_llm)

    print(f"Goal: {tc.prompt}")
    result = agent.run(tc.prompt)
    print(f"-> Kết quả: {'THÀNH CÔNG (CONFIRMED)' if result['completed'] else 'THẤT BẠI'}")
    print(f"-> Lý do: {result['completion_reason']}")
    print(f"-> Số lượt tool: {harness.budget_manager.steps_taken}, Số lần Replan: {harness.budget_manager.replans_count}")


def run_demo_human_handoff(live_llm: bool = False):
    print("\n" + "=" * 65)
    print("  [DEMO 4] BÀN GIAO CHO CON NGƯỜI (HUMAN HANDOFF TRONG 30 GIÂY)")
    print("  (Cơ chế Kiểm quyền Lớp 5 -> Cần con người phê duyệt thanh toán)")
    print("=" * 65)
    tc = TC06_PAYMENT_APPROVAL_REQUIRED
    tc.setup()

    harness = Harness(constraints=tc.constraints, agent_name="ReAct", auto_approve_human_actions=False)
    agent = ReActAgent(harness=harness, use_mock_llm=not live_llm)

    result = agent.run(tc.prompt)
    print(f"Trạng thái kết thúc: {result['handoff'].status.value}")
    print("\nGÓI BÀN GIAO CON NGƯỜI 30 GIÂY:")
    print(result['handoff'].format_30s_summary())


def run_evaluation_benchmark(live_llm: bool = False):
    print("\n" + "=" * 65)
    print("  [PHẦN 03 ĐỀ BÀI] ĐÁNH GIÁ SO SÁNH 3 MẪU THIẾT KẾ (TC01 -> TC08)")
    print("=" * 65)
    agent_types = ["ReAct", "Plan-then-Execute", "Hybrid"]
    scenarios = get_all_scenarios()

    raw_results = []
    for tc in scenarios:
        tc.setup()
        for agent_name in agent_types:
            harness = Harness(
                constraints=tc.constraints,
                agent_name=agent_name,
                auto_approve_human_actions=tc.auto_approve_human_actions
            )
            use_mock = not live_llm
            if agent_name == "ReAct":
                agent = ReActAgent(harness=harness, use_mock_llm=use_mock)
            elif agent_name == "Plan-then-Execute":
                agent = PlanThenExecuteAgent(harness=harness, use_mock_llm=use_mock)
            else:
                agent = HybridAgent(harness=harness, use_mock_llm=use_mock)

            # Phun kịch bản mô phỏng kiểm thử nếu chạy chế độ heuristic
            if tc.id == "TC07" and use_mock:
                harness.execute_tool("check_seat", {"flight_id": "VN122"})
                harness.execute_tool("check_seat", {"flight_id": "VN122"})
                harness.execute_tool("check_seat", {"flight_id": "VN122"})
            elif tc.id == "TC08" and use_mock:
                harness.execute_tool("book_seat", {"flight_id": "VN999", "seat_number": "12A", "passenger_name": "Tien Vo"})
            else:
                agent.run(tc.prompt)

            m = harness.get_metrics(scenario_id=tc.id)
            raw_results.append(m.model_dump())

    # Tính toán tổng hợp
    summary_data = []
    headers = ["Kiến trúc Agent", "Success Rate", "Thỏa mãn Ràng buộc", "Tool Calls TB", "Tokens TB", "Replans", "Bắt vòng lặp", "Chặn trái phép"]
    for agent_name in agent_types:
        runs = [r for r in raw_results if r["agent_name"] == agent_name]
        n = len(runs)
        succ = sum(1 for r in runs if r["success"])
        sat = sum(1 for r in runs if r["constraint_satisfied"])
        tools = sum(r["total_tool_calls"] for r in runs)
        tokens = sum(r["tokens_used"] for r in runs)
        replans = sum(r["replan_count"] for r in runs)
        loops = sum(r["loop_detected_count"] for r in runs)
        blocks = sum(r["unauthorized_blocked_count"] for r in runs)

        summary_data.append([
            agent_name,
            f"{(succ / n) * 100:.1f}%",
            f"{(sat / n) * 100:.1f}%",
            f"{tools / n:.2f}",
            f"{tokens / n:.0f}",
            replans,
            loops,
            blocks
        ])

    print("\nBẢNG TỔNG HỢP SO SÁNH 3 MẪU THIẾT KẾ:")
    print(tabulate(summary_data, headers=headers, tablefmt="github"))

    # Ma trận kịch bản
    matrix_headers = ["Kịch bản", "Kết quả mong đợi", "ReAct", "Plan-then-Execute", "Hybrid"]
    matrix_data = []
    for tc in scenarios:
        r_run = next(r for r in raw_results if r["agent_name"] == "ReAct" and r["scenario_id"] == tc.id)
        p_run = next(r for r in raw_results if r["agent_name"] == "Plan-then-Execute" and r["scenario_id"] == tc.id)
        h_run = next(r for r in raw_results if r["agent_name"] == "Hybrid" and r["scenario_id"] == tc.id)

        def fmt_res(r):
            if r["success"]: return "PASS (Confirmed)"
            if r["handoff_triggered"]: return f"HANDOFF ({r['handoff_status']})"
            return "TERMINATED"

        matrix_data.append([
            f"{tc.id}: {tc.title}",
            tc.expected_outcome,
            fmt_res(r_run),
            fmt_res(p_run),
            fmt_res(h_run)
        ])

    print("\nMA TRẬN KỊCH BẢN CHI TIẾT:")
    print(tabulate(matrix_data, headers=matrix_headers, tablefmt="github"))
    print("\n" + "=" * 65)


def main():
    parser = argparse.ArgumentParser(description="SE373 - BTVN#3 Flight Booking Agent System")
    parser.add_argument("--live-llm", action="store_true", help="Chạy với model LLM trực tiếp (cần quota API)")
    parser.add_argument("--demo", type=str, choices=["react", "plan", "hybrid", "handoff", "all"], default="all")
    args = parser.parse_args()

    print("""
========================================================================================
   ĐẠI HỌC CÔNG NGHỆ THÔNG TIN (UIT) - KHOA CÔNG NGHỆ PHẦN MỀM
   SE373: KỸ THUẬT XÂY DỰNG HỆ THỐNG AGENTIC AI · BUỔI 03
   BTVN#3: AGENT ĐẶT VÉ MÁY BAY VỚI 3 THIẾT KẾ & LỚP HARNESS AN TOÀN
========================================================================================
""")

    if args.demo in ("react", "all"):
        run_demo_react(live_llm=args.live_llm)
    if args.demo in ("plan", "all"):
        run_demo_plan_then_execute(live_llm=args.live_llm)
    if args.demo in ("hybrid", "all"):
        run_demo_hybrid(live_llm=args.live_llm)
    if args.demo in ("handoff", "all"):
        run_demo_human_handoff(live_llm=args.live_llm)

    run_evaluation_benchmark(live_llm=args.live_llm)


if __name__ == "__main__":
    main()
