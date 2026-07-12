from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor

import numpy as np

from ....domain import (
    Box,
    EvidenceState,
    MeasurementProvenance,
    PixelInterval,
    SeparatorBandObservation,
    SeparatorCrossAxisMeasurement,
)
from ....configuration.separator import SeparatorObservationParameters
from ....image.statistics import ImageMeasurementStatistics
from ....utils import runs_from_mask


@dataclass(frozen=True)
class SeparatorObservationSet:
    observations: tuple[SeparatorBandObservation, ...]
    budget_exhausted: bool


def _longest_true_run(mask: np.ndarray) -> int:
    longest = 0
    current = 0
    for value in mask.astype(bool):
        if value:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def _break_count(mask: np.ndarray) -> int:
    transitions = np.diff(mask.astype(np.int8), prepend=0, append=0)
    return int(max(0, np.count_nonzero(transitions == 1) - 1))


def _cross_axis_path_exists(mask: np.ndarray) -> bool:
    if mask.ndim != 2 or not mask.shape[0] or not mask.shape[1]:
        return False
    reachable = mask[0].astype(bool, copy=True)
    for row in mask[1:]:
        adjacent = reachable.copy()
        adjacent[1:] |= reachable[:-1]
        adjacent[:-1] |= reachable[1:]
        reachable = row.astype(bool, copy=False) & adjacent
        if not reachable.any():
            return False
    return bool(reachable.any())


def _cross_axis_measurement(
    gray_work: np.ndarray,
    corridor: Box,
    start: float,
    end: float,
    statistics: ImageMeasurementStatistics,
) -> SeparatorCrossAxisMeasurement:
    bounded = corridor.clamp(gray_work.shape[1], gray_work.shape[0])
    pixel_start = max(bounded.left, int(floor(start)))
    pixel_end = min(bounded.right, int(ceil(end)))
    if not bounded.valid() or pixel_end <= pixel_start:
        return SeparatorCrossAxisMeasurement(
            EvidenceState.UNAVAILABLE,
            None,
            None,
            None,
            None,
            "separator_band_outside_measurement_corridor",
        )
    if statistics.intensity_high <= statistics.intensity_low:
        return SeparatorCrossAxisMeasurement(
            EvidenceState.UNAVAILABLE,
            None,
            None,
            None,
            None,
            "separator_tonal_reference_unavailable",
        )
    band = gray_work[
        bounded.top : bounded.bottom,
        pixel_start:pixel_end,
    ]
    extreme = (band <= float(statistics.intensity_low)) | (
        band >= float(statistics.intensity_high)
    )
    row_support = extreme.any(axis=1)
    coverage = float(row_support.mean()) if row_support.size else 0.0
    continuity = (
        float(_longest_true_run(row_support)) / float(max(1, len(row_support)))
    )
    row_centers = tuple(
        float(positions.mean())
        for row in extreme
        if (positions := np.flatnonzero(row)).size
    )
    straightness = (
        max(
            0.0,
            1.0
            - float(np.std(row_centers))
            / max(1.0, float(pixel_end - pixel_start)),
        )
        if row_centers
        else 0.0
    )
    supported = _cross_axis_path_exists(extreme)
    return SeparatorCrossAxisMeasurement(
        EvidenceState.SUPPORTED if supported else EvidenceState.CONTRADICTED,
        coverage,
        continuity,
        _break_count(row_support),
        straightness,
        "supported" if supported else "cross_axis_continuity_weak",
    )


def _activation_threshold(
    profile: np.ndarray,
    parameters: SeparatorObservationParameters,
) -> tuple[float, float] | None:
    if not profile.size:
        return None
    minimum = float(profile.min())
    maximum = float(profile.max())
    spread = maximum - minimum
    if spread <= float(parameters.minimum_profile_range):
        return None
    threshold = float(
        np.percentile(profile, parameters.activation_percentile)
    )
    return threshold, spread


def measure_focused_separator_band(
    profile: np.ndarray,
    allowed_interval: PixelInterval,
    *,
    gray_work: np.ndarray,
    corridor: Box,
    statistics: ImageMeasurementStatistics,
    parameters: SeparatorObservationParameters,
) -> SeparatorBandObservation | None:
    if profile.ndim != 1:
        raise ValueError("separator profile must be one-dimensional")
    local_start = max(
        0,
        int(floor(float(allowed_interval.minimum) - float(corridor.left))),
    )
    local_end = min(
        int(profile.size),
        int(ceil(float(allowed_interval.maximum) - float(corridor.left))),
    )
    if local_end <= local_start:
        return None
    minimum_width = int(parameters.minimum_run_px)
    measured: list[SeparatorBandObservation] = []
    focused = profile[local_start:local_end]
    activation = _activation_threshold(profile, parameters)
    if activation is None:
        return None
    threshold, spread = activation
    for start, end in runs_from_mask(
        focused >= threshold
    ):
        if end - start < minimum_width:
            continue
        absolute_start = float(corridor.left + local_start + start)
        absolute_end = float(corridor.left + local_start + end)
        measured.append(
            SeparatorBandObservation(
                start=absolute_start,
                end=absolute_end,
                center=0.5 * (absolute_start + absolute_end),
                tonal_evidence=float(
                    max(0.0, focused[start:end].mean() - threshold) / spread
                ),
                provenance=MeasurementProvenance(
                    root_measurement="separator_profile",
                    source="focused_dimension_window",
                    dependencies=(
                        "gray_work",
                        "frame_dimensions",
                        "sequence_boundaries",
                    ),
                ),
                cross_axis=_cross_axis_measurement(
                    gray_work,
                    corridor,
                    absolute_start,
                    absolute_end,
                    statistics,
                ),
            )
        )
    return max(
        measured,
        key=lambda item: (item.tonal_evidence, item.width),
        default=None,
    )


def measure_separator_bands(
    profile: np.ndarray,
    *,
    gray_work: np.ndarray,
    corridor: Box,
    statistics: ImageMeasurementStatistics,
    parameters: SeparatorObservationParameters,
) -> SeparatorObservationSet:
    if profile.ndim != 1:
        raise ValueError("separator profile must be one-dimensional")
    activation = _activation_threshold(profile, parameters)
    if activation is None:
        return SeparatorObservationSet((), False)
    threshold, spread = activation
    minimum_width = int(parameters.minimum_run_px)
    measured: list[SeparatorBandObservation] = []
    for local_start, local_end in runs_from_mask(
        profile >= threshold
    ):
        if int(local_end) - int(local_start) < minimum_width:
            continue
        start = float(corridor.left) + float(local_start)
        end = float(corridor.left) + float(local_end)
        center = 0.5 * (start + end)
        measured.append(
            SeparatorBandObservation(
                start=start,
                end=end,
                center=center,
                tonal_evidence=float(
                    max(0.0, profile[local_start:local_end].mean() - threshold)
                    / spread
                ),
                provenance=MeasurementProvenance(
                    root_measurement="separator_profile",
                    source="observed_separator_band",
                    dependencies=("gray_work", "boundary_corridor"),
                ),
                cross_axis=_cross_axis_measurement(
                    gray_work,
                    corridor,
                    start,
                    end,
                    statistics,
                ),
            )
        )
    budget = int(parameters.maximum_observations)
    strongest = sorted(
        measured,
        key=lambda observation: (
            observation.tonal_evidence,
            observation.width,
        ),
        reverse=True,
    )[:budget]
    return SeparatorObservationSet(
        observations=tuple(
            sorted(strongest, key=lambda observation: observation.center)
        ),
        budget_exhausted=len(measured) > budget,
    )
