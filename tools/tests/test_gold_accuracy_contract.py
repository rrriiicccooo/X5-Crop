from __future__ import annotations

import json
import unittest

from tools.manual_annotation.model import (
    BASELINE_SCHEMA,
    canonical_record_sha256,
)
from tools.regression.accuracy import (
    CONFIRMED_GEOMETRY_KEYS,
    GOLD_COHORT_PATH,
    _validate_task_result,
)
from tools.regression.gold_geometry import (
    ordered_gold_mapping,
    validate_approved_geometry,
    validate_selected_candidate_coverage,
)


def _frame(polygon: list[list[float]]) -> dict[str, object]:
    return {
        "frame_index": 1,
        "polygon_source_pixel_center_coordinates": polygon,
    }


def _output(polygon: list[list[float]]) -> dict[str, object]:
    return {"required_source_footprint": polygon}


def _basis_line(line_id: str, review_basis: str) -> dict[str, object]:
    return {"line_id": line_id, "review_basis": review_basis}


def _directional_geometry(
    polygon: list[list[float]],
    *,
    start_basis: str = "directly_visible",
) -> dict[str, object]:
    return {
        "strip_orientation": "horizontal",
        "shared_edges": [
            _basis_line("E1", "directly_visible"),
            _basis_line("E2", "directly_visible"),
        ],
        "boundary_pool": [
            _basis_line("B001", start_basis),
            _basis_line("B002", "directly_visible"),
        ],
        "slots": [
            {
                "ordinal": 1,
                "slot_kind": "image",
                "reference_geometry": {
                    "kind": "boundary_pair",
                    "start_boundary_id": "B001",
                    "end_boundary_id": "B002",
                },
            }
        ],
        "frames": [_frame(polygon)],
    }


def _basis_aware_record() -> dict[str, object]:
    gold = [[0.0, 0.0], [560.0, 0.0], [560.0, 560.0], [0.0, 560.0]]
    return {
        "sample_id": "estimated-start",
        "format_id": "120-66",
        "cohort_role": "nominal",
        "confirmed_geometry": _directional_geometry(
            gold,
            start_basis="human_width_estimate",
        ),
    }


def _approved_report(polygon: list[list[float]]) -> dict[str, object]:
    output = _output(polygon)
    return {
        "decision": {"status": "approved_auto"},
        "photo_geometry": {"lanes": [{"output_footprints": [output]}]},
        "output": {"finalization": {"output_footprints": [output]}},
    }


