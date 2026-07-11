from __future__ import annotations

from typing import Any

from x5crop.detection.decision.decision_gate import apply_decision_gate
from x5crop.detection.evidence.frame_coverage import FrameCoverageEvidence
from x5crop.detection.evidence.state import EvidenceState
from x5crop.domain import (
    AxisBleedParameters,
    Box,
    DetectionCandidate,
    FinalDetection,
    OutputProtectionPlan,
)


def candidate_gate_detail(
    *,
    passed: bool = True,
    failed_check: str = "boundary_proof",
) -> dict[str, Any]:
    checks = []
    if not passed:
        checks.append(
            {
                "code": failed_check,
                "stage": "candidate",
                "state": "contradicted",
                "consequence": "blocker",
                "blocks": True,
                "detail": {},
            }
        )
    return {
        "passed": passed,
        "checks": checks,
        "proof_paths": (
            [
                {
                    "code": "separator_led",
                    "state": "supported",
                    "detail": {},
                }
            ]
            if passed
            else []
        ),
        "failed_checks": [] if passed else [failed_check],
        "diagnostics": [],
    }


def candidate_fixture(
    *,
    confidence: float = 0.90,
    candidate_gate_passed: bool = True,
    failed_check: str = "boundary_proof",
    automatic_processing_supported: bool = True,
    geometry_disagreement: bool = False,
) -> DetectionCandidate:
    return DetectionCandidate(
        format_id="135",
        layout="horizontal",
        strip_mode="full",
        count=2,
        outer=Box(0, 0, 200, 100),
        frames=[Box(0, 0, 100, 100), Box(100, 0, 200, 100)],
        gaps=[],
        confidence=confidence,
        detail={
            "automatic_processing_supported": automatic_processing_supported,
            "candidate_assessment": {
                "source": "separator",
                "candidate_gate": candidate_gate_detail(
                    passed=candidate_gate_passed,
                    failed_check=failed_check,
                ),
            },
            "selection_geometry_consensus": {
                "agreed": not geometry_disagreement,
                "geometry_disagreement": geometry_disagreement,
                "cluster_count": 2 if geometry_disagreement else 1,
            },
        },
    )


def output_protection_fixture(*, feasible: bool = True) -> OutputProtectionPlan:
    return OutputProtectionPlan(
        base_bleed=AxisBleedParameters(20, 10),
        output_bleed=AxisBleedParameters(40 if feasible else 50, 10),
        exposure_overlap_detected=True,
        required_long_axis_bleed_px=40 if feasible else 80,
        available_long_axis_bleed_px=50,
        feasible=feasible,
        reason=(
            "exposure_overlap_protection_planned"
            if feasible
            else "exposure_overlap_exceeds_bleed_capacity"
        ),
    )


def supported_frame_coverage() -> FrameCoverageEvidence:
    return FrameCoverageEvidence(
        state=EvidenceState.SUPPORTED,
        reason="content_runs_covered",
        holder_interval=(0, 200),
        film_interval=(0, 200),
        frame_intervals=((0, 200),),
        content_runs=((0, 200),),
        uncovered_content=(),
    )


def decide_candidate(
    candidate: DetectionCandidate | None = None,
    *,
    content_detail: dict[str, Any] | None = None,
    outer_alignment: dict[str, Any] | None = None,
    deskew_detail: dict[str, Any] | None = None,
    output_protection_feasible: bool = True,
) -> FinalDetection:
    return apply_decision_gate(
        candidate or candidate_fixture(),
        content_detail
        or {
            "used": True,
            "frame_content_support_available": True,
        },
        outer_alignment or {"used": True, "ok": True},
        supported_frame_coverage(),
        deskew_detail=deskew_detail or {"applied": False},
        output_protection_plan=output_protection_fixture(
            feasible=output_protection_feasible,
        ),
    )


def final_detection_fixture(
    *,
    status: str = "approved_auto",
    confidence: float = 0.90,
    final_review_reasons: list[str] | None = None,
    detail: dict[str, Any] | None = None,
) -> FinalDetection:
    candidate = candidate_fixture(confidence=confidence)
    if detail is not None:
        candidate.detail = dict(detail)
    else:
        candidate.detail["decision_summary"] = {
            "decision_gate": {
                "passed": status == "approved_auto",
                "checks": [],
                "reason_inputs": [],
            }
        }
    return FinalDetection.from_candidate(
        candidate,
        status=status,
        final_review_reasons=list(final_review_reasons or []),
    )
