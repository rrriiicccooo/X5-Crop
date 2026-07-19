from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor

import numpy as np

from ....domain import (
    Box,
    CrossAxisPathMeasurement,
    CrossAxisPathOutcome,
    EvidenceState,
    GrayAppearanceObservation,
    gray_intensity_tail,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
    SeparatorBandCrossAxisSupport,
    SeparatorBandObservation,
    SeparatorCrossAxisMeasurement,
)
from ....configuration.separator import SeparatorObservationParameters
from ....image.statistics import ImageMeasurementStatistics
from ....image.separator_profile import SeparatorProfileMeasurement
from ....utils import runs_from_mask
from ..model import SharedShortAxisSafetySpan


SEPARATOR_EDGE_COUNT = 2
MINIMUM_BAND_EDGE_SEPARATION_PX = 2
@dataclass(frozen=True)
class SeparatorObservationSet:
    observations: tuple[SeparatorBandObservation, ...]


@dataclass(frozen=True)
class SeparatorSupportSet:
    canonical_supports: tuple[SeparatorBandCrossAxisSupport, ...]
    budget_exhausted: bool


@dataclass(frozen=True)
class _SeparatorBandRowMeasurements:
    corridor: Box
    band: np.ndarray
    row_appearance: np.ndarray
    row_texture: np.ndarray
    leading_flank_appearance: np.ndarray | None
    trailing_flank_appearance: np.ndarray | None
    leading_flank_texture: np.ndarray | None
    trailing_flank_texture: np.ndarray | None


@dataclass(frozen=True)
class _SeparatorEdgeProfiles:
    corridor: Box
    profiles: tuple[np.ndarray, ...]
    gradients: tuple[np.ndarray, ...]


@dataclass(frozen=True)
class _SeparatorBoundaryRowSupport:
    leading: np.ndarray
    trailing: np.ndarray


def _span_contains(outer: PixelInterval, inner: PixelInterval) -> bool:
    return bool(
        outer.minimum <= inner.minimum
        and outer.maximum >= inner.maximum
    )


def _same_separator_location(
    left: SeparatorBandCrossAxisSupport,
    right: SeparatorBandCrossAxisSupport,
) -> bool:
    left_span = left.observation.span
    right_span = right.observation.span
    return _span_contains(left_span, right_span) or _span_contains(
        right_span,
        left_span,
    )


def _support_rank(
    support: SeparatorBandCrossAxisSupport,
) -> tuple[int, int, int, float, float, float, float, float, ObservationId]:
    measurement = support.measurement
    paths = (
        measurement.leading_edge_path,
        measurement.trailing_edge_path,
        measurement.band_path,
    )
    return (
        int(measurement.complete_separator_supported),
        measurement.supported_edge_count,
        int(measurement.band_path.state == EvidenceState.SUPPORTED),
        max(float(path.longest_supported_ratio or 0.0) for path in paths),
        max(float(path.coverage_ratio or 0.0) for path in paths),
        float(measurement.appearance_coherence_ratio or 0.0),
        support.observation.width_px.midpoint,
        support.observation.tonal_evidence,
        support.observation.provenance.observation_id,
    )


