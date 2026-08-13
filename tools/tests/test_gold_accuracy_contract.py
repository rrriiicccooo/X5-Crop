from __future__ import annotations

import unittest

from tools.regression.gold_geometry import ordered_gold_mapping


def _frame(polygon: list[list[float]]) -> dict[str, object]:
    return {"polygon_source_pixel_center_coordinates": polygon}


def _output(polygon: list[list[float]]) -> dict[str, object]:
    return {"constrained_source_footprint": polygon}


class GoldAccuracyContractTest(unittest.TestCase):
    def test_corner_local_sampling_difference_is_accepted(self) -> None:
        gold = [[0.0, 0.0], [560.0, 0.0], [560.0, 560.0], [0.0, 560.0]]
        corner_local = [
            [0.0, -1.0],
            [560.0, 0.004],
            [560.0, 559.996],
            [0.0, 561.0],
        ]

        self.assertEqual(
            ordered_gold_mapping(
                [_frame(gold)],
                [_output(corner_local)],
                "horizontal",
                "120-66",
            ),
            (0,),
        )

    def test_continuous_edge_inset_is_not_corner_local(self) -> None:
        gold = [[0.0, 0.0], [560.0, 0.0], [560.0, 560.0], [0.0, 560.0]]
        bottom_inset = [
            [0.0, 0.0],
            [560.0, 0.0],
            [560.0, 559.0],
            [0.0, 559.0],
        ]

        self.assertEqual(
            ordered_gold_mapping(
                [_frame(gold)],
                [_output(bottom_inset)],
                "horizontal",
                "120-66",
            ),
            (),
        )

    def test_corner_difference_beyond_sampling_uncertainty_is_rejected(
        self,
    ) -> None:
        gold = [[0.0, 0.0], [560.0, 0.0], [560.0, 560.0], [0.0, 560.0]]
        large_corner_cut = [
            [0.0, -5.0],
            [560.0, 0.1],
            [560.0, 559.9],
            [0.0, 565.0],
        ]

        self.assertEqual(
            ordered_gold_mapping(
                [_frame(gold)],
                [_output(large_corner_cut)],
                "horizontal",
                "120-66",
            ),
            (),
        )


if __name__ == "__main__":
    unittest.main()
