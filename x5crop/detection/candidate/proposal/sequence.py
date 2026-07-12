from __future__ import annotations

from itertools import combinations

import numpy as np

from ....cache import MeasurementCache
from ....cache.separator import cached_separator_profile
from ....domain import Box, MeasurementProvenance, SequenceHypothesis
from ....formats import FormatPhysicalSpec
from ....policies.parameters.sequence import SequenceParameters
from ....policies.runtime.separator import SeparatorPolicy
from ....policies.parameters.candidate import SequenceHypothesisParameters
from ....units import ScanCalibration
from ...guidance.content_crop_envelope import expand_crop_envelopes_for_content
from ...physical.sequence import (
    base_sequence_span_candidates,
    unique_sequence_hypotheses,
)
from ...physical.photo_size import frame_dimension_prior
from ...physical.separator.observations import measure_separator_bands
from x5crop.domain import CropEnvelope, VisibleSequenceSpan


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
    separator_policy: SeparatorPolicy,
    hypothesis_parameters: SequenceHypothesisParameters,
) -> list[SequenceHypothesis]:
    if count <= 1:
        return []
    height, width = cache.gray_work.shape
    candidates: list[tuple[float, SequenceHypothesis]] = []
    for source in base:
        corridor = _measurement_corridor(source, cache)
        profile = cached_separator_profile(cache, corridor, separator_policy.profile)
        observations = measure_separator_bands(
            profile,
            corridor_start=float(corridor.left),
            parameters=separator_policy.observation,
        )
        if len(observations) < count - 1:
            continue
        observation_budget = max(
            count - 1,
            int(hypothesis_parameters.observation_budget),
        )
        strongest = tuple(
            sorted(
                sorted(
                    observations,
                    key=lambda item: (item.score, item.width),
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
            observation_score = sum(item.score for item in sequence) / len(sequence)
            rank = float(observation_score) - float(physical_error)
            candidates.append(
                (
                    rank,
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
    ranked = [item for _rank, item in sorted(candidates, key=lambda item: item[0], reverse=True)]
    return unique_sequence_hypotheses(ranked)[
        : max(0, int(hypothesis_parameters.maximum_hypotheses))
    ]


def sequence_hypotheses(
    gray_work: np.ndarray,
    fmt: FormatPhysicalSpec,
    count: int,
    cache: MeasurementCache,
    calibration: ScanCalibration,
    layout: str,
    *,
    sequence_policy: SequenceParameters,
    separator_policy: SeparatorPolicy,
    hypothesis_parameters: SequenceHypothesisParameters,
) -> list[SequenceHypothesis]:
    if cache.gray_work is not gray_work and not np.shares_memory(cache.gray_work, gray_work):
        raise ValueError("sequence proposal requires the context measurement workspace")
    base = base_sequence_span_candidates(
        gray_work,
        sequence_policy.boundary_detection,
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
    physical_sources = unique_sequence_hypotheses([*base, *separator_dimension])
    return expand_crop_envelopes_for_content(
        gray_work,
        physical_sources,
        sequence_policy.content_alignment,
    )
