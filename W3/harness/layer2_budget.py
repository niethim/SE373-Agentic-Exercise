"""
LỚP 2 HARNESS: HẾT NGÂN SÁCH (BUDGET & RESOURCE LIMITS)
Theo Sơ đồ Quyết định kiến trúc chuẩn (Kết B: dò 12 chuyến, đều trên 2 triệu).

Nhiệm vụ & Các Case đặc biệt:
- Case 1 (Chạm trần bước - Step Limit): Harness đếm số vòng và dừng khi chạm trần (mặc định 12 vòng).
- Case 2 (Chạm trần Tokens & Thời gian): Ngăn chặn cạn kiệt tài nguyên API hoặc treo hệ thống.
- Case 3 (Giới hạn Replan & Retry): Giới hạn tối đa 3 lần lập lại kế hoạch (replan) và 2 lần retry mạng.
- Case 4 (Ngân sách kiểm cuối cùng - kiến trúc chuẩn): Đảm bảo đếm và kiểm tra sau khi các lỗi lặp, bế tắc
  đã được phân tích, tránh việc che lấp chẩn đoán lỗi.
"""
import time
from typing import Tuple, Optional


class BudgetLimitLayer:
    """Lớp 2 Harness: Kiểm soát trần tài nguyên và ngân sách (Kết B)."""

    def __init__(
        self,
        max_steps: int = 12,
        max_tokens: int = 25000,
        max_execution_time_sec: float = 60.0,
        max_replans: int = 3,
        max_retries: int = 2,
        timeout_seconds: Optional[float] = None,
    ):
        self.max_steps = max_steps
        self.max_tokens = max_tokens
        self.max_execution_time_sec = timeout_seconds if timeout_seconds is not None else max_execution_time_sec
        self.max_replans = max_replans
        self.max_retries = max_retries

        self.steps_taken: int = 0
        self.tokens_used: int = 0
        self.start_time: float = time.time()
        self.replans_count: int = 0
        self.retries_count: int = 0

    def reset(self):
        self.steps_taken = 0
        self.tokens_used = 0
        self.start_time = time.time()
        self.replans_count = 0
        self.retries_count = 0

    def get_elapsed_time(self) -> float:
        return time.time() - self.start_time

    def check_budget(self) -> Tuple[bool, Optional[str]]:
        """Kiểm tra xem hệ thống có nằm trong giới hạn ngân sách không (không tăng bước)."""
        if self.steps_taken >= self.max_steps:
            return False, f"Chạm trần ngân sách: Đã thực thi {self.steps_taken}/{self.max_steps} vòng (Kết B: hết ngân sách). Step budget exhausted."

        if self.tokens_used >= self.max_tokens:
            return False, f"Chạm trần token: Đã dùng {self.tokens_used}/{self.max_tokens} tokens. Token budget exhausted."

        elapsed = self.get_elapsed_time()
        if elapsed >= self.max_execution_time_sec:
            return False, f"Chạm trần thời gian: {elapsed:.1f}s >= {self.max_execution_time_sec}s. Timeout."

        if self.replans_count > self.max_replans:
            return False, f"Vượt quá số lần tái lập kế hoạch cho phép: {self.replans_count}/{self.max_replans} replans."

        return True, None

    def check_and_record_step(self) -> Tuple[bool, Optional[str]]:
        """Ghi nhận một bước thực thi và kiểm tra trần tài nguyên."""
        self.steps_taken += 1
        return self.check_budget()

    record_step = check_and_record_step



    def record_tokens(self, tokens: int):
        self.tokens_used += tokens

    def record_replan(self) -> Tuple[bool, Optional[str]]:
        self.replans_count += 1
        if self.replans_count > self.max_replans:
            return False, f"Vượt quá giới hạn replan: {self.replans_count}/{self.max_replans} lần."
        return True, None

    def record_retry(self) -> Tuple[bool, Optional[str]]:
        self.retries_count += 1
        if self.retries_count > self.max_retries:
            return False, f"Vượt quá giới hạn retry công cụ: {self.retries_count}/{self.max_retries} lần."
        return True, None
