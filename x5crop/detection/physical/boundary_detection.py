from __future__ import annotations

from statistics import median

import numpy as np

from ...configuration.boundary import BoundaryPathParameters
from ...domain import (
    BoundaryKind,
    BoundaryPathGroup,
    BoundaryPathObservation,
    BoundaryPathSource,
    BoundarySide,
    GrayAppearanceObservation,
    gray_intensity_tail,
    MeasurementIdentity,
    MeasurementProvenance,
    PixelInterval,
)
from ...image.statistics import ImageMeasurementStatistics
from ...utils import runs_from_mask
from .boundary import canvas_boundary_paths


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


def _first_run(mask: np.ndarray) -> int | None:
    return next((int(start) for start, end in runs_from_mask(mask) if end > start), None)


def _edge_transition(holder_mask: np.ndarray) -> int | None:
    holder = holder_mask.astype(bool)
    if not holder.size or not bool(holder[0]):
        return None
    non_holder = np.flatnonzero(~holder)
    return None if not non_holder.size else int(non_holder[0])


def _reference_masks(
    intensity: np.ndarray,
    texture: np.ndarray,
    texture_limit: float,
    parameters: BoundaryPathParameters,
) -> tuple[np.ndarray, np.ndarray]:
    edge_reference = float(intensity[0])
    deviation = np.abs(intensity - edge_reference)
    tolerance = float(
        np.percentile(deviation, parameters.holder_reference_percentile)
    )
    holder = (deviation <= tolerance) & (texture <= float(texture_limit))
    return holder, deviation > tolerance


def _change_point_interval(
    profile: np.ndarray,
    position: int,
    parameters: BoundaryPathParameters,
) -> PixelInterval:
    if profile.size <= 1:
        return PixelInterval.exact(float(position))
    change = np.abs(np.diff(profile, prepend=profile[:1]))
    threshold = float(np.percentile(change, parameters.change_point_percentile))
    if threshold <= 0.0:
        return PixelInterval.exact(float(position))
    runs = tuple(runs_from_mask(change >= threshold))
    if not runs:
        return PixelInterval.exact(float(position))
    start, end = min(
        runs,
        key=lambda run: abs(float(sum(run)) / float(len(run)) - float(position)),
    )
    return PixelInterval(float(start), float(max(start + 1, end)))


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


def _provenance(kind: BoundaryKind, side: BoundarySide) -> MeasurementProvenance:
    return MeasurementProvenance(
        root_measurement=MeasurementIdentity.HOLDER_BOUNDARY_PROFILE,
        source=kind.value,
        dependencies=(
            MeasurementIdentity.GRAY_WORK,
            MeasurementIdentity.IMAGE_MEASUREMENT_STATISTICS,
        ),
        boundary_anchors=(side.value,),
    )


def _appearance_observation(
    intensities: list[float],
    mads: list[float],
    textures: list[float],
    gradients: list[float],
    support_ratio: float,
    provenance: MeasurementProvenance,
    statistics: ImageMeasurementStatistics,
) -> GrayAppearanceObservation:
    intensity_median = float(median(intensities))
    return GrayAppearanceObservation(
        intensity_median=intensity_median,
        intensity_mad=float(median(mads)),
        texture_median=float(median(textures)),
        gradient_median=float(median(gradients)),
        spatial_continuity=float(support_ratio),
        intensity_tail=gray_intensity_tail(
            intensity_median,
            statistics.intensity_low,
            statistics.intensity_high,
        ),
        provenance=provenance,
    )


