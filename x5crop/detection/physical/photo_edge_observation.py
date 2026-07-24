from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import math

import numpy as np

from ...configuration.photo_edges import PhotoEdgeDetectionParameters
from ...domain import (
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
)
from ..evidence.photo_edges import (
    LocalTransitionState,
    PhotoEdgeMeasurementSummary,
    PhotoEdgeObservation,
    PhotoEdgeSearchCorridor,
    PhotoEdgeSideStatistics,
    fragment_constraint_hash,
)


_HALF_PIXEL_POSITION_ENVELOPE = 0.5
_EVEN_DIVISOR = 2
_PREFIX_WORKING_BUFFER_COUNT = 2


@dataclass(frozen=True)
class PhotoEdgeFragment:
    fragment_id: ObservationId
    observations: tuple[PhotoEdgeObservation, ...]
    censored: bool
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if not self.observations:
            raise ValueError("photo-edge fragments require observations")
        if tuple(
            sorted(
                self.observations,
                key=lambda item: (
                    item.long_axis_footprint.minimum,
                    item.short_axis_position_interval.minimum,
                    str(item.observation_id),
                ),
            )
        ) != self.observations:
            raise ValueError("photo-edge fragment observations must be ordered")
        if any(
            observation.state != LocalTransitionState.SUPPORTED
            for observation in self.observations
        ):
            raise ValueError(
                "persisted photo-edge fragments contain supported transitions only"
            )
        if self.provenance.observation_id != self.fragment_id:
            raise ValueError(
                "photo-edge fragment identity must match its provenance"
            )

    @property
    def long_axis_footprint(self) -> PixelInterval:
        return PixelInterval(
            min(
                observation.long_axis_footprint.minimum
                for observation in self.observations
            ),
            max(
                observation.long_axis_footprint.maximum
                for observation in self.observations
            ),
        )

    @property
    def short_axis_position_interval(self) -> PixelInterval:
        return PixelInterval(
            min(
                observation.short_axis_position_interval.minimum
                for observation in self.observations
            ),
            max(
                observation.short_axis_position_interval.maximum
                for observation in self.observations
            ),
        )

    @property
    def constraint_sha256(self) -> str:
        return fragment_constraint_hash(self.observations)


@dataclass(frozen=True)
class PhotoEdgeObservationResult:
    fragments: tuple[PhotoEdgeFragment, ...]
    summary: PhotoEdgeMeasurementSummary


@dataclass(frozen=True)
class _ScalePeak:
    scale: float
    depth: int
    position: float
    threshold_support_interval: PixelInterval
    intensity_effect: float
    texture_effect: float
    gradient_effect: float
    local_noise: float
    censored: bool


@dataclass(frozen=True)
class _AnchorTransition:
    long_axis_footprint: PixelInterval
    position_interval: PixelInterval
    negative: PhotoEdgeSideStatistics
    positive: PhotoEdgeSideStatistics
    intensity_effect: float
    texture_effect: float
    gradient_effect: float
    local_noise: float
    scales: tuple[float, ...]
    censored: bool


@dataclass(frozen=True)
class _MeasurementDomain:
    interval: PixelInterval
    uncensored_interval: PixelInterval | None


@dataclass(frozen=True)
class _ChunkAnchorProfiles:
    starts: tuple[int, ...]
    intensity: np.ndarray
    texture: np.ndarray
    gradient: np.ndarray
    temporary_buffer_upper_bound_bytes: int


def _rolling_mean(values: np.ndarray, width: int) -> np.ndarray:
    if width <= 0 or width > values.shape[0]:
        raise ValueError("rolling mean requires a valid width")
    cumulative = np.concatenate(
        (np.zeros(1, dtype=np.float64), np.cumsum(values, dtype=np.float64))
    )
    return (cumulative[width:] - cumulative[:-width]) / float(width)


def _deterministic_median(values: np.ndarray) -> float:
    ordered = np.sort(np.ravel(values))
    midpoint = ordered.shape[0] // _EVEN_DIVISOR
    if ordered.shape[0] % _EVEN_DIVISOR:
        return float(ordered[midpoint])
    return 0.5 * float(ordered[midpoint - 1] + ordered[midpoint])


