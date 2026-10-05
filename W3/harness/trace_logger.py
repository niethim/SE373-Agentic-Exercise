"""
TraceLogger: Enforces Global Security Rule 11 (Secure Logging).
Redacts sensitive information (API keys, card numbers, secrets) while logging detailed execution events.
"""
import re
from typing import List, Dict, Any, Optional
from datetime import datetime
from models.trace import TraceEvent


CREDIT_CARD_REGEX = re.compile(r"\b(?:\d[ -]*?){13,16}\b")
API_KEY_REGEX = re.compile(r"(AIza[0-9A-Za-z-_]{35}|sk-[A-Za-z0-9-_]{20,})")
PASSWORD_REGEX = re.compile(r"(['\"]?(?:password|token|secret|cvv)['\"]?\s*[:=]\s*['\"])([^'\"]+)(['\"])", re.IGNORECASE)


def redact_sensitive_data(text: str) -> str:
    """Sanitizes sensitive data like API keys, credit cards, and passwords."""
    if not isinstance(text, str):
        text = str(text)

    # Redact API keys
    text = API_KEY_REGEX.sub("[REDACTED_API_KEY]", text)
    # Redact Credit Cards
    text = CREDIT_CARD_REGEX.sub("[REDACTED_CARD]", text)
    # Redact passwords/tokens/cvv
    text = PASSWORD_REGEX.sub(r"\1[REDACTED_SECRET]\3", text)

    return text


def sanitize_payload(payload: Any) -> Any:
    """Recursively redacts dictionary and list objects."""
    if isinstance(payload, dict):
        sanitized = {}
        for k, v in payload.items():
            if any(secret_term in k.lower() for secret_term in ["token", "password", "api_key", "secret", "cvv", "card"]):
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = sanitize_payload(v)
        return sanitized
    elif isinstance(payload, list):
        return [sanitize_payload(item) for item in payload]
    elif isinstance(payload, str):
        return redact_sensitive_data(payload)
    return payload


class TraceLogger:
    def __init__(self, agent_name: str = "Agent"):
        self.agent_name = agent_name
        self.events: List[TraceEvent] = []
        self.step_counter: int = 1

    def reset(self):
        self.events.clear()
        self.step_counter = 1

    def log(self, event_type: str, content: Any):
        clean_content = sanitize_payload(content)
        event = TraceEvent(
            step_id=self.step_counter,
            agent_type=self.agent_name,
            event_type=event_type,
            content=clean_content,
            timestamp=datetime.now().isoformat(),
            sensitive_redacted=True,
        )
        self.events.append(event)
        self.step_counter += 1
        return event

    def format_trace_summary(self) -> str:
        """Formats the trace into human-readable debug logs."""
        lines = [f"=== EXECUTION TRACE: {self.agent_name} ==="]
        for ev in self.events:
            lines.append(f"[{ev.timestamp[:19]}] Step {ev.step_id:02d} | {ev.event_type:<18} | {ev.content}")
        lines.append("=" * 45)
        return "\n".join(lines)
