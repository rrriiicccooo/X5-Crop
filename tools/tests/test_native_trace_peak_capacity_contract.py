"""Peak-capacity reservation preserves selector and completed-work semantics."""

from dataclasses import replace
import unittest

import numpy as np

from tools.tests.test_native_trace_bridge_measurement_contract import _field, _measure, _plan, _steps
from x5crop.domain import FiniteInterval
from x5crop.detection.photo_geometry import native_trace_bridge_measurement as bridge
from x5crop.detection.photo_geometry import registered_transition_measurement as transition
from x5crop.detection.photo_geometry.model import PHOTO_BOUNDARY_MEASUREMENT_SPEC as SPEC


LIMITS = {
    "maximum_pixel_queries": 1_000_000_000,
    "maximum_temporary_bytes": 128 * 1024 * 1024,
}


def _selector_signals(mask, *, tone_only=False, alternating=False):
    mask = np.asarray(mask, dtype=bool)
    width = mask.size
    coordinates = np.arange(width, dtype=np.int32)
    gradient = np.where(mask if not tone_only else np.zeros(width, dtype=bool), 8.0, 0.0).astype(np.float64)
    tone = np.where(mask if tone_only else np.zeros(width, dtype=bool), 8.0, 0.0).astype(np.float64)
    texture = np.zeros(width, dtype=np.float64)
    signed = np.where(np.arange(width) % 2 == 0, 1.0, -1.0) if alternating else np.ones(width)
    return transition.TracePeakSignals(coordinates, gradient, tone, texture, signed.astype(np.float64))


def _run_count(mask):
    return sum(bool(value) and (index == 0 or not mask[index - 1])
               for index, value in enumerate(mask))


def _payload(batch):
    """Normalize strips to the physical row payload, independent of strip blocks."""
    result = {}
    for strip in batch.strips:
        sources = {source.trace_coordinate_px: source for source in strip.original_trace_sources}
        for row, trace in enumerate(range(strip.trace_start_px, strip.trace_stop_px)):
            result[(strip.plan_index, trace)] = (
                bridge.peaks_at_row(strip, row),
                bridge._mask_row_hex(strip, strip.positive_mask_hex, trace),
                bridge._mask_row_hex(strip, strip.negative_mask_hex, trace),
                bridge._mask_row_hex(strip, strip.credible_mask_hex, trace),
                sources.get(trace),
            )
    return result


def _mixed_plans(field):
    first = _plan(field, split_gradient_reversals=False, original_trace_coordinates_px=())
    second = replace(
        _plan(
            field,
            split_gradient_reversals=True,
            original_query_id="second:original",
            baseline_query_id="second:baseline",
            coordinate_interval_px=FiniteInterval(20.0, 46.0),
            trace_intervals_px=((5, 13),),
            original_trace_coordinates_px=(),
        ),
    )
    return first, second


