from __future__ import annotations

import math, unittest
from dataclasses import replace
from types import SimpleNamespace
from x5crop.domain import FiniteInterval
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.output_model import OutputBoundaryUse
from x5crop.detection.photo_geometry.template_cross_model import CrossLineProjectionBasis
from x5crop.detection.photo_geometry.template_output import (
    _footprint,
    _frame_boundary_residuals,
    _state_footprint,
    output_footprint_from_template_placement,
    template_direct_use_budget_assessment,
)
from x5crop.detection.photo_geometry.template_feasible_geometry import (
    JointFrameState,
    project_format_placement,
)
from x5crop.geometry.convex import convex_hull
from x5crop.detection.photo_geometry.line_observations import PhysicalLineRegion
from x5crop.detection.photo_geometry.template_model import SequenceRoleLineEvidence
from tools.tests.template_test_support import (
    placement_compose as _compose,
    placement_cross as _cross,
    placement_direction as _direction,
    placement_sequence as _sequence,
    placement_template as _template,
)
from tools.tests.output_fixture_support import _lane


class TemplateOutputReprojectionContractTest(unittest.TestCase):
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
        )
        placement = _compose(
            template,
            sequence,
            cross,
        )
        output = output_footprint_from_template_placement(
            placement,
            project_format_placement(placement),
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
        self.assertGreater(
            max(
                budget[BoundaryRole.TOP].required_extent_px,
                budget[BoundaryRole.BOTTOM].required_extent_px,
            ),
            120.0,
        )

    def test_retained_review_cross_uses_only_statistical_fit_projection(
            self,
        ) -> None:
        template = _template(3)
        cross = _cross(template, direction=_direction())
        top, bottom = cross.direct_bindings
        top = replace(
            top,
            canonical_direction_degrees=0.0,
            fit_direction_interval_degrees=FiniteInterval.exact(0.0),
            full_direction_interval_degrees=FiniteInterval(-1.0, 1.0),
            observed_direction_interval_degrees=FiniteInterval(-1.0, 1.0),
        )
        bottom = replace(
            bottom,
            canonical_direction_degrees=0.0,
            fit_direction_interval_degrees=FiniteInterval.exact(0.0),
            full_direction_interval_degrees=FiniteInterval.exact(0.0),
            observed_direction_interval_degrees=FiniteInterval.exact(0.0),
        )
        complete_cross = replace(
            cross,
            direct_bindings=(top, bottom),
            line_projection_basis=(
                CrossLineProjectionBasis.COMPLETE_PHYSICAL_DIRECTION
            ),
        )
        retained_cross = replace(
            complete_cross,
            line_projection_basis=(
                CrossLineProjectionBasis.RETAINED_REVIEW_STATISTICAL_FIT
            ),
        )
        complete_placement = _compose(
            template,
            _sequence(template),
            complete_cross,
        )
        retained_placement = _compose(
            template,
            _sequence(template),
            retained_cross,
        )

        def top_residual(placement) -> float:
            output = output_footprint_from_template_placement(
                placement,
                project_format_placement(placement),
                lane=_lane(),
                lane_ordinal=3,
                layout="horizontal",
            )
            return next(
                item.local_boundary_residual_px
                for item in output.boundary_protections
                if item.role == BoundaryRole.TOP
            )

        self.assertGreater(
            top_residual(complete_placement),
            top_residual(retained_placement),
        )
        self.assertNotEqual(
            complete_placement.placement_id,
            retained_placement.placement_id,
        )

    def test_opposite_side_projection_cannot_erase_uncovered_edge_position(self) -> None:
        template = _template(3)
        cross = _cross(template, direction=_direction())
        top, bottom = cross.direct_bindings
        top = replace(
            top,
            trace_coordinates_px=(0, 50, 100),
            canonical_direction_degrees=0.0,
            fit_direction_interval_degrees=FiniteInterval.exact(0.0),
            full_direction_interval_degrees=FiniteInterval.exact(0.0),
            observed_direction_interval_degrees=FiniteInterval.exact(0.0),
        )
        bottom = replace(
            bottom,
            trace_coordinates_px=(0, 200, 400),
            canonical_direction_degrees=1.0,
            fit_direction_interval_degrees=FiniteInterval.exact(1.0),
            full_direction_interval_degrees=FiniteInterval.exact(1.0),
            observed_direction_interval_degrees=FiniteInterval.exact(1.0),
        )
        direction = replace(
            _direction(),
            selected_observation_ids=(top.observation_id, bottom.observation_id),
            full_angle_interval_degrees=FiniteInterval(0.0, 1.0),
            observed_angle_interval_degrees=FiniteInterval(0.0, 1.0),
            canonical_angle_degrees=0.5,
        )
        cross = replace(
            cross,
            direct_bindings=(top, bottom),
            selected_direction=direction,
        )
        placement = _compose(template, _sequence(template), cross)
        frame = placement.frames[2]
        output = output_footprint_from_template_placement(
            placement,
            project_format_placement(placement),
            lane=_lane(),
            lane_ordinal=3,
            layout="horizontal",
        )
        protection = next(
            item
            for item in output.boundary_protections
            if item.role == BoundaryRole.TOP
        )
        projected_offset = frame.top.canonical_position_px - top.full_interval_px.center

        self.assertGreater(projected_offset, 4.0)
        self.assertGreaterEqual(
            protection.local_boundary_residual_px,
            projected_offset + 1.0,
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

        self.assertGreater(end.local_boundary_residual_px, 3.0)
        self.assertGreaterEqual(max(x for x, _ in output.mandatory_source_footprint),
                                200.0 + math.tan(math.radians(1.0)) * 120.0 + 1.0)
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
        template = replace(_template(1), frame_width_px=FiniteInterval(100.0, 104.0))
        sequence = _sequence(template)
        # Fix the representative width at 100 while allowing the native END
        # range to remain reachable under W; an exact W would exclude 204.
        sequence = replace(sequence, role_bindings=(sequence.role_bindings[0], replace(
            sequence.role_bindings[1], canonical_position_px=200.0,
            fit_position_interval_px=FiniteInterval.exact(200.0),
            full_position_interval_px=FiniteInterval.exact(200.0),
        )))
        bindings = list(sequence.role_bindings)
        binding = bindings[1]
        assert binding is not None
        bindings[1] = replace(
            binding,
            full_position_interval_px=FiniteInterval(200.0, 204.0),
        )
        sequence = replace(sequence, role_bindings=tuple(bindings))
        cross = _cross(template)
        cross = replace(cross, direct_bindings=tuple(replace(
            binding, fit_direction_interval_degrees=FiniteInterval.exact(0.0),
            full_direction_interval_degrees=FiniteInterval.exact(0.0),
            observed_direction_interval_degrees=FiniteInterval.exact(0.0),
        ) for binding in cross.direct_bindings))
        baseline_placement = _compose(template, sequence, cross)
        baseline = _footprint(baseline_placement, baseline_placement.frames[0],
                              project_format_placement(baseline_placement), apply_residual=True)
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
            cross,
        )

        actual = _footprint(placement, placement.frames[0],
                            project_format_placement(placement), apply_residual=True)
        self.assertEqual(actual, baseline)

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
        mandatory = _footprint(placement, placement.frames[0],
                               project_format_placement(placement), apply_residual=True)
        self.assertGreaterEqual(max(x for x, _ in mandatory),
                                200.0 + math.tan(math.radians(1.0)) * 120.0 + 1.0)

    def test_inferred_edge_keeps_width_and_direction_at_the_same_corner(
            self,
        ) -> None:
        for missing_index in (0, 1):
            for angle in (-2.0, 2.0):
                for full_padding in (0.0, 2.0, 6.0):
                    with self.subTest(
                        missing=missing_index,
                        angle=angle,
                        full_padding=full_padding,
                    ):
                        template = replace(
                            _template(1),
                            frame_width_px=FiniteInterval(90.0, 110.0),
                        )
                        sequence = _sequence(template, missing=(missing_index,))
                        bindings = list(sequence.role_bindings)
                        direct_index = 1 - missing_index
                        direct = bindings[direct_index]
                        assert direct is not None
                        coordinate = direct.canonical_position_px
                        bindings[direct_index] = replace(
                            direct,
                            full_position_interval_px=FiniteInterval(
                                coordinate - full_padding,
                                coordinate + full_padding,
                            ),
                            line_evidence=SequenceRoleLineEvidence(
                                observation_id=direct.observation_id,
                                reference_trace_px=130.0,
                                fit_position_interval_px=FiniteInterval.exact(
                                    coordinate
                                ),
                                fit_direction_interval_degrees=(
                                    FiniteInterval.exact(angle)
                                ),
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
                            project_format_placement(placement),
                            lane=_lane(),
                            lane_ordinal=1,
                            layout="horizontal",
                        )
                        # Each physical corner uses one W and one observed
                        # direction together. Width uncertainty cannot consume
                        # the line's additional departure from its own full
                        # position interval.
                        sign = -1 if missing_index == 0 else 1
                        corners = tuple(
                            coordinate
                            + sign * width
                            - math.tan(math.radians(angle)) * (trace - 130.0)
                            for width in (90.0, 110.0)
                            for trace in (10.0, 250.0)
                        )
                        boundary = (
                            placement.frames[0].start
                            if missing_index == 0
                            else placement.frames[0].end
                        )
                        actual = tuple(
                            point[0] for point in output.mandatory_source_footprint
                        )
                        if missing_index == 0:
                            self.assertLessEqual(min(actual), min(corners))
                        else:
                            self.assertGreaterEqual(max(actual), max(corners))
                        # Raster and small angular feedback cannot add W a
                        # second time.  Here their complete bound is <2 px.
                        if missing_index == 0:
                            self.assertGreater(min(actual), min(min(corners), boundary.full_position_interval_px.minimum) - 2.0)
                        else:
                            self.assertLess(max(actual), max(max(corners), boundary.full_position_interval_px.maximum) + 2.0)

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
            project_format_placement(placement),
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
        self.assertGreaterEqual(
            protection.required_expansion_px,
            protection.local_boundary_residual_px,
        )
        self.assertFalse(hasattr(protection, "joint_expansion_px"))

    def test_two_axis_line_protection_contains_their_joint_corner(self) -> None:
        template = replace(
            _template(1),
            frame_width_px=FiniteInterval.exact(3000.0),
            pitch_px=FiniteInterval.exact(3120.0),
            frame_height_px=FiniteInterval.exact(2000.0),
            phase_lattice_authority=replace(_template(1).phase_lattice_authority, period_px=3120.0),
        )
        slope = 0.05
        angle = math.degrees(math.atan(slope))
        sequence = _sequence(template)
        bindings = tuple(
            replace(
                binding,
                line_evidence=SequenceRoleLineEvidence(
                    observation_id=binding.observation_id,
                    reference_trace_px=1000.0,
                    fit_position_interval_px=binding.fit_position_interval_px,
                    fit_direction_interval_degrees=FiniteInterval.exact(-angle),
                ),
            )
            for binding in sequence.role_bindings
        )
        sequence = replace(sequence, role_bindings=bindings)
        cross = _cross(template, lane_reference=1500.0)
        cross = replace(
            cross,
            fixed_height_px=FiniteInterval.exact(2000.0),
            top_canonical_px=0.0,
            bottom_canonical_px=2000.0,
            top_fit_interval_px=FiniteInterval.exact(0.0),
            bottom_fit_interval_px=FiniteInterval.exact(2000.0),
            top_full_interval_px=FiniteInterval.exact(0.0),
            bottom_full_interval_px=FiniteInterval.exact(2000.0),
            direct_bindings=tuple(
                replace(
                    binding,
                    coordinate_interval_px=FiniteInterval.exact(position),
                    fit_interval_px=FiniteInterval.exact(position),
                    full_interval_px=FiniteInterval.exact(position),
                    canonical_direction_degrees=angle,
                    fit_direction_interval_degrees=FiniteInterval.exact(angle),
                    full_direction_interval_degrees=FiniteInterval.exact(angle),
                    observed_direction_interval_degrees=FiniteInterval.exact(angle),
                )
                for binding, position in zip(cross.direct_bindings, (0.0, 2000.0), strict=True)
            ),
        )
        placement = _compose(template, sequence, cross)
        projection = project_format_placement(placement)
        mandatory = _footprint(
            placement, placement.frames[0], projection, apply_residual=True,
        )
        # x=3100+.05(y-1000), y=2000+.05(x-1500).  Independent
        # projections at the original spans miss their actual intersection.
        right = (3100.0 - slope * 1000.0 + slope * (2000.0 - slope * 1500.0)) / (1.0 - slope * slope)
        bottom = 2000.0 + slope * (right - 1500.0)
        self.assertGreaterEqual(max(x for x, _ in mandatory), right)
        self.assertGreaterEqual(max(y for _, y in mandatory), bottom)
        output = output_footprint_from_template_placement(
            placement, projection,
            lane=_lane(long_axis_px=5000, short_axis_px=3000),
            lane_ordinal=1, layout="horizontal",
        )
        requested = output.requested_source_footprint
        self.assertAlmostEqual(
            max(x for x, _ in requested) - min(x for x, _ in requested),
            output.fixed_size.output_width_px,
        )
        self.assertAlmostEqual(
            max(y for _, y in requested) - min(y for _, y in requested),
            output.fixed_size.output_height_px,
        )

    def test_raw_joint_line_is_projected_at_reachable_native_reference(self) -> None:
        template = _template(1)
        sequence = _sequence(template)
        end = sequence.role_bindings[1]
        assert end is not None
        end = replace(end, full_position_interval_px=FiniteInterval(190.0, 210.0),
                      line_evidence=SequenceRoleLineEvidence(
                          end.observation_id, 130.0, FiniteInterval.exact(200.0), FiniteInterval.exact(0.0),
                          PhysicalLineRegion(130.0, ((190.0, 0.0), (200.0, -0.04),
                                                    (210.0, 0.0), (200.0, 0.04))),
                      ))
        sequence = replace(sequence, role_bindings=(sequence.role_bindings[0], end))
        cross = _cross(template)
        cross = replace(cross, direct_bindings=tuple(replace(
            binding, fit_direction_interval_degrees=FiniteInterval.exact(0.0),
            full_direction_interval_degrees=FiniteInterval.exact(0.0),
            observed_direction_interval_degrees=FiniteInterval.exact(0.0),
        ) for binding in cross.direct_bindings))
        placement = _compose(template, sequence, cross)
        projection = project_format_placement(placement)
        mandatory = _footprint(placement, placement.frames[0], projection, apply_residual=True)
        # Native START=100 and W=100 make END=200; all raw slopes at
        # that slice remain. The impossible p=210,slope=.04 is not exported.
        self.assertAlmostEqual(max(x for x, _ in mandatory), 200.0 + 1.0 + 0.04 * 121.0)

    def test_cross_protection_reprojects_both_actual_longitudinal_ends(self) -> None:
        template = _template(1)
        sequence = _sequence(template)
        end = sequence.role_bindings[1]
        assert end is not None
        end = replace(end, line_evidence=SequenceRoleLineEvidence(
            end.observation_id, 130.0, FiniteInterval.exact(200.0),
            FiniteInterval.exact(math.degrees(math.atan(-0.04))),
        ))
        sequence = replace(sequence, role_bindings=(sequence.role_bindings[0], end))
        angle = math.degrees(math.atan(0.01))
        for one_sided in (False, True):
            cross = _cross(template, one_sided=one_sided)
            cross = replace(cross, direct_bindings=tuple(replace(
                binding,
                fit_direction_interval_degrees=FiniteInterval.exact(0.0),
                full_direction_interval_degrees=FiniteInterval(-angle, angle),
                observed_direction_interval_degrees=FiniteInterval(-angle, angle),
                physical_line_region=PhysicalLineRegion(150.0, (
                    (binding.full_interval_px.minimum, 0.01),
                    (binding.full_interval_px.minimum + 0.001, -0.01),
                )),
            ) for binding in cross.direct_bindings))
            placement = _compose(template, sequence, cross)
            projection = project_format_placement(placement)
            with self.subTest(one_sided=one_sided):
                polygon = _footprint(
                    placement, placement.frames[0], projection, apply_residual=True,
                )
                left, right = min(x for x, _ in polygon), max(x for x, _ in polygon)
                # Before expansion the positive-slope line controls TOP.
                # The larger END extension makes the negative-slope line
                # control it instead. Both ends of both lines must survive.
                lines = ((10.0, 0.01), (10.001, -0.01))
                minimum = min(p + m * (x - 150.0)
                              for p, m in lines for x in (left, right))
                self.assertLess(10.001 - 0.01 * (right - 150.0),
                                10.0 + 0.01 * (left - 150.0))
                self.assertAlmostEqual(min(y for _, y in polygon), minimum - 1.0)
                if one_sided:
                    maximum = max(p + m * (x - 150.0)
                                  for p, m in lines for x in (left, right))
                    self.assertAlmostEqual(max(y for _, y in polygon),
                                           maximum + 240.0 + 1.0)

    def test_raw_trace_protects_interior_reference_states_and_new_span(self) -> None:
        for interior in (True, False):
            with self.subTest(interior=interior):
                template = _template(1)
                sequence = _sequence(template)
                start, end = sequence.role_bindings
                assert start is not None and end is not None
                if interior:
                    start = replace(start, full_position_interval_px=FiniteInterval(0.0, 1000.0))
                    end = replace(end, full_position_interval_px=FiniteInterval(100.0, 1100.0))
                    trace = 550
                else:
                    end = replace(end, line_evidence=SequenceRoleLineEvidence(
                        end.observation_id, 130.0, FiniteInterval.exact(200.0), FiniteInterval.exact(-1.0),
                    ))
                    trace = 202
                sequence = replace(sequence, role_bindings=(start, end))
                cross = _cross(template)
                top, bottom = tuple(replace(
                    binding, fit_direction_interval_degrees=FiniteInterval.exact(0.0),
                    full_direction_interval_degrees=FiniteInterval.exact(0.0),
                    observed_direction_interval_degrees=FiniteInterval.exact(0.0),
                ) for binding in cross.direct_bindings)
                top = replace(top, trace_coordinates_px=(trace,),
                              trace_position_intervals_px=(FiniteInterval.exact(-10.0),))
                cross = replace(cross, direct_bindings=(top, bottom))
                placement = _compose(template, sequence, cross)
                projection = project_format_placement(placement)
                mandatory = _footprint(placement, placement.frames[0], projection, apply_residual=True)
                self.assertLessEqual(min(y for _, y in mandatory), -11.0)

    def test_cross_reprojection_contains_mixed_states_in_every_hull_direction(self) -> None:
        template = _template(1)
        placement = _compose(template, _sequence(template), _cross(template))
        original = placement.frames[0]
        frame = replace(original,
            start=replace(original.start, full_position_interval_px=FiniteInterval(100, 110)),
            end=replace(original.end, full_position_interval_px=FiniteInterval(200, 230)),
            top=replace(original.top, full_position_interval_px=FiniteInterval(10, 20)),
            bottom=replace(original.bottom, full_position_interval_px=FiniteInterval(250, 280)),
        )
        vertices = (JointFrameState(100, 200, 10, 250, None),
                    JointFrameState(110, 230, 20, 280, None))
        angle = math.degrees(math.atan(0.03))
        bindings = tuple(replace(binding,
            fit_direction_interval_degrees=FiniteInterval(-angle, angle),
            full_direction_interval_degrees=FiniteInterval(-angle, angle),
            observed_direction_interval_degrees=FiniteInterval(-angle, angle),
            trace_coordinates_px=(215,),
            trace_position_intervals_px=(FiniteInterval(position - 2, position + 2),),
        ) for binding, position in zip(placement.cross_fit.direct_bindings, (8.0, 282.0), strict=True))
        for direction in (1, -1):
            directed_frame = frame if direction == 1 else replace(frame,
                start=replace(frame.end, role=BoundaryRole.START),
                end=replace(frame.start, role=BoundaryRole.END),
            )
            directed_vertices = tuple(replace(state,
                sequence_start_px=state.sequence_end_px,
                sequence_end_px=state.sequence_start_px,
            ) for state in vertices) if direction == -1 else vertices
            for inferred_role in (None, BoundaryRole.TOP, BoundaryRole.BOTTOM):
                direct = tuple(b for b in bindings if b.role != inferred_role)
                inferred = () if inferred_role is None else (SimpleNamespace(
                    role=inferred_role,
                    source_observation_ids=(direct[0].observation_id,),
                ),)
                # This mechanism fixture holds the complete line and raw
                # ledger fixed while varying signed W/H and reference state.
                context = SimpleNamespace(
                    frame_spec=placement.frame_spec,
                    sequence_fit=SimpleNamespace(template=SimpleNamespace(direction=direction),
                                                 adjacency_relations=()),
                    cross_fit=SimpleNamespace(
                        boundary_use=OutputBoundaryUse.APERTURE_PAIR,
                        direct_bindings=direct, inferred_bindings=inferred,
                        direct_pair=inferred_role is None,
                        line_projection_basis=CrossLineProjectionBasis.COMPLETE_PHYSICAL_DIRECTION,
                        lane_reference_trace_px=150.0,
                    ),
                )
                mixed = tuple(JointFrameState(*(
                    (1.0 - weight) * getattr(directed_vertices[0], name)
                    + weight * getattr(directed_vertices[1], name)
                    for name in ('sequence_start_px', 'sequence_end_px',
                                 'top_at_lane_reference_px', 'bottom_at_lane_reference_px')
                ), None) for weight in (0.1, 0.25, 0.5, 0.75, 0.9))
                states = directed_vertices + mixed
                residuals = _frame_boundary_residuals(context, directed_frame, states)
                polygons = tuple(_state_footprint(
                    context, directed_frame, state,
                    apply_residual=True, residuals=residual,
                ) for state, residual in zip(states, residuals, strict=True))
                hull = convex_hull(tuple(point for polygon in polygons[:2] for point in polygon))
                # All hull halfplanes, including oblique ones, must contain
                # every protected corner of each interior reference state.
                for left, right in zip(hull, (*hull[1:], hull[0]), strict=True):
                    for polygon in polygons[2:]:
                        for x, y in polygon:
                            self.assertGreaterEqual(
                                (right[0] - left[0]) * (y - left[1])
                                - (right[1] - left[1]) * (x - left[0]), -1e-8,
                                (direction, inferred_role),
                            )
