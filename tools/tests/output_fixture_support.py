from __future__ import annotations

import ast
from dataclasses import replace
import inspect
import math
from pathlib import Path
from types import SimpleNamespace
import unittest

from x5crop.domain import (
    Box,
    EvidenceState,
    FiniteInterval,
    MeasurementIdentity,
    MeasurementProvenance,
    WorkspaceExtent,
    ObservationId,
    PositiveInterval,
)
from x5crop.formats import (
    DEVELOPMENT_GOLD_CALIBRATION_COHORT_SHA256,
    EnclosingSupportApertureCalibrationSpec,
)
from x5crop.formats.scan_canvas import ScanCanvasPhysicalSpec
from x5crop.detection.gate_checks import GateGap
from x5crop.detection.evidence.scan_canvas import (
    CanvasAxisScaleIntervals,
    ScanCanvasEvidence,
    ScanCanvasOutcome,
    ScanCanvasProfileMatch,
)
from x5crop.detection.photo_geometry.model import (
    AuthoritySide,
    BoundaryAxis,
    BoundaryRole,
)
from x5crop.detection.photo_geometry.output_model import (
    FootprintSaturationKind,
    fixed_output_rectangle,
    OutputBoundaryUse,
    sampling_authority_bounds,
)
from x5crop.detection.photo_geometry.template_cross_model import (
    CrossFit,
    CrossFitStatus,
    CrossHeightProjectionBasis,
    CrossLineProjectionBasis,
    EnclosingSupportPair,
)
from x5crop.detection.photo_geometry.template_gate import build_template_gate
from x5crop.detection.photo_geometry.template_holder_fill import HolderFillState
from x5crop.detection.photo_geometry.source_geometry import SourceFixedOutputSize
from x5crop.detection.photo_geometry.template_phase_model import PhaseFitStatus
from x5crop.detection.photo_geometry.template_nominal_grid_authority import (
    assess_calibrated_nominal_grid_authority,
)
from x5crop.detection.photo_geometry.template_output import (
    _aperture_binding_positions,
    _enclosing_support_aperture_risk,
    _footprint,
    _frame_boundary_residuals,
    _line_outward_expansion_px,
    _saturation_facts,
    _state_footprint,
    output_footprint_from_template_placement,
    template_direct_use_budget_assessment,
)
from x5crop.detection.photo_geometry.template_feasible_geometry import (
    JointFrameState,
    _shared_slope_polygon_vertices,
    _support_cross_vertices,
    project_format_placement,
)
from x5crop.geometry.convex import clip_convex_polygon_to_bounds, convex_hull
from x5crop.detection.photo_geometry.template_enclosing_support_aperture import (
    derive_enclosing_support_aperture_authority,
    unavailable_enclosing_support_aperture_authority,
)
from x5crop.detection.photo_geometry.template_placement import (
    resolved_cross_support_domains_px,
)
from x5crop.detection.photo_geometry.line_observations import PhysicalLineRegion, SourceCoordinateLine
from x5crop.detection.photo_geometry.template_model import (
    ContactRelation,
    OverlapRelation,
    SequenceRoleLineEvidence,
)
from x5crop.detection.source_core import (
    SourceLaneEvidence,
    SourceStripValidationDomain,
)
from tools.tests.template_test_support import (
    placement_binding as _binding,
    placement_compose as _compose,
    placement_cross as _cross,
    placement_direction as _direction,
    placement_sequence as _sequence,
    placement_template as _template,
)


def _placement():
    template = _template(1)
    direction = _direction()
    return _compose(
        template,
        _sequence(template),
        _cross(template, direction=direction),
    )


