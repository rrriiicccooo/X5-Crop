from __future__ import annotations

from dataclasses import replace
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from x5crop.domain import Box, WorkspaceExtent
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
    SequenceProjectionConstraintBasis,
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


def sampling_footprint(authority: Box, source_extent: WorkspaceExtent, *, requested=None, mandatory=None) -> OutputFootprint:
    from x5crop.detection.photo_geometry.source_geometry import SourceFixedOutputSize
    from x5crop.detection.photo_geometry.model import BoundaryAxis
    polygon = (
        (float(authority.left), float(authority.top)),
        (float(authority.right - 1), float(authority.top)),
        (float(authority.right - 1), float(authority.bottom - 1)),
        (float(authority.left), float(authority.bottom - 1)),
    )
    from x5crop.detection.photo_geometry.template_output import _saturation_facts
    from x5crop.detection.photo_geometry.output_model import sampling_authority_bounds, fixed_output_rectangle
    from x5crop.geometry.convex import clip_convex_polygon_to_bounds
    polygon = convex_hull(requested if requested is not None else polygon)
    protected = convex_hull(mandatory if mandatory is not None else polygon)
    size = SourceFixedOutputSize("sampling-fixture", (max(x for x, _ in polygon) - min(x for x, _ in polygon)) / 1.1,
                               (max(y for _, y in polygon) - min(y for _, y in polygon)) / 1.1)
    center = ((min(x for x, _ in polygon) + max(x for x, _ in polygon)) / 2.0,
              (min(y for _, y in polygon) + max(y for _, y in polygon)) / 2.0)
    polygon = fixed_output_rectangle(size, BoundaryAxis.X, protected, source_extent, preferred_center=center)
    saturation = _saturation_facts(polygon, protected, authority, source_extent)
    required = clip_convex_polygon_to_bounds(polygon, sampling_authority_bounds(authority, source_extent)) if (
        saturation and all(f.source_boundary for f in saturation)) else polygon
    return OutputFootprint(
        geometry_id="sampling-fixture",
        fixed_size=size,
        width_axis=BoundaryAxis.X,
        sequence_direction=1,
        envelope=JointPlacementEnvelope(
            placement_id="sampling-fixture",
            projection_id="sampling-fixture",
            lane_id="lane:0",
            lane_ordinal=1,
            boundary_use=OutputBoundaryUse.APERTURE_PAIR,
            canonical_source_footprint=polygon,
            feasible_source_footprint=polygon,
            extreme_evaluation_count=1,
            sequence_constraint_basis=(
                SequenceProjectionConstraintBasis.MODEL_INTERVALS
            ),
            global_lattice_constraint_ids=(),
        ),
        mandatory_source_footprint=protected,
        requested_source_footprint=polygon,
        required_source_footprint=required,
        boundary_protections=tuple(
            BoundaryProtectionFact(role, 0.0, 0.0, 0.0)
            for role in (
                BoundaryRole.START,
                BoundaryRole.END,
                BoundaryRole.TOP,
                BoundaryRole.BOTTOM,
            )
        ),
        maximum_same_state_cross_alignment_padding_px=None,
        enclosing_support_aperture_risk=None,
        saturation_facts=saturation,
        sampling_authority_box=authority,
        source_extent=source_extent,
        authority_profile_id="sampling-fixture",
    )


# Affine and TIFF contracts share deterministic raster fixtures.
__all__ = tuple(name for name in globals() if not name.startswith("__"))
