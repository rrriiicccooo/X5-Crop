from __future__ import annotations

from dataclasses import replace
from copy import deepcopy
import unittest
from unittest.mock import patch
import weakref

import numpy as np

from x5crop.domain import FiniteInterval, PositiveInterval
from x5crop.detection.photo_geometry.measurement_model import (
    PhotoBoundaryMeasurementField,
    PhotoBoundaryMeasurementQuery,
)
from x5crop.detection.photo_geometry.model import (
    BoundaryAxis,
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    QueryPurpose,
)
from x5crop.detection.photo_geometry.registered_measurement import measure_registered_queries
from x5crop.detection.photo_geometry import registered_measurement
from x5crop.detection.photo_geometry.registered_transition_measurement import measure_trace
from x5crop.report.development import _measurement_set_read_model
from tools.regression.report_validation import _validate_registered_normalization


class CrossNormalizationBaselineContractTest(unittest.TestCase):
    @staticmethod
    def _queries():
        traces = (0, 10, 20, 30, 40, 50)
        scale = PositiveInterval.exact(81.5144220962)
        interval = FiniteInterval(1824.3751429638355, 1997.0)
        bottom = PhotoBoundaryMeasurementQuery(
            query_id="bottom", registration_index=0, lane_id="lane:0",
            purpose=QueryPurpose.BOTTOM_CORRIDOR,
            boundary_axis=BoundaryAxis.Y, trace_positions_px=traces,
            search_intervals_px=(interval,) * len(traces),
            transition_ownership_intervals_px=(interval,) * len(traces),
            expected_support_px=50.0, boundary_axis_scale_px_per_mm=scale,
            trace_axis_scale_px_per_mm=scale, measurement_halo_px=26,
            registration_provenance_ids=("bottom-intent",),
        )
        baseline = replace(
            bottom, query_id="cross-baseline", registration_index=1,
            purpose=QueryPurpose.CROSS_BASELINE,
            search_intervals_px=(FiniteInterval(0.0, 1997.0),) * len(traces),
            transition_ownership_intervals_px=(FiniteInterval(0.0, 1997.0),) * len(traces),
        )
        return bottom, baseline

    @staticmethod
    def _source(outer_edge: int | None):
        values = np.zeros(1998, dtype=np.uint8)
        values[:1888] = 100 + 2 * (np.arange(1888) % 2)
        if outer_edge is not None:
            values[outer_edge:] = 255
        return np.repeat(values[:, None], 51, axis=1)

    def test_remote_step_does_not_erase_unchanged_local_material(self):
        records = []
        for outer_edge in (None, 1926, 1980):
            source = self._source(outer_edge)
            bottom, baseline = measure_registered_queries(
                PhotoBoundaryMeasurementField(source, "horizontal"), self._queries(),
            )
            self.assertEqual(baseline.transitions, ())
            self.assertEqual(baseline.cross_height_transitions, ())
            self.assertEqual(baseline.broad_material_transitions, ())
            inner = tuple(t for t in bottom.transitions if 1880.0 <= t.coordinate_px <= 1895.0)
            self.assertEqual(len(inner), 6)
            self.assertTrue(all(t.tone_z >= 3.0 for t in inner))
            records.append(tuple((t.left_tone_mean, t.right_tone_mean,
                                  t.left_texture_mean, t.right_texture_mean) for t in inner))
        self.assertEqual(records[0], records[1])
        self.assertEqual(records[0], records[2])

    def test_fixture_exposes_query_local_normalization_coupling(self):
        secondary = []
        for outer_edge in (None, 1926):
            measured = measure_trace(
                self._source(outer_edge)[:, 0],
                FiniteInterval(1824.3751429638355, 1997.0), 81.5144220962,
                PHOTO_BOUNDARY_MEASUREMENT_SPEC,
            )
            index = int(np.flatnonzero(measured.coordinates == 1888)[0])
            secondary.append(max(measured.tone_z[index], measured.texture_z[index]))
        self.assertGreater(secondary[0], 3.0)
        self.assertLess(secondary[1], 3.0)

    def test_cross_windows_require_exactly_one_matching_baseline(self):
        bottom, baseline = self._queries()
        field = PhotoBoundaryMeasurementField(self._source(1926), "horizontal")
        with self.assertRaisesRegex(ValueError, "baseline"):
            measure_registered_queries(field, (bottom,))
        with self.assertRaisesRegex(ValueError, "baseline"):
            measure_registered_queries(field, (bottom, baseline, replace(
                baseline, query_id="duplicate-baseline", registration_index=2,
            )))
        for invalid in (
            replace(baseline, boundary_axis=BoundaryAxis.X),
            replace(baseline, lane_id="lane:other"),
            replace(baseline, boundary_axis_scale_px_per_mm=PositiveInterval.exact(80.0)),
            replace(baseline, trace_positions_px=(0, 10, 20, 30, 40, 49)),
            replace(baseline, search_intervals_px=(FiniteInterval(1850.0, 1997.0),) * 6,
                    transition_ownership_intervals_px=(FiniteInterval(1850.0, 1997.0),) * 6),
        ):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, "baseline"):
                measure_registered_queries(field, (bottom, invalid))

    def test_baseline_never_emits_an_out_of_window_transition(self):
        source = self._source(None)
        source[1000:1200] = 200
        bottom, baseline = measure_registered_queries(
            PhotoBoundaryMeasurementField(source, "horizontal"), self._queries(),
        )
        self.assertEqual(baseline.transitions, ())
        self.assertTrue(all(t.coordinate_px >= 1824.0 for t in bottom.transitions))

    def test_common_baseline_keeps_window_and_axis_invariance(self):
        records = []
        for vertical in (False, True):
            source = self._source(1926)
            queries = self._queries()
            if vertical:
                source = source.T.copy()
                queries = tuple(replace(query, boundary_axis=BoundaryAxis.X) for query in queries)
            field = PhotoBoundaryMeasurementField(source, "vertical" if vertical else "horizontal")
            for lower in (1800.0, 1824.3751429638355, 1840.0):
                bottom, baseline = queries
                window = FiniteInterval(lower, 1997.0)
                bottom = replace(bottom, search_intervals_px=(window,) * 6,
                                 transition_ownership_intervals_px=(window,) * 6)
                measured, _baseline = measure_registered_queries(field, (bottom, baseline))
                inner = tuple(t for t in measured.transitions if 1880.0 <= t.coordinate_px <= 1895.0)
                self.assertEqual(len(inner), 6)
                records.append(tuple((t.gradient_z, t.tone_z, t.texture_z,
                                      t.localization_interval_px) for t in inner))
        self.assertTrue(all(record == records[0] for record in records))

    def test_batch_memory_counts_all_traces_but_not_window_views_twice(self):
        queries = self._queries()
        field = PhotoBoundaryMeasurementField(self._source(1926), "horizontal")
        bottom, baseline = measure_registered_queries(field, queries)
        # Eight returned float64 arrays plus one int32 coordinate array per
        # baseline trace; 26 pixels at each source end are outside the kernel.
        retained_bytes = 6 * (1998 - 52) * (8 * 8 + 4)
        self.assertGreaterEqual(baseline.coverage.peak_temporary_bytes, retained_bytes)
        radius = PHOTO_BOUNDARY_MEASUREMENT_SPEC.local_measurement_work_radius_px(81.5144220962)
        self.assertEqual(baseline.coverage.pixel_query_count, 6 * 1998 * (2 * radius + 2))
        self.assertEqual(bottom.coverage.pixel_query_count, 6 * (1998 - 1825))
        duplicate_view = replace(queries[0], query_id="second-view", registration_index=2)
        same_bottom, same_baseline, _view = measure_registered_queries(field, (*queries, duplicate_view))
        self.assertEqual(same_baseline.coverage.peak_temporary_bytes, baseline.coverage.peak_temporary_bytes)
        self.assertEqual(same_bottom.transitions, bottom.transitions)

    def test_baseline_groups_release_pixel_arrays_before_measuring_next_axis(self):
        bottom, baseline = self._queries()
        sequence_baseline = replace(
            baseline, query_id="sequence-baseline", registration_index=2,
            purpose=QueryPurpose.SEQUENCE_BASELINE, boundary_axis=BoundaryAxis.X,
            boundary_axis_scale_px_per_mm=PositiveInterval.exact(10.0),
            search_intervals_px=(FiniteInterval(0.0, 50.0),) * 6,
            transition_ownership_intervals_px=(FiniteInterval(0.0, 50.0),) * 6,
        )
        sequence_window = replace(
            sequence_baseline, query_id="sequence-window", registration_index=3,
            purpose=QueryPurpose.SEQUENCE_ANCHOR_WINDOW,
        )
        original = registered_measurement._premeasure_registered_windows
        prior_buffers = []
        calls = []

        def observe(*args):
            self.assertTrue(all(reference() is None for reference in prior_buffers))
            result = original(*args)
            calls.append(args[1].purpose)
            prior_buffers.extend(weakref.ref(item.coordinates) for item in result[0][args[1].query_id])
            return result

        with patch.object(registered_measurement, "_premeasure_registered_windows", side_effect=observe):
            records = measure_registered_queries(
                PhotoBoundaryMeasurementField(self._source(1926), "horizontal"),
                (bottom, baseline, sequence_baseline, sequence_window),
            )
        self.assertEqual(calls, [QueryPurpose.CROSS_BASELINE, QueryPurpose.SEQUENCE_BASELINE])
        self.assertEqual(tuple(item.query.registration_index for item in records), (0, 1, 2, 3))
        self.assertTrue(all(reference() is None for reference in prior_buffers))

    def test_report_rejects_lost_baseline_evidence_and_forged_work(self):
        bottom, baseline = self._queries()
        top = replace(bottom, query_id="top", purpose=QueryPurpose.TOP_CORRIDOR)
        bottom = replace(bottom, registration_index=1)
        baseline = replace(baseline, registration_index=2)
        sequence = replace(
            baseline, query_id="sequence-baseline", registration_index=3,
            purpose=QueryPurpose.SEQUENCE_BASELINE, boundary_axis=BoundaryAxis.X,
            boundary_axis_scale_px_per_mm=PositiveInterval.exact(10.0),
            search_intervals_px=(FiniteInterval(0.0, 50.0),) * 6,
            transition_ownership_intervals_px=(FiniteInterval(0.0, 50.0),) * 6,
        )
        window = replace(sequence, query_id="sequence-window", registration_index=4,
                         purpose=QueryPurpose.SEQUENCE_ANCHOR_WINDOW)
        measured = measure_registered_queries(
            PhotoBoundaryMeasurementField(self._source(1926), "horizontal"),
            (top, bottom, baseline, sequence, window),
        )
        record = {
            "measurement": {"source_extent": {"width": 51, "height": 1998}},
            "development": {
                "measurement": {
                    "source_lanes": [{"domain": {
                        "lane_id": "lane:0", "source_axis_long": "x",
                        "work_box": {"left": 0, "top": 0, "right": 51, "bottom": 1998},
                    }}],
                    "queries": [_measurement_set_read_model(item) for item in measured],
                },
                "lanes": [{"lane_id": "lane:0"}],
            },
        }

        def relink_work(value):
            receipts = [item["coverage"] for item in value["development"]["measurement"]["queries"]]
            value["development"]["lanes"][0]["measurement_work"] = {
                "coverage_receipts": deepcopy(receipts),
                "measurement_query_count": len(receipts),
                "completed_query_count": sum(item["complete"] for item in receipts),
                "pixel_query_count": sum(item["pixel_query_count"] for item in receipts),
                "peak_temporary_bytes": max(item["peak_temporary_bytes"] for item in receipts),
            }

        relink_work(record)
        _validate_registered_normalization(record)
        for fault in ("missing", "evidence", "axis", "lane_extent", "pixels", "memory", "ledger"):
            invalid = deepcopy(record)
            members = invalid["development"]["measurement"]["queries"]
            raw = members[2]
            if fault == "missing":
                members.pop(2)
                for index, item in enumerate(members):
                    item["query"]["registration_index"] = index
            elif fault == "evidence":
                raw["transitions"] = deepcopy(members[1]["transitions"])
                self.assertTrue(raw["transitions"])
                raw["transition_count"] = len(raw["transitions"])
            elif fault == "axis":
                raw["query"]["boundary_axis"] = "x"
            elif fault == "lane_extent":
                invalid["development"]["measurement"]["source_lanes"][0]["domain"]["work_box"]["bottom"] -= 1
            elif fault == "pixels":
                raw["coverage"]["pixel_query_count"] = 0
            elif fault == "memory":
                # Even a self-consistent lane ledger cannot erase retained
                # arrays for the other five traces in the baseline batch.
                raw["coverage"]["peak_temporary_bytes"] = (1998 - 52) * 68
            relink_work(invalid)
            if fault == "ledger":
                invalid["development"]["lanes"][0]["measurement_work"]["pixel_query_count"] -= 1
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                _validate_registered_normalization(invalid)


if __name__ == "__main__":
    unittest.main()
