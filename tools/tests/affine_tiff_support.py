from __future__ import annotations

from dataclasses import replace
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from x5crop.domain import Box
from x5crop.domain import (
    EvidenceState,
    FiniteInterval,
    ObservationId,
)
from x5crop.detection.output_geometry import (
    SharedStripDirectionResolution,
    output_transform_assessment,
)
from x5crop.detection.photo_geometry.line_observations import (
    PhotoBoundaryObservation,
    RobustLineFitReceipt,
    SourceCoordinateLine,
)
from x5crop.detection.photo_geometry.model import BoundaryAxis, BoundaryRole
from x5crop.detection.photo_geometry.output_model import SharedStripDirection
from x5crop.export.crops import write_crops
from x5crop.geometry.affine import (
    AFFINE_OUTPUT_RASTER_GUARD_PX,
    AffineCoordinateTransform,
)
from x5crop.geometry.convex import (
    clip_convex_polygon_to_box,
    convex_hull,
    mapped_half_open_box,
)
from x5crop.image.transforms import sample_affine_roi
from x5crop.io.model import ImageProfile, TiffExtraTag, TiffMetadata
from x5crop.io.orientation import orientation_mapping
from x5crop.io.tiff import read_tiff


def make_angle_observation(
    identity: str,
    angle_minimum: float,
    angle_maximum: float,
    *,
    role: BoundaryRole = BoundaryRole.TOP,
) -> PhotoBoundaryObservation:
    observation_id = ObservationId(identity)
    return PhotoBoundaryObservation(
        observation_id=observation_id,
        role=role,
        line=SourceCoordinateLine(
            normal_x=0.0,
            normal_y=1.0,
            offset_px=5.0,
            support_projection_px=FiniteInterval(0.0, 20.0),
            source_axis_long=BoundaryAxis.X,
        ),
        offset_interval_px=FiniteInterval(4.5, 5.5),
        fit_residual_px=0.1,
        angle_interval_degrees=FiniteInterval(
            angle_minimum,
            angle_maximum,
        ),
        trace_support_count=8,
        queried_trace_count=8,
        independent_support_region_count=3,
        continuous_support_fraction=1.0,
        transition_ids=(ObservationId(f"{identity}:transition"),),
        fit_receipt=RobustLineFitReceipt(
            method="scipy_least_squares_huber",
            converged=True,
            status=1,
            evaluation_count=1,
            cost=0.0,
            optimality=0.0,
        ),
    )


def make_transform_assessment(
    observations: tuple[PhotoBoundaryObservation, ...],
):
    cross_observations = tuple(
        item
        for item in observations
        if item.role in {BoundaryRole.TOP, BoundaryRole.BOTTOM}
    )
    minimum = max(
        item.angle_interval_degrees.minimum for item in cross_observations
    )
    maximum = min(
        item.angle_interval_degrees.maximum for item in cross_observations
    )
    if maximum < minimum:
        resolution = SharedStripDirectionResolution(
            direction=None,
            state=EvidenceState.UNAVAILABLE,
            named_gap="selected_direction_unavailable",
        )
    else:
        interval = FiniteInterval(
            min(
                item.angle_interval_degrees.minimum
                for item in cross_observations
            ),
            max(
                item.angle_interval_degrees.maximum
                for item in cross_observations
            ),
        )
        estimate = 0.0 if interval.contains(0.0) else interval.center
        resolution = SharedStripDirectionResolution(
            direction=SharedStripDirection(
                direction_id="test:selected-direction",
                selected_observation_ids=tuple(
                    item.observation_id for item in cross_observations
                ),
                full_angle_interval_degrees=interval,
                observed_angle_interval_degrees=interval,
                canonical_angle_degrees=min(
                    interval.maximum,
                    max(interval.minimum, estimate),
                ),
            ),
            state=EvidenceState.SUPPORTED,
            named_gap=None,
        )
    return output_transform_assessment(
        resolution,
        layout="horizontal",
        source_width=100,
        source_height=40,
    )

# Affine and TIFF contracts share deterministic raster fixtures.
__all__ = tuple(name for name in globals() if not name.startswith("__"))
