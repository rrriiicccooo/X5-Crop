from __future__ import annotations

from ....domain import DetectionCandidate
from ....formats import FormatPhysicalSpec
from ....policies.parameters.scoring import CandidateCompetitionParameters
from ...detail import candidate_signals_from_detail


def _candidate_assessment(candidate: DetectionCandidate) -> dict:
    assessment = candidate.detail.get("candidate_assessment", {})
    return dict(assessment) if isinstance(assessment, dict) else {}


def calibrated_candidate_rank(
    detection: DetectionCandidate,
    threshold: float,
) -> tuple[int, float, float, float]:
    candidate = detection.detail.get("candidate_assessment", {})
    joint = float(candidate.get("joint_score", 0.0)) if isinstance(candidate, dict) else 0.0
    partial_edge_safety_supported = bool(
        isinstance(candidate, dict)
        and isinstance(candidate.get("partial_edge_safety"), dict)
        and candidate["partial_edge_safety"].get("ok", False)
    )
    if partial_edge_safety_supported:
        return (
            1 if detection.confidence >= threshold else 0,
            float(detection.count),
            float(detection.confidence),
            joint,
        )
    return (
        1 if detection.confidence >= threshold else 0,
        float(detection.confidence),
        int(detection.count),
        joint,
    )


def select_source_candidate(candidates: list[DetectionCandidate], threshold: float) -> DetectionCandidate:
    return max(candidates, key=lambda detection: calibrated_candidate_rank(detection, threshold))


def is_partial_edge_safety_candidate(detection: DetectionCandidate, threshold: float) -> bool:
    candidate = detection.detail.get("candidate_assessment", {})
    candidate_gate = {}
    if isinstance(candidate, dict):
        gate = candidate.get("candidate_gate")
        candidate_gate = dict(gate) if isinstance(gate, dict) else {}
    candidate_gate_allows_auto = bool(candidate_gate.get("passed", False))
    return bool(
        detection.strip_mode == "partial"
        and detection.confidence >= threshold
        and isinstance(candidate, dict)
        and isinstance(candidate.get("partial_edge_safety"), dict)
        and candidate["partial_edge_safety"].get("ok", False)
        and candidate_gate_allows_auto
    )


def _candidate_summary(candidate: DetectionCandidate) -> dict:
    assessment = _candidate_assessment(candidate)
    return {
        "format_id": candidate.format_id,
        "count": int(candidate.count),
        "strip_mode": candidate.strip_mode,
        "confidence": float(candidate.confidence),
        "candidate_signals": candidate_signals_from_detail(candidate),
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
    candidates: list[DetectionCandidate],
    fmt: FormatPhysicalSpec,
    threshold: float,
    selection_policy: CandidateCompetitionParameters,
) -> DetectionCandidate:
    candidates = sorted(candidates, key=lambda d: calibrated_candidate_rank(d, threshold), reverse=True)
    best = candidates[0]
    second = next((candidate for candidate in candidates if candidate is not best), None)
    competition = [
        {
            "rank": index,
            "selected": candidate is best,
            **_candidate_summary(candidate),
        }
        for index, candidate in enumerate(candidates[: selection_policy.top_n], start=1)
    ]
    best.detail["candidate_competition"] = {
        "candidate_count": len(candidates),
        "format_ids": [fmt.format_id],
        "selected_candidate": _candidate_summary(best),
        "top_candidates": competition,
    }
    if second is not None:
        margin = float(best.confidence) - float(second.confidence)
        best.detail["candidate_competition"]["margin_to_second"] = margin
        second_close = margin < selection_policy.close_margin
        partial_full_conflict = (
            best.strip_mode != second.strip_mode
            and min(best.confidence, second.confidence) >= threshold
        )
        best_assessment = best.detail.get("candidate_assessment", {})
        best_partial_edge_safety_supported = bool(
            isinstance(best_assessment, dict)
            and isinstance(best_assessment.get("partial_edge_safety"), dict)
            and best_assessment["partial_edge_safety"].get("ok", False)
        )
        if (
            best.confidence >= threshold
            and not best_partial_edge_safety_supported
            and (second_close or partial_full_conflict)
        ):
            uncertainty_input = {
                "bucket": "candidate_selection",
                "signal": (
                    "partial_full_conflict"
                    if partial_full_conflict and not second_close
                    else "candidate_competition_close"
                ),
                "margin_to_second": float(margin),
                "close_margin": float(selection_policy.close_margin),
                "partial_full_conflict": bool(partial_full_conflict),
            }
            uncertainty_inputs = list(
                best.detail["candidate_competition"].get("selection_uncertainty_inputs", [])
            )
            uncertainty_inputs.append(uncertainty_input)
            best.detail["candidate_competition"]["selection_uncertainty_inputs"] = list(
                uncertainty_inputs
            )
        best.detail["candidate_competition"]["second_candidate_close"] = bool(second_close)
        best.detail["candidate_competition"]["partial_full_conflict"] = bool(partial_full_conflict)
        best.detail["candidate_competition"]["close_margin"] = float(selection_policy.close_margin)
    return best
