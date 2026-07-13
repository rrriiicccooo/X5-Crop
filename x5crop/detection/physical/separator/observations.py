from __future__ import annotations

from dataclasses import dataclass, replace
from math import ceil, floor

import numpy as np

from ....domain import (
    Box,
    GrayAppearanceObservation,
    gray_intensity_tail,
    MeasurementIdentity,
    MeasurementProvenance,
    PhotoApertureCrossAxisHypothesis,
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


@dataclass(frozen=True)
class _SeparatorBandRowMeasurements:
    corridor: Box
    band: np.ndarray
    row_appearance: np.ndarray
    row_texture: np.ndarray
    flank_references: tuple[np.ndarray, ...]


def _band_row_measurements(
    gray_work: np.ndarray,
    corridor: Box,
    start: float,
    end: float,
) -> _SeparatorBandRowMeasurements | None:
    bounded = corridor.clamp(gray_work.shape[1], gray_work.shape[0])
    pixel_start = max(bounded.left, int(floor(start)))
    pixel_end = min(bounded.right, int(ceil(end)))
    if not bounded.valid() or pixel_end <= pixel_start:
        return None
    band = gray_work[
        bounded.top : bounded.bottom,
        pixel_start:pixel_end,
    ].astype(np.float32, copy=False)
    gx = np.abs(np.diff(band, axis=1, prepend=band[:, :1]))
    gy = np.abs(np.diff(band, axis=0, prepend=band[:1, :]))
    flank_width = max(1, min(pixel_end - pixel_start, bounded.width // 2))
    flanks = (
        gray_work[
            bounded.top : bounded.bottom,
            max(bounded.left, pixel_start - flank_width) : pixel_start,
        ],
        gray_work[
            bounded.top : bounded.bottom,
            pixel_end : min(bounded.right, pixel_end + flank_width),
        ],
    )
    return _SeparatorBandRowMeasurements(
        corridor=bounded,
        band=band,
        row_appearance=np.median(band, axis=1),
        row_texture=np.median(gx + gy, axis=1),
        flank_references=tuple(
            np.median(flank.astype(np.float32, copy=False), axis=1)
            for flank in flanks
            if flank.shape[1] > 0
        ),
    )


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


def _cross_axis_support_is_continuous(
    mask: np.ndarray,
    maximum_break_rows: int,
) -> bool:
    if mask.ndim != 1:
        raise ValueError("cross-axis row support must be one-dimensional")
    if maximum_break_rows < 0:
        raise ValueError("maximum cross-axis break must be non-negative")
    supported_rows = np.flatnonzero(mask)
    if not supported_rows.size:
        return False
    internal_breaks = np.diff(supported_rows) - 1
    longest_break = max(
        int(supported_rows[0]),
        int(mask.size - 1 - supported_rows[-1]),
        int(internal_breaks.max()) if internal_breaks.size else 0,
    )
    return longest_break <= maximum_break_rows


def _cross_axis_measurement(
    row_measurements: _SeparatorBandRowMeasurements | None,
    aperture_cross_axis: PhotoApertureCrossAxisHypothesis,
    statistics: ImageMeasurementStatistics,
    parameters: SeparatorObservationParameters,
) -> SeparatorCrossAxisMeasurement:
    if row_measurements is None:
        return SeparatorCrossAxisMeasurement(
            aperture_cross_axis,
            SeparatorCrossAxisOutcome.BAND_OUTSIDE_CORRIDOR,
            None,
            None,
            None,
            None,
        )
    corridor = row_measurements.corridor
    row_start = max(
        0,
        int(ceil(aperture_cross_axis.top_path.position.maximum)) - corridor.top,
    )
    row_end = min(
        corridor.height,
        int(floor(aperture_cross_axis.bottom_path.position.minimum)) - corridor.top,
    )
    if row_end <= row_start:
        return SeparatorCrossAxisMeasurement(
            aperture_cross_axis,
            SeparatorCrossAxisOutcome.BAND_OUTSIDE_CORRIDOR,
            None,
            None,
            None,
            None,
        )
    measurement_floor = float(parameters.minimum_profile_range)
    if (
        float(statistics.gradient_quantiles[1]) <= measurement_floor
        and float(statistics.texture_quantiles[1]) <= measurement_floor
    ):
        return SeparatorCrossAxisMeasurement(
            aperture_cross_axis,
            SeparatorCrossAxisOutcome.APPEARANCE_REFERENCE_UNAVAILABLE,
            None,
            None,
            None,
            None,
        )
    row_appearance = row_measurements.row_appearance[row_start:row_end]
    appearance_center = float(np.median(row_appearance))
    appearance_scale = max(
        measurement_floor,
        float(statistics.gradient_quantiles[0]),
        float(statistics.gradient_mad),
        float(statistics.texture_mad),
    )
    appearance_coherent = (
        np.abs(row_appearance - appearance_center) <= appearance_scale
    )
    row_texture = row_measurements.row_texture[row_start:row_end]
    texture_supported = row_texture <= max(
        measurement_floor,
        float(statistics.texture_quantiles[1]),
    )
    flank_references = tuple(
        reference[row_start:row_end]
        for reference in row_measurements.flank_references
    )
    contrast_supported = (
        np.maximum.reduce(
            tuple(np.abs(row_appearance - reference) for reference in flank_references)
        )
        >= max(measurement_floor, float(statistics.gradient_quantiles[1]))
        if flank_references
        else np.zeros_like(appearance_coherent, dtype=bool)
    )
    row_support = appearance_coherent & (texture_supported | contrast_supported)
    coverage = float(row_support.mean()) if row_support.size else 0.0
    longest_supported = (
        float(_longest_true_run(row_support)) / float(max(1, len(row_support)))
    )
    maximum_break_rows = int(
        round(row_support.size * parameters.maximum_cross_axis_break_ratio)
    )
    supported = _cross_axis_support_is_continuous(
        row_support,
        maximum_break_rows,
    )
    return SeparatorCrossAxisMeasurement(
        aperture_cross_axis,
        (
            SeparatorCrossAxisOutcome.PATH_SUPPORTED
            if supported
            else SeparatorCrossAxisOutcome.CONTINUITY_WEAK
        ),
        coverage,
        longest_supported,
        _break_count(row_support),
        float(appearance_coherent.mean()) if appearance_coherent.size else 0.0,
    )


def _band_appearance_observation(
    row_measurements: _SeparatorBandRowMeasurements | None,
    statistics: ImageMeasurementStatistics,
    cross_axis_measurements: tuple[SeparatorCrossAxisMeasurement, ...],
    provenance: MeasurementProvenance,
) -> GrayAppearanceObservation:
    if row_measurements is None or not row_measurements.band.size:
        raise ValueError("separator appearance requires a non-empty measured band")
    band = row_measurements.band
    center = float(np.median(band))
    gx = np.abs(np.diff(band, axis=1, prepend=band[:, :1]))
    gy = np.abs(np.diff(band, axis=0, prepend=band[:1, :]))
    return GrayAppearanceObservation(
        intensity_median=center,
        intensity_mad=float(np.median(np.abs(band - center))),
        texture_median=float(np.median(gx + gy)),
        gradient_median=float(np.median(np.maximum(gx, gy))),
        spatial_continuity=max(
            (
                float(item.longest_supported_ratio or 0.0)
                for item in cross_axis_measurements
            ),
            default=0.0,
        ),
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


def propose_separator_bands(
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
        provenance = MeasurementProvenance(
            root_measurement=MeasurementIdentity.SEPARATOR_PROFILE,
            source="observed_separator_band",
            dependencies=(
                MeasurementIdentity.GRAY_WORK,
                MeasurementIdentity.BOUNDARY_CORRIDOR,
            ),
        )
        row_measurements = _band_row_measurements(
            gray_work,
            corridor,
            start,
            end,
        )
        measured.append(
            SeparatorBandObservation(
                start=start,
                end=end,
                tonal_evidence=float(
                    max(0.0, profile[local_start:local_end].mean() - threshold)
                    / spread
                ),
                appearance=_band_appearance_observation(
                    row_measurements,
                    statistics,
                    (),
                    provenance,
                ),
                provenance=provenance,
                cross_axis_measurements=(),
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
            sorted(strongest, key=lambda observation: observation.midpoint)
        ),
        budget_exhausted=len(measured) > budget,
    )


def measure_separator_cross_axis_support(
    proposed: SeparatorObservationSet,
    *,
    gray_work: np.ndarray,
    corridor: Box,
    statistics: ImageMeasurementStatistics,
    parameters: SeparatorObservationParameters,
    cross_axis_hypotheses: tuple[PhotoApertureCrossAxisHypothesis, ...],
) -> SeparatorObservationSet:
    if not cross_axis_hypotheses:
        raise ValueError("separator cross-axis measurement requires hypotheses")
    measured: list[SeparatorBandObservation] = []
    for observation in proposed.observations:
        row_measurements = _band_row_measurements(
            gray_work,
            corridor,
            observation.start,
            observation.end,
        )
        cross_axis_measurements = tuple(
            _cross_axis_measurement(
                row_measurements,
                hypothesis,
                statistics,
                parameters,
            )
            for hypothesis in cross_axis_hypotheses
        )
        measured.append(
            replace(
                observation,
                appearance=_band_appearance_observation(
                    row_measurements,
                    statistics,
                    cross_axis_measurements,
                    observation.provenance,
                ),
                cross_axis_measurements=cross_axis_measurements,
            )
        )
    return SeparatorObservationSet(tuple(measured), proposed.budget_exhausted)
