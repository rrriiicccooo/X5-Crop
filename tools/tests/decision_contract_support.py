from __future__ import annotations

from pathlib import Path

import numpy as np

from x5crop.detection.decision.decision_gate import apply_decision_gate
from x5crop.detection.evidence.selected_candidate import complete_selected_candidate_evidence
from x5crop.domain import Box, DetectionCandidate, FinalDetection
from x5crop.policies.decision.contract import decision_contract_for_policy
from x5crop.policies.registry import get_detection_policy
from x5crop.run_config import RunConfig


def decision_test_config(*, threshold: float = 0.85) -> RunConfig:
    return RunConfig(
        input_path=Path("synthetic.tif"),
        output_dir=None,
        format_id="135",
        layout_auto=False,
        layout="horizontal",
        strip_mode="full",
        requested_count=1,
        page=0,
        bleed_x=0,
        bleed_y=0,
        deskew="off",
        deskew_fallback="off",
        deskew_min_angle=-2.0,
        deskew_max_angle=2.0,
        confidence_threshold=threshold,
        review_dir=None,
        copy_review_files=False,
        export_review=False,
        diagnostics=False,
        compression="auto",
        debug=False,
        debug_analysis=False,
        dry_run=True,
        overwrite=True,
        report=True,
        debug_errors=False,
        reuse_analysis=False,
        jobs=1,
    )


def content_ok_detail() -> dict[str, bool | str]:
    return {
        "used": True,
        "support": "ok",
        "content_containment_ok": True,
        "content_integrity_failed": False,
    }


def decision_contract(format_id: str = "135", strip_mode: str = "full"):
    return decision_contract_for_policy(get_detection_policy(format_id, strip_mode))


def candidate_gate_detail(
    passed: bool,
    *,
    blockers: list[str] | None = None,
    diagnostics: list[str] | None = None,
) -> dict:
    return {
        "passed": bool(passed),
        "checks": [],
        "blockers": list(blockers or []),
        "diagnostics": list(diagnostics or []),
        "confidence_caps": [],
    }


def final_detection_fixture(
    *,
    status: str = "needs_review",
    final_review_reasons: list[str] | None = None,
    detail: dict | None = None,
) -> FinalDetection:
    requested_reasons = set(final_review_reasons or [])
    count = 2 if "separator_evidence_incomplete" in requested_reasons else 1
    confidence = 0.99 if status == "approved_auto" or requested_reasons else 0.80
    candidate_detail = {
        "candidate_assessment": {
            "source": "separator",
            "geometry_score": 1.0,
            "content_score": 1.0,
            "content_quality_score": 1.0,
            "separator_support": {
                "expected_gaps": max(0, count - 1),
                "hard_gaps": 0,
                "grid_gaps": 0,
                "equal_gaps": 0,
                "content_gaps": 0,
            },
            "partial_edge_safety": {"ok": False},
            "candidate_gate": candidate_gate_detail(True),
        },
        "candidate_source": "separator",
        "outer_area_ratio": 0.64,
        "width_cv": 0.0,
        "width_cv_source": "photo_edges",
        "photo_width_cv": 0.0,
        "photo_width_cv_source": "photo_edges",
        "exposure_overlap_evidence": {"exposure_overlap_detected": False},
        "output_protection_plan": {"feasible": True},
    }
    if "candidate_competition_close" in requested_reasons:
        candidate_detail["candidate_competition"] = {"margin_to_second": 0.0}
    candidate = DetectionCandidate(
        format_id="135",
        layout="horizontal",
        strip_mode="full",
        count=count,
        outer=Box(10, 10, 90, 90),
        frames=[Box(10, 10, 90, 90)] * count,
        gaps=[],
        confidence=confidence,
        detail=candidate_detail,
    )
    outer_alignment = {
        "used": True,
        "ok": "outer_content_mismatch" not in requested_reasons,
        "overcontainment_allowed": False,
    }
    final = apply_decision_gate(
        np.zeros((100, 100), dtype=np.uint8),
        candidate,
        decision_test_config(threshold=0.85),
        content_ok_detail(),
        outer_alignment,
        policy=decision_contract(),
        deskew_detail={},
    )
    if detail:
        final.detail.update(detail)
    return final


def apply_test_detection_decision(
    gray,
    candidate,
    config,
    cache,
    deskew_detail,
    policy,
    contract,
):
    evidence = complete_selected_candidate_evidence(
        gray,
        candidate,
        cache,
        content_policy=policy.content,
        alignment_parameters=policy.outer.alignment_evidence,
        horizontal_frame_aspect=contract.physical_spec.horizontal_content_aspect,
    )
    return apply_decision_gate(
        gray,
        evidence.candidate,
        config,
        evidence.content,
        evidence.outer_alignment,
        policy=contract,
        deskew_detail=deskew_detail,
    )
