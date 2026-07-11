from __future__ import annotations

import numpy as np

from ....domain import MeasurementProvenance
from ....geometry.detection_parameters import OuterBoxDetectionParameters
from ....utils import clamp_int, runs_from_mask
from ..boundary import BoundaryObservation, canvas_boundary_observations
from ..intervals import PixelInterval


BoundaryObservationGroup = tuple[str, tuple[BoundaryObservation, ...]]


def _first_footprint_index(holder_mask: np.ndarray, min_run: int) -> int:
    if holder_mask.size == 0:
        return 0
    footprint = ~holder_mask.astype(bool)
    for start, end in runs_from_mask(footprint):
        if end - start >= min_run:
            return int(start)
    indexes = np.flatnonzero(footprint)
    return int(indexes[0]) if indexes.size else 0


def _position_interval(
    side: str,
    position: int,
    gray: np.ndarray,
    parameters: OuterBoxDetectionParameters,
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
    parameters: OuterBoxDetectionParameters,
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
    parameters: OuterBoxDetectionParameters,
    min_run_x: int,
    min_run_y: int,
) -> tuple[BoundaryObservation, ...]:
    width = gray.shape[1]
    height = gray.shape[0]
    return (
        _boundary_observation(
            "leading",
            _first_footprint_index(col_holder, min_run_x),
            "white_holder_transition",
            gray,
            parameters,
        ),
        _boundary_observation(
            "trailing",
            width - _first_footprint_index(col_holder[::-1], min_run_x),
            "white_holder_transition",
            gray,
            parameters,
        ),
        _boundary_observation(
            "top",
            _first_footprint_index(row_holder, min_run_y),
            "white_holder_transition",
            gray,
            parameters,
        ),
        _boundary_observation(
            "bottom",
            height - _first_footprint_index(row_holder[::-1], min_run_y),
            "white_holder_transition",
            gray,
            parameters,
        ),
    )


def _observations_from_footprint(
    gray: np.ndarray,
    column_footprint: np.ndarray,
    row_footprint: np.ndarray,
    kind: str,
    parameters: OuterBoxDetectionParameters,
    min_run_x: int,
    min_run_y: int,
) -> tuple[BoundaryObservation, ...]:
    width = gray.shape[1]
    height = gray.shape[0]
    return (
        _boundary_observation(
            "leading",
            _first_footprint_index(~column_footprint, min_run_x),
            kind,
            gray,
            parameters,
        ),
        _boundary_observation(
            "trailing",
            width - _first_footprint_index((~column_footprint)[::-1], min_run_x),
            kind,
            gray,
            parameters,
        ),
        _boundary_observation(
            "top",
            _first_footprint_index(~row_footprint, min_run_y),
            kind,
            gray,
            parameters,
        ),
        _boundary_observation(
            "bottom",
            height - _first_footprint_index((~row_footprint)[::-1], min_run_y),
            kind,
            gray,
            parameters,
        ),
    )


def boundary_observation_groups(
    gray: np.ndarray,
    parameters: OuterBoxDetectionParameters,
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
        white.mean(axis=0),
        white.mean(axis=1),
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
