from __future__ import annotations

from contextlib import redirect_stderr
import io
import json
import unittest

from tools.manual_annotation.model import EVALUATION_ROLE_CONTRACT
from tools.regression.accuracy import (
    GOLD_COHORT_PATH,
    _validate_evaluation_role,
    _validate_task_result,
    main as accuracy_main,
    validate_gold_source_identities,
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


def _basis_line(
    line_id: str,
    review_basis: str,
    points: list[list[float]],
) -> dict[str, object]:
    return {
        "line_id": line_id,
        "review_basis": review_basis,
        "points_raw": points,
    }


def _directional_geometry(
    polygon: list[list[float]],
    *,
    start_basis: str = "directly_visible",
) -> dict[str, object]:
    return {
        "format_id": "120-66",
        "count": 1,
        "strip_orientation": "horizontal",
        "coordinate_system": {
            "origin": "top_left",
            "x_direction": "right",
            "y_direction": "down",
            "continuous_coordinates": "raw_tiff_raster_pixel_centers",
            "canonical_extent": {"width": 560, "height": 560},
            "orientation_mapping": {
                "original_tag": 1,
                "raw_to_canonical": [
                    [1.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0],
                    [0.0, 0.0, 1.0],
                ],
                "canonical_to_raw": [
                    [1.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0],
                    [0.0, 0.0, 1.0],
                ],
            },
        },
        "shared_edges": [
            _basis_line("E1", "directly_visible", [[0.0, 0.0], [560.0, 0.0]]),
            _basis_line("E2", "directly_visible", [[0.0, 560.0], [560.0, 560.0]]),
        ],
        "boundary_pool": [
            _basis_line("B001", start_basis, [[0.0, 0.0], [0.0, 560.0]]),
            _basis_line("B002", "directly_visible", [[560.0, 0.0], [560.0, 560.0]]),
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
        "adjacencies": [],
        "frames": [_frame(polygon)],
        "evaluation_role": {
            "contract": EVALUATION_ROLE_CONTRACT,
            "cohort_role": "nominal",
            "reasons": [],
        },
    }


def _basis_aware_record(
    *,
    start_basis: str = "human_width_estimate",
) -> dict[str, object]:
    gold = [[0.0, 0.0], [560.0, 0.0], [560.0, 560.0], [0.0, 560.0]]
    return {
        "sample_id": "estimated-start",
        "format_id": "120-66",
        "cohort_role": "nominal",
        "confirmed_geometry": _directional_geometry(
            gold,
            start_basis=start_basis,
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
    def test_floating_partial_role_is_recomputed_from_frozen_geometry(self) -> None:
        gold = [
            [560.0, 0.0],
            [1120.0, 0.0],
            [1120.0, 560.0],
            [560.0, 560.0],
        ]
        geometry = _directional_geometry(
            gold,
            start_basis="visible_content_limit",
        )
        geometry["coordinate_system"]["canonical_extent"] = {
            "width": 1681,
            "height": 560,
        }
        geometry["shared_edges"] = [
            _basis_line(
                "E1",
                "directly_visible",
                [[0.0, 0.0], [1680.0, 0.0]],
            ),
            _basis_line(
                "E2",
                "directly_visible",
                [[0.0, 560.0], [1680.0, 560.0]],
            ),
        ]
        geometry["boundary_pool"] = [
            _basis_line(
                "B001",
                "visible_content_limit",
                [[560.0, 0.0], [560.0, 560.0]],
            ),
            _basis_line(
                "B002",
                "directly_visible",
                [[1120.0, 0.0], [1120.0, 560.0]],
            ),
        ]
        geometry["evaluation_role"] = {
            "contract": EVALUATION_ROLE_CONTRACT,
            "cohort_role": "challenge",
            "reasons": ["two_sided_floating_partial_sequence"],
        }
        record = {
            "sample_id": "floating-partial",
            "format_id": "120-66",
            "cohort_role": "challenge",
            "confirmed_geometry": geometry,
        }

        _validate_evaluation_role(record)

        record["cohort_role"] = "nominal"
        with self.assertRaisesRegex(ValueError, "evaluation role is invalid"):
            _validate_evaluation_role(record)

    def test_cohort_role_must_match_frozen_human_evidence(self) -> None:
        record = _basis_aware_record()
        _validate_evaluation_role(record)

        record["cohort_role"] = "challenge"
        with self.assertRaisesRegex(ValueError, "evaluation role is invalid"):
            _validate_evaluation_role(record)

        record = _basis_aware_record()
        record["confirmed_geometry"]["evaluation_role"]["reasons"] = [
            "manually_overridden"
        ]
        with self.assertRaisesRegex(ValueError, "evaluation role is invalid"):
            _validate_evaluation_role(record)

    def test_tracked_cohort_is_explicitly_incomplete_during_recalibration(self) -> None:
        records = [
            json.loads(line)
            for line in GOLD_COHORT_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(records, [])
        with self.assertRaisesRegex(ValueError, "calibration is incomplete"):
            validate_gold_source_identities()
        error = io.StringIO()
        with redirect_stderr(error):
            self.assertEqual(accuracy_main(), 1)
        self.assertIn("calibration is incomplete", error.getvalue())

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

    def test_directly_visible_gold_requires_safe_crop_not_detector_line_match(
        self,
    ) -> None:
        output = [
            [-20.0, -20.0],
            [580.0, -20.0],
            [580.0, 580.0],
            [-20.0, 580.0],
        ]
        report = _approved_report(output)
        self.assertNotIn("observations", report["photo_geometry"])

        self.assertEqual(
            _validate_task_result(
                _basis_aware_record(start_basis="directly_visible"),
                report,
            ),
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

    def test_visible_content_limit_blocks_inward_accuracy(self) -> None:
        output = [[10.0, 0.0], [560.0, 0.0], [560.0, 560.0], [10.0, 560.0]]

        with self.assertRaisesRegex(
            ValueError,
            "candidate crosses user-confirmed inward baseline",
        ):
            _validate_task_result(
                _basis_aware_record(start_basis="visible_content_limit"),
                _approved_report(output),
            )

    def test_visible_content_limit_does_not_block_outward_budget(self) -> None:
        output = [
            [-100.0, 0.0],
            [560.0, 0.0],
            [560.0, 560.0],
            [-100.0, 560.0],
        ]

        self.assertEqual(
            _validate_task_result(
                _basis_aware_record(start_basis="visible_content_limit"),
                _approved_report(output),
            ),
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

    def test_source_truncated_budget_uses_physical_line_axes(self) -> None:
        clipped_gold = [
            [0.0, 0.0],
            [200.0, 0.0],
            [560.0, 10.0],
            [560.0, 560.0],
            [0.0, 560.0],
        ]
        record = {
            "sample_id": "source-truncated",
            "format_id": "120-66",
            "cohort_role": "nominal",
            "confirmed_geometry": _directional_geometry(clipped_gold),
        }
        record["confirmed_geometry"]["slots"][0]["slot_kind"] = "source_truncated"
        output = [
            [-45.0, 0.0],
            [560.0, 0.0],
            [560.0, 560.0],
            [-45.0, 560.0],
        ]

        with self.assertRaisesRegex(
            ValueError,
            "exceeds acceptance-baseline direct-use budget",
        ):
            _validate_task_result(record, _approved_report(output))

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

    def test_blank_slot_keeps_runtime_ordinal_without_requiring_gold_geometry(
        self,
    ) -> None:
        slot_polygons = [
            [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]],
            [[20.0, 0.0], [30.0, 0.0], [30.0, 10.0], [20.0, 10.0]],
            [[40.0, 0.0], [50.0, 0.0], [50.0, 10.0], [40.0, 10.0]],
        ]
        for blank_ordinal in (1, 2, 3):
            with self.subTest(blank_ordinal=blank_ordinal):
                boundary_pool = []
                slots = []
                frames = []
                for ordinal, polygon in enumerate(slot_polygons, start=1):
                    if ordinal == blank_ordinal:
                        slots.append(
                            {
                                "ordinal": ordinal,
                                "slot_kind": "blank_exposure",
                                "reference_geometry": {"kind": "not_applicable"},
                            }
                        )
                        continue
                    start_id = f"B{ordinal:02d}S"
                    end_id = f"B{ordinal:02d}E"
                    boundary_pool.extend(
                        (
                            _basis_line(
                                start_id,
                                "directly_visible",
                                [polygon[0], polygon[3]],
                            ),
                            _basis_line(
                                end_id,
                                "directly_visible",
                                [polygon[1], polygon[2]],
                            ),
                        )
                    )
                    slots.append(
                        {
                            "ordinal": ordinal,
                            "slot_kind": "image",
                            "reference_geometry": {
                                "kind": "boundary_pair",
                                "start_boundary_id": start_id,
                                "end_boundary_id": end_id,
                            },
                        }
                    )
                    frames.append(
                        {
                            "frame_index": ordinal,
                            "polygon_source_pixel_center_coordinates": polygon,
                        }
                    )
                geometry = {
                    "strip_orientation": "horizontal",
                    "shared_edges": [
                        _basis_line(
                            "E1", "directly_visible", [[0.0, 0.0], [50.0, 0.0]]
                        ),
                        _basis_line(
                            "E2", "directly_visible", [[0.0, 10.0], [50.0, 10.0]]
                        ),
                    ],
                    "boundary_pool": boundary_pool,
                    "slots": slots,
                    "frames": frames,
                }
                outputs = [_output(polygon) for polygon in slot_polygons]
                record = {
                    "sample_id": f"blank-{blank_ordinal}",
                    "confirmed_geometry": geometry,
                }
                report = {
                    "photo_geometry": {"lanes": [{"output_footprints": outputs}]},
                    "output": {"finalization": {"output_footprints": outputs}},
                }

                self.assertTrue(validate_selected_candidate_coverage(record, report))
                validate_approved_geometry(record, report)


if __name__ == "__main__":
    unittest.main()
