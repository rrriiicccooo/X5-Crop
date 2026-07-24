from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean, median
import numpy as np

from ...configuration.boundary import BoundaryPathParameters
from ...configuration.path_sampling import BoundaryPathSamplingParameters
from ...domain import (
    BoundaryAxis,
    BoundaryKind,
    BoundaryMeasurementSet,
    BoundaryPathSample,
    BoundarySide,
    Box,
    ContainmentFallback,
    GrayAppearanceObservation,
    GrayBoundaryPathObservation,
    HolderBoundaryObservation,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
    boundary_axis_for_side,
    gray_intensity_tail,
)
from ...image.statistics import ImageMeasurementStatistics
from ...utils import runs_from_mask


@dataclass(frozen=True)
class _CrossSectionProfile:
    orthogonal_interval: PixelInterval
    intensity: np.ndarray
    texture: np.ndarray


@dataclass(frozen=True)
class _LocalPathSample:
    section_index: int
    orthogonal_interval: PixelInterval
    position: PixelInterval
    lower_intensity: float
    lower_mad: float
    lower_texture: float
    lower_gradient: float
    upper_intensity: float
    upper_mad: float
    upper_texture: float
    upper_gradient: float


_WindowStatistics = tuple[float, float, float, float]


@dataclass(frozen=True)
class _WindowStatisticsKey:
    section_index: int
    reverse: bool
    start: int
    end: int


_WindowStatisticsCache = dict[_WindowStatisticsKey, _WindowStatistics]


def _texture_image(gray: np.ndarray) -> np.ndarray:
    data = gray.astype(np.float32, copy=False)
    gx = np.abs(np.diff(data, axis=1, prepend=data[:, :1]))
    gy = np.abs(np.diff(data, axis=0, prepend=data[:1, :]))
    return gx + gy


def _cross_section_profiles(
    gray: np.ndarray,
    texture: np.ndarray,
    *,
    scan_axis: int,
    parameters: BoundaryPathSamplingParameters,
) -> tuple[_CrossSectionProfile, ...]:
    orthogonal_extent = gray.shape[0] if scan_axis == 1 else gray.shape[1]
    scan_extent = gray.shape[1] if scan_axis == 1 else gray.shape[0]
    maximum_section_width = max(
        1.0,
        float(scan_extent)
        * float(parameters.maximum_section_width_ratio_to_scan_extent),
    )
    section_count = max(
        int(parameters.minimum_cross_sections),
        int(np.ceil(float(orthogonal_extent) / maximum_section_width)),
    )
    start = 0
    end = orthogonal_extent
    edges = np.linspace(start, end, section_count + 1)
    profiles: list[_CrossSectionProfile] = []
    for left, right in zip(edges[:-1], edges[1:], strict=True):
        section_start = max(start, min(end - 1, int(round(left))))
        section_end = max(section_start + 1, min(end, int(round(right))))
        if scan_axis == 1:
            intensity_section = gray[section_start:section_end, :]
            texture_section = texture[section_start:section_end, :]
            reduction_axis = 0
        else:
            intensity_section = gray[:, section_start:section_end]
            texture_section = texture[:, section_start:section_end]
            reduction_axis = 1
        profiles.append(
            _CrossSectionProfile(
                orthogonal_interval=PixelInterval(
                    float(section_start),
                    float(section_end),
                ),
                intensity=np.median(
                    intensity_section,
                    axis=reduction_axis,
                ).astype(np.float32),
                texture=np.median(
                    texture_section,
                    axis=reduction_axis,
                ).astype(np.float32),
            )
        )
    return tuple(profiles)


def _edge_reference_mask(
    intensity: np.ndarray,
    texture: np.ndarray,
    texture_limit: float,
    parameters: BoundaryPathParameters,
) -> np.ndarray:
    window = max(
        parameters.path_sampling.minimum_local_measurement_window_px,
        int(
            round(
                len(intensity)
                * parameters.path_sampling.local_measurement_window_ratio
            )
        ),
    )
    window = min(len(intensity), window)
    seed_intensity = intensity[:window]
    seed_texture = texture[:window]
    quiet_seed = seed_intensity[seed_texture <= float(texture_limit)]
    reference_intensity = float(
        np.median(quiet_seed if quiet_seed.size else seed_intensity)
    )
    seed_deviation = np.abs(seed_intensity - reference_intensity)
    deviation_center = float(np.median(seed_deviation))
    deviation_mad = float(
        np.median(np.abs(seed_deviation - deviation_center))
    )
    tolerance = float(
        deviation_center
        + parameters.edge_reference_mad_multiplier * deviation_mad
    )
    deviation = np.abs(intensity - reference_intensity)
    return (deviation <= tolerance) & (texture <= float(texture_limit))


