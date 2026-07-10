from __future__ import annotations

from ..parameters.aggregate import FormatParameters
from ..runtime.base import CountHypothesisPolicy


def count_hypothesis_policy(params: FormatParameters) -> CountHypothesisPolicy:
    return CountHypothesisPolicy(
        partial_offsets=params.candidate.partial_counts.offsets,
    )
