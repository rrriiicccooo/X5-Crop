from __future__ import annotations

from ...formats import FormatPhysicalSpec
from ..parameters.aggregate import FormatParameters
from ..runtime.base import CountHypothesisPolicy, FrameFitPolicy


def partial_frame_fit(fmt: FormatPhysicalSpec) -> FrameFitPolicy:
    return FrameFitPolicy(
        name=f"{fmt.format_id}-partial",
        edge_evidence=False,
    )


def count_hypothesis_policy(params: FormatParameters) -> CountHypothesisPolicy:
    return CountHypothesisPolicy(
        partial_offsets=params.candidate.partial_counts.offsets,
    )
