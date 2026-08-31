"""Prepared-lane fixtures shared by runtime and replay contract tests."""

from __future__ import annotations

from x5crop.configuration.registry import get_detection_configuration
from x5crop.detection.evidence.scan_canvas import observe_scan_canvas
from x5crop.detection.photo_geometry.coarse_strip_support import (
    CoarseAxisSupport,
    CoarseStripSupport,
    CoarseStripSupportReceipt,
    CoarseSupportAuthority,
)
from x5crop.detection.photo_geometry.measurement_model import (
    PhotoBoundaryCoverageReceipt,
    PhotoBoundaryMeasurementQuery,
    PhotoBoundaryMeasurementSet,
)
from x5crop.detection.photo_geometry.model import BoundaryAxis, QueryPurpose
from x5crop.detection.photo_geometry.observation_types import BasicAxisProfile
from x5crop.detection.photo_geometry.search_model import (
    SequenceAnchorDiscoveryDomain,
    SequenceAnchorWindow,
)
from x5crop.detection.photo_geometry.source_geometry import SourceScanGeometry
from x5crop.detection.photo_geometry.template_cross import fit_template_cross
from x5crop.detection.photo_geometry.template_cross_model import (
    TemplateCrossInput,
)
from x5crop.detection.photo_geometry.template_frame_width import (
    SourceFrameWidthAuthority,
    SourceFrameWidthAuthorityFailureKind,
)
from x5crop.detection.photo_geometry.template_measurement_plan import (
    compile_template_measurement_plan,
)
from x5crop.detection.photo_geometry.template_phase import fit_template_phase
from x5crop.detection.photo_geometry.template_phase_model import (
    TemplatePhaseInput,
)
from x5crop.detection.photo_geometry.template_runtime_model import (
    PreparedTemplateLane,
    RegisteredTemplateLane,
    TemplateMeasurementWorkReceipt,
)
from x5crop.detection.source_core import (
    SourceLaneEvidence,
    SourceStripValidationDomain,
)
from x5crop.domain import Box, EvidenceState, FiniteInterval, PositiveInterval
from x5crop.formats import FramePhysicalSpec


def runtime_lane() -> SourceLaneEvidence:
    configuration = get_detection_configuration("135")
    canvas = observe_scan_canvas(
        2320,
        322,
        "horizontal",
        configuration.scan_canvas,
    )
    return SourceLaneEvidence(
        SourceStripValidationDomain(
            lane_id="lane:0",
            work_box=Box(0, 0, 2320, 322),
            source_axis_long="x",
            authority_profile_id="135_standard",
        ),
        canvas,
    )


def runtime_axis_profile(axis_name: str) -> BasicAxisProfile:
    return BasicAxisProfile(
        axis_name=axis_name,
        coordinate_count=1,
        trace_coordinates_px=(0,),
        runs=(),
    )


def runtime_measurement_set(
    lane_id: str,
    *,
    registration_index: int,
    purpose: QueryPurpose = QueryPurpose.SEQUENCE_ANCHOR_WINDOW,
) -> PhotoBoundaryMeasurementSet:
    query = PhotoBoundaryMeasurementQuery(
        query_id=f"query:{lane_id}:{registration_index}:{purpose.value}",
        registration_index=registration_index,
        lane_id=lane_id,
        purpose=purpose,
        boundary_axis=BoundaryAxis.X,
        trace_positions_px=(0,),
        search_intervals_px=(FiniteInterval(0.0, 10.0),),
        transition_ownership_intervals_px=(FiniteInterval(0.0, 10.0),),
        expected_support_px=1.0,
        boundary_axis_scale_px_per_mm=PositiveInterval.exact(1.0),
        trace_axis_scale_px_per_mm=PositiveInterval.exact(1.0),
        measurement_halo_px=1,
        registration_provenance_ids=(f"intent:{lane_id}",),
    )
    coverage = PhotoBoundaryCoverageReceipt(
        query_id=query.query_id,
        registered_trace_count=1,
        completed_trace_count=1,
        registered_coordinate_count=1,
        completed_coordinate_count=1,
        pixel_query_count=1,
        streaming_block_count=1,
        peak_temporary_bytes=8,
        complete=True,
    )
    return PhotoBoundaryMeasurementSet(
        query=query,
        state=EvidenceState.SUPPORTED,
        transitions=(),
        cross_height_transitions=(),
        coverage=coverage,
    )


