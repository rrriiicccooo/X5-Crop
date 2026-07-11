from __future__ import annotations

import numpy as np

from ...domain import BoundaryObservation, MeasurementProvenance, PixelInterval
from ...geometry.detection_parameters import BoundaryDetectionParameters
from ...utils import clamp_int, runs_from_mask
from .boundary import canvas_boundary_observations


BoundaryObservationGroup = tuple[str, tuple[BoundaryObservation, ...]]


def _first_footprint_index(holder_mask: np.ndarray, min_run: int) -> int | None:
    if holder_mask.size == 0:
        return None
    footprint = ~holder_mask.astype(bool)
    for start, end in runs_from_mask(footprint):
        if end - start >= min_run:
            return int(start)
    return None


def _edge_holder_transition(holder_mask: np.ndarray, min_run: int) -> int | None:
    holder = holder_mask.astype(bool)
    if holder.size == 0 or not bool(holder[0]):
        return None
    non_holder = np.flatnonzero(~holder)
    if not non_holder.size:
        return None
    transition = int(non_holder[0])
    return transition if transition >= int(min_run) else None


def _position_interval(
    side: str,
    position: int,
    gray: np.ndarray,
    parameters: BoundaryDetectionParameters,
) -> PixelInterval:
    axis_length = gray.shape[1] if side in {"leading", "trailing"} else gray.shape[0]
    uncertainty = max(
        int(parameters.white_margin_min),
        int(round(float(axis_length) * float(parameters.white_margin_ratio))),
    )
    return PixelInterval(
        max(0.0, float(position - uncertainty)),
        min(float(axis_length), float(position + uncertainty)),
    )


def _boundary_observation(
    side: str,
    position: int,
    kind: str,
    gray: np.ndarray,
    parameters: BoundaryDetectionParameters,
) -> BoundaryObservation:
    return BoundaryObservation(
        side=side,
        position=_position_interval(side, position, gray, parameters),
        kind=kind,
        provenance=MeasurementProvenance(
            root_measurement="holder_boundary_profile",
            source=kind,
            dependencies=("gray_work",),
            boundary_anchors=(side,),
        ),
    )


def _observations_from_holder_profiles(
    gray: np.ndarray,
    col_holder: np.ndarray,
    row_holder: np.ndarray,
    parameters: BoundaryDetectionParameters,
    min_run_x: int,
    min_run_y: int,
) -> tuple[BoundaryObservation, ...]:
    width = gray.shape[1]
    height = gray.shape[0]
    transitions = (
        ("leading", _edge_holder_transition(col_holder, min_run_x)),
        (
            "trailing",
            (
                None
                if (offset := _edge_holder_transition(col_holder[::-1], min_run_x))
                is None
                else width - offset
            ),
        ),
        ("top", _edge_holder_transition(row_holder, min_run_y)),
        (
            "bottom",
            (
                None
                if (offset := _edge_holder_transition(row_holder[::-1], min_run_y))
                is None
                else height - offset
            ),
        ),
    )
    return tuple(
        _boundary_observation(
            side,
            position,
            "white_holder_transition",
            gray,
            parameters,
        )
        for side, position in transitions
        if position is not None
    )


def _observations_from_footprint(
    gray: np.ndarray,
    column_footprint: np.ndarray,
    row_footprint: np.ndarray,
    kind: str,
    parameters: BoundaryDetectionParameters,
    min_run_x: int,
    min_run_y: int,
) -> tuple[BoundaryObservation, ...]:
    width = gray.shape[1]
    height = gray.shape[0]
    leading = _first_footprint_index(~column_footprint, min_run_x)
    trailing_offset = _first_footprint_index(
        (~column_footprint)[::-1],
        min_run_x,
    )
    top = _first_footprint_index(~row_footprint, min_run_y)
    bottom_offset = _first_footprint_index((~row_footprint)[::-1], min_run_y)
    transitions = (
        ("leading", leading if leading not in {None, 0} else None),
        (
            "trailing",
            width - trailing_offset
            if trailing_offset not in {None, 0}
            else None,
        ),
        ("top", top if top not in {None, 0} else None),
        (
            "bottom",
            height - bottom_offset
            if bottom_offset not in {None, 0}
            else None,
        ),
    )
    return tuple(
        _boundary_observation(
            side,
            position,
            kind,
            gray,
            parameters,
        )
        for side, position in transitions
        if position is not None
    )


def boundary_observation_groups(
    gray: np.ndarray,
    parameters: BoundaryDetectionParameters,
) -> tuple[BoundaryObservationGroup, ...]:
    height, width = gray.shape
    min_run_x = clamp_int(
        width * parameters.white_run_ratio,
        parameters.white_run_min,
        parameters.white_run_max,
    )
    min_run_y = clamp_int(
        height * parameters.white_run_ratio,
        parameters.white_run_min,
        parameters.white_run_max,
    )
    white = gray >= int(parameters.white_light_threshold)
    white_boundaries = _observations_from_holder_profiles(
        gray,
        white.mean(axis=0) >= float(parameters.white_holder_cross_axis_min),
        white.mean(axis=1) >= float(parameters.white_holder_cross_axis_min),
        parameters,
        min_run_x,
        min_run_y,
    )
    tonal = gray < int(parameters.bw_not_white_threshold)
    tonal_boundaries = _observations_from_footprint(
        gray,
        tonal.mean(axis=0) >= float(parameters.tonal_footprint_min_fraction),
        tonal.mean(axis=1) >= float(parameters.tonal_footprint_min_fraction),
        "tonal_transition",
        parameters,
        min_run_x,
        min_run_y,
    )
    texture_boundaries = _observations_from_footprint(
        gray,
        gray.astype(np.float32).std(axis=0) / 255.0
        >= float(parameters.texture_activity_min),
        gray.astype(np.float32).std(axis=1) / 255.0
        >= float(parameters.texture_activity_min),
        "texture_transition",
        parameters,
        min_run_x,
        min_run_y,
    )
    return (
        ("white_holder", white_boundaries),
        ("tonal", tonal_boundaries),
        ("texture", texture_boundaries),
        ("full_canvas", canvas_boundary_observations(width, height)),
    )
