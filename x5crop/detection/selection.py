from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from ..domain import Detection
from ..formats import FormatSpec
from ..policies.base import DetectionPolicy
from ..policies.registry import get_detection_policy


@dataclass(frozen=True)
class SelectionResult:
    selected: Detection
    candidates: tuple[Detection, ...]


def calibrated_candidate_rank(detection: Detection, threshold: float) -> tuple[int, float, int, float]:
    candidate = detection.detail.get("candidate_decision", {})
    joint = float(candidate.get("joint_score", 0.0)) if isinstance(candidate, dict) else 0.0
    partial_safe = bool(
        isinstance(candidate, dict)
        and isinstance(candidate.get("partial_safe_extra_frames"), dict)
        and candidate["partial_safe_extra_frames"].get("ok", False)
    )
    if partial_safe:
        return (
            1 if detection.confidence >= threshold else 0,
            float(detection.count),
            int(round(float(detection.confidence) * 1000.0)),
            joint,
        )
    return (
        1 if detection.confidence >= threshold else 0,
        float(detection.confidence),
        int(detection.count),
        joint,
    )


def is_partial_safe_auto_candidate(detection: Detection, threshold: float) -> bool:
    candidate = detection.detail.get("candidate_decision", {})
    return bool(
        detection.strip_mode == "partial"
        and detection.confidence >= threshold
        and isinstance(candidate, dict)
        and isinstance(candidate.get("partial_safe_extra_frames"), dict)
        and candidate["partial_safe_extra_frames"].get("ok", False)
        and candidate.get("auto_gate", False)
    )


def select_separator_review_candidate_on_content_mismatch(
    best: Detection,
    candidates: list[Detection],
    fmt: FormatSpec,
    policy: DetectionPolicy,
) -> Optional[Detection]:
    review_policy = policy.candidate_selection.content_mismatch_review
    best_decision = best.detail.get("candidate_decision", {})
    best_source = best_decision.get("source") if isinstance(best_decision, dict) else None
    if (
        not review_policy.enabled
        or best.film_format != fmt.name
        or best.strip_mode not in review_policy.strip_modes
        or (review_policy.require_default_count and best.count != fmt.default_count)
        or best_source != review_policy.required_best_source
        or review_policy.required_review_reason not in best.review_reasons
    ):
        return None
    plausible: list[Detection] = []
    for candidate in candidates:
        if (
            candidate is best
            or candidate.film_format != fmt.name
            or candidate.strip_mode != best.strip_mode
            or candidate.count != best.count
        ):
            continue
        candidate_decision = candidate.detail.get("candidate_decision", {})
        if not isinstance(candidate_decision, dict) or candidate_decision.get("source") != review_policy.candidate_source:
            continue
        hard_detail = candidate_decision.get("separator_hard_evidence", {})
        if not isinstance(hard_detail, dict):
            continue
        expected = max(1, int(hard_detail.get("expected_gaps", best.count - 1) or best.count - 1))
        hard = int(hard_detail.get("hard_gaps", 0) or 0)
        equal = int(hard_detail.get("equal_gaps", 0) or 0)
        support = str(candidate_decision.get("content_support", ""))
        min_hard = max(1, math.ceil(expected * review_policy.min_hard_ratio))
        if (
            hard >= min_hard
            and equal <= review_policy.max_equal_gaps
            and support == review_policy.required_content_support
        ):
            plausible.append(candidate)
    if not plausible:
        return None
    return max(
        plausible,
        key=lambda candidate: (
            int((candidate.detail.get("candidate_decision", {}).get("separator_hard_evidence", {}) or {}).get("hard_gaps", 0) or 0),
            float((candidate.detail.get("candidate_decision", {}) or {}).get("joint_score", 0.0) or 0.0),
            float(candidate.confidence),
        ),
    )


def select_detection_candidate(
    candidates: list[Detection],
    fmt: FormatSpec,
    threshold: float,
    policy: Optional[DetectionPolicy] = None,
) -> Detection:
    policy = policy or get_detection_policy(fmt.name, candidates[0].strip_mode if candidates else "full")
    candidates = sorted(candidates, key=lambda d: calibrated_candidate_rank(d, threshold), reverse=True)
    best = candidates[0]
    selection_override: Optional[str] = None
    separator_review_on_mismatch = select_separator_review_candidate_on_content_mismatch(
        best,
        candidates,
        fmt,
        policy,
    )
    if separator_review_on_mismatch is not None and separator_review_on_mismatch.confidence < threshold:
        override_reason = policy.candidate_selection.content_mismatch_review.override_reason
        separator_review_on_mismatch.review_reasons.append(override_reason)
        separator_review_on_mismatch.review_reasons = sorted(set(separator_review_on_mismatch.review_reasons))
        separator_review_on_mismatch.detail["content_candidate_mismatch"] = {
            "content_candidate_confidence": float(best.confidence),
            "content_candidate_review_reasons": list(best.review_reasons),
            "content_candidate_decision": best.detail.get("candidate_decision", {}),
        }
        best = separator_review_on_mismatch
        selection_override = override_reason
    second = next((candidate for candidate in candidates if candidate is not best), None)
    selected_policy = get_detection_policy(best.film_format, best.strip_mode)
    competition = [
        {
            "rank": index,
            "selected": candidate is best,
            "format": candidate.film_format,
            "count": int(candidate.count),
            "strip_mode": candidate.strip_mode,
            "confidence": float(candidate.confidence),
            "review_reasons": list(candidate.review_reasons),
            "candidate_decision": candidate.detail.get("candidate_decision", {}),
        }
        for index, candidate in enumerate(candidates[: selected_policy.candidate_selection.top_n], start=1)
    ]
    best.detail["candidate_competition"] = {
        "candidate_count": len(candidates),
        "formats": [fmt.name],
        "selected_candidate": {
            "format": best.film_format,
            "count": int(best.count),
            "strip_mode": best.strip_mode,
            "confidence": float(best.confidence),
            "review_reasons": list(best.review_reasons),
            "candidate_decision": best.detail.get("candidate_decision", {}),
        },
        "selection_override": selection_override,
        "top_candidates": competition,
    }
    if second is not None:
        margin = float(best.confidence) - float(second.confidence)
        best.detail["candidate_competition"]["margin_to_second"] = margin
        second_close = margin < selected_policy.candidate_selection.close_margin
        partial_full_conflict = (
            best.strip_mode != second.strip_mode
            and min(best.confidence, second.confidence) >= threshold
        )
        best_decision = best.detail.get("candidate_decision", {})
        best_partial_safe = bool(
            isinstance(best_decision, dict)
            and isinstance(best_decision.get("partial_safe_extra_frames"), dict)
            and best_decision["partial_safe_extra_frames"].get("ok", False)
        )
        if (
            best.confidence >= threshold
            and not best_partial_safe
            and (second_close or partial_full_conflict)
        ):
            best.confidence = min(best.confidence, selected_policy.candidate_selection.confidence_cap)
            best.review_reasons.append("candidate_competition_uncertain")
            best.review_reasons = sorted(set(best.review_reasons))
    return best


__all__ = [
    "SelectionResult",
    "calibrated_candidate_rank",
    "is_partial_safe_auto_candidate",
    "select_detection_candidate",
    "select_separator_review_candidate_on_content_mismatch",
]