def _first_difference_mad(
    values: np.ndarray,
) -> float:
    if values.shape[0] <= 1:
        return 0.0
    differences = np.abs(np.diff(values))
    median = _deterministic_median(differences)
    return _deterministic_median(np.abs(differences - median))


def _local_noise_at(
    values: np.ndarray,
    position: int,
    depth: int,
    floor: float,
) -> float:
    return max(
        floor,
        _first_difference_mad(values[position - depth : position]),
        _first_difference_mad(values[position : position + depth]),
    )


def _side_statistics(
    intensities: np.ndarray,
    textures: np.ndarray,
    gradients: np.ndarray,
) -> PhotoEdgeSideStatistics:
    median = _deterministic_median(intensities)
    return PhotoEdgeSideStatistics(
        intensity_median_u8=median,
        intensity_mad_u8=_deterministic_median(
            np.abs(intensities - median)
        ),
        texture_median_u8=_deterministic_median(textures),
        gradient_median_u8=_deterministic_median(gradients),
    )


def _window_means(
    values: np.ndarray,
    starts: np.ndarray,
    width: int,
) -> np.ndarray:
    prefix = np.concatenate(
        (
            np.zeros((values.shape[0], 1), dtype=np.float64),
            np.cumsum(values, axis=1, dtype=np.float64),
        ),
        axis=1,
    )
    return (
        prefix[:, starts + width] - prefix[:, starts]
    ) / float(width)


def _chunk_anchor_profiles(
    gray_work: np.ndarray,
    starts: tuple[int, ...],
    support_width: int,
) -> _ChunkAnchorProfiles:
    if not starts:
        return _ChunkAnchorProfiles(
            starts=(),
            intensity=np.empty((gray_work.shape[0], 0), dtype=np.float64),
            texture=np.empty((gray_work.shape[0], 0), dtype=np.float64),
            gradient=np.empty((gray_work.shape[0], 0), dtype=np.float64),
            temporary_buffer_upper_bound_bytes=0,
        )
    read_start = starts[0]
    read_end = starts[-1] + support_width
    chunk_u8 = gray_work[:, read_start:read_end]
    chunk = chunk_u8.astype(np.float64)
    relative_starts = np.asarray(starts, dtype=np.int64) - read_start
    intensity = _window_means(
        chunk,
        relative_starts,
        support_width,
    )
    squared_mean = _window_means(
        chunk * chunk,
        relative_starts,
        support_width,
    )
    texture = np.sqrt(
        np.maximum(0.0, squared_mean - intensity * intensity)
    )
    if support_width > 1:
        horizontal_gradient = _window_means(
            np.abs(np.diff(chunk, axis=1)),
            relative_starts,
            support_width - 1,
        )
    else:
        horizontal_gradient = np.zeros_like(intensity)
    vertical_values = np.empty_like(chunk)
    vertical_values[0] = 0.0
    vertical_values[1:] = np.abs(np.diff(chunk, axis=0))
    vertical_gradient = _window_means(
        vertical_values,
        relative_starts,
        support_width,
    )
    gradient = np.maximum(horizontal_gradient, vertical_gradient)
    retained_bytes = sum(
        array.nbytes
        for array in (
            chunk_u8,
            chunk,
            intensity,
            squared_mean,
            texture,
            horizontal_gradient,
            vertical_values,
            vertical_gradient,
            gradient,
        )
    )
    prefix_upper_bound = _PREFIX_WORKING_BUFFER_COUNT * (
        chunk.shape[0] * (chunk.shape[1] + 1) * np.dtype(np.float64).itemsize
    )
    return _ChunkAnchorProfiles(
        starts=starts,
        intensity=intensity,
        texture=texture,
        gradient=gradient,
        temporary_buffer_upper_bound_bytes=(
            retained_bytes + prefix_upper_bound
        ),
    )


