from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from ....domain import Detection
from ...evidence.separator_summary import separator_support_detail_summary
from ....formats import FormatSpec
from ....policies.context import RuntimePolicyContext
from ....policies.runtime.policy import DetectionPolicy
from ..signals import candidate_signals


@dataclass(frozen=True)
class SelectionResult:
    selected: Detection
    candidates: tuple[Detection, ...]


def _candidate_assessment(candidate: Detection) -> dict:
    assessment = candidate.detail.get("candidate_assessment", {})
    return dict(assessment) if isinstance(assessment, dict) else {}


def _candidate_detail_list(candidate: Detection, key: str) -> list:
    value = _candidate_assessment(candidate).get(key)
    return list(value) if isinstance(value, list) else []


def calibrated_candidate_rank(detection: Detection, threshold: float) -> tuple[int, float, int, float]:
    candidate = detection.detail.get("candidate_assessment", {})
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


def is_partial_safe_candidate(detection: Detection, threshold: float) -> bool:
    candidate = detection.detail.get("candidate_assessment", {})
    candidate_gate = {}
    if isinstance(candidate, dict):
        gate = candidate.get("candidate_gate")
        candidate_gate = dict(gate) if isinstance(gate, dict) else {}
    candidate_gate_passed = bool(
        candidate_gate.get(
            "passed",
            candidate.get("candidate_gate_passed", False) if isinstance(candidate, dict) else False,
        )
    )
    return bool(
        detection.strip_mode == "partial"
        and detection.confidence >= threshold
        and isinstance(candidate, dict)
        and isinstance(candidate.get("partial_safe_extra_frames"), dict)
        and candidate["partial_safe_extra_frames"].get("ok", False)
        and candidate_gate_passed
    )


