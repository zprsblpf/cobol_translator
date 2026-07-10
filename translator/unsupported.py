"""
Structured unsupported markers.

New deterministic fallbacks should use a stable rule_id instead of anonymous
TODO comments so unsupported cases remain searchable and machine-readable.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UnsupportedEvent:
    rule_id: str
    kind: str
    raw: str
    reason: str

    def comment(self) -> str:
        return unsupported_comment(self.rule_id, self.kind, self.raw, self.reason)


def _one_line(value: str) -> str:
    return " ".join(str(value).split())


def unsupported_comment(rule_id: str, kind: str, raw: str, reason: str) -> str:
    """Render a stable unsupported marker as a Java comment."""
    rule_id = _one_line(rule_id)
    kind = _one_line(kind)
    raw = _one_line(raw)
    reason = _one_line(reason)
    return f"// UNSUPPORTED[{rule_id}] {kind}: {reason}; raw={raw}"


__all__ = ["UnsupportedEvent", "unsupported_comment"]
