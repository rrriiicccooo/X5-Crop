from __future__ import annotations

import ast
from dataclasses import replace
import inspect
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
from x5crop.geometry.affine import AffineCoordinateTransform
from x5crop.detection.evidence.scan_canvas import (
    CanvasAxisScaleIntervals,
    ScanCanvasEvidence,
    ScanCanvasOutcome,
    ScanCanvasProfileMatch,
)
from x5crop.detection.photo_geometry.model import AuthoritySide, BoundaryRole
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
from x5crop.detection.source_core import (
    SourceLaneEvidence,
    SourceStripValidationDomain,
)
from tools.tests.test_template_placement_contract import (
    _compose,
    _binding,
    _cross,
    _direction,
    _sequence,
    _template,
)


def _placement():
    template = _template(1)
    direction = _direction()
    return _compose(
        template,
        _sequence(template),
        _cross(template, direction=direction),
    )


def _enclosing_support_placement(*, support_span_px: float = 250.0):
    template = _template(1)
    direction = _direction()
    support_center = 152.0
    support_top = support_center - support_span_px / 2.0
    support_bottom = support_center + support_span_px / 2.0
    top = _binding(BoundaryRole.TOP, "support-top", support_top)
    bottom = _binding(BoundaryRole.BOTTOM, "support-bottom", support_bottom)
    support = EnclosingSupportPair(
        top_canonical_px=support_top,
        bottom_canonical_px=support_bottom,
        top_full_interval_px=FiniteInterval.exact(support_top),
        bottom_full_interval_px=FiniteInterval.exact(support_bottom),
        top_provenance_ids=(top.observation_id,),
        bottom_provenance_ids=(bottom.observation_id,),
        observed_span_px=FiniteInterval.exact(support_span_px),
        reference_trace_px=150.0,
        trace_coordinates_px=(0, 150, 300),
        top_trace_intervals_px=tuple(
            FiniteInterval.exact(support_top) for _ in range(3)
        ),
        bottom_trace_intervals_px=tuple(
            FiniteInterval.exact(support_bottom) for _ in range(3)
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
        center_compatible=True,
        boundary_use=OutputBoundaryUse.ENCLOSING_SUPPORT_PAIR,
        enclosing_support_pair=support,
    )
    return _compose(template, _sequence(template), cross, direction=direction)


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
    def test_enclosing_support_uses_no_cross_bleed_and_its_own_height_limit(self) -> None:
        placement = _enclosing_support_placement()
        output = output_footprint_from_template_placement(
            placement,
            project_selected_placement(placement),
            lane=_lane(),
            lane_ordinal=1,
            layout="horizontal",
            transform=AffineCoordinateTransform.identity(500, 400),
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
                not item.limit_applies
                for item in assessment.edge_assessments
                if item.role in {BoundaryRole.TOP, BoundaryRole.BOTTOM}
            )
        )

    def test_enclosing_support_at_exact_height_limit_remains_supported(self) -> None:
        placement = _enclosing_support_placement(support_span_px=264.0)
        output = output_footprint_from_template_placement(
            placement,
            project_selected_placement(placement),
            lane=_lane(),
            lane_ordinal=1,
            layout="horizontal",
            transform=AffineCoordinateTransform.identity(500, 400),
        )

        assessment = template_direct_use_budget_assessment(placement, output)

        self.assertEqual(assessment.state, EvidenceState.SUPPORTED)
        self.assertLessEqual(
            assessment.enclosing_support_height_ratio,
            OUTPUT_PROTECTION_SPEC.maximum_enclosing_support_height_ratio,
        )
        self.assertTrue(assessment.enclosing_support_within_limit)

    def test_selected_placement_produces_supported_output_footprint(self) -> None:
        placement = _placement()
        transform = AffineCoordinateTransform.identity(500, 400)
        output = output_footprint_from_template_placement(
            placement,
            project_selected_placement(placement),
            lane=_lane(),
            lane_ordinal=1,
            layout="horizontal",
            transform=transform,
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
        self.assertEqual(
            assessment.placement_solution_ids,
            (placement.placement_id,),
        )
        self.assertTrue(
            all(
                item.worst_placement_solution_id == placement.placement_id
                for item in assessment.edge_assessments
            )
        )

    def test_lane_overflow_is_explicit_and_never_clipped(self) -> None:
        placement = _placement()
        lane = _lane()
        lane = replace(
            lane,
            domain=replace(lane.domain, work_box=Box(0, 20, 500, 400)),
        )
        transform = AffineCoordinateTransform.identity(500, 400)
        output = output_footprint_from_template_placement(
            placement,
            project_selected_placement(placement),
            lane=lane,
            lane_ordinal=1,
            layout="horizontal",
            transform=transform,
        )
        self.assertIn(
            AuthoritySide.TOP,
            tuple(item.authority_side for item in output.saturation_facts),
        )
        self.assertLess(
            min(point[1] for point in output.required_source_footprint),
            float(lane.domain.work_box.top),
        )
        self.assertIsNone(output.mapped_output_box)
        assessment = template_direct_use_budget_assessment(
            placement,
            output,
        )
        self.assertEqual(assessment.state, EvidenceState.SUPPORTED)
        self.assertTrue(all(item.within_limit for item in assessment.edge_assessments))

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
            transform=AffineCoordinateTransform.identity(500, 400),
        )
        assessment = template_direct_use_budget_assessment(placement, output)
        self.assertEqual(assessment.state, EvidenceState.CONTRADICTED)
        top = next(
            item
            for item in assessment.edge_assessments
            if item.role == BoundaryRole.TOP
        )
        self.assertFalse(top.within_limit)

    def test_selected_frame_residual_is_retained_before_bleed(self) -> None:
        template = _template(1)
        sequence = _sequence(template)
        intervals = list(sequence.role_full_position_intervals_px)
        intervals[1] = FiniteInterval(200.0, 210.0)
        sequence = replace(
            sequence,
            role_full_position_intervals_px=tuple(intervals),
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
            lane_ordinal=1,
            layout="horizontal",
            transform=AffineCoordinateTransform.identity(500, 400),
        )
        end = next(
            item
            for item in output.boundary_protections
            if item.role == BoundaryRole.END
        )
        self.assertGreaterEqual(end.local_boundary_residual_px, 9.9)
        self.assertGreater(end.joint_expansion_px, end.local_boundary_residual_px)
        self.assertEqual(
            template_direct_use_budget_assessment(placement, output).state,
            EvidenceState.SUPPORTED,
        )

    def test_inferred_edge_retains_same_role_selected_fit_residual(self) -> None:
        template = replace(
            _template(2),
            frame_width_px=FiniteInterval(96.0, 104.0),
        )
        sequence = _sequence(template, missing=(3,))
        intervals = list(sequence.role_full_position_intervals_px)
        intervals[1] = FiniteInterval(200.0, 210.0)
        sequence = replace(
            sequence,
            role_full_position_intervals_px=tuple(intervals),
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
            transform=AffineCoordinateTransform.identity(500, 400),
        )
        end = next(
            item
            for item in output.boundary_protections
            if item.role == BoundaryRole.END
        )
        self.assertGreaterEqual(end.local_boundary_residual_px, 9.9)

    def test_inferred_frame_does_not_add_width_twice(self) -> None:
        template = replace(
            _template(4),
            frame_width_px=FiniteInterval(96.0, 104.0),
        )
        sequence = _sequence(template, missing=(4, 5))
        intervals = list(sequence.role_full_position_intervals_px)
        # A remote first-frame outlier must not be copied into frame 3.  The
        # nearest direct START/END facts on both sides bound the local straight
        # residual. W already belongs to the joint state and is not added again.
        intervals[0] = FiniteInterval(70.0, 100.0)
        intervals[2] = FiniteInterval(215.0, 220.0)
        intervals[3] = FiniteInterval(320.0, 325.0)
        intervals[6] = FiniteInterval(454.0, 460.0)
        intervals[7] = FiniteInterval(560.0, 566.0)
        sequence = replace(
            sequence,
            role_full_position_intervals_px=tuple(intervals),
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
            transform=AffineCoordinateTransform.identity(700, 400),
        )
        protections = {item.role: item for item in output.boundary_protections}

        self.assertLess(
            protections[BoundaryRole.START].local_boundary_residual_px,
            10.0,
        )
        self.assertAlmostEqual(
            protections[BoundaryRole.END].local_boundary_residual_px,
            6.0,
        )

    def test_selected_frame_residual_still_obeys_five_percent_limit(self) -> None:
        template = _template(1)
        sequence = _sequence(template)
        intervals = list(sequence.role_full_position_intervals_px)
        intervals[1] = FiniteInterval(200.0, 230.0)
        sequence = replace(
            sequence,
            role_full_position_intervals_px=tuple(intervals),
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
            lane_ordinal=1,
            layout="horizontal",
            transform=AffineCoordinateTransform.identity(500, 400),
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
        transform = AffineCoordinateTransform.identity(500, 400)
        with self.assertRaises(ValueError):
            output_footprint_from_template_placement(
                placement,
                project_selected_placement(placement),
                lane=_lane("lane:other"),
                lane_ordinal=1,
                layout="horizontal",
                transform=transform,
            )
        output = output_footprint_from_template_placement(
            placement,
            project_selected_placement(placement),
            lane=_lane(),
            lane_ordinal=1,
            layout="horizontal",
            transform=transform,
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

    def test_invalid_ordinal_and_output_extent_fail_without_fallback(self) -> None:
        placement = _placement()
        with self.assertRaises(ValueError):
            output_footprint_from_template_placement(
                placement,
                project_selected_placement(placement),
                lane=_lane(),
                lane_ordinal=0,
                layout="horizontal",
                transform=AffineCoordinateTransform.identity(500, 400),
            )
        with self.assertRaises(ValueError):
            output_footprint_from_template_placement(
                placement,
                project_selected_placement(placement),
                lane=_lane(),
                lane_ordinal=1,
                layout="horizontal",
                transform=AffineCoordinateTransform.identity(150, 150),
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
                "transform",
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
