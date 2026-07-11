from __future__ import annotations

from dataclasses import dataclass

from ....cache import MeasurementCache
from ....domain import SequenceHypothesis
from ....formats import FormatPhysicalSpec
from ....policies.parameters.sequence import SequenceParameters
from ....policies.runtime.separator import SeparatorPolicy
from ....policies.parameters.candidate import SequenceHypothesisParameters
from ....units import ScanCalibration
from ...context import DetectionRequest
from ..plan.count_hypotheses import CountHypothesis
from ..proposal.sequence import sequence_hypotheses


@dataclass(frozen=True)
class FrameSequencePlan:
    hypotheses: tuple[SequenceHypothesis, ...]
    count_hypothesis: CountHypothesis


def frame_sequence_plan(
    request: DetectionRequest,
    fmt: FormatPhysicalSpec,
    count_hypothesis: CountHypothesis,
    *,
    cache: MeasurementCache,
    sequence_policy: SequenceParameters,
    separator_policy: SeparatorPolicy,
    hypothesis_parameters: SequenceHypothesisParameters,
    scan_calibration: ScanCalibration,
) -> FrameSequencePlan:
    if cache.layout != request.layout:
        raise ValueError("sequence planning requires matching measurement cache")
    hypotheses = sequence_hypotheses(
        cache.gray_work,
        fmt,
        count_hypothesis.count,
        cache,
        scan_calibration,
        request.layout,
        sequence_policy=sequence_policy,
        separator_policy=separator_policy,
        hypothesis_parameters=hypothesis_parameters,
    )
    return FrameSequencePlan(tuple(hypotheses), count_hypothesis)
