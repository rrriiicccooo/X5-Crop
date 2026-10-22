"""Raw spatial support cannot certify an unmeasured junction or photo identity."""

from copy import deepcopy
import unittest
from unittest.mock import patch

import numpy as np

from tools.regression.gold_spatial_incidence import native_spatial_incidence_probe


def _line(identity, traces, position, vertices=None):
    return {"observation_id": identity, "trace_coordinates_px": traces,
            "physical_line_region": {"reference_trace_px": 0.,
                "vertices": vertices or [[position, 0.]]}}


class SpatialIncidenceContractTest(unittest.TestCase):
    def test_crossing_fitted_lines_outside_observed_domains_is_not_a_corner(self):
        edge = _line("edge", [20, 80], 50.)
        side = _line("side", [20, 80], 10.)
        result = native_spatial_incidence_probe([edge], [side])
        self.assertEqual(result["measurements"], [["edge", "side", 0., 10.]])
        self.assertEqual(result["disjoint_domain_pair_count"], 1)
        self.assertEqual(result["same_photo_pair_authority"], "unavailable")

    def test_unsampled_connection_can_change_while_all_registered_profiles_stay_equal(self):
        connected = np.zeros((101, 101), dtype=np.uint8)
        connected[50, 20:81] = 255
        connected[20:81, 50] = 255
        disconnected = connected.copy()
        disconnected[50, 50] = 0
        traces = [20, 80]
        np.testing.assert_array_equal(connected[traces], disconnected[traces])
        np.testing.assert_array_equal(connected[:, traces], disconnected[:, traces])
        self.assertNotEqual(connected[50, 50], disconnected[50, 50])
        result = native_spatial_incidence_probe([_line("edge", traces, 50.)], [_line("side", traces, 50.)])
        self.assertEqual(result["overlapping_domain_pair_count"], 1)
        for authority in ("same_photo_pair_authority", "terminal_authority", "ordinal_authority"):
            self.assertEqual(result[authority], "unavailable")

    def test_full_physical_position_slope_region_is_preserved(self):
        edge = _line("edge", [20, 80], 0., vertices=[[0., 1.], [10., .5]])
        side = _line("side", [80, 100], 30.)
        original = deepcopy((edge, side))
        result = native_spatial_incidence_probe([edge], [side])
        self.assertEqual(result["overlapping_domain_pair_count"], 1)  # x=80 remains possible.
        self.assertEqual((edge, side), original)
        edge["physical_line_region"]["vertices"] = [[10., .5]]
        narrowed = native_spatial_incidence_probe([edge], [side])
        self.assertEqual(narrowed["measurements"][0][2], 30.)

    def test_missing_physical_domain_is_unmeasured_and_not_a_refutation(self):
        edge = _line("edge", [], 50.)
        result = native_spatial_incidence_probe([edge], [_line("side", [20, 80], 30.)])
        self.assertEqual(result["measurements"], [["edge", "side", None, None]])
        self.assertEqual(result["unavailable_domain_pair_count"], 1)

    def test_bound_exhaustion_keeps_no_favorable_prefix(self):
        with patch("tools.regression.gold_spatial_incidence.MAX_INCIDENCE_PAIRS", 1):
            result = native_spatial_incidence_probe([_line("a", [0, 1], 1.), _line("b", [0, 1], 2.)],
                                                  [_line("s", [0, 1], 1.)])
        self.assertEqual(result["state"], "work_bound_exceeded")
        self.assertEqual(result["required_pair_count"], 2)
        self.assertFalse(result["measurements"])
        self.assertFalse(result["candidate_or_reference_consumed"])
