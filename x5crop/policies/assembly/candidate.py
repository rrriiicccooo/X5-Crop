from __future__ import annotations

from ..parameters.aggregate import FormatParameters
from ..runtime.base import PARTIAL
from ..runtime.candidate import (
    PartialHolderPolicy,
    ScoringPolicy,
)


def partial_holder_policy(
    detector_kind: str,
    strip_mode: str,
    params: FormatParameters,
) -> PartialHolderPolicy:
    holder = params.candidate.partial_holder
    content_evidence = params.content.content_evidence
    partial_edge_safety_enabled = bool(
        strip_mode == PARTIAL and detector_kind != "review_only"
    )
    return PartialHolderPolicy(
        enabled=partial_edge_safety_enabled,
        parameters=holder,
        max_frame_aspect_error=float(content_evidence.aspect_ok_max),
    )


def scoring_policy(params: FormatParameters) -> ScoringPolicy:
    return ScoringPolicy(
        calibration=params.candidate.scoring_calibration,
        base_detection=params.candidate.base_detection_score,
        geometry_support=params.candidate.geometry_support_score,
        separator_support=params.candidate.separator_support_score,
    )
