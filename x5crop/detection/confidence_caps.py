from __future__ import annotations

from typing import Any


def confidence_cap_record(
    *,
    owner: str,
    reason: str,
    cap_value: float,
    confidence_before: float,
    confidence_after: float,
) -> dict[str, Any]:
    return {
        "owner": owner,
        "reason": reason,
        "cap_value": float(cap_value),
        "confidence_before": float(confidence_before),
        "confidence_after": float(confidence_after),
        "changed": bool(float(confidence_after) < float(confidence_before)),
    }


def apply_confidence_cap(
    confidence: float,
    cap_value: float,
    *,
    owner: str,
    reason: str,
) -> tuple[float, dict[str, Any]]:
    before = float(confidence)
    after = min(before, float(cap_value))
    return after, confidence_cap_record(
        owner=owner,
        reason=reason,
        cap_value=float(cap_value),
        confidence_before=before,
        confidence_after=after,
    )


__all__ = [
    "apply_confidence_cap",
    "confidence_cap_record",
]
