"""Native responses stay at the registered original pixel without identity authority."""

from copy import deepcopy
import unittest
from unittest.mock import patch

import numpy as np

from tools.regression.gold_native_connections import (
    NATIVE_CONNECTION_CONTRACT, _original_peak_anchor_reservation,
    native_local_connection_diagnostic,
)


SCALES = {name: {"minimum": 20., "maximum": 20.}
          for name in ("width_axis_px_per_mm", "height_axis_px_per_mm")}
OWNER = "tools.regression.gold_native_connections"


def _inputs(*, pixel=60, axis="long", layout="horizontal", polarity=-1):
    rgb = np.full((121, 181, 3), 60000, dtype=np.uint16)
    rgb[:, 60:] = 12000
    if axis == "short":
        rgb = rgb.transpose(1, 0, 2)
    if layout == "vertical":
        rgb = rgb.transpose(1, 0, 2)
    raw_axis = "x" if (axis == "long") == (layout == "horizontal") else "y"
    line = {"observation_id": "native-line", "trace_coordinates_px": [40, 80],
            "transition_ids": ["raw:0", "raw:1"],
            "physical_line_region": {"reference_trace_px": 60., "vertices": [[60., 0.], [90., 0.]]}}
    interval = {"minimum": 0., "maximum": 180.}
    measurement = {"query": {"query_id": "registered:line", "boundary_axis": raw_axis,
        "trace_positions_px": [40, 80], "search_intervals_px": [dict(interval), dict(interval)],
        "transition_ownership_intervals_px": [dict(interval), dict(interval)]},
        "coverage": {"complete": True}, "transitions": []}
    for ordinal, trace in enumerate((40, 80)):
        measurement["transitions"].append({"transition_id": f"raw:{ordinal}",
            "query_id": "registered:line", "trace_ordinal": ordinal,
            "trace_coordinate_px": trace, "texture_sample_coordinate_px": pixel,
            "polarity": polarity,
            "peak_source": {"group_id": f"registered:group:{ordinal}",
                "candidate_ordinal": 2, "source_coordinate_px": pixel, "polarity": polarity}})
    return rgb, ([line] if axis == "long" else []), ([line] if axis == "short" else []), [measurement]


def _measure(inputs, *, layout="horizontal", **kwargs):
    rgb, edges, sides, measurements = inputs
    return native_local_connection_diagnostic(rgb, layout=layout, sequence_edges=edges,
        side_lines=sides, scales=SCALES, original_measurements=measurements, **kwargs)