def _candidate_domains_at(
    coordinate: float,
    corridors: tuple[PhotoEdgeSearchCorridor, ...],
) -> tuple[PixelInterval, ...]:
    intervals = tuple(
        corridor.side_interval_at(coordinate, top=top)
        for corridor in corridors
        for top in (True, False)
    )
    if not intervals:
        return ()
    ordered = sorted(intervals)
    merged: list[PixelInterval] = []
    for interval in ordered:
        if not merged or interval.minimum > merged[-1].maximum:
            merged.append(interval)
        else:
            merged[-1] = PixelInterval(
                merged[-1].minimum,
                max(merged[-1].maximum, interval.maximum),
            )
    return tuple(merged)


def _measurement_domain(
    intervals: tuple[PixelInterval, ...],
    short_extent: int,
    halo: int,
) -> tuple[_MeasurementDomain, ...]:
    canvas = PixelInterval(0.0, float(short_extent - 1))
    domains: list[_MeasurementDomain] = []
    for interval in intervals:
        requested = PixelInterval(
            interval.minimum - float(halo),
            interval.maximum + float(halo),
        )
        measured = requested.intersection(canvas)
        if measured is not None:
            uncensored_minimum = (
                measured.minimum + float(halo)
                if requested.minimum < canvas.minimum
                else measured.minimum
            )
            uncensored_maximum = (
                measured.maximum - float(halo)
                if requested.maximum > canvas.maximum
                else measured.maximum
            )
            domains.append(
                _MeasurementDomain(
                    measured,
                    (
                        None
                        if uncensored_maximum < uncensored_minimum
                        else PixelInterval(
                            uncensored_minimum,
                            uncensored_maximum,
                        )
                    ),
                )
            )
    if not domains:
        return ()
    return tuple(sorted(domains, key=lambda item: item.interval))