class GoldAccuracyContractTest(unittest.TestCase):
    def test_tracked_v1_rows_use_current_directional_schema(self) -> None:
        records = [
            json.loads(line)
            for line in GOLD_COHORT_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(len(records), 9)
        for record in records:
            geometry = record["confirmed_geometry"]
            self.assertEqual(set(geometry), CONFIRMED_GEOMETRY_KEYS)
            self.assertEqual(geometry["baseline_schema"], BASELINE_SCHEMA)
            self.assertEqual(record["acceptance_baseline_schema"], BASELINE_SCHEMA)
            self.assertEqual(
                record["geometry_digest"],
                canonical_record_sha256(geometry),
            )
            lines = geometry["shared_edges"] + geometry["boundary_pool"]
            self.assertEqual(
                [line["role"] for line in geometry["shared_edges"]],
                ["short_low", "short_high"],
            )
            self.assertTrue(
                all(line["review_basis"] == "directly_visible" for line in lines)
            )
            self.assertTrue(
                all(slot["slot_kind"] == "image" for slot in geometry["slots"])
            )
            self.assertTrue(
                all(
                    slot["reference_geometry"]["kind"] == "boundary_pair"
                    for slot in geometry["slots"]
                )
            )
            boundary_ids = {
                line["line_id"] for line in geometry["boundary_pool"]
            }
            self.assertTrue(
                all(
                    {
                        slot["reference_geometry"]["start_boundary_id"],
                        slot["reference_geometry"]["end_boundary_id"],
                    }
                    <= boundary_ids
                    for slot in geometry["slots"]
                )
            )
            self.assertTrue(
                all(item["kind"] == "separator" for item in geometry["adjacencies"])
            )

    def test_incomplete_directional_geometry_is_rejected(self) -> None:
        gold = [[0.0, 0.0], [560.0, 0.0], [560.0, 560.0], [0.0, 560.0]]
        record = {
            "sample_id": "incomplete",
            "confirmed_geometry": {
                "strip_orientation": "horizontal",
                "frames": [_frame(gold)],
            },
        }
        report = {
            "photo_geometry": {"lanes": [{"output_footprints": [_output(gold)]}]},
            "output": {"finalization": {"output_footprints": []}},
        }

        with self.assertRaisesRegex(
            ValueError,
            "gold directional evidence is incomplete",
        ):
            validate_selected_candidate_coverage(record, report)

    def test_estimated_start_does_not_block_inward_accuracy(self) -> None:
        output = [[10.0, 0.0], [560.0, 0.0], [560.0, 560.0], [10.0, 560.0]]

        self.assertEqual(
            _validate_task_result(_basis_aware_record(), _approved_report(output)),
            "approved_auto",
        )

    def test_directional_check_does_not_depend_on_output_vertex_origin(self) -> None:
        output = [[560.0, 0.0], [560.0, 560.0], [10.0, 560.0], [10.0, 0.0]]

        self.assertEqual(
            _validate_task_result(_basis_aware_record(), _approved_report(output)),
            "approved_auto",
        )

    def test_estimated_start_does_not_block_direct_use_budget(self) -> None:
        output = [
            [-100.0, 0.0],
            [560.0, 0.0],
            [560.0, 560.0],
            [-100.0, 560.0],
        ]

        self.assertEqual(
            _validate_task_result(_basis_aware_record(), _approved_report(output)),
            "approved_auto",
        )

    def test_visible_end_remains_blocking_when_start_is_estimated(self) -> None:
        output = [[0.0, 0.0], [559.0, 0.0], [559.0, 560.0], [0.0, 560.0]]

        with self.assertRaisesRegex(
            ValueError,
            "candidate crosses user-confirmed inward baseline",
        ):
            _validate_task_result(_basis_aware_record(), _approved_report(output))

    def test_visible_end_budget_remains_blocking_when_start_is_estimated(
        self,
    ) -> None:
        output = [[0.0, 0.0], [660.0, 0.0], [660.0, 560.0], [0.0, 560.0]]

        with self.assertRaisesRegex(
            ValueError,
            "exceeds acceptance-baseline direct-use budget",
        ):
            _validate_task_result(_basis_aware_record(), _approved_report(output))

    def test_challenge_review_cannot_bypass_candidate_coverage(self) -> None:
        gold = [[0.0, 0.0], [560.0, 0.0], [560.0, 560.0], [0.0, 560.0]]
        record = {
            "sample_id": "challenge-cut",
            "format_id": "120-66",
            "cohort_role": "challenge",
            "confirmed_geometry": _directional_geometry(gold),
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

        with self.assertRaisesRegex(
            ValueError,
            "candidate crosses user-confirmed inward baseline",
        ):
            _validate_task_result(record, report)

    def test_review_candidate_geometry_is_checked_without_official_outputs(
        self,
    ) -> None:
        gold = [[0.0, 0.0], [560.0, 0.0], [560.0, 560.0], [0.0, 560.0]]
        record = {
            "sample_id": "candidate-review",
            "format_id": "120-66",
            "confirmed_geometry": _directional_geometry(gold),
        }
        report = {
            "photo_geometry": {"lanes": [{"output_footprints": [_output(gold)]}]},
            "output": {"finalization": {"output_footprints": []}},
        }

        self.assertTrue(validate_selected_candidate_coverage(record, report))

    def test_review_candidate_that_crosses_inward_baseline_is_rejected(
        self,
    ) -> None:
        gold = [[0.0, 0.0], [560.0, 0.0], [560.0, 560.0], [0.0, 560.0]]
        record = {
            "sample_id": "candidate-cut",
            "format_id": "120-66",
            "confirmed_geometry": _directional_geometry(gold),
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

        with self.assertRaisesRegex(
            ValueError,
            "candidate crosses user-confirmed inward baseline",
        ):
            validate_selected_candidate_coverage(record, report)

    def test_review_without_selected_candidate_has_no_geometry_verdict(self) -> None:
        record = {
            "sample_id": "candidate-absent",
            "format_id": "120-66",
            "confirmed_geometry": _directional_geometry(
                [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
            ),
        }
        report = {
            "photo_geometry": {"lanes": [{"output_footprints": []}]},
            "output": {"finalization": {"output_footprints": []}},
        }

        self.assertFalse(validate_selected_candidate_coverage(record, report))

    def test_subpixel_corner_inset_crosses_the_inward_baseline(self) -> None:
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
            ),
            (),
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
            ),
            (),
        )

    def test_corner_inset_is_rejected(self) -> None:
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
            ),
            (),
        )

    def test_five_percent_outward_envelope_is_direct_use(self) -> None:
        gold = [[100.0, 100.0], [660.0, 100.0], [660.0, 660.0], [100.0, 660.0]]
        five_percent = [[72.0, 72.0], [688.0, 72.0], [688.0, 688.0], [72.0, 688.0]]
        record = {
            "sample_id": "five-percent",
            "confirmed_geometry": _directional_geometry(gold),
        }
        report = {
            "output": {
                "finalization": {
                    "output_footprints": [_output(five_percent)],
                }
            }
        }

        validate_approved_geometry(record, report)

    def test_enclosing_height_cannot_hide_one_sided_ten_percent_expansion(
        self,
    ) -> None:
        gold = [[100.0, 100.0], [660.0, 100.0], [660.0, 660.0], [100.0, 660.0]]
        one_sided_ten_percent = [
            [100.0, 44.0],
            [660.0, 44.0],
            [660.0, 660.0],
            [100.0, 660.0],
        ]
        record = {
            "sample_id": "one-sided-ten-percent",
            "confirmed_geometry": _directional_geometry(gold),
        }
        output = _output(one_sided_ten_percent)
        output["envelope"] = {"boundary_use": "enclosing_support_pair"}
        report = {
            "output": {"finalization": {"output_footprints": [output]}}
        }

        with self.assertRaisesRegex(
            ValueError,
            "exceeds acceptance-baseline direct-use budget",
        ):
            validate_approved_geometry(record, report)

    def test_extra_output_is_not_a_valid_gold_mapping(self) -> None:
        gold = [[0.0, 0.0], [560.0, 0.0], [560.0, 560.0], [0.0, 560.0]]

        self.assertEqual(
            ordered_gold_mapping(
                [_frame(gold)],
                [_output(gold), _output(gold)],
                "horizontal",
            ),
            (),
        )


if __name__ == "__main__":
    unittest.main()
