from __future__ import annotations

from ..formats import FORMATS
from .factory_candidate import (
    candidate_plan_policy,
    partial_edge_hint_policy,
    partial_holder_policy,
    scoring_policy,
    selection_policy,
)
from .factory_common import count_policy, gate_policy, partial_frame_fit, report_policy
from .factory_content import content_policy
from .factory_finalization import diagnostics_policy, finalization_policy
from .factory_outer import outer_policy
from .factory_presets import FormatPolicyPreset
from .factory_separator import separator_policy
from .ids import detection_policy_id_for
from .runtime_base import DetectorPolicy
from .runtime_policy import DetectionPolicy


def build_policy_from_preset(
    preset: FormatPolicyPreset,
    strip_mode: str,
) -> DetectionPolicy:
    mode_preset = preset.modes[strip_mode]
    fmt = FORMATS[preset.format_id]
    params = preset.parameters()
    return DetectionPolicy(
        policy_id=detection_policy_id_for(preset.format_id, strip_mode),
        format_id=preset.format_id,
        strip_mode=strip_mode,
        family=fmt.family,
        role=mode_preset.role,
        detector=DetectorPolicy(
            kind=mode_preset.detector_kind,
            review_only=mode_preset.review_only,
        ),
        source_parameters=params,
        counts=count_policy(preset.format_id, strip_mode, params),
        outer=outer_policy(mode_preset, strip_mode, params),
        separator=separator_policy(preset, mode_preset, strip_mode, params),
        content=content_policy(params),
        partial_holder=partial_holder_policy(strip_mode, params),
        partial_edge_hint=partial_edge_hint_policy(params),
        frame_fit=mode_preset.frame_fit or partial_frame_fit(preset.format_id),
        gates=gate_policy(),
        scoring=scoring_policy(params),
        candidate_selection=selection_policy(preset, strip_mode, params),
        candidate_plan=candidate_plan_policy(),
        finalization=finalization_policy(params),
        diagnostics=diagnostics_policy(mode_preset, params),
        report=report_policy(),
        notes=mode_preset.notes,
    )


__all__ = [
    "build_policy_from_preset",
]
