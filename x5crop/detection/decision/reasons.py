from __future__ import annotations

from ...domain import Detection


def final_review_reasons(detection: Detection) -> list[str]:
    return list(detection.final_review_reasons)


def set_final_review_reasons(detection: Detection, reasons: list[str]) -> None:
    detection.final_review_reasons = [str(reason) for reason in reasons if reason]


__all__ = [
    "final_review_reasons",
    "set_final_review_reasons",
]
