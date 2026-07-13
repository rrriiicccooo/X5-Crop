from __future__ import annotations

from dataclasses import dataclass

from ....cache import MeasurementCache
from ....configuration.boundary import BoundaryPathParameters
from ....domain import PhotoSequenceSearchScope
from ...context import DetectionRequest
from ..plan.count_hypotheses import CountHypothesis
from ..proposal.sequence import photo_sequence_search_scope


@dataclass(frozen=True)
class PhotoSequencePlan:
    search_scope: PhotoSequenceSearchScope
    count_hypothesis: CountHypothesis


def photo_sequence_plan(
    request: DetectionRequest,
    count_hypothesis: CountHypothesis,
    *,
    cache: MeasurementCache,
    boundary_parameters: BoundaryPathParameters,
) -> PhotoSequencePlan:
    if cache.layout != request.layout:
        raise ValueError("photo sequence planning requires matching measurement cache")
    return PhotoSequencePlan(
        search_scope=photo_sequence_search_scope(cache, boundary_parameters),
        count_hypothesis=count_hypothesis,
    )
