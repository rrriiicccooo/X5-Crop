from __future__ import annotations

from dataclasses import replace
from unittest.mock import patch

from tools.tests.photo_geometry_support import *
from x5crop.detection.photo_geometry.sequence_direction_measurement import (
    sequence_run_direction_measurement,
)


class BoundaryMeasurementContractTest(unittest.TestCase):
    def test_role_qualified_continuous_bend_requires_unanimous_role_relation(
        self,
    ) -> None:
        from x5crop.detection.photo_geometry.observations import (
            build_sequence_observations,
        )

        traces = (0, 100, 200, 300, 400)
        coordinates = (100.0, 101.0, 100.0, 101.0, 114.0)

        def transition(index: int) -> PhotoBoundaryTransition:
            coordinate = coordinates[index]
            return PhotoBoundaryTransition(
                transition_id=ObservationId(f"continuous-bend:{index}"),
                query_id="query:continuous-bend",
                trace_ordinal=index,
                trace_coordinate_px=traces[index],
                canonical_coordinate_px=coordinate,
                localization_interval_px=FiniteInterval(
                    coordinate - 0.1,
                    coordinate + 0.1,
                ),
                physical_position_interval_px=FiniteInterval(
                    coordinate - 0.1,
                    coordinate + 0.1,
                ),
                gradient_z=10.0,
                tone_z=10.0,
                texture_z=1.0,
                left_tone_mean=1.0,
                right_tone_mean=20.0,
                left_texture_mean=1.0,
                right_texture_mean=4.0,
                polarity=1,
                peak_width_px=1.0,
                prominence=10.0,
                local_noise=0.0,
            )

        values = tuple(transition(index) for index in range(len(traces)))
        run = ProfileRun(
            run_id="continuous-bend",
            coordinate_interval_px=FiniteInterval(99.0, 115.0),
            transition_ids=tuple(item.transition_id for item in values),
            trace_coordinates_px=traces,
            role_hint=None,
            qualified_anchor_roles=(BoundaryRole.START,),
            support_fraction=1.0,
            continuous_support_fraction=1.0,
            fit_residual_px=1.0,
            evidence_strength=20.0,
            pair_qualified=True,
        )
        profile = BasicAxisProfile("sequence", 300, traces, (run,))

        edges, bands = build_sequence_observations(
            profile,
            {str(item.transition_id): item for item in values},
            mock.Mock(),
            BoundaryAxis.X,
            PositiveInterval(10.0, 10.0),
            reference_trace_px=200.0,
            frame_width_px=PositiveInterval(90.0, 110.0),
        )

        self.assertEqual(len(edges), 1)
        self.assertEqual(bands, ())
        self.assertEqual(
            edges[0].transition_ids,
            tuple(item.transition_id for item in values[:-1]),
        )
        self.assertEqual(edges[0].trace_coordinates_px, traces[:-1])
        self.assertIsNone(edges[0].canonical_direction_degrees)
        self.assertIsNone(edges[0].fit_direction_interval_degrees)
        self.assertIsNone(edges[0].full_direction_interval_degrees)

        inconsistent = (
            replace(
                values[0],
                left_texture_mean=4.0,
                right_texture_mean=1.0,
            ),
            *values[1:],
        )
        edges, bands = build_sequence_observations(
            profile,
            {str(item.transition_id): item for item in inconsistent},
            mock.Mock(),
            BoundaryAxis.X,
            PositiveInterval(10.0, 10.0),
            reference_trace_px=200.0,
            frame_width_px=PositiveInterval(90.0, 110.0),
        )

        self.assertEqual(edges, ())
        self.assertEqual(bands, ())

    def test_unqualified_bend_does_not_create_sequence_authority(self) -> None:
        from x5crop.detection.photo_geometry.observations import (
            build_sequence_observations,
        )

        traces = (0, 100, 200, 300)
        values = tuple(
            PhotoBoundaryTransition(
                transition_id=ObservationId(f"unqualified-bend:{index}"),
                query_id="query:unqualified-bend",
                trace_ordinal=index,
                trace_coordinate_px=trace,
                canonical_coordinate_px=coordinate,
                localization_interval_px=FiniteInterval(
                    coordinate - 0.1,
                    coordinate + 0.1,
                ),
                physical_position_interval_px=FiniteInterval(
                    coordinate - 0.1,
                    coordinate + 0.1,
                ),
                gradient_z=10.0,
                tone_z=10.0,
                texture_z=1.0,
                left_tone_mean=1.0,
                right_tone_mean=20.0,
                left_texture_mean=1.0,
                right_texture_mean=4.0,
                polarity=1,
                peak_width_px=1.0,
                prominence=10.0,
                local_noise=0.0,
            )
            for index, (trace, coordinate) in enumerate(
                zip(traces, (100.0, 101.0, 100.0, 101.0), strict=True)
            )
        )
        run = ProfileRun(
            run_id="unqualified-bend",
            coordinate_interval_px=FiniteInterval(99.0, 102.0),
            transition_ids=tuple(item.transition_id for item in values),
            trace_coordinates_px=traces,
            role_hint=None,
            qualified_anchor_roles=(),
            support_fraction=1.0,
            continuous_support_fraction=1.0,
            fit_residual_px=1.0,
            evidence_strength=20.0,
            pair_qualified=False,
        )

        edges, bands = build_sequence_observations(
            BasicAxisProfile("sequence", 300, traces, (run,)),
            {str(item.transition_id): item for item in values},
            mock.Mock(),
            BoundaryAxis.X,
            PositiveInterval(10.0, 10.0),
            reference_trace_px=150.0,
            frame_width_px=PositiveInterval(90.0, 110.0),
        )

        self.assertEqual(edges, ())
        self.assertEqual(bands, ())

    def test_impossible_sequence_family_skips_robust_refit(self) -> None:
        def transition(
            identity: str,
            *,
            trace_ordinal: int,
            trace: int,
            coordinate: float,
        ) -> PhotoBoundaryTransition:
            return PhotoBoundaryTransition(
                transition_id=ObservationId(identity),
                query_id="query:impossible-family",
                trace_ordinal=trace_ordinal,
                trace_coordinate_px=trace,
                canonical_coordinate_px=coordinate,
                localization_interval_px=FiniteInterval(
                    coordinate - 0.5,
                    coordinate + 0.5,
                ),
                physical_position_interval_px=FiniteInterval(
                    coordinate - 0.5,
                    coordinate + 0.5,
                ),
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
            transition("family:left:0", trace_ordinal=0, trace=0, coordinate=100.0),
            transition("family:left:1", trace_ordinal=1, trace=10, coordinate=100.0),
            transition("family:right:0", trace_ordinal=2, trace=20, coordinate=200.0),
            transition("family:right:1", trace_ordinal=3, trace=30, coordinate=200.0),
        )
        transitions = {str(item.transition_id): item for item in values}

        def run(name: str, selected: tuple[int, int]) -> ProfileRun:
            chosen = tuple(values[index] for index in selected)
            return ProfileRun(
                run_id=name,
                coordinate_interval_px=FiniteInterval(
                    min(item.coordinate_px for item in chosen) - 0.5,
                    max(item.coordinate_px for item in chosen) + 0.5,
                ),
                transition_ids=tuple(item.transition_id for item in chosen),
                trace_coordinates_px=tuple(
                    item.trace_coordinate_px for item in chosen
                ),
                role_hint=None,
                qualified_anchor_roles=(BoundaryRole.START,),
                support_fraction=0.5,
                continuous_support_fraction=0.5,
                fit_residual_px=0.0,
                evidence_strength=10.0,
                pair_qualified=True,
            )

        profile = BasicAxisProfile(
            "sequence",
            300,
            (0, 10, 20, 30),
            (run("family:left", (0, 1)), run("family:right", (2, 3))),
        )
        with patch(
            "x5crop.detection.photo_geometry.sequence_edge_families.fit_transition_line"
        ) as robust_refit:
            merged = merge_sequence_edge_families(
                profile,
                transitions,
                reference_trace_px=15.0,
                boundary_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
            )

        robust_refit.assert_not_called()
        self.assertEqual(merged.runs, profile.runs)

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
            queried_trace_coordinates_px=(902, 1056),
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
            position_interval_px=FiniteInterval(99.0, 101.0),
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

    def test_separator_pairing_accepts_direct_wide_material_below_one_frame(
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
            interval = run.coordinate_interval_px
            return BoundaryEdgeObservation(
                observation_id=ObservationId(f"edge:{run.run_id}"),
                run_id=run.run_id,
                discovery_interval_px=interval,
                reference_trace_px=50.0,
                canonical_position_px=interval.center,
                fit_position_interval_px=interval,
                full_position_interval_px=interval,
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
                PositiveInterval(900.0, 920.0),
            )

        self.assertEqual(result, (marker,))
        builder.assert_called_once()

    def test_separator_pairing_rejects_material_wide_enough_for_a_frame(
        self,
    ) -> None:
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

        left_run = run("left", 100.0)
        right_run = run("right", 900.0)
        profile = BasicAxisProfile(
            "sequence",
            1000,
            traces,
            (left_run, right_run),
        )

        def edge(value: ProfileRun, polarity: int) -> BoundaryEdgeObservation:
            interval = value.coordinate_interval_px
            return BoundaryEdgeObservation(
                observation_id=ObservationId(f"edge:{value.run_id}"),
                run_id=value.run_id,
                discovery_interval_px=interval,
                reference_trace_px=50.0,
                canonical_position_px=interval.center,
                fit_position_interval_px=interval,
                full_position_interval_px=interval,
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

        with mock.patch(
            "x5crop.detection.photo_geometry.separator_observations._separator_band_from_edges",
            return_value=mock.Mock(),
        ) as builder:
            result = build_format_separator_bands(
                profile,
                (edge(left_run, -1), edge(right_run, 1)),
                {},
                mock.Mock(),
                BoundaryAxis.X,
                PositiveInterval(700.0, 720.0),
            )

        self.assertEqual(result, ())
        builder.assert_not_called()

    def test_polarity_ambiguous_edge_remains_an_observation(self) -> None:
        from x5crop.detection.photo_geometry.observations import (
            build_sequence_observations,
        )

        run = ProfileRun(
            run_id="mixed-polarity-edge",
            coordinate_interval_px=FiniteInterval(80.0, 120.0),
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
        def transition(
            identity: str,
            *,
            trace_ordinal: int,
            trace_coordinate_px: int,
            polarity: int,
        ) -> PhotoBoundaryTransition:
            return PhotoBoundaryTransition(
                transition_id=ObservationId(identity),
                query_id="query:mixed-polarity",
                trace_ordinal=trace_ordinal,
                trace_coordinate_px=trace_coordinate_px,
                canonical_coordinate_px=100.0,
                localization_interval_px=FiniteInterval(99.0, 101.0),
                physical_position_interval_px=FiniteInterval(99.0, 101.0),
                gradient_z=4.0,
                tone_z=4.0,
                texture_z=4.0,
                left_tone_mean=1.0,
                right_tone_mean=1.0,
                left_texture_mean=1.0,
                right_texture_mean=1.0,
                polarity=polarity,
                peak_width_px=1.0,
                prominence=4.0,
                local_noise=0.0,
            )

        transitions = {
            "negative": transition(
                "negative",
                trace_ordinal=0,
                trace_coordinate_px=0,
                polarity=-1,
            ),
            "positive": transition(
                "positive",
                trace_ordinal=1,
                trace_coordinate_px=100,
                polarity=1,
            ),
        }

        edges, bands = build_sequence_observations(
            profile,
            transitions,
            mock.Mock(),
            BoundaryAxis.X,
            PositiveInterval(10.0, 10.0),
            reference_trace_px=50.0,
            frame_width_px=PositiveInterval(90.0, 110.0),
        )

        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0].polarity, 0)
        self.assertEqual(edges[0].discovery_interval_px, FiniteInterval(80.0, 120.0))
        self.assertLess(edges[0].fit_position_interval_px.width, 2.0)
        self.assertLess(
            edges[0].full_position_interval_px.width,
            edges[0].discovery_interval_px.width,
        )
        self.assertTrue(
            edges[0].full_position_interval_px.contains(
                edges[0].fit_position_interval_px.minimum
            )
        )
        self.assertEqual(bands, ())

    def test_separator_material_cannot_skip_an_internal_transition(self) -> None:
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
            interval = value.coordinate_interval_px
            return BoundaryEdgeObservation(
                observation_id=ObservationId(f"edge:{value.run_id}"),
                run_id=value.run_id,
                discovery_interval_px=interval,
                reference_trace_px=50.0,
                canonical_position_px=interval.center,
                fit_position_interval_px=interval,
                full_position_interval_px=interval,
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
                PositiveInterval(250.0, 260.0),
            )

        self.assertNotIn(("outer-left", "outer-right"), markers)
        self.assertEqual(
            set(markers),
            {
                ("outer-left", "inner-right"),
                ("inner-left", "outer-right"),
            },
        )
        self.assertEqual(
            {item.observation_id for item in result},
            {item.observation_id for item in markers.values()},
        )

    def test_canonical_direction_keeps_rotation_equivalent_slope_sign(self) -> None:
        direction = SharedStripDirection(
            direction_id="direction:slope-sign",
            selected_observation_ids=(ObservationId("observation:slope-sign"),),
            full_angle_interval_degrees=FiniteInterval(-0.3, -0.2),
            observed_angle_interval_degrees=FiniteInterval(-0.3, -0.2),
            canonical_angle_degrees=-0.25,
        )
        expected = np.tan(np.deg2rad(-0.25))

        for long_axis, cross_axis in (
            (BoundaryAxis.X, BoundaryAxis.Y),
            (BoundaryAxis.Y, BoundaryAxis.X),
        ):
            with self.subTest(long_axis=long_axis):
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