def _contact_placement(
    *,
    shared_uncertainty_px: float = 0.0,
    shared_direction_uncertainty_degrees: float = 0.0,
):
    template = _template(2)
    sequence = _sequence(template)
    shared_id = ObservationId("sequence:contact-shared")
    contact_id = ObservationId("contact-edge:test")
    shared_interval = FiniteInterval(
        200.0 - shared_uncertainty_px,
        200.0 + shared_uncertainty_px,
    )
    shared_binding = replace(
        sequence.role_bindings[1],
        observation_id=shared_id,
        evidence_group_id=shared_id,
        canonical_position_px=200.0,
        fit_position_interval_px=shared_interval,
        full_position_interval_px=shared_interval,
        line_evidence=(
            None
            if shared_direction_uncertainty_degrees == 0.0
            else SequenceRoleLineEvidence(
                observation_id=shared_id,
                reference_trace_px=150.0,
                fit_position_interval_px=shared_interval,
                fit_direction_interval_degrees=FiniteInterval(
                    -shared_direction_uncertainty_degrees,
                    shared_direction_uncertainty_degrees,
                ),
            )
        ),
    )
    assert shared_binding is not None
    final_binding = replace(
        sequence.role_bindings[3],
        canonical_position_px=300.0,
        fit_position_interval_px=FiniteInterval.exact(300.0),
        full_position_interval_px=FiniteInterval.exact(300.0),
    )
    assert final_binding is not None
    positions = (100.0, 200.0, 200.0, 300.0)
    fit_intervals = tuple(FiniteInterval.exact(value) for value in positions)
    full_intervals = list(fit_intervals)
    full_intervals[1] = shared_interval
    full_intervals[2] = shared_interval
    sequence = replace(
        sequence,
        model_role_positions_px=positions,
        model_role_intervals_px=fit_intervals,
        model_full_role_intervals_px=tuple(full_intervals),
        role_bindings=(
            sequence.role_bindings[0],
            shared_binding,
            shared_binding,
            final_binding,
        ),
        adjacency_relations=(
            ContactRelation(
                relation_ordinal=1,
                contact_observation_id=contact_id,
                physical_edge_id=shared_id,
                shared_edge_observation_id=shared_id,
                delta_interval_px=FiniteInterval.exact(-20.0),
                canonical_delta_px=-20.0,
                supporting_observation_ids=(shared_id,),
            ),
        ),
    )
    return _compose(
        template,
        sequence,
        _cross(template, direction=_direction()),
    )


def _overlap_placement():
    template = _template(2)
    sequence = _sequence(template)
    end_id = ObservationId("sequence:1")
    start_id = ObservationId("sequence:2")
    end_binding = sequence.role_bindings[1]
    start_binding = sequence.role_bindings[2]
    final_binding = sequence.role_bindings[3]
    assert end_binding is not None
    assert start_binding is not None
    assert final_binding is not None
    start_binding = replace(
        start_binding,
        canonical_position_px=195.0,
        fit_position_interval_px=FiniteInterval.exact(195.0),
        full_position_interval_px=FiniteInterval.exact(195.0),
    )
    final_binding = replace(
        final_binding,
        canonical_position_px=295.0,
        fit_position_interval_px=FiniteInterval.exact(295.0),
        full_position_interval_px=FiniteInterval.exact(295.0),
    )
    positions = (100.0, 200.0, 195.0, 295.0)
    intervals = tuple(FiniteInterval.exact(value) for value in positions)
    sequence = replace(
        sequence,
        model_role_positions_px=positions,
        model_role_intervals_px=intervals,
        model_full_role_intervals_px=intervals,
        role_bindings=(
            sequence.role_bindings[0],
            end_binding,
            start_binding,
            final_binding,
        ),
        adjacency_relations=(
            OverlapRelation(
                relation_ordinal=1,
                overlap_observation_id=ObservationId("overlap:test"),
                end_edge_observation_id=end_id,
                next_start_edge_observation_id=start_id,
                signed_gap_interval_px=FiniteInterval.exact(-5.0),
                canonical_signed_gap_px=-5.0,
                delta_interval_px=FiniteInterval.exact(-25.0),
                canonical_delta_px=-25.0,
                supporting_observation_ids=(end_id, start_id),
            ),
        ),
    )
    return _compose(
        template,
        sequence,
        _cross(template, direction=_direction()),
    )


