"""Dense local pixel facts stay distinct from independent photo identity."""

from copy import deepcopy
from hashlib import sha256
import unittest
from unittest.mock import patch

import numpy as np

from tools.regression.gold_native_connections import (
    _measure_profiles, _normalization_plan, native_local_connection_diagnostic,
)
from x5crop.detection.photo_geometry.model import PHOTO_BOUNDARY_MEASUREMENT_SPEC as SPEC
from x5crop.detection.photo_geometry.registered_transition_measurement import measure_trace
from x5crop.domain import FiniteInterval
from x5crop.image.gray import BaseGrayParameters, _luma_u16


SCALES = {name: {"minimum": 20., "maximum": 20.}
          for name in ("width_axis_px_per_mm", "height_axis_px_per_mm")}


def _native_inputs():
    edge = {"observation_id": "native-edge", "trace_coordinates_px": [45, 80],
            "physical_line_region": {"reference_trace_px": 50., "vertices": [[50., 0.]]}}
    side = {"observation_id": "native-side", "trace_coordinates_px": [45, 80],
            "physical_line_region": {"reference_trace_px": 50., "vertices": [[50., 0.]]}}
    return [edge], [side]


def _measure(rgb, **kwargs):
    edges, sides = _native_inputs()
    return native_local_connection_diagnostic(rgb, layout="horizontal", sequence_edges=edges,
        side_lines=sides, scales=SCALES, **kwargs)


