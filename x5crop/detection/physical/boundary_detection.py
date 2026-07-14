from __future__ import annotations

from dataclasses import dataclass
from statistics import median

import numpy as np

from ...configuration.boundary import BoundaryPathParameters
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
    parameters: BoundaryPathParameters,
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
    deviation = np.abs(intensity - float(intensity[0]))
    tolerance = float(
        np.percentile(deviation, parameters.edge_reference_percentile)
    )
    return (deviation <= tolerance) & (texture <= float(texture_limit))


def _edge_adjacent_transition(
    intensity: np.ndarray,
    texture: np.ndarray,
    texture_limit: float,
    parameters: BoundaryPathParameters,
) -> tuple[PixelInterval, ...]:
    if not intensity.size or float(texture[0]) > float(texture_limit):
        return ()
    reference = _edge_reference_mask(
        intensity,
        texture,
        texture_limit,
        parameters,
    )
    if not bool(reference[0]):
        return ()
    exits = np.flatnonzero(~reference)
    if not exits.size or int(exits[0]) <= 0:
        return ()
    return (PixelInterval.exact(float(exits[0])),)


def _adaptive_change_points(
    signal: np.ndarray,
    parameters: BoundaryPathParameters,
) -> tuple[PixelInterval, ...]:
    if signal.size <= 1:
        return ()
    change = np.abs(np.diff(signal, prepend=signal[:1]))
    threshold = float(np.percentile(change, parameters.change_point_percentile))
    if threshold <= 0.0:
        return ()
    runs = tuple(
        (start, end)
        for start, end in runs_from_mask(change >= threshold)
        if start > 0 and end > start and start < signal.size
    )
    ranked = sorted(
        runs,
        key=lambda run: float(np.max(change[run[0] : run[1]])),
        reverse=True,
    )
    selected = ranked[: parameters.strongest_change_points_per_section]
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
) -> tuple[float, float, float, float]:
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


def _local_sample(
    section_index: int,
    orthogonal_interval: PixelInterval,
    position: PixelInterval,
    intensity: np.ndarray,
    texture: np.ndarray,
    reverse: bool,
    parameters: BoundaryPathParameters,
) -> _LocalPathSample | None:
    coordinate = int(round(position.midpoint))
    extent = len(intensity)
    if coordinate <= 0 or coordinate >= extent:
        return None
    sample_width = max(1, int(round(extent * parameters.inner_sample_ratio)))
    outer_start = max(0, coordinate - sample_width)
    inner_end = min(extent, coordinate + sample_width)
    if outer_start >= coordinate or inner_end <= coordinate:
        return None
    outward = _window_statistics(
        intensity,
        texture,
        outer_start,
        coordinate,
    )
    inward = _window_statistics(
        intensity,
        texture,
        coordinate,
        inner_end,
    )
    lower, upper = (outward, inward) if not reverse else (inward, outward)
    return _LocalPathSample(
        section_index=section_index,
        orthogonal_interval=orthogonal_interval,
        position=_source_interval(position, extent, reverse),
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
    parameters: BoundaryPathParameters,
) -> tuple[_LocalPathSample, ...]:
    reverse = side in {BoundarySide.TRAILING, BoundarySide.BOTTOM}
    samples: list[_LocalPathSample] = []
    for section_index, profile in enumerate(profiles):
        source_intensity = profile.intensity
        source_texture = profile.texture
        intensity = source_intensity[::-1] if reverse else source_intensity
        texture = source_texture[::-1] if reverse else source_texture
        if kind == BoundaryKind.EDGE_ADJACENT_TRANSITION:
            positions = _edge_adjacent_transition(
                intensity,
                texture,
                statistics.edge_texture_limit,
                parameters,
            )
        elif kind == BoundaryKind.TONAL_TRANSITION:
            positions = _adaptive_change_points(intensity, parameters)
        elif kind == BoundaryKind.TEXTURE_TRANSITION:
            positions = _adaptive_change_points(texture, parameters)
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
                parameters,
            )
            if sample is not None:
                samples.append(sample)
    return tuple(samples)