class NativeEndpointAnchorContractTest(unittest.TestCase):
    def assert_authority_unavailable(self, result):
        for authority in ("same_photo_pair_authority", "terminal_authority", "ordinal_authority",
                          "boundary_identity_authority"):
            self.assertEqual(result[authority], "unavailable")
        self.assertFalse(result["candidate_or_reference_consumed"])
        self.assertEqual(result["original_peak_anchor_context"],
                         "native16_and_registered_gray8_contexts_differ")

    def test_nearby_strong_line_does_not_reselect_weak_original_pixel(self):
        result = _measure(_inputs(pixel=80))
        self.assertEqual(result["contract"], NATIVE_CONNECTION_CONTRACT)
        self.assertEqual(result["contract"], "x5crop_native_endpoint_pixels_v2")
        for query in result["queries"]:
            self.assertGreater(sum(item["anchor_component_count"] for item in query["step_components"]), 0)
            self.assertEqual(query["original_peak_anchor_completeness"], "complete")
            self.assertEqual(query["original_peak_anchor_response_state"], "unavailable")
            response, = query["original_peak_anchor_responses"]
            self.assertEqual(response["source_coordinate_px"], 80)
            self.assertEqual(response["native_component_label"], 0)
            self.assertFalse(response["native_component_reaches_query_edge"])
            self.assertEqual(response["failure_kind"], "native_signal_unavailable")
        self.assert_authority_unavailable(result)

    def test_actual_pixel_component_has_signal_without_boundary_or_photo_authority(self):
        inputs = _inputs()
        original = deepcopy((inputs[1], inputs[2], inputs[3]))
        result = _measure(inputs)
        for index, query in enumerate(result["queries"]):
            self.assertEqual(query["original_peak_anchor_response_state"], "supported")
            response, = query["original_peak_anchor_responses"]
            self.assertGreater(response["native_component_label"], 0)
            self.assertTrue(response["native_component_reaches_query_edge"])
            self.assertEqual(response["original_polarity"], -1)
            self.assertEqual(response["query_id"], "registered:line")
            self.assertEqual(response["transition_id"], f"raw:{index}")
            self.assertEqual(response["peak_source"], inputs[3][0]["transitions"][index]["peak_source"])
            self.assertEqual(response["response_basis"], "native16_response_at_registered_original_pixel_only")
        self.assertEqual((inputs[1], inputs[2], inputs[3]), original)
        self.assert_authority_unavailable(result)

    def test_no_peak_reference_preserves_exact_texture_sample(self):
        inputs = _inputs()
        for point in inputs[3][0]["transitions"]:
            del point["peak_source"]
        result = _measure(inputs)
        for query in result["queries"]:
            response, = query["original_peak_anchor_responses"]
            self.assertEqual(response["state"], "supported")
            self.assertIsNone(response["peak_source"])
            self.assertEqual(response["source_coordinate_px"], 60)

    def test_secondary_reference_keeps_actual_sign_without_identity_authority(self):
        inputs = _inputs()
        for point in inputs[3][0]['transitions']:
            point.update(gradient_z=1.,tone_z=6.,texture_z=0.)
            point['peak_source'].update(polarity=0,candidate_ordinal=0)
        result = _measure(inputs)
        for query in result['queries']:
            response, = query['original_peak_anchor_responses']
            self.assertEqual(response['state'],'supported')
            self.assertEqual(response['original_polarity'],-1)
            self.assertEqual(response['peak_source']['polarity'],0)
            self.assertEqual(response['source_coordinate_px'],60)
        self.assert_authority_unavailable(result)
        for bad in ('strong_gradient','weak_secondary','candidate','zero_sign'):
            with self.subTest(bad=bad):
                changed = deepcopy(inputs)
                for point in changed[3][0]['transitions']:
                    if bad == 'strong_gradient':
                        point['gradient_z'] = 3.
                    elif bad == 'weak_secondary':
                        point['tone_z'] = 1.
                    elif bad == 'candidate':
                        point['peak_source']['candidate_ordinal'] = 2
                    else:
                        point['polarity'] = 0
                denied = _measure(changed)
                for query in denied['queries']:
                    response, = query['original_peak_anchor_responses']
                    self.assertEqual(response['failure_kind'],'original_polarity_unavailable'
                                     if bad == 'zero_sign' else 'original_peak_source_conflict')
                    self.assertIsNone(response['native_component_label'])
                self.assert_authority_unavailable(denied)

    def test_missing_ids_are_complete_and_not_joined_by_coordinate(self):
        inputs = _inputs()
        inputs[1][0]["transition_ids"] = ["missing:0", "missing:1", "raw:0", "missing:2"]
        result = _measure(inputs)
        for query in result["queries"]:
            self.assertEqual(query["original_peak_anchor_missing_transition_ids"],
                             ["missing:0", "missing:1", "missing:2"])
            self.assertEqual(query["original_peak_anchor_completeness"], "incomplete")
            for response in query["original_peak_anchor_responses"]:
                self.assertEqual(response["failure_kind"], "original_transition_set_incomplete")
                self.assertIsNone(response["native_component_label"])

    def test_missing_transition_ids_do_not_mean_no_obligations(self):
        inputs = _inputs()
        del inputs[1][0]["transition_ids"]
        result = _measure(inputs)
        for query in result["queries"]:
            self.assertEqual(query["original_peak_anchor_completeness"], "incomplete")
            self.assertIn("original_transition_ids_unavailable", query["original_peak_anchor_failure_kinds"])

    def test_duplicate_id_cannot_select_a_favorable_query(self):
        inputs = _inputs()
        duplicate = deepcopy(inputs[3][0])
        duplicate["query"]["query_id"] = "other-query"
        for point in duplicate["transitions"]:
            point["query_id"] = "other-query"
        inputs[3].append(duplicate)
        result = _measure(inputs)
        for query in result["queries"]:
            self.assertEqual(query["original_peak_anchor_ambiguous_transition_ids"], ["raw:0", "raw:1"])
            self.assertEqual(query["original_peak_anchor_responses"], [])

    def test_wrong_axis_cannot_borrow_the_same_coordinates(self):
        inputs = _inputs()
        inputs[3][0]["query"]["boundary_axis"] = "y"
        for query in _measure(inputs)["queries"]:
            response, = query["original_peak_anchor_responses"]
            self.assertEqual(response["failure_kind"], "original_query_axis_mismatch")
            self.assertEqual(response["boundary_axis"], "y")
            self.assertIsNone(response["native_component_label"])

    def test_pixel_must_be_in_both_original_search_and_ownership_domains(self):
        for name in ("search_intervals_px", "transition_ownership_intervals_px"):
            with self.subTest(name=name):
                inputs = _inputs()
                for interval in inputs[3][0]["query"][name]:
                    interval["maximum"] = 59.
                for query in _measure(inputs)["queries"]:
                    response, = query["original_peak_anchor_responses"]
                    self.assertEqual(response["failure_kind"], "original_pixel_outside_query")
                    self.assertIsNone(response["native_component_label"])

    def test_original_integer_pixel_does_not_receive_an_extra_query_tolerance(self):
        for endpoint, value in (("minimum", float(np.nextafter(60., np.inf))),
                                ("maximum", float(np.nextafter(60., -np.inf)))):
            with self.subTest(endpoint=endpoint):
                inputs = _inputs()
                for interval in inputs[3][0]["query"]["transition_ownership_intervals_px"]:
                    interval[endpoint] = value
                for query in _measure(inputs)["queries"]:
                    response, = query["original_peak_anchor_responses"]
                    self.assertEqual(response["failure_kind"], "original_pixel_outside_query")
                    self.assertIsNone(response["native_component_label"])

    def test_native_query_is_never_expanded_to_capture_original_pixel(self):
        inputs = _inputs(pixel=140)
        result = _measure(inputs)
        for query in result["queries"]:
            response, = query["original_peak_anchor_responses"]
            self.assertLess(query["query"]["sampled_strip_box"][2], 140)
            self.assertEqual(response["failure_kind"], "native_query_pixel_unobserved")
            self.assertIsNone(response["native_component_label"])

    def test_incomplete_or_inconsistent_original_fields_are_unavailable(self):
        cases = (
            (lambda m, p: p.pop("texture_sample_coordinate_px"), "original_pixel_unavailable"),
            (lambda m, p: p.update(polarity=0), "original_polarity_unavailable"),
            (lambda m, p: p.pop("polarity"), "original_polarity_unavailable"),
            (lambda m, p: p["peak_source"].update(source_coordinate_px=61), "original_peak_source_conflict"),
            (lambda m, p: p["peak_source"].update(polarity=1), "original_peak_source_conflict"),
            (lambda m, p: p.update(query_id="wrong"), "original_query_id_conflict"),
            (lambda m, p: p.update(trace_ordinal=1), "original_query_trace_unavailable"),
            (lambda m, p: m.update(coverage=None), "original_query_incomplete"),
            (lambda m, p: m["query"].update(trace_positions_px=None), "original_query_trace_unavailable"),
        )
        for alter, reason in cases:
            with self.subTest(reason=reason):
                inputs = _inputs()
                alter(inputs[3][0], inputs[3][0]["transitions"][0])
                result = _measure(inputs)
                response, = result["queries"][0]["original_peak_anchor_responses"]
                self.assertEqual(response["failure_kind"], reason)
                self.assertIsNone(response["native_component_label"])
                self.assertEqual(result["queries"][1]["original_peak_anchor_response_state"], "unavailable")

    def test_horizontal_vertical_and_both_axes_preserve_nonsquare_pixel_mapping(self):
        for axis in ("long", "short"):
            with self.subTest(axis=axis):
                horizontal = _measure(_inputs(axis=axis))
                vertical = _measure(_inputs(axis=axis, layout="vertical"), layout="vertical")
                for h, v in zip(horizontal["queries"], vertical["queries"], strict=True):
                    self.assertEqual(h["query"]["requested_strip_box"], v["query"]["requested_strip_box"])
                    self.assertEqual(h["native_rgb_sha256"], v["native_rgb_sha256"])
                    self.assertEqual(h["step_components"], v["step_components"])
                    a, = h["original_peak_anchor_responses"]
                    b, = v["original_peak_anchor_responses"]
                    self.assertEqual(a["state"], "supported")
                    self.assertEqual(a["native_component_label"], b["native_component_label"])
                    self.assertEqual(a["canonical_source_pixel_xy"], b["canonical_source_pixel_xy"][::-1])
                    self.assertNotEqual(a["boundary_axis"], b["boundary_axis"])

    def test_native_signal_uses_original_polarity_only(self):
        result = _measure(_inputs(polarity=1))
        for query in result["queries"]:
            response, = query["original_peak_anchor_responses"]
            self.assertEqual(response["original_polarity"], 1)
            self.assertEqual(response["native_component_label"], 0)
            self.assertEqual(response["failure_kind"], "native_signal_unavailable")

    def test_not_provided_and_explicit_empty_inputs_remain_distinct(self):
        inputs = _inputs()
        rgb, edges, sides, _measurements = inputs
        absent = native_local_connection_diagnostic(rgb, layout="horizontal", sequence_edges=edges,
            side_lines=sides, scales=SCALES)
        empty = _measure((rgb, edges, sides, []))
        self.assertEqual(absent["original_peak_anchor_input_state"], "not_provided")
        self.assertIsNone(absent["original_peak_anchor_input_transition_count"])
        self.assertEqual(empty["original_peak_anchor_input_state"], "provided")
        self.assertEqual(empty["original_peak_anchor_input_transition_count"], 0)
        for a, b in zip(absent["queries"], empty["queries"], strict=True):
            self.assertEqual(a["original_peak_anchor_completeness"], "not_provided")
            self.assertIsNone(a["original_peak_anchor_missing_transition_ids"])
            self.assertEqual(b["original_peak_anchor_completeness"], "incomplete")
            self.assertEqual(b["original_peak_anchor_missing_transition_ids"], ["raw:0", "raw:1"])

    def test_old_region_components_hashes_and_normalization_are_unchanged(self):
        inputs = _inputs()
        rgb, edges, sides, _measurements = inputs
        plain = native_local_connection_diagnostic(rgb, layout="horizontal", sequence_edges=edges,
            side_lines=sides, scales=SCALES)
        anchored = _measure(inputs)
        for name in ("registered_pixel_work", "normalization_queries", "mask_site_work_bound",
                     "anchor_signal_query_count", "continuing_signal_query_count"):
            self.assertEqual(plain[name], anchored[name])
        for a, b in zip(plain["queries"], anchored["queries"], strict=True):
            for name in ("query", "native_rgb_sha256", "pixel_count", "measured_profile_coordinate_count",
                         "profile_state", "kernel_unobserved_coordinate_columns", "step_components"):
                self.assertEqual(a[name], b[name])

    def test_metadata_reservation_counts_all_original_kinds_and_line_refs(self):
        inputs = _inputs()
        _, edges, sides, measurements = inputs
        measurements[0]["cross_height_transitions"] = [deepcopy(measurements[0]["transitions"][0])]
        measurements[0]["broad_material_transitions"] = [deepcopy(measurements[0]["transitions"][0])]
        reserved = _original_peak_anchor_reservation(measurements, edges, sides)
        self.assertEqual(reserved["original_peak_anchor_input_query_count"], 1)
        self.assertEqual(reserved["original_peak_anchor_input_line_count"], 1)
        self.assertEqual(reserved["original_peak_anchor_input_transition_count"], 4)
        self.assertEqual(reserved["original_peak_anchor_line_transition_reference_count"], 2)
        self.assertEqual(reserved["original_peak_anchor_value_work"], 4096+128*2+256*4+512*2)
        self.assertEqual(reserved["original_peak_anchor_retained_bytes"], 8192+1024*(2+4+4))

    def test_value_budget_is_checked_before_index_or_pixel_work_with_no_prefix(self):
        inputs = _inputs()
        rgb, edges, sides, measurements = inputs
        plain = native_local_connection_diagnostic(rgb, layout="horizontal", sequence_edges=edges,
            side_lines=sides, scales=SCALES)
        reserved = _original_peak_anchor_reservation(measurements, edges, sides)
        existing = plain["pixel_work_limit"]-plain["registered_pixel_work"]-reserved["original_peak_anchor_value_work"]+1
        with patch(OWNER+"._original_transition_index", side_effect=AssertionError("index before reservation")), \
             patch(OWNER+"._measure_profiles", side_effect=AssertionError("pixels before reservation")):
            result = _measure(inputs, existing_pixel_work=existing)
        self.assertEqual(result["state"], "work_bound_exceeded")
        self.assertEqual(result["bound_failures"], ["pixel_work"])
        self.assertEqual(result["queries"], [])
        self.assertEqual(result["original_peak_anchor_processing_state"], "not_started")
        self.assertEqual(result["original_peak_anchor_value_work"], reserved["original_peak_anchor_value_work"])

    def test_metadata_memory_is_reserved_before_index_or_pixels_with_no_prefix(self):
        _, edges, sides, measurements = _inputs()
        rgb = np.zeros((101, 2000, 3), dtype=np.uint16)
        measurements[0]["transitions"] = [measurements[0]["transitions"][0]]*40000
        with patch(OWNER+"._original_transition_index", side_effect=AssertionError("index before reservation")), \
             patch(OWNER+"._measure_profiles", side_effect=AssertionError("pixels before reservation")):
            result = _measure((rgb, edges, sides, measurements))
        self.assertEqual(result["state"], "work_bound_exceeded")
        self.assertEqual(result["bound_failures"], ["temporary_memory"])
        self.assertEqual(result["queries"], [])
        self.assertGreater(result["original_peak_anchor_retained_bytes"], 10*101*2000+32*1024*1024)
        self.assertLess(result["registered_pixel_work"]+result["original_peak_anchor_value_work"],
                        result["pixel_work_limit"])


if __name__ == "__main__":
    unittest.main()
