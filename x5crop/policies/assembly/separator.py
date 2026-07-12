from __future__ import annotations

from ..parameters.aggregate import FormatParameters
from ..runtime.separator import SeparatorPolicy


def separator_policy(
    params: FormatParameters,
) -> SeparatorPolicy:
    return SeparatorPolicy(
        observation=params.separator.separator_observation,
        profile=params.separator.separator_profile,
    )