class NativeEndpointConnectionContractTest(unittest.TestCase):
    def test_unsampled_junction_change_is_measured_from_native_pixels(self):
        rgb = np.zeros((101, 101, 3), dtype=np.uint16)
        rgb[50, 45:81] = 32000
        rgb[45:81, 50] = 32000
        detached = rgb.copy()
        detached[50, 50] = 0
        np.testing.assert_array_equal(rgb[[45, 80]], detached[[45, 80]])
        np.testing.assert_array_equal(rgb[:, [45, 80]], detached[:, [45, 80]])
        connected, disconnected = _measure(rgb), _measure(detached)
        self.assertEqual(connected["state"], "measured_native_endpoint_neighborhoods")
        self.assertEqual(connected["completed_query_count"], 4)
        self.assertEqual(sum(a["native_rgb_sha256"] != b["native_rgb_sha256"]
                             for a, b in zip(connected["queries"], disconnected["queries"], strict=True)), 2)
        for result in (connected, disconnected):
            for authority in ("same_photo_pair_authority", "terminal_authority", "ordinal_authority"):
                self.assertEqual(result[authority], "unavailable")

    def test_real_l_shaped_rgb_step_does_not_label_a_photo_or_terminal(self):
        rgb = np.full((101, 101, 3), 64000, dtype=np.uint16)
        rgb[50:, 50:] = 12000
        result = _measure(rgb)
        self.assertTrue(any(sum(c["anchor_components_reaching_query_edge_count"]
                                    for c in q["step_components"])
                            for q in result["queries"]))
        # The identical pixels can also depict a printed L inside an exposure.
        self.assertEqual(result, _measure(rgb.copy()))
        self.assertFalse(result["candidate_or_reference_consumed"])
        self.assertEqual(result["same_photo_pair_authority"], "unavailable")
        self.assertEqual(result["terminal_authority"], "unavailable")

    def test_local_masks_use_the_complete_source_trace_baseline(self):
        rgb = np.full((101, 101, 3), 64000, dtype=np.uint16)
        rgb[:, 50:] = 12000
        queries = [{"state": "registered", "axis": "long", "coordinate_scale_px_per_mm": 20.,
                    "sampled_strip_box": box}
                   for box in ((35, 20, 65, 81), (48, 20, 53, 81))]
        plans = _normalization_plan(rgb, queries)
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["coordinate_interval_px"], (0, 101))
        self.assertEqual(plans[0]["trace_intervals_px"], ((20, 81),))
        masks, _peak = _measure_profiles(rgb, queries, plans, 32 * 1024 * 1024)
        luma = np.empty(rgb.shape[:2], dtype=np.float32)
        _luma_u16(rgb, luma, np.empty_like(luma), BaseGrayParameters())
        scalar = measure_trace(luma[20], FiniteInterval(0., 100.), 20., SPEC)
        credible = (scalar.gradient_z >= SPEC.gradient_z_minimum) & (
            np.maximum(scalar.tone_z, scalar.texture_z) >= SPEC.tone_or_texture_z_minimum)
        expected = np.zeros(101, dtype=np.uint8)
        expected[scalar.coordinates] = credible & (scalar.signed_gradient < 0.)
        self.assertTrue(np.any(expected[48:53]))
        for index, (left, _top, right, _bottom) in enumerate(q["sampled_strip_box"] for q in queries):
            np.testing.assert_array_equal(masks[index][1], np.tile(expected[left:right], (61, 1)))
        np.testing.assert_array_equal(masks[0][1][:, 13:18], masks[1][1])

    def test_vertical_layout_preserves_canonical_strip_measurements(self):
        rng = np.random.default_rng(20261022)
        rgb = rng.integers(0, 65536, (101, 101, 3), dtype=np.uint16)
        edges, sides = _native_inputs()
        horizontal = _measure(rgb)
        vertical = native_local_connection_diagnostic(rgb.transpose(1, 0, 2), layout="vertical",
            sequence_edges=edges, side_lines=sides, scales=SCALES)
        self.assertEqual(horizontal, vertical)

    def test_short_axis_queries_read_the_correct_nonsquare_source_pixels(self):
        rgb = np.random.default_rng(72).integers(0, 65536, (121, 181, 3), dtype=np.uint16)
        side = {"observation_id": "short-axis", "trace_coordinates_px": [20, 140],
                "physical_line_region": {"reference_trace_px": 80., "vertices": [[70., 0.]]}}
        result = native_local_connection_diagnostic(rgb, layout="horizontal", sequence_edges=[],
            side_lines=[side], scales=SCALES)
        first = result["queries"][0]
        self.assertEqual(first["query"]["sampled_strip_box"], (64, 14, 77, 27))
        # Short coordinate is source Y, trace is source X. The recorded box is
        # in that axis-local field; the hash preserves its transposed row order.
        expected = rgb[64:77, 14:27].transpose(1, 0, 2)
        self.assertEqual(first["native_rgb_sha256"], sha256(expected.tobytes()).hexdigest())
        changed = rgb.copy()
        changed[70, 20] ^= 65535
        other = native_local_connection_diagnostic(changed, layout="horizontal", sequence_edges=[],
            side_lines=[side], scales=SCALES)
        self.assertNotEqual(first["native_rgb_sha256"], other["queries"][0]["native_rgb_sha256"])
        self.assertEqual(result["queries"][1]["native_rgb_sha256"], other["queries"][1]["native_rgb_sha256"])

    def test_complete_joint_region_and_source_clipping_are_retained(self):
        rgb = np.zeros((101, 101, 3), dtype=np.uint16)
        edges, sides = _native_inputs()
        edges[0]["trace_coordinates_px"][0] = 0
        sides[0]["trace_coordinates_px"][0] = 0
        edges[0]["physical_line_region"]["vertices"] = [[50., -.02], [60., .02]]
        before = deepcopy(edges)
        result = native_local_connection_diagnostic(rgb, layout="horizontal", sequence_edges=edges,
            side_lines=sides, scales=SCALES)
        self.assertEqual(edges, before)
        self.assertTrue(any(q["query"]["source_clipped"] for q in result["queries"]))
        self.assertTrue(all(q["query"]["query_basis"] == "joint_native_position_slope_region"
                            for q in result["queries"]))
        self.assertLessEqual(result["registered_pixel_work"], result["pixel_work_limit"])
        self.assertLessEqual(result["peak_temporary_bytes"], 10 * 101 * 101 + 32 * 1024 * 1024)

    def test_work_exhaustion_never_measures_a_favorable_prefix(self):
        rgb = np.zeros((101, 101, 3), dtype=np.uint16)
        with patch("tools.regression.gold_native_connections._measure_query",
                   side_effect=AssertionError("must freeze and reserve all queries first")):
            result = _measure(rgb, existing_pixel_work=128 * 101 * 101)
        self.assertEqual(result["state"], "work_bound_exceeded")
        self.assertEqual(result["queries"], [])
        self.assertEqual(result["registered_query_count"], 4)

    def test_invalid_existing_work_is_rejected(self):
        for value in (True, -1, 1.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                _measure(np.zeros((101, 101, 3), dtype=np.uint16), existing_pixel_work=value)


if __name__ == "__main__":
    unittest.main()