def _cluster_samples(
    samples: tuple[_LocalPathSample, ...],
    extent: int,
    section_count: int,
    parameters: BoundaryPathParameters,
) -> tuple[tuple[tuple[_LocalPathSample, ...], ...], bool]:
    tolerance = max(
        float(parameters.path_cluster_tolerance_min_px),
        float(extent) * float(parameters.path_cluster_tolerance_ratio),
    )
    minimum_support = max(
        1,
        int(np.ceil(section_count * parameters.minimum_path_support_ratio)),
    )
    by_section = {
        section_index: tuple(
            sample for sample in samples if sample.section_index == section_index
        )
        for section_index in sorted({sample.section_index for sample in samples})
    }
    tracks: dict[
        tuple[tuple[int, float, float], ...],
        tuple[_LocalPathSample, ...],
    ] = {}

    def track_key(
        track: tuple[_LocalPathSample, ...],
    ) -> tuple[tuple[int, float, float], ...]:
        return tuple(
            (
                sample.section_index,
                sample.position.minimum,
                sample.position.maximum,
            )
            for sample in track
        )

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

    active_tracks: tuple[tuple[_LocalPathSample, ...], ...] = ()
    for section_index in range(section_count):
        section_samples = by_section.get(section_index, ())
        next_tracks: dict[
            tuple[tuple[int, float, float], ...],
            tuple[_LocalPathSample, ...],
        ] = {}
        for track in active_tracks:
            gap = section_index - track[-1].section_index
            if gap <= 0 or gap > parameters.maximum_path_section_gap + 1:
                continue
            if section_samples:
                closest = min(
                    section_samples,
                    key=lambda sample: abs(
                        sample.position.midpoint
                        - prediction(
                            track,
                            sample.orthogonal_interval.midpoint,
                        )
                    ),
                )
                residual = abs(
                    closest.position.midpoint
                    - prediction(
                        track,
                        closest.orthogonal_interval.midpoint,
                    )
                )
                if residual <= tolerance * float(gap):
                    extended = (*track, closest)
                    next_tracks[track_key(extended)] = extended
                    tracks[track_key(extended)] = extended
                    continue
            if gap <= parameters.maximum_path_section_gap:
                next_tracks[track_key(track)] = track
        for sample in section_samples:
            track = (sample,)
            next_tracks[track_key(track)] = track
            tracks[track_key(track)] = track
        active_tracks = tuple(next_tracks.values())

    def fit_residual(cluster: tuple[_LocalPathSample, ...]) -> float:
        coordinates = tuple(
            item.orthogonal_interval.midpoint for item in cluster
        )
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

    supported = tuple(
        track for track in tracks.values() if len(track) >= minimum_support
    )
    ranked = tuple(
        sorted(
            supported,
            key=lambda cluster: (
                -len(cluster),
                fit_residual(cluster),
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
    return (
        tuple(canonical[: parameters.maximum_paths_per_axis]),
        len(canonical) > parameters.maximum_paths_per_axis,
    )


def _provenance(
    kind: BoundaryKind,
    axis: BoundaryAxis,
    path_index: int,
    scan_origin: BoundarySide | None,
) -> MeasurementProvenance:
    source = f"{kind.value}:{axis.value}:{path_index}"
    if scan_origin is not None:
        source = f"{source}:scan_from_{scan_origin.value}"
    return MeasurementProvenance(
        root_measurement=MeasurementIdentity.BOUNDARY_PATHS,
        observation_id=ObservationId(source),
        dependencies=(
            MeasurementIdentity.GRAY_WORK,
            MeasurementIdentity.IMAGE_MEASUREMENT_STATISTICS,
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
    parameters: BoundaryPathParameters,
    *,
    scan_origin: BoundarySide | None = None,
) -> tuple[tuple[GrayBoundaryPathObservation, ...], bool]:
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
    )
    clusters, path_budget_exhausted = _cluster_samples(
        local_samples,
        extent,
        len(profiles),
        parameters,
    )
    paths: list[GrayBoundaryPathObservation] = []
    for path_index, cluster in enumerate(clusters):
        samples = tuple(
            BoundaryPathSample(item.orthogonal_interval, item.position)
            for item in cluster
        )
        provenance = _provenance(kind, axis, path_index, scan_origin)
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
    return tuple(paths), path_budget_exhausted


def _holder_boundary(
    side: BoundarySide,
    candidates: tuple[GrayBoundaryPathObservation, ...],
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
    shared = PixelInterval.common_intersection(tuple(path.position for path in best))
    if shared is None:
        return None
    return HolderBoundaryObservation(side, shared, best)


def boundary_measurements(
    gray: np.ndarray,
    statistics: ImageMeasurementStatistics,
    parameters: BoundaryPathParameters,
) -> BoundaryMeasurementSet:
    if gray.ndim != 2 or not gray.size:
        raise ValueError("boundary measurement requires non-empty grayscale")
    texture = _texture_image(gray)
    long_axis_profiles = _cross_section_profiles(
        gray,
        texture,
        scan_axis=1,
        parameters=parameters,
    )
    short_axis_profiles = _cross_section_profiles(
        gray,
        texture,
        scan_axis=0,
        parameters=parameters,
    )
    profiles_by_axis = {
        BoundaryAxis.LONG: long_axis_profiles,
        BoundaryAxis.SHORT: short_axis_profiles,
    }
    generic_paths: list[GrayBoundaryPathObservation] = []
    measurement_budget_exhausted = False
    for axis, profiles in profiles_by_axis.items():
        for kind in (BoundaryKind.TONAL_TRANSITION, BoundaryKind.TEXTURE_TRANSITION):
            paths, budget_exhausted = _paths_for_axis(
                axis,
                profiles,
                statistics,
                kind,
                parameters,
            )
            generic_paths.extend(paths)
            measurement_budget_exhausted = bool(
                measurement_budget_exhausted or budget_exhausted
            )
    edge_measurements_by_side = {
        side: _paths_for_axis(
            boundary_axis_for_side(side),
            profiles_by_axis[boundary_axis_for_side(side)],
            statistics,
            BoundaryKind.EDGE_ADJACENT_TRANSITION,
            parameters,
            scan_origin=side,
        )
        for side in BoundarySide
    }
    edge_paths_by_side = {
        side: paths
        for side, (paths, _) in edge_measurements_by_side.items()
    }
    measurement_budget_exhausted = bool(
        measurement_budget_exhausted
        or any(exhausted for _, exhausted in edge_measurements_by_side.values())
    )
    edge_paths = tuple(
        path for paths in edge_paths_by_side.values() for path in paths
    )
    raw_paths = (*generic_paths, *edge_paths)
    holder_boundaries = tuple(
        boundary
        for side, paths in edge_paths_by_side.items()
        if (boundary := _holder_boundary(side, paths)) is not None
    )
    height, width = gray.shape
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
        measurement_budget_exhausted=measurement_budget_exhausted,
    )
