from __future__ import annotations

import ast
from dataclasses import replace
import inspect
import math
from pathlib import Path
import unittest

from x5crop.domain import (
    Box,
    EvidenceState,
    FiniteInterval,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PositiveInterval,
)
from x5crop.formats import OUTPUT_PROTECTION_SPEC
from x5crop.formats.scan_canvas import ScanCanvasPhysicalSpec
from x5crop.detection.evidence.scan_canvas import (
    CanvasAxisScaleIntervals,
    ScanCanvasEvidence,
    ScanCanvasOutcome,
    ScanCanvasProfileMatch,
)
from x5crop.detection.photo_geometry.model import (
    AuthoritySide,
    BoundaryRole,
)
from x5crop.detection.photo_geometry.output_model import OutputBoundaryUse
from x5crop.detection.photo_geometry.template_cross_model import (
    CrossFit,
    EnclosingSupportPair,
)
from x5crop.detection.photo_geometry.template_output import (
    output_footprint_from_template_placement,
    template_direct_use_budget_assessment,
)
from x5crop.detection.photo_geometry.template_feasible_geometry import (
    project_selected_placement,
)
from x5crop.detection.photo_geometry.template_model import (
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


def _enclosing_support_placement(
    *,
    frame_count: int = 1,
    support_span_px: float = 250.0,
    support_position_uncertainty_px: float = 0.0,
    support_slope: float = 0.0,
    observed_direction_half_width_degrees: float = 0.0,
):
    template = _template(frame_count)
    support_center = 152.0
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
        trace_coordinates_px=support_traces,
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
    cross = CrossFit(
        template_id=template.template_id,
        lane_reference_trace_px=150.0,
        fixed_height_px=FiniteInterval.exact(240.0),
        top_canonical_px=32.0,
        bottom_canonical_px=272.0,
        top_fit_interval_px=FiniteInterval.exact(32.0),
        bottom_fit_interval_px=FiniteInterval.exact(272.0),
        top_full_interval_px=FiniteInterval.exact(32.0),
        bottom_full_interval_px=FiniteInterval.exact(272.0),
        direct_bindings=(top, bottom),
        inferred_bindings=(),
        selected_direction=direction,
        direct_pair=True,
        shared_trace_support_count=3,
        continuous_support_fraction=1.0,
        residual_sum_px=0.0,
        boundary_use=OutputBoundaryUse.ENCLOSING_SUPPORT_PAIR,
        enclosing_support_pair=support,
    )
    return _compose(template, _sequence(template), cross)


def _lane(lane_id: str = "lane:test") -> SourceLaneEvidence:
    profile = ScanCanvasPhysicalSpec(
        profile_id="template-output-holder",
        short_axis_mm=40.0,
        long_axis_mm=50.0,
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
        observed_long_axis_px=500,
        observed_short_axis_px=400,
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
            work_box=Box(0, 0, 500, 400),
            source_axis_long="x",
            authority_profile_id=profile.profile_id,
        ),
        scan_canvas=scan_canvas,
    )