def _local_peaks_for_scale(
    row_intensity: np.ndarray,
    row_texture: np.ndarray,
    row_gradient: np.ndarray,
    domains: tuple[_MeasurementDomain, ...],
    depth: int,
    scale: float,
    parameters: PhotoEdgeDetectionParameters,
) -> tuple[_ScalePeak, ...]:
    short_extent = row_intensity.shape[0]
    if 2 * depth + 1 >= short_extent:
        return ()
    negative_intensity = _rolling_mean(row_intensity, depth)[: -depth]
    positive_intensity = _rolling_mean(row_intensity, depth)[depth:]
    negative_texture = _rolling_mean(row_texture, depth)[: -depth]
    positive_texture = _rolling_mean(row_texture, depth)[depth:]
    negative_gradient = _rolling_mean(row_gradient, depth)[: -depth]
    positive_gradient = _rolling_mean(row_gradient, depth)[depth:]
    candidate_positions = np.arange(
        depth,
        short_extent - depth + 1,
        dtype=np.int64,
    )
    expected = candidate_positions.shape[0]
    arrays = (
        negative_intensity,
        positive_intensity,
        negative_texture,
        positive_texture,
        negative_gradient,
        positive_gradient,
    )
    arrays = tuple(array[:expected] for array in arrays)
    (
        negative_intensity,
        positive_intensity,
        negative_texture,
        positive_texture,
        negative_gradient,
        positive_gradient,
    ) = arrays
    intensity_effect = np.abs(positive_intensity - negative_intensity)
    texture_effect = np.abs(positive_texture - negative_texture)
    gradient_effect = np.abs(positive_gradient - negative_gradient)
    response = np.maximum.reduce(
        (intensity_effect, texture_effect, gradient_effect)
    )
    supported = response >= (
        parameters.minimum_local_effect
        + parameters.local_noise_floor_u8
    )
    domain_mask = np.zeros(expected, dtype=bool)
    for domain in domains:
        domain_mask |= (
            (
                candidate_positions
                >= math.floor(domain.interval.minimum)
            )
            & (
                candidate_positions
                <= math.ceil(domain.interval.maximum)
            )
        )
    supported &= domain_mask
    supported_indices = np.flatnonzero(supported)
    components = tuple(
        component
        for component in np.split(
            supported_indices,
            np.flatnonzero(np.diff(supported_indices) > 1) + 1,
        )
        if component.size
    )
    peaks: list[_ScalePeak] = []
    for component in components:
        component_responses = response[component]
        candidate_indices: list[int] = []
        plateau_start = 0
        while plateau_start < component.size:
            plateau_end = plateau_start + 1
            plateau_response = component_responses[plateau_start]
            while (
                plateau_end < component.size
                and component_responses[plateau_end] == plateau_response
            ):
                plateau_end += 1
            left_response = (
                component_responses[plateau_start - 1]
                if plateau_start > 0
                else -math.inf
            )
            right_response = (
                component_responses[plateau_end]
                if plateau_end < component.size
                else -math.inf
            )
            if (
                plateau_response >= left_response
                and plateau_response >= right_response
                and (
                    plateau_response > left_response
                    or plateau_response > right_response
                )
            ):
                plateau_midpoint = (
                    plateau_start + plateau_end - 1
                ) // _EVEN_DIVISOR
                candidate_indices.append(
                    int(component[plateau_midpoint])
                )
            plateau_start = plateau_end
        for index in candidate_indices:
            local_noise = _local_noise_at(
                row_intensity,
                int(candidate_positions[index]),
                depth,
                parameters.local_noise_floor_u8,
            )
            if response[index] < (
                parameters.minimum_local_effect + local_noise
            ):
                continue
            position = int(candidate_positions[index])
            threshold_support_interval = PixelInterval(
                float(position) - _HALF_PIXEL_POSITION_ENVELOPE,
                float(position) + _HALF_PIXEL_POSITION_ENVELOPE,
            )
            containing_domains = tuple(
                domain
                for domain in domains
                if domain.interval.intersects(threshold_support_interval)
            )
            censored = not any(
                domain.uncensored_interval is not None
                and (
                    threshold_support_interval.minimum
                    > domain.uncensored_interval.minimum
                )
                and (
                    threshold_support_interval.maximum
                    < domain.uncensored_interval.maximum
                )
                for domain in containing_domains
            )
            peaks.append(
                _ScalePeak(
                    scale=scale,
                    depth=depth,
                    position=float(position),
                    threshold_support_interval=threshold_support_interval,
                    intensity_effect=float(intensity_effect[index]),
                    texture_effect=float(texture_effect[index]),
                    gradient_effect=float(gradient_effect[index]),
                    local_noise=local_noise,
                    censored=censored,
                )
            )
    return tuple(peaks)


def _cluster_scale_peaks(
    peaks: tuple[_ScalePeak, ...],
    row_intensity: np.ndarray,
    row_texture: np.ndarray,
    row_gradient: np.ndarray,
    base_depth: int,
    minimum_scales: int,
    position_tolerance_ratio: float,
    footprint: PixelInterval,
) -> tuple[tuple[_AnchorTransition, ...], int]:
    if not peaks:
        return (), 0
    tolerance = max(
        1.0,
        position_tolerance_ratio * float(base_depth),
    )
    groups: list[list[_ScalePeak]] = []
    common_support: list[PixelInterval] = []
    for peak in sorted(peaks, key=lambda item: (item.position, item.scale)):
        if not groups:
            groups.append([peak])
            common_support.append(peak.threshold_support_interval)
            continue
        current = groups[-1]
        shared = common_support[-1].intersection(
            peak.threshold_support_interval
        )
        if (
            shared is not None
            and peak.position - current[0].position <= tolerance
        ):
            current.append(peak)
            common_support[-1] = shared
        else:
            groups.append([peak])
            common_support.append(peak.threshold_support_interval)
    transitions: list[_AnchorTransition] = []
    merged_duplicate_count = 0
    for group in groups:
        scales = tuple(sorted({item.scale for item in group}))
        if len(scales) < minimum_scales:
            continue
        merged_duplicate_count += max(0, len(group) - 1)
        positions = tuple(item.position for item in group)
        interval = PixelInterval(
            min(positions) - _HALF_PIXEL_POSITION_ENVELOPE,
            max(positions) + _HALF_PIXEL_POSITION_ENVELOPE,
        )
        representative = min(
            group,
            key=lambda item: (
                abs(item.scale - 1.0),
                item.position,
            ),
        )
        position = int(round(representative.position))
        negative_slice = slice(
            position - representative.depth,
            position,
        )
        positive_slice = slice(
            position,
            position + representative.depth,
        )
        transitions.append(
            _AnchorTransition(
                long_axis_footprint=footprint,
                position_interval=interval,
                negative=_side_statistics(
                    row_intensity[negative_slice],
                    row_texture[negative_slice],
                    row_gradient[negative_slice],
                ),
                positive=_side_statistics(
                    row_intensity[positive_slice],
                    row_texture[positive_slice],
                    row_gradient[positive_slice],
                ),
                intensity_effect=max(
                    item.intensity_effect for item in group
                ),
                texture_effect=max(
                    item.texture_effect for item in group
                ),
                gradient_effect=max(
                    item.gradient_effect for item in group
                ),
                local_noise=max(item.local_noise for item in group),
                scales=scales,
                censored=any(item.censored for item in group),
            )
        )
    return tuple(transitions), merged_duplicate_count


