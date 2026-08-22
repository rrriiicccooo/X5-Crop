from __future__ import annotations

from dataclasses import replace
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from x5crop.domain import Box
from x5crop.domain import EvidenceState
from x5crop.detection.final.deskew import assess_output_deskew
from x5crop.detection.output_deskew import (
    DeskewEdgeFit,
    LightweightDeskewObservation,
)
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.output_model import (
    BoundaryProtectionFact,
    JointPlacementEnvelope,
    OutputBoundaryUse,
    OutputFootprint,
)
from x5crop.export.crops import write_crops
from x5crop.geometry.affine import (
    AFFINE_OUTPUT_RASTER_GUARD_PX,
    AffineCoordinateTransform,
)
from x5crop.geometry.convex import (
    convex_hull,
    mapped_half_open_box,
)
from x5crop.image.transforms import sample_affine_roi
from x5crop.io.model import ImageProfile, TiffExtraTag, TiffMetadata
from x5crop.io.orientation import orientation_mapping
from x5crop.io.tiff import read_tiff


def make_deskew_observation(
    angle_degrees: float,
    *,
    fit_angle_degrees: float | None = None,
) -> LightweightDeskewObservation:
    fit_angle = angle_degrees if fit_angle_degrees is None else fit_angle_degrees
    slope = math.tan(math.radians(fit_angle))
    fit = DeskewEdgeFit(
        slope=slope,
        angle_degrees=fit_angle,
        sample_count=8,
        inlier_count=8,
        median_residual_px=0.25,
    )
    return LightweightDeskewObservation(
        state=EvidenceState.SUPPORTED,
        angle_degrees=angle_degrees,
        top_fit=fit,
        bottom_fit=fit,
        sample_trace_count=8,
        skip_reason=None,
    )


def sampling_footprint(authority: Box) -> OutputFootprint:
    polygon = (
        (float(authority.left), float(authority.top)),
        (float(authority.right - 1), float(authority.top)),
        (float(authority.right - 1), float(authority.bottom - 1)),
        (float(authority.left), float(authority.bottom - 1)),
    )
    return OutputFootprint(
        geometry_id="sampling-fixture",
        envelope=JointPlacementEnvelope(
            placement_id="sampling-fixture",
            projection_id="sampling-fixture",
            lane_id="lane:0",
            lane_ordinal=1,
            boundary_use=OutputBoundaryUse.APERTURE_PAIR,
            canonical_source_footprint=polygon,
            feasible_source_footprint=polygon,
            extreme_evaluation_count=1,
        ),
        required_source_footprint=polygon,
        boundary_protections=tuple(
            BoundaryProtectionFact(role, 0.0, 0.0, 0.0, 0.0)
            for role in (
                BoundaryRole.START,
                BoundaryRole.END,
                BoundaryRole.TOP,
                BoundaryRole.BOTTOM,
            )
        ),
        saturation_facts=(),
        sampling_authority_box=authority,
        authority_profile_id="sampling-fixture",
    )


# Affine and TIFF contracts share deterministic raster fixtures.
__all__ = tuple(name for name in globals() if not name.startswith("__"))
