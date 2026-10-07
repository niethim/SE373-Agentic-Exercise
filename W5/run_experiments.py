"""Script chạy các trường hợp kiểm tra Block 1:
1. Kiểm tra tool list_files trực tiếp (4 cases: hợp lệ, file, không tồn tại, ngoài workspace).
2. Trường hợp A: Mua trước ngày đổi chính sách (28/09/2026, yêu cầu 06/10/2026, chưa kích hoạt).
3. Trường hợp B (sau khi đổi tên file): Mua từ ngày đổi chính sách (02/10/2026, yêu cầu 12/10/2026, chưa kích hoạt).
4. Trường hợp Thiếu thông tin: "Tôi mua ngày 02/10/2026, muốn hoàn ngày 12/10/2026." (chưa nêu kích hoạt).
Tất cả đều sinh trace JSONL và ghi lại kết quả chi tiết.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import uuid
from pathlib import Path

# Thêm stage-02-skills vào sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
STAGE02_DIR = SCRIPT_DIR / "stage-02-skills"
sys.path.insert(0, str(STAGE02_DIR))

import paths
from agent import TOOLS, build_agent, build_model, capabilities
from config import RECURSION_LIMIT, load_settings
from langchain_core.messages import AIMessage, HumanMessage
from observer import Observer
from tools.files import _list
from trace import TraceWriter


def run_direct_tool_tests() -> list[dict]:
    print("\n=== 1. KIỂM TRA TOOL TRỰC TIẾP ===")
    ws = paths.WORKSPACE_DIR
    tests = [
        ("Thư mục hợp lệ", "data/policies"),
        ("Đường dẫn file", "data/weekly_notes.md"),
        ("Đường dẫn không tồn tại", "data/khong-ton-tai"),
        ("Đường dẫn ngoài workspace", "../secret.txt"),
    ]
    results = []
    for name, p in tests:
        res = _list(ws, p)
        print(f"[{name}] path='{p}' -> ok={res.get('ok')}")
        if not res.get("ok"):
            print(f"   Error code: {res.get('error', {}).get('code')}")
            print(f"   Error message: {res.get('error', {}).get('message')}")
        else:
            print(f"   Entries count: {len(res.get('entries', []))}")
            for entry in res.get("entries", []):
                print(f"     - {entry['name']} ({entry['type']})")
        results.append({"name": name, "path": p, "result": res})
    return results


def run_agent_turn(conversation_id: str, prompt: str, tag: str) -> tuple[str, str, Observer]:
    import time
    settings, missing = load_settings()
    if missing:
        raise RuntimeError(f"Thiếu cấu hình: {missing}")

    run_id = uuid.uuid4().hex
    observer = Observer(conversation_id=conversation_id)
    observer.start_turn(run_id)

    writer = TraceWriter(paths.TRACES_DIR, f"stage-02-skills-{tag}", conversation_id, run_id, observer.chat_turn)
    working = [HumanMessage(content=prompt)]

    def emit(event_type: str, data: dict | None = None) -> None:
        event = observer.record(event_type, data)
        writer.write(event)

    caps = capabilities()
    emit("user_submitted", {"text": prompt, "tools": caps["tools"], "skills": caps["skills"]})
    observer.sync_messages(working)

    agent = build_agent(build_model(settings))

    # Retry loop if rate limited
    max_retries = 3
    for attempt in range(max_retries):
        try:
            stream = agent.stream(
                {"messages": working},
                config={"recursion_limit": RECURSION_LIMIT},
                stream_mode=["updates", "custom"],
            )
            for mode, chunk in stream:
                if mode == "custom" and isinstance(chunk, dict) and chunk.get("observer"):
                    emit(chunk["event"], chunk["data"])
                elif mode == "updates" and isinstance(chunk, dict):
                    for update in chunk.values():
                        if isinstance(update, dict) and update.get("messages"):
                            working.extend(update["messages"])
                            observer.sync_messages(working)
            break
        except Exception as exc:
            if "429" in str(exc) or "Quota" in str(exc) or "rate" in str(exc).lower():
                print(f"[Rate limit hit, sleeping 40s before retry {attempt + 1}/{max_retries}...]")
                time.sleep(40)
            else:
                raise

    final_ans = ""
    for m in reversed(working):
        if isinstance(m, AIMessage) and not m.tool_calls:
            final_ans = m.text
            break

    emit("run_completed", {"answer_chars": len(final_ans)})
    trace_path = str(writer.path)
    return final_ans, trace_path, observer


def main():
    import time

    # Kiểm tra tool trực tiếp
    direct_tool_results = run_direct_tool_tests()

    summary_path = SCRIPT_DIR / "experiment_summary.json"
    summary = {}
    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    summary["direct_tool_tests"] = direct_tool_results

    # 2. Trường hợp A
    if "case_a" not in summary:
        print("\n=== 2. CHẠY TRƯỜNG HỢP A (Mua trước 01/10) ===")
        prompt_a = "Tôi mua ngày 28/09/2026, yêu cầu hoàn ngày 06/10/2026, chưa kích hoạt. Tôi có được hoàn không?"
        conv_a = "case-a-" + uuid.uuid4().hex[:8]
        ans_a, trace_a, obs_a = run_agent_turn(conv_a, prompt_a, "case-a")
        print("Trace path:", trace_a)
        print("Final answer:\n", ans_a)
        print(f"Tool calls: {obs_a.tool_calls}, Model calls: {obs_a.model_calls}")
        summary["case_a"] = {
            "prompt": prompt_a,
            "trace": trace_a,
            "answer": ans_a,
            "model_calls": obs_a.model_calls,
            "tool_calls": obs_a.tool_calls,
        }
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
    else:
        print("\n[Trường hợp A đã có trong summary, tiếp tục...]")

    print("\n[Chờ 40s để reset token quota trước case tiếp theo...]")
    time.sleep(40)

    # 3. Đổi tên file cho Trường hợp B
    if "case_b_renamed" not in summary:
        print("\n=== 3. ĐỔI TÊN FILE CHÍNH SÁCH VÀ CHẠY TRƯỜNG HỢP B ===")
        policies_dir = paths.WORKSPACE_DIR / "data" / "policies"
        file_old = policies_dir / "policy-before-oct.md"
        file_new = policies_dir / "policy-from-oct.md"
        renamed_old = policies_dir / "quy-dinh-hoan-tien-cu.md"
        renamed_new = policies_dir / "quy-dinh-hoan-tien-moi.md"

        # Backup & Rename
        content_old = file_old.read_text(encoding="utf-8")
        content_new = file_new.read_text(encoding="utf-8")
        if file_old.exists():
            file_old.unlink()
        if file_new.exists():
            file_new.unlink()
        renamed_old.write_text(content_old, encoding="utf-8")
        renamed_new.write_text(content_new, encoding="utf-8")
        print(f"Đã đổi tên: policy-before-oct.md -> quy-dinh-hoan-tien-cu.md")
        print(f"Đã đổi tên: policy-from-oct.md -> quy-dinh-hoan-tien-moi.md")

        prompt_b = "Tôi mua ngày 02/10/2026, yêu cầu hoàn ngày 12/10/2026, chưa kích hoạt. Tôi có được hoàn không?"
        conv_b = "case-b-" + uuid.uuid4().hex[:8]
        try:
            ans_b, trace_b, obs_b = run_agent_turn(conv_b, prompt_b, "case-b-renamed")
            print("Trace path:", trace_b)
            print("Final answer:\n", ans_b)
            print(f"Tool calls: {obs_b.tool_calls}, Model calls: {obs_b.model_calls}")
            summary["case_b_renamed"] = {
                "prompt": prompt_b,
                "trace": trace_b,
                "answer": ans_b,
                "model_calls": obs_b.model_calls,
                "tool_calls": obs_b.tool_calls,
            }
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
        finally:
            # Khôi phục file gốc
            file_old.write_text(content_old, encoding="utf-8")
            file_new.write_text(content_new, encoding="utf-8")
            print("Đã khôi phục file chính sách gốc policy-before-oct.md và policy-from-oct.md.")

    print("\n[Chờ 40s để reset token quota trước case tiếp theo...]")
    time.sleep(40)

    # 4. Trường hợp Thiếu thông tin
    if "case_missing_info" not in summary:
        print("\n=== 4. CHẠY TRƯỜNG HỢP THIẾU THÔNG TIN ===")
        prompt_missing = "Tôi mua ngày 02/10/2026, muốn hoàn ngày 12/10/2026."
        conv_missing = "case-missing-" + uuid.uuid4().hex[:8]
        ans_m, trace_m, obs_m = run_agent_turn(conv_missing, prompt_missing, "case-missing-info")
        print("Trace path:", trace_m)
        print("Final answer:\n", ans_m)
        print(f"Tool calls: {obs_m.tool_calls}, Model calls: {obs_m.model_calls}")
        summary["case_missing_info"] = {
            "prompt": prompt_missing,
            "trace": trace_m,
            "answer": ans_m,
            "model_calls": obs_m.model_calls,
            "tool_calls": obs_m.tool_calls,
        }
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\nĐã lưu kết quả tổng hợp vào: {summary_path}")


if __name__ == "__main__":
    main()