def _anchor_transitions(
    row_intensity: np.ndarray,
    row_texture: np.ndarray,
    row_gradient: np.ndarray,
    start: int,
    end: int,
    corridors: tuple[PhotoEdgeSearchCorridor, ...],
    parameters: PhotoEdgeDetectionParameters,
) -> tuple[tuple[_AnchorTransition, ...], int]:
    center = 0.5 * float(start + end - 1)
    proposal_domains = (
        _candidate_domains_at(center, corridors)
        if corridors
        else (PixelInterval(0.0, float(row_intensity.shape[0] - 1)),)
    )
    base_depth = max(
        parameters.local_window_min_px,
        int(round(row_intensity.shape[0] * parameters.local_window_height_ratio)),
    )
    maximum_depth = max(
        parameters.local_window_min_px,
        int(round(base_depth * max(parameters.multiscale_factors))),
    )
    domains = _measurement_domain(
        proposal_domains,
        row_intensity.shape[0],
        maximum_depth + 1,
    )
    scale_by_depth: dict[int, float] = {}
    for scale in parameters.multiscale_factors:
        depth = max(
            parameters.local_window_min_px,
            int(round(base_depth * scale)),
        )
        scale_by_depth.setdefault(depth, scale)
    peaks = tuple(
        peak
        for depth, scale in sorted(scale_by_depth.items())
        for peak in _local_peaks_for_scale(
            row_intensity,
            row_texture,
            row_gradient,
            domains,
            depth,
            scale,
            parameters,
        )
    )
    transitions, duplicate_count = _cluster_scale_peaks(
        peaks,
        row_intensity,
        row_texture,
        row_gradient,
        base_depth,
        parameters.minimum_supporting_scales,
        parameters.multiscale_position_tolerance_ratio,
        PixelInterval(float(start), float(end - 1)),
    )
    return transitions, duplicate_count


