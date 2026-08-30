from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np

from x5crop.configuration.registry import get_detection_configuration
from x5crop.detection.photo_geometry.boundary_fitting import (
    fit_format_bound_boundary_observation,
)
from x5crop.detection.photo_geometry.registered_measurement import (
    measure_registered_queries,
)
from x5crop.detection.photo_geometry.transition_tracking import (
    track_side_transition_regions,
)
from x5crop.detection.photo_geometry.sequence_edge_families import (
    merge_sequence_edge_families,
)
from x5crop.detection.photo_geometry.boundary_geometry import (
    canonical_boundary_line,
)
from x5crop.detection.photo_geometry.model import (
    BoundaryAxis,
    BoundaryRole,
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    QueryPurpose,
)
from x5crop.detection.photo_geometry.measurement_model import (
    PhotoBoundaryCoverageReceipt,
    PhotoBoundaryMeasurementField,
    PhotoBoundaryMeasurementQuery,
    PhotoBoundaryMeasurementSet,
    PhotoBoundaryTransition,
)
from x5crop.detection.photo_geometry.observation_types import (
    BasicAxisProfile,
    BoundaryEdgeObservation,
    ProfileRun,
    SeparatorMaterialPolarity,
    SeparatorMaterialRegionObservation,
    SeparatorMaterialRegionState,
)
from x5crop.detection.photo_geometry.line_observations import (
    SideTransitionRegion,
)
from x5crop.detection.photo_geometry.profile_adapters import (
    cross_profile_from_regions,
)
from x5crop.detection.photo_geometry.separator_material import (
    classify_separator_material_region,
    repeated_separator_material_supported,
)
from x5crop.detection.photo_geometry.separator_observations import (
    build_format_separator_bands,
)
from x5crop.detection.photo_geometry.output_model import (
    DirectUseBudgetEdgeAssessment,
    ResolvedOutputSlots,
    SharedStripDirection,
)
from x5crop.detection.pipeline import choose_detection
from x5crop.detection.workspace import prepare_detection_workspace
from x5crop.domain import (
    EvidenceState,
    FiniteInterval,
    ObservationId,
    PositiveInterval,
)
from x5crop.io.model import ImageProfile, TiffMetadata
from x5crop.io.orientation import orientation_mapping


def make_profile(shape: tuple[int, int, int]) -> ImageProfile:
    return ImageProfile(
        shape=shape,
        dtype="uint16",
        axes="YXS",
        photometric="RGB",
        compression="NONE",
        sample_format=None,
        bits_per_sample=(16, 16, 16),
        samples_per_pixel=3,
        planar_config="CONTIG",
        resolution=None,
        resolution_unit=None,
        icc_profile=None,
        metadata=TiffMetadata(None, None, None, ()),
        orientation=orientation_mapping(1, shape[1], shape[0]),
    )


def make_candidate(pixels: np.ndarray):
    product_pixels = (
        np.repeat(pixels[..., None], 3, axis=2).astype(np.uint16) * 257
    )
    configuration = get_detection_configuration("135")
    workspace = prepare_detection_workspace(
        product_pixels,
        make_profile(tuple(int(value) for value in product_pixels.shape)),
        "horizontal",
        configuration,
    )
    return workspace, configuration, choose_detection(
        workspace,
        configuration,
    )


def make_side_measurement_set(
    coordinates_by_trace: tuple[tuple[float, ...], ...],
    *,
    transition_half_width_px: float = 0.25,
) -> PhotoBoundaryMeasurementSet:
    traces = tuple(index * 10 for index in range(len(coordinates_by_trace)))
    query = PhotoBoundaryMeasurementQuery(
        query_id="query:side-tracking",
        registration_index=0,
        lane_id="lane:0",
        purpose=QueryPurpose.SEQUENCE_ANCHOR_WINDOW,
        boundary_axis=BoundaryAxis.X,
        trace_positions_px=traces,
        search_intervals_px=(FiniteInterval(0.0, 200.0),) * len(traces),
        transition_ownership_intervals_px=(FiniteInterval(0.0, 200.0),)
        * len(traces),
        expected_support_px=40.0,
        boundary_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        trace_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        measurement_halo_px=2,
        registration_provenance_ids=("anchor-domain:test",),
    )
    transitions = []
    for trace_ordinal, (trace, coordinates) in enumerate(
        zip(traces, coordinates_by_trace, strict=True)
    ):
        for coordinate_ordinal, coordinate in enumerate(coordinates):
            identity = ObservationId(
                f"transition:{trace_ordinal}:{coordinate_ordinal}"
            )
            transitions.append(
                PhotoBoundaryTransition(
                    transition_id=identity,
                    query_id=query.query_id,
                    trace_ordinal=trace_ordinal,
                    trace_coordinate_px=trace,
                    canonical_coordinate_px=coordinate,
                    localization_interval_px=FiniteInterval(
                        coordinate - transition_half_width_px,
                        coordinate + transition_half_width_px,
                    ),
                    physical_position_interval_px=FiniteInterval(
                        coordinate - transition_half_width_px,
                        coordinate + transition_half_width_px,
                    ),
                    gradient_z=5.0,
                    tone_z=5.0,
                    texture_z=5.0,
                    left_tone_mean=10.0,
                    right_tone_mean=30.0,
                    left_texture_mean=1.0,
                    right_texture_mean=5.0,
                    polarity=1,
                    peak_width_px=1.0,
                    prominence=5.0,
                    local_noise=0.0,
                )
            )
    coordinate_count = len(traces) * 201
    coverage = PhotoBoundaryCoverageReceipt(
        query_id=query.query_id,
        registered_trace_count=len(traces),
        completed_trace_count=len(traces),
        registered_coordinate_count=coordinate_count,
        completed_coordinate_count=coordinate_count,
        pixel_query_count=coordinate_count,
        streaming_block_count=1,
        peak_temporary_bytes=4096,
        complete=True,
    )
    return PhotoBoundaryMeasurementSet(
        query=query,
        state=EvidenceState.SUPPORTED,
        transitions=tuple(transitions),
        coverage=coverage,
    )

# The split measurement contracts share one explicit fixture namespace.
__all__ = tuple(name for name in globals() if not name.startswith("__"))
