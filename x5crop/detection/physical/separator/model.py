from __future__ import annotations

import numpy as np

from ....domain import Gap
from ....geometry.model_gaps import equal_model_gap


def propose_equal_model_gap(index: int, expected: float, score: float) -> Gap:
    return equal_model_gap(index, expected, score)


def profile_score_at(profile: np.ndarray, position: float) -> float:
    if profile.size <= 0:
        return 0.0
    index = min(len(profile) - 1, max(0, int(round(position))))
    return float(profile[index])


def propose_equal_model_gaps_from_profile(
    profile: np.ndarray,
    origin: float,
    pitch: float,
    count: int,
) -> list[Gap]:
    return [
        propose_equal_model_gap(index, origin + pitch * index, profile_score_at(profile, origin + pitch * index))
        for index in range(1, count)
    ]


__all__ = [
    "profile_score_at",
    "propose_equal_model_gap",
    "propose_equal_model_gaps_from_profile",
]
