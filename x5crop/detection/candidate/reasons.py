from __future__ import annotations

from ...domain import Detection
from ..detail import CANDIDATE_REASONS, candidate_reasons_from_detail


def normalized_candidate_reasons(reasons: list[str]) -> list[str]:
    return sorted(set(str(reason) for reason in reasons if reason))


def candidate_reasons(detection: Detection) -> list[str]:
    return candidate_reasons_from_detail(detection)


def set_candidate_reasons(detection: Detection, reasons: list[str]) -> None:
    detection.detail[CANDIDATE_REASONS] = normalized_candidate_reasons(reasons)


def add_candidate_reasons(detection: Detection, reasons: list[str]) -> None:
    set_candidate_reasons(detection, [*candidate_reasons(detection), *reasons])


def add_candidate_reason(detection: Detection, reason: str) -> None:
    add_candidate_reasons(detection, [reason])


def merged_candidate_reasons(detection: Detection, reasons: list[str]) -> list[str]:
    return normalized_candidate_reasons([*candidate_reasons(detection), *reasons])


__all__ = [
    "add_candidate_reason",
    "add_candidate_reasons",
    "candidate_reasons",
    "merged_candidate_reasons",
    "normalized_candidate_reasons",
    "set_candidate_reasons",
]
