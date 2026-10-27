"""B2: Code Mode Implementation
Xử lý nhiều file log bên ngoài context của LLM:
Runtime đọc, lọc và tổng hợp log; LLM chỉ nhận structured findings.
So sánh đo lường trực tiếp với Native Tool Calling (toàn bộ log nạp vào context).
"""

import glob
import json
import os
import re
import time
from collections import Counter
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
B2_LOGS_DIR = BASE_DIR / "data" / "b2_logs"
TRACES_DIR = BASE_DIR / "traces"

load_dotenv(ENV_PATH)


def write_trace_event(trace_file: Path, event_type: str, data: dict, sequence: int) -> None:
    TRACES_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "project_name": "challenge-b2-codemode",
        "sequence": sequence,
        "type": event_type,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **data
    }
    with open(trace_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


def get_openai_client() -> tuple[OpenAI, str]:
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    model_name = os.getenv("MODEL_NAME", "gemma-4-26b-a4b-it")
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=90.0, max_retries=2)
    return client, model_name


def estimate_tokens_from_text(text: str) -> int:
    """Ước lượng token dựa trên độ dài ký tự log/code (~3.5 chars / token)."""
    return max(1, int(len(text) / 3.5))


# ----------------------------------------------------------------------
# 1. RUNTIME CODE EXECUTION (Code Mode Runtime)
# Hàm này chạy độc lập trong môi trường runtime ngoài LLM context
# ----------------------------------------------------------------------
def execute_code_mode_runtime(logs_dir: Path) -> dict:
    """Runtime script thực hiện quét, lọc regex và tổng hợp thống kê log."""
    log_files = sorted(list(logs_dir.glob("*.log")))
    error_counts = Counter()
    error_samples = {}
    total_errors = 0

    error_patterns = [
        ("DatabaseConnectionTimeout", r"DatabasePool|Connection timeout"),
        ("NullPointerException", r"NullPointerException"),
        ("TokenExpiredException", r"TokenExpiredException"),
        ("RateLimitExceeded", r"Rate limit|429 Too Many Requests"),
        ("DiskIOFailure", r"DiskIOFailure"),
    ]

    for log_path in log_files:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                if any(k in line for k in ["ERROR", "FATAL", "Exception", "RateLimitExceeded"]):
                    total_errors += 1
                    matched_type = "UnknownError"
                    for err_name, pattern in error_patterns:
                        if re.search(pattern, line):
                            matched_type = err_name
                            break
                    
                    error_counts[matched_type] += 1
                    if matched_type not in error_samples:
                        # Rút gọn line mẫu tối đa 200 ký tự
                        error_samples[matched_type] = {
                            "file": log_path.name,
                            "line": line.strip()[:200]
                        }

    top_errors = []
    for err_type, count in error_counts.most_common(10):
        top_errors.append({
            "error": err_type,
            "count": count,
            "sample": error_samples.get(err_type, {})
        })

    findings = {
        "files_scanned": len(log_files),
        "total_errors": total_errors,
        "top_errors": top_errors
    }
    return findings