def _connected_components(
    transitions: tuple[_AnchorTransition, ...],
) -> tuple[tuple[_AnchorTransition, ...], ...]:
    ordered = tuple(
        sorted(
            transitions,
            key=lambda item: (
                item.long_axis_footprint.minimum,
                item.position_interval.minimum,
            ),
        )
    )
    parents = list(range(len(ordered)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parents[max(left_root, right_root)] = min(left_root, right_root)

    for right_index, right in enumerate(ordered):
        for left_index in range(right_index - 1, -1, -1):
            left = ordered[left_index]
            overlap = min(
                left.long_axis_footprint.maximum,
                right.long_axis_footprint.maximum,
            ) - max(
                left.long_axis_footprint.minimum,
                right.long_axis_footprint.minimum,
            )
            if (
                right.long_axis_footprint.minimum
                > left.long_axis_footprint.maximum + 1.0
            ):
                break
            if overlap < -1.0:
                continue
            if left.position_interval.expanded(1.0).intersects(
                right.position_interval
            ):
                union(left_index, right_index)
    groups: dict[int, list[_AnchorTransition]] = {}
    for index, transition in enumerate(ordered):
        groups.setdefault(find(index), []).append(transition)
    return tuple(
        tuple(group)
        for _, group in sorted(
            groups.items(),
            key=lambda item: (
                min(
                    transition.long_axis_footprint.minimum
                    for transition in item[1]
                ),
                min(
                    transition.position_interval.minimum
                    for transition in item[1]
                ),
            ),
        )
    )


def _canonical_observations(
    component: tuple[_AnchorTransition, ...],
    source_sha256: str,
    observation_prefix: str,
    component_index: int,
    support_width: int,
) -> tuple[PhotoEdgeObservation, ...]:
    minimum = int(
        math.floor(
            min(item.long_axis_footprint.minimum for item in component)
            / float(support_width)
        )
        * support_width
    )
    maximum = int(
        math.ceil(
            max(item.long_axis_footprint.maximum for item in component)
            / float(support_width)
        )
        * support_width
    )
    observations: list[PhotoEdgeObservation] = []
    for start in range(minimum, maximum, support_width):
        end = start + support_width
        covering = tuple(
            item
            for item in component
            if (
                item.long_axis_footprint.minimum <= float(start)
                and item.long_axis_footprint.maximum >= float(end - 1)
            )
        )
        if not covering:
            continue
        position = PixelInterval(
            min(item.position_interval.minimum for item in covering),
            max(item.position_interval.maximum for item in covering),
        )
        observation_id = ObservationId(
            f"{observation_prefix}:component_{component_index:04d}:"
            f"u_{start}_{end}"
        )
        representative = min(
            covering,
            key=lambda item: (
                item.position_interval.maximum
                - item.position_interval.minimum,
                item.position_interval.midpoint,
            ),
        )
        channels = tuple(
            channel
            for channel, effect in (
                ("gradient", representative.gradient_effect),
                ("intensity", representative.intensity_effect),
                ("texture", representative.texture_effect),
            )
            if effect > 0.0
        )
        observations.append(
            PhotoEdgeObservation(
                observation_id=observation_id,
                source_sha256=source_sha256,
                long_axis_footprint=PixelInterval(
                    float(start),
                    float(end - 1),
                ),
                short_axis_position_interval=position,
                negative_side_statistics=representative.negative,
                positive_side_statistics=representative.positive,
                absolute_intensity_effect=max(
                    item.intensity_effect for item in covering
                ),
                absolute_texture_effect=max(
                    item.texture_effect for item in covering
                ),
                absolute_gradient_effect=max(
                    item.gradient_effect for item in covering
                ),
                local_noise_u8=max(item.local_noise for item in covering),
                multiscale_position_interval=position,
                state=LocalTransitionState.SUPPORTED,
                measurement_channels=channels,
                measurement_scales=tuple(
                    sorted(
                        {
                            scale
                            for item in covering
                            for scale in item.scales
                        }
                    )
                ),
                censored=any(item.censored for item in covering),
                provenance=MeasurementProvenance(
                    root_measurement=MeasurementIdentity.PHOTO_EDGES,
                    observation_id=observation_id,
                    dependencies=(MeasurementIdentity.GRAY_WORK,),
                    description=(
                        "canonical multiscale local photo-edge transition"
                    ),
                ),
            )
        )
    return tuple(observations)


def observe_photo_edge_fragments(
    gray_work: np.ndarray,
    corridors: tuple[PhotoEdgeSearchCorridor, ...],
    parameters: PhotoEdgeDetectionParameters,
    *,
    source_sha256: str,
    observation_prefix: str,
) -> PhotoEdgeObservationResult:
    if gray_work.ndim != 2 or gray_work.dtype != np.uint8:
        raise ValueError(
            "photo-edge observation requires canonical base_gray_u8"
        )
    if (
        len(source_sha256) != 64
        or any(character not in "0123456789abcdef" for character in source_sha256)
    ):
        raise ValueError("photo-edge observation requires a source SHA-256")
    width = gray_work.shape[1]
    transitions: list[_AnchorTransition] = []
    raw_anchor_count = 0
    neutral_anchor_count = 0
    merged_duplicate_count = 0
    peak_buffer_bytes = 0
    for chunk_start in range(0, width, parameters.chunk_size_px):
        chunk_end = min(width, chunk_start + parameters.chunk_size_px)
        anchor_start = (
            chunk_start
            if chunk_start == 0
            else max(0, chunk_start - parameters.long_support_width_px)
        )
        first = (
            (
                anchor_start + parameters.long_anchor_stride_px - 1
            )
            // parameters.long_anchor_stride_px
        ) * parameters.long_anchor_stride_px
        starts = tuple(
            start
            for start in range(
                first,
                chunk_end,
                parameters.long_anchor_stride_px,
            )
            if (
                (start >= chunk_start or chunk_start == 0)
                and start + parameters.long_support_width_px <= width
            )
        )
        incomplete_anchor_count = sum(
            1
            for start in range(
                first,
                chunk_end,
                parameters.long_anchor_stride_px,
            )
            if start + parameters.long_support_width_px > width
        )
        neutral_anchor_count += incomplete_anchor_count
        profiles = _chunk_anchor_profiles(
            gray_work,
            starts,
            parameters.long_support_width_px,
        )
        peak_buffer_bytes = max(
            peak_buffer_bytes,
            profiles.temporary_buffer_upper_bound_bytes,
        )
        for profile_index, start in enumerate(profiles.starts):
            end = start + parameters.long_support_width_px
            raw_anchor_count += 1
            observed, duplicate_count = _anchor_transitions(
                profiles.intensity[:, profile_index],
                profiles.texture[:, profile_index],
                profiles.gradient[:, profile_index],
                start,
                end,
                corridors,
                parameters,
            )
            merged_duplicate_count += duplicate_count
            if not observed:
                neutral_anchor_count += 1
            transitions.extend(observed)
    components = _connected_components(tuple(transitions))
    fragments: list[PhotoEdgeFragment] = []
    canonical_count = 0
    censored_count = 0
    for component_index, component in enumerate(components, start=1):
        observations = _canonical_observations(
            component,
            source_sha256,
            observation_prefix,
            component_index,
            parameters.long_support_width_px,
        )
        if not observations:
            continue
        canonical_count += len(observations)
        censored = any(observation.censored for observation in observations)
        if censored:
            censored_count += 1
        digest = sha256(
            fragment_constraint_hash(observations).encode("ascii")
        ).hexdigest()[:16]
        fragment_id = ObservationId(
            f"{observation_prefix}:fragment:{digest}"
        )
        fragments.append(
            PhotoEdgeFragment(
                fragment_id=fragment_id,
                observations=observations,
                censored=censored,
                provenance=MeasurementProvenance(
                    root_measurement=MeasurementIdentity.PHOTO_EDGES,
                    observation_id=fragment_id,
                    dependencies=(MeasurementIdentity.GRAY_WORK,),
                    description="maximal continuous photo-edge ridge fragment",
                    boundary_anchors=tuple(
                        observation.observation_id
                        for observation in observations
                    ),
                ),
            )
        )
    fragments.sort(
        key=lambda fragment: (
            fragment.long_axis_footprint.minimum,
            fragment.short_axis_position_interval.minimum,
            str(fragment.fragment_id),
        )
    )
    return PhotoEdgeObservationResult(
        fragments=tuple(fragments),
        summary=PhotoEdgeMeasurementSummary(
            raw_anchor_count=raw_anchor_count,
            supported_transition_count=len(transitions),
            neutral_anchor_count=neutral_anchor_count,
            censored_component_count=censored_count,
            merged_duplicate_count=merged_duplicate_count,
            fragment_count=len(fragments),
            canonical_observation_count=canonical_count,
            chunk_size_px=parameters.chunk_size_px,
            peak_temporary_buffer_bytes=peak_buffer_bytes,
        ),
    )
