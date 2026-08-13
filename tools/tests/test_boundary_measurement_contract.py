from __future__ import annotations

from tools.tests.photo_geometry_support import *
from x5crop.detection.photo_geometry.sequence_direction_measurement import (
    sequence_run_direction_measurement,
)


class BoundaryMeasurementContractTest(unittest.TestCase):
    def test_sequence_direction_full_interval_contains_fit_at_angle_limit(
        self,
    ) -> None:
        def transition(
            identity: str,
            *,
            trace_ordinal: int,
            trace: int,
            coordinate: float,
            physical: FiniteInterval,
        ) -> PhotoBoundaryTransition:
            return PhotoBoundaryTransition(
                transition_id=ObservationId(identity),
                query_id="query:angle-limit",
                trace_ordinal=trace_ordinal,
                trace_coordinate_px=trace,
                canonical_coordinate_px=coordinate,
                localization_interval_px=FiniteInterval(
                    coordinate - 0.5,
                    coordinate + 0.5,
                ),
                physical_position_interval_px=physical,
                gradient_z=10.0,
                tone_z=1.0,
                texture_z=1.0,
                left_tone_mean=10.0,
                right_tone_mean=20.0,
                left_texture_mean=1.0,
                right_texture_mean=2.0,
                polarity=-1,
                peak_width_px=1.0,
                prominence=10.0,
                local_noise=0.0,
            )

        values = (
            transition(
                "angle-limit:left",
                trace_ordinal=0,
                trace=902,
                coordinate=4195.0,
                physical=FiniteInterval(4182.5, 4204.5),
            ),
            transition(
                "angle-limit:right",
                trace_ordinal=1,
                trace=1056,
                coordinate=4184.0,
                physical=FiniteInterval(4183.5, 4205.5),
            ),
        )
        run = ProfileRun(
            run_id="angle-limit",
            coordinate_interval_px=FiniteInterval(4165.0, 4204.0),
            transition_ids=tuple(item.transition_id for item in values),
            trace_coordinates_px=tuple(
                item.trace_coordinate_px for item in values
            ),
            role_hint=None,
            qualified_anchor_roles=(BoundaryRole.END,),
            support_fraction=0.2,
            continuous_support_fraction=0.1,
            fit_residual_px=5.5,
            evidence_strength=1.0,
        )
        result = sequence_run_direction_measurement(
            run,
            {str(item.transition_id): item for item in values},
            boundary_axis_scale_px_per_mm=70.0,
        )

        self.assertIsNotNone(result)
        _canonical, fit, full = result
        self.assertTrue(full.contains(fit.minimum, epsilon=1.0e-9))
        self.assertTrue(full.contains(fit.maximum, epsilon=1.0e-9))

    def test_duplicate_trace_fits_merge_before_role_generation(self) -> None:
        measurement = make_side_measurement_set(((100.0,),) * 4)
        transitions = {
            str(item.transition_id): item for item in measurement.transitions
        }
        identities = tuple(item.transition_id for item in measurement.transitions)

        def run(name: str, selected: tuple[int, ...]) -> ProfileRun:
            chosen = tuple(identities[index] for index in selected)
            return ProfileRun(
                run_id=name,
                coordinate_interval_px=FiniteInterval(99.75, 100.25),
                transition_ids=chosen,
                trace_coordinates_px=tuple(
                    transitions[str(identity)].trace_coordinate_px
                    for identity in chosen
                ),
                role_hint=None,
                qualified_anchor_roles=(BoundaryRole.START,),
                support_fraction=len(chosen) / 4,
                continuous_support_fraction=1.0,
                fit_residual_px=0.0,
                evidence_strength=10.0,
                pair_qualified=True,
            )

        profile = BasicAxisProfile(
            "sequence",
            200,
            (0, 10, 20, 30),
            (run("overlap:left", (0, 1, 2)), run("overlap:right", (1, 2, 3))),
        )
        merged = merge_sequence_edge_families(
            profile,
            transitions,
            reference_trace_px=15.0,
            boundary_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        )

        self.assertEqual(len(merged.runs), 1)
        self.assertEqual(set(merged.runs[0].transition_ids), set(identities))

    def test_local_cross_segment_reaches_physical_family_merge(self) -> None:
        transition_id = ObservationId("cross:local")
        region = SideTransitionRegion(
            region_id="region:local",
            proposal_position_interval_px=FiniteInterval(99.0, 101.0),
            transition_ids=(transition_id,),
            trace_support_count=1,
            queried_trace_count=3,
            independent_support_region_count=1,
            continuous_support_fraction=0.1,
            fit_residual_px=0.0,
            mean_gradient_z=4.0,
            mean_tone_or_texture_z=4.0,
            left_background_preference_fraction=1.0,
            right_background_preference_fraction=0.0,
        )
        profile = cross_profile_from_regions(
            (region,),
            (),
            coordinate_count=200,
            transition_by_id={
                str(transition_id): SimpleNamespace(trace_coordinate_px=10)
            },
        )
        self.assertEqual(len(profile.runs), 1)
        self.assertTrue(profile.runs[0].pair_qualified)
        self.assertEqual(profile.runs[0].qualified_anchor_roles, ())

    def test_height_pair_uses_physical_direction_not_narrow_fit_overlap(
        self,
    ) -> None:
        def observation(role, name, fit_angle):
            return SimpleNamespace(
                observation_id=ObservationId(name),
                role=role,
                transition_ids=(
                    ObservationId(
                        "top:t" if role == BoundaryRole.TOP else "bottom:t"
                    ),
                ),
                line=SimpleNamespace(
                    support_projection_px=FiniteInterval(0.0, 100.0)
                ),
                angle_interval_degrees=FiniteInterval(-0.2, 0.2),
                fit_angle_interval_degrees=fit_angle,
            )

        top_run = ProfileRun(
            run_id="top",
            coordinate_interval_px=FiniteInterval.exact(100.0),
            transition_ids=(ObservationId("top:t"),),
            trace_coordinates_px=(0, 10, 90, 100),
            role_hint=BoundaryRole.TOP,
            qualified_anchor_roles=(BoundaryRole.TOP,),
            support_fraction=1.0,
            continuous_support_fraction=1.0,
            fit_residual_px=0.0,
            evidence_strength=1.0,
            pair_qualified=True,
        )
        bottom_run = ProfileRun(
            run_id="bottom",
            coordinate_interval_px=FiniteInterval.exact(340.0),
            transition_ids=(ObservationId("bottom:t"),),
            trace_coordinates_px=(0, 10, 90, 100),
            role_hint=BoundaryRole.BOTTOM,
            qualified_anchor_roles=(BoundaryRole.BOTTOM,),
            support_fraction=1.0,
            continuous_support_fraction=1.0,
            fit_residual_px=0.0,
            evidence_strength=1.0,
            pair_qualified=True,
        )
        lane = SimpleNamespace(
            height_axis=BoundaryAxis.Y,
            top_measurement_set=SimpleNamespace(
                query=SimpleNamespace(trace_positions_px=(0, 10, 90, 100))
            ),
            bottom_measurement_set=SimpleNamespace(
                query=SimpleNamespace(trace_positions_px=(0, 10, 90, 100))
            ),
        )
        height_state = SimpleNamespace(
            extent_projection_px=lambda: FiniteInterval.exact(240.0),
            retained_extent_budget_px=lambda _ratio: FiniteInterval.exact(8.0),
        )
        geometry = SimpleNamespace(
            height_state=height_state,
            frame_spec=SimpleNamespace(frame_spec_id="frame:test"),
        )
        result = pair_cross_edge_families(
            lane,
            geometry,
            (
                top_run,
                observation(
                    BoundaryRole.TOP,
                    "top:o",
                    FiniteInterval(-0.10, -0.05),
                ),
                FiniteInterval.exact(100.0),
            ),
            (
                bottom_run,
                observation(
                    BoundaryRole.BOTTOM,
                    "bottom:o",
                    FiniteInterval(0.05, 0.10),
                ),
                FiniteInterval.exact(100.0),
            ),
            FiniteInterval.exact(100.0),
        )
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].direct_height_span_validated)

    def test_separator_material_requires_repeated_resolved_darkness(self) -> None:
        def region(index: int, minimum: float, maximum: float):
            return SeparatorMaterialRegionObservation(
                region_index=index,
                sample_count=2,
                darkness_contrast_interval=FiniteInterval(minimum, maximum),
                texture_contrast_interval=FiniteInterval.exact(0.0),
            )

        self.assertTrue(
            repeated_dark_material_supported(
                (region(0, 2.0, 4.0), region(2, 3.0, 5.0))
            )
        )
        self.assertFalse(
            repeated_dark_material_supported(
                (region(0, 2.0, 4.0), region(2, 0.0, 5.0))
            )
        )
        self.assertFalse(
            repeated_dark_material_supported(
                (region(0, 1.0, 4.0), region(2, 1.0, 5.0))
            )
        )

    def test_cross_edge_uses_joint_lane_direction_not_local_fit(self) -> None:
        direction = SharedStripDirection(
            direction_id="joint:test",
            selected_observation_ids=(ObservationId("edge:test"),),
            full_angle_interval_degrees=FiniteInterval(-0.10, 0.40),
            canonical_angle_degrees=0.22,
        )
        retained, canonical = conditioned_observation_direction(
            SimpleNamespace(
                fit_angle_interval_degrees=FiniteInterval(0.10, 0.15),
                angle_interval_degrees=FiniteInterval(0.00, 0.31),
            ),
            direction,
        )
        self.assertEqual(retained, FiniteInterval(0.00, 0.31))
        self.assertEqual(canonical, 0.22)

    def test_joint_direction_uses_both_axes_without_weighted_score(self) -> None:
        sequence_edges = tuple(
            SimpleNamespace(
                run_id=f"run:{index}",
                observation_id=ObservationId(f"sequence:{index}"),
                canonical_direction_degrees=value,
                fit_direction_interval_degrees=FiniteInterval(
                    value - 0.01,
                    value + 0.01,
                ),
                full_direction_interval_degrees=FiniteInterval(
                    value - 0.08,
                    value + 0.08,
                ),
            )
            for index, value in enumerate((0.18, 0.24, 0.26), start=1)
        )
        seed = SimpleNamespace(
            role_proposals=tuple(
                SimpleNamespace(run_id=edge.run_id)
                for edge in sequence_edges
            ),
            local_advance_proposals=(),
        )
        cross = SharedStripDirection(
            direction_id="cross:test",
            selected_observation_ids=(ObservationId("cross:edge"),),
            full_angle_interval_degrees=FiniteInterval(0.10, 0.30),
            canonical_angle_degrees=0.12,
        )
        joint = joint_chain_direction(
            SimpleNamespace(sequence_edges=sequence_edges),
            seed,
            cross,
        )
        self.assertAlmostEqual(joint.canonical_angle_degrees, 0.21)
        self.assertEqual(
            set(joint.selected_observation_ids),
            {
                ObservationId("cross:edge"),
                *(edge.observation_id for edge in sequence_edges),
            },
        )
        # The shared lane direction is the common feasible interval, not the
        # hull of every local edge direction.  Local bend may locate a boundary
        # but cannot widen the global deskew authority.
        self.assertAlmostEqual(
            joint.full_angle_interval_degrees.minimum,
            0.18,
        )
        self.assertAlmostEqual(
            joint.full_angle_interval_degrees.maximum,
            0.26,
        )

    def test_direct_cross_pair_owns_direction_after_sequence_validation(self) -> None:
        sequence_edges = tuple(
            SimpleNamespace(
                run_id=f"run:pair:{index}",
                observation_id=ObservationId(f"sequence:pair:{index}"),
                canonical_direction_degrees=value,
                fit_direction_interval_degrees=FiniteInterval(
                    value - 0.02,
                    value + 0.02,
                ),
                full_direction_interval_degrees=FiniteInterval(
                    value - 0.10,
                    value + 0.10,
                ),
            )
            for index, value in enumerate((0.19, 0.23), start=1)
        )
        seed = SimpleNamespace(
            role_proposals=tuple(
                SimpleNamespace(run_id=edge.run_id)
                for edge in sequence_edges
            ),
            local_advance_proposals=(),
        )
        cross = SharedStripDirection(
            direction_id="cross:direct-pair",
            selected_observation_ids=(
                ObservationId("cross:top"),
                ObservationId("cross:bottom"),
            ),
            full_angle_interval_degrees=FiniteInterval(0.10, 0.30),
            canonical_angle_degrees=0.20,
        )
        self.assertIs(
            joint_chain_direction(
                SimpleNamespace(sequence_edges=sequence_edges),
                seed,
                cross,
            ),
            cross,
        )

    def test_direct_pair_requires_repeated_shared_trace_regions(self) -> None:
        queried = (0, 10, 20, 30, 40, 50, 60)
        self.assertEqual(
            shared_independent_trace_support_count(
                queried,
                (0, 10, 20, 30),
                (30, 40, 50, 60),
            ),
            1,
        )
        self.assertEqual(
            shared_independent_trace_support_count(
                queried,
                (0, 10, 20, 40, 50, 60),
                (0, 10, 20, 40, 50, 60),
            ),
            3,
        )

    def test_separator_pairing_uses_material_not_gap_width(
        self,
    ) -> None:
        traces = (0, 50, 100)

        def profile_run(name: str, coordinate: float) -> ProfileRun:
            identity = ObservationId(f"transition:{name}")
            return ProfileRun(
                run_id=name,
                coordinate_interval_px=FiniteInterval.exact(coordinate),
                transition_ids=(identity,),
                trace_coordinates_px=traces,
                role_hint=None,
                qualified_anchor_roles=(),
                support_fraction=1.0,
                continuous_support_fraction=1.0,
                fit_residual_px=0.0,
                evidence_strength=1.0,
            )

        left_run = profile_run("left", 100.0)
        right_run = profile_run("right", 900.0)
        profile = BasicAxisProfile(
            "sequence",
            1000,
            traces,
            (left_run, right_run),
        )

        def edge(run: ProfileRun, polarity: int) -> BoundaryEdgeObservation:
            return BoundaryEdgeObservation(
                observation_id=ObservationId(f"edge:{run.run_id}"),
                run_id=run.run_id,
                coordinate_interval_px=run.coordinate_interval_px,
                transition_ids=run.transition_ids,
                trace_coordinates_px=traces,
                polarity=polarity,
                support_fraction=1.0,
                continuous_support_fraction=1.0,
                fit_residual_px=0.0,
                canonical_direction_degrees=None,
                fit_direction_interval_degrees=None,
                full_direction_interval_degrees=None,
            )

        marker = mock.Mock()
        marker.observation_id = ObservationId("separator:wide")
        with mock.patch(
            "x5crop.detection.photo_geometry.separator_observations._separator_band_from_edges",
            return_value=marker,
        ) as builder:
            result = build_format_separator_bands(
                profile,
                (edge(left_run, -1), edge(right_run, 1)),
                {},
                mock.Mock(),
                BoundaryAxis.X,
            )

        self.assertEqual(result, (marker,))
        builder.assert_called_once()

    def test_polarity_ambiguous_edge_remains_an_observation(self) -> None:
        from x5crop.detection.photo_geometry.observations import (
            build_sequence_observations,
        )

        run = ProfileRun(
            run_id="mixed-polarity-edge",
            coordinate_interval_px=FiniteInterval.exact(100.0),
            transition_ids=(ObservationId("negative"), ObservationId("positive")),
            trace_coordinates_px=(0, 100),
            role_hint=None,
            qualified_anchor_roles=(BoundaryRole.START,),
            support_fraction=1.0,
            continuous_support_fraction=1.0,
            fit_residual_px=0.0,
            evidence_strength=10.0,
        )
        profile = BasicAxisProfile("sequence", 200, (0, 100), (run,))
        transitions = {
            "negative": SimpleNamespace(
                polarity=-1,
                transition_id=ObservationId("negative"),
                trace_coordinate_px=0,
                coordinate_px=100.0,
                localization_interval_px=FiniteInterval(99.0, 101.0),
                physical_position_interval_px=FiniteInterval(99.0, 101.0),
                gradient_z=4.0,
                tone_z=4.0,
                texture_z=4.0,
            ),
            "positive": SimpleNamespace(
                polarity=1,
                transition_id=ObservationId("positive"),
                trace_coordinate_px=100,
                coordinate_px=100.0,
                localization_interval_px=FiniteInterval(99.0, 101.0),
                physical_position_interval_px=FiniteInterval(99.0, 101.0),
                gradient_z=4.0,
                tone_z=4.0,
                texture_z=4.0,
            ),
        }

        edges, bands = build_sequence_observations(
            profile,
            transitions,
            mock.Mock(),
            BoundaryAxis.X,
            PositiveInterval(10.0, 10.0),
        )

        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0].polarity, 0)
        self.assertEqual(bands, ())

    def test_separator_material_can_span_an_internal_transition_peak(self) -> None:
        traces = (0, 50, 100)

        def run(name: str, coordinate: float) -> ProfileRun:
            identity = ObservationId(f"transition:{name}")
            return ProfileRun(
                run_id=name,
                coordinate_interval_px=FiniteInterval.exact(coordinate),
                transition_ids=(identity,),
                trace_coordinates_px=traces,
                role_hint=None,
                qualified_anchor_roles=(),
                support_fraction=1.0,
                continuous_support_fraction=1.0,
                fit_residual_px=0.0,
                evidence_strength=1.0,
            )

        runs = (
            run("outer-left", 100.0),
            run("inner-right", 150.0),
            run("inner-left", 160.0),
            run("outer-right", 220.0),
        )
        profile = BasicAxisProfile("sequence", 300, traces, runs)

        def edge(value: ProfileRun, polarity: int) -> BoundaryEdgeObservation:
            return BoundaryEdgeObservation(
                observation_id=ObservationId(f"edge:{value.run_id}"),
                run_id=value.run_id,
                coordinate_interval_px=value.coordinate_interval_px,
                transition_ids=value.transition_ids,
                trace_coordinates_px=traces,
                polarity=polarity,
                support_fraction=1.0,
                continuous_support_fraction=1.0,
                fit_residual_px=0.0,
                canonical_direction_degrees=None,
                fit_direction_interval_degrees=None,
                full_direction_interval_degrees=None,
            )

        edges = (
            edge(runs[0], -1),
            edge(runs[1], 1),
            edge(runs[2], -1),
            edge(runs[3], 1),
        )
        markers = {}

        def material_builder(left, right, **_kwargs):
            is_outer = (
                left.run_id == "outer-left"
                and right.run_id == "outer-right"
            )
            marker = SimpleNamespace(
                observation_id=ObservationId(
                    f"separator:{left.run_id}:{right.run_id}"
                ),
                left_edge_observation_id=left.observation_id,
                right_edge_observation_id=right.observation_id,
                independent_support_region_count=3 if is_outer else 2,
                continuous_support_fraction=1.0,
                darkness_contrast_interval=FiniteInterval.exact(1.0),
                texture_contrast_interval=FiniteInterval.exact(1.0),
            )
            markers[(left.run_id, right.run_id)] = marker
            return marker

        with mock.patch(
            "x5crop.detection.photo_geometry.separator_observations._separator_band_from_edges",
            side_effect=material_builder,
        ):
            result = build_format_separator_bands(
                profile,
                edges,
                {},
                mock.Mock(),
                BoundaryAxis.X,
            )

        self.assertIn(("outer-left", "outer-right"), markers)
        self.assertIn(
            markers[("outer-left", "outer-right")],
            result,
        )

    def test_canonical_direction_keeps_rotation_equivalent_slope_sign(self) -> None:
        direction = SharedStripDirection(
            direction_id="direction:slope-sign",
            selected_observation_ids=(ObservationId("observation:slope-sign"),),
            full_angle_interval_degrees=FiniteInterval(-0.3, -0.2),
            canonical_angle_degrees=-0.25,
        )
        expected = np.tan(np.deg2rad(-0.25))

        for long_axis, cross_axis in (
            (BoundaryAxis.X, BoundaryAxis.Y),
            (BoundaryAxis.Y, BoundaryAxis.X),
        ):
            with self.subTest(long_axis=long_axis):
                self.assertAlmostEqual(
                    canonical_source_cross_axis_slope(direction, cross_axis),
                    expected,
                )
                self.assertAlmostEqual(
                    canonical_source_sequence_axis_slope(direction, long_axis),
                    -expected,
                )
                cross_line = canonical_boundary_line(
                    direction,
                    boundary_axis=cross_axis,
                    source_axis_long=long_axis,
                    trace_coordinate_px=100.0,
                    position_px=20.0,
                    support_projection_px=FiniteInterval(0.0, 200.0),
                )
                coordinate = (
                    (cross_line.offset_px - cross_line.normal_x * 150.0)
                    / cross_line.normal_y
                    if cross_axis == BoundaryAxis.Y
                    else (
                        cross_line.offset_px - cross_line.normal_y * 150.0
                    )
                    / cross_line.normal_x
                )
                self.assertAlmostEqual(
                    coordinate - 20.0,
                    expected * 50.0,
                )

    def test_vertical_strip_preserves_source_slope_sign(self) -> None:
        measurement_set = make_side_measurement_set(
            tuple((10.0 - index * 0.1,) for index in range(7))
        )

        observation = fit_format_bound_boundary_observation(
            measurement_set,
            transition_ids=tuple(
                item.transition_id for item in measurement_set.transitions
            ),
            role=BoundaryRole.TOP,
            source_axis_long=BoundaryAxis.Y,
            boundary_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        )

        self.assertIsNotNone(observation)
        assert observation is not None
        self.assertLess(observation.angle_interval_degrees.center, 0.0)

    def test_format_role_observation_propagates_only_robust_inliers(
        self,
    ) -> None:
        measurement_set = make_side_measurement_set(
            (
                (10.0,),
                (10.0,),
                (10.0,),
                (40.0,),
                (10.0,),
                (10.0,),
                (10.0,),
            )
        )

        observation = fit_format_bound_boundary_observation(
            measurement_set,
            transition_ids=tuple(
                item.transition_id for item in measurement_set.transitions
            ),
            role=BoundaryRole.TOP,
            source_axis_long=BoundaryAxis.Y,
            boundary_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        )

        self.assertIsNotNone(observation)
        assert observation is not None
        self.assertEqual(observation.trace_support_count, 6)
        self.assertNotIn(
            ObservationId("transition:3:0"),
            observation.transition_ids,
        )

    def test_transition_width_expands_only_full_angle_safety(self) -> None:
        coordinates = tuple((10.0 + index * 0.1,) for index in range(7))
        narrow = fit_format_bound_boundary_observation(
            make_side_measurement_set(
                coordinates,
                transition_half_width_px=0.25,
            ),
            transition_ids=tuple(
                ObservationId(f"transition:{index}:0")
                for index in range(7)
            ),
            role=BoundaryRole.TOP,
            source_axis_long=BoundaryAxis.X,
            boundary_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        )
        wide = fit_format_bound_boundary_observation(
            make_side_measurement_set(
                coordinates,
                transition_half_width_px=4.0,
            ),
            transition_ids=tuple(
                ObservationId(f"transition:{index}:0")
                for index in range(7)
            ),
            role=BoundaryRole.TOP,
            source_axis_long=BoundaryAxis.X,
            boundary_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        )

        self.assertIsNotNone(narrow)
        self.assertIsNotNone(wide)
        assert narrow is not None and wide is not None
        self.assertEqual(
            narrow.fit_angle_interval_degrees,
            wide.fit_angle_interval_degrees,
        )
        self.assertGreater(
            wide.angle_interval_degrees.width,
            narrow.angle_interval_degrees.width,
        )


if __name__ == "__main__":
    unittest.main()
