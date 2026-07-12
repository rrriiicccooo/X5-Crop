from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import numpy as np

from ....cache import MeasurementCache
from ....cache.separator import cached_separator_profile
from ....domain import Box, MeasurementProvenance, SequenceHypothesis
from ....formats import FormatPhysicalSpec
from ....configuration.content import ContentConfiguration
from ....configuration.boundary import BoundaryObservationParameters
from ....configuration.separator import SeparatorConfiguration
from ....configuration.candidate import SequenceHypothesisParameters
from ....units import ScanCalibration
from ...guidance.content_crop_envelope import expand_crop_envelopes_for_content
from ...physical.sequence import (
    base_sequence_span_candidates,
    unique_sequence_hypotheses,
)
from ...physical.photo_size import frame_dimension_prior
from ...physical.separator.observations import measure_separator_bands
from x5crop.domain import CropEnvelope, VisibleSequenceSpan


@dataclass(frozen=True)
class SequenceHypothesisSet:
    hypotheses: tuple[SequenceHypothesis, ...]
    budget_exhausted: bool


def _measurement_corridor(
    source: SequenceHypothesis,
    cache: MeasurementCache,
) -> Box:
    height, width = cache.gray_work.shape
    crop = source.crop_envelope.box
    corridor = Box(0, max(0, crop.top), width, min(height, crop.bottom))
    return corridor if corridor.valid() else Box(0, 0, width, height)


def _compatible_boundary_observations(
    source: SequenceHypothesis,
    box: Box,
) -> tuple:
    compatible = []
    for observation in source.boundary_observations:
        if observation.side in {"top", "bottom"}:
            compatible.append(observation)
            continue
        coordinate = float(box.left if observation.side == "leading" else box.right)
        if observation.position.minimum <= coordinate <= observation.position.maximum:
            compatible.append(observation)
    return tuple(compatible)


def _separator_dimension_hypotheses(
    base: list[SequenceHypothesis],
    fmt: FormatPhysicalSpec,
    count: int,
    cache: MeasurementCache,
    calibration: ScanCalibration,
    layout: str,
    separator_policy: SeparatorConfiguration,
    hypothesis_parameters: SequenceHypothesisParameters,
) -> SequenceHypothesisSet:
    if count <= 1:
        return SequenceHypothesisSet((), False)
    height, width = cache.gray_work.shape
    candidates: list[tuple[float, SequenceHypothesis]] = []
    budget_exhausted = False
    for source in base:
        corridor = _measurement_corridor(source, cache)
        profile = cached_separator_profile(cache, corridor, separator_policy.profile)
        observation_set = measure_separator_bands(
            profile,
            corridor_start=float(corridor.left),
            parameters=separator_policy.observation,
        )
        observations = observation_set.observations
        budget_exhausted |= observation_set.budget_exhausted
        if len(observations) < count - 1:
            continue
        observation_budget = max(
            count - 1,
            int(hypothesis_parameters.observation_budget),
        )
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
        dimensions = frame_dimension_prior(
            source.visible_sequence_span,
            fmt,
            calibration,
            layout=layout,
        )
        frame_width = dimensions.width_px.midpoint
        for sequence in combinations(strongest, count - 1):
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
                        name="separator_dimension_sequence",
                        visible_sequence_span=VisibleSequenceSpan(box),
                        crop_envelope=CropEnvelope(box),
                        strategy="separator_dimension_led",
                        provenance=MeasurementProvenance(
                            root_measurement="frame_dimensions",
                            source="separator_dimension_sequence",
                            dependencies=(
                                "separator_profile",
                                dimensions.provenance.root_measurement,
                            ),
                            boundary_anchors=("separator_sequence",),
                        ),
                        boundary_observations=_compatible_boundary_observations(
                            source,
                            box,
                        ),
                    ),
                )
            )
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
    calibration: ScanCalibration,
    layout: str,
    *,
    boundary_parameters: BoundaryObservationParameters,
    content_policy: ContentConfiguration,
    separator_policy: SeparatorConfiguration,
    hypothesis_parameters: SequenceHypothesisParameters,
) -> SequenceHypothesisSet:
    if cache.gray_work is not gray_work and not np.shares_memory(cache.gray_work, gray_work):
        raise ValueError("sequence proposal requires the context measurement workspace")
    base = base_sequence_span_candidates(
        gray_work,
        cache.image_statistics,
        boundary_parameters,
    )
    separator_dimension = _separator_dimension_hypotheses(
        base,
        fmt,
        count,
        cache,
        calibration,
        layout,
        separator_policy,
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
        content_policy.evidence,
    )
    return SequenceHypothesisSet(tuple(hypotheses), budget_exhausted)