def canonical_separator_supports(
    supports: tuple[SeparatorBandCrossAxisSupport, ...],
) -> tuple[SeparatorBandCrossAxisSupport, ...]:
    groups: list[list[SeparatorBandCrossAxisSupport]] = []
    for support in dict.fromkeys(supports):
        matching = [
            index
            for index, group in enumerate(groups)
            if any(_same_separator_location(support, item) for item in group)
        ]
        if not matching:
            groups.append([support])
            continue
        target = matching[0]
        groups[target].append(support)
        for index in reversed(matching[1:]):
            groups[target].extend(groups.pop(index))
    representatives = tuple(max(group, key=_support_rank) for group in groups)
    return tuple(
        sorted(
            representatives,
            key=lambda support: (
                support.observation.leading_edge.midpoint,
                support.observation.trailing_edge.midpoint,
                support.observation.provenance.observation_id,
            ),
        )
    )


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
    leading_flank = gray_work[
        bounded.top : bounded.bottom,
        max(bounded.left, pixel_start - flank_width) : pixel_start,
    ].astype(np.float32, copy=False)
    trailing_flank = gray_work[
        bounded.top : bounded.bottom,
        pixel_end : min(bounded.right, pixel_end + flank_width),
    ].astype(np.float32, copy=False)

    def row_median(values: np.ndarray) -> np.ndarray | None:
        return (
            np.median(values, axis=1)
            if values.shape[1] > 0
            else None
        )

    def row_texture(values: np.ndarray) -> np.ndarray | None:
        if values.shape[1] <= 0:
            return None
        flank_gx = np.abs(np.diff(values, axis=1, prepend=values[:, :1]))
        flank_gy = np.abs(np.diff(values, axis=0, prepend=values[:1, :]))
        return np.median(flank_gx + flank_gy, axis=1)

    return _SeparatorBandRowMeasurements(
        corridor=bounded,
        band=band,
        row_appearance=np.median(band, axis=1),
        row_texture=np.median(gx + gy, axis=1),
        leading_flank_appearance=row_median(leading_flank),
        trailing_flank_appearance=row_median(trailing_flank),
        leading_flank_texture=row_texture(leading_flank),
        trailing_flank_texture=row_texture(trailing_flank),
    )


def _edge_gradient_by_row(
    gray_work: np.ndarray,
    corridor: Box,
    edge: PixelInterval,
) -> np.ndarray | None:
    bounded = corridor.clamp(gray_work.shape[1], gray_work.shape[0])
    start = max(bounded.left + 1, int(floor(edge.minimum)))
    end = min(bounded.right, int(ceil(edge.maximum)) + 1)
    if not bounded.valid() or end <= start:
        return None
    edge_pixels = gray_work[
        bounded.top : bounded.bottom,
        start - 1 : end,
    ].astype(np.float32, copy=False)
    gradients = np.abs(np.diff(edge_pixels, axis=1))
    if not gradients.shape[1]:
        return None
    return np.max(gradients, axis=1)


def _separator_boundary_row_support(
    gray_work: np.ndarray,
    corridor: Box,
    observation: SeparatorBandObservation,
    statistics: ImageMeasurementStatistics,
    parameters: SeparatorObservationParameters,
) -> _SeparatorBoundaryRowSupport | None:
    leading = _edge_gradient_by_row(
        gray_work,
        corridor,
        observation.leading_edge,
    )
    trailing = _edge_gradient_by_row(
        gray_work,
        corridor,
        observation.trailing_edge,
    )
    if leading is None or trailing is None or leading.shape != trailing.shape:
        return None
    minimum_gradient = max(
        float(parameters.minimum_profile_range),
        float(statistics.gradient_signal),
    )
    return _SeparatorBoundaryRowSupport(
        leading=leading >= minimum_gradient,
        trailing=trailing >= minimum_gradient,
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
    minimum_supported_rows: int,
) -> bool:
    if mask.ndim != 1:
        raise ValueError("cross-axis row support must be one-dimensional")
    if maximum_break_rows < 0:
        raise ValueError("maximum cross-axis break must be non-negative")
    if minimum_supported_rows <= 0:
        raise ValueError("minimum cross-axis support must be positive")
    supported_rows = np.flatnonzero(mask)
    if supported_rows.size < minimum_supported_rows:
        return False
    component_support = 1
    for internal_break in np.diff(supported_rows) - 1:
        component_support = (
            1
            if int(internal_break) > maximum_break_rows
            else component_support + 1
        )
        if component_support >= minimum_supported_rows:
            return True
    return component_support >= minimum_supported_rows


def _unavailable_cross_axis_path(
    outcome: CrossAxisPathOutcome,
) -> CrossAxisPathMeasurement:
    if outcome not in {
        CrossAxisPathOutcome.BAND_OUTSIDE_CORRIDOR,
        CrossAxisPathOutcome.APPEARANCE_REFERENCE_UNAVAILABLE,
    }:
        raise ValueError("unavailable cross-axis path requires an unavailable outcome")
    return CrossAxisPathMeasurement(outcome, None, None, None)


