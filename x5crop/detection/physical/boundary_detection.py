from __future__ import annotations

from dataclasses import dataclass
from statistics import median

import numpy as np

from ...configuration.boundary import BoundaryPathParameters
from ...domain import (
    BoundaryAxis,
    BoundaryKind,
    BoundaryMeasurementSet,
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
class _LocalPathSample:
    section_index: int
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
) -> tuple[tuple[np.ndarray, np.ndarray], ...]:
    orthogonal_extent = gray.shape[0] if scan_axis == 1 else gray.shape[1]
    margin = int(round(orthogonal_extent * parameters.cross_section_margin_ratio))
    start = max(0, min(orthogonal_extent - 1, margin))
    end = max(start + 1, min(orthogonal_extent, orthogonal_extent - margin))
    edges = np.linspace(start, end, int(parameters.cross_sections) + 1)
    profiles: list[tuple[np.ndarray, np.ndarray]] = []
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
            (
                np.median(intensity_section, axis=reduction_axis).astype(np.float32),
                np.median(texture_section, axis=reduction_axis).astype(np.float32),
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
) -> tuple[tuple[PixelInterval, ...], bool]:
    if signal.size <= 1:
        return (), False
    change = np.abs(np.diff(signal, prepend=signal[:1]))
    threshold = float(np.percentile(change, parameters.change_point_percentile))
    if threshold <= 0.0:
        return (), False
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
    selected = ranked[: parameters.maximum_change_points_per_section]
    return tuple(
        PixelInterval(float(start), float(max(start + 1, end)))
        for start, end in sorted(selected)
    ), len(ranked) > parameters.maximum_change_points_per_section


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
    profiles: tuple[tuple[np.ndarray, np.ndarray], ...],
    side: BoundarySide,
    kind: BoundaryKind,
    statistics: ImageMeasurementStatistics,
    parameters: BoundaryPathParameters,
) -> tuple[tuple[_LocalPathSample, ...], bool]:
    reverse = side in {BoundarySide.TRAILING, BoundarySide.BOTTOM}
    samples: list[_LocalPathSample] = []
    budget_exhausted = False
    for section_index, (source_intensity, source_texture) in enumerate(profiles):
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
            positions, truncated = _adaptive_change_points(intensity, parameters)
            budget_exhausted = budget_exhausted or truncated
        elif kind == BoundaryKind.TEXTURE_TRANSITION:
            positions, truncated = _adaptive_change_points(texture, parameters)
            budget_exhausted = budget_exhausted or truncated
        else:
            raise ValueError(f"unsupported boundary path kind: {kind}")
        for position in positions:
            sample = _local_sample(
                section_index,
                position,
                intensity,
                texture,
                reverse,
                parameters,
            )
            if sample is not None:
                samples.append(sample)
    return tuple(samples), budget_exhausted


def _cluster_samples(
    samples: tuple[_LocalPathSample, ...],
    extent: int,
    parameters: BoundaryPathParameters,
) -> tuple[tuple[tuple[_LocalPathSample, ...], ...], bool]:
    tolerance = max(
        float(parameters.path_cluster_tolerance_min_px),
        float(extent) * float(parameters.path_cluster_tolerance_ratio),
    )
    clusters: list[list[_LocalPathSample]] = []
    for sample in sorted(samples, key=lambda item: item.position.midpoint):
        eligible = tuple(
            (abs(sample.position.midpoint - median(
                item.position.midpoint for item in cluster
            )), index)
            for index, cluster in enumerate(clusters)
            if sample.section_index not in {item.section_index for item in cluster}
            and abs(
                sample.position.midpoint
                - median(item.position.midpoint for item in cluster)
            )
            <= tolerance
        )
        if eligible:
            clusters[min(eligible)[1]].append(sample)
        else:
            clusters.append([sample])
    minimum_support = max(
        1,
        int(np.ceil(parameters.cross_sections * parameters.minimum_path_support_ratio)),
    )
    supported = tuple(
        tuple(cluster)
        for cluster in clusters
        if len({item.section_index for item in cluster}) >= minimum_support
    )
    ranked = tuple(
        sorted(
            supported,
            key=lambda cluster: (
                -len(cluster),
                max(item.position.maximum for item in cluster)
                - min(item.position.minimum for item in cluster),
                median(item.position.midpoint for item in cluster),
            ),
        )
    )
    return (
        ranked[: parameters.maximum_paths_per_axis],
        len(ranked) > parameters.maximum_paths_per_axis,
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
    profiles: tuple[tuple[np.ndarray, np.ndarray], ...],
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
    extent = len(profiles[0][0]) if profiles else 0
    local_samples, change_point_budget_exhausted = _local_samples_for_kind(
        profiles,
        oriented_side,
        kind,
        statistics,
        parameters,
    )
    clusters, path_budget_exhausted = _cluster_samples(
        local_samples,
        extent,
        parameters,
    )
    paths: list[GrayBoundaryPathObservation] = []
    for path_index, cluster in enumerate(clusters):
        local_positions = tuple(item.position for item in cluster)
        position = PixelInterval(
            min(item.minimum for item in local_positions),
            max(item.maximum for item in local_positions),
        )
        provenance = _provenance(kind, axis, path_index, scan_origin)
        support_ratio = len(cluster) / float(len(profiles))
        paths.append(
            GrayBoundaryPathObservation(
                axis=axis,
                position=position,
                kind=kind,
                local_positions=local_positions,
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
    return tuple(paths), bool(
        change_point_budget_exhausted or path_budget_exhausted
    )


def _holder_boundary(
    side: BoundarySide,
    candidates: tuple[GrayBoundaryPathObservation, ...],
) -> HolderBoundaryObservation | None:
    if not candidates:
        return None
    wrapped = tuple(
        HolderBoundaryObservation(side, path.position, path) for path in candidates
    )
    best_support = max(item.outer_appearance.spatial_continuity for item in wrapped)
    best = tuple(
        item
        for item in wrapped
        if item.outer_appearance.spatial_continuity == best_support
    )
    if len(best) > 1 and any(
        not best[0].position.intersects(item.position) for item in best[1:]
    ):
        return None
    return min(
        best,
        key=lambda item: item.position.maximum - item.position.minimum,
    )


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
