from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor

import numpy as np

from ....domain import (
    Box,
    GrayAppearanceObservation,
    gray_intensity_tail,
    MeasurementIdentity,
    MeasurementProvenance,
    PixelInterval,
    SeparatorBandObservation,
    SeparatorCrossAxisMeasurement,
    SeparatorCrossAxisOutcome,
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


def _cross_axis_path_exists(
    mask: np.ndarray,
    maximum_break_ratio: float,
) -> bool:
    if mask.ndim != 2 or not mask.shape[0] or not mask.shape[1]:
        return False
    maximum_break = int(round(mask.shape[0] * float(maximum_break_ratio)))
    reachable: np.ndarray | None = None
    break_length = 0
    for row in mask:
        row = row.astype(bool, copy=False)
        if reachable is None:
            if row.any():
                reachable = row.copy()
                break_length = 0
            else:
                break_length += 1
                if break_length > maximum_break:
                    return False
            continue
        adjacent = reachable.copy()
        adjacent[1:] |= reachable[:-1]
        adjacent[:-1] |= reachable[1:]
        continuation = row & adjacent
        if continuation.any():
            reachable = continuation
            break_length = 0
        elif not row.any() and break_length < maximum_break:
            reachable = adjacent
            break_length += 1
        else:
            return False
    return bool(reachable is not None and break_length <= maximum_break)


def _cross_axis_measurement(
    gray_work: np.ndarray,
    corridor: Box,
    start: float,
    end: float,
    statistics: ImageMeasurementStatistics,
    parameters: SeparatorObservationParameters,
) -> SeparatorCrossAxisMeasurement:
    bounded = corridor.clamp(gray_work.shape[1], gray_work.shape[0])
    pixel_start = max(bounded.left, int(floor(start)))
    pixel_end = min(bounded.right, int(ceil(end)))
    if not bounded.valid() or pixel_end <= pixel_start:
        return SeparatorCrossAxisMeasurement(
            SeparatorCrossAxisOutcome.BAND_OUTSIDE_CORRIDOR,
            None,
            None,
            None,
            None,
        )
    if statistics.intensity_high <= statistics.intensity_low:
        return SeparatorCrossAxisMeasurement(
            SeparatorCrossAxisOutcome.TONAL_REFERENCE_UNAVAILABLE,
            None,
            None,
            None,
            None,
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
    supported = _cross_axis_path_exists(
        extreme,
        parameters.maximum_cross_axis_break_ratio,
    )
    return SeparatorCrossAxisMeasurement(
        (
            SeparatorCrossAxisOutcome.PATH_SUPPORTED
            if supported
            else SeparatorCrossAxisOutcome.CONTINUITY_WEAK
        ),
        coverage,
        continuity,
        _break_count(row_support),
        straightness,
    )


def _band_appearance_observation(
    gray_work: np.ndarray,
    corridor: Box,
    start: float,
    end: float,
    statistics: ImageMeasurementStatistics,
    cross_axis: SeparatorCrossAxisMeasurement,
    provenance: MeasurementProvenance,
) -> GrayAppearanceObservation:
    bounded = corridor.clamp(gray_work.shape[1], gray_work.shape[0])
    pixel_start = max(bounded.left, int(floor(start)))
    pixel_end = min(bounded.right, int(ceil(end)))
    band = gray_work[
        bounded.top : bounded.bottom,
        pixel_start:pixel_end,
    ].astype(np.float32, copy=False)
    if not band.size:
        raise ValueError("separator appearance requires a non-empty measured band")
    center = float(np.median(band))
    gx = np.abs(np.diff(band, axis=1, prepend=band[:, :1]))
    gy = np.abs(np.diff(band, axis=0, prepend=band[:1, :]))
    return GrayAppearanceObservation(
        intensity_median=center,
        intensity_mad=float(np.median(np.abs(band - center))),
        texture_median=float(np.median(gx + gy)),
        gradient_median=float(np.median(np.maximum(gx, gy))),
        spatial_continuity=float(cross_axis.continuity_ratio or 0.0),
        intensity_tail=gray_intensity_tail(
            center,
            statistics.intensity_low,
            statistics.intensity_high,
        ),
        provenance=provenance,
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
        provenance = MeasurementProvenance(
            root_measurement=MeasurementIdentity.FOCUSED_SEPARATOR_PROFILE,
            source="focused_dimension_window",
            dependencies=(
                MeasurementIdentity.GRAY_WORK,
                MeasurementIdentity.FRAME_DIMENSIONS,
                MeasurementIdentity.SEQUENCE_BOUNDARIES,
            ),
        )
        cross_axis = _cross_axis_measurement(
            gray_work,
            corridor,
            absolute_start,
            absolute_end,
            statistics,
            parameters,
        )
        measured.append(
            SeparatorBandObservation(
                start=absolute_start,
                end=absolute_end,
                center=0.5 * (absolute_start + absolute_end),
                tonal_evidence=float(
                    max(0.0, focused[start:end].mean() - threshold) / spread
                ),
                appearance=_band_appearance_observation(
                    gray_work,
                    corridor,
                    absolute_start,
                    absolute_end,
                    statistics,
                    cross_axis,
                    provenance,
                ),
                provenance=provenance,
                cross_axis=cross_axis,
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
        provenance = MeasurementProvenance(
            root_measurement=MeasurementIdentity.SEPARATOR_PROFILE,
            source="observed_separator_band",
            dependencies=(
                MeasurementIdentity.GRAY_WORK,
                MeasurementIdentity.BOUNDARY_CORRIDOR,
            ),
        )
        cross_axis = _cross_axis_measurement(
            gray_work,
            corridor,
            start,
            end,
            statistics,
            parameters,
        )
        measured.append(
            SeparatorBandObservation(
                start=start,
                end=end,
                center=center,
                tonal_evidence=float(
                    max(0.0, profile[local_start:local_end].mean() - threshold)
                    / spread
                ),
                appearance=_band_appearance_observation(
                    gray_work,
                    corridor,
                    start,
                    end,
                    statistics,
                    cross_axis,
                    provenance,
                ),
                provenance=provenance,
                cross_axis=cross_axis,
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