def _measured_cross_axis_path(
    support: np.ndarray,
    maximum_break_rows: int,
    minimum_supported_rows: int,
    *,
    continuity_support: np.ndarray | None = None,
) -> CrossAxisPathMeasurement:
    coverage = float(support.mean()) if support.size else 0.0
    longest_supported = float(_longest_true_run(support)) / float(
        max(1, len(support))
    )
    supported = bool(
        np.count_nonzero(support) >= minimum_supported_rows
        and _cross_axis_support_is_continuous(
            support if continuity_support is None else continuity_support,
            maximum_break_rows,
            minimum_supported_rows,
        )
    )
    return CrossAxisPathMeasurement(
        (
            CrossAxisPathOutcome.PATH_SUPPORTED
            if supported
            else CrossAxisPathOutcome.CONTINUITY_WEAK
        ),
        coverage,
        longest_supported,
        _break_count(support),
    )


def _cross_axis_measurement(
    observation_id: ObservationId,
    row_measurements: _SeparatorBandRowMeasurements | None,
    boundary_row_support: _SeparatorBoundaryRowSupport | None,
    shared_short_axis: SharedShortAxisSafetySpan,
    statistics: ImageMeasurementStatistics,
    parameters: SeparatorObservationParameters,
) -> SeparatorCrossAxisMeasurement:
    if row_measurements is None or boundary_row_support is None:
        unavailable = _unavailable_cross_axis_path(
            CrossAxisPathOutcome.BAND_OUTSIDE_CORRIDOR
        )
        return SeparatorCrossAxisMeasurement(
            observation_id,
            shared_short_axis.measurement_span,
            unavailable,
            unavailable,
            unavailable,
            None,
        )
    corridor = row_measurements.corridor
    row_start = max(
        0,
        int(ceil(shared_short_axis.top.maximum)) - corridor.top,
    )
    row_end = min(
        corridor.height,
        int(floor(shared_short_axis.bottom.minimum)) - corridor.top,
    )
    if row_end <= row_start:
        unavailable = _unavailable_cross_axis_path(
            CrossAxisPathOutcome.BAND_OUTSIDE_CORRIDOR
        )
        return SeparatorCrossAxisMeasurement(
            observation_id,
            shared_short_axis.measurement_span,
            unavailable,
            unavailable,
            unavailable,
            None,
        )
    measurement_floor = float(parameters.minimum_profile_range)
    if (
        float(statistics.gradient_signal) <= measurement_floor
        and float(statistics.texture_signal) <= measurement_floor
    ):
        unavailable = _unavailable_cross_axis_path(
            CrossAxisPathOutcome.APPEARANCE_REFERENCE_UNAVAILABLE
        )
        return SeparatorCrossAxisMeasurement(
            observation_id,
            shared_short_axis.measurement_span,
            unavailable,
            unavailable,
            unavailable,
            None,
        )
    row_appearance = row_measurements.row_appearance[row_start:row_end]
    appearance_center = float(np.median(row_appearance))
    appearance_scale = max(
        measurement_floor,
        float(statistics.gradient_baseline),
        float(statistics.gradient_mad),
        float(statistics.texture_mad),
    )
    appearance_coherent = (
        np.abs(row_appearance - appearance_center) <= appearance_scale
    )
    local_contrast_floor = max(
        measurement_floor,
        float(statistics.gradient_baseline),
        float(statistics.gradient_mad),
    )
    local_texture_floor = max(
        measurement_floor,
        float(statistics.texture_mad),
    )
    band_texture = row_measurements.row_texture[row_start:row_end]

    def flank_contrast_support(
        flank: np.ndarray | None,
    ) -> np.ndarray:
        return (
            np.abs(row_appearance - flank[row_start:row_end])
            >= local_contrast_floor
            if flank is not None
            else np.zeros_like(appearance_coherent, dtype=bool)
        )

    def flank_texture_support(
        flank: np.ndarray | None,
    ) -> np.ndarray:
        return (
            flank[row_start:row_end] - band_texture >= local_texture_floor
            if flank is not None
            else np.zeros_like(appearance_coherent, dtype=bool)
        )

    leading_local_support = flank_contrast_support(
        row_measurements.leading_flank_appearance
    ) | flank_texture_support(row_measurements.leading_flank_texture)
    trailing_local_support = flank_contrast_support(
        row_measurements.trailing_flank_appearance
    ) | flank_texture_support(row_measurements.trailing_flank_texture)
    leading_local_support &= appearance_coherent
    trailing_local_support &= appearance_coherent
    leading_support = (
        boundary_row_support.leading[row_start:row_end]
        | leading_local_support
    )
    trailing_support = (
        boundary_row_support.trailing[row_start:row_end]
        | trailing_local_support
    )
    row_support = leading_support | trailing_support | appearance_coherent
    maximum_break_rows = int(
        round(row_support.size * parameters.maximum_cross_axis_break_ratio)
    )
    minimum_supported_rows = max(
        1,
        int(
            ceil(
                row_support.size
                * parameters.minimum_cross_axis_supported_ratio
            )
        ),
    )
    return SeparatorCrossAxisMeasurement(
        observation_id,
        shared_short_axis.measurement_span,
        _measured_cross_axis_path(
            leading_support,
            maximum_break_rows,
            minimum_supported_rows,
            continuity_support=row_support,
        ),
        _measured_cross_axis_path(
            trailing_support,
            maximum_break_rows,
            minimum_supported_rows,
            continuity_support=row_support,
        ),
        _measured_cross_axis_path(
            row_support,
            maximum_break_rows,
            minimum_supported_rows,
        ),
        float(appearance_coherent.mean()) if appearance_coherent.size else 0.0,
    )


