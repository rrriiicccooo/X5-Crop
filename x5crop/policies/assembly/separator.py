from __future__ import annotations

from ..parameters.aggregate import FormatParameters
from ..runtime.separator import SeparatorPolicy


def separator_policy(
    params: FormatParameters,
) -> SeparatorPolicy:
    return SeparatorPolicy(
        observation=params.separator.separator_observation,
        frame_dimension_prior=params.separator.frame_dimension_prior,
        continuity=params.separator.separator_continuity,
        profile=params.separator.separator_profile,
    )