def _edge_adjacent_transition(
    intensity: np.ndarray,
    texture: np.ndarray,
    texture_limit: float,
    parameters: BoundaryPathParameters,
) -> tuple[PixelInterval, ...]:
    if not intensity.size:
        return ()
    reference = _edge_reference_mask(
        intensity,
        texture,
        texture_limit,
        parameters,
    )
    window = max(
        parameters.path_sampling.minimum_local_measurement_window_px,
        int(
            round(
                len(reference)
                * parameters.path_sampling.local_measurement_window_ratio
            )
        ),
    )
    window = min(len(reference), window)
    required_nonreference = int(
        np.ceil(window * parameters.edge_transition_persistence_ratio)
    )
    nonreference_counts = np.convolve(
        (~reference).astype(np.int32),
        np.ones(window, dtype=np.int32),
        mode="valid",
    )
    exits = np.flatnonzero(nonreference_counts >= required_nonreference)
    if not exits.size or int(exits[0]) <= 0:
        return ()
    first_exit = int(exits[0])
    return (PixelInterval(float(first_exit), float(first_exit + 1)),)


def _adaptive_change_points(
    signal: np.ndarray,
    parameters: BoundaryPathSamplingParameters,
) -> tuple[PixelInterval, ...]:
    if signal.size <= 1:
        return ()
    change = np.abs(np.diff(signal, prepend=signal[:1]))
    if not np.any(change > 0.0):
        return ()
    runs = tuple(
        (start, end)
        for start, end in runs_from_mask(change > 0.0)
        if start > 0 and end > start and start < signal.size
    )
    if not runs:
        return ()
    strengths = {
        run: float(np.max(change[run[0] : run[1]]))
        for run in runs
    }
    ranked = sorted(
        runs,
        key=lambda run: (-strengths[run], run[0], run[1]),
    )
    priority_threshold = float(
        np.percentile(
            tuple(strengths.values()),
            parameters.change_point_percentile,
        )
    )
    priority_ranked = tuple(
        run for run in ranked if strengths[run] >= priority_threshold
    )
    limit = min(parameters.maximum_change_points_per_section, len(runs))
    bin_count = limit
    spatial_edges = np.linspace(0.0, float(signal.size), bin_count + 1)
    selected: list[tuple[int, int]] = []
    selected_set: set[tuple[int, int]] = set()
    for left, right in zip(spatial_edges[:-1], spatial_edges[1:], strict=True):
        local = tuple(
            run
            for run in runs
            if left <= fmean(run) < right
        )
        if not local:
            continue
        choice = min(local, key=lambda run: (-strengths[run], run[0], run[1]))
        selected.append(choice)
        selected_set.add(choice)
    for candidates in (priority_ranked, ranked):
        for run in candidates:
            if len(selected) >= limit:
                break
            if run not in selected_set:
                selected.append(run)
                selected_set.add(run)
    return tuple(
        PixelInterval(float(start), float(max(start + 1, end)))
        for start, end in sorted(selected)
    )


def _source_interval(
    oriented: PixelInterval,
    extent: int,
    reverse: bool,
) -> PixelInterval:
    if not reverse:
        return oriented
    return PixelInterval(
        float(extent) - oriented.maximum,
        float(extent) - oriented.minimum,
    )


def _window_statistics(
    intensity: np.ndarray,
    texture: np.ndarray,
    start: int,
    end: int,
) -> _WindowStatistics:
    values = intensity[start:end]
    texture_values = texture[start:end]
    if not values.size:
        raise ValueError("boundary appearance window must be non-empty")
    center = float(np.median(values))
    gradient = np.abs(np.diff(values, prepend=values[:1]))
    return (
        center,
        float(np.median(np.abs(values - center))),
        float(np.median(texture_values)),
        float(np.median(gradient)),
    )


def _exact_window_statistics(
    cache: _WindowStatisticsCache,
    key: _WindowStatisticsKey,
    intensity: np.ndarray,
    texture: np.ndarray,
    start: int,
    end: int,
) -> _WindowStatistics:
    measured = cache.get(key)
    if measured is None:
        measured = _window_statistics(intensity, texture, start, end)
        cache[key] = measured
    return measured


