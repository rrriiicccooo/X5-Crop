from __future__ import annotations

import unittest

import numpy as np

from x5crop.detection.physical.outer.base import base_outer_candidates
from x5crop.detection.physical.outer.side_boundary import side_boundary_outer
from x5crop.geometry.detection_parameters import OuterBoxDetectionParameters


class OuterSideBoundaryTests(unittest.TestCase):
    def test_sides_can_independently_touch_black_rim_or_content(self) -> None:
        gray = np.full((120, 240), 255, dtype=np.uint8)
        gray[20:100, 40:200] = 120
        gray[20:24, 40:200] = 0
        gray[20:100, 196:200] = 0
        gray[96:100, 40:200] = 0
        config = OuterBoxDetectionParameters(
            white_border_ratio=0.95,
            white_run_ratio=0.01,
            white_run_min=2,
            white_run_max=8,
            white_margin_ratio=0.0,
            white_margin_min=0,
        )

        result = side_boundary_outer(gray, config)
        detail = result.detail()

        self.assertTrue(detail["used"])
        self.assertEqual(detail["box"], {"left": 40, "top": 20, "right": 200, "bottom": 100})
        models = {side["side"]: side["boundary_model"] for side in detail["sides"]}
        self.assertEqual(models["left"], "content_to_white_holder")
        self.assertEqual(models["top"], "black_border_to_white_holder")
        self.assertEqual(models["right"], "black_border_to_white_holder")
        self.assertEqual(models["bottom"], "black_border_to_white_holder")

    def test_base_outer_candidate_carries_side_boundary_detail(self) -> None:
        gray = np.full((120, 240), 255, dtype=np.uint8)
        gray[20:100, 40:200] = 120
        config = OuterBoxDetectionParameters(
            white_border_ratio=0.95,
            white_run_ratio=0.01,
            white_run_min=2,
            white_run_max=8,
            white_margin_ratio=0.0,
            white_margin_min=0,
        )

        candidates = base_outer_candidates(gray, config)
        side_candidates = [candidate for candidate in candidates if candidate.name == "mixed_boundary"]

        self.assertEqual(len(side_candidates), 1)
        self.assertEqual(
            side_candidates[0].detail["physical_rule"],
            "mixed_boundary_side_independent",
        )
        self.assertEqual(
            side_candidates[0].detail["evidence_name"],
            "outer_side_boundary_evidence",
        )
        self.assertEqual(len(side_candidates[0].detail["sides"]), 4)


if __name__ == "__main__":
    unittest.main()
