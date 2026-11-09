"""Same-call response consumption preserves every original measurement."""
from dataclasses import replace
import json
import unittest
import weakref
from unittest.mock import patch

import numpy as np

from tools.tests.test_native_trace_bridge_measurement_contract import _field,_steps,_plan,_measure
from tools.tests.test_sequence_connections_contract import _case,_prepare,_validate
from x5crop.detection.photo_geometry import native_trace_bridge_measurement as owner
from x5crop.detection.photo_geometry.model import BoundaryAxis
from x5crop.report.read_models import typed_read_model
from tools.regression.report_validation import _read_common_proof


LIMITS = dict(maximum_pixel_queries=1_000_000_000,maximum_temporary_bytes=128*1024*1024)


def signals(field,plan,**limits):
    return owner.measure_native_trace_signals(field,(replace(plan,record_peaks=False,retain_responses=True),),
                                             **(LIMITS|limits))


def payload(batch):
    result = {}
    for strip in batch.strips:
        masks = (owner.decode_mask(strip,1),owner.decode_mask(strip,-1),owner.decode_credible_mask(strip))
        sources = {s.trace_coordinate_px:s for s in strip.original_trace_sources}
        for row,trace in enumerate(range(strip.trace_start_px,strip.trace_stop_px)):
            result[(strip.plan_index,trace)] = (owner.peaks_at_row(strip,row),
                tuple(m[row].tobytes() for m in masks),sources.get(trace))
    return result