class TemplateOutputContractTest(unittest.TestCase):
    def test_enclosing_support_keeps_its_same_state_target_projection(self) -> None:
        placement = _enclosing_support_placement(
            frame_count=2,
            support_slope=0.002,
        )
        projection = project_selected_placement(placement)
        frame = placement.frames[1]
        expected_top = 27.0 + 0.002 * (
            frame.top.reference_trace_px - 150.0
        )

        self.assertTrue(
            all(
                abs(state.top_at_lane_reference_px - expected_top) < 1.0e-8
                and abs(float(state.enclosing_support_slope) - 0.002) < 1.0e-10
                for state in projection.frame_states[1]
            )
        )

    def test_enclosing_support_retains_observed_direction_beyond_trace_span(
        self,
    ) -> None:
        placement = _enclosing_support_placement(
            frame_count=3,
            observed_direction_half_width_degrees=4.0,
        )
        output = output_footprint_from_template_placement(
            placement,
            project_selected_placement(placement),
            lane=_lane(),
            lane_ordinal=3,
            layout="horizontal",
        )
        protections = {
            item.role: item for item in output.boundary_protections
        }

        self.assertGreater(
            protections[BoundaryRole.TOP].local_boundary_residual_px,
            8.0,
        )
        self.assertGreater(
            protections[BoundaryRole.BOTTOM].local_boundary_residual_px,
            8.0,
        )

    def test_enclosing_support_uses_no_cross_bleed_and_keeps_per_side_limit(self) -> None:
        placement = _enclosing_support_placement()
        output = output_footprint_from_template_placement(
            placement,
            project_selected_placement(placement),
            lane=_lane(),
            lane_ordinal=1,
            layout="horizontal",
        )
        self.assertEqual(
            output.envelope.boundary_use,
            OutputBoundaryUse.ENCLOSING_SUPPORT_PAIR,
        )
        cross_protections = tuple(
            item
            for item in output.boundary_protections
            if item.role in {BoundaryRole.TOP, BoundaryRole.BOTTOM}
        )
        self.assertTrue(all(item.bleed_px == 0.0 for item in cross_protections))
        assessment = template_direct_use_budget_assessment(placement, output)
        self.assertEqual(assessment.state, EvidenceState.SUPPORTED)
        self.assertLessEqual(
            assessment.enclosing_support_height_ratio,
            OUTPUT_PROTECTION_SPEC.maximum_enclosing_support_height_ratio,
        )
        self.assertTrue(assessment.enclosing_support_within_limit)
        self.assertTrue(
            all(
                item.limit_applies
                for item in assessment.edge_assessments
                if item.role in {BoundaryRole.TOP, BoundaryRole.BOTTOM}
            )
        )

    def test_exact_enclosing_height_still_needs_per_side_sampling_headroom(self) -> None:
        placement = _enclosing_support_placement(support_span_px=264.0)
        output = output_footprint_from_template_placement(
            placement,
            project_selected_placement(placement),
            lane=_lane(),
            lane_ordinal=1,
            layout="horizontal",
        )

        assessment = template_direct_use_budget_assessment(placement, output)

        self.assertEqual(assessment.state, EvidenceState.CONTRADICTED)
        self.assertLessEqual(
            assessment.enclosing_support_height_ratio,
            OUTPUT_PROTECTION_SPEC.maximum_enclosing_support_height_ratio,
        )
        self.assertTrue(assessment.enclosing_support_within_limit)

    def test_enclosing_height_ratio_does_not_mix_alternative_support_positions(
        self,
    ) -> None:
        placement = _enclosing_support_placement(
            frame_count=2,
            support_span_px=259.0,
            support_position_uncertainty_px=2.5,
        )
        output = output_footprint_from_template_placement(
            placement,
            project_selected_placement(placement),
            lane=_lane(),
            lane_ordinal=2,
            layout="horizontal",
        )

        assessment = template_direct_use_budget_assessment(placement, output)

        self.assertEqual(assessment.state, EvidenceState.CONTRADICTED)
        self.assertAlmostEqual(
            assessment.enclosing_support_height_ratio,
            OUTPUT_PROTECTION_SPEC.maximum_enclosing_support_height_ratio,
        )
        self.assertTrue(assessment.enclosing_support_within_limit)

    def test_selected_placement_produces_supported_output_footprint(self) -> None:
        placement = _placement()
        output = output_footprint_from_template_placement(
            placement,
            project_selected_placement(placement),
            lane=_lane(),
            lane_ordinal=1,
            layout="horizontal",
        )
        self.assertEqual(
            output.envelope.canonical_source_footprint,
            placement.frames[0].canonical_source_polygon,
        )
        self.assertEqual(output.saturation_facts, ())
        assessment = template_direct_use_budget_assessment(
            placement,
            output,
        )
        self.assertEqual(assessment.state, EvidenceState.SUPPORTED)
        self.assertEqual(
            tuple(item.role for item in assessment.edge_assessments),
            (
                BoundaryRole.START,
                BoundaryRole.END,
                BoundaryRole.TOP,
                BoundaryRole.BOTTOM,
            ),
        )
        self.assertEqual(assessment.geometry_id, output.geometry_id)

    def test_lane_overflow_is_explicit_and_never_clipped(self) -> None:
        placement = _placement()
        lane = _lane()
        lane = replace(
            lane,
            domain=replace(lane.domain, work_box=Box(0, 20, 500, 400)),
        )
        output = output_footprint_from_template_placement(
            placement,
            project_selected_placement(placement),
            lane=lane,
            lane_ordinal=1,
            layout="horizontal",
        )
        self.assertIn(
            AuthoritySide.TOP,
            tuple(item.authority_side for item in output.saturation_facts),
        )
        self.assertLess(
            min(point[1] for point in output.required_source_footprint),
            float(lane.domain.work_box.top),
        )
        self.assertFalse(hasattr(output, "mapped_output_box"))
        assessment = template_direct_use_budget_assessment(
            placement,
            output,
        )
        self.assertEqual(assessment.state, EvidenceState.SUPPORTED)
        self.assertTrue(all(item.within_limit for item in assessment.edge_assessments))

    def test_source_footprint_is_safe_without_output_transform(self) -> None:
        placement = _placement()
        output = output_footprint_from_template_placement(
            placement,
            project_selected_placement(placement),
            lane=_lane(),
            lane_ordinal=1,
            layout="horizontal",
        )

        self.assertEqual(output.saturation_facts, ())
        self.assertFalse(hasattr(output, "sampling_source_footprint"))
        self.assertFalse(hasattr(output, "mapped_output_box"))

    def test_joint_measurement_expansion_above_five_percent_is_rejected(self) -> None:
        placement = _placement()
        cross = replace(
            placement.cross_fit,
            top_full_interval_px=FiniteInterval(-20.0, 10.0),
            bottom_full_interval_px=FiniteInterval(220.0, 250.0),
        )
        placement = replace(placement, cross_fit=cross)
        output = output_footprint_from_template_placement(
            placement,
            project_selected_placement(placement),
            lane=_lane(),
            lane_ordinal=1,
            layout="horizontal",
        )
        assessment = template_direct_use_budget_assessment(placement, output)
        self.assertEqual(assessment.state, EvidenceState.CONTRADICTED)
        top = next(
            item
            for item in assessment.edge_assessments
            if item.role == BoundaryRole.TOP
        )
        self.assertFalse(top.within_limit)

    def test_local_cross_departure_is_retained_in_output_budget(self) -> None:
        template = _template(1)
        sequence = _sequence(template)
        cross = _cross(template, direction=_direction())
        top, bottom = cross.direct_bindings
        top = replace(
            top,
            canonical_direction_degrees=0.15,
            fit_direction_interval_degrees=FiniteInterval(0.12, 0.18),
            full_direction_interval_degrees=FiniteInterval(0.10, 0.20),
            observed_direction_interval_degrees=FiniteInterval(0.10, 0.20),
            trace_position_intervals_px=(
                FiniteInterval.exact(10.0),
                FiniteInterval.exact(10.0),
                FiniteInterval(8.0, 10.0),
            ),
        )
        bottom = replace(
            bottom,
            canonical_direction_degrees=-0.05,
            fit_direction_interval_degrees=FiniteInterval(-0.08, -0.02),
            full_direction_interval_degrees=FiniteInterval(-0.10, 0.00),
            observed_direction_interval_degrees=FiniteInterval(-0.10, 0.00),
            trace_position_intervals_px=(
                FiniteInterval.exact(250.0),
                FiniteInterval.exact(250.0),
                FiniteInterval(250.0, 252.0),
            ),
        )
        local_direction = replace(
            _direction(),
            direction_id="direction:local-cross-departure",
            selected_observation_ids=(top.observation_id, bottom.observation_id),
            full_angle_interval_degrees=FiniteInterval(-0.10, 0.20),
            observed_angle_interval_degrees=FiniteInterval(-0.10, 0.20),
            canonical_angle_degrees=0.05,
        )
        cross = replace(
            cross,
            direct_bindings=(top, bottom),
            selected_direction=local_direction,
            independent_support_region_count=2,
            longitudinal_support_domain_count=2,
            role_authorized_pair_support_domain_count=2,
        )
        placement = _compose(
            template,
            sequence,
            cross,
        )
        output = output_footprint_from_template_placement(
            placement,
            project_selected_placement(placement),
            lane=_lane(),
            lane_ordinal=1,
            layout="horizontal",
        )

        protections = {
            item.role: item for item in output.boundary_protections
        }
        self.assertGreater(
            max(
                protections[BoundaryRole.TOP].local_boundary_residual_px,
                protections[BoundaryRole.BOTTOM].local_boundary_residual_px,
            ),
            1.0,
        )
        assessment = template_direct_use_budget_assessment(placement, output)
        budget = {item.role: item for item in assessment.edge_assessments}
        self.assertGreaterEqual(
            max(
                budget[BoundaryRole.TOP].expansion_px,
                budget[BoundaryRole.BOTTOM].expansion_px,
            ),
            max(
                protections[BoundaryRole.TOP].local_boundary_residual_px,
                protections[BoundaryRole.BOTTOM].local_boundary_residual_px,
            ),
        )

    def test_sequence_line_departure_protects_axis_aligned_output(self) -> None:
        template = _template(1)
        sequence = _sequence(template)
        bindings = list(sequence.role_bindings)
        binding = bindings[1]
        assert binding is not None
        bindings[1] = replace(
            binding,
            line_evidence=SequenceRoleLineEvidence(
            observation_id=binding.observation_id,
            reference_trace_px=130.0,
            fit_position_interval_px=FiniteInterval.exact(200.0),
            fit_direction_interval_degrees=FiniteInterval.exact(-1.0),
            ),
        )
        sequence = replace(sequence, role_bindings=tuple(bindings))
        placement = _compose(
            template,
            sequence,
            _cross(template, direction=_direction()),
        )
        output = output_footprint_from_template_placement(
            placement,
            project_selected_placement(placement),
            lane=_lane(),
            lane_ordinal=1,
            layout="horizontal",
        )
        end = next(
            item
            for item in output.boundary_protections
            if item.role == BoundaryRole.END
        )

        self.assertGreater(placement.frames[0].end.local_outward_departure_px, 2.0)
        self.assertAlmostEqual(
            end.local_boundary_residual_px,
            placement.frames[0].end.local_outward_departure_px + 1.0,
        )
        self.assertTrue(
            all(
                frame.start.line.normal_x == 1.0
                and frame.start.line.normal_y == 0.0
                and frame.end.line.normal_x == 1.0
                and frame.end.line.normal_y == 0.0
                for frame in placement.frames
            )
        )

    def test_sequence_line_extent_already_in_full_interval_is_not_added_twice(
        self,
    ) -> None:
        template = _template(1)
        sequence = _sequence(template)
        bindings = list(sequence.role_bindings)
        binding = bindings[1]
        assert binding is not None
        bindings[1] = replace(
            binding,
            full_position_interval_px=FiniteInterval(200.0, 204.0),
        )
        sequence = replace(sequence, role_bindings=tuple(bindings))
        baseline = _compose(
            template,
            sequence,
            _cross(template, direction=_direction()),
        ).frames[0].end.local_outward_departure_px
        bindings = list(sequence.role_bindings)
        binding = bindings[1]
        assert binding is not None
        bindings[1] = replace(
            binding,
            line_evidence=SequenceRoleLineEvidence(
            observation_id=binding.observation_id,
            reference_trace_px=130.0,
            fit_position_interval_px=FiniteInterval.exact(200.0),
            fit_direction_interval_degrees=FiniteInterval.exact(-1.0),
            ),
        )
        sequence = replace(sequence, role_bindings=tuple(bindings))
        placement = _compose(
            template,
            sequence,
            _cross(template, direction=_direction()),
        )

        self.assertAlmostEqual(
            placement.frames[0].end.local_outward_departure_px,
            baseline,
        )

    def test_inferred_fixed_width_edge_inherits_shifted_line_safety(self) -> None:
        template = _template(1)
        sequence = _sequence(template, missing=(1,))
        bindings = list(sequence.role_bindings)
        binding = bindings[0]
        assert binding is not None
        bindings[0] = replace(
            binding,
            line_evidence=SequenceRoleLineEvidence(
            observation_id=binding.observation_id,
            reference_trace_px=130.0,
            fit_position_interval_px=FiniteInterval.exact(100.0),
            fit_direction_interval_degrees=FiniteInterval.exact(-1.0),
            ),
        )
        sequence = replace(sequence, role_bindings=tuple(bindings))
        placement = _compose(
            template,
            sequence,
            _cross(template, direction=_direction()),
        )

        self.assertEqual(
            placement.frames[0].end.position_source.value,
            "inferred_sequence",
        )
        self.assertGreater(
            placement.frames[0].end.local_outward_departure_px,
            2.0,
        )

    def test_cross_position_and_trace_residual_share_one_state(self) -> None:
        template = _template(1)
        cross = _cross(template, direction=_direction())
        top, bottom = cross.direct_bindings
        top = replace(
            top,
            coordinate_interval_px=FiniteInterval(8.0, 10.0),
            fit_interval_px=FiniteInterval(8.0, 10.0),
            full_interval_px=FiniteInterval(8.0, 10.0),
            fit_direction_interval_degrees=FiniteInterval.exact(0.0),
            full_direction_interval_degrees=FiniteInterval.exact(0.0),
            observed_direction_interval_degrees=FiniteInterval.exact(0.0),
            trace_position_intervals_px=(
                FiniteInterval.exact(8.0),
                FiniteInterval.exact(8.0),
                FiniteInterval.exact(8.0),
            ),
        )
        bottom = replace(
            bottom,
            coordinate_interval_px=FiniteInterval(248.0, 250.0),
            fit_interval_px=FiniteInterval(248.0, 250.0),
            full_interval_px=FiniteInterval(248.0, 250.0),
            fit_direction_interval_degrees=FiniteInterval.exact(0.0),
            full_direction_interval_degrees=FiniteInterval.exact(0.0),
            observed_direction_interval_degrees=FiniteInterval.exact(0.0),
            trace_position_intervals_px=(
                FiniteInterval.exact(250.0),
                FiniteInterval.exact(250.0),
                FiniteInterval.exact(250.0),
            ),
        )
        cross = replace(
            cross,
            top_fit_interval_px=FiniteInterval(8.0, 10.0),
            bottom_fit_interval_px=FiniteInterval(248.0, 250.0),
            top_full_interval_px=FiniteInterval(8.0, 10.0),
            bottom_full_interval_px=FiniteInterval(248.0, 250.0),
            direct_bindings=(top, bottom),
        )
        placement = _compose(template, _sequence(template), cross)
        output = output_footprint_from_template_placement(
            placement,
            project_selected_placement(placement),
            lane=_lane(),
            lane_ordinal=1,
            layout="horizontal",
        )
        protection = next(
            item
            for item in output.boundary_protections
            if item.role == BoundaryRole.TOP
        )

        self.assertAlmostEqual(protection.measurement_expansion_px, 2.0)
        self.assertAlmostEqual(protection.local_boundary_residual_px, 3.0)
        self.assertAlmostEqual(protection.joint_expansion_px, 5.5)

    def test_native_direct_interval_is_retained_before_bleed(self) -> None:
        template = replace(
            _template(1),
            frame_width_px=FiniteInterval(90.0, 110.0),
        )
        sequence = _sequence(template)
        bindings = list(sequence.role_bindings)
        binding = bindings[1]
        assert binding is not None
        bindings[1] = replace(
            binding,
            full_position_interval_px=FiniteInterval(200.0, 210.0),
        )
        sequence = replace(sequence, role_bindings=tuple(bindings))
        placement = _compose(
            template,
            sequence,
            _cross(template, direction=_direction()),
        )
        output = output_footprint_from_template_placement(
            placement,
            project_selected_placement(placement),
            lane=_lane(),
            lane_ordinal=1,
            layout="horizontal",
        )
        end = next(
            item
            for item in output.boundary_protections
            if item.role == BoundaryRole.END
        )
        self.assertGreaterEqual(end.measurement_expansion_px, 9.9)
        self.assertGreater(end.joint_expansion_px, end.measurement_expansion_px)

    def test_final_footprint_retains_the_complete_pixel_center_span(self) -> None:
        template = _template(1)
        placement = _compose(
            template,
            _sequence(template),
            _cross(template, direction=_direction()),
        )
        output = output_footprint_from_template_placement(
            placement,
            project_selected_placement(placement),
            lane=_lane(),
            lane_ordinal=1,
            layout="horizontal",
        )

        self.assertTrue(
            all(
                item.local_boundary_residual_px >= 1.0
                for item in output.boundary_protections
            )
        )
        self.assertEqual(
            template_direct_use_budget_assessment(placement, output).state,
            EvidenceState.SUPPORTED,
        )

    def test_inferred_edge_does_not_inherit_remote_direct_interval(self) -> None:
        template = replace(
            _template(2),
            frame_width_px=FiniteInterval(96.0, 104.0),
        )
        sequence = _sequence(template, missing=(3,))
        intervals = list(sequence.model_full_role_intervals_px)
        intervals[1] = FiniteInterval(200.0, 210.0)
        sequence = replace(
            sequence,
            model_full_role_intervals_px=tuple(intervals),
        )
        placement = _compose(
            template,
            sequence,
            _cross(template, direction=_direction()),
        )
        self.assertEqual(
            placement.frames[1].end.position_source.value,
            "inferred_sequence",
        )
        self.assertEqual(
            placement.frames[1].end.full_position_interval_px,
            FiniteInterval(316.0, 324.0),
        )
        output = output_footprint_from_template_placement(
            placement,
            project_selected_placement(placement),
            lane=_lane(),
            lane_ordinal=2,
            layout="horizontal",
        )
        end = next(
            item
            for item in output.boundary_protections
            if item.role == BoundaryRole.END
        )
        self.assertLess(end.local_boundary_residual_px, 3.0)

    def test_inferred_frame_does_not_inherit_remote_model_residual(self) -> None:
        template = replace(
            _template(4),
            frame_width_px=FiniteInterval(96.0, 104.0),
        )
        sequence = _sequence(template, missing=(4, 5))
        intervals = list(sequence.model_full_role_intervals_px)
        # A remote direct-model departure must not be copied into an inferred
        # frame. Its joint model interval already owns all placement uncertainty.
        intervals[0] = FiniteInterval(70.0, 100.0)
        intervals[2] = FiniteInterval(215.0, 220.0)
        intervals[3] = FiniteInterval(320.0, 325.0)
        intervals[6] = FiniteInterval(454.0, 460.0)
        intervals[7] = FiniteInterval(560.0, 566.0)
        sequence = replace(
            sequence,
            model_full_role_intervals_px=tuple(intervals),
        )
        placement = _compose(
            template,
            sequence,
            _cross(template, direction=_direction()),
        )
        output = output_footprint_from_template_placement(
            placement,
            project_selected_placement(placement),
            lane=_lane(),
            lane_ordinal=3,
            layout="horizontal",
        )
        protections = {item.role: item for item in output.boundary_protections}

        for role, boundary in (
            (BoundaryRole.START, placement.frames[2].start),
            (BoundaryRole.END, placement.frames[2].end),
        ):
            self.assertAlmostEqual(
                protections[role].local_boundary_residual_px,
                boundary.local_outward_departure_px + 1.0,
            )

    def test_selected_frame_residual_still_obeys_five_percent_limit(self) -> None:
        template = replace(
            _template(1),
            frame_width_px=FiniteInterval(70.0, 130.0),
            nominal_gap_px=FiniteInterval(0.0, 50.0),
        )
        sequence = _sequence(template)
        bindings = list(sequence.role_bindings)
        binding = bindings[1]
        assert binding is not None
        bindings[1] = replace(
            binding,
            full_position_interval_px=FiniteInterval(200.0, 230.0),
        )
        sequence = replace(sequence, role_bindings=tuple(bindings))
        placement = _compose(
            template,
            sequence,
            _cross(template, direction=_direction()),
        )
        output = output_footprint_from_template_placement(
            placement,
            project_selected_placement(placement),
            lane=_lane(),
            lane_ordinal=1,
            layout="horizontal",
        )
        assessment = template_direct_use_budget_assessment(placement, output)
        self.assertEqual(assessment.state, EvidenceState.CONTRADICTED)
        end = next(
            item for item in assessment.edge_assessments
            if item.role == BoundaryRole.END
        )
        self.assertFalse(end.within_limit)

    def test_mismatched_lane_and_nonselected_geometry_are_rejected(self) -> None:
        placement = _placement()
        with self.assertRaises(ValueError):
            output_footprint_from_template_placement(
                placement,
                project_selected_placement(placement),
                lane=_lane("lane:other"),
                lane_ordinal=1,
                layout="horizontal",
            )
        output = output_footprint_from_template_placement(
            placement,
            project_selected_placement(placement),
            lane=_lane(),
            lane_ordinal=1,
            layout="horizontal",
        )
        tampered = replace(
            output,
            envelope=replace(output.envelope, placement_id="placement:other"),
        )
        with self.assertRaises(ValueError):
            template_direct_use_budget_assessment(
                placement,
                tampered,
            )

    def test_invalid_ordinal_fails_without_fallback(self) -> None:
        placement = _placement()
        with self.assertRaises(ValueError):
            output_footprint_from_template_placement(
                placement,
                project_selected_placement(placement),
                lane=_lane(),
                lane_ordinal=0,
                layout="horizontal",
            )

    def test_api_is_current_only_and_ratios_are_frozen(self) -> None:
        self.assertEqual(
            tuple(
                inspect.signature(
                    output_footprint_from_template_placement
                ).parameters
            ),
            (
                "placement",
                "projection",
                "lane",
                "lane_ordinal",
                "layout",
            ),
        )
        self.assertEqual(
            tuple(
                inspect.signature(
                    template_direct_use_budget_assessment
                ).parameters
            ),
            ("placement", "output"),
        )
        self.assertEqual(
            OUTPUT_PROTECTION_SPEC.maximum_expansion_ratio_per_side,
            0.05,
        )
        self.assertEqual(OUTPUT_PROTECTION_SPEC.cross_bleed_mm, 0.25)
        self.assertAlmostEqual(
            OUTPUT_PROTECTION_SPEC.sequence_bleed_mm(36.0),
            0.252,
        )
        path = (
            Path(__file__).parents[2]
            / "x5crop/detection/photo_geometry/template_output.py"
        )
        source = path.read_text()
        tree = ast.parse(source)
        modules = tuple(
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        )
        forbidden = (
            "chains",
            "fixed_frame_geometry",
            "candidate_sampling",
            "materialization",
            "selection",
            "cache",
            "frame_footprints",
            "corridors",
        )
        self.assertFalse(
            any(token in module for token in forbidden for module in modules)
        )
        self.assertNotIn("UNAVAILABLE", source)


if __name__ == "__main__":
    unittest.main()
