from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations, islice
import math

import numpy as np

from ....cache import MeasurementCache
from ....cache.separator import cached_separator_profile
from ....domain import (
    BoundaryPathGroup,
    BoundaryPathObservation,
    BoundarySide,
    Box,
    CropEnvelope,
    EvidenceState,
    MeasurementIdentity,
    MeasurementProvenance,
    SequenceHypothesis,
    VisibleSequenceSpan,
)
from ....formats import FormatPhysicalSpec
from ....configuration.content import ContentConfiguration
from ....configuration.boundary import BoundaryPathParameters
from ....configuration.separator import SeparatorConfiguration
from ....configuration.candidate import SequenceHypothesisParameters
from ....units import ScanCalibrationResolution
from ...guidance.content_crop_envelope import expand_crop_envelopes_for_content
from ...physical.sequence import (
    base_sequence_span_candidates,
    unique_sequence_hypotheses,
)
from ...physical.boundary_detection import boundary_path_groups
from ...physical.photo_size import frame_dimension_priors
from ...physical.separator.observations import measure_separator_bands


@dataclass(frozen=True)
class SequenceHypothesisSet:
    hypotheses: tuple[SequenceHypothesis, ...]
    budget_exhausted: bool


def cached_boundary_path_groups(
    cache: MeasurementCache,
    parameters: BoundaryPathParameters,
) -> tuple[BoundaryPathGroup, ...]:
    groups = cache.boundary_path_groups.get(parameters)
    if groups is None:
        groups = boundary_path_groups(
            cache.gray_work,
            cache.image_statistics,
            parameters,
        )
        cache.boundary_path_groups[parameters] = groups
    return groups


def _measurement_corridor(
    source: SequenceHypothesis,
    cache: MeasurementCache,
) -> Box:
    height, width = cache.gray_work.shape
    crop = source.crop_envelope.box
    corridor = Box(0, max(0, crop.top), width, min(height, crop.bottom))
    return corridor if corridor.valid() else Box(0, 0, width, height)


def _compatible_boundary_paths(
    source: SequenceHypothesis,
    box: Box,
) -> tuple[BoundaryPathObservation, ...]:
    compatible = []
    for observation in source.boundary_paths:
        if observation.side in {BoundarySide.TOP, BoundarySide.BOTTOM}:
            compatible.append(observation)
            continue
        if observation.side == BoundarySide.LEADING:
            coordinate = float(box.left)
        elif observation.side == BoundarySide.TRAILING:
            coordinate = float(box.right)
        else:
            raise ValueError("sequence boundary path has an unknown side")
        if observation.position.minimum <= coordinate <= observation.position.maximum:
            compatible.append(observation)
    return tuple(compatible)


