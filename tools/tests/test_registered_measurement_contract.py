from __future__ import annotations

from tools.tests.photo_geometry_support import *


class RegisteredMeasurementContractTest(unittest.TestCase):
    def test_measurement_spec_contains_only_production_values(self) -> None:
        spec = PHOTO_BOUNDARY_MEASUREMENT_SPEC
        self.assertEqual(spec.lattice_spacing_mm(12.0), 2.0)
        self.assertEqual(spec.lattice_spacing_mm(36.0), 3.0)
        self.assertEqual(spec.lattice_spacing_mm(120.0), 4.0)
        self.assertEqual(spec.local_window_mm, 0.25)
        self.assertEqual(spec.transition_gap_mm, 0.05)
        self.assertFalse(hasattr(spec, "maximum_transition_interval_mm"))
        self.assertFalse(hasattr(spec, "top_bottom_search_angle_degrees"))
        self.assertEqual(spec.maximum_measurable_line_angle_degrees, 4.0)
        self.assertEqual(spec.robust_loss_minimum_scale_mm, 0.05)
        self.assertFalse(hasattr(spec, "robust_loss_mad_multiplier"))
        self.assertEqual(spec.robust_fit_maximum_evaluations, 128)
        self.assertEqual(spec.robust_fit_tolerance, 1.0e-8)
        self.assertFalse(hasattr(spec, "huber_irls_rounds"))
        self.assertEqual(spec.maximum_streaming_block_pixels, 1_048_576)
        self.assertFalse(hasattr(spec, "nominal_calibration_sample_ids"))
        self.assertFalse(hasattr(spec, "stress_excluded_sample_id"))
        self.assertFalse(hasattr(spec, "contract_id"))

    def test_measurement_field_is_immutable_and_partial_query_is_unavailable(
        self,
    ) -> None:
        gray = np.zeros((20, 30), dtype=np.uint8)
        field = PhotoBoundaryMeasurementField(gray, "horizontal")
        self.assertFalse(field.source_gray.flags.writeable)
        query = PhotoBoundaryMeasurementQuery(
            query_id="query:test",
            registration_index=0,
            lane_id="lane:0",
            purpose=QueryPurpose.SEQUENCE_ANCHOR_WINDOW,
            boundary_axis=BoundaryAxis.X,
            trace_positions_px=(2, 4, 6, 8),
            search_intervals_px=(FiniteInterval(0.0, 29.0),) * 4,
            transition_ownership_intervals_px=(
                FiniteInterval(0.0, 29.0),
            )
            * 4,
            expected_support_px=20.0,
            boundary_axis_scale_px_per_mm=PositiveInterval(1.0, 1.1),
            trace_axis_scale_px_per_mm=PositiveInterval(1.0, 1.1),
            measurement_halo_px=2,
            registration_provenance_ids=("anchor-domain:test",),
        )
        coverage = PhotoBoundaryCoverageReceipt(
            query_id=query.query_id,
            registered_trace_count=4,
            completed_trace_count=3,
            registered_coordinate_count=120,
            completed_coordinate_count=90,
            pixel_query_count=90,
            streaming_block_count=1,
            peak_temporary_bytes=4096,
            complete=False,
        )
        measurement = PhotoBoundaryMeasurementSet(
            query=query,
            state=EvidenceState.UNAVAILABLE,
            transitions=(),
            coverage=coverage,
        )
        self.assertEqual(measurement.state, EvidenceState.UNAVAILABLE)
        with self.assertRaises(ValueError):
            PhotoBoundaryMeasurementSet(
                query=query,
                state=EvidenceState.SUPPORTED,
                transitions=(),
                coverage=coverage,
            )

    def test_overlapping_query_halos_emit_transition_once(self) -> None:
        gray = np.zeros((4, 30), dtype=np.uint8)
        gray[:, 15:] = 255
        field = PhotoBoundaryMeasurementField(gray, "horizontal")
        common = dict(
            lane_id="lane:0",
            purpose=QueryPurpose.SEQUENCE_ANCHOR_WINDOW,
            boundary_axis=BoundaryAxis.X,
            trace_positions_px=(0, 1, 2, 3),
            expected_support_px=20.0,
            boundary_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
            trace_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
            measurement_halo_px=10,
        )
        queries = (
            PhotoBoundaryMeasurementQuery(
                query_id="query:baseline",
                registration_index=0,
                search_intervals_px=(FiniteInterval(0.0, 29.0),) * 4,
                transition_ownership_intervals_px=(FiniteInterval(0.0, 29.0),)
                * 4,
                registration_provenance_ids=("baseline",),
                purpose=QueryPurpose.SEQUENCE_BASELINE,
                **{
                    key: value
                    for key, value in common.items()
                    if key != "purpose"
                },
            ),
            PhotoBoundaryMeasurementQuery(
                query_id="query:left",
                registration_index=1,
                search_intervals_px=(FiniteInterval(0.0, 20.0),) * 4,
                transition_ownership_intervals_px=(FiniteInterval(0.0, 9.0),)
                * 4,
                registration_provenance_ids=("tile:left",),
                **common,
            ),
            PhotoBoundaryMeasurementQuery(
                query_id="query:right",
                registration_index=2,
                search_intervals_px=(FiniteInterval(9.0, 29.0),) * 4,
                transition_ownership_intervals_px=(FiniteInterval(10.0, 29.0),)
                * 4,
                registration_provenance_ids=("tile:right",),
                **common,
            ),
        )
        baseline, left, right = measure_registered_queries(field, queries)
        self.assertEqual(baseline.transitions, ())
        self.assertEqual(left.transitions, ())
        self.assertEqual(
            {item.query_id for item in right.transitions},
            {"query:right"},
        )

    def test_cross_corridor_preserves_opposite_physical_transitions_only(
        self,
    ) -> None:
        gray = np.full((40, 6), 200, dtype=np.uint8)
        gray[15:17, :] = 0
        field = PhotoBoundaryMeasurementField(gray, "horizontal")

        def query(purpose: QueryPurpose, registration_index: int):
            return PhotoBoundaryMeasurementQuery(
                query_id=f"query:{purpose.value}",
                registration_index=registration_index,
                lane_id="lane:0",
                purpose=purpose,
                boundary_axis=BoundaryAxis.Y,
                trace_positions_px=tuple(range(6)),
                search_intervals_px=(FiniteInterval(4.0, 34.0),) * 6,
                transition_ownership_intervals_px=(
                    FiniteInterval(4.0, 34.0),
                )
                * 6,
                expected_support_px=30.0,
                boundary_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
                trace_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
                measurement_halo_px=4,
                registration_provenance_ids=(f"corridor:{purpose.value}",),
            )

        cross, baseline, sequence = measure_registered_queries(
            field,
            (
                query(QueryPurpose.TOP_CORRIDOR, 0),
                query(QueryPurpose.SEQUENCE_BASELINE, 1),
                query(QueryPurpose.SEQUENCE_ANCHOR_WINDOW, 2),
            ),
        )
        self.assertEqual(baseline.transitions, ())

        cross_by_trace = {
            trace: tuple(
                item
                for item in cross.transitions
                if item.trace_coordinate_px == trace
            )
            for trace in range(6)
        }
        self.assertTrue(
            all(
                {item.polarity for item in values} == {-1, 1}
                for values in cross_by_trace.values()
            ),
            cross_by_trace,
        )
        self.assertTrue(
            all(
                len(
                    {
                        item.polarity
                        for item in sequence.transitions
                        if item.trace_coordinate_px == trace
                    }
                )
                <= 1
                for trace in range(6)
            )
        )

    def test_side_tracking_keeps_close_separator_sides_distinct(self) -> None:
        regions = track_side_transition_regions(
            (make_side_measurement_set(((100.0, 104.0),) * 5),),
            reference_trace_px=20.0,
            boundary_axis_scale_px_per_mm=PositiveInterval(10.0, 10.0),
        )
        self.assertEqual(len(regions), 2)
        self.assertNotEqual(regions[0].transition_ids, regions[1].transition_ids)

    def test_side_tracking_allows_one_missing_step_not_two(self) -> None:
        scale = PositiveInterval(10.0, 10.0)
        one_missing = make_side_measurement_set(
            ((100.0,), (100.0,), (), (100.0,), (100.0,), (100.0,))
        )
        two_missing = make_side_measurement_set(
            ((100.0,), (100.0,), (), (), (100.0,), (100.0,))
        )
        self.assertEqual(
            len(
                track_side_transition_regions(
                    (one_missing,),
                    reference_trace_px=25.0,
                    boundary_axis_scale_px_per_mm=scale,
                )
            ),
            1,
        )
        self.assertEqual(
            track_side_transition_regions(
                (two_missing,),
                reference_trace_px=25.0,
                boundary_axis_scale_px_per_mm=scale,
            ),
            (),
        )


if __name__ == "__main__":
    unittest.main()
