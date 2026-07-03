from __future__ import annotations

from typing import Any

import numpy as np

from ...domain import Detection
from ...formats import FormatSpec
from ...constants import ANALYSIS_SOURCE_HARD_SAFETY
from ...runtime import AnalysisCache
from ...runtime_config import RuntimeConfig
from ...policies.runtime_policy import DetectionPolicy
from ..evidence.content_evidence import content_evidence_detail
from ..evidence.outer_alignment import outer_content_alignment_detail
from .corrected_outer import build_assessed_corrected_outer_candidate
from ..outer.correction.content_containment import content_containment_correction_proposal
from ..outer.correction.geometry import geometry_consistency_correction_proposal, geometry_consistency_model_detail


def outer_correction_candidate_extensions(
    gray: np.ndarray,
    config: RuntimeConfig,
    fmt: FormatSpec,
    detection: Detection,
    cache: AnalysisCache,
    policy: DetectionPolicy,
) -> list[Detection]:
    if detection.detail.get("analysis_source") == ANALYSIS_SOURCE_HARD_SAFETY:
        return []
    if not bool(policy.candidate_plan.outer_correction_extension.enabled):
        return []

    content_detail = content_evidence_detail(gray, detection, cache, policy.content)
    detection.detail["content_evidence"] = content_detail
    outer_alignment = (
        outer_content_alignment_detail(gray, detection, cache, policy=policy)
        if policy.finalization.align_outer_to_content
        else {"used": False, "reason": policy.finalization.outer_alignment_disabled_reason}
    )
    detection.detail["outer_content_alignment"] = outer_alignment

    extensions: list[Detection] = []
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
        reassessed.detail["candidate_plan"] = {
            "source": "outer_correction_candidate",
            "extension_of": detection.detail.get("candidate_plan", {}),
            "correction_order": "geometry_consistency",
        }
        extensions.append(reassessed)
        return extensions

    if bool(outer_alignment.get("used", False)) and not bool(outer_alignment.get("ok", True)):
        proposal = content_containment_correction_proposal(config, fmt, detection, outer_alignment, cache)
        if proposal is not None:
            reassessed = build_assessed_corrected_outer_candidate(gray, config, fmt, detection, proposal, cache, policy)
            reassessed.detail["candidate_plan"] = {
                "source": "outer_correction_candidate",
                "extension_of": detection.detail.get("candidate_plan", {}),
                "correction_order": "content_containment",
            }
            extensions.append(reassessed)
            return extensions
        detection.detail["outer_correction"] = {
            "used": False,
            "reason": "no_valid_content_containment_correction",
        }

    return extensions


__all__ = ["outer_correction_candidate_extensions"]