def _local_sample(
    section_index: int,
    orthogonal_interval: PixelInterval,
    position: PixelInterval,
    intensity: np.ndarray,
    texture: np.ndarray,
    reverse: bool,
    parameters: BoundaryPathSamplingParameters,
    transform_position_uncertainty_px: float,
    window_statistics: _WindowStatisticsCache,
) -> _LocalPathSample | None:
    coordinate = int(round(position.midpoint))
    extent = len(intensity)
    if coordinate <= 0 or coordinate >= extent:
        return None
    sample_width = max(
        parameters.minimum_local_measurement_window_px,
        int(round(extent * parameters.local_measurement_window_ratio)),
    )
    sample_width = min(extent, sample_width)
    outer_start = max(0, coordinate - sample_width)
    inner_end = min(extent, coordinate + sample_width)
    if outer_start >= coordinate or inner_end <= coordinate:
        return None
    outward = _exact_window_statistics(
        window_statistics,
        _WindowStatisticsKey(
            section_index,
            reverse,
            outer_start,
            coordinate,
        ),
        intensity,
        texture,
        outer_start,
        coordinate,
    )
    inward = _exact_window_statistics(
        window_statistics,
        _WindowStatisticsKey(
            section_index,
            reverse,
            coordinate,
            inner_end,
        ),
        intensity,
        texture,
        coordinate,
        inner_end,
    )
    lower, upper = (outward, inward) if not reverse else (inward, outward)
    source_position = _source_interval(position, extent, reverse)
    measured_position = source_position.expanded(
        transform_position_uncertainty_px
    ).intersection(PixelInterval(0.0, float(extent)))
    if measured_position is None:
        return None
    return _LocalPathSample(
        section_index=section_index,
        orthogonal_interval=orthogonal_interval,
        position=measured_position,
        lower_intensity=lower[0],
        lower_mad=lower[1],
        lower_texture=lower[2],
        lower_gradient=lower[3],
        upper_intensity=upper[0],
        upper_mad=upper[1],
        upper_texture=upper[2],
        upper_gradient=upper[3],
    )


def _local_samples_for_kind(
    profiles: tuple[_CrossSectionProfile, ...],
    side: BoundarySide,
    kind: BoundaryKind,
    statistics: ImageMeasurementStatistics,
    parameters: BoundaryPathSamplingParameters | BoundaryPathParameters,
    transform_position_uncertainty_px: float,
    window_statistics: _WindowStatisticsCache,
) -> tuple[_LocalPathSample, ...]:
    sampling = (
        parameters.path_sampling
        if isinstance(parameters, BoundaryPathParameters)
        else parameters
    )
    reverse = side in {BoundarySide.TRAILING, BoundarySide.BOTTOM}
    samples: list[_LocalPathSample] = []
    for section_index, profile in enumerate(profiles):
        source_intensity = profile.intensity
        source_texture = profile.texture
        intensity = source_intensity[::-1] if reverse else source_intensity
        texture = source_texture[::-1] if reverse else source_texture
        if kind == BoundaryKind.EDGE_ADJACENT_TRANSITION:
            if not isinstance(parameters, BoundaryPathParameters):
                raise TypeError(
                    "edge-adjacent samples require boundary path parameters"
                )
            positions = _edge_adjacent_transition(
                intensity,
                texture,
                statistics.edge_texture_limit,
                parameters,
            )
        elif kind == BoundaryKind.TONAL_TRANSITION:
            positions = _adaptive_change_points(intensity, sampling)
        elif kind == BoundaryKind.TEXTURE_TRANSITION:
            positions = _adaptive_change_points(texture, sampling)
        else:
            raise ValueError(f"unsupported boundary path kind: {kind}")
        for position in positions:
            sample = _local_sample(
                section_index,
                profile.orthogonal_interval,
                position,
                intensity,
                texture,
                reverse,
                sampling,
                transform_position_uncertainty_px,
                window_statistics,
            )
            if sample is not None:
                samples.append(sample)
    return tuple(samples)


