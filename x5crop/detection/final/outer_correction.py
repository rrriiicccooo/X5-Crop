from __future__ import annotations

from typing import Any

import numpy as np

from ...domain import Detection
from ...formats import FormatSpec
from ...policies.registry import get_detection_policy
from ...runtime import AnalysisCache
from ...runtime_config import RuntimeConfig
from ..candidate.corrected_outer import build_assessed_corrected_outer_candidate
from ..outer.correction.content_containment import content_containment_correction_proposal
from ..outer.correction.geometry import geometry_consistency_correction_proposal, geometry_consistency_model_detail


def apply_outer_correction_flow(
    gray: np.ndarray,
    config: RuntimeConfig,
    fmt: FormatSpec,
    detection: Detection,
    content_detail: dict[str, Any],
    outer_alignment: dict[str, Any],
    cache: AnalysisCache,
) -> tuple[Detection, dict[str, Any], dict[str, Any], bool]:
    policy = get_detection_policy(fmt.name, detection.strip_mode)
    proposal = geometry_consistency_correction_proposal(
        gray,
        config,
        fmt,
        detection,
        content_detail,
        outer_alignment,
        cache,
    )
    if proposal is not None:
        reassessed = build_assessed_corrected_outer_candidate(gray, config, fmt, detection, proposal, cache, policy)
        if "source_geometry_consistency" in proposal.detail:
            reassessed_geometry = geometry_consistency_model_detail(gray, reassessed, config, fmt, cache)
            reassessed.detail["geometry_consistency_model"] = reassessed_geometry
            reassessed.detail["outer_correction"]["reassessed_geometry_consistency"] = reassessed_geometry
        return (
            reassessed,
            dict(reassessed.detail.get("content_evidence", {})),
            dict(reassessed.detail.get("outer_content_alignment", {})),
            proposal.suppress_outer_mismatch,
        )

    if bool(outer_alignment.get("used", False)) and not bool(outer_alignment.get("ok", True)):
        proposal = content_containment_correction_proposal(config, fmt, detection, outer_alignment, cache)
        if proposal is not None:
            reassessed = build_assessed_corrected_outer_candidate(gray, config, fmt, detection, proposal, cache, policy)
            return (
                reassessed,
                dict(reassessed.detail.get("content_evidence", {})),
                dict(reassessed.detail.get("outer_content_alignment", {})),
                False,
            )
        detection.detail["outer_correction"] = {
            "used": False,
            "reason": "no_valid_content_containment_correction",
        }

    return detection, content_detail, outer_alignment, False


__all__ = ["apply_outer_correction_flow"]