def _path_for_side(
    side: BoundarySide,
    profiles: tuple[tuple[np.ndarray, np.ndarray], ...],
    statistics: ImageMeasurementStatistics,
    kind: BoundaryKind,
    parameters: BoundaryPathParameters,
) -> BoundaryPathObservation | None:
    reverse = side in {BoundarySide.TRAILING, BoundarySide.BOTTOM}
    positions: list[PixelInterval] = []
    outer_intensity_measurements: list[float] = []
    outer_mad: list[float] = []
    outer_texture_measurements: list[float] = []
    outer_gradient_measurements: list[float] = []
    inner_intensity: list[float] = []
    inner_mad: list[float] = []
    inner_texture: list[float] = []
    inner_gradient: list[float] = []

    for intensity, texture in profiles:
        oriented_intensity = intensity[::-1] if reverse else intensity
        oriented_texture = texture[::-1] if reverse else texture
        holder, tonal = _reference_masks(
            oriented_intensity,
            oriented_texture,
            statistics.edge_texture_limit,
            parameters,
        )
        if kind == BoundaryKind.HOLDER_BOUNDARY_TRANSITION:
            if oriented_texture[0] > float(statistics.edge_texture_limit):
                continue
            offset = _first_run(
                oriented_texture > float(statistics.edge_texture_limit)
            )
            if offset is None:
                offset = _edge_transition(holder)
        elif kind == BoundaryKind.TONAL_TRANSITION:
            offset = _first_run(tonal)
        elif kind == BoundaryKind.TEXTURE_TRANSITION:
            offset = _first_run(
                oriented_texture > float(statistics.edge_texture_limit)
            )
        else:
            raise ValueError(f"unsupported boundary path kind: {kind}")
        if offset in {None, 0, len(oriented_intensity)}:
            continue
        oriented_interval = _change_point_interval(
            oriented_intensity,
            int(offset),
            parameters,
        )
        positions.append(
            _source_interval(oriented_interval, len(oriented_intensity), reverse)
        )
        inner_end = min(
            len(oriented_texture),
            int(offset)
            + max(1, int(round(len(oriented_texture) * parameters.inner_sample_ratio))),
        )
        inner_intensity_values = oriented_intensity[int(offset):inner_end]
        inner_texture_values = oriented_texture[int(offset):inner_end]
        inner_center = float(np.median(inner_intensity_values))
        inner_intensity.append(inner_center)
        inner_mad.append(
            float(np.median(np.abs(inner_intensity_values - inner_center)))
        )
        inner_texture.append(float(np.median(inner_texture_values)))
        inner_gradient.append(
            float(
                np.median(
                    np.abs(
                        np.diff(
                            inner_intensity_values,
                            prepend=inner_intensity_values[:1],
                        )
                    )
                )
            )
        )
        outer_intensity = oriented_intensity[: int(offset)]
        outer_texture = oriented_texture[: int(offset)]
        outer_gradient = np.abs(
            np.diff(outer_intensity, prepend=outer_intensity[:1])
        )
        center = float(np.median(outer_intensity))
        outer_intensity_measurements.append(center)
        outer_mad.append(float(np.median(np.abs(outer_intensity - center))))
        outer_texture_measurements.append(float(np.median(outer_texture)))
        outer_gradient_measurements.append(float(np.median(outer_gradient)))

    support_ratio = len(positions) / float(len(profiles)) if profiles else 0.0
    if not positions or support_ratio < parameters.minimum_path_support_ratio:
        return None
    position = PixelInterval(
        min(item.minimum for item in positions),
        max(item.maximum for item in positions),
    )
    provenance = _provenance(kind, side)
    outer_appearance = _appearance_observation(
        outer_intensity_measurements,
        outer_mad,
        outer_texture_measurements,
        outer_gradient_measurements,
        support_ratio,
        provenance,
        statistics,
    )
    inner_appearance = _appearance_observation(
        inner_intensity,
        inner_mad,
        inner_texture,
        inner_gradient,
        support_ratio,
        provenance,
        statistics,
    )
    return BoundaryPathObservation(
        side=side,
        position=position,
        kind=kind,
        local_positions=tuple(positions),
        outer_appearance=outer_appearance,
        inner_appearance=inner_appearance,
        provenance=provenance,
    )


def _paths_for_kind(
    gray: np.ndarray,
    texture: np.ndarray,
    statistics: ImageMeasurementStatistics,
    kind: BoundaryKind,
    parameters: BoundaryPathParameters,
) -> tuple[BoundaryPathObservation, ...]:
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
    paths = tuple(
        path
        for side, profiles in (
            (BoundarySide.LEADING, long_axis_profiles),
            (BoundarySide.TRAILING, long_axis_profiles),
            (BoundarySide.TOP, short_axis_profiles),
            (BoundarySide.BOTTOM, short_axis_profiles),
        )
        if (
            path := _path_for_side(
                side,
                profiles,
                statistics,
                kind,
                parameters,
            )
        )
        is not None
    )
    return paths


def boundary_path_groups(
    gray: np.ndarray,
    statistics: ImageMeasurementStatistics,
    parameters: BoundaryPathParameters,
) -> tuple[BoundaryPathGroup, ...]:
    texture = _texture_image(gray)
    return (
        BoundaryPathGroup(
            BoundaryPathSource.HOLDER_BOUNDARY,
            _paths_for_kind(
                gray,
                texture,
                statistics,
                BoundaryKind.HOLDER_BOUNDARY_TRANSITION,
                parameters,
            ),
        ),
        BoundaryPathGroup(
            BoundaryPathSource.TONAL,
            _paths_for_kind(
                gray,
                texture,
                statistics,
                BoundaryKind.TONAL_TRANSITION,
                parameters,
            ),
        ),
        BoundaryPathGroup(
            BoundaryPathSource.TEXTURE,
            _paths_for_kind(
                gray,
                texture,
                statistics,
                BoundaryKind.TEXTURE_TRANSITION,
                parameters,
            ),
        ),
        BoundaryPathGroup(
            BoundaryPathSource.FULL_CANVAS,
            canvas_boundary_paths(gray.shape[1], gray.shape[0]),
        ),
    )
