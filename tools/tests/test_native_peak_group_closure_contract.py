"""Peak-group closure is independent evidence for native continuity.

These are synthetic DTO/replay contracts.  They do not assert that any real
TIFF qualifies; they assert that a dense bridge cannot turn a clipped OR
credible peak group into continuity evidence merely because its AND sign mask
is connected.
"""

from copy import deepcopy
from dataclasses import replace
import unittest

import numpy as np

from tools.tests.test_native_trace_bridge_measurement_contract import (
    _field,
    _measure,
    _plan,
    _steps,
)
from tools.tests.test_native_trace_continuity_contract import _case, _cross, _prepare
from x5crop.domain import FiniteInterval, WorkspaceExtent
from x5crop.detection.photo_geometry import native_trace_bridge_measurement as bridge
from x5crop.detection.photo_geometry.model import (
    BoundaryAxis,
    PHOTO_BOUNDARY_MEASUREMENT_SPEC as SPEC,
)
from x5crop.detection.photo_geometry.native_trace_continuity import (
    NativeTraceContinuityEvidence,
    NativeTraceContinuityFailure,
    apply_native_continuity,
    assess_native_continuity,
    prepare_native_continuity,
)
from x5crop.detection.photo_geometry.template_cross_model import CrossFitStatus
from x5crop.detection.photo_geometry.registered_measurement import (
    _slice_trace_measurement,
    measure_trace,
)
from x5crop.detection.photo_geometry.registered_transition_measurement import (
    TraceRowsMeasurement,
    measured_transition_peaks,
    transition_peak_support,
)
from x5crop.report.read_models import typed_read_model


def _pack_mask(mask: np.ndarray) -> str:
    return np.packbits(np.asarray(mask, dtype=np.uint8), bitorder="little").tobytes().hex()


def _measured_one_row_peak_strip() -> tuple[TraceRowsMeasurement, bridge.NativeTraceBridgePlan,
                                             bridge.NativeTraceBridgeStrip]:
    """Run the reported DTO counterexample through the real peak selector/strip owner."""

    coordinates = np.arange(21, 101, dtype=np.int32)
    shape = (1, coordinates.size)
    zeros = np.zeros(shape, dtype=np.float64)
    gradient_z = zeros.copy()
    gradient_z[0, 60 - 21] = 10.0
    tone_z = zeros.copy()
    tone_z[0, : 65 - 21 + 1] = 10.0
    signed_gradient = zeros.copy()
    signed_gradient[0, 60 - 21] = -10.0
    measured = TraceRowsMeasurement(
        coordinates,
        gradient_z,
        tone_z,
        zeros.copy(),
        signed_gradient,
        zeros.copy(),
        zeros.copy(),
        zeros.copy(),
        zeros.copy(),
        0,
    )
    plan = bridge.NativeTraceBridgePlan(
        source_id="synthetic-peak-group",
        source_extent=WorkspaceExtent(200, 1),
        boundary_axis=BoundaryAxis.X,
        original_query_id="synthetic:original",
        baseline_query_id="synthetic:baseline",
        normalization_interval_px=FiniteInterval(21.0, 100.0),
        coordinate_interval_px=FiniteInterval(21.0, 100.0),
        trace_intervals_px=((0, 1),),
        coordinate_scale_px_per_mm=10.0,
        original_trace_coordinates_px=(0,),
    )
    source = bridge._source(bridge._row(measured, 0), plan, 0)
    strip = bridge._strip(measured, 0, 0, 1, 0, plan, {0: source})
    return measured, plan, strip


def _dense_batch_with_or_group(evidence, *, left: int, right: int):
    """Replace only dense signal DTOs, retaining the registered plan/source ledger."""

    batch = evidence.batch
    strip = batch.strips[0]
    rows = strip.trace_stop_px - strip.trace_start_px
    columns = strip.coordinate_stop_px - strip.coordinate_start_px
    selected = 80 - strip.coordinate_start_px
    credible = np.zeros((rows, columns), dtype=np.uint8)
    credible[:, left - strip.coordinate_start_px : right - strip.coordinate_start_px + 1] = 1
    positive = np.zeros_like(credible)
    negative = np.zeros_like(credible)
    negative[:, selected] = 1
    record = bridge._PEAK_RECORD.pack(80, 80.0, 75.5, 83.5, 4.0, 3.0, 0.0, -1).hex()
    records = record * rows
    offsets = tuple(range(rows + 1))
    forged = replace(
        strip,
        positive_mask_hex=_pack_mask(positive),
        negative_mask_hex=_pack_mask(negative),
        credible_mask_hex=_pack_mask(credible),
        peak_records_hex=records,
        peak_row_offsets=offsets,
    )
    return replace(batch, strips=(forged,))


