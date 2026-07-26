from __future__ import annotations

import unittest

from tools.regression.golden_baseline import (
    COMPARISON_SCHEMA,
    compare_baseline_record_to_report,
    compare_confirmed_polygon,
    map_output_box_to_source_polygon,
)
from tools.tests.support.physical_gates import (
    detection_workspace_fixture,
    review_only_candidate_fixture,
    selection_fixture,
)
from tools.tests.support.report import (
    analysis_identity_fixture,
    image_profile_fixture,
    report_record_fixture,
)
from x5crop.configuration.registry import get_detection_configuration
from x5crop.detection.decision.decision_gate import apply_decision_gate
from x5crop.detection.final.finalize import finalize_detection
from x5crop.domain import EvidenceState
from x5crop.output.model import AxisBleedParameters, FrameBleedPlan
from x5crop.report.configuration import detection_configuration_read_model
from x5crop.report.read_models import typed_read_model
from x5crop.report.record import report_record_for_final_detection


def _confirmed_baseline() -> dict:
    return {
        "baseline_schema": "x5crop_user_confirmed_golden_baseline_v1",
        "sample_id": "SYNTHETIC",
        "status": "user_confirmed",
        "authority": "explicit_user_confirmation_of_current_fitted_review_jpg",
        "source_relative_path": "input.tif",
        "source_sha256": "0" * 64,
        "raw_width_px": 310,
        "raw_height_px": 100,
        "frame_count": 2,
        "frames": [
            {
                "frame_index": 1,
                "confirmed_integer_boundary_polygon": [
                    [0, 0],
                    [150, 0],
                    [150, 100],
                    [0, 100],
                ],
            },
            {
                "frame_index": 2,
                "confirmed_integer_boundary_polygon": [
                    [160, 0],
                    [310, 0],
                    [310, 100],
                    [160, 100],
                ],
            },
        ],
    }


def _unresolved_report() -> dict:
    workspace = detection_workspace_fixture(EvidenceState.UNAVAILABLE)
    selection = selection_fixture(review_only_candidate_fixture())
    bleed = FrameBleedPlan(AxisBleedParameters(20, 10), (), (), (), ())
    detection = finalize_detection(
        apply_decision_gate(
            selection,
            bleed,
            workspace.scan_canvas_evidence,
            workspace.transform_geometry,
            automatic_processing_eligibility=EvidenceState.SUPPORTED,
        ),
        bleed,
        None,
    )
    return report_record_for_final_detection(
        detection,
        selection,
        source="input.tif",
        profile=typed_read_model(image_profile_fixture()),
        workspace=workspace,
        output_files=[],
        review_copy=None,
        warnings=[],
        configuration=detection_configuration_read_model(
            get_detection_configuration("135", "partial")
        ),
        analysis_identity=analysis_identity_fixture(
            workspace_identity=workspace.identity,
        ),
    )


class GoldenBaselineComparisonContractTest(unittest.TestCase):
    def test_output_box_uses_the_reported_inverse_affine_mapping(self) -> None:
        polygon = map_output_box_to_source_polygon(
            {"left": 15, "top": 27, "right": 25, "bottom": 37},
            {
                "matrix": [
                    [1.0, 0.0, 5.0],
                    [0.0, 1.0, 7.0],
                    [0.0, 0.0, 1.0],
                ],
                "source_extent": {"width": 100, "height": 100},
                "output_extent": {"width": 110, "height": 110},
            },
        )

        self.assertEqual(
            polygon,
            [
                [10.0, 20.0],
                [20.0, 20.0],
                [20.0, 30.0],
                [10.0, 30.0],
            ],
        )

    def test_directional_metrics_distinguish_outward_from_inward(self) -> None:
        comparison = compare_confirmed_polygon(
            [[10, 10], [20, 10], [20, 20], [10, 20]],
            [[9, 12], [21, 12], [21, 19], [9, 19]],
        )

        edges = {edge["role"]: edge for edge in comparison["edges"]}
        self.assertEqual(edges["top"]["signed_normal_distance_px"], -2.0)
        self.assertEqual(edges["top"]["inward_content_loss_px"], 2.0)
        self.assertEqual(edges["right"]["signed_normal_distance_px"], 1.0)
        self.assertEqual(edges["right"]["unsafe_outward_crossing_px"], 1.0)
        self.assertEqual(edges["bottom"]["signed_normal_distance_px"], -1.0)
        self.assertEqual(edges["left"]["signed_normal_distance_px"], 1.0)
        self.assertEqual(
            comparison["containment_relationship"],
            "crossing_or_disjoint",
        )
        self.assertEqual(comparison["unsafe_outward_crossing_max_px"], 1.0)
        self.assertEqual(comparison["inward_content_loss_max_px"], 2.0)

    def test_exact_current_output_compares_against_confirmed_integer_geometry(
        self,
    ) -> None:
        result = compare_baseline_record_to_report(
            _confirmed_baseline(),
            report_record_fixture(),
        )

        self.assertEqual(result["comparison_schema"], COMPARISON_SCHEMA)
        self.assertEqual(result["comparison_state"], "compared")
        self.assertEqual(
            result["confirmed_geometry_authority"],
            "confirmed_integer_boundary_polygon",
        )
        self.assertEqual(
            result["production_geometry_source"],
            "output.finalization_plan.base_geometry.frame_crop_envelopes",
        )
        self.assertEqual(result["frame_count"]["match"], True)
        self.assertEqual(result["aggregate"]["unsafe_outward_crossing_max_px"], 0.0)
        self.assertEqual(result["aggregate"]["inward_content_loss_max_px"], 0.0)
        self.assertEqual(result["aggregate"]["angle_difference_abs_max_deg"], 0.0)
        self.assertEqual(
            result["production"]["final_boxes"],
            [
                {"left": 0, "top": 0, "right": 170, "bottom": 100},
                {"left": 140, "top": 0, "right": 310, "bottom": 100},
            ],
        )
        self.assertNotIn("unsafe_outward_edge_count", result["aggregate"])
        self.assertNotIn("inward_content_loss_edge_count", result["aggregate"])
        self.assertNotIn("resolved-safe", str(result))
        self.assertTrue(
            all(
                frame["containment_relationship"] == "mutual"
                for frame in result["frames"]
            )
        )

    def test_unresolved_current_output_is_preserved_without_fake_frames(
        self,
    ) -> None:
        result = compare_baseline_record_to_report(
            _confirmed_baseline(),
            _unresolved_report(),
        )

        self.assertEqual(
            result["comparison_state"],
            "production_geometry_unavailable",
        )
        self.assertEqual(result["production"]["decision_status"], "needs_review")
        self.assertEqual(
            result["production"]["final_review_reasons"],
            [
                "count_resolution_unavailable",
                "transform_geometry_uncertain",
            ],
        )
        self.assertEqual(result["frames"], [])
        self.assertIsNone(result["aggregate"])
        self.assertIsNone(result["production"]["final_boxes"])

    def test_source_hash_mismatch_is_rejected(self) -> None:
        baseline = _confirmed_baseline()
        baseline["source_sha256"] = "f" * 64

        with self.assertRaisesRegex(ValueError, "source SHA-256 mismatch"):
            compare_baseline_record_to_report(
                baseline,
                report_record_fixture(),
            )


if __name__ == "__main__":
    unittest.main()
