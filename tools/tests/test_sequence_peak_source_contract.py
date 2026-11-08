"""Sequence provenance and exact replay preserve the original single-peak rule."""

from dataclasses import replace
import math
import unittest

import numpy as np

from tools.tests.photo_geometry_support import make_native_test_field
from x5crop.domain import FiniteInterval, PositiveInterval
from x5crop.detection.photo_geometry.measurement_model import PhotoBoundaryMeasurementQuery
from x5crop.detection.photo_geometry.model import BoundaryAxis, QueryPurpose, PHOTO_BOUNDARY_MEASUREMENT_SPEC as SPEC
from x5crop.detection.photo_geometry.native_trace_bridge_measurement import (
    NativeTraceBridgePlan, measure_native_trace_bridges, peaks_at_row,
)
from x5crop.detection.photo_geometry.registered_measurement import measure_registered_queries
from x5crop.detection.photo_geometry.transition_peak_validation import validate_peak_source_measurements


def _case(*, transpose=False, sequence_first=False):
    gray = np.full((200, 201), 30, dtype=np.uint8)
    gray[70:130, 60:140] = 200 + 15 * (np.arange(80) % 2)
    scale = PositiveInterval.exact(20.)

    def query(name, purpose, axis, traces, interval):
        return PhotoBoundaryMeasurementQuery(name, 0, "lane:sequence-source", purpose, axis,
            traces, (interval,)*len(traces), (interval,)*len(traces), 100., scale, scale,
            SPEC.measurement_halo_px(20.), ("frozen:sequence-source",))

    top = query("top", QueryPurpose.TOP_CORRIDOR, BoundaryAxis.Y, (70, 90, 110, 130), FiniteInterval(50., 95.))
    cross = replace(top, query_id="cross-baseline", purpose=QueryPurpose.CROSS_BASELINE,
        search_intervals_px=(FiniteInterval(0., 199.),)*4,
        transition_ownership_intervals_px=(FiniteInterval(0., 199.),)*4)
    sequence = query("sequence-baseline", QueryPurpose.SEQUENCE_BASELINE, BoundaryAxis.X,
        (80, 100, 120), FiniteInterval(0., 200.))
    left = replace(sequence, query_id="left-window", purpose=QueryPurpose.SEQUENCE_ANCHOR_WINDOW,
        search_intervals_px=(FiniteInterval(40., 100.),)*3,
        transition_ownership_intervals_px=(FiniteInterval(40., 94.),)*3)
    right = replace(left, query_id="right-window", search_intervals_px=(FiniteInterval(90., 160.),)*3,
        transition_ownership_intervals_px=(FiniteInterval(95., 160.),)*3)
    queries = (sequence, left, right, top, cross) if sequence_first else (top, cross, sequence, left, right)
    if transpose:
        gray = gray.T.copy()
        queries = tuple(replace(q, boundary_axis=BoundaryAxis.Y if q.boundary_axis == BoundaryAxis.X else BoundaryAxis.X)
                        for q in queries)
    field = make_native_test_field(gray, "vertical" if transpose else "horizontal")
    return field, tuple(replace(q, registration_index=i) for i, q in enumerate(queries))


