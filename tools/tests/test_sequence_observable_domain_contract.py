from __future__ import annotations

from copy import copy
from dataclasses import replace
import math
import unittest

import numpy as np

from tools.tests.photo_geometry_support import make_native_test_field
from tools.tests.test_sequence_connections_contract import (
    SPEC,
    _case,
    _prepare,
    _validate,
)
from x5crop.detection.photo_geometry.measurement_model import (
    PhotoBoundaryMeasurementQuery,
)
from x5crop.detection.photo_geometry.model import (
    BoundaryAxis,
    BoundaryRole,
    QueryPurpose,
)
from x5crop.detection.photo_geometry.native_trace_bridge_measurement import (
    decode_credible_mask,
    native_trace_bridge_normalization_domain,
)
from x5crop.detection.photo_geometry.observation_types import (
    BoundaryEdgeMeasurementBasis,
    BoundaryEdgeObservation,
)
from x5crop.detection.photo_geometry.registered_measurement import (
    measure_registered_queries,
)
from x5crop.detection.photo_geometry.robust_line_fit import physical_line_region
from x5crop.detection.photo_geometry.sequence_connections import (
    prepare_sequence_connections,
    sequence_connection_persistent_input_bound,
    sequence_connection_plans,
    sequence_connection_requests,
)
from x5crop.domain import FiniteInterval, ObservationId, PositiveInterval


def _full_query_case(
    *,
    center: int = 60,
    broken: bool = False,
    dense_boundary: bool = False,
    transpose: bool = False,
    trace_length: int = 512,
):
    """Real registered measurements whose declared window reaches both edges."""
    gray = np.full((trace_length, 201), 30, dtype=np.uint8)
    for row in range(trace_length):
        edge = center + round(3 * math.sin(2 * math.pi * (row - 20) / 40))
        gray[row] = (
            30 + 170 * np.clip((np.arange(201) - edge) / 8.0, 0.0, 1.0)
        ).astype(np.uint8)
    if dense_boundary:
        coordinates = np.arange(201)
        gray[90] = np.clip(
            20 + 2 * coordinates + 70 * (coordinates >= 60),
            0,
            255,
        ).astype(np.uint8)
    elif broken:
        gray[90] = 30
    axis = BoundaryAxis.Y if transpose else BoundaryAxis.X
    if transpose:
        gray = gray.T.copy()
    field = make_native_test_field(
        gray,
        "vertical" if transpose else "horizontal",
    )
    traces = (40, 60, 80, 100, 120, 140)
    scale = PositiveInterval.exact(20.0)
    baseline = PhotoBoundaryMeasurementQuery(
        "sequence:baseline",
        0,
        "lane:connection",
        QueryPurpose.SEQUENCE_BASELINE,
        axis,
        traces,
        (FiniteInterval(0.0, 200.0),) * 6,
        (FiniteInterval(0.0, 200.0),) * 6,
        120.0,
        scale,
        scale,
        SPEC.measurement_halo_px(20.0),
        ("registered:connection",),
    )
    window = replace(
        baseline,
        query_id="sequence:window:full-edge",
        registration_index=1,
        purpose=QueryPurpose.SEQUENCE_ANCHOR_WINDOW,
    )
    measurements = measure_registered_queries(field, (baseline, window))
    original = tuple(
        item
        for item in measurements[1].transitions
        if item.trace_coordinate_px in (60, 80, 100, 120)
    )
    if len(original) != 4:
        raise AssertionError("synthetic edge case did not retain four parent peaks")
    region = physical_line_region(
        tuple(
            (item.trace_coordinate_px, item.physical_position_interval_px)
            for item in original
        ),
        math.tan(math.radians(SPEC.maximum_measurable_line_angle_degrees)),
        0.0,
    )
    center_position = original[0].canonical_coordinate_px
    projected = region.project(0.0)
    protected = FiniteInterval(center_position - 2.0, center_position + 2.0)
    parent = BoundaryEdgeObservation(
        ObservationId("native:parent"),
        "native:run",
        projected,
        0.0,
        center_position,
        FiniteInterval(center_position - 0.5, center_position + 0.5),
        FiniteInterval(
            min(protected.minimum, projected.minimum),
            max(protected.maximum, projected.maximum),
        ),
        tuple(item.transition_id for item in original),
        tuple(item.trace_coordinate_px for item in original),
        1,
        4 / 6,
        1.0,
        0.0,
        0.0,
        FiniteInterval.exact(0.0),
        FiniteInterval(-4.0, 4.0),
        BoundaryEdgeMeasurementBasis.DIRECT_WITH_AGGREGATE,
        ObservationId("aggregate:support"),
        (BoundaryRole.START,),
        physical_line_region=region,
        position_protection_interval_px=protected,
    )
    return field, parent, measurements