def _enclosing_support_placement(
    *,
    frame_count: int = 1,
    frame_width_px: float = 100.0,
    support_span_px: float = 250.0,
    support_center_px: float = 152.0,
    support_position_uncertainty_px: float = 0.0,
    support_slope: float = 0.0,
    observed_direction_half_width_degrees: float = 0.0,
):
    template = _template(frame_count)
    if frame_width_px != 100.0:
        template = replace(
            template,
            frame_width_px=FiniteInterval.exact(frame_width_px),
            pitch_px=FiniteInterval.exact(frame_width_px + 20.0),
            phase_lattice_authority=replace(template.phase_lattice_authority, period_px=frame_width_px + 20.0),
        )
    support_center = support_center_px
    support_top = support_center - support_span_px / 2.0
    support_bottom = support_center + support_span_px / 2.0
    support_traces = (0, 150, 300)
    canonical_direction = math.degrees(math.atan(support_slope))
    full_direction = FiniteInterval.exact(canonical_direction)
    observed_direction = FiniteInterval(
        canonical_direction - observed_direction_half_width_degrees,
        canonical_direction + observed_direction_half_width_degrees,
    )
    top = replace(
        _binding(BoundaryRole.TOP, "support-top", support_top),
        full_interval_px=FiniteInterval(
            support_top - support_position_uncertainty_px,
            support_top + support_position_uncertainty_px,
        ),
        trace_coordinates_px=support_traces,
        canonical_direction_degrees=canonical_direction,
        fit_direction_interval_degrees=full_direction,
        full_direction_interval_degrees=full_direction,
        observed_direction_interval_degrees=observed_direction,
    )
    bottom = replace(
        _binding(BoundaryRole.BOTTOM, "support-bottom", support_bottom),
        full_interval_px=FiniteInterval(
            support_bottom - support_position_uncertainty_px,
            support_bottom + support_position_uncertainty_px,
        ),
        trace_coordinates_px=support_traces,
        canonical_direction_degrees=canonical_direction,
        fit_direction_interval_degrees=full_direction,
        full_direction_interval_degrees=full_direction,
        observed_direction_interval_degrees=observed_direction,
    )
    direction = replace(
        _direction(),
        selected_observation_ids=(top.observation_id, bottom.observation_id),
        full_angle_interval_degrees=full_direction,
        observed_angle_interval_degrees=observed_direction,
        canonical_angle_degrees=canonical_direction,
    )
    support = EnclosingSupportPair(
        top_canonical_px=support_top,
        bottom_canonical_px=support_bottom,
        top_full_interval_px=FiniteInterval(
            support_top - support_position_uncertainty_px,
            support_top + support_position_uncertainty_px,
        ),
        bottom_full_interval_px=FiniteInterval(
            support_bottom - support_position_uncertainty_px,
            support_bottom + support_position_uncertainty_px,
        ),
        top_provenance_ids=(top.observation_id,),
        bottom_provenance_ids=(bottom.observation_id,),
        observed_span_px=FiniteInterval(
            support_span_px - 2.0 * support_position_uncertainty_px,
            support_span_px + 2.0 * support_position_uncertainty_px,
        ),
        reference_trace_px=150.0,
        top_trace_coordinates_px=support_traces,
        bottom_trace_coordinates_px=support_traces,
        top_trace_intervals_px=tuple(
            FiniteInterval(
                support_top
                + support_slope * (trace - 150.0)
                - support_position_uncertainty_px,
                support_top
                + support_slope * (trace - 150.0)
                + support_position_uncertainty_px,
            )
            for trace in support_traces
        ),
        bottom_trace_intervals_px=tuple(
            FiniteInterval(
                support_bottom
                + support_slope * (trace - 150.0)
                - support_position_uncertainty_px,
                support_bottom
                + support_slope * (trace - 150.0)
                + support_position_uncertainty_px,
            )
            for trace in support_traces
        ),
    )
    top = replace(
        top,
        trace_position_intervals_px=support.top_trace_intervals_px,
    )
    bottom = replace(
        bottom,
        trace_position_intervals_px=support.bottom_trace_intervals_px,
    )
    cross = CrossFit(
        template_id=template.template_id,
        lane_reference_trace_px=150.0,
        fixed_height_px=FiniteInterval.exact(240.0),
        top_canonical_px=support_center - 120.0,
        bottom_canonical_px=support_center + 120.0,
        top_fit_interval_px=FiniteInterval.exact(support_center - 120.0),
        bottom_fit_interval_px=FiniteInterval.exact(support_center + 120.0),
        top_full_interval_px=FiniteInterval.exact(support_center - 120.0),
        bottom_full_interval_px=FiniteInterval.exact(support_center + 120.0),
        direct_bindings=(top, bottom),
        inferred_bindings=(),
        selected_direction=direction,
        direct_pair=True,
        shared_trace_support_count=3,
        continuous_support_fraction=1.0,
        residual_sum_px=0.0,
        boundary_use=OutputBoundaryUse.ENCLOSING_SUPPORT_PAIR,
        pair_support_mode=None,
        height_projection_basis=(
            CrossHeightProjectionBasis.COMPLETE_PHYSICAL_INTERVAL
        ),
        enclosing_support_pair=support,
    )
    return _compose(template, _sequence(template), cross)