def _separator_dimension_hypotheses(
    base: list[SequenceHypothesis],
    fmt: FormatPhysicalSpec,
    count: int,
    cache: MeasurementCache,
    calibration: ScanCalibrationResolution,
    layout: str,
    separator_configuration: SeparatorConfiguration,
    hypothesis_parameters: SequenceHypothesisParameters,
) -> SequenceHypothesisSet:
    if count <= 1:
        return SequenceHypothesisSet((), False)
    observation_budget = int(hypothesis_parameters.observation_budget)
    if observation_budget < count - 1:
        return SequenceHypothesisSet((), True)
    height, width = cache.gray_work.shape
    candidates: list[tuple[float, SequenceHypothesis]] = []
    budget_exhausted = False
    for source in base:
        corridor = _measurement_corridor(source, cache)
        profile = cached_separator_profile(
            cache,
            corridor,
            separator_configuration.profile,
        )
        observation_set = measure_separator_bands(
            profile,
            gray_work=cache.gray_work,
            corridor=corridor,
            statistics=cache.image_statistics,
            parameters=separator_configuration.observation,
        )
        observations = tuple(
            observation
            for observation in observation_set.observations
            if observation.cross_axis.state == EvidenceState.SUPPORTED
        )
        budget_exhausted |= observation_set.budget_exhausted
        if len(observations) < count - 1:
            continue
        budget_exhausted |= len(observations) > observation_budget
        strongest = tuple(
            sorted(
                sorted(
                    observations,
                    key=lambda item: (item.tonal_evidence, item.width),
                    reverse=True,
                )[:observation_budget],
                key=lambda item: item.center,
            )
        )
        for dimensions in frame_dimension_priors(
            source.visible_sequence_span,
            fmt,
            calibration,
            layout=layout,
        ):
            frame_width = dimensions.width_px.midpoint
            remaining_evaluations = max(
                0,
                int(hypothesis_parameters.maximum_hypotheses) - len(candidates),
            )
            combination_count = math.comb(len(strongest), count - 1)
            budget_exhausted |= combination_count > remaining_evaluations
            for sequence in islice(
                combinations(strongest, count - 1),
                remaining_evaluations,
            ):
                leading = int(round(sequence[0].start - frame_width))
                trailing = int(round(sequence[-1].end + frame_width))
                box = Box(
                    max(0, leading),
                    source.visible_sequence_span.box.top,
                    min(width, trailing),
                    source.visible_sequence_span.box.bottom,
                ).clamp(width, height)
                if not box.valid():
                    continue
                photo_widths = tuple(
                    float(right.start) - float(left.end)
                    for left, right in zip(sequence[:-1], sequence[1:])
                )
                physical_error = (
                    sum(abs(value - frame_width) for value in photo_widths)
                    / max(1.0, frame_width * len(photo_widths))
                    if photo_widths
                    else 0.0
                )
                candidates.append(
                    (
                        physical_error,
                        SequenceHypothesis(
                            visible_sequence_span=VisibleSequenceSpan(box),
                            crop_envelope=CropEnvelope(box),
                            provenance=MeasurementProvenance(
                                root_measurement=MeasurementIdentity.FRAME_DIMENSIONS,
                                source="separator_dimension_sequence",
                                dependencies=(
                                    MeasurementIdentity.SEPARATOR_PROFILE,
                                    dimensions.provenance.root_measurement,
                                ),
                                boundary_anchors=("separator_sequence",),
                            ),
                            boundary_paths=_compatible_boundary_paths(
                                source,
                                box,
                            ),
                        ),
                    )
                )
            if len(candidates) >= int(hypothesis_parameters.maximum_hypotheses):
                break
        if len(candidates) >= int(hypothesis_parameters.maximum_hypotheses):
            break
    ranked = [item for _residual, item in sorted(candidates, key=lambda item: item[0])]
    unique = unique_sequence_hypotheses(ranked)
    limit = int(hypothesis_parameters.maximum_hypotheses)
    return SequenceHypothesisSet(
        hypotheses=tuple(unique[:limit]),
        budget_exhausted=budget_exhausted or len(unique) > limit,
    )


def sequence_hypotheses(
    gray_work: np.ndarray,
    fmt: FormatPhysicalSpec,
    count: int,
    cache: MeasurementCache,
    calibration: ScanCalibrationResolution,
    layout: str,
    *,
    boundary_parameters: BoundaryPathParameters,
    content_configuration: ContentConfiguration,
    separator_configuration: SeparatorConfiguration,
    hypothesis_parameters: SequenceHypothesisParameters,
) -> SequenceHypothesisSet:
    if cache.gray_work is not gray_work and not np.shares_memory(cache.gray_work, gray_work):
        raise ValueError("sequence proposal requires the context measurement workspace")
    base = base_sequence_span_candidates(
        gray_work,
        cached_boundary_path_groups(cache, boundary_parameters),
    )
    separator_dimension = _separator_dimension_hypotheses(
        base,
        fmt,
        count,
        cache,
        calibration,
        layout,
        separator_configuration,
        hypothesis_parameters,
    )
    physical_sources = unique_sequence_hypotheses(
        [*base, *separator_dimension.hypotheses]
    )
    limit = int(hypothesis_parameters.maximum_hypotheses)
    budget_exhausted = (
        separator_dimension.budget_exhausted
        or len(physical_sources) > limit
    )
    hypotheses = expand_crop_envelopes_for_content(
        cache.content_evidence_float_work,
        physical_sources[:limit],
        content_configuration.evidence,
    )
    return SequenceHypothesisSet(tuple(hypotheses), budget_exhausted)