def select_separator_candidate_for_content_mismatch(
    best: Detection,
    candidates: list[Detection],
    fmt: FormatSpec,
    policy: DetectionPolicy,
) -> Optional[Detection]:
    mismatch_policy = policy.candidate_selection.content_mismatch_candidate
    best_assessment = _candidate_assessment(best)
    best_source = best_assessment.get("source")

    def separator_summary_for(candidate: Detection) -> tuple[int, int, int]:
        candidate_assessment = _candidate_assessment(candidate)
        hard_detail = candidate_assessment.get("separator_support", {})
        if not isinstance(hard_detail, dict):
            return 0, 0, 0
        evidence = separator_support_detail_summary(
            hard_detail,
            expected_default=max(1, best.count - 1),
        )
        return (
            max(1, evidence.expected_gaps),
            evidence.hard_separator_gaps,
            evidence.equal_model_gaps,
        )

    if (
        not mismatch_policy.enabled
        or best.film_format != fmt.name
        or best.strip_mode not in mismatch_policy.strip_modes
        or (mismatch_policy.require_default_count and best.count != fmt.default_count)
        or best_source != mismatch_policy.required_best_source
        or mismatch_policy.required_candidate_diagnostic
        not in _candidate_detail_list(best, "diagnostics")
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
        candidate_assessment = _candidate_assessment(candidate)
        if candidate_assessment.get("source") != mismatch_policy.candidate_source:
            continue
        expected, hard, equal = separator_summary_for(candidate)
        support = str(candidate_assessment.get("content_support", ""))
        min_hard = max(1, math.ceil(expected * mismatch_policy.min_hard_ratio))
        if (
            hard >= min_hard
            and equal <= mismatch_policy.max_equal_gaps
            and support == mismatch_policy.required_content_support
        ):
            plausible.append(candidate)
    if not plausible:
        return None
    return max(
        plausible,
        key=lambda candidate: (
            separator_summary_for(candidate)[1],
            float((candidate.detail.get("candidate_assessment", {}) or {}).get("joint_score", 0.0) or 0.0),
            float(candidate.confidence),
        ),
    )


def _candidate_summary(candidate: Detection) -> dict:
    assessment = _candidate_assessment(candidate)
    return {
        "format": candidate.film_format,
        "count": int(candidate.count),
        "strip_mode": candidate.strip_mode,
        "confidence": float(candidate.confidence),
        "candidate_signals": candidate_signals(candidate),
        "candidate_blockers": list(assessment.get("blockers", []))
        if isinstance(assessment.get("blockers"), list)
        else [],
        "candidate_diagnostics": list(assessment.get("diagnostics", []))
        if isinstance(assessment.get("diagnostics"), list)
        else [],
        "candidate_assessment": assessment,
        "candidate_plan": candidate.detail.get("candidate_plan", {}),
        "gap_search_profile": candidate.detail.get("gap_search_profile", {}),
    }


def select_detection_candidate(
    candidates: list[Detection],
    fmt: FormatSpec,
    threshold: float,
    policy: DetectionPolicy,
    policy_context: RuntimePolicyContext,
) -> Detection:
    candidates = sorted(candidates, key=lambda d: calibrated_candidate_rank(d, threshold), reverse=True)
    best = candidates[0]
    selection_override: Optional[str] = None
    separator_candidate_on_mismatch = select_separator_candidate_for_content_mismatch(
        best,
        candidates,
        fmt,
        policy,
    )
    if separator_candidate_on_mismatch is not None and separator_candidate_on_mismatch.confidence < threshold:
        override_reason = policy.candidate_selection.content_mismatch_candidate.override_reason
        separator_candidate_on_mismatch.detail["content_candidate_mismatch"] = {
            "content_candidate_confidence": float(best.confidence),
            "content_candidate_diagnostics": _candidate_detail_list(best, "diagnostics"),
            "content_candidate_blockers": _candidate_detail_list(best, "blockers"),
            "content_candidate_assessment": best.detail.get("candidate_assessment", {}),
        }
        best = separator_candidate_on_mismatch
        selection_override = override_reason
    second = next((candidate for candidate in candidates if candidate is not best), None)
    selected_policy = policy_context.policy_for(best.film_format, best.strip_mode)
    competition = [
        {
            "rank": index,
            "selected": candidate is best,
            **_candidate_summary(candidate),
        }
        for index, candidate in enumerate(candidates[: selected_policy.candidate_selection.top_n], start=1)
    ]
    best.detail["candidate_competition"] = {
        "candidate_count": len(candidates),
        "formats": [fmt.name],
        "selected_candidate": _candidate_summary(best),
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
        best_assessment = best.detail.get("candidate_assessment", {})
        best_partial_safe = bool(
            isinstance(best_assessment, dict)
            and isinstance(best_assessment.get("partial_safe_extra_frames"), dict)
            and best_assessment["partial_safe_extra_frames"].get("ok", False)
        )
        if (
            best.confidence >= threshold
            and not best_partial_safe
            and (second_close or partial_full_conflict)
        ):
            uncertainty_inputs = best.detail.setdefault("selection_uncertainty_inputs", [])
            if not isinstance(uncertainty_inputs, list):
                uncertainty_inputs = []
                best.detail["selection_uncertainty_inputs"] = uncertainty_inputs
            uncertainty_input = {
                "bucket": "candidate_selection",
                "signal": (
                    "partial_full_conflict"
                    if partial_full_conflict and not second_close
                    else "candidate_competition_close"
                ),
                "margin_to_second": float(margin),
                "close_margin": float(selected_policy.candidate_selection.close_margin),
                "partial_full_conflict": bool(partial_full_conflict),
            }
            uncertainty_inputs.append(uncertainty_input)
            best.detail["candidate_competition"]["selection_uncertainty_inputs"] = list(
                uncertainty_inputs
            )
        best.detail["candidate_competition"]["second_candidate_close"] = bool(second_close)
        best.detail["candidate_competition"]["partial_full_conflict"] = bool(partial_full_conflict)
        best.detail["candidate_competition"]["close_margin"] = float(
            selected_policy.candidate_selection.close_margin
        )
    return best


__all__ = [
    "SelectionResult",
    "calibrated_candidate_rank",
    "is_partial_safe_candidate",
    "select_detection_candidate",
    "select_separator_candidate_for_content_mismatch",
]
