from __future__ import annotations

from dataclasses import replace

from ...formats import FormatPhysicalSpec
from ..parameters.aggregate import FormatParameters
from ..runtime.base import FULL, PARTIAL
from .candidate import (
    partial_holder_policy,
    scoring_policy,
)
from .common import count_hypothesis_policy
from .content import content_policy
from .diagnostics import diagnostics_policy
from .finalization import finalization_policy
from .outer import outer_policy
from .output import output_policy
from .preprocess import preprocess_policy
from .separator import separator_policy
from ..identity import detection_policy_id_for
from ..runtime.base import DetectorPolicy
from ..runtime.policy import DetectionPolicy


def _detector_kind(spec: FormatPhysicalSpec, strip_mode: str) -> str:
    if spec.physical_layout == "dual_lane" and strip_mode == FULL:
        return "dual_lane"
    if spec.physical_layout == "dual_lane" and strip_mode == PARTIAL:
        return "review_only"
    return "standard_strip"


def build_detection_policy(
    spec: FormatPhysicalSpec,
    params: FormatParameters,
    strip_mode: str,
) -> DetectionPolicy:
    detector_kind = _detector_kind(spec, strip_mode)
    preprocess = preprocess_policy(params)
    separator = separator_policy(strip_mode, detector_kind, params)
    decision_evidence = (
        params.decision.partial_evidence
        if strip_mode == "partial"
        else params.decision.full_evidence
    )
    decision_evidence = replace(
        decision_evidence,
        allow_geometry_supported_separator=bool(
            separator.geometry_support.active_modes()
        ),
    )
    return DetectionPolicy(
        policy_id=detection_policy_id_for(spec.format_id, strip_mode),
        physical_spec=spec,
        strip_mode=strip_mode,
        preprocess=preprocess,
        detector=DetectorPolicy(
            kind=detector_kind,
        ),
        count_hypotheses=count_hypothesis_policy(params),
        outer=outer_policy(detector_kind, strip_mode, params),
        separator=separator,
        content=content_policy(params, evidence_image=preprocess.content_evidence_image),
        partial_holder=partial_holder_policy(detector_kind, strip_mode, params),
        partial_edge_hint=params.candidate.partial_edge_hint,
        frame_fit=(
            params.candidate.partial_frame_fit
            if strip_mode == "partial"
            else params.candidate.full_frame_fit
        ),
        scoring=scoring_policy(params),
        candidate_selection=params.candidate.candidate_competition,
        candidate_plan=params.candidate.candidate_plan,
        exposure_overlap_evidence=params.output.exposure_overlap_evidence,
        decision_evidence=decision_evidence,
        decision=params.decision.decision_review,
        finalization=finalization_policy(params),
        output=output_policy(params),
        diagnostics=diagnostics_policy(params),
    )