def _legacy_storage_reservation(plans):
    """The pre-capacity storage contract, reconstructed independently."""
    rows = sum(stop - start for plan in plans for start, stop in plan.trace_intervals_px)
    sites = sum(
        (stop - start) * (bridge._corridor_domain(plan)[1] - bridge._corridor_domain(plan)[0])
        for plan in plans if plan.record_peaks
        for start, stop in plan.trace_intervals_px
    )
    localization_sites = sum(
        (stop - start) * (bridge._corridor_domain(plan)[1] - bridge._corridor_domain(plan)[0])
        for plan in plans if plan.record_peaks and not plan.split_gradient_reversals
        for start, stop in plan.trace_intervals_px
    )
    original_count = sum(sum(1 for _ in bridge._included_original_traces(plan)) for plan in plans)
    metadata = (8192 + 4096 * len(plans) + 256 * sum(len(p.trace_intervals_px) for p in plans)
                + 128 * sum(len(p.original_trace_coordinates_px) for p in plans)
                + 4 * sum(len(p.source_id) + len(p.original_query_id) + len(p.baseline_query_id)
                          for p in plans))
    mask_hex = 6 * sum(
        (stop - start) * ((bridge._corridor_domain(plan)[1] - bridge._corridor_domain(plan)[0] + 7) // 8)
        for plan in plans for start, stop in plan.trace_intervals_px
    )
    return metadata, metadata + 1120 * rows + 128 * sites + 16 * localization_sites + mask_hex + 1024 * original_count


def _legacy_value_reservation(plans, *, hash_work=0, reuse_masks=False):
    """The pre-capacity visit contract, including its original refund rule."""
    rows = sum(stop - start for plan in plans for start, stop in plan.trace_intervals_px)

    def sites(predicate):
        return sum(
            (stop - start) * (bridge._corridor_domain(plan)[1] - bridge._corridor_domain(plan)[0])
            for plan in plans if predicate(plan)
            for start, stop in plan.trace_intervals_px
        )

    mask_work = (16 if reuse_masks else 32) * sites(lambda plan: True) + 96 * rows
    visits = (hash_work + 704 * sites(lambda plan: plan.record_peaks)
              + 64 * sites(lambda plan: plan.record_peaks and not plan.split_gradient_reversals)
              + 160 * rows + mask_work
              + 128 * (len(plans) + sum(len(p.trace_intervals_px) for p in plans)
                       + sum(len(p.original_trace_coordinates_px) for p in plans))
              + 16 * sites(lambda plan: plan.retain_responses)
              + 512 * sum(stop - start for plan in plans if plan.retain_responses
                           for start, stop in plan.trace_intervals_px))
    return visits, mask_work


def _legacy_completed_value(plans, batch):
    reserved, _ = _legacy_value_reservation(plans)
    counts = [0] * len(plans)
    for strip in batch.strips:
        counts[strip.plan_index] += strip.peak_row_offsets[-1]
    refund = 0
    for plan, count in zip(plans, counts, strict=True):
        if not plan.record_peaks:
            continue
        width = bridge._corridor_domain(plan)[1] - bridge._corridor_domain(plan)[0]
        sites = width * sum(stop - start for start, stop in plan.trace_intervals_px)
        refund += (384 + (0 if plan.split_gradient_reversals else 64)) * (sites - count)
    return reserved - refund


def _legacy_minimum_peak(plan):
    """Minimum one-row peak memory under the old full-corridor reservation."""
    _, retained = _legacy_storage_reservation((plan,))
    length, _ = bridge._axis_lengths(plan.source_extent, plan.boundary_axis)
    width = bridge._corridor_domain(plan)[1] - bridge._corridor_domain(plan)[0]
    fixed = 4096 + 8 * length + 2048 * width
    per_row = 256 * (length + 1) + 112 * width
    if plan.record_peaks and not plan.split_gradient_reversals:
        per_row += 32 * width
    return retained + fixed + per_row


def _response_cache_bound(plans):
    return (8192 + 4096 * len(plans)
            + sum(1024 * (stop - start)
                  + 32 * (stop - start) * (bridge._corridor_domain(plan)[1] - bridge._corridor_domain(plan)[0])
                  for plan in plans for start, stop in plan.trace_intervals_px)
            + 4 * sum(bridge._corridor_domain(plan)[1] - bridge._corridor_domain(plan)[0]
                      for plan in plans))


class NativeTracePeakCapacityContractTest(unittest.TestCase):
    def test_unsplit_selector_is_bounded_by_credible_runs_for_every_small_or_mask(self):
        for width in range(1, 10):
            for encoded in range(1 << width):
                mask = tuple(bool(encoded & (1 << index)) for index in range(width))
                runs = _run_count(mask)
                unsplit = transition.measured_transition_peak_geometry(
                    _selector_signals(mask), SPEC, split_gradient_reversals=False
                )
                split = transition.measured_transition_peak_geometry(
                    _selector_signals(mask), SPEC, split_gradient_reversals=True
                )
                with self.subTest(width=width, encoded=encoded):
                    self.assertLessEqual(len(unsplit), runs)
                    self.assertLessEqual(len(unsplit), (width + 1) // 2)
                    self.assertGreaterEqual(len(split), len(unsplit))

                tone_only = transition.measured_transition_peak_geometry(
                    _selector_signals(mask, tone_only=True), SPEC, split_gradient_reversals=False
                )
                with self.subTest(width=width, encoded=encoded, basis="tone-only"):
                    self.assertLessEqual(len(tone_only), runs)
                    self.assertLessEqual(len(tone_only), (width + 1) // 2)

            alternating = (False,) + (True,) * width + (False,)
            alternating_peaks = transition.measured_transition_peak_geometry(
                _selector_signals(alternating, alternating=True),
                SPEC,
                split_gradient_reversals=True,
            )
            self.assertEqual(len(alternating_peaks), width)
            self.assertEqual(
                len(transition.measured_transition_peak_geometry(
                    _selector_signals(alternating, alternating=True),
                    SPEC,
                    split_gradient_reversals=False,
                )),
                1,
            )

    def test_storage_and_value_reservations_charge_capacity_not_full_corridor(self):
        field = _field(_steps())
        for split, record in ((False, True), (True, True), (False, False)):
            plan = _plan(field, split_gradient_reversals=split, record_peaks=record)
            rows = sum(stop - start for start, stop in plan.trace_intervals_px)
            low, high = bridge._corridor_domain(plan)
            width = high - low
            capacity = rows * (0 if not record else width if split else (width + 1) // 2)
            metadata, retained = bridge._storage_reservation((plan,))
            original_count = sum(1 for _ in bridge._included_original_traces(plan))
            expected_storage = metadata + 1120 * rows + 128 * capacity
            expected_storage += (0 if split else 16 * capacity)
            expected_storage += 6 * rows * ((width + 7) // 8) + 1024 * original_count
            self.assertEqual(retained, expected_storage)

            sites = rows * width
            mask_work = 32 * sites + 96 * rows
            expected_value = 320 * (sites if record else 0) + 384 * capacity
            expected_value += (0 if split else 64 * capacity) + 160 * rows + mask_work
            expected_value += 128 * (1 + len(plan.trace_intervals_px) + len(plan.original_trace_coordinates_px))
            value, actual_mask_work = bridge._value_reservation((plan,))
            self.assertEqual(value, expected_value)
            self.assertEqual(actual_mask_work, mask_work)

    def test_capacity_formula_keeps_scan_and_masks_while_reducing_only_peak_storage(self):
        field = _field(_steps())
        plans = _mixed_plans(field)
        legacy_metadata, legacy_retained = _legacy_storage_reservation(plans)
        legacy_value, legacy_mask_work = _legacy_value_reservation(plans)
        new_metadata, new_retained = bridge._storage_reservation(plans)
        new_value, new_mask_work = bridge._value_reservation(plans)
        new_batch = _measure(field, plans)
        self.assertFalse(new_batch.bound_exceeded)
        self.assertEqual(new_metadata, legacy_metadata)
        self.assertEqual(new_mask_work, legacy_mask_work)
        self.assertEqual(new_batch.mask_site_work_bound, legacy_mask_work)
        self.assertEqual(new_batch.value_visit_bound, new_value)
        self.assertEqual(new_batch.completed_value_visit_bound, _legacy_completed_value(plans, new_batch))
        self.assertLess(new_retained, legacy_retained)
        self.assertLess(new_value, legacy_value)

        same_domain_split = replace(plans[0], split_gradient_reversals=True)
        unsplit_batch = _measure(field, (plans[0],))
        split_batch = _measure(field, (same_domain_split,))
        self.assertEqual(unsplit_batch.pixel_query_count, split_batch.pixel_query_count)
        self.assertEqual(unsplit_batch.mask_site_work_bound, split_batch.mask_site_work_bound)

        for plan in plans:
            low, high = bridge._corridor_domain(plan)
            rows = sum(stop - start for start, stop in plan.trace_intervals_px)
            expected = 0 if not plan.record_peaks else rows * (
                high - low if plan.split_gradient_reversals else (high - low + 1) // 2
            )
            self.assertEqual(bridge._peak_row_count_bound(plan) * rows, expected)

        signal_plans = tuple(
            replace(plan, record_peaks=False, retain_responses=True) for plan in plans
        )
        self.assertEqual(
            bridge.native_trace_response_cache_byte_bound(signal_plans),
            _response_cache_bound(signal_plans),
        )

    def test_tight_new_admission_passes_old_admission_fails_without_losing_peaks(self):
        field = _field(_steps())
        plan = _plan(field, split_gradient_reversals=False, original_trace_coordinates_px=())
        _, _, _, _, tight_bytes, _, _ = bridge._prepare((plan,), 0)
        prepared = bridge._prepare((plan,), tight_bytes)
        self.assertTrue(prepared[-1])
        self.assertGreater(_legacy_minimum_peak(plan), tight_bytes)

        tight = _measure(field, (plan,), maximum_temporary_bytes=tight_bytes)
        full = _measure(field, (plan,))
        self.assertFalse(tight.bound_exceeded)
        self.assertEqual(_payload(tight), _payload(full))
        self.assertGreater(sum(len(bridge.peaks_at_row(strip, row))
                               for strip in tight.strips
                               for row in range(strip.trace_stop_px - strip.trace_start_px)), 0)

    def test_signal_cache_refinement_payload_is_identical_to_direct_measurement(self):
        field = _field(_steps())
        plan = _plan(field, split_gradient_reversals=False)
        direct = _measure(field, (plan,))
        source = replace(plan, record_peaks=False, retain_responses=True)
        signal, cache = bridge.measure_native_trace_signals(field, (source,), **LIMITS)
        refined = bridge.refine_native_trace_responses(signal, cache, (plan,), **LIMITS)
        self.assertEqual(_payload(refined), _payload(direct))

    def test_row_capacity_rejects_local_overflow_even_when_total_bound_would_fit(self):
        field = _field(_steps())
        plan = _plan(
            field,
            split_gradient_reversals=False,
            trace_intervals_px=((2, 4),),
            original_trace_coordinates_px=(2,),
        )
        measured = _measure(field, (plan,))
        strip = measured.strips[0]
        capacity = bridge._peak_row_count_bound(plan)
        self.assertGreater(capacity, 1)
        records = bytearray()
        widths = bytearray()
        for coordinate in range(strip.coordinate_start_px, strip.coordinate_start_px + capacity + 1):
            records.extend(bridge._PEAK_RECORD.pack(
                coordinate, float(coordinate), coordinate - 0.5, coordinate + 0.5,
                8.0, 0.0, 0.0, 1,
            ))
            widths.extend(bridge._LOCALIZATION_WIDTH.pack(1.0))
        forged_strip = replace(
            strip,
            peak_records_hex=records.hex(),
            peak_row_offsets=(0, capacity + 1, capacity + 1),
            localization_widths_hex=widths.hex(),
        )
        with self.assertRaisesRegex(ValueError, "row peak inventory"):
            replace(
                measured,
                strips=(forged_strip,),
                completed_value_visit_bound=bridge._completed_value_visit_bound(
                    measured.plans, (forged_strip,), measured.value_visit_bound
                ),
            )

    def test_split_and_signal_only_capacity_boundaries_remain_typed(self):
        field = _field(_steps())
        split = _plan(field, split_gradient_reversals=True)
        unsplit = _plan(field, split_gradient_reversals=False)
        signal_only = _plan(field, split_gradient_reversals=False, record_peaks=False, retain_responses=False)
        self.assertEqual(bridge._peak_row_count_bound(split), bridge._corridor_domain(split)[1] - bridge._corridor_domain(split)[0])
        self.assertEqual(bridge._peak_row_count_bound(unsplit), (bridge._corridor_domain(unsplit)[1] - bridge._corridor_domain(unsplit)[0] + 1) // 2)
        self.assertEqual(bridge._peak_row_count_bound(signal_only), 0)
        signal_batch = _measure(field, (signal_only,))
        self.assertTrue(all(not any(strip.peak_row_offsets) for strip in signal_batch.strips))
        strip = signal_batch.strips[0]
        record = bridge._PEAK_RECORD.pack(
            strip.coordinate_start_px, float(strip.coordinate_start_px),
            strip.coordinate_start_px - 0.5, strip.coordinate_start_px + 0.5,
            8.0, 0.0, 0.0, 1,
        ).hex()
        forged_strip = replace(strip, peak_records_hex=record, peak_row_offsets=(0, 1, *([1] * (len(strip.peak_row_offsets) - 2))))
        with self.assertRaisesRegex(ValueError, "signal-only"):
            replace(signal_batch, strips=(forged_strip, *signal_batch.strips[1:]))

    def test_over_bound_complete_work_returns_no_prefix(self):
        field = _field(_steps())
        plan = _plan(field, split_gradient_reversals=False)
        _, _, _, _, required_peak, _, _ = bridge._prepare((plan,), 0)
        failed = _measure(field, (plan,), maximum_temporary_bytes=required_peak - 1)
        self.assertTrue(failed.bound_exceeded)
        self.assertFalse(failed.strips)
        self.assertEqual(failed.completed_value_visit_bound, 0)


if __name__ == "__main__":
    unittest.main()
