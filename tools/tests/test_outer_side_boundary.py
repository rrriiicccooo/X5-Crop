from __future__ import annotations

import unittest

import numpy as np

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
        roles = {side["side"]: side["role"] for side in detail["sides"]}
        self.assertEqual(roles["left"], "holder_to_content")
        self.assertEqual(roles["top"], "holder_to_black_rim")
        self.assertEqual(roles["right"], "holder_to_black_rim")
        self.assertEqual(roles["bottom"], "holder_to_black_rim")


if __name__ == "__main__":
    unittest.main()