class NativeTraceResponseReuseContractTest(unittest.TestCase):
    def test_reuse_matches_independent_measurement_on_both_axes_without_source_reads(self):
        for transpose in (False,True):
            field = _field(_steps().T.copy() if transpose else _steps())
            plan = _plan(field,boundary_axis=BoundaryAxis.Y if transpose else BoundaryAxis.X,
                         normalization_interval_px=owner.FiniteInterval(0.,96.),split_gradient_reversals=False)
            original = _measure(field,(plan,))
            signal,cache = signals(field,plan)
            for matrix,_ in cache.rows.values():
                self.assertIsNone(matrix.base)
                self.assertFalse(matrix.flags.writeable)
                self.assertEqual(matrix.dtype,np.float64)
                self.assertEqual(matrix.nbytes,64*matrix.shape[1])
            with (patch.object(owner,'measure_trace_rows',side_effect=AssertionError('duplicate normalization')),
                  patch.object(owner,'_source',side_effect=AssertionError('duplicate full-domain hash')),
                  patch.object(owner,'transition_peak_support',side_effect=AssertionError('duplicate mask construction'))):
                reused = owner.refine_native_trace_responses(signal,cache,(plan,),**LIMITS)
            self.assertEqual(payload(reused),payload(original))
            self.assertEqual(reused.pixel_query_count,0)
            self.assertTrue(cache.closed)
            self.assertFalse(cache.rows)
            owner.validate_native_trace_bridge_batch(signal)
            owner.validate_native_trace_bridge_batch(reused)
            owner.validate_native_trace_response_reuse(reused,signal)

    def test_wrong_context_missing_trace_and_duplicate_obligation_are_rejected(self):
        field = _field(_steps());plan = _plan(field,split_gradient_reversals=False)
        signal,cache = signals(field,plan)
        for changes in ({'source_id':'another-source'},{'baseline_query_id':'another-baseline'},
                        {'original_query_id':'another-query'},{'coordinate_scale_px_per_mm':10.1},
                        {'coordinate_interval_px':owner.FiniteInterval(16.,78.)}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                owner.refine_native_trace_responses(signal,cache,(replace(plan,**changes),),**LIMITS)
        with self.assertRaises(ValueError):
            owner.refine_native_trace_responses(signal,cache,(plan,plan),**LIMITS)
        key = next(iter(cache.rows));row = cache.rows.pop(key)
        with self.assertRaisesRegex(ValueError,'lost or duplicated'):
            owner.refine_native_trace_responses(signal,cache,(plan,),**LIMITS)
        cache.rows[key] = row
        with self.assertRaisesRegex(ValueError,'same-call'):
            owner.refine_native_trace_responses(replace(signal),cache,(plan,),**LIMITS)
        cache.release()

    def test_entire_cache_is_admitted_before_pixels_and_failed_refinement_keeps_no_prefix(self):
        field = _field(_steps());plan = _plan(field,split_gradient_reversals=False)
        source = replace(plan,record_peaks=False,retain_responses=True)
        bound = owner.native_trace_response_cache_byte_bound((source,))
        with patch.object(owner,'measure_trace_rows',side_effect=AssertionError('unadmitted pixels')):
            failed,cache = signals(field,plan,maximum_temporary_bytes=bound-1)
        self.assertTrue(failed.bound_exceeded)
        self.assertIsNone(cache)
        self.assertFalse(failed.strips)
        self.assertGreater(failed.preflight_value_visit_bound,0)
        signal,cache = signals(field,plan)
        count = len(cache.rows)
        failed = owner.refine_native_trace_responses(signal,cache,(plan,),**(LIMITS|{'maximum_pixel_queries':0}))
        self.assertTrue(failed.bound_exceeded)
        self.assertFalse(failed.strips)
        self.assertEqual(len(cache.rows),count)
        self.assertFalse(cache.closed)
        cache.release()

    def test_partial_survivor_uses_its_complete_original_corridor_and_trace_span(self):
        field = _field(_steps());plan = _plan(field,split_gradient_reversals=False)
        signal,cache = signals(field,plan)
        survivor = replace(plan,trace_intervals_px=((5,8),))
        reused = owner.refine_native_trace_responses(signal,cache,(survivor,),**LIMITS)
        original = _measure(field,(survivor,))
        self.assertEqual(payload(reused),payload(original))
        owner.validate_native_trace_response_reuse(reused,signal)

    def test_partial_mask_decoding_preserves_unaligned_rows_and_full_hex_validation(self):
        field = _field(_steps());plan = _plan(field,split_gradient_reversals=False)
        signal,cache = signals(field,plan)
        strip = signal.strips[0]
        self.assertNotEqual((strip.coordinate_stop_px-strip.coordinate_start_px)%8,0)
        for polarity in (-1,1):
            full = owner.decode_mask(strip,polarity)
            for low in range(strip.trace_start_px,strip.trace_stop_px):
                for high in range(low+1,strip.trace_stop_px+1):
                    np.testing.assert_array_equal(owner.decode_mask(strip,polarity,trace_interval_px=(low,high)),
                        full[low-strip.trace_start_px:high-strip.trace_start_px])
        with self.assertRaisesRegex(ValueError,'row range'):
            owner.decode_mask(strip,1,trace_interval_px=(strip.trace_start_px-1,strip.trace_stop_px))
        # Frozen report objects normally reject malformed input at construction;
        # the decode boundary also checks bytes outside the selected row.
        object.__setattr__(strip,'positive_mask_hex',strip.positive_mask_hex[:-1]+'z')
        with self.assertRaisesRegex(ValueError,'hexadecimal'):
            owner.decode_mask(strip,1,trace_interval_px=(strip.trace_start_px,strip.trace_start_px+1))
        cache.release()

    def test_report_cannot_forge_reuse_context_or_change_measured_masks(self):
        field = _field(_steps());plan = _plan(field,split_gradient_reversals=False)
        signal,cache = signals(field,plan)
        reused = owner.refine_native_trace_responses(signal,cache,(plan,),**LIMITS)
        forged = replace(reused,plans=(replace(plan,baseline_query_id='forged'),),
                         response_source_plans=(replace(signal.plans[0],baseline_query_id='forged'),))
        with self.assertRaisesRegex(ValueError,'complete measured signal source'):
            owner.validate_native_trace_response_reuse(forged,signal)
        strip = reused.strips[0]
        width = strip.coordinate_stop_px-strip.coordinate_start_px
        encoded = np.packbits(np.ones(width,dtype=np.uint8),bitorder='little').tobytes().hex()
        changed = replace(reused,strips=(replace(strip,credible_mask_hex=encoded),*reused.strips[1:]))
        with self.assertRaisesRegex(ValueError,'signal masks'):
            owner.validate_native_trace_response_reuse(changed,signal)

    def test_cache_leaves_no_arrays_after_guard_or_refinement_and_report_round_trips(self):
        from x5crop.detection.photo_geometry import sequence_connections as sequence
        original = sequence.measure_native_trace_signals
        for broken in (False,True):
            references=[];caches=[]
            def capture(*args,**kwargs):
                signal,cache = original(*args,**kwargs)
                caches.append(cache)
                references.extend(weakref.ref(matrix) for matrix,_ in cache.rows.values())
                return signal,cache
            case = _case(broken=broken)
            with patch.object(sequence,'measure_native_trace_signals',side_effect=capture):
                evidence = _prepare(case)
            self.assertTrue(all(c.closed for c in caches))
            self.assertTrue(all(r() is None for r in references))
            raw = json.loads(json.dumps(typed_read_model(evidence)))
            restored = _read_common_proof(raw,type(evidence))
            self.assertEqual(restored,evidence)
            _validate(case,restored)
