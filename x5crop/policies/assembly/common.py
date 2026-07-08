from __future__ import annotations

from ...formats import FORMATS
from .profile_defaults import partial_count_parameters
from ..parameters.aggregate import FormatParameters
from ..runtime.base import (
    FULL,
    CountPolicy,
    FrameFitPolicy,
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
    partial = partial_count_parameters(fmt, params)
    return CountPolicy(
        fixed_count=None,
        auto_counts=tuple(reversed(fmt.allowed_counts)),
        partial_offsets=partial.offsets,
        include_default_in_partial_auto=bool(partial.include_default_auto),
    )


__all__ = [
    "partial_frame_fit",
    "count_policy",
]