def _cluster_samples(
    samples: tuple[_LocalPathSample, ...],
    extent: int,
    section_count: int,
    parameters: BoundaryPathSamplingParameters,
    minimum_path_samples: int | None = None,
    minimum_path_support_ratio: float | None = None,
) -> tuple[tuple[_LocalPathSample, ...], ...]:
    if (
        minimum_path_samples is None
        and minimum_path_support_ratio is None
    ):
        raise ValueError(
            "path clustering requires a count or support-ratio contract"
        )
    tolerance = max(
        float(parameters.path_cluster_tolerance_min_px),
        float(extent) * float(parameters.path_cluster_tolerance_ratio),
    )
    if minimum_path_samples is not None:
        minimum_support = max(1, int(minimum_path_samples))
    else:
        assert minimum_path_support_ratio is not None
        minimum_support = max(
            1,
            int(
                np.ceil(
                    section_count * minimum_path_support_ratio
                )
            ),
        )
    by_section = {
        section_index: tuple(
            sample for sample in samples if sample.section_index == section_index
        )
        for section_index in sorted({sample.section_index for sample in samples})
    }
    def prediction(
        track: tuple[_LocalPathSample, ...],
        coordinate: float,
    ) -> float:
        if len(track) == 1:
            return track[0].position.midpoint
        coordinates = tuple(
            sample.orthogonal_interval.midpoint for sample in track
        )
        positions = tuple(sample.position.midpoint for sample in track)
        coordinate_center = sum(coordinates) / float(len(coordinates))
        position_center = sum(positions) / float(len(positions))
        denominator = sum(
            (item - coordinate_center) ** 2 for item in coordinates
        )
        if denominator <= 0.0:
            return position_center
        slope = sum(
            (item - coordinate_center) * (position - position_center)
            for item, position in zip(coordinates, positions, strict=True)
        ) / denominator
        return position_center + slope * (coordinate - coordinate_center)

    active_tracks: list[tuple[_LocalPathSample, ...]] = []
    completed_tracks: list[tuple[_LocalPathSample, ...]] = []
    for section_index in range(section_count):
        section_samples = by_section.get(section_index, ())
        eligible_tracks: list[tuple[_LocalPathSample, ...]] = []
        for track in active_tracks:
            gap = section_index - track[-1].section_index
            if 0 < gap <= parameters.maximum_path_section_gap + 1:
                eligible_tracks.append(track)
            else:
                completed_tracks.append(track)

        associations: list[tuple[float, int, int]] = []
        for track_index, track in enumerate(eligible_tracks):
            gap = section_index - track[-1].section_index
            for sample_index, sample in enumerate(section_samples):
                residual = abs(
                    sample.position.midpoint
                    - prediction(track, sample.orthogonal_interval.midpoint)
                )
                if residual <= tolerance * float(gap):
                    associations.append((residual, track_index, sample_index))
        assigned_tracks: dict[int, int] = {}
        assigned_samples: set[int] = set()
        for _, track_index, sample_index in sorted(associations):
            if track_index in assigned_tracks or sample_index in assigned_samples:
                continue
            assigned_tracks[track_index] = sample_index
            assigned_samples.add(sample_index)

        next_tracks: list[tuple[_LocalPathSample, ...]] = []
        for track_index, track in enumerate(eligible_tracks):
            sample_index = assigned_tracks.get(track_index)
            if sample_index is not None:
                next_tracks.append((*track, section_samples[sample_index]))
                continue
            gap = section_index - track[-1].section_index
            if gap <= parameters.maximum_path_section_gap:
                next_tracks.append(track)
            else:
                completed_tracks.append(track)
        next_tracks.extend(
            (sample,)
            for sample_index, sample in enumerate(section_samples)
            if sample_index not in assigned_samples
        )
        active_tracks = next_tracks
    completed_tracks.extend(active_tracks)

    supported = tuple(
        track for track in completed_tracks if len(track) >= minimum_support
    )
    ranked = tuple(
        sorted(
            supported,
            key=lambda cluster: (
                -len(cluster),
                _path_fit_residual(cluster),
                max(item.position.maximum for item in cluster)
                - min(item.position.minimum for item in cluster),
                median(item.position.midpoint for item in cluster),
            ),
        )
    )
    canonical: list[tuple[_LocalPathSample, ...]] = []

    def same_path(
        left: tuple[_LocalPathSample, ...],
        right: tuple[_LocalPathSample, ...],
    ) -> bool:
        left_by_section = {sample.section_index: sample for sample in left}
        right_by_section = {sample.section_index: sample for sample in right}
        shared_sections = left_by_section.keys() & right_by_section.keys()
        if len(shared_sections) != min(len(left), len(right)):
            return False
        return all(
            left_by_section[section].orthogonal_interval
            == right_by_section[section].orthogonal_interval
            and left_by_section[section].position
            == right_by_section[section].position
            for section in shared_sections
        )

    for cluster in ranked:
        if any(same_path(cluster, accepted) for accepted in canonical):
            continue
        canonical.append(cluster)
    return tuple(canonical)