def _generous_prepare(case):
    field, parent, measurements = case
    pixels = field.source_extent.width * field.source_extent.height
    measurement_work = sum(
        item.coverage.pixel_query_count
        + item.coverage.peak_source_value_visit_bound
        for item in measurements
    )
    boundary_axis = measurements[1].query.boundary_axis
    cross_extent = (
        field.source_extent.height
        if boundary_axis == BoundaryAxis.X
        else field.source_extent.width
    )
    persistent = sequence_connection_persistent_input_bound(
        measurements,
        1,
        cross_extent,
    )
    return prepare_sequence_connections(
        field,
        (parent,),
        measurements,
        maximum_value_visits=128 * pixels - measurement_work,
        maximum_temporary_bytes=10 * pixels + 32 * 1024 * 1024,
        persistent_input_bytes=persistent,
    )


def _expected_observable_corridor(field, measurements) -> FiniteInterval:
    baseline = measurements[0].query
    query = measurements[1].query
    low, high = native_trace_bridge_normalization_domain(
        field.source_extent,
        query.boundary_axis,
        baseline.search_intervals_px[0],
        baseline.boundary_axis_scale_px_per_mm.maximum,
    )
    start = max(low, math.ceil(query.search_intervals_px[0].minimum))
    stop = min(high, math.floor(query.search_intervals_px[0].maximum) + 1)
    if stop <= start:
        raise AssertionError("expected synthetic case to have an observable corridor")
    return FiniteInterval(float(start), float(stop - 1))


def _measurement_ledger(measurements):
    return tuple(
        (
            measurement.query.query_id,
            measurement.query.search_intervals_px,
            measurement.query.transition_ownership_intervals_px,
            tuple(
                (
                    source.trace_coordinate_px,
                    source.normalization_domain_px,
                    source.signal_sha256,
                )
                for source in measurement.peak_trace_sources
            ),
            tuple(
                (
                    group.primitive_id,
                    group.source.signal_sha256,
                    group.measurement_domain_px,
                    group.credible_group_domain_px,
                    group.candidate_peak_coordinates_px,
                    group.reliable_gradient_partitions,
                )
                for group in measurement.peak_source_groups
            ),
            tuple(
                (
                    transition.transition_id,
                    transition.query_id,
                    transition.trace_coordinate_px,
                    None
                    if transition.peak_source is None
                    else (
                        transition.peak_source.group_id,
                        transition.peak_source.source_coordinate_px,
                        transition.peak_source.candidate_ordinal,
                    ),
                )
                for transition in measurement.transitions
            ),
        )
        for measurement in measurements
    )