def _lane(
    lane_id: str = "lane:test", *, long_axis_px: int = 500, short_axis_px: int = 400,
) -> SourceLaneEvidence:
    profile = ScanCanvasPhysicalSpec(
        profile_id="template-output-holder",
        short_axis_mm=short_axis_px / 10.0,
        long_axis_mm=long_axis_px / 10.0,
    )
    shared_scale = PositiveInterval.exact(10.0)
    scales = CanvasAxisScaleIntervals(
        holder_profile_id=profile.profile_id,
        width_axis_px_per_mm=shared_scale,
        height_axis_px_per_mm=shared_scale,
        source_width_axis="x",
        source_height_axis="y",
    )
    scan_canvas = ScanCanvasEvidence(
        outcome=ScanCanvasOutcome.SUPPORTED,
        observed_long_axis_px=long_axis_px,
        observed_short_axis_px=short_axis_px,
        matches=(
            ScanCanvasProfileMatch(
                profile=profile,
                aspect_error_ratio=0.0,
                shared_scale_px_per_mm=shared_scale,
            ),
        ),
        selected_profile=profile,
        axis_scales=scales,
        provenance=MeasurementProvenance(
            root_measurement=MeasurementIdentity.SCAN_CANVAS_GEOMETRY,
            observation_id=ObservationId("template-output:canvas"),
            dependencies=(),
            description="template output test canvas",
        ),
    )
    return SourceLaneEvidence(
        domain=SourceStripValidationDomain(
            lane_id=lane_id,
            work_box=Box(0, 0, long_axis_px, short_axis_px),
            source_axis_long="x",
            authority_profile_id=profile.profile_id,
        ),
        scan_canvas=scan_canvas,
    )


def _selected_output_gate_fact(
    output,
    assessment,
    *,
    code="selected_output_footprint",
):
    aperture_state = (
        EvidenceState.NOT_APPLICABLE
        if output.enclosing_support_aperture_risk is None
        else output.enclosing_support_aperture_risk.aperture_authority_state
    )
    reconstruction = SimpleNamespace(
        prepared=SimpleNamespace(
            measurement_sets=(),
            measurement_work=SimpleNamespace(
                completed_query_count=1,
                measurement_query_count=1,
            ),
            phase_competition=SimpleNamespace(
                status=PhaseFitStatus.RESOLVED,
                failure_kind=None,
            ),
            cross_competition=SimpleNamespace(status=CrossFitStatus.RESOLVED),
        ),
        work=SimpleNamespace(bound_exceeded=False),
        placement_competition=SimpleNamespace(placements=(object(),)),
        selected_placement=object(),
        output_footprints=(output,),
        calibrated_nominal_grid_authority=(
            assess_calibrated_nominal_grid_authority(
                None,
                placement_id=None,
                output_geometry_ids=(),
            )
        ),
        enclosing_support_aperture_authority=SimpleNamespace(
            state=aperture_state,
            failure_detail=(
                "calibrated center contradicts direct support"
                if aperture_state == EvidenceState.CONTRADICTED
                else None
            ),
        ),
        direct_use_budget_assessments=(assessment,),
        holder_fill_assessment=SimpleNamespace(state=HolderFillState.FILLED),
        content_veto_facts=(),
    )
    return build_template_gate(
        SimpleNamespace(output_slot_count=1),
        (reconstruction,),
        SimpleNamespace(
            state=EvidenceState.SUPPORTED,
            failure=None,
        ),
    )[code]