def _path_fit_residual(cluster: tuple[_LocalPathSample, ...]) -> float:
    coordinates = tuple(item.orthogonal_interval.midpoint for item in cluster)
    positions = tuple(item.position.midpoint for item in cluster)
    coordinate_center = sum(coordinates) / float(len(coordinates))
    position_center = sum(positions) / float(len(positions))
    denominator = sum(
        (coordinate - coordinate_center) ** 2 for coordinate in coordinates
    )
    if denominator <= 0.0:
        return max(positions) - min(positions)
    slope = sum(
        (coordinate - coordinate_center) * (position - position_center)
        for coordinate, position in zip(coordinates, positions, strict=True)
    ) / denominator
    intercept = position_center - slope * coordinate_center
    return max(
        abs(position - (intercept + slope * coordinate))
        for coordinate, position in zip(coordinates, positions, strict=True)
    )


def _edge_adjacent_cluster(
    samples: tuple[_LocalPathSample, ...],
    extent: int,
    section_count: int,
    parameters: BoundaryPathParameters,
    minimum_path_samples: int | None = None,
) -> tuple[tuple[_LocalPathSample, ...], ...]:
    minimum_support = (
        max(1, int(minimum_path_samples))
        if minimum_path_samples is not None
        else max(
            1,
            int(np.ceil(section_count * parameters.minimum_path_support_ratio)),
        )
    )
    if len(samples) < minimum_support:
        return ()
    positions = np.asarray(
        [sample.position.midpoint for sample in samples],
        dtype=np.float64,
    )
    center = float(np.median(positions))
    mad = float(np.median(np.abs(positions - center)))
    tolerance = max(
        float(parameters.path_sampling.path_cluster_tolerance_min_px),
        float(extent)
        * float(parameters.path_sampling.path_cluster_tolerance_ratio),
        mad * float(parameters.path_inlier_mad_multiplier),
    )
    inliers = tuple(
        sample
        for sample in samples
        if abs(sample.position.midpoint - center) <= tolerance
    )
    if len(inliers) < minimum_support:
        return ()
    maximum_residual = max(
        float(parameters.path_sampling.path_cluster_tolerance_min_px),
        float(extent) * float(parameters.maximum_path_fit_residual_ratio),
    )
    if _path_fit_residual(inliers) > maximum_residual:
        return ()
    return (inliers,)


def _provenance(
    kind: BoundaryKind,
    axis: BoundaryAxis,
    path_index: int,
    scan_origin: BoundarySide | None,
    transform_position_uncertainty_px: float,
    observation_prefix: str | None = None,
) -> MeasurementProvenance:
    source = f"{kind.value}:{axis.value}:{path_index}"
    if observation_prefix is not None:
        source = f"{observation_prefix}:{source}"
    if scan_origin is not None:
        source = f"{source}:scan_from_{scan_origin.value}"
    return MeasurementProvenance(
        root_measurement=MeasurementIdentity.BOUNDARY_PATHS,
        observation_id=ObservationId(source),
        dependencies=(
            MeasurementIdentity.GRAY_WORK,
            MeasurementIdentity.IMAGE_MEASUREMENT_STATISTICS,
            *(
                (MeasurementIdentity.WORKSPACE_TRANSFORM,)
                if transform_position_uncertainty_px > 0.0
                else ()
            ),
        ),
        description="measured gray boundary path",
    )


def _appearance(
    cluster: tuple[_LocalPathSample, ...],
    prefix: str,
    provenance: MeasurementProvenance,
    statistics: ImageMeasurementStatistics,
    support_ratio: float,
) -> GrayAppearanceObservation:
    intensity = float(median(getattr(item, f"{prefix}_intensity") for item in cluster))
    return GrayAppearanceObservation(
        intensity_median=intensity,
        intensity_mad=float(median(getattr(item, f"{prefix}_mad") for item in cluster)),
        texture_median=float(median(getattr(item, f"{prefix}_texture") for item in cluster)),
        gradient_median=float(median(getattr(item, f"{prefix}_gradient") for item in cluster)),
        spatial_continuity=support_ratio,
        intensity_tail=gray_intensity_tail(
            intensity,
            statistics.intensity_low,
            statistics.intensity_high,
        ),
        provenance=provenance,
    )