def _band_appearance_observation(
    row_measurements: _SeparatorBandRowMeasurements | None,
    statistics: ImageMeasurementStatistics,
    parameters: SeparatorObservationParameters,
    provenance: MeasurementProvenance,
) -> GrayAppearanceObservation:
    if row_measurements is None or not row_measurements.band.size:
        raise ValueError("separator appearance requires a non-empty measured band")
    band = row_measurements.band
    center = float(np.median(band))
    gx = np.abs(np.diff(band, axis=1, prepend=band[:, :1]))
    gy = np.abs(np.diff(band, axis=0, prepend=band[:1, :]))
    row_appearance = row_measurements.row_appearance
    appearance_scale = max(
        float(parameters.minimum_profile_range),
        float(statistics.gradient_baseline),
        float(statistics.gradient_mad),
        float(statistics.texture_mad),
    )
    coherent_rows = np.abs(row_appearance - center) <= appearance_scale
    return GrayAppearanceObservation(
        intensity_median=center,
        intensity_mad=float(np.median(np.abs(band - center))),
        texture_median=float(np.median(gx + gy)),
        gradient_median=float(np.median(np.maximum(gx, gy))),
        spatial_continuity=(
            float(_longest_true_run(coherent_rows))
            / float(max(1, coherent_rows.size))
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
    *,
    percentile: float,
    minimum_profile_range: float,
) -> tuple[float, float] | None:
    if not profile.size:
        return None
    minimum = float(profile.min())
    maximum = float(profile.max())
    spread = maximum - minimum
    if spread <= float(minimum_profile_range):
        return None
    threshold = float(np.percentile(profile, percentile))
    if threshold <= minimum:
        threshold = float(
            np.nextafter(
                np.asarray(minimum, dtype=profile.dtype),
                np.asarray(maximum, dtype=profile.dtype),
            )
        )
    return threshold, spread


def _local_profile_baseline(
    profile: np.ndarray,
    window: int,
) -> np.ndarray:
    bounded_window = max(1, min(int(window), int(profile.size)))
    if bounded_window <= 1:
        return profile.astype(np.float32, copy=False)
    leading = (bounded_window - 1) // SEPARATOR_EDGE_COUNT
    trailing = bounded_window - 1 - leading
    padded = np.pad(
        profile.astype(np.float32, copy=False),
        (leading, trailing),
        mode="edge",
    )
    kernel = np.ones(bounded_window, dtype=np.float32) / float(bounded_window)
    return np.convolve(padded, kernel, mode="valid")


def _activation_strength(
    profile: np.ndarray,
    activation: tuple[float, float] | None,
) -> np.ndarray:
    if activation is None:
        return np.zeros(profile.shape, dtype=np.float32)
    _threshold, spread = activation
    minimum = float(profile.min())
    return np.clip(
        (profile.astype(np.float32, copy=False) - minimum) / float(spread),
        0.0,
        1.0,
    )


@dataclass(frozen=True)
class _ProfileActivation:
    mask: np.ndarray
    strength: np.ndarray


def _profile_activation(
    profile: np.ndarray,
    parameters: SeparatorObservationParameters,
    baseline_window: int,
) -> _ProfileActivation:
    global_activation = _activation_threshold(
        profile,
        percentile=parameters.activation_percentile,
        minimum_profile_range=parameters.minimum_profile_range,
    )
    local_prominence = np.maximum(
        profile.astype(np.float32, copy=False)
        - _local_profile_baseline(profile, baseline_window),
        0.0,
    )
    local_activation = _activation_threshold(
        local_prominence,
        percentile=parameters.prominence_activation_percentile,
        minimum_profile_range=parameters.minimum_profile_range,
    )
    global_threshold = (
        global_activation[0]
        if global_activation is not None
        else float("inf")
    )
    local_threshold = (
        local_activation[0]
        if local_activation is not None
        else float("inf")
    )
    return _ProfileActivation(
        mask=(profile >= global_threshold) | (
            local_prominence >= local_threshold
        ),
        strength=np.maximum(
            _activation_strength(profile, global_activation),
            _activation_strength(local_prominence, local_activation),
        ),
    )


def _raw_activation_edge_interval(
    active_mask: np.ndarray,
    nominal_position: float,
    search_radius_px: int,
    profile_origin_px: int,
    *,
    leading: bool,
) -> PixelInterval | None:
    if active_mask.ndim != 1 or active_mask.size < SEPARATOR_EDGE_COUNT:
        return None
    transitions = (
        (~active_mask[:-1] & active_mask[1:])
        if leading
        else (active_mask[:-1] & ~active_mask[1:])
    )
    coordinates = np.flatnonzero(transitions) + 1
    candidates = tuple(
        int(coordinate)
        for coordinate in coordinates
        if abs(float(coordinate) - nominal_position) <= search_radius_px
    )
    if not candidates:
        return None
    coordinate = min(
        candidates,
        key=lambda value: (abs(float(value) - nominal_position), value),
    )
    return PixelInterval(
        float(profile_origin_px + coordinate - 1),
        float(profile_origin_px + coordinate),
    )


def _measurement_envelope(
    primary: PixelInterval,
    corroborating: PixelInterval | None,
) -> PixelInterval:
    if corroborating is None:
        return primary
    return PixelInterval(
        min(primary.minimum, corroborating.minimum),
        max(primary.maximum, corroborating.maximum),
    )


def _canonical_activation_runs(
    runs: tuple[tuple[int, int], ...],
    activation_strength: np.ndarray,
    neighborhood_px: int,
) -> tuple[tuple[int, int], ...]:
    remaining = list(runs)
    canonical: list[tuple[int, int]] = []
    while remaining:
        representative = max(
            remaining,
            key=lambda run: (
                float(activation_strength[run[0] : run[1]].mean()),
                run[1] - run[0],
                -run[0],
            ),
        )
        representative_midpoint = sum(representative) / SEPARATOR_EDGE_COUNT
        local_feature = tuple(
            run
            for run in remaining
            if abs(
                sum(run) / SEPARATOR_EDGE_COUNT - representative_midpoint
            )
            <= neighborhood_px
        )
        canonical.append(representative)
        grouped = set(local_feature)
        remaining = [run for run in remaining if run not in grouped]
    return tuple(sorted(canonical))


def _robust_edge_interval(
    positions: list[PixelInterval],
    cross_section_count: int,
    parameters: SeparatorObservationParameters,
) -> PixelInterval | None:
    minimum_support = max(
        1,
        int(
            ceil(
                cross_section_count
                * parameters.minimum_cross_axis_supported_ratio
            )
        ),
    )
    if len(positions) < minimum_support:
        return None
    return PixelInterval(
        float(
            np.percentile(
                [item.minimum for item in positions],
                parameters.edge_position_lower_percentile,
            )
        ),
        float(
            np.percentile(
                [item.maximum for item in positions],
                parameters.edge_position_upper_percentile,
            )
        ),
    )


def _separator_edge_profiles(
    gray_work: np.ndarray,
    corridor: Box,
    parameters: SeparatorObservationParameters,
) -> _SeparatorEdgeProfiles | None:
    bounded = corridor.clamp(gray_work.shape[1], gray_work.shape[0])
    if not bounded.valid():
        return None
    section_count = min(
        bounded.height,
        int(parameters.edge_measurement_cross_sections),
    )
    if section_count <= 0:
        return None
    section_edges = np.linspace(bounded.top, bounded.bottom, section_count + 1)
    profiles: list[np.ndarray] = []
    gradients: list[np.ndarray] = []
    for lower, upper in zip(section_edges[:-1], section_edges[1:], strict=True):
        row_start = max(bounded.top, min(bounded.bottom - 1, int(round(lower))))
        row_end = max(row_start + 1, min(bounded.bottom, int(round(upper))))
        profile = np.median(
            gray_work[row_start:row_end, bounded.left : bounded.right],
            axis=0,
        ).astype(np.float32)
        profiles.append(profile)
        gradients.append(np.abs(np.diff(profile, prepend=profile[:1])))
    return _SeparatorEdgeProfiles(
        corridor=bounded,
        profiles=tuple(profiles),
        gradients=tuple(gradients),
    )


def _cross_section_band_edge_intervals(
    edge_profiles: _SeparatorEdgeProfiles | None,
    start: float,
    end: float,
    search_radius_px: int,
    statistics: ImageMeasurementStatistics,
    parameters: SeparatorObservationParameters,
) -> tuple[PixelInterval | None, PixelInterval | None]:
    if edge_profiles is None:
        return None, None
    bounded = edge_profiles.corridor
    leading_positions: list[PixelInterval] = []
    trailing_positions: list[PixelInterval] = []
    minimum_gradient = max(
        float(parameters.minimum_profile_range),
        float(statistics.gradient_signal),
    )
    nominal_band_start = max(bounded.left, int(floor(start)))
    nominal_band_end = min(bounded.right, int(ceil(end)))
    band_width = nominal_band_end - nominal_band_start
    if band_width <= 0:
        return None, None

    def strongest_edge(
        gradient: np.ndarray,
        nominal_position: float,
    ) -> PixelInterval | None:
        search_start = max(
            bounded.left + 1,
            int(floor(nominal_position)) - int(search_radius_px),
        )
        search_end = min(
            bounded.right,
            int(ceil(nominal_position)) + int(search_radius_px) + 1,
        )
        if search_end <= search_start:
            return None
        local_start = search_start - bounded.left
        local_end = search_end - bounded.left
        local_gradient = gradient[local_start:local_end]
        if not local_gradient.size:
            return None
        supported_indexes = np.flatnonzero(local_gradient >= minimum_gradient)
        if not supported_indexes.size:
            return None
        coordinate = min(
            (search_start + int(index) for index in supported_indexes),
            key=lambda value: (
                abs(float(value) - nominal_position),
                -float(local_gradient[value - search_start]),
            ),
        )
        return PixelInterval(float(coordinate - 1), float(coordinate))

    for profile, gradient in zip(
        edge_profiles.profiles,
        edge_profiles.gradients,
        strict=True,
    ):
        local_band_start = nominal_band_start - bounded.left
        local_band_end = nominal_band_end - bounded.left
        inside = profile[local_band_start:local_band_end]
        leading_flank = profile[
            max(0, local_band_start - band_width) : local_band_start
        ]
        trailing_flank = profile[
            local_band_end : min(profile.size, local_band_end + band_width)
        ]
        if not inside.size or not leading_flank.size or not trailing_flank.size:
            continue
        inside_center = float(np.median(inside))
        if (
            abs(inside_center - float(np.median(leading_flank)))
            >= minimum_gradient
            and (leading := strongest_edge(gradient, start)) is not None
        ):
            leading_positions.append(leading)
        if (
            abs(inside_center - float(np.median(trailing_flank)))
            >= minimum_gradient
            and (trailing := strongest_edge(gradient, end)) is not None
        ):
            trailing_positions.append(trailing)
    return (
        _robust_edge_interval(
            leading_positions,
            len(edge_profiles.profiles),
            parameters,
        ),
        _robust_edge_interval(
            trailing_positions,
            len(edge_profiles.profiles),
            parameters,
        ),
    )


def propose_separator_bands(
    profile_measurement: SeparatorProfileMeasurement,
    *,
    gray_work: np.ndarray,
    corridor: Box,
    statistics: ImageMeasurementStatistics,
    parameters: SeparatorObservationParameters,
    transform_position_uncertainty_px: float,
) -> SeparatorObservationSet:
    profile = profile_measurement.smoothed_score
    if profile.ndim != 1:
        raise ValueError("separator profile must be one-dimensional")
    if (
        not np.isfinite(transform_position_uncertainty_px)
        or transform_position_uncertainty_px < 0.0
    ):
        raise ValueError("transform position uncertainty must be finite")
    baseline_window = int(profile_measurement.local_baseline_window_px)
    profile_activation = _profile_activation(
        profile,
        parameters,
        baseline_window,
    )
    raw_activation = _profile_activation(
        profile_measurement.raw_score,
        parameters,
        baseline_window,
    )
    if not np.any(profile_activation.mask):
        return SeparatorObservationSet(())
    minimum_width = max(
        int(parameters.minimum_run_px),
        MINIMUM_BAND_EDGE_SEPARATION_PX,
    )
    measured_runs = tuple(
        (int(local_start), int(local_end))
        for local_start, local_end in runs_from_mask(profile_activation.mask)
        if int(local_end) - int(local_start) >= minimum_width
    )
    active_runs = _canonical_activation_runs(
        measured_runs,
        profile_activation.strength,
        max(minimum_width, baseline_window // SEPARATOR_EDGE_COUNT),
    )
    if not active_runs:
        return SeparatorObservationSet(())
    edge_profiles = _separator_edge_profiles(gray_work, corridor, parameters)
    measured: list[SeparatorBandObservation] = []
    for local_start, local_end in active_runs:
        start = float(corridor.left) + float(local_start)
        end = float(corridor.left) + float(local_end)
        profile_uncertainty_radius = max(
            0,
            (
                int(profile_measurement.smoothing_window_px) - 1
            )
            // SEPARATOR_EDGE_COUNT,
        )
        cross_section_search_radius = max(
            int(profile_measurement.smoothing_window_px),
            int(ceil((end - start) / 2.0)),
        )
        cross_section_leading, cross_section_trailing = (
            _cross_section_band_edge_intervals(
                edge_profiles,
                start,
                end,
                cross_section_search_radius,
                statistics,
                parameters,
            )
        )
        raw_leading = _raw_activation_edge_interval(
            raw_activation.mask,
            float(local_start),
            int(profile_measurement.smoothing_window_px),
            corridor.left,
            leading=True,
        )
        raw_trailing = _raw_activation_edge_interval(
            raw_activation.mask,
            float(local_end),
            int(profile_measurement.smoothing_window_px),
            corridor.left,
            leading=False,
        )
        profile_leading_edge = PixelInterval(
            max(
                float(corridor.left),
                start - 1.0 - float(profile_uncertainty_radius),
            ),
            start + float(profile_uncertainty_radius),
        )
        profile_trailing_edge = PixelInterval(
            end - 1.0 - float(profile_uncertainty_radius),
            min(
                float(corridor.right),
                end + float(profile_uncertainty_radius),
            ),
        )
        leading_edge = (
            cross_section_leading
            if cross_section_leading is not None
            else _measurement_envelope(profile_leading_edge, raw_leading)
        ).expanded(transform_position_uncertainty_px).intersection(
            PixelInterval(float(corridor.left), float(corridor.right))
        )
        trailing_edge = (
            cross_section_trailing
            if cross_section_trailing is not None
            else _measurement_envelope(profile_trailing_edge, raw_trailing)
        ).expanded(transform_position_uncertainty_px).intersection(
            PixelInterval(float(corridor.left), float(corridor.right))
        )
        if (
            leading_edge is None
            or trailing_edge is None
            or trailing_edge.midpoint <= leading_edge.midpoint
        ):
            continue
        provenance = MeasurementProvenance(
            root_measurement=MeasurementIdentity.SEPARATOR_PROFILE,
            observation_id=ObservationId(
                f"separator_band:{start:.6f}:{end:.6f}"
            ),
            dependencies=(
                MeasurementIdentity.GRAY_WORK,
                MeasurementIdentity.BOUNDARY_CORRIDOR,
                *(
                    (MeasurementIdentity.WORKSPACE_TRANSFORM,)
                    if transform_position_uncertainty_px > 0.0
                    else ()
                ),
            ),
            description="observed separator band",
        )
        row_measurements = _band_row_measurements(
            gray_work,
            corridor,
            start,
            end,
        )
        measured.append(
            SeparatorBandObservation(
                leading_edge=leading_edge,
                trailing_edge=trailing_edge,
                tonal_evidence=float(
                    profile_activation.strength[local_start:local_end].mean()
                ),
                appearance=_band_appearance_observation(
                    row_measurements,
                    statistics,
                    parameters,
                    provenance,
                ),
                provenance=provenance,
            )
        )
    return SeparatorObservationSet(
        observations=tuple(
            sorted(
                measured,
                key=lambda observation: observation.leading_edge.midpoint,
            )
        ),
    )


def measure_separator_cross_axis_support(
    proposed: SeparatorObservationSet,
    *,
    gray_work: np.ndarray,
    corridor: Box,
    statistics: ImageMeasurementStatistics,
    parameters: SeparatorObservationParameters,
    shared_short_axis: SharedShortAxisSafetySpan,
) -> SeparatorSupportSet:
    measured: list[SeparatorBandCrossAxisSupport] = []
    for observation in proposed.observations:
        row_measurements = _band_row_measurements(
            gray_work,
            corridor,
            observation.span.minimum,
            observation.span.maximum,
        )
        cross_axis_measurement = _cross_axis_measurement(
            observation.provenance.observation_id,
            row_measurements,
            _separator_boundary_row_support(
                gray_work,
                corridor,
                observation,
                statistics,
                parameters,
            ),
            shared_short_axis,
            statistics,
            parameters,
        )
        measured.append(
            SeparatorBandCrossAxisSupport(
                observation=observation,
                measurement=cross_axis_measurement,
            )
        )
    viable = tuple(
        support
        for support in canonical_separator_supports(tuple(measured))
        if not support.measurement.all_paths_contradicted
    )
    budget = int(parameters.maximum_observations)
    ranked = tuple(sorted(viable, key=_support_rank, reverse=True))
    strongest = ranked[:budget]
    retained_ids = {
        support.observation.provenance.observation_id for support in strongest
    }
    omitted_measured_edge = any(
        support.measurement.supported_edge_count > 0
        and support.observation.provenance.observation_id not in retained_ids
        for support in viable
    )
    return SeparatorSupportSet(
        tuple(
            sorted(
                strongest,
                key=lambda support: (
                    support.observation.leading_edge.midpoint,
                    support.observation.trailing_edge.midpoint,
                    support.observation.provenance.observation_id,
                ),
            )
        ),
        omitted_measured_edge,
    )
