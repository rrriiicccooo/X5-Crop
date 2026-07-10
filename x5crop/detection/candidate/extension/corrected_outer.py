from __future__ import annotations

from dataclasses import asdict

import numpy as np

from ....cache import AnalysisCache
from ....domain import DetectionCandidate
from ....formats import FormatPhysicalSpec
from ....policies.runtime.policy import DetectionPolicy
from ....run_config import RunConfig
from ...physical.outer.correction.types import OuterCorrectionProposal


def build_assessed_corrected_outer_candidate(
    gray: np.ndarray,
    config: RunConfig,
    fmt: FormatPhysicalSpec,
    detection: DetectionCandidate,
    corrected: OuterCorrectionProposal,
    cache: AnalysisCache,
    policy: DetectionPolicy,
) -> DetectionCandidate:
    from ...evidence.content.frame_support import content_evidence_detail
    from ...evidence.outer_alignment import outer_content_alignment_detail
    from ...physical.separator.proposal import separator_gap_search_detail
    from ..assessment.candidate import apply_candidate_assessment_policy
    from ..build.detection import build_detection_geometry_for_outer, enrich_detection_geometry_evidence

    reassessed = build_detection_geometry_for_outer(
        gray,
        config,
        fmt,
        detection.count,
        detection.strip_mode,
        corrected.box,
        float(detection.detail.get("offset_fraction", 0.0)),
        corrected.name,
        corrected.strategy,
        outer_candidate_detail={
            "family": "outer_correction",
            "source_reason": corrected.source_reason,
            "original_outer_work_box": corrected.original_outer_work_box,
            **corrected.detail,
        },
        cache=cache,
        allow_outer_refine=False,
        gap_max_width_ratio_override=None,
        policy=policy,
    )
    reassessed = enrich_detection_geometry_evidence(gray, reassessed, config, fmt, cache, policy=policy)
    reassessed = apply_candidate_assessment_policy(gray, reassessed, config, fmt, "separator", cache, policy=policy)
    reassessed.detail["separator_gap_search"] = separator_gap_search_detail(
        policy.separator.width_profile
    )

    reassessed_alignment = outer_content_alignment_detail(
        gray,
        reassessed,
        cache,
        alignment_policy=policy.outer.alignment_evidence,
    )
    reassessed_content = content_evidence_detail(
        gray,
        reassessed,
        cache,
        content_policy=policy.content,
        horizontal_frame_aspect=fmt.horizontal_content_aspect,
    )
    reassessed.detail["outer_content_alignment"] = reassessed_alignment
    reassessed.detail["content_evidence"] = reassessed_content
    reassessed.detail["outer_correction"] = {
        "used": True,
        "source_reason": corrected.source_reason,
        "original_outer_work_box": corrected.original_outer_work_box,
        "corrected_outer_work_box": asdict(corrected.box),
        "suppress_outer_mismatch": bool(corrected.suppress_outer_mismatch),
        "reassessed_alignment": reassessed_alignment,
        "reassessed_content_support": reassessed_content.get("support"),
        "candidate_reassessment": {
            "used": True,
            "owner": "candidate.extension",
            "source": "separator",
        },
    }
    reassessed.detail["outer_correction"].update(corrected.detail)
    return reassessed
