from __future__ import annotations

from .presets import ModePolicyPreset
from ..parameters.aggregate import FormatParameters
from ..runtime.output_evidence import (
    OutputOverlapEvidencePolicy,
    RuntimeOutputEvidencePolicy,
)


def runtime_output_evidence_policy(
    mode_preset: ModePolicyPreset,
    params: FormatParameters,
) -> RuntimeOutputEvidencePolicy:
    overlap = params.output.output_overlap
    return RuntimeOutputEvidencePolicy(
        output_overlap=OutputOverlapEvidencePolicy(
            enabled=mode_preset.output_overlap_enabled,
            bleed_protection_enabled=bool(overlap.bleed_protection_enabled),
            required_bleed_window_fraction=float(overlap.required_bleed_window_fraction),
            required_bleed_padding_px=int(overlap.required_bleed_padding_px),
            required_bleed_min_px=int(overlap.required_bleed_min_px),
            mean_min=float(overlap.mean_min),
            weak_continuity=float(overlap.weak_continuity),
            weak_activity=float(overlap.weak_activity),
            medium_continuity=float(overlap.medium_continuity),
            medium_activity=float(overlap.medium_activity),
            strong_continuity=float(overlap.strong_continuity),
            strong_activity=float(overlap.strong_activity),
        ),
    )


__all__ = [
    "runtime_output_evidence_policy",
]
