"""Script chạy toàn bộ thực nghiệm Challenge B (B1: Compact và B2: Code Mode)
Thu thập số liệu đo lường, kiểm chứng tính năng và xuất kết quả ra file JSON.
"""

import json
import os
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from generate_fixtures import generate_b1_fixtures, generate_b2_fixtures
from compaction import run_b1_experiment
from codemode import run_b2_experiment


def main():
    print("="*70)
    print("      CHALLENGE B — CONTEXT MANAGEMENT BENCHMARK RUNNER")
    print("="*70)
    start_total = time.time()

    # 1. Khởi tạo fixtures
    print("\n[BƯỚC 1] Khởi tạo Fixtures kiểm thử cho B1 và B2...")
    generate_b1_fixtures()
    generate_b2_fixtures()

    # 2. Chạy bài B1: Compact
    print("\n[BƯỚC 2] Khởi chạy B1 — Compact (Controlled Reboot với Structured Checkpoint)...")
    b1_results = run_b1_experiment()

    time.sleep(2)

    # 3. Chạy bài B2: Code Mode
    print("\n[BƯỚC 3] Khởi chạy B2 — Code Mode (Xử lý 100 log files ngoài context LLM)...")
    b2_results = run_b2_experiment()

    total_time = time.time() - start_total

    # 4. Tổng hợp kết quả
    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_runtime_seconds": round(total_time, 2),
        "compaction": b1_results,
        "codemode": b2_results,
        "overall_status": "SUCCESS" if (b1_results["status"] == "SUCCESS" and b2_results["status"] == "SUCCESS") else "PARTIAL"
    }

    results_file = BASE_DIR / "results.json"
    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print("\n" + "="*70)
    print("                 BẢNG TỔNG HỢP KẾT QUẢ CHALLENGE B")
    print("="*70)
    print(f"{'Hạng mục':<30} | {'Ban đầu':<12} | {'Sau tối ưu':<12} | {'Tiết kiệm (%)':<15}")
    print("-" * 75)
    b1_before = f"{b1_results['raw_tokens_before']:,} tok"
    b1_after = f"{b1_results['tokens_after_compaction']:,} tok"
    b1_pct = f"{b1_results['reduction_percentage']}%"
    print(f"{'B1: Compaction (Checkpoint)':<30} | {b1_before:<12} | {b1_after:<12} | {b1_pct:<15}")

    b2_before = f"{b2_results['metrics']['native_tool_calling_tokens']:,} tok"
    b2_after = f"{b2_results['metrics']['code_mode_input_tokens']:,} tok"
    b2_pct = f"{b2_results['metrics']['savings_percentage']}%"
    print(f"{'B2: Code Mode (100 log files)':<30} | {b2_before:<12} | {b2_after:<12} | {b2_pct:<15}")
    print("-" * 75)
    print(f"Trạng thái tổng thể: {summary['overall_status']}")
    print(f"Dữ liệu kết quả chi tiết đã được lưu tại: {results_file}")
    print("="*70)


if __name__ == "__main__":
    main()