class SequencePeakSourceContractTest(unittest.TestCase):
    def test_both_axes_replay_registered_original_peaks_with_identical_sources(self):
        for transpose in (False, True):
            with self.subTest(transpose=transpose):
                field, queries = _case(transpose=transpose)
                measurements = measure_registered_queries(field, queries)
                validate_peak_source_measurements(measurements, source_id=field.source_id, source_extent=field.source_extent)
                baseline = next(m for m in measurements if m.query.purpose == QueryPurpose.SEQUENCE_BASELINE)
                windows = tuple(m for m in measurements if m.query.purpose == QueryPurpose.SEQUENCE_ANCHOR_WINDOW)
                self.assertEqual(baseline.transitions, ())
                self.assertEqual(len(baseline.peak_trace_sources), 3)
                plans = tuple(NativeTraceBridgePlan(field.source_id, field.source_extent, m.query.boundary_axis,
                    m.query.query_id, baseline.query.query_id, baseline.query.search_intervals_px[0],
                    m.query.search_intervals_px[0], tuple((t, t+1) for t in m.query.trace_positions_px),
                    20., m.query.trace_positions_px, split_gradient_reversals=False) for m in windows)
                batch = measure_native_trace_bridges(field, plans, maximum_pixel_queries=128*200*201,
                    maximum_temporary_bytes=32*1024*1024+10*200*201)
                self.assertFalse(batch.bound_exceeded)
                source_by_trace = {s.trace_coordinate_px: s for s in baseline.peak_trace_sources}
                for index, window in enumerate(windows):
                    self.assertTrue(window.transitions)
                    self.assertTrue(all(p.peak_source is not None for p in window.transitions))
                    self.assertTrue(all(not g.split_gradient_reversals for g in window.peak_source_groups))
                    for strip in (s for s in batch.strips if s.plan_index == index):
                        trace = strip.trace_start_px
                        self.assertEqual(strip.original_trace_sources, (source_by_trace[trace],))
                        replayed = peaks_at_row(strip, 0)
                        originals = tuple(p for p in window.transitions if p.trace_coordinate_px == trace)
                        self.assertEqual(len(replayed), len(originals))
                        for old, new in zip(originals, replayed, strict=True):
                            self.assertEqual((old.peak_source.source_coordinate_px, old.canonical_coordinate_px,
                                old.physical_position_interval_px, old.polarity, old.gradient_z, old.tone_z, old.texture_z),
                                (new.source_coordinate_px, new.canonical_coordinate_px,
                                 new.physical_position_interval_px, new.polarity, new.gradient_z, new.tone_z, new.texture_z))
                with self.assertRaisesRegex(ValueError, "normalization source"):
                    # Keep the forged empty receipt self-consistent so the
                    # missing baseline link, rather than visit accounting,
                    # is the guard under test.
                    missing = replace(baseline, peak_trace_sources=(), coverage=replace(baseline.coverage,
                        peak_source_value_visit_bound=baseline.coverage.peak_source_planning_value_visit_bound,
                        peak_source_retained_bytes=0))
                    validate_peak_source_measurements(tuple(missing if m is baseline else m for m in measurements),
                        source_id=field.source_id, source_extent=field.source_extent)

    def test_sequence_capture_cannot_displace_cross_source_or_native_texture_work(self):
        field, queries = _case(sequence_first=True)
        generous = measure_registered_queries(field, queries)
        counts = {q.query_id: sum(math.floor(i.maximum)-math.ceil(i.minimum)+1 for i in q.search_intervals_px)
                  for q in queries}
        cross_work = sum((5*counts[q.query_id]+32*len(q.trace_positions_px)
                          if q.purpose == QueryPurpose.CROSS_BASELINE else 256*counts[q.query_id]+32)
                         for q in queries if q.purpose in (QueryPurpose.TOP_CORRIDOR, QueryPurpose.CROSS_BASELINE))
        # Exact original pixels (including native texture), original Cross
        # provenance preflight, and two failed optional-capture preflights.
        limit = sum(m.coverage.pixel_query_count for m in generous) + cross_work + 64
        limited = measure_registered_queries(field, queries, max_pixel_query_count=limit)
        self.assertEqual(tuple(m.query.query_id for m in limited), tuple(q.query_id for q in queries))
        validate_peak_source_measurements(limited, source_id=field.source_id, source_extent=field.source_extent)
        for before, after in zip(generous, limited, strict=True):
            if before.query.purpose in (QueryPurpose.TOP_CORRIDOR, QueryPurpose.CROSS_BASELINE):
                self.assertEqual(before.transitions, after.transitions)
                self.assertEqual(before.peak_trace_sources, after.peak_trace_sources)
                self.assertEqual(before.peak_source_groups, after.peak_source_groups)
                self.assertEqual(before.coverage.native_texture_completed_count, after.coverage.native_texture_completed_count)
            elif before.query.purpose == QueryPurpose.SEQUENCE_ANCHOR_WINDOW:
                self.assertTrue(after.coverage.peak_source_bound_exceeded)
                self.assertFalse(after.coverage.peak_source_capture_attempted)
                self.assertEqual(tuple(replace(p, peak_source=None) for p in before.transitions), after.transitions)
        self.assertLessEqual(sum(m.coverage.pixel_query_count+m.coverage.peak_source_value_visit_bound for m in limited), limit)

    def test_exhausted_pool_skips_new_preflight_without_uncharged_work(self):
        field, queries = _case(sequence_first=True)
        generous = measure_registered_queries(field, queries)
        original = sum(m.coverage.pixel_query_count for m in generous) + sum(
            m.coverage.peak_source_value_visit_bound for m in generous
            if m.query.purpose in (QueryPurpose.TOP_CORRIDOR, QueryPurpose.CROSS_BASELINE))
        # Three baseline traces and two windows: 96 planning visits plus
        # 64 failed-capture preflight visits. No signal/group scans fit here.
        minimum = 32*(3+2)
        for remaining in (0, 32, 64, minimum):
            with self.subTest(remaining=remaining):
                limited = measure_registered_queries(field, queries, max_pixel_query_count=original+remaining)
                validate_peak_source_measurements(limited, source_id=field.source_id, source_extent=field.source_extent)
                self.assertLessEqual(sum(m.coverage.pixel_query_count+m.coverage.peak_source_value_visit_bound
                                         for m in limited), original+remaining)
                for before, after in zip(generous, limited, strict=True):
                    if before.query.purpose in (QueryPurpose.TOP_CORRIDOR, QueryPurpose.CROSS_BASELINE):
                        self.assertEqual(before.transitions, after.transitions)
                        self.assertEqual(before.peak_source_groups, after.peak_source_groups)
                    elif before.query.purpose == QueryPurpose.SEQUENCE_ANCHOR_WINDOW:
                        self.assertFalse(after.coverage.peak_source_capture_attempted)
                        self.assertTrue(after.coverage.peak_source_bound_exceeded)
                        self.assertEqual(after.coverage.peak_source_preflight_completed, remaining == minimum)
                        self.assertEqual(after.coverage.peak_source_value_visit_bound, 32 if remaining == minimum else 0)
                        self.assertEqual(tuple(replace(p, peak_source=None) for p in before.transitions), after.transitions)
                    elif before.query.purpose == QueryPurpose.SEQUENCE_BASELINE:
                        self.assertEqual(after.coverage.peak_source_preflight_completed, remaining == minimum)
                        self.assertEqual(after.coverage.peak_source_bound_exceeded, remaining < minimum)
                        self.assertEqual(after.coverage.peak_source_planning_value_visit_bound,
                                         32*3 if remaining == minimum else 0)

    def test_executed_source_preflight_cannot_be_relabelled_as_unattempted(self):
        field, queries = _case()
        measurements = measure_registered_queries(field, queries)
        baseline = next(m for m in measurements if m.query.purpose == QueryPurpose.SEQUENCE_BASELINE)
        self.assertGreater(baseline.coverage.peak_source_planning_value_visit_bound, 0)
        with self.assertRaisesRegex(ValueError, "whole-query state"):
            replace(baseline.coverage, peak_source_preflight_completed=False)
        erased = replace(baseline, coverage=replace(baseline.coverage, peak_source_planning_value_visit_bound=0,
            peak_source_value_visit_bound=(baseline.coverage.peak_source_value_visit_bound
                                           - baseline.coverage.peak_source_planning_value_visit_bound)))
        with self.assertRaisesRegex(ValueError, "planning work"):
            validate_peak_source_measurements(tuple(erased if m is baseline else m for m in measurements),
                source_id=field.source_id, source_extent=field.source_extent)


if __name__ == "__main__":
    unittest.main()
