from __future__ import annotations

from ...formats import FORMATS
from .candidate import (
    candidate_plan_policy,
    partial_edge_hint_policy,
    partial_holder_policy,
    scoring_policy,
    selection_policy,
)
from .common import count_policy, partial_frame_fit
from .content import content_policy
from .decision import runtime_decision_policy
from .diagnostics import diagnostics_policy
from .finalization import finalization_policy
from .outer import outer_policy
from .output import output_policy
from .preprocess import preprocess_policy
from .presets import FormatPolicyPreset
from .report import report_policy
from .output_evidence import runtime_output_evidence_policy
from .separator import separator_policy
from ..ids import detection_policy_id_for
from ..runtime.base import DetectorPolicy
from ..runtime.policy import DetectionPolicy


def build_policy_from_preset(
    preset: FormatPolicyPreset,
    strip_mode: str,
) -> DetectionPolicy:
    mode_preset = preset.modes[strip_mode]
    fmt = FORMATS[preset.format_id]
    params = preset.parameters()
    preprocess = preprocess_policy(params)
    return DetectionPolicy(
        policy_id=detection_policy_id_for(preset.format_id, strip_mode),
        format_id=preset.format_id,
        strip_mode=strip_mode,
        family=fmt.family,
        default_count=int(fmt.default_count),
        preprocess=preprocess,
        detector=DetectorPolicy(
            kind=mode_preset.detector_kind,
            review_only=mode_preset.review_only,
        ),
        counts=count_policy(fmt, strip_mode, params),
        outer=outer_policy(mode_preset, strip_mode, params, fmt),
        separator=separator_policy(preset, mode_preset, strip_mode, params),
        content=content_policy(params, evidence_image=preprocess.content_evidence_image),
        partial_holder=partial_holder_policy(fmt, mode_preset, strip_mode, params),
        partial_edge_hint=partial_edge_hint_policy(params),
        frame_fit=mode_preset.frame_fit or partial_frame_fit(fmt),
        scoring=scoring_policy(fmt, params),
        candidate_selection=selection_policy(preset, strip_mode, params),
        candidate_plan=candidate_plan_policy(mode_preset, strip_mode, params),
        output_evidence=runtime_output_evidence_policy(mode_preset, params),
        decision=runtime_decision_policy(params),
        finalization=finalization_policy(params),
        output=output_policy(),
        diagnostics=diagnostics_policy(params),
        report=report_policy(),
    )


__all__ = [
    "build_policy_from_preset",
]
