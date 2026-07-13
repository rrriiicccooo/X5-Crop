from __future__ import annotations

from dataclasses import dataclass

from ....cache import MeasurementCache
from ....domain import SequenceHypothesis
from ....formats import FormatPhysicalSpec
from ....configuration.content import ContentConfiguration
from ....configuration.boundary import BoundaryPathParameters
from ....configuration.separator import SeparatorConfiguration
from ....configuration.candidate import SequenceHypothesisParameters
from ....units import ScanCalibrationResolution
from ...context import DetectionRequest
from ..plan.count_hypotheses import CountHypothesis
from ..proposal.sequence import sequence_hypotheses


@dataclass(frozen=True)
class FrameSequencePlan:
    hypotheses: tuple[SequenceHypothesis, ...]
    count_hypothesis: CountHypothesis
    search_budget_exhausted: bool


def frame_sequence_plan(
    request: DetectionRequest,
    fmt: FormatPhysicalSpec,
    count_hypothesis: CountHypothesis,
    *,
    cache: MeasurementCache,
    boundary_parameters: BoundaryPathParameters,
    content_configuration: ContentConfiguration,
    separator_configuration: SeparatorConfiguration,
    hypothesis_parameters: SequenceHypothesisParameters,
    scan_calibration: ScanCalibrationResolution,
) -> FrameSequencePlan:
    if cache.layout != request.layout:
        raise ValueError("sequence planning requires matching measurement cache")
    hypothesis_set = sequence_hypotheses(
        cache.gray_work,
        fmt,
        count_hypothesis.count,
        cache,
        scan_calibration,
        request.layout,
        boundary_parameters=boundary_parameters,
        content_configuration=content_configuration,
        separator_configuration=separator_configuration,
        hypothesis_parameters=hypothesis_parameters,
    )
    return FrameSequencePlan(
        hypothesis_set.hypotheses,
        count_hypothesis,
        hypothesis_set.budget_exhausted,
    )
