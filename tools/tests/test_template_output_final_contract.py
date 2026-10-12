from __future__ import annotations

import ast, inspect, unittest
from dataclasses import replace
from pathlib import Path
from x5crop.domain import EvidenceState, FiniteInterval
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.template_output import (
    _footprint,
    output_footprint_from_template_placement,
    template_direct_use_budget_assessment,
)
from x5crop.detection.photo_geometry.template_feasible_geometry import project_format_placement
from x5crop.detection.photo_geometry.line_observations import PhysicalLineRegion
from x5crop.detection.photo_geometry.template_model import SequenceRoleLineEvidence
from tools.tests.template_test_support import (
    placement_compose as _compose,
    placement_cross as _cross,
    placement_direction as _direction,
    placement_sequence as _sequence,
    placement_template as _template,
)
from tools.tests.output_fixture_support import _lane, _placement


class TemplateOutputFinalContractTest(unittest.TestCase):
    def test_empty_native_physical_slice_cannot_fall_back_to_statistical_fit(self) -> None:
        template = _template(1)
        sequence = _sequence(template)
        start = sequence.role_bindings[0]
        assert start is not None
        start = replace(start, full_position_interval_px=FiniteInterval(90.0, 100.0),
                        line_evidence=SequenceRoleLineEvidence(
                            start.observation_id, 130.0, FiniteInterval.exact(100.0), FiniteInterval.exact(0.0),
                            PhysicalLineRegion(130.0, ((90.0, 0.0),)),
                        ))
        sequence = replace(sequence, role_bindings=(start, sequence.role_bindings[1]))
        placement = _compose(template, sequence, _cross(template))
        with self.assertRaisesRegex(ValueError, "physical line contradicts native reachable"):
            _footprint(placement, placement.frames[0], project_format_placement(placement), apply_residual=True)

    def test_native_direct_interval_is_retained_before_fixed_output(self) -> None:
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
            project_format_placement(placement),
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
        self.assertGreater(end.required_expansion_px, end.measurement_expansion_px)

    def test_final_footprint_retains_the_complete_pixel_center_span(self) -> None:
        template = _template(1)
        placement = _compose(
            template,
            _sequence(template),
            _cross(template, direction=_direction()),
        )
        output = output_footprint_from_template_placement(
            placement,
            project_format_placement(placement),
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
            project_format_placement(placement),
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
            project_format_placement(placement),
            lane=_lane(),
            lane_ordinal=3,
            layout="horizontal",
        )
        protections = {item.role: item for item in output.boundary_protections}

        for role, boundary in (
            (BoundaryRole.START, placement.frames[2].start),
            (BoundaryRole.END, placement.frames[2].end),
        ):
            self.assertIsNone(boundary.line_evidence)
            self.assertLess(protections[role].local_boundary_residual_px, 2.0)

    def test_selected_frame_residual_stays_inside_the_fixed_window(self) -> None:
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
            project_format_placement(placement),
            lane=_lane(),
            lane_ordinal=1,
            layout="horizontal",
        )
        assessment = template_direct_use_budget_assessment(placement, output)
        self.assertEqual(assessment.state, EvidenceState.SUPPORTED)
        end = next(
            item for item in assessment.edge_assessments
            if item.role == BoundaryRole.END
        )
        self.assertTrue(end.within_limit)

    def test_mismatched_lane_and_nonselected_geometry_are_rejected(self) -> None:
        placement = _placement()
        with self.assertRaises(ValueError):
            output_footprint_from_template_placement(
                placement,
                project_format_placement(placement),
                lane=_lane("lane:other"),
                lane_ordinal=1,
                layout="horizontal",
            )
        output = output_footprint_from_template_placement(
            placement,
            project_format_placement(placement),
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
                project_format_placement(placement),
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
            _placement().source_scan_geometry.fixed_output_size.margin_ratio_per_side,
            0.05,
        )
        path = (
            Path(__file__).parents[2]
            / "x5crop/detection/photo_geometry/template_output.py"
        )
        source = path.read_text()
        self.assertNotIn("apply_bleed", source)
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