def prepared_template_lane() -> PreparedTemplateLane:
    lane = runtime_lane()
    configuration = get_detection_configuration("135")
    scales = lane.scan_canvas.axis_scales
    assert scales is not None
    plan = compile_template_measurement_plan(
        format_spec=configuration.physical_spec,
        frame_spec=configuration.physical_spec.frame,
        count=1,
        full_count=6,
        holder_full_count=6,
        lane_authority=lane.domain,
        layout="horizontal",
        scale_authority=scales,
    )
    template = plan.template_spec
    coarse_long = runtime_measurement_set(
        "lane:0",
        registration_index=0,
        purpose=QueryPurpose.COARSE_STRIP_LONG,
    )
    coarse_short = runtime_measurement_set(
        "lane:0",
        registration_index=1,
        purpose=QueryPurpose.COARSE_STRIP_SHORT,
    )
    registered = RegisteredTemplateLane(
        lane=lane,
        layout="horizontal",
        output_slot_count=1,
        measurement_slot_count=6,
        width_axis=BoundaryAxis.X,
        height_axis=BoundaryAxis.Y,
        width_authority_px=FiniteInterval(0.0, 2320.0),
        height_authority_px=FiniteInterval(0.0, 322.0),
        coarse_support=CoarseStripSupport(
            "lane:0",
            CoarseAxisSupport(
                FiniteInterval(0.0, 2319.0),
                None,
                CoarseSupportAuthority.HOLDER_CONSERVATIVE,
                (),
            ),
            CoarseAxisSupport(
                FiniteInterval(0.0, 321.0),
                None,
                CoarseSupportAuthority.HOLDER_CONSERVATIVE,
                (),
            ),
            None,
            None,
            CoarseStripSupportReceipt(2, 2, 2, 2, 8, 2, 2),
        ),
        anchor_domain=SequenceAnchorDiscoveryDomain(
            domain_id="domain:runtime",
            lane_id="lane:0",
            long_axis_extent_px=2320,
            support_interval_px=FiniteInterval(0.0, 2319.0),
            authoritative_sequence_length=6,
            windows=(
                SequenceAnchorWindow(
                    window_id="anchor-window:lane:0:conservative",
                    core_px=FiniteInterval(0.0, 2320.0),
                    measurement_px=FiniteInterval(0.0, 2319.0),
                ),
            ),
            query_execution_order=("anchor-window:lane:0:conservative",),
        ),
        measurement_sets=(coarse_long, coarse_short),
        side_regions=(),
        cross_height_regions=(),
        cross_height_edges=(),
        cross_height_edge_resolutions=(),
        top_regions=(),
        bottom_regions=(),
        transition_by_id={},
        sequence_profile=runtime_axis_profile("sequence"),
        cross_profile=runtime_axis_profile("cross"),
        sequence_edges=(),
        separator_bands=(),
        top_cross_bindings=(),
        bottom_cross_bindings=(),
        raw_cross_observations=(),
        cross_boundary_family_resolutions=(),
        measurement_work=TemplateMeasurementWorkReceipt(
            2,
            2,
            2,
            8,
            (coarse_long.coverage, coarse_short.coverage),
        ),
        measurement_plan=plan,
    )
    source = SourceScanGeometry.create(
        FramePhysicalSpec(36.0, 24.0, 2.0),
        width_scale_px_per_mm=PositiveInterval.exact(10.0),
        height_scale_px_per_mm=PositiveInterval.exact(10.0),
    )
    phase_input = TemplatePhaseInput(
        observations=(),
        separator_bands=(),
        template=template,
        scale_px_per_mm=None,
        holder_span_px=None,
        phase_authority_px=None,
    )
    cross_input = TemplateCrossInput(
        template=template,
        fixed_height_px=240.0,
    )
    return PreparedTemplateLane(
        **registered.__dict__,
        template_spec=template,
        source_scan_geometry=source,
        source_frame_width_authority=SourceFrameWidthAuthority(
            authority_id="source-width:test:unavailable",
            state=EvidenceState.UNAVAILABLE,
            selected_integer_slot_offset=None,
            selected_role_observation_ids=(),
            supporting_frame_ordinals=(),
            width_px=None,
            canonical_width_px=None,
            observation_ids=(),
            failure_kind=(
                SourceFrameWidthAuthorityFailureKind.UNIQUE_PLACEMENT_UNAVAILABLE
            ),
            reason="test fixture has no selected placement",
        ),
        phase_input=phase_input,
        cross_input=cross_input,
        phase_competition=fit_template_phase((), template),
        cross_competition=fit_template_cross(cross_input),
    )


__all__ = [
    "prepared_template_lane",
    "runtime_axis_profile",
    "runtime_lane",
    "runtime_measurement_set",
]