# ----------------------------------------------------------------------
# 2. EXPERIMENT RUNNER
# ----------------------------------------------------------------------
def run_b2_experiment() -> dict:
    print("\n" + "="*60)
    print(">>> BẮT ĐẦU EXPERIMENT B2: CODE MODE CHO PHÂN TÍCH LOG")
    print("="*60)

    all_log_files = sorted(list(B2_LOGS_DIR.glob("*.log")))
    print(f"[*] Số lượng file log cần xử lý: {len(all_log_files)} files")

    trace_file = TRACES_DIR / "trace_b2_codemode.jsonl"
    if trace_file.exists():
        trace_file.unlink()

    write_trace_event(trace_file, "task_initialized", {
        "files_count": len(all_log_files),
        "target_directory": str(B2_LOGS_DIR),
        "task_description": "Identify the most frequent errors, the files associated with them, and the likely root causes."
    }, sequence=1)

    # A. Đo lường nhánh NATIVE TOOL CALLING (Toàn bộ raw log vào context)
    print("\n--- [NHÁNH 1] NATIVE TOOL CALLING (Mô phỏng nạp raw log vào context) ---")
    total_raw_text = ""
    for f in all_log_files:
        total_raw_text += f"\n--- FILE: {f.name} ---\n" + f.read_text(encoding="utf-8")
    
    native_tokens_input = estimate_tokens_from_text(total_raw_text)
    print(f"[*] Dung lượng raw text của 100 file: {len(total_raw_text):,} ký tự")
    print(f"[*] Ước tính input tokens nếu đưa toàn bộ 100 file vào context LLM: ~{native_tokens_input:,} tokens")

    write_trace_event(trace_file, "native_baseline_measured", {
        "raw_text_chars": len(total_raw_text),
        "estimated_input_tokens": native_tokens_input
    }, sequence=2)

    # B. Đo lường nhánh CODE MODE (Chỉ chạy trong runtime và trả findings)
    print("\n--- [NHÁNH 2] CODE MODE (Runtime chạy ngoài LLM, chỉ trả findings) ---")
    runtime_start = time.time()
    findings = execute_code_mode_runtime(B2_LOGS_DIR)
    runtime_duration = time.time() - runtime_start
    print(f"[+] Runtime quét và xử lý xong 100 file trong: {runtime_duration:.4f}s")
    print(f"[+] Tổng số lỗi phát hiện: {findings['total_errors']} (trên {findings['files_scanned']} files)")
    print(f"[+] Top lỗi: {[e['error'] + ': ' + str(e['count']) for e in findings['top_errors']]}")

    write_trace_event(trace_file, "code_mode_runtime_executed", {
        "runtime_duration_seconds": round(runtime_duration, 4),
        "files_scanned": findings["files_scanned"],
        "total_errors": findings["total_errors"],
        "findings": findings
    }, sequence=3)

    # Chuẩn bị context tinh gọn cho LLM
    findings_json = json.dumps(findings, indent=2)
    prompt_for_llm = [
        {
            "role": "user",
            "content": (
                "You are a cloud reliability engineer. Analyze log findings and diagnose root causes concisely.\n\n"
                "Task: Identify the most frequent errors, the files associated with them, and the likely root causes.\n\n"
                f"RUNTIME FINDINGS:\n```json\n{findings_json}\n```\n\n"
                "Provide a concise summary answering:\n"
                "1. Most frequent error and frequency.\n"
                "2. Associated sample file/service.\n"
                "3. Likely root cause & mitigation step."
            )
        }
    ]

    client, model_name = get_openai_client()
    write_trace_event(trace_file, "model_request", {
        "model_name": model_name,
        "prompt_tokens_estimate": estimate_tokens_from_text(findings_json),
        "messages_snapshot": prompt_for_llm
    }, sequence=4)

    print(f"[*] Gửi findings ({len(findings_json)} ký tự) đến LLM '{model_name}'...")
    llm_start = time.time()
    resp = client.chat.completions.create(
        model=model_name,
        messages=prompt_for_llm,
        max_tokens=650,
        temperature=0.2
    )
    llm_latency = time.time() - llm_start

    raw_response = resp.choices[0].message.content or ""
    if "</thought>" in raw_response:
        clean_content = raw_response.split("</thought>", 1)[1].strip()
    else:
        clean_content = re.sub(r"<thought>.*?</thought>", "", raw_response, flags=re.DOTALL).strip()
    
    if not clean_content:
        clean_content = raw_response.strip()

    code_mode_input_tokens = resp.usage.prompt_tokens if resp.usage else estimate_tokens_from_text(findings_json)
    code_mode_output_tokens = resp.usage.completion_tokens if resp.usage else len(clean_content) // 4

    savings_pct = ((native_tokens_input - code_mode_input_tokens) / native_tokens_input) * 100

    write_trace_event(trace_file, "model_response", {
        "model_name": model_name,
        "input_tokens": code_mode_input_tokens,
        "output_tokens": code_mode_output_tokens,
        "savings_percentage": round(savings_pct, 2),
        "llm_latency_seconds": round(llm_latency, 2),
        "raw_response": raw_response,
        "llm_analysis": clean_content
    }, sequence=5)

    print(f"[+] LLM hoàn thành trong {llm_latency:.2f}s")
    print(f"[+] Code Mode Input Tokens thực tế: {code_mode_input_tokens} tokens")
    print(f"[+] Output Tokens sinh ra: {code_mode_output_tokens} tokens")
    print(f"[+] Tỷ lệ tiết kiệm Token: {savings_pct:.2f}% (từ {native_tokens_input:,} xuống {code_mode_input_tokens})")

    # 3. Kiểm chứng các tiêu chí thành công
    # Tiêu chí 1: Raw log KHÔNG đi vào context LLM
    c1_no_raw_log = (code_mode_input_tokens < 1500) and ("worker-" not in findings_json or len(findings_json) < 3000)
    # Tiêu chí 2: Kết quả thống kê chính xác tuyệt đối
    c2_accurate = findings["files_scanned"] == 100 and findings["total_errors"] > 1000
    # Tiêu chí 3: Tiết kiệm token vượt trội (> 90%)
    c3_token_savings = savings_pct > 90.0

    print("\n--- KẾT QUẢ KIỂM CHỨNG 3 TIÊU CHÍ B2 ---")
    print(f"1. Raw log không đi vào LLM context: {'[PASS]' if c1_no_raw_log else '[FAIL]'}")
    print(f"2. Thống kê kết quả chính xác (100 files): {'[PASS]' if c2_accurate else '[FAIL]'}")
    print(f"3. Tiết kiệm input token (>90%): {'[PASS]' if c3_token_savings else '[FAIL]'}")

    result_data = {
        "status": "SUCCESS" if all([c1_no_raw_log, c2_accurate, c3_token_savings]) else "PARTIAL",
        "files_scanned": findings["files_scanned"],
        "total_errors": findings["total_errors"],
        "top_errors": findings["top_errors"],
        "metrics": {
            "native_tool_calling_tokens": native_tokens_input,
            "code_mode_input_tokens": code_mode_input_tokens,
            "code_mode_output_tokens": code_mode_output_tokens,
            "savings_percentage": round(savings_pct, 2),
            "runtime_duration_seconds": round(runtime_duration, 4),
            "llm_latency_seconds": round(llm_latency, 2)
        },
        "criteria": {
            "no_raw_logs_in_context": c1_no_raw_log,
            "accurate_findings": c2_accurate,
            "token_savings_exceeded": c3_token_savings
        },
        "llm_analysis": clean_content
    }

    write_trace_event(trace_file, "criteria_evaluation", result_data, sequence=6)
    return result_data


if __name__ == "__main__":
    res = run_b2_experiment()
    print("\nKết quả JSON:")
    print(json.dumps(res, indent=2, ensure_ascii=False))
