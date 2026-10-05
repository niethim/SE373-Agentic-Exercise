"""
LỚP 3 HARNESS: PHÁT HIỆN LẶP (LOOP DETECTOR)
Theo Sơ đồ Quyết định kiến trúc chuẩn (Kết C: check_seat lỗi ba lần liền) & Code mẫu kiến trúc chuẩn.

Nhiệm vụ & Các Case đặc biệt:
- Case 1 (Trùng action): Cùng fingerprint (tool, args) xuất hiện >= repeat_k lần trong cửa sổ trượt window.
- Case 2 (Ngoại lệ Polling hợp lệ - kiến trúc chuẩn): Gọi lại get_booking để chờ trạng thái 'confirmed'
  là polling hợp lệ, có ngưỡng cho phép cao hơn trước khi coi là loop.
- Case 3 (Trùng observation lỗi): Tham số khác nhau nhưng nhận lại cùng một kết quả lỗi liên tiếp 3 lần.
"""
from collections import deque
from typing import Dict, Any, Optional, Tuple


class LoopDetectorLayer:
    """Lớp 3 Harness: Phát hiện vòng lặp không tiến bộ (Kết C)."""

    def __init__(self, window: int = 6, repeat_k: int = 3):
        self.window = window
        self.repeat_k = repeat_k
        self.recent_actions = deque(maxlen=window)
        self.consecutive_error_count: int = 0
        self.last_error_fingerprint: Optional[str] = None

    def reset(self):
        self.recent_actions.clear()
        self.consecutive_error_count = 0
        self.last_error_fingerprint = None

    def check_action(self, tool_name: str, args: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
        """
        So sánh (tool, args) trong cửa sổ trượt (kiến trúc chuẩn).
        Trả về: ('LOOP', chi_tiet) hoặc (None, None)
        """
        # Tạo fingerprint chuẩn hóa từ (tool, sorted(args))
        args_repr = repr(sorted((k, repr(v)) for k, v in args.items()))
        fp = (tool_name, args_repr)

        # Case đặc biệt: Polling hợp lệ cho get_booking (kiến trúc chuẩn)
        is_polling = (tool_name == "get_booking")
        threshold = self.repeat_k + 1 if is_polling else self.repeat_k

        if self.recent_actions.count(fp) + 1 >= threshold:
            count = self.recent_actions.count(fp) + 1
            return "LOOP", f"Phát hiện lặp hành động: Công cụ '{tool_name}' với tham số {args} đã được gọi {count} lần (Kết C: lặp không tiến bộ)."

        self.recent_actions.append(fp)
        return None, None

    def check_observation(self, tool_name: str, raw_result: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
        """
        Case đặc biệt: Phát hiện trùng lặp observation lỗi liên tiếp 3 lần.
        """
        if raw_result.get("status") == "error":
            err_fp = f"{tool_name}:{raw_result.get('error')}"
            if err_fp == self.last_error_fingerprint:
                self.consecutive_error_count += 1
            else:
                self.consecutive_error_count = 1
                self.last_error_fingerprint = err_fp

            if self.consecutive_error_count >= 3:
                return "LOOP", f"Phát hiện bế tắc kết quả: Công cụ '{tool_name}' liên tiếp trả về cùng lỗi '{raw_result.get('error')}' 3 lần."
        else:
            self.consecutive_error_count = 0
            self.last_error_fingerprint = None

        return None, None

    def check_action_loop(self, tool_name: str, args: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        verdict, msg = self.check_action(tool_name, args)
        return verdict == "LOOP", msg

    def check_observation_loop(self, tool_name: str, raw_result: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        verdict, msg = self.check_observation(tool_name, raw_result)
        return verdict == "LOOP", msg