def _paths_for_axis(
    axis: BoundaryAxis,
    profiles: tuple[_CrossSectionProfile, ...],
    statistics: ImageMeasurementStatistics,
    kind: BoundaryKind,
    parameters: BoundaryPathSamplingParameters | BoundaryPathParameters,
    *,
    scan_origin: BoundarySide | None = None,
    minimum_path_samples: int | None,
    transform_position_uncertainty_px: float,
    window_statistics: _WindowStatisticsCache,
    observation_prefix: str | None = None,
) -> tuple[GrayBoundaryPathObservation, ...]:
    if scan_origin is not None and boundary_axis_for_side(scan_origin) != axis:
        raise ValueError("boundary scan origin must lie on the measured axis")
    oriented_side = scan_origin or (
        BoundarySide.LEADING if axis == BoundaryAxis.LONG else BoundarySide.TOP
    )
    extent = len(profiles[0].intensity) if profiles else 0
    local_samples = _local_samples_for_kind(
        profiles,
        oriented_side,
        kind,
        statistics,
        parameters,
        transform_position_uncertainty_px,
        window_statistics,
    )
    if kind == BoundaryKind.EDGE_ADJACENT_TRANSITION:
        if not isinstance(parameters, BoundaryPathParameters):
            raise TypeError(
                "edge-adjacent paths require boundary path parameters"
            )
        clusters = _edge_adjacent_cluster(
            local_samples,
            extent,
            len(profiles),
            parameters,
            minimum_path_samples,
        )
    else:
        sampling = (
            parameters.path_sampling
            if isinstance(parameters, BoundaryPathParameters)
            else parameters
        )
        clusters = _cluster_samples(
            local_samples,
            extent,
            len(profiles),
            sampling,
            minimum_path_samples,
            (
                parameters.minimum_path_support_ratio
                if isinstance(parameters, BoundaryPathParameters)
                else None
            ),
        )
    paths: list[GrayBoundaryPathObservation] = []
    for path_index, cluster in enumerate(clusters):
        samples = tuple(
            BoundaryPathSample(item.orthogonal_interval, item.position)
            for item in cluster
        )
        provenance = _provenance(
            kind,
            axis,
            path_index,
            scan_origin,
            transform_position_uncertainty_px,
            observation_prefix,
        )
        support_ratio = len(cluster) / float(len(profiles))
        paths.append(
            GrayBoundaryPathObservation(
                axis=axis,
                kind=kind,
                samples=samples,
                lower_appearance=_appearance(
                    cluster,
                    "lower",
                    provenance,
                    statistics,
                    support_ratio,
                ),
                upper_appearance=_appearance(
                    cluster,
                    "upper",
                    provenance,
                    statistics,
                    support_ratio,
                ),
                provenance=provenance,
            )
        )
    return tuple(paths)


def _generic_path_rank(
    path: GrayBoundaryPathObservation,
) -> tuple[float, float, float, str, ObservationId]:
    return (
        min(
            path.lower_appearance.spatial_continuity,
            path.upper_appearance.spatial_continuity,
        ),
        path.orthogonal_extent.maximum - path.orthogonal_extent.minimum,
        -(path.position.maximum - path.position.minimum),
        path.kind.value,
        path.provenance.observation_id,
    )


def _holder_boundary(
    side: BoundarySide,
    candidates: tuple[GrayBoundaryPathObservation, ...],
    measurement_extent: PixelInterval,
) -> HolderBoundaryObservation | None:
    if not candidates:
        return None
    outer_appearance = (
        (lambda path: path.lower_appearance)
        if side in {BoundarySide.LEADING, BoundarySide.TOP}
        else (lambda path: path.upper_appearance)
    )
    best_support = max(
        outer_appearance(path).spatial_continuity for path in candidates
    )
    best = tuple(
        path
        for path in candidates
        if outer_appearance(path).spatial_continuity == best_support
    )
    shared = PixelInterval.common_intersection(
        tuple(path.position for path in best)
    )
    if shared is not None:
        shared = shared.intersection(measurement_extent)
    if shared is None:
        return None
    return HolderBoundaryObservation(side, shared, best)