class SequenceObservableDomainContractTest(unittest.TestCase):
    def test_full_edge_query_uses_kernel_intersection_without_narrowing_to_parent(self):
        for transpose in (False, True):
            with self.subTest(transpose=transpose):
                case = _full_query_case(transpose=transpose)
                field, parent, measurements = case
                trace_axis_length = (
                    field.source_extent.height
                    if measurements[1].query.boundary_axis == BoundaryAxis.X
                    else field.source_extent.width
                )
                self.assertEqual(trace_axis_length, 512)
                request = sequence_connection_requests(
                    (parent,),
                    measurements,
                    source_extent=field.source_extent,
                )[0]
                self.assertIsNone(request.failure_kind)
                expected = _expected_observable_corridor(field, measurements)
                plans = sequence_connection_plans(field, (request,), measurements)
                self.assertEqual(len(plans), 1)
                plan = plans[0]
                self.assertEqual(plan.coordinate_interval_px, expected)
                self.assertEqual(
                    {
                        group.measurement_domain_px
                        for group in measurements[1].peak_source_groups
                    },
                    {(int(expected.minimum), int(expected.maximum))},
                )
                self.assertTrue(
                    all(
                        expected.contains(endpoint)
                        for transition in measurements[1].transitions
                        for endpoint in (
                            transition.physical_position_interval_px.minimum,
                            transition.physical_position_interval_px.maximum,
                        )
                    )
                )
                self.assertNotEqual(
                    plan.coordinate_interval_px,
                    FiniteInterval(*request.trace_interval_px),
                )
                self.assertEqual(plan.source_id, field.source_id)
                self.assertEqual(plan.source_extent, field.source_extent)
                self.assertEqual(
                    plan.original_query_id,
                    measurements[1].query.query_id,
                )
                self.assertEqual(
                    plan.baseline_query_id,
                    measurements[0].query.query_id,
                )
                self.assertEqual(
                    plan.normalization_interval_px,
                    measurements[0].query.search_intervals_px[0],
                )
                self.assertEqual(
                    plan.original_trace_coordinates_px,
                    measurements[1].query.trace_positions_px,
                )
                self.assertEqual(
                    plan.boundary_axis,
                    measurements[1].query.boundary_axis,
                )
                self.assertEqual(
                    plan.coordinate_scale_px_per_mm,
                    measurements[1].query.boundary_axis_scale_px_per_mm.maximum,
                )
                self.assertFalse(plan.split_gradient_reversals)
                self.assertTrue(plan.record_peaks)
                self.assertFalse(plan.retain_responses)
                before = _measurement_ledger(measurements)
                evidence = _generous_prepare(case)
                self.assertIsNotNone(evidence.signal_batch)
                self.assertIsNotNone(evidence.batch)
                self.assertEqual(evidence.signal_batch.plans[0].coordinate_interval_px, expected)
                self.assertEqual(evidence.batch.plans[0].coordinate_interval_px, expected)
                self.assertIsNotNone(evidence.assessments[0].constraint)
                self.assertEqual(_measurement_ledger(evidence.measurements), before)
                pixels = field.source_extent.width * field.source_extent.height
                measurement_work = sum(
                    item.coverage.pixel_query_count
                    + item.coverage.peak_source_value_visit_bound
                    for item in measurements
                )
                self.assertEqual(
                    evidence.budget.maximum_value_visits,
                    128 * pixels - measurement_work,
                )
                self.assertEqual(
                    evidence.budget.maximum_temporary_bytes,
                    10 * pixels + 32 * 1024 * 1024,
                )
                _validate(case, evidence)

    def test_internal_query_keeps_the_existing_two_axis_behavior(self):
        for transpose in (False, True):
            with self.subTest(transpose=transpose):
                case = _case(transpose=transpose)
                evidence = _prepare(case)
                _validate(case, evidence)
                self.assertIsNotNone(evidence.assessments[0].constraint)
                plan = evidence.signal_batch.plans[0]
                self.assertEqual(
                    plan.coordinate_interval_px,
                    case[2][1].query.search_intervals_px[0],
                )

    def test_boundary_cut_groups_and_broken_rows_remain_unavailable_on_both_axes(self):
        for center in (6, 185):
            for transpose in (False, True):
                with self.subTest(center=center, transpose=transpose):
                    case = _full_query_case(center=center, transpose=transpose)
                    groups = case[2][1].peak_source_groups
                    self.assertTrue(groups)
                    self.assertFalse(all(group.complete for group in groups))
                    evidence = _generous_prepare(case)
                    _validate(case, evidence)
                    self.assertIsNotNone(evidence.requests[0].failure_kind)
                    self.assertIsNone(evidence.assessments[0].constraint)

        for transpose in (False, True):
            with self.subTest(broken=True, transpose=transpose):
                case = _full_query_case(center=60, broken=True, transpose=transpose)
                field, parent, measurements = case
                request = sequence_connection_requests(
                    (parent,),
                    measurements,
                    source_extent=field.source_extent,
                )[0]
                self.assertIsNone(request.failure_kind)
                evidence = _generous_prepare(case)
                _validate(case, evidence)
                self.assertIsNotNone(evidence.signal_batch)
                self.assertIsNone(evidence.batch)
                self.assertEqual(
                    evidence.assessments[0].failure_kind,
                    "original_connection_unavailable",
                )
                self.assertIsNone(evidence.assessments[0].constraint)

        for transpose in (False, True):
            with self.subTest(dense_boundary=True, transpose=transpose):
                case = _full_query_case(
                    center=60,
                    dense_boundary=True,
                    transpose=transpose,
                )
                field, parent, measurements = case
                request = sequence_connection_requests(
                    (parent,),
                    measurements,
                    source_extent=field.source_extent,
                )[0]
                self.assertIsNone(request.failure_kind)
                evidence = _generous_prepare(case)
                self.assertIsNotNone(evidence.signal_batch)
                self.assertIsNotNone(evidence.batch)
                strip = next(
                    item
                    for item in evidence.batch.strips
                    if item.trace_start_px <= 90 < item.trace_stop_px
                )
                credible = decode_credible_mask(
                    strip,
                    trace_interval_px=(90, 91),
                )[0]
                self.assertTrue(bool(credible[0]) or bool(credible[-1]))
                self.assertEqual(
                    evidence.assessments[0].failure_kind,
                    "dense_group_unavailable",
                )
                self.assertIsNone(evidence.assessments[0].constraint)
                _validate(case, evidence)

    def test_empty_observable_intersection_is_unavailable(self):
        field, parent, measurements = _full_query_case()
        window = copy(measurements[1])
        query = replace(
            window.query,
            search_intervals_px=(FiniteInterval(0.0, 5.0),) * 6,
            transition_ownership_intervals_px=(FiniteInterval(0.0, 5.0),) * 6,
        )
        object.__setattr__(window, "query", query)
        tampered_measurements = (measurements[0], window)
        request = sequence_connection_requests(
            (parent,),
            tampered_measurements,
            source_extent=field.source_extent,
        )[0]
        self.assertEqual(request.failure_kind, "source_domain_unavailable")
        self.assertEqual(
            sequence_connection_plans(field, (request,), tampered_measurements),
            (),
        )
        evidence = _generous_prepare((field, parent, tampered_measurements))
        self.assertIsNone(evidence.batch)
        self.assertIsNone(evidence.assessments[0].constraint)

    def test_plan_expansion_narrowing_and_missing_raw_peak_are_rejected(self):
        for transpose in (False, True):
            with self.subTest(transpose=transpose):
                case = _full_query_case(transpose=transpose)
                evidence = _generous_prepare(case)
                self.assertIsNotNone(evidence.signal_batch)
                plan = evidence.signal_batch.plans[0]
                for label, interval in (
                    (
                        "expanded",
                        FiniteInterval(
                            plan.coordinate_interval_px.minimum - 1.0,
                            plan.coordinate_interval_px.maximum,
                        ),
                    ),
                    (
                        "narrowed",
                        FiniteInterval(
                            plan.coordinate_interval_px.minimum + 1.0,
                            plan.coordinate_interval_px.maximum - 1.0,
                        ),
                    ),
                ):
                    with self.subTest(plan_mutation=label):
                        forged_plan = copy(plan)
                        object.__setattr__(forged_plan, "coordinate_interval_px", interval)
                        forged_batch = copy(evidence.signal_batch)
                        object.__setattr__(forged_batch, "plans", (forged_plan,))
                        forged_evidence = replace(evidence, signal_batch=forged_batch)
                        with self.assertRaises(ValueError):
                            _validate(case, forged_evidence)

                missing_raw = copy(case[2][1])
                object.__setattr__(
                    missing_raw,
                    "transitions",
                    case[2][1].transitions[:-1],
                )
                forged_evidence = replace(
                    evidence,
                    measurements=(case[2][0], missing_raw),
                )
                with self.assertRaises(ValueError):
                    _validate(case, forged_evidence)


if __name__ == "__main__":
    unittest.main()