from dataclasses import replace
import unittest

from tools.tests.template_test_support import placement_binding, placement_compose, placement_cross_longitudinal_authority
from x5crop.domain import Box, EvidenceState, FiniteInterval
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.template_feasible_geometry import project_format_placement
from x5crop.detection.photo_geometry.template_output import (
    common_h_output_footprint, output_footprint_from_template_placement,
    template_direct_use_budget_assessment,
)


def translated_h(placement, delta):
    original = placement.cross_fit
    top = original.top_canonical_px + delta
    bottom = original.bottom_canonical_px + delta
    bindings = (placement_binding(BoundaryRole.TOP, f"top:{delta}", top),
                placement_binding(BoundaryRole.BOTTOM, f"bottom:{delta}", bottom))
    fit = replace(original, top_canonical_px=top, bottom_canonical_px=bottom,
        top_fit_interval_px=FiniteInterval.exact(top), bottom_fit_interval_px=FiniteInterval.exact(bottom),
        top_full_interval_px=FiniteInterval.exact(top), bottom_full_interval_px=FiniteInterval.exact(bottom),
        direct_bindings=bindings, direct_provenance_ids=(),
        selected_direction=replace(original.selected_direction, selected_observation_ids=tuple(b.observation_id for b in bindings)),
        longitudinal_projection_authority=placement_cross_longitudinal_authority(placement.sequence_fit.template, *bindings))
    return placement_compose(placement.sequence_fit.template, placement.sequence_fit, fit)


def native_output(placement, lane=None):
    return output_footprint_from_template_placement(placement, project_format_placement(placement),
        lane=lane or _lane(), lane_ordinal=1, layout="horizontal")

from dataclasses import replace
import unittest
from unittest.mock import patch

from tools.tests.cross_fixture_support import aspect_input, binding, template
from x5crop.domain import FiniteInterval
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.template_common_output import common_h_fit_members, materialize_common_h_output
from x5crop.detection.photo_geometry.template_cross import fit_template_cross
from x5crop.detection.photo_geometry.template_family_membership import MembershipFitBudget, MembershipReceipt, MembershipState
from x5crop.detection.photo_geometry.template_feasible_geometry import project_format_placement
from x5crop.detection.photo_geometry.template_registration import CrossRegistrationWorkReceipt


def registration():
    membership = MembershipReceipt(MembershipState.COMPLETE, (), tuple(
        MembershipFitBudget(role, 0, 0, 0, 0) for role in (BoundaryRole.TOP, BoundaryRole.BOTTOM)), ())
    return CrossRegistrationWorkReceipt(0, 0, 0, membership=membership)

"""Common-output authority must cover every H interpretation before selection."""

from dataclasses import replace
from types import SimpleNamespace
import unittest

