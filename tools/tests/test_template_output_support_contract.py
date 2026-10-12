from __future__ import annotations

import math, unittest
from dataclasses import replace
from types import SimpleNamespace
from x5crop.domain import EvidenceState, FiniteInterval, WorkspaceExtent
from x5crop.formats import (
    DEVELOPMENT_GOLD_CALIBRATION_COHORT_SHA256,
    EnclosingSupportApertureCalibrationSpec,
)
from x5crop.detection.gate_checks import GateGap
from x5crop.detection.photo_geometry.model import BoundaryAxis, BoundaryRole
from x5crop.detection.photo_geometry.output_model import fixed_output_rectangle, OutputBoundaryUse
from x5crop.detection.photo_geometry.template_cross_model import CrossLineProjectionBasis
from x5crop.detection.photo_geometry.source_geometry import SourceFixedOutputSize
from x5crop.detection.photo_geometry.template_output import (
    _aperture_binding_positions,
    _enclosing_support_aperture_risk,
    _footprint,
    _frame_boundary_residuals,
    _line_outward_expansion_px,
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
from x5crop.detection.photo_geometry.template_placement import resolved_cross_support_domains_px
from x5crop.detection.photo_geometry.line_observations import (
    PhysicalLineRegion,
    SourceCoordinateLine,
)
from x5crop.detection.photo_geometry.template_model import SequenceRoleLineEvidence
from tools.tests.template_test_support import (
    placement_binding as _binding,
    placement_compose as _compose,
)
from tools.tests.output_fixture_support import (
    _contact_placement,
    _enclosing_support_placement,
    _lane,
    _overlap_placement,
    _placement,
    _selected_output_gate_fact,
)


class FixedOutputCenterContractTest(unittest.TestCase):
    def setUp(self):
        self.size = SourceFixedOutputSize("source:test", 100.0, 60.0)
        self.extent = WorkspaceExtent(400, 300)

    def rectangle(self, bounds, target, *, extent=None, axis=BoundaryAxis.X):
        left, top, right, bottom = bounds
        mandatory = convex_hull(((left, top), (right, top), (right, bottom), (left, bottom)))
        return fixed_output_rectangle(self.size, axis, mandatory, extent or self.extent,
                                      preferred_center=target)

    def test_all_four_true_source_sides_keep_the_complete_fixed_window(self):
        for name, bounds, target, expected in (
            ("left", (-25, 100, 60, 140), (-5, 120), (-.5, 87, 109.5, 153)),
            ("right", (350, 100, 430, 140), (405, 120), (289.5, 87, 399.5, 153)),
            ("top", (100, -20, 140, 30), (120, -5), (65, -.5, 175, 65.5)),
            ("bottom", (100, 270, 140, 330), (120, 300), (65, 233.5, 175, 299.5)),
        ):
            with self.subTest(side=name):
                actual = self.rectangle(bounds, target)
                for value, wanted in zip(
                    (min(x for x, _ in actual), min(y for _, y in actual),
                     max(x for x, _ in actual), max(y for _, y in actual)), expected, strict=True,
                ):
                    self.assertAlmostEqual(value, wanted)

    def test_center_rule_commutes_with_axis_transpose_and_source_reflections(self):
        mandatory = convex_hull(((-30, 110), (80, 110), (80, 155), (-30, 155)))
        target = (-20, 120)
        original = fixed_output_rectangle(self.size, BoundaryAxis.X, mandatory, self.extent,
                                          preferred_center=target)
        for transpose in (False, True):
            for reflect_x in (False, True):
                for reflect_y in (False, True):
                    def transform(point):
                        x, y = point
                        x = self.extent.width - 1 - x if reflect_x else x
                        y = self.extent.height - 1 - y if reflect_y else y
                        return (y, x) if transpose else (x, y)
                    with self.subTest(transpose=transpose, x=reflect_x, y=reflect_y):
                        extent = WorkspaceExtent(300, 400) if transpose else self.extent
                        actual = fixed_output_rectangle(self.size,
                            BoundaryAxis.Y if transpose else BoundaryAxis.X,
                            convex_hull(tuple(transform(point) for point in mandatory)), extent,
                            preferred_center=transform(target))
                        expected = convex_hull(tuple(transform(point) for point in original))
                        for point, wanted in zip(actual, expected, strict=True):
                            for coordinate, value in zip(point, wanted, strict=True):
                                self.assertAlmostEqual(coordinate, value)

    def test_source_shorter_than_fixed_dimension_keeps_legal_clipping_and_size(self):
        actual = self.rectangle((-20, -10, 90, 60), (40, 25), extent=WorkspaceExtent(80, 50))
        for point, wanted in zip(actual, ((-15, -8), (95, -8), (95, 58), (-15, 58)), strict=True):
            for coordinate, value in zip(point, wanted, strict=True):
                self.assertAlmostEqual(coordinate, value)
        clipped = clip_convex_polygon_to_bounds(actual, (-.5, -.5, 79.5, 49.5))
        self.assertEqual(clipped, ((-.5, -.5), (79.5, -.5), (79.5, 49.5), (-.5, 49.5)))
        self.assertAlmostEqual(max(x for x, _ in actual) - min(x for x, _ in actual), self.size.output_width_px)
        self.assertAlmostEqual(max(y for _, y in actual) - min(y for _, y in actual), self.size.output_height_px)

    def test_uncontainable_axis_keeps_original_target_even_if_it_overflows_source(self):
        actual = self.rectangle((-30, 100, 400, 140), (-10, 120))
        self.assertAlmostEqual((min(x for x, _ in actual) + max(x for x, _ in actual)) / 2.0, -10.0)
        self.assertGreater(399.5 - max(x for x, _ in actual), 0.0)
        self.assertAlmostEqual(max(x for x, _ in actual) - min(x for x, _ in actual), self.size.output_width_px)

    def test_preferred_center_is_unchanged_when_it_already_contains_source_visible_content(self):
        actual = self.rectangle((100, 100, 180, 140), (140, 120))
        self.assertAlmostEqual((min(x for x, _ in actual) + max(x for x, _ in actual)) / 2.0, 140.0)
        self.assertAlmostEqual((min(y for _, y in actual) + max(y for _, y in actual)) / 2.0, 120.0)


class TemplateOutputSupportContractTest(unittest.TestCase):
    def test_support_slope_join_does_not_count_nonvertex_slice_corners(self) -> None:
            # Ten slope slices have forty corners, but only twenty-four are
            # extreme: the sixteen interior points on p_top=100 are redundant.
        top = tuple((float(m * m), float(m)) for m in range(10)) + ((100.0, 9.0), (100.0, 0.0))
        bottom = ((200.0, 0.0), (201.0, 0.0), (201.0, 9.0), (200.0, 9.0))
        for left, right in ((top, bottom), (bottom, top), (top[::-1], bottom[::-1])):
            with self.subTest(swapped=left == bottom, reversed=left == top[::-1]):
                vertices, work = _shared_slope_polygon_vertices(left, right)
                self.assertEqual(len(vertices), 24)
                self.assertEqual(work, 40)
        vertices, _ = _shared_slope_polygon_vertices(top, bottom)
        for m in range(1, 9):
            for b in (200.0, 201.0):
                self.assertNotIn((100.0, b, float(m)), vertices)
                self.assertIn((100.0, b, 0.0), vertices)
                self.assertIn((100.0, b, 9.0), vertices)
                # Exact convex-combination certificate, without a hull tolerance.
                self.assertEqual(
                    tuple(((9 - m) * a + m * z) / 9 for a, z in
                          zip((100.0, b, 0.0), (100.0, b, 9.0), strict=True)),
                    (100.0, b, float(m)),
                )

    def test_support_slope_join_keeps_real_bound_and_degenerate_fibers(self) -> None:
        curved = (tuple((float(m * m), float(m)) for m in range(10))
                  + tuple((float(200 - m * m), float(m)) for m in reversed(range(10))))
        with self.assertRaisesRegex(ValueError, "vertex bound"):
            _shared_slope_polygon_vertices(curved, tuple((p + 300.0, m) for p, m in curved))
        top = ((0.0, 0.0), (9.0, 9.0))
        bottom = ((20.0, 4.0), (22.0, 4.0))
        vertices, _ = _shared_slope_polygon_vertices(top, bottom)
        self.assertEqual(set(vertices), {(4.0, 20.0, 4.0), (4.0, 22.0, 4.0)})

    def test_redundant_support_slices_preserve_full_output_and_risk(self) -> None:
        top = tuple((float(m * m), float(m)) for m in range(10)) + ((100.0, 9.0), (100.0, 0.0))
        bottom = ((200.0, 0.0), (201.0, 0.0), (201.0, 9.0), (200.0, 9.0))
        extremes, _ = _shared_slope_polygon_vertices(top, bottom)
        all_corners = tuple((p, b, float(m)) for m in range(10)
                            for p in (float(m * m), 100.0) for b in (200.0, 201.0))
        for width in (100.0, 300.0):
            placement = _enclosing_support_placement(
                frame_width_px=width, support_position_uncertainty_px=2.0,
                observed_direction_half_width_degrees=1.0,
            )
            direction = FiniteInterval(-math.degrees(math.atan(0.005)), math.degrees(math.atan(0.005)))
            placement = replace(placement, cross_fit=replace(
                placement.cross_fit, direct_bindings=tuple(replace(
                    binding, full_direction_interval_degrees=direction,
                ) for binding in placement.cross_fit.direct_bindings),
            ))
            projection = project_format_placement(placement)
            first = projection.frame_states[0][0]
            outputs = []
            for corners in (all_corners, extremes):
                # An affine image of the certified polygon join, with the
                # same physical/raw protection context for both representations.
                states = tuple(JointFrameState(
                    first.sequence_start_px, first.sequence_end_px,
                    27.0 + 0.01 * (p - 50.0), 277.0 + 0.01 * (b - 200.5),
                    0.001 * (m - 4.5),
                ) for p, b, m in corners)
                outputs.append(output_footprint_from_template_placement(
                    placement, replace(projection, frame_states=(states,)),
                    lane=_lane(), lane_ordinal=1, layout="horizontal",
                ))
            before, after = outputs
            for field in ("mandatory_source_footprint", "requested_source_footprint", "required_source_footprint"):
                old, new = getattr(before, field), getattr(after, field)
                self.assertEqual(len(old), len(new))
                for left, right in zip(old, new, strict=True):
                    for a, b in zip(left, right, strict=True):
                        self.assertAlmostEqual(a, b)
            self.assertAlmostEqual(before.maximum_same_state_cross_alignment_padding_px,
                                   after.maximum_same_state_cross_alignment_padding_px)
            for field in ("top_expansion_px", "bottom_expansion_px", "maximum_center_shift_px"):
                self.assertAlmostEqual(getattr(before.enclosing_support_aperture_risk, field),
                                       getattr(after.enclosing_support_aperture_risk, field))

    def test_support_projection_keeps_unpaired_constraints_and_rejects_lost_raw(self) -> None:
        placement = _enclosing_support_placement(support_position_uncertainty_px=0.5)
        cross = placement.cross_fit
        pair = cross.enclosing_support_pair
        assert pair is not None
        direction = FiniteInterval(-math.degrees(math.atan(0.01)), math.degrees(math.atan(0.01)))
        top, bottom = cross.direct_bindings
        top = replace(top, trace_coordinates_px=(0, 50, 150, 250, 300),
            trace_position_intervals_px=(FiniteInterval.exact(27.0),) + (FiniteInterval(25.0, 29.0),) * 3
                                       + (FiniteInterval.exact(27.0),),
            fit_direction_interval_degrees=direction, full_direction_interval_degrees=direction,
            observed_direction_interval_degrees=direction)
        bottom = replace(bottom, trace_coordinates_px=(50, 150, 250),
            trace_position_intervals_px=(FiniteInterval(275.0, 279.0),) * 3,
            fit_direction_interval_degrees=direction, full_direction_interval_degrees=direction,
            observed_direction_interval_degrees=direction)
        pair = replace(pair, top_trace_coordinates_px=top.trace_coordinates_px,
            bottom_trace_coordinates_px=bottom.trace_coordinates_px,
            top_trace_intervals_px=top.trace_position_intervals_px,
            bottom_trace_intervals_px=bottom.trace_position_intervals_px)
        cross = replace(cross, direct_bindings=(top, bottom), enclosing_support_pair=pair)
        placement = replace(placement, cross_fit=cross)
        vertices, _ = _support_cross_vertices(placement)
        self.assertEqual(set(vertices), {(27.0, 276.5, 0.0), (27.0, 277.5, 0.0)})
        for altered in (
            replace(pair, top_trace_coordinates_px=pair.top_trace_coordinates_px[1:],
                    top_trace_intervals_px=pair.top_trace_intervals_px[1:]),
            replace(pair, top_trace_intervals_px=(FiniteInterval(26.5, 27.5),)
                    + pair.top_trace_intervals_px[1:]),
        ):
            with self.assertRaisesRegex(ValueError, "preserve direct bindings"):
                replace(cross, enclosing_support_pair=altered)
        with self.assertRaisesRegex(ValueError, "preserve direct bindings"):
            replace(cross, shared_trace_support_count=5)

    def test_cross_projection_preserves_joint_positions_without_marginal_corners(self) -> None:
            # The two measured intervals y(0) in [0,2], y(1000) in [8,10]
            # give these four exact line states at reference 500. A statistical
            # location band cannot be combined with the full physical slope range.
        region = PhysicalLineRegion(500.0, ((4.0, 0.008), (5.0, 0.010), (6.0, 0.008), (5.0, 0.006)))
        binding = replace(
            _binding(BoundaryRole.TOP, 'joint', 5.0),
            fit_interval_px=FiniteInterval(4.9, 5.1),
            full_interval_px=FiniteInterval(4.9, 5.1),
            canonical_direction_degrees=math.degrees(math.atan(0.008)),
            fit_direction_interval_degrees=FiniteInterval(
                math.degrees(math.atan(0.00775)), math.degrees(math.atan(0.00825))),
            full_direction_interval_degrees=FiniteInterval(
                math.degrees(math.atan(0.006)), math.degrees(math.atan(0.010))),
            observed_direction_interval_degrees=None,
            physical_line_region=region,
        )
        def positions(trace, value=binding, basis=CrossLineProjectionBasis.COMPLETE_PHYSICAL_DIRECTION):
            return _aperture_binding_positions(value, lane_reference_trace_px=500.0,
                                              support=FiniteInterval.exact(trace), line_projection_basis=basis)
        self.assertAlmostEqual(min(positions(-1000)), -10.0)
        self.assertAlmostEqual(min(positions(-1000, replace(binding, physical_line_region=None))), -10.1)
        self.assertEqual((min(positions(500)), max(positions(500))), (4.0, 6.0))
        statistical = positions(500, basis=CrossLineProjectionBasis.RETAINED_REVIEW_STATISTICAL_FIT)
        self.assertEqual((min(statistical), max(statistical)), (4.9, 5.1))
        # A broad local measurement may extend beyond every common straight
        # line. Its complete raw interval must still be protected independently.
        raw = replace(binding, trace_coordinates_px=(0, 500, 1000), trace_position_intervals_px=(
            FiniteInterval(0, 2), FiniteInterval(3, 7), FiniteInterval(8, 10)))
        self.assertEqual((min(positions(500, raw)), max(positions(500, raw))), (3.0, 7.0))

    def test_cross_support_partitions_only_an_explicit_overlap(self) -> None:
        placement = _overlap_placement()

        self.assertEqual(
            resolved_cross_support_domains_px(placement.sequence_fit),
            (
                FiniteInterval(100.0, 197.5),
                FiniteInterval(197.5, 295.0),
            ),
        )
        unmodeled = replace(
            placement.sequence_fit,
            adjacency_relations=(),
        )
        with self.assertRaisesRegex(
            ValueError,
            "explicit OverlapRelation",
        ):
            resolved_cross_support_domains_px(unmodeled)

    def test_overlap_protection_keeps_typed_physical_protection_facts(
            self,
        ) -> None:
        placement = _overlap_placement()
        projection = project_format_placement(placement)
        outputs = tuple(
            output_footprint_from_template_placement(
                placement,
                projection,
                lane=_lane(),
                lane_ordinal=ordinal,
                layout="horizontal",
            )
            for ordinal in (1, 2)
        )
        protections = {
            (output.envelope.lane_ordinal, item.role): item
            for output in outputs
            for item in output.boundary_protections
        }
        self.assertEqual(
            set(protections),
            {(ordinal, role) for ordinal in (1, 2) for role in (
                BoundaryRole.START, BoundaryRole.END,
                BoundaryRole.TOP, BoundaryRole.BOTTOM,
            )},
        )
        self.assertEqual(
            tuple(next(iter(protections.values())).__dataclass_fields__),
            (
                "role",
                "measurement_expansion_px",
                "local_boundary_residual_px",
                "required_expansion_px",
            ),
        )
        for fact in protections.values():
            self.assertGreaterEqual(fact.required_expansion_px, fact.measurement_expansion_px)
            self.assertGreaterEqual(
                fact.required_expansion_px,
                fact.local_boundary_residual_px - 1.0e-8,
            )
            self.assertFalse(hasattr(fact, "topology_relation_id"))
            self.assertFalse(hasattr(fact, "base_bleed_px"))

    def test_contact_protection_keeps_typed_physical_protection_facts(
            self,
        ) -> None:
        placement = _contact_placement()
        projection = project_format_placement(placement)
        outputs = tuple(
            output_footprint_from_template_placement(
                placement,
                projection,
                lane=_lane(),
                lane_ordinal=ordinal,
                layout="horizontal",
            )
            for ordinal in (1, 2)
        )
        protections = {
            (output.envelope.lane_ordinal, item.role): item
            for output in outputs
            for item in output.boundary_protections
        }
        self.assertEqual(
            set(protections),
            {(ordinal, role) for ordinal in (1, 2) for role in (
                BoundaryRole.START, BoundaryRole.END,
                BoundaryRole.TOP, BoundaryRole.BOTTOM,
            )},
        )
        for fact in protections.values():
            self.assertGreaterEqual(fact.required_expansion_px, fact.measurement_expansion_px)
            self.assertGreaterEqual(
                fact.required_expansion_px,
                fact.local_boundary_residual_px - 1.0e-8,
            )
            self.assertFalse(hasattr(fact, "topology_relation_id"))
            self.assertFalse(hasattr(fact, "base_bleed_px"))

    def test_contact_protection_is_evaluated_against_the_fixed_window(
            self,
        ) -> None:
        placement = _contact_placement(
            shared_direction_uncertainty_degrees=10.0,
        )
        projection = project_format_placement(placement)
        output = output_footprint_from_template_placement(
            placement,
            projection,
            lane=_lane(),
            lane_ordinal=1,
            layout="horizontal",
        )

        assessment = template_direct_use_budget_assessment(placement, output)
        end = next(
            item
            for item in assessment.edge_assessments
            if item.role == BoundaryRole.END
        )
        self.assertGreater(end.required_extent_px, 0.0)
        self.assertLessEqual(end.required_extent_px, end.available_extent_px)
        self.assertEqual(assessment.state, EvidenceState.SUPPORTED)

    def test_enclosing_support_keeps_its_same_state_target_projection(self) -> None:
        placement = _enclosing_support_placement(
            frame_count=2,
            support_slope=0.002,
        )
        projection = project_format_placement(placement)
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

    def test_enclosing_support_counts_its_same_state_slope_once(self) -> None:
        placement = _enclosing_support_placement(
            frame_count=3,
            support_slope=0.02,
        )
        output = output_footprint_from_template_placement(
            placement,
            project_format_placement(placement),
            lane=_lane(),
            lane_ordinal=3,
            layout="horizontal",
        )
        protections = {
            item.role: item for item in output.boundary_protections
        }

        self.assertAlmostEqual(
            protections[BoundaryRole.TOP].local_boundary_residual_px,
            1.0,
        )
        self.assertAlmostEqual(
            protections[BoundaryRole.BOTTOM].local_boundary_residual_px,
            1.0,
        )

    def test_enclosing_support_preserves_both_slopes_at_one_position_vertex(self) -> None:
        placement = _enclosing_support_placement(support_position_uncertainty_px=0.5)
        cross = placement.cross_fit
        pair = cross.enclosing_support_pair
        assert pair is not None
        traces = (0, 50, 250, 300)
        angle = math.degrees(math.atan(0.01))
        direction = FiniteInterval(-angle, angle)
        pair = replace(
            pair,
            top_trace_coordinates_px=traces,
            bottom_trace_coordinates_px=traces,
            top_trace_intervals_px=(FiniteInterval(23.5, 30.5),) * 4,
            bottom_trace_intervals_px=(FiniteInterval(273.5, 280.5),) * 4,
        )
        bindings = tuple(replace(
            binding,
            trace_coordinates_px=traces,
            trace_position_intervals_px=intervals,
            fit_direction_interval_degrees=direction,
            full_direction_interval_degrees=direction,
            observed_direction_interval_degrees=direction,
        ) for binding, intervals in zip(
            cross.direct_bindings,
            (pair.top_trace_intervals_px, pair.bottom_trace_intervals_px),
            strict=True,
        ))
        placement = replace(placement, cross_fit=replace(
            cross, direct_bindings=bindings, enclosing_support_pair=pair,
            shared_trace_support_count=4,
        ))
        projection = project_format_placement(placement)
        states = projection.frame_states[0]
        self.assertEqual({round(state.enclosing_support_slope, 8) for state in states}, {-0.01, 0.01})
        reference = placement.frames[0].top.reference_trace_px
        for trace in (100.0, 200.0):
            self.assertAlmostEqual(min(
                state.top_at_lane_reference_px + state.enclosing_support_slope * (trace - reference)
                for state in states
            ), 26.5 - 0.01 * abs(trace - 150.0))
        output = output_footprint_from_template_placement(
            placement, projection, lane=_lane(), lane_ordinal=1, layout="horizontal",
        )
        polygon = output.envelope.feasible_source_footprint
        self.assertLessEqual(min(y for _, y in polygon), 26.0)
        self.assertGreaterEqual(max(y for _, y in polygon), 278.0)

    def test_support_risk_uses_source_axis_units_at_all_slopes(self) -> None:
            # Normalized distance at either slope endpoint would be 4.99985;
            # source-axis expansion must retain the 5.0001 maximum at slope zero.
        for axis in (BoundaryAxis.X, BoundaryAxis.Y):
            for slope in (-0.01, 0.0, 0.01):
                norm = math.hypot(1.0, slope)
                normal = (-slope / norm, 1.0 / norm)
                polygon = ((0.0, -5.0001), (1.0, slope - 5.0001), (1.0, slope), (0.0, 0.0))
                if axis == BoundaryAxis.Y:
                    normal = tuple(reversed(normal))
                    polygon = tuple((y, x) for x, y in polygon)
                line = SourceCoordinateLine(
                    normal_x=normal[0], normal_y=normal[1], offset_px=0.0,
                    support_projection_px=FiniteInterval(0.0, 1.0), source_axis_long=axis,
                )
                self.assertAlmostEqual(
                    _line_outward_expansion_px(line, BoundaryRole.TOP, polygon),
                    5.0001,
                )

    def test_support_admits_raw_endpoints_reached_by_each_protection_layer(self) -> None:
        for width, trace, slope in ((100.0, 201, 0.0), (300.0, 402, 0.0), (300.0, 402, 0.02)):
            with self.subTest(width=width, slope=slope):
                placement = _enclosing_support_placement(frame_width_px=width, support_slope=slope)
                baseline = output_footprint_from_template_placement(
                    placement, project_format_placement(placement), lane=_lane(), lane_ordinal=1, layout="horizontal",
                )
                top, bottom = placement.cross_fit.direct_bindings
                raw = dict(zip(top.trace_coordinates_px, top.trace_position_intervals_px, strict=True))
                measured_position = 27.0 + slope * (trace - 150.0)
                raw[trace] = FiniteInterval(measured_position - 3.0, measured_position)
                top = replace(top, trace_coordinates_px=tuple(sorted(raw)),
                              trace_position_intervals_px=tuple(raw[t] for t in sorted(raw)))
                pair = placement.cross_fit.enclosing_support_pair
                assert pair is not None
                pair = replace(pair, top_trace_coordinates_px=top.trace_coordinates_px,
                               top_trace_intervals_px=top.trace_position_intervals_px)
                placement = replace(placement, cross_fit=replace(placement.cross_fit,
                                    direct_bindings=(top, bottom), enclosing_support_pair=pair))
                output = output_footprint_from_template_placement(
                    placement, project_format_placement(placement), lane=_lane(), lane_ordinal=1, layout="horizontal",
                )
                polygon = output.mandatory_source_footprint
                top_intercept = min(y - slope * (x - 150.0) for x, y in polygon)
                if width == 300.0:
                    self.assertGreaterEqual(max(x for x, _ in polygon), trace - 1.0)
                    self.assertAlmostEqual(top_intercept, 26.0)
                else:
                    self.assertGreaterEqual(max(x for x, _ in polygon), trace - 1.0)
                    self.assertAlmostEqual(top_intercept, 23.0)
                requested = output.requested_source_footprint
                self.assertAlmostEqual(
                    max(x for x, _ in requested) - min(x for x, _ in requested),
                    output.fixed_size.output_width_px,
                )
                risk = output.enclosing_support_aperture_risk
                baseline_risk = baseline.enclosing_support_aperture_risk
                assert risk is not None and baseline_risk is not None
                self.assertGreaterEqual(risk.top_expansion_px, baseline_risk.top_expansion_px)
                self.assertGreater(output.maximum_same_state_cross_alignment_padding_px, 0.0)

    def test_support_and_measured_sequence_protection_close_the_actual_corner(self) -> None:
        slope = 0.06
        placement = _enclosing_support_placement(frame_width_px=300.0, support_slope=slope)
        cross = placement.cross_fit
        pair = cross.enclosing_support_pair
        assert pair is not None
        traces = (0, 150, 450)
        pair = replace(pair, top_trace_coordinates_px=traces, bottom_trace_coordinates_px=traces,
                       top_trace_intervals_px=tuple(FiniteInterval.exact(27.0 + slope * (t - 150.0)) for t in traces),
                       bottom_trace_intervals_px=tuple(FiniteInterval.exact(277.0 + slope * (t - 150.0)) for t in traces))
        cross = replace(cross, enclosing_support_pair=pair, direct_bindings=tuple(
            replace(binding, trace_coordinates_px=traces, trace_position_intervals_px=intervals)
            for binding, intervals in zip(cross.direct_bindings, (pair.top_trace_intervals_px, pair.bottom_trace_intervals_px), strict=True)
        ))
        sequence = placement.sequence_fit
        sequence = replace(sequence, role_bindings=tuple(replace(binding, line_evidence=SequenceRoleLineEvidence(
            observation_id=binding.observation_id, reference_trace_px=152.0,
            fit_position_interval_px=binding.fit_position_interval_px,
            fit_direction_interval_degrees=FiniteInterval.exact(-math.degrees(math.atan(slope))),
        )) for binding in sequence.role_bindings))
        placement = _compose(sequence.template, sequence, cross)
        output = output_footprint_from_template_placement(
            placement, project_format_placement(placement), lane=_lane(), lane_ordinal=1, layout="horizontal",
        )
        x = (400.0 + slope * 125.0 - slope * slope * 150.0) / (1.0 - slope * slope)
        y = 277.0 + slope * (x - 150.0)
        polygon = output.mandatory_source_footprint
        for (x0, y0), (x1, y1) in zip(polygon, (*polygon[1:], polygon[0]), strict=True):
            self.assertGreaterEqual((x1 - x0) * (y - y0) - (y1 - y0) * (x - x0), -1.0e-9)

    def test_enclosing_support_retains_observed_direction_beyond_trace_span(
            self,
        ) -> None:
        placement = _enclosing_support_placement(
            frame_count=3,
            observed_direction_half_width_degrees=4.0,
        )
        output = output_footprint_from_template_placement(
            placement,
            project_format_placement(placement),
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

    def test_support_extrapolates_only_to_the_actual_protected_ends(self) -> None:
        for slope in (-0.02, 0.02):
            placement = _enclosing_support_placement(
                frame_width_px=300.0, support_slope=slope,
                observed_direction_half_width_degrees=0.5,
            )
            sequence = placement.sequence_fit
            start, end = sequence.role_bindings
            assert start is not None
            start = replace(start, line_evidence=SequenceRoleLineEvidence(
                start.observation_id, 152.0, FiniteInterval.exact(100.0),
                FiniteInterval.exact(math.degrees(math.atan(0.04))),
            ))
            placement = _compose(sequence.template,
                                 replace(sequence, role_bindings=(start, end)), placement.cross_fit)
            projection = project_format_placement(placement)
            polygon = _footprint(
                placement, placement.frames[0], projection, apply_residual=True,
            )
            left, right = min(x for x, _ in polygon), max(x for x, _ in polygon)
            self.assertGreater(100.0 - left, right - 400.0)
            self.assertGreater(left, 0.0)
            # Raw support is exactly the selected line on [0, 300].
            # Only the actual right extension has unmeasured direction;
            # the larger START protection cannot lengthen that domain.
            low, high = (math.tan(math.atan(slope) + math.radians(a))
                         for a in (-0.5, 0.5))
            intercepts = tuple(y - slope * (x - 150.0) for x, y in polygon)
            self.assertAlmostEqual(min(intercepts), 27.0 - 1.0 - (slope - low) * (right - 300.0))
            self.assertAlmostEqual(max(intercepts), 277.0 + 1.0 + (high - slope) * (right - 300.0))

    def test_support_product_vertices_cover_mixed_slopes_and_same_state_risk(self) -> None:
        placement = _enclosing_support_placement(frame_width_px=300.0,
                                                observed_direction_half_width_degrees=4.0)
        original = placement.frames[0]
        frame = replace(original,
            start=replace(original.start, full_position_interval_px=FiniteInterval(90, 110)),
            end=replace(original.end, full_position_interval_px=FiniteInterval(380, 420)),
        )
        bindings = tuple(replace(binding, trace_coordinates_px=(0, 250, 300, 423),
            trace_position_intervals_px=(interval,) * 3 + (outside,),
        ) for binding, interval, outside in zip(placement.cross_fit.direct_bindings,
            (FiniteInterval(20, 40), FiniteInterval(268, 287)),
            (FiniteInterval(-8, 50), FiniteInterval(260, 320)), strict=True))
        pair = placement.cross_fit.enclosing_support_pair
        assert pair is not None
        pair = replace(pair, top_trace_coordinates_px=bindings[0].trace_coordinates_px,
                       bottom_trace_coordinates_px=bindings[1].trace_coordinates_px,
                       top_trace_intervals_px=bindings[0].trace_position_intervals_px,
                       bottom_trace_intervals_px=bindings[1].trace_position_intervals_px)
        placement = replace(placement, frames=(frame,), cross_fit=replace(placement.cross_fit,
                            direct_bindings=bindings, enclosing_support_pair=pair,
                            shared_trace_support_count=4))
        sequence = ((90.0, 380.0), (110.0, 420.0))
        support = ((25.0, 275.0, -0.02), (30.0, 278.0, 0.01), (28.0, 282.0, 0.03))
        vertices = tuple(JointFrameState(*q, *z) for q in sequence for z in support)
        mixed = tuple(JointFrameState(
            *((1 - w) * sequence[0][i] + w * sequence[1][i] for i in range(2)),
            *(sum(a * z[i] for a, z in zip(weights, support, strict=True)) for i in range(3)),
        ) for w in (0.1, 0.5, 0.9) for weights in ((0.2, 0.3, 0.5), (0.5, 0.5, 0.0), (0.0, 0.4, 0.6)))
        residuals = _frame_boundary_residuals(placement, frame, vertices)
        all_residuals = _frame_boundary_residuals(placement, frame, vertices + mixed)
        self.assertEqual(residuals, all_residuals[:len(vertices)])
        polygons = tuple(_state_footprint(
            placement, frame, state, apply_residual=True, residuals=residual,
        ) for state, residual in zip(vertices + mixed, all_residuals, strict=True))
        hull = convex_hull(tuple(point for polygon in polygons[:len(vertices)] for point in polygon))
        for left, right in zip(hull, (*hull[1:], hull[0]), strict=True):
            for polygon in polygons[len(vertices):]:
                for x, y in polygon:
                    self.assertGreaterEqual((right[0] - left[0]) * (y - left[1])
                                            - (right[1] - left[1]) * (x - left[0]), -1e-8)
        requested = fixed_output_rectangle(
            placement.source_scan_geometry.fixed_output_size, placement.width_axis,
            hull, WorkspaceExtent(500, 400),
        )
        for offset in (None, FiniteInterval(-1.0, 2.0)):
            context = SimpleNamespace(
                frame_spec=placement.frame_spec, sequence_fit=placement.sequence_fit,
                cross_fit=placement.cross_fit,
                enclosing_support_aperture_authority=SimpleNamespace(
                    authority_id="test-center", effective_center_offset_px=offset,
                    state=EvidenceState.UNAVAILABLE if offset is None else EvidenceState.SUPPORTED,
                ),
            )
            risk = _enclosing_support_aperture_risk(
                context, frame, SimpleNamespace(frame_states=(vertices,)), requested=requested)
            mixed_risk = _enclosing_support_aperture_risk(
                context, frame, SimpleNamespace(frame_states=(mixed,)), requested=requested)
            assert risk is not None and mixed_risk is not None
            self.assertLessEqual(mixed_risk.top_expansion_px, risk.top_expansion_px + 1e-8)
            self.assertLessEqual(mixed_risk.bottom_expansion_px, risk.bottom_expansion_px + 1e-8)

    def test_support_direction_span_is_specific_to_each_sequence_state(self) -> None:
        placement = _enclosing_support_placement(frame_width_px=300.0)
        original = placement.frames[0]
        vertices = (JointFrameState(100, 400, 27, 277, 0.0),
                    JointFrameState(100, 420, 27, 277, 0.0))
        frame = replace(original, end=replace(original.end, full_position_interval_px=FiniteInterval(400, 420)))
        for angles in ((-1.0, 1.0), (0.0, 1.0), (-1.0, 0.0)):
            context = replace(placement, cross_fit=replace(placement.cross_fit, direct_bindings=tuple(
                replace(binding, observed_direction_interval_degrees=FiniteInterval(*angles))
                for binding in placement.cross_fit.direct_bindings)))
            for direction in (1, -1):
                directed = SimpleNamespace(frame_spec=context.frame_spec, cross_fit=context.cross_fit,
                    sequence_fit=SimpleNamespace(template=SimpleNamespace(direction=direction), adjacency_relations=()))
                directed_frame = frame if direction == 1 else replace(frame,
                    start=replace(frame.end, role=BoundaryRole.START),
                    end=replace(frame.start, role=BoundaryRole.END))
                states = vertices if direction == 1 else tuple(replace(state,
                    sequence_start_px=state.sequence_end_px, sequence_end_px=state.sequence_start_px)
                    for state in vertices)
                residuals = _frame_boundary_residuals(directed, directed_frame, states)
                for state, residual in zip(states, residuals, strict=True):
                    polygon = _state_footprint(directed, directed_frame, state, apply_residual=True,
                                               residuals=residual)
                    right = max(420.0, max(x for x, _ in polygon))
                    self.assertAlmostEqual(residual[BoundaryRole.TOP],
                        1.0 + max(0.0, -math.tan(math.radians(angles[0]))) * (right - 300.0))
                    self.assertAlmostEqual(residual[BoundaryRole.BOTTOM],
                        1.0 + max(0.0, math.tan(math.radians(angles[1]))) * (right - 300.0))

    def test_enclosing_support_keeps_physical_diagnostics_separate_from_coverage(self) -> None:
        placement = _enclosing_support_placement()
        output = output_footprint_from_template_placement(
            placement,
            project_format_placement(placement),
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
        self.assertEqual(
            {item.role for item in output.boundary_protections},
            {
                BoundaryRole.START, BoundaryRole.END,
                BoundaryRole.TOP, BoundaryRole.BOTTOM,
            },
        )
        self.assertTrue(all(
            item.required_expansion_px >= item.measurement_expansion_px
            and item.required_expansion_px >= item.local_boundary_residual_px
            for item in cross_protections
        ))
        assessment = template_direct_use_budget_assessment(placement, output)
        self.assertEqual(assessment.state, EvidenceState.SUPPORTED)
        self.assertTrue(all(item.within_limit for item in assessment.edge_assessments))
        self.assertIsNotNone(output.enclosing_support_aperture_risk)
        self.assertIsNotNone(output.maximum_same_state_cross_alignment_padding_px)

    def test_exact_enclosing_height_still_needs_per_side_sampling_headroom(self) -> None:
        placement = _enclosing_support_placement(support_span_px=264.0)
        output = output_footprint_from_template_placement(
            placement,
            project_format_placement(placement),
            lane=_lane(),
            lane_ordinal=1,
            layout="horizontal",
        )

        assessment = template_direct_use_budget_assessment(placement, output)

        self.assertEqual(assessment.state, EvidenceState.CONTRADICTED)
        self.assertTrue(any(
            not item.within_limit
            for item in assessment.edge_assessments
            if item.role in {BoundaryRole.TOP, BoundaryRole.BOTTOM}
        ))

    def test_enclosing_position_uncertainty_is_checked_against_fixed_window(
            self,
        ) -> None:
        placement = _enclosing_support_placement(
            frame_count=2,
            support_span_px=259.0,
            support_position_uncertainty_px=2.5,
        )
        output = output_footprint_from_template_placement(
            placement,
            project_format_placement(placement),
            lane=_lane(),
            lane_ordinal=2,
            layout="horizontal",
        )

        assessment = template_direct_use_budget_assessment(placement, output)

        self.assertEqual(assessment.state, EvidenceState.CONTRADICTED)
        self.assertTrue(any(
            not item.within_limit
            for item in assessment.edge_assessments
            if item.role in {BoundaryRole.TOP, BoundaryRole.BOTTOM}
        ))

    def test_unknown_aperture_center_is_nonblocking_physical_diagnostic(self) -> None:
        placement = _enclosing_support_placement(
            support_span_px=248.0,
            support_position_uncertainty_px=2.0,
        )
        placement = replace(
            placement,
            enclosing_support_aperture_authority=(
                unavailable_enclosing_support_aperture_authority(
                    placement.cross_fit
                )
            ),
        )
        output = output_footprint_from_template_placement(
            placement,
            project_format_placement(placement),
            lane=_lane(),
            lane_ordinal=1,
            layout="horizontal",
        )

        assessment = template_direct_use_budget_assessment(placement, output)
        edges = {item.role: item for item in assessment.edge_assessments}
        assert output.enclosing_support_aperture_risk is not None
        self.assertEqual(
            output.enclosing_support_aperture_risk.maximum_center_shift_px,
            6.0,
        )
        self.assertEqual(edges[BoundaryRole.TOP].required_extent_px, 127.0)
        self.assertEqual(edges[BoundaryRole.BOTTOM].required_extent_px, 127.0)
        self.assertTrue(edges[BoundaryRole.TOP].within_limit)
        self.assertTrue(edges[BoundaryRole.BOTTOM].within_limit)
        self.assertEqual(assessment.state, EvidenceState.SUPPORTED)

    def test_calibrated_aperture_center_narrows_only_the_risk_envelope(
            self,
        ) -> None:
        placement = _enclosing_support_placement(
            support_span_px=248.0,
            support_position_uncertainty_px=2.0,
        )
        output = output_footprint_from_template_placement(
            placement,
            project_format_placement(placement),
            lane=_lane(),
            lane_ordinal=1,
            layout="horizontal",
        )

        risk = output.enclosing_support_aperture_risk
        assert risk is not None
        self.assertEqual(risk.aperture_authority_state, EvidenceState.SUPPORTED)
        self.assertEqual(
            risk.center_offset_interval_px,
            FiniteInterval(-1.68, 2.0),
        )
        self.assertEqual(risk.maximum_center_shift_px, 2.0)
        self.assertLess(risk.top_expansion_px, 18.0)
        self.assertLess(risk.bottom_expansion_px, 18.0)
        self.assertEqual(
            template_direct_use_budget_assessment(placement, output).state,
            EvidenceState.SUPPORTED,
        )

    def test_non_enclosing_output_has_no_center_authority(self) -> None:
        self.assertEqual(
            _placement().enclosing_support_aperture_authority.state,
            EvidenceState.NOT_APPLICABLE,
        )

    def test_calibrated_center_conflict_is_typed_before_budget(self) -> None:
        placement = _enclosing_support_placement(support_span_px=242.0)
        conflicting_calibration = EnclosingSupportApertureCalibrationSpec(
            calibration_id="unit-enclosing-center-conflict",
            development_gold_cohort_sha256=(
                DEVELOPMENT_GOLD_CALIBRATION_COHORT_SHA256
            ),
            development_observation_set_sha256="0" * 64,
            eligibility_revision="unit-conflict-v1",
            minimum_center_offset_ratio=0.01,
            maximum_center_offset_ratio=0.02,
            development_source_count=3,
            development_task_count=3,
            outward_rounding_ratio=0.001,
        )
        authority = derive_enclosing_support_aperture_authority(
            placement.cross_fit,
            calibration=conflicting_calibration,
        )
        self.assertEqual(authority.state, EvidenceState.CONTRADICTED)
        placement = replace(
            placement,
            enclosing_support_aperture_authority=authority,
        )
        output = output_footprint_from_template_placement(
            placement,
            project_format_placement(placement),
            lane=_lane(),
            lane_ordinal=1,
            layout="horizontal",
        )
        assessment = template_direct_use_budget_assessment(placement, output)

        gate = _selected_output_gate_fact(
            output,
            assessment,
            code="enclosing_support_aperture_consistency",
        )
        self.assertEqual(gate.state, EvidenceState.CONTRADICTED)
        self.assertEqual(
            gate.gap,
            GateGap.ENCLOSING_SUPPORT_APERTURE_CONFLICT,
        )

    def test_same_state_cross_alignment_padding_remains_nonblocking_diagnostic(self) -> None:
        placement = _enclosing_support_placement(
            frame_count=3,
            support_span_px=241.0,
            observed_direction_half_width_degrees=3.0,
        )
        output = output_footprint_from_template_placement(
            placement,
            project_format_placement(placement),
            lane=_lane(),
            lane_ordinal=3,
            layout="horizontal",
        )

        assessment = template_direct_use_budget_assessment(placement, output)
        edges = {item.role: item for item in assessment.edge_assessments}

        self.assertTrue(edges[BoundaryRole.TOP].within_limit)
        self.assertTrue(edges[BoundaryRole.BOTTOM].within_limit)
        self.assertGreater(output.maximum_same_state_cross_alignment_padding_px, 0.0)
        self.assertEqual(assessment.state, EvidenceState.SUPPORTED)