def _record(case, evidence):
    field, registration, measurements = case
    binding = apply_native_continuity(registration, evidence).bottom_bindings[0]
    return {
        "measurement": {
            "source_id": field.source_id,
            "source_extent": typed_read_model(field.source_extent),
        },
        "development": None,
        "photo_geometry": {
            "lanes": [{
                "lane_id": measurements[0].query.lane_id,
                "native_continuity": typed_read_model(evidence),
                "native_continuity_work": typed_read_model(evidence.work),
                "base_cross_registration": typed_read_model(registration),
                "direct_binding": typed_read_model(binding),
            }],
        },
    }


class NativePeakGroupClosureContractTest(unittest.TestCase):
    def test_peak_selector_and_strip_owner_retain_the_or_group_counterexample(self):
        measured, plan, strip = _measured_one_row_peak_strip()
        view = _slice_trace_measurement(bridge._row(measured, 0), plan.coordinate_interval_px)
        selected = measured_transition_peaks(view, SPEC, split_gradient_reversals=True)
        self.assertEqual(len(selected), 1)
        self.assertEqual(int(view.coordinates[selected[0].coordinate_index]), 60)
        interval = selected[0].physical_position_interval
        self.assertEqual((interval.minimum, interval.maximum), (20.5, 65.5))
        _gradient, _secondary, group_support = transition_peak_support(view, SPEC)
        group_coordinates = view.coordinates[np.flatnonzero(group_support)]
        self.assertEqual((int(group_coordinates[0]), int(group_coordinates[-1])), (21, 65))

        peaks = bridge.peaks_at_row(strip, 0)
        self.assertEqual(tuple(peak.source_coordinate_px for peak in peaks), (60,))
        self.assertEqual(
            (peaks[0].physical_position_interval_px.minimum,
             peaks[0].physical_position_interval_px.maximum),
            (20.5, 65.5),
        )
        credible = bridge.decode_credible_mask(strip)[0]
        negative = bridge.decode_mask(strip, -1)[0]
        self.assertEqual((int(np.flatnonzero(credible)[0]), int(np.flatnonzero(credible)[-1])), (0, 44))
        self.assertEqual(tuple(np.flatnonzero(negative)), (39,))
        self.assertFalse(bool(negative[0] or negative[-1]))

    def test_measured_or_mask_and_resource_receipt_keep_original_numeric_semantics(self):
        field = _field(_steps())
        batch = _measure(field, (_plan(field),))
        self.assertFalse(batch.bound_exceeded)
        sites = sum(
            (strip.trace_stop_px - strip.trace_start_px)
            * (strip.coordinate_stop_px - strip.coordinate_start_px)
            for strip in batch.strips
        )
        rows = sum(strip.trace_stop_px - strip.trace_start_px for strip in batch.strips)
        self.assertGreater(batch.mask_site_work_bound, 16 * sites + 64 * rows)
        self.assertEqual(batch.pixel_query_count, batch.required_pixel_query_count)
        for strip in batch.strips:
            plan = batch.plans[strip.plan_index]
            for row in range(strip.trace_stop_px - strip.trace_start_px):
                values = field.source_gray[row + strip.trace_start_px]
                scalar = measure_trace(
                    values,
                    plan.normalization_interval_px,
                    plan.coordinate_scale_px_per_mm,
                    SPEC,
                    peak_source_context=(field.source_id, field.source_extent, plan.boundary_axis,
                                         row + strip.trace_start_px),
                )
                view = _slice_trace_measurement(scalar, plan.coordinate_interval_px)
                expected = (
                    (view.gradient_z >= SPEC.gradient_z_minimum)
                    | (np.maximum(view.tone_z, view.texture_z) >= SPEC.tone_or_texture_z_minimum)
                )
                np.testing.assert_array_equal(
                    bridge.decode_credible_mask(strip)[row].astype(bool), expected
                )
                strong = (
                    (view.gradient_z >= SPEC.gradient_z_minimum)
                    & (np.maximum(view.tone_z, view.texture_z) >= SPEC.tone_or_texture_z_minimum)
                )
                np.testing.assert_array_equal(
                    bridge.decode_mask(strip, 1)[row], strong & (view.signed_gradient > 0.0)
                )
                np.testing.assert_array_equal(
                    bridge.decode_mask(strip, -1)[row], strong & (view.signed_gradient < 0.0)
                )
                expected_peaks = tuple(
                    bridge.NativeTraceBridgePeak(
                        int(view.coordinates[p.coordinate_index]),
                        p.canonical_coordinate,
                        p.physical_position_interval,
                        p.polarity,
                        p.gradient_z,
                        p.tone_z,
                        p.texture_z,
                    )
                    for p in measured_transition_peaks(view, SPEC, split_gradient_reversals=True)
                )
                self.assertEqual(bridge.peaks_at_row(strip, row), expected_peaks)

    def test_dense_left_truncated_or_group_is_unavailable_even_with_interior_and_component(self):
        case = _case()
        evidence = _prepare(case)
        batch = _dense_batch_with_or_group(evidence, left=65, right=94)
        strip = batch.strips[0]
        self.assertFalse(np.any(bridge.decode_mask(strip, -1)[:, (0, -1)]))
        self.assertTrue(np.any(bridge.decode_credible_mask(strip)[:, 0]))
        actual = assess_native_continuity(evidence.requests, evidence.measurements, batch)[0]
        self.assertEqual(actual.failure_kind, NativeTraceContinuityFailure.DENSE_GROUP_UNAVAILABLE)
        self.assertIsNone(actual.constraint)
        self.assertEqual(tuple(p.source_coordinate_px for p in bridge.peaks_at_row(strip, 0)), (80,))
        forged_evidence = replace(evidence, batch=batch, assessments=(actual,))
        self.assertEqual(
            _cross(apply_native_continuity(case[1], forged_evidence)).status,
            CrossFitStatus.UNRESOLVED,
        )

    def test_dense_right_truncated_or_group_is_unavailable_even_with_interior_and_component(self):
        case = _case()
        evidence = _prepare(case)
        batch = _dense_batch_with_or_group(evidence, left=66, right=95)
        strip = batch.strips[0]
        self.assertFalse(np.any(bridge.decode_mask(strip, -1)[:, (0, -1)]))
        self.assertTrue(np.any(bridge.decode_credible_mask(strip)[:, -1]))
        actual = assess_native_continuity(evidence.requests, evidence.measurements, batch)[0]
        self.assertEqual(actual.failure_kind, NativeTraceContinuityFailure.DENSE_GROUP_UNAVAILABLE)
        self.assertIsNone(actual.constraint)

    def test_dense_or_group_with_both_original_query_flanks_still_qualifies(self):
        case = _case()
        evidence = _prepare(case)
        batch = _dense_batch_with_or_group(evidence, left=66, right=94)
        actual = assess_native_continuity(evidence.requests, evidence.measurements, batch)[0]
        self.assertIsNone(actual.failure_kind)
        self.assertIsNotNone(actual.constraint)
        forged_evidence = replace(evidence, batch=batch, assessments=(actual,))
        self.assertEqual(
            _cross(apply_native_continuity(case[1], forged_evidence)).status,
            CrossFitStatus.RESOLVED,
        )

    def test_dense_group_with_flanks_but_peak_interval_outside_or_group_is_unavailable(self):
        case = _case()
        evidence = _prepare(case)
        # The OR group has an observed zero flank on each side (80..90 inside
        # the 65..95 corridor), but the selected peak's physical interval
        # starts at 75.5 and therefore is not fully contained by that group.
        batch = _dense_batch_with_or_group(evidence, left=80, right=90)
        actual = assess_native_continuity(evidence.requests, evidence.measurements, batch)[0]
        self.assertEqual(actual.failure_kind, NativeTraceContinuityFailure.DENSE_GROUP_UNAVAILABLE)
        self.assertIsNone(actual.constraint)

    def test_required_original_peak_group_incomplete_cannot_be_replaced_by_dense_evidence(self):
        case = _case()
        field, registration, measurements = case
        bottom = measurements[-1]
        groups = list(bottom.peak_source_groups)
        target = next(i for i, group in enumerate(groups) if group.source.trace_coordinate_px == 0)
        group = groups[target]
        groups[target] = replace(
            group,
            measurement_domain_px=(group.credible_group_domain_px[0], group.measurement_domain_px[1]),
        )
        incomplete = (*measurements[:-1], replace(bottom, peak_source_groups=tuple(groups)))
        evidence = prepare_native_continuity(
            field,
            registration,
            incomplete,
            maximum_value_visits=128 * field.source_gray.size,
            maximum_temporary_bytes=10 * field.source_gray.size + 32 * 1024 * 1024,
        )
        self.assertIsNotNone(evidence)
        self.assertTrue(evidence.requests)
        failures = {
            evidence.requests[0].preliminary_failure,
            evidence.assessments[0].failure_kind,
        }
        self.assertIn(NativeTraceContinuityFailure.ORIGINAL_GROUP_UNAVAILABLE, failures)
        self.assertIsNone(evidence.assessments[0].constraint)

    def test_typed_and_ordinary_replay_reject_credible_mask_mutation_or_omission(self):
        from tools.regression.native_continuity_validation import validate_native_continuity
        from tools.regression.report_validation import _read_common_proof

        case = _case()
        evidence = _prepare(case)
        record = _record(case, evidence)
        validate_native_continuity(record, read_proof=_read_common_proof)
        lane = record["photo_geometry"]["lanes"][0]
        strips = lane["native_continuity"]["batch"]["strips"]
        changed = deepcopy(record)
        changed_mask = changed["photo_geometry"]["lanes"][0]["native_continuity"]["batch"]["strips"][0]
        changed_mask["credible_mask_hex"] = "0" * len(changed_mask["credible_mask_hex"])
        with self.assertRaises(ValueError):
            validate_native_continuity(changed, read_proof=_read_common_proof)
        omitted = deepcopy(record)
        del omitted["photo_geometry"]["lanes"][0]["native_continuity"]["batch"]["strips"][0]["credible_mask_hex"]
        with self.assertRaises(ValueError):
            _read_common_proof(
                omitted["photo_geometry"]["lanes"][0]["native_continuity"],
                NativeTraceContinuityEvidence,
            )
        with self.assertRaises(ValueError):
            validate_native_continuity(omitted, read_proof=_read_common_proof)
        self.assertIn("credible_mask_hex", strips[0])

        extended = deepcopy(record)
        extended_strip = extended["photo_geometry"]["lanes"][0]["native_continuity"]["batch"]["strips"][0]
        original_strip = evidence.batch.strips[0]
        original_credible = bridge.decode_credible_mask(original_strip)
        widened_credible = original_credible.copy()
        for row in widened_credible:
            sites = np.flatnonzero(row)
            self.assertGreater(sites.size, 0)
            row[: int(sites[-1]) + 1] = 1
        widened_hex = _pack_mask(widened_credible)
        extended_strip["credible_mask_hex"] = widened_hex
        self.assertEqual(extended_strip["positive_mask_hex"],
                         lane["native_continuity"]["batch"]["strips"][0]["positive_mask_hex"])
        self.assertEqual(extended_strip["negative_mask_hex"],
                         lane["native_continuity"]["batch"]["strips"][0]["negative_mask_hex"])
        self.assertEqual(extended_strip["peak_records_hex"],
                         lane["native_continuity"]["batch"]["strips"][0]["peak_records_hex"])
        self.assertEqual(
            extended["photo_geometry"]["lanes"][0]["native_continuity"]["work"],
            lane["native_continuity"]["work"],
        )
        self.assertEqual(
            extended["photo_geometry"]["lanes"][0]["direct_binding"]["native_continuity_constraint"],
            lane["direct_binding"]["native_continuity_constraint"],
        )
        widened_strip = replace(original_strip, credible_mask_hex=widened_hex)
        widened_or = bridge.decode_credible_mask(widened_strip)
        and_mask = bridge.decode_mask(widened_strip, 1) | bridge.decode_mask(widened_strip, -1)
        self.assertTrue(np.all(and_mask <= widened_or))
        self.assertTrue(np.any(widened_or[:, 0]))
        widened_evidence = _read_common_proof(
            extended["photo_geometry"]["lanes"][0]["native_continuity"],
            NativeTraceContinuityEvidence,
        )
        widened_assessment = assess_native_continuity(
            widened_evidence.requests,
            widened_evidence.measurements,
            widened_evidence.batch,
        )[0]
        self.assertEqual(
            widened_assessment.failure_kind,
            NativeTraceContinuityFailure.DENSE_GROUP_UNAVAILABLE,
        )
        with self.assertRaises(ValueError):
            validate_native_continuity(extended, read_proof=_read_common_proof)

    def test_ordinary_replay_rejects_deleting_registered_original_peak_group(self):
        from tools.regression.native_continuity_validation import validate_native_continuity
        from tools.regression.report_validation import _read_common_proof

        case = _case()
        evidence = _prepare(case)
        record = _record(case, evidence)
        validate_native_continuity(record, read_proof=_read_common_proof)
        forged = deepcopy(record)
        measurements = forged["photo_geometry"]["lanes"][0]["native_continuity"]["measurements"]
        bottom = next(item for item in measurements if item["query"]["purpose"] == "bottom_corridor")
        bottom["peak_source_groups"] = [
            group for group in bottom["peak_source_groups"]
            if group["source"]["trace_coordinate_px"] != 0
        ]
        with self.assertRaises(ValueError):
            validate_native_continuity(forged, read_proof=_read_common_proof)


if __name__ == "__main__":
    unittest.main()