def boundary_measurements(
    gray: np.ndarray,
    statistics: ImageMeasurementStatistics,
    parameters: BoundaryPathParameters,
    *,
    axes: tuple[BoundaryAxis, ...],
    minimum_path_samples: int | None = None,
    transform_position_uncertainty_px: float,
) -> BoundaryMeasurementSet:
    if gray.ndim != 2 or not gray.size:
        raise ValueError("boundary measurement requires non-empty grayscale")
    if (
        not np.isfinite(transform_position_uncertainty_px)
        or transform_position_uncertainty_px < 0.0
    ):
        raise ValueError("transform position uncertainty must be finite")
    if not axes or len(set(axes)) != len(axes) or any(
        axis not in {BoundaryAxis.LONG, BoundaryAxis.SHORT} for axis in axes
    ):
        raise ValueError("boundary measurement requires unique spatial axes")
    if minimum_path_samples is not None and minimum_path_samples <= 0:
        raise ValueError("boundary path retention count must be positive")
    texture = _texture_image(gray)
    profiles_by_axis = {}
    if BoundaryAxis.LONG in axes:
        profiles_by_axis[BoundaryAxis.LONG] = _cross_section_profiles(
            gray,
            texture,
            scan_axis=1,
            parameters=parameters.path_sampling,
        )
    if BoundaryAxis.SHORT in axes:
        profiles_by_axis[BoundaryAxis.SHORT] = _cross_section_profiles(
            gray,
            texture,
            scan_axis=0,
            parameters=parameters.path_sampling,
        )
    window_statistics_by_axis: dict[
        BoundaryAxis,
        _WindowStatisticsCache,
    ] = {axis: {} for axis in profiles_by_axis}
    generic_paths: list[GrayBoundaryPathObservation] = []
    for axis, profiles in profiles_by_axis.items():
        measured_axis_paths: list[GrayBoundaryPathObservation] = []
        for kind in (BoundaryKind.TONAL_TRANSITION, BoundaryKind.TEXTURE_TRANSITION):
            measured_axis_paths.extend(
                _paths_for_axis(
                    axis,
                    profiles,
                    statistics,
                    kind,
                    parameters,
                    minimum_path_samples=minimum_path_samples,
                    transform_position_uncertainty_px=(
                        transform_position_uncertainty_px
                    ),
                    window_statistics=window_statistics_by_axis[axis],
                )
            )
        ranked_axis_paths = tuple(
            sorted(
                dict.fromkeys(measured_axis_paths),
                key=_generic_path_rank,
                reverse=True,
            )
        )
        generic_paths.extend(ranked_axis_paths)
    edge_measurements_by_side = {
        side: _paths_for_axis(
            boundary_axis_for_side(side),
            profiles_by_axis[boundary_axis_for_side(side)],
            statistics,
            BoundaryKind.EDGE_ADJACENT_TRANSITION,
            parameters,
            scan_origin=side,
            minimum_path_samples=minimum_path_samples,
            transform_position_uncertainty_px=(
                transform_position_uncertainty_px
            ),
            window_statistics=window_statistics_by_axis[
                boundary_axis_for_side(side)
            ],
        )
        for side in BoundarySide
        if boundary_axis_for_side(side) in profiles_by_axis
    }
    edge_paths_by_side = {
        side: paths for side, paths in edge_measurements_by_side.items()
    }
    edge_paths = tuple(
        path for paths in edge_paths_by_side.values() for path in paths
    )
    raw_paths = (*generic_paths, *edge_paths)
    height, width = gray.shape
    holder_boundaries = tuple(
        boundary
        for side, paths in edge_paths_by_side.items()
        if (
            boundary := _holder_boundary(
                side,
                paths,
                PixelInterval(
                    0.0,
                    float(
                        width
                        if boundary_axis_for_side(side) == BoundaryAxis.LONG
                        else height
                    ),
                ),
            )
        )
        is not None
    )
    return BoundaryMeasurementSet(
        raw_paths=raw_paths,
        holder_boundaries=holder_boundaries,
        containment_fallback=ContainmentFallback(
            Box(0, 0, width, height),
            MeasurementProvenance(
                root_measurement=MeasurementIdentity.CANVAS,
                observation_id=ObservationId("workspace_containment_fallback"),
                dependencies=(MeasurementIdentity.GRAY_WORK,),
                description="workspace containment fallback",
            ),
        ),
    )
