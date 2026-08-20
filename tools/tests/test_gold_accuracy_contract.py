from __future__ import annotations

import unittest

from tools.regression.accuracy import _validate_task_result
from tools.regression.gold_geometry import (
    ordered_gold_mapping,
    validate_selected_candidate_coverage,
)


def _frame(polygon: list[list[float]]) -> dict[str, object]:
    return {"polygon_source_pixel_center_coordinates": polygon}


def _output(polygon: list[list[float]]) -> dict[str, object]:
    return {"required_source_footprint": polygon}


class GoldAccuracyContractTest(unittest.TestCase):
    def test_challenge_review_cannot_bypass_candidate_coverage(self) -> None:
        gold = [[0.0, 0.0], [560.0, 0.0], [560.0, 560.0], [0.0, 560.0]]
        record = {
            "sample_id": "challenge-cut",
            "format_id": "120-66",
            "cohort_role": "challenge",
            "confirmed_geometry": {
                "strip_orientation": "horizontal",
                "frames": [_frame(gold)],
            },
        }
        report = {
            "decision": {"status": "needs_review"},
            "photo_geometry": {
                "lanes": [
                    {
                        "output_footprints": [
                            _output(
                                [
                                    [0.0, 0.0],
                                    [560.0, 0.0],
                                    [560.0, 559.0],
                                    [0.0, 559.0],
                                ]
                            )
                        ]
                    }
                ]
            },
            "output": {"finalization": {"output_footprints": []}},
        }

        with self.assertRaisesRegex(ValueError, "candidate cuts confirmed content"):
            _validate_task_result(record, report)

    def test_review_candidate_geometry_is_checked_without_official_outputs(
        self,
    ) -> None:
        gold = [[0.0, 0.0], [560.0, 0.0], [560.0, 560.0], [0.0, 560.0]]
        record = {
            "sample_id": "candidate-review",
            "format_id": "120-66",
            "confirmed_geometry": {
                "strip_orientation": "horizontal",
                "frames": [_frame(gold)],
            },
        }
        report = {
            "photo_geometry": {"lanes": [{"output_footprints": [_output(gold)]}]},
            "output": {"finalization": {"output_footprints": []}},
        }

        self.assertTrue(validate_selected_candidate_coverage(record, report))

    def test_review_candidate_that_cuts_content_is_rejected(self) -> None:
        gold = [[0.0, 0.0], [560.0, 0.0], [560.0, 560.0], [0.0, 560.0]]
        record = {
            "sample_id": "candidate-cut",
            "format_id": "120-66",
            "confirmed_geometry": {
                "strip_orientation": "horizontal",
                "frames": [_frame(gold)],
            },
        }
        report = {
            "photo_geometry": {
                "lanes": [
                    {
                        "output_footprints": [
                            _output(
                                [
                                    [0.0, 0.0],
                                    [560.0, 0.0],
                                    [560.0, 559.0],
                                    [0.0, 559.0],
                                ]
                            )
                        ]
                    }
                ]
            },
            "output": {"finalization": {"output_footprints": []}},
        }

        with self.assertRaisesRegex(ValueError, "candidate cuts confirmed content"):
            validate_selected_candidate_coverage(record, report)

    def test_review_without_selected_candidate_has_no_geometry_verdict(self) -> None:
        record = {
            "sample_id": "candidate-absent",
            "format_id": "120-66",
            "confirmed_geometry": {
                "strip_orientation": "horizontal",
                "frames": [_frame([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])],
            },
        }
        report = {
            "photo_geometry": {"lanes": [{"output_footprints": []}]},
            "output": {"finalization": {"output_footprints": []}},
        }

        self.assertFalse(validate_selected_candidate_coverage(record, report))

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

    def test_extra_output_is_not_a_valid_gold_mapping(self) -> None:
        gold = [[0.0, 0.0], [560.0, 0.0], [560.0, 560.0], [0.0, 560.0]]

        self.assertEqual(
            ordered_gold_mapping(
                [_frame(gold)],
                [_output(gold), _output(gold)],
                "horizontal",
                "120-66",
            ),
            (),
        )


if __name__ == "__main__":
    unittest.main()
