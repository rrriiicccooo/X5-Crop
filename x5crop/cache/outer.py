from __future__ import annotations

from collections.abc import Callable

from ..domain import OuterCandidate
from ..geometry.detection_parameters import OuterBoxDetectionParameters
from . import AnalysisCache


def cached_base_outer_candidates(
    cache: AnalysisCache | None,
    parameters: OuterBoxDetectionParameters,
    compute: Callable[[], list[OuterCandidate]],
) -> list[OuterCandidate]:
    if cache is None:
        return compute()
    key = (parameters,)
    candidates = cache.base_outer_candidates.get(key)
    if candidates is None:
        candidates = compute()
        cache.base_outer_candidates[key] = list(candidates)
    return list(candidates)
