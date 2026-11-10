"""Complete peak inventories settle work without weakening whole admission."""
from dataclasses import replace
import unittest
from unittest.mock import patch

from tools.tests.test_native_trace_bridge_measurement_contract import _field,_steps,_plan,_measure
from tools.tests.test_sequence_connections_contract import _case,_prepare
from x5crop.detection.photo_geometry import native_trace_bridge_measurement as owner
from x5crop.detection.photo_geometry import sequence_connections as sequence


class NativeTraceCompletionWorkContractTest(unittest.TestCase):
    def test_admission_stays_worst_case_while_every_complete_record_is_charged(self):
        for split in (False,True):
            field=_field(_steps());plan=_plan(field,split_gradient_reversals=split)
            batch=_measure(field,(plan,))
            low,high=owner._corridor_domain(plan)
            sites=sum(b-a for a,b in plan.trace_intervals_px)*(high-low)
            peaks=sum(len(s.peak_records_hex)//128 for s in batch.strips)
            self.assertEqual(peaks,sum(s.peak_row_offsets[-1] for s in batch.strips))
            self.assertEqual(batch.value_visit_bound,batch.required_value_visit_bound)
            self.assertEqual(batch.completed_value_visit_bound,
                batch.value_visit_bound-384*(sites-peaks)-(0 if split else 64*(sites-peaks)))
            self.assertLess(batch.completed_value_visit_bound,batch.value_visit_bound)
            self.assertGreaterEqual(batch.completed_value_visit_bound,batch.mask_site_work_bound)
            owner.validate_native_trace_bridge_batch(batch)
            optimistic=batch.pixel_query_count+batch.completed_value_visit_bound+batch.preflight_value_visit_bound
            with patch.object(owner,'measure_trace_rows',side_effect=AssertionError('cannot admit a favorable sparse image')):
                failed=_measure(field,(plan,),maximum_pixel_queries=optimistic)
            self.assertTrue(failed.bound_exceeded)
            self.assertEqual(failed.completed_value_visit_bound,0)
            self.assertFalse(failed.strips)

    def test_signal_and_failed_prefixes_cannot_claim_a_peak_credit(self):
        field=_field(_steps());plan=_plan(field,record_peaks=False)
        signal=_measure(field,(plan,))
        self.assertEqual(signal.completed_value_visit_bound,signal.value_visit_bound)
        failed=_measure(field,(plan,),maximum_temporary_bytes=0)
        with self.assertRaises(ValueError):replace(failed,completed_value_visit_bound=1)
        measured=_measure(field,(_plan(field),))
        for amount in (measured.completed_value_visit_bound-1,measured.completed_value_visit_bound+1):
            with self.subTest(amount=amount),self.assertRaises(ValueError):
                replace(measured,completed_value_visit_bound=amount)
        with self.assertRaises(ValueError):
            replace(measured,strips=measured.strips[:-1])

    def test_physical_failure_still_charges_the_complete_peak_table_and_proof(self):
        case=_case()
        positive=_prepare(case)
        def unavailable(parents,*args):
            return tuple(sequence.SequenceConnectionAssessment(p.observation_id,'dense_peak_unavailable',None) for p in parents)
        with patch.object(sequence,'assess_sequence_connections',side_effect=unavailable):
            failed=_prepare(case)
        self.assertEqual(failed.batch,positive.batch)
        self.assertEqual(failed.work,positive.work)
        self.assertTrue(all(a.constraint is None for a in failed.assessments))
        self.assertGreater(failed.batch.completed_value_visit_bound,0)

    def test_aligned_row_copy_is_exact_and_keeps_unaligned_and_trace_guards(self):
        field=_field(_steps())
        for interval in (owner.FiniteInterval(16.,79.),owner.FiniteInterval(15.2,78.8)):
            batch=_measure(field,(_plan(field,coordinate_interval_px=interval),))
            for strip in batch.strips:
                for name,decoder in (('positive_mask_hex',lambda s:owner.decode_mask(s,1)),
                                     ('negative_mask_hex',lambda s:owner.decode_mask(s,-1)),
                                     ('credible_mask_hex',owner.decode_credible_mask)):
                    decoded=decoder(strip)
                    for row,trace in enumerate(range(strip.trace_start_px,strip.trace_stop_px)):
                        expected=owner.np.packbits(decoded[row],bitorder='little').tobytes().hex()
                        self.assertEqual(owner._mask_row_hex(strip,getattr(strip,name),trace),expected)
                with self.assertRaises(ValueError):
                    owner._mask_row_hex(strip,strip.positive_mask_hex,strip.trace_stop_px)