from tools.tests.template_test_support import (
    phase_edge,
    phase_template,
    placement_compose,
)
from tools.tests.cross_fixture_support import (
    aspect_input,
    binding,
    _supported_aspect_ratio,
)
from tools.tests.cross_fixture_support import _problem
from x5crop.domain import EvidenceState, FiniteInterval, ObservationId
from x5crop.formats import FramePhysicalSpec
from x5crop.detection.gate_checks import GateGap
from x5crop.detection.photo_geometry.content_veto_model import (
    ContentVetoAssessment,
    ContentVetoFact,
    ContentVetoReason,
)
from x5crop.detection.photo_geometry.line_observations import (
    PhotoBoundaryObservation,
    RobustLineFitReceipt,
    SourceCoordinateLine,
)
from x5crop.detection.photo_geometry.model import BoundaryAxis, BoundaryRole
from x5crop.detection.photo_geometry.template_common_output import (
    assess_common_h_output_authority,
    common_h_fit_members,
    materialize_common_h_output,
)
from x5crop.detection.photo_geometry.template_cross import fit_template_cross
from x5crop.detection.photo_geometry.template_cross_model import CrossFitStatus
from x5crop.detection.photo_geometry.template_cross_support import SupportFitStatus
from x5crop.detection.photo_geometry.template_family_membership import (
    MembershipState,
    enumerate_membership_scope,
)
from x5crop.detection.photo_geometry.template_output import common_direct_use_budget_assessment
from x5crop.detection.photo_geometry.template_phase_competition import fit_template_phase
from x5crop.detection.photo_geometry.template_registration import membership_projection_coverage
from x5crop.detection.photo_geometry.template_selection import (
    select_lane_template_placement,
    select_template_source,
)


def _case(*, support_pair=False, aspect_height=None):
    spec = phase_template(1)
    phase = fit_template_phase((phase_edge("start", 40), phase_edge("end", 140)), spec)
    if support_pair:
        tops = (binding(BoundaryRole.TOP, "top", 100),)
        bottoms = tuple(binding(BoundaryRole.BOTTOM, f"bottom:{i}", 350 + i) for i in range(2))
        tops = tuple(replace(b, trace_position_intervals_px=(b.full_interval_px,) * 3) for b in tops)
        bottoms = tuple(replace(b, trace_position_intervals_px=(b.full_interval_px,) * 3) for b in bottoms)
    else:
        tops = tuple(binding(BoundaryRole.TOP, f"top:{i}", 100 + i) for i in range(2))
        bottoms = (binding(BoundaryRole.BOTTOM, "bottom", 340),)
    inputs = aspect_input(
        template=spec, fixed_height_px=FiniteInterval(230, 260), canonical_fixed_height_px=240,
        top_bindings=tops, bottom_bindings=bottoms,
    )
    if aspect_height is not None:
        inputs = replace(inputs, aperture_aspect_ratio_authority=_supported_aspect_ratio(aspect_height))
    cross = fit_template_cross(inputs)
    members, mapping = common_h_fit_members(cross, registration())
    placements = tuple(placement_compose(
        spec, phase.best, fit, frame_spec=FramePhysicalSpec(10.0, 25.0 if support_pair else 24.0, 2.0),
    ) for fit in members)
    common = materialize_common_h_output(placements, mapping, lane=_lane(), layout="horizontal")
    if common.failure is not None:
        raise AssertionError(common.failure)
    return phase, cross, inputs, common


def _authority(case, *, work=None, coverage=()):
    phase, cross, inputs, common = case
    return assess_common_h_output_authority(
        common, phase=phase, cross=cross, registration=work or registration(),
        membership_coverage=coverage, cross_input=inputs,
    )


def _select(case, authority, content):
    phase, cross, _inputs, common = case
    return select_lane_template_placement(
        lane_id=common.lane_id, best=common.placements[0], runner_up=common.placements[1],
        phase=phase, cross=cross, content_assessment=content,
        common_h_output=common, common_h_authority=authority,
    )


def _clear_content(common):
    return ContentVetoAssessment("common-content", common.placement_id, ())


def _observation(identity, transitions):
    return PhotoBoundaryObservation(
        observation_id=ObservationId(identity), role=BoundaryRole.TOP,
        line=SourceCoordinateLine(0, 1, 100, FiniteInterval(0, 100), BoundaryAxis.X),
        offset_interval_px=FiniteInterval.exact(100),
        fit_residual_px=0, angle_interval_degrees=FiniteInterval.exact(0),
        trace_support_count=len(transitions), queried_trace_count=len(transitions),
        independent_support_region_count=2, continuous_support_fraction=1,
        transition_ids=tuple(map(ObservationId, transitions)),
        fit_receipt=RobustLineFitReceipt("scipy_least_squares_huber", True, 1, 1, 0, 0),
        left_background_preference_fraction=1,
    )
