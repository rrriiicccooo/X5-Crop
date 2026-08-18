from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from tools.regression.file_identity import sha256_file
from tools.regression.v4_gold_comparison import (
    COMPARISON_SCHEMA,
    build_comparison_record,
    compare_gold_reports,
)


ROOT = Path(__file__).resolve().parents[2]


def cohort() -> dict[str, object]:
    return {
        "sample_id": "S001",
        "source_relative_path": "Test/135/example.tif",
        "source_sha256": "a" * 64,
        "confirmed_geometry": {
            "strip_orientation": "horizontal",
            "raw_width_px": 100,
            "raw_height_px": 80,
            "frames": [
                {
                    "polygon_source_pixel_center_coordinates": [
                        [10.0, 20.0],
                        [90.0, 20.0],
                        [90.0, 70.0],
                        [10.0, 70.0],
                    ]
                }
            ],
        },
    }


def v4_report() -> dict[str, object]:
    return {
        "source": "/tmp/example.tif",
        "status": "approved_auto",
        "outer_box": {"left": 12, "top": 22, "right": 88, "bottom": 68},
        "frame_boxes": [
            {"left": 8, "top": 18, "right": 92, "bottom": 72}
        ],
        "detail": {
            "output_bleed": {
                "used": True,
                "output_long_axis_bleed": 4,
                "output_short_axis_bleed": 4,
                "overlap_risk_long_axis_bleed": False,
            }
        },
    }


def v5_report() -> dict[str, object]:
    footprint = {
        "required_source_footprint": [
            [7.0, 17.0],
            [93.0, 17.0],
            [93.0, 73.0],
            [7.0, 73.0],
        ],
        "boundary_protections": [
            {"role": role, "bleed_px": 2.0, "joint_expansion_px": 3.0}
            for role in ("start", "end", "top", "bottom")
        ],
    }
    return {
        "runtime_identity": {
            "source": {"name": "example.tif", "shape": [80, 100, 3]}
        },
        "decision": {"status": "approved_auto"},
        "photo_geometry": {
            "matched_holder": {
                "axis_scales": {
                    "width_axis_px_per_mm": {"minimum": 10.0, "maximum": 10.0},
                    "height_axis_px_per_mm": {"minimum": 10.0, "maximum": 10.0},
                }
            },
            "lanes": [
                {
                    "lane_id": "lane:0",
                    "coarse_strip_support": {
                        "long_interval_px": {"minimum": 0.0, "maximum": 100.0},
                        "short_interval_px": {"minimum": 0.0, "maximum": 80.0},
                    },
                    "photo_group_outer": {
                        "lower_px": {"minimum": 10.0, "maximum": 11.0},
                        "upper_px": {"minimum": 89.0, "maximum": 90.0},
                    },
                    "output_footprints": [footprint],
                }
            ],
        },
        "development": {
            "lanes": [
                {
                    "lane_id": "lane:0",
                    "observations": {
                        "sequence_edges": [
                            {
                                "observation_id": "edge:1",
                                "qualified_anchor_roles": ["start"],
                            }
                        ],
                        "registered_top_bottom_bindings": [
                            {
                                "observation_id": "cross:1",
                                "role_authorized": True,
                            }
                        ],
                    },
                    "cross_competition": {
                        "best": {
                            "boundary_use": "aperture_pair",
                            "top_canonical_px": 20.0,
                            "bottom_canonical_px": 70.0,
                            "direct_bindings": [
                                {"observation_id": "cross:1"}
                            ],
                        }
                    },
                }
            ]
        },
    }


class V4GoldComparisonContractTest(unittest.TestCase):
    def test_keeps_truth_and_historical_behavior_separate(self) -> None:
        result = build_comparison_record(cohort(), v4_report(), v5_report())
        self.assertEqual(result["schema"], COMPARISON_SCHEMA)
        self.assertEqual(
            result["authority"]["reference"],
            "user_confirmed_golden_geometry",
        )
        self.assertEqual(result["authority"]["v4"], "historical_behavior_only")
        self.assertEqual(
            result["v4_outer_to_final_crop_delta"]["sequence"],
            {"lower_delta_px": -4.0, "upper_delta_px": 4.0},
        )
        self.assertEqual(result["v4_output_bleed_policy"]["long_axis_px"], 4)
        self.assertIn("different physical objects", result["v4_outer_crop_identity_note"])
        self.assertEqual(
            result["deviation_from_human"]["v4_detected_outer"]["cross"]
            ["lower_delta_px"],
            2.0,
        )
        self.assertEqual(
            result["v5_protection_ledger"]["top"]["maximum_bleed_px"],
            2.0,
        )

    def test_photo_group_outer_does_not_claim_cross_authority(self) -> None:
        result = build_comparison_record(cohort(), v4_report(), v5_report())
        self.assertEqual(set(result["v5_photo_group_outer"]), {"sequence"})
        self.assertEqual(
            result["v5_selected_cross"][0]["direct_observation_ids"],
            ["cross:1"],
        )

    def test_rejects_mismatched_source_identity(self) -> None:
        report = deepcopy(v5_report())
        report["runtime_identity"]["source"]["name"] = "other.tif"
        with self.assertRaisesRegex(ValueError, "source identity"):
            build_comparison_record(cohort(), v4_report(), report)

    def test_comparison_entrypoint_rehashes_the_golden_source(self) -> None:
        record = cohort()
        record.update(
            {
                "source_relative_path": "README.md",
                "source_sha256": sha256_file(ROOT / "README.md"),
                "format_id": "135",
                "count": 1,
            }
        )
        historical = v4_report()
        historical["source"] = "/tmp/README.md"
        current = v5_report()
        current["runtime_identity"]["source"]["name"] = "README.md"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cohort_path = root / "cohort.jsonl"
            cohort_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            for report_root, name, payload in (
                (root / "v4", "split_report.jsonl", historical),
                (root / "v5", "x5_crop_report.jsonl", current),
            ):
                sample = report_root / "S001"
                sample.mkdir(parents=True)
                (sample / name).write_text(
                    json.dumps(payload) + "\n",
                    encoding="utf-8",
                )
            self.assertEqual(
                len(
                    compare_gold_reports(
                        cohort_path=cohort_path,
                        v4_root=root / "v4",
                        v5_root=root / "v5",
                    )
                ),
                1,
            )
            record["source_sha256"] = "0" * 64
            cohort_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "golden source identity"):
                compare_gold_reports(
                    cohort_path=cohort_path,
                    v4_root=root / "v4",
                    v5_root=root / "v5",
                )


if __name__ == "__main__":
    unittest.main()
