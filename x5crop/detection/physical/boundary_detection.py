from __future__ import annotations

import numpy as np

from ...configuration.boundary import BoundaryObservationParameters
from ...domain import (
    BoundaryObservation,
    MeasurementIdentity,
    MeasurementProvenance,
    PixelInterval,
)
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
    return (
        np.median(data, axis=reduction_axis),
        np.median(texture, axis=reduction_axis),
    )


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
    edge_reference = float(intensity[0])
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
        key=lambda run: abs(float(sum(run)) / float(len(run)) - float(position)),
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
            root_measurement=MeasurementIdentity.HOLDER_BOUNDARY_PROFILE,
            source=kind,
            dependencies=(
                MeasurementIdentity.GRAY_WORK,
                MeasurementIdentity.IMAGE_MEASUREMENT_STATISTICS,
            ),
            boundary_anchors=(side,),
        ),
    )


def _side_observations(
    column_intensity: np.ndarray,
    column_texture: np.ndarray,
    row_intensity: np.ndarray,
    row_texture: np.ndarray,
    statistics: ImageMeasurementStatistics,
    kind: str,
    parameters: BoundaryObservationParameters,
) -> tuple[BoundaryObservation, ...]:
    profiles = (
        ("leading", column_intensity, column_texture, False),
        ("trailing", column_intensity, column_texture, True),
        ("top", row_intensity, row_texture, False),
        ("bottom", row_intensity, row_texture, True),
    )
    observations: list[BoundaryObservation] = []
    for side, intensity, texture, reverse in profiles:
        oriented_intensity = intensity[::-1] if reverse else intensity
        oriented_texture = texture[::-1] if reverse else texture
        holder, tonal = _reference_masks(
            oriented_intensity,
            oriented_texture,
            statistics.edge_texture_limit,
            parameters,
        )
        if kind == "white_holder_transition":
            if float(oriented_intensity[0]) < float(statistics.intensity_high):
                continue
            offset = _edge_transition(holder)
        elif kind == "tonal_transition":
            offset = _first_run(tonal)
        elif kind == "texture_transition":
            offset = _first_run(
                oriented_texture > float(statistics.edge_texture_limit)
            )
        else:
            raise ValueError(f"unsupported boundary observation kind: {kind}")
        position = (
            None
            if offset is None
            else int(intensity.size) - offset
            if reverse
            else offset
        )
        if position in {None, 0, len(intensity)}:
            continue
        observations.append(
            _observation(
                side,
                int(position),
                kind,
                intensity,
                parameters,
            )
        )
    return tuple(observations)


def boundary_observation_groups(
    gray: np.ndarray,
    statistics: ImageMeasurementStatistics,
    parameters: BoundaryObservationParameters,
) -> tuple[BoundaryObservationGroup, ...]:
    column_intensity, column_texture = _axis_profiles(gray, axis=1)
    row_intensity, row_texture = _axis_profiles(gray, axis=0)
    white_holder = _side_observations(
        column_intensity,
        column_texture,
        row_intensity,
        row_texture,
        statistics,
        "white_holder_transition",
        parameters,
    )
    tonal = _side_observations(
        column_intensity,
        column_texture,
        row_intensity,
        row_texture,
        statistics,
        "tonal_transition",
        parameters,
    )
    texture = _side_observations(
        column_intensity,
        column_texture,
        row_intensity,
        row_texture,
        statistics,
        "texture_transition",
        parameters,
    )
    return (
        ("white_holder", white_holder),
        ("tonal", tonal),
        ("texture", texture),
        ("full_canvas", canvas_boundary_observations(gray.shape[1], gray.shape[0])),
    )
