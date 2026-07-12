from __future__ import annotations

import numpy as np

from ...configuration.boundary import BoundaryObservationParameters
from ...domain import BoundaryObservation, MeasurementProvenance, PixelInterval
from ...image.statistics import ImageMeasurementStatistics
from ...utils import runs_from_mask
from .boundary import canvas_boundary_observations


BoundaryObservationGroup = tuple[str, tuple[BoundaryObservation, ...]]


def _axis_profiles(gray: np.ndarray, axis: int) -> tuple[np.ndarray, np.ndarray]:
    data = gray.astype(np.float32, copy=False)
    gx = np.abs(np.diff(data, axis=1, prepend=data[:, :1]))
    gy = np.abs(np.diff(data, axis=0, prepend=data[:1, :]))
    texture = gx + gy
    reduction_axis = 0 if axis == 1 else 1
    return data.mean(axis=reduction_axis), texture.mean(axis=reduction_axis)


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
    parameters: BoundaryObservationParameters,
) -> tuple[np.ndarray, np.ndarray]:
    edge_reference = float(np.median((intensity[0], intensity[-1])))
    deviation = np.abs(intensity - edge_reference)
    tolerance = float(
        np.percentile(deviation, parameters.holder_reference_percentile)
    )
    holder = (deviation <= tolerance) & (texture <= float(texture_limit))
    tonal_change = deviation > tolerance
    return holder, tonal_change


def _change_point_interval(
    profile: np.ndarray,
    position: int,
    parameters: BoundaryObservationParameters,
) -> PixelInterval:
    if profile.size <= 1:
        return PixelInterval.exact(float(position))
    change = np.abs(np.diff(profile, prepend=profile[:1]))
    threshold = float(
        np.percentile(change, parameters.change_point_percentile)
    )
    if threshold <= 0.0:
        return PixelInterval.exact(float(position))
    runs = tuple(runs_from_mask(change >= threshold))
    if not runs:
        return PixelInterval.exact(float(position))
    start, end = min(
        runs,
        key=lambda run: abs(0.5 * (run[0] + run[1]) - float(position)),
    )
    return PixelInterval(float(start), float(max(start + 1, end)))


def _observation(
    side: str,
    position: int,
    kind: str,
    profile: np.ndarray,
    parameters: BoundaryObservationParameters,
) -> BoundaryObservation:
    return BoundaryObservation(
        side=side,
        position=_change_point_interval(profile, position, parameters),
        kind=kind,
        provenance=MeasurementProvenance(
            root_measurement="holder_boundary_profile",
            source=kind,
            dependencies=("gray_work", "image_measurement_statistics"),
            boundary_anchors=(side,),
        ),
    )


def _four_side_observations(
    column_mask: np.ndarray,
    row_mask: np.ndarray,
    column_profile: np.ndarray,
    row_profile: np.ndarray,
    kind: str,
    *,
    holder_transition: bool,
    parameters: BoundaryObservationParameters,
) -> tuple[BoundaryObservation, ...]:
    find = _edge_transition if holder_transition else _first_run
    width = int(column_mask.size)
    height = int(row_mask.size)
    leading = find(column_mask)
    trailing_offset = find(column_mask[::-1])
    top = find(row_mask)
    bottom_offset = find(row_mask[::-1])
    values = (
        ("leading", leading, column_profile),
        (
            "trailing",
            None if trailing_offset is None else width - trailing_offset,
            column_profile,
        ),
        ("top", top, row_profile),
        (
            "bottom",
            None if bottom_offset is None else height - bottom_offset,
            row_profile,
        ),
    )
    return tuple(
        _observation(side, int(position), kind, profile, parameters)
        for side, position, profile in values
        if position not in {None, 0, len(profile)}
    )


def boundary_observation_groups(
    gray: np.ndarray,
    statistics: ImageMeasurementStatistics,
    parameters: BoundaryObservationParameters,
) -> tuple[BoundaryObservationGroup, ...]:
    column_intensity, column_texture = _axis_profiles(gray, axis=1)
    row_intensity, row_texture = _axis_profiles(gray, axis=0)
    texture_limit = statistics.edge_texture_limit
    column_holder, column_tonal = _reference_masks(
        column_intensity,
        column_texture,
        texture_limit,
        parameters,
    )
    row_holder, row_tonal = _reference_masks(
        row_intensity,
        row_texture,
        texture_limit,
        parameters,
    )
    column_texture_change = column_texture > texture_limit
    row_texture_change = row_texture > texture_limit
    edge_is_white_holder = bool(
        statistics.intensity_low < statistics.edge_intensity_quantiles[1]
        and statistics.edge_intensity_quantiles[1] >= statistics.intensity_high
    )
    white_holder = (
        _four_side_observations(
            column_holder,
            row_holder,
            column_intensity,
            row_intensity,
            "white_holder_transition",
            holder_transition=True,
            parameters=parameters,
        )
        if edge_is_white_holder
        else ()
    )
    tonal = _four_side_observations(
        column_tonal,
        row_tonal,
        column_intensity,
        row_intensity,
        "tonal_transition",
        holder_transition=False,
        parameters=parameters,
    )
    texture = _four_side_observations(
        column_texture_change,
        row_texture_change,
        column_texture,
        row_texture,
        "texture_transition",
        holder_transition=False,
        parameters=parameters,
    )
    return (
        ("white_holder", white_holder),
        ("tonal", tonal),
        ("texture", texture),
        ("full_canvas", canvas_boundary_observations(gray.shape[1], gray.shape[0])),
    )
