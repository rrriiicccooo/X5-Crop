from __future__ import annotations

from typing import Any

import numpy as np

from ....policies.parameters.content import ContentEvidenceParameters
from .holder_texture import holder_texture_evidence_detail


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _frame_scores(detail: dict[str, Any]) -> list[dict[str, Any]]:
    value = detail.get("frame_scores", [])
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _leading_trailing_internal_empty_counts(
    empty_indexes: list[int],
    content_indexes: list[int],
    expected_count: int,
) -> tuple[int, int, int]:
    if expected_count <= 0 or not content_indexes:
        return 0, 0, len(empty_indexes)
    first_content = min(content_indexes)
    last_content = max(content_indexes)
    leading = sum(1 for index in empty_indexes if index < first_content)
    trailing = sum(1 for index in empty_indexes if index > last_content)
    internal = sum(1 for index in empty_indexes if first_content < index < last_content)
    return leading, trailing, internal


def frame_content_support_detail(
    content_detail: dict[str, Any],
    evidence_policy: ContentEvidenceParameters,
    *,
    expected_count: int | None = None,
) -> dict[str, Any]:
    if not bool(content_detail.get("used", False)):
        return {
            "used": False,
            "reason": content_detail.get("reason", "content_evidence_not_used"),
            "frame_content_support_available": False,
            "support": "unknown",
            "empty_frames_allowed": True,
        }

    scores = _frame_scores(content_detail)
    expected = int(expected_count or len(scores))
    if expected <= 0:
        expected = len(scores)

    content_indexes: list[int] = []
    empty_indexes: list[int] = []
    aspect_conflict_indexes: list[int] = []
    boundary_contact_indexes: list[int] = []
    normalized: list[dict[str, Any]] = []
    content_means: list[float] = []
    content_coverages: list[float] = []
    content_aspect_errors: list[float] = []

    seen_indexes: set[int] = set()
    for fallback_index, item in enumerate(scores, start=1):
        index = int(_float(item.get("index"), fallback_index))
        seen_indexes.add(index)
        mean = _float(item.get("mean"), 0.0)
        coverage = _float(item.get("coverage"), 0.0)
        aspect_value = item.get("aspect_error")
        aspect_error = None if aspect_value is None else _float(aspect_value, 0.0)
        content_present = (
            mean >= float(evidence_policy.present_mean_min)
            or coverage >= float(evidence_policy.present_coverage_min)
        )
        boundary_contact_sides = sorted(
            str(side)
            for side in item.get("boundary_contact_sides", [])
            if isinstance(side, str)
        )
        if boundary_contact_sides:
            boundary_contact_indexes.append(index)
        if content_present:
            content_indexes.append(index)
            content_means.append(mean)
            content_coverages.append(coverage)
            if aspect_error is not None:
                content_aspect_errors.append(aspect_error)
                if aspect_error > float(evidence_policy.aspect_ok_max):
                    aspect_conflict_indexes.append(index)
        else:
            empty_indexes.append(index)
        normalized.append(
            {
                "index": int(index),
                "mean": float(mean),
                "coverage": float(coverage),
                "aspect_error": aspect_error,
                "content_present": bool(content_present),
                "boundary_contact_sides": boundary_contact_sides,
                "boundary_coverages": dict(item.get("boundary_coverages", {})),
            }
        )

    for index in range(1, expected + 1):
        if index not in seen_indexes:
            empty_indexes.append(index)

    empty_indexes = sorted(set(empty_indexes))
    content_indexes = sorted(set(content_indexes))
    aspect_conflict_indexes = sorted(set(aspect_conflict_indexes))
    leading_empty, trailing_empty, internal_empty = _leading_trailing_internal_empty_counts(
        empty_indexes,
        content_indexes,
        expected,
    )

    has_content = bool(content_indexes)
    aspect_conflict = bool(aspect_conflict_indexes)
    support_available = has_content and not aspect_conflict
    support = "ok" if support_available else ("aspect_conflict" if aspect_conflict else "low_content")
    reason = "ok"
    if not has_content:
        reason = "no_content_detected"
    elif aspect_conflict:
        reason = "content_aspect_conflict"

    median_mean = float(np.median(np.array(content_means, dtype=np.float32))) if content_means else 0.0
    min_mean = float(min(content_means)) if content_means else 0.0
    median_coverage = float(np.median(np.array(content_coverages, dtype=np.float32))) if content_coverages else 0.0
    max_aspect_error = float(max(content_aspect_errors)) if content_aspect_errors else None

    return {
        "used": True,
        "evidence_role": "frame_content_support",
        "support": support,
        "reason": reason,
        "frame_content_support_available": bool(support_available),
        "empty_frames_allowed": True,
        "expected_count": int(expected),
        "content_bearing_frame_indexes": content_indexes,
        "empty_frame_indexes": empty_indexes,
        "leading_empty_count": int(leading_empty),
        "trailing_empty_count": int(trailing_empty),
        "internal_empty_count": int(internal_empty),
        "aspect_conflict_frame_indexes": aspect_conflict_indexes,
        "content_boundary_contact": bool(boundary_contact_indexes),
        "boundary_contact_frame_indexes": sorted(set(boundary_contact_indexes)),
        "median_mean": median_mean,
        "min_mean": min_mean,
        "median_coverage": median_coverage,
        "expected_aspect": content_detail.get("expected_aspect"),
        "max_aspect_error": max_aspect_error,
        "frame_scores": normalized,
        "holder_texture_evidence": holder_texture_evidence_detail(
            normalized,
            content_indexes=content_indexes,
            empty_indexes=empty_indexes,
            evidence_policy=evidence_policy,
        ),
        "source_content_support": content_detail.get("support"),
    }
