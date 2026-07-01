from __future__ import annotations

from ..formats import FORMATS
from .factory_presets import FormatPolicyPreset, ModePolicyPreset
from .parameter_aggregate import FormatParameters
from .runtime_policy import (
    FULL,
    CountPolicy,
    FrameFitPolicy,
    GatePolicy,
    ReportPolicy,
)

def partial_frame_fit(format_id: str) -> FrameFitPolicy:
    return FrameFitPolicy(
        name=f"{format_id}-partial",
        edge_evidence=False,
        geometry_fallback=True,
    )

def count_policy(fmt_id: str, strip_mode: str, params: FormatParameters) -> CountPolicy:
    fmt = FORMATS[fmt_id]
    if strip_mode == FULL:
        return CountPolicy(fixed_count=None, auto_counts=(fmt.default_count,))
    partial = params.partial_counts
    return CountPolicy(
        fixed_count=None,
        auto_counts=tuple(reversed(fmt.allowed_counts)),
        partial_offsets=partial.offsets,
        include_default_in_partial_auto=bool(partial.include_default_auto),
    )

def gate_policy() -> GatePolicy:
    return GatePolicy(
        ordered_gates=(
            "confidence_floor_gate",
            "separator_gate",
            "content_gate",
            "geometry_gate",
            "mode_specific_gate",
            "hard_review_reason_gate",
            "auto_pass_gate",
            "finalization_gate",
        ),
    )

def report_policy() -> ReportPolicy:
    return ReportPolicy()

__all__ = [
    'partial_frame_fit',
    'count_policy',
    'gate_policy',
    'report_policy',
]
