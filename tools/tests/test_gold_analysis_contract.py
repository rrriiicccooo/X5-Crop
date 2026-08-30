from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools.regression.accuracy import DEVELOPMENT_GOLD_COHORT_PATH
from tools.regression.gold_analysis import (
    ANALYSIS_RECORD_SCHEMA,
    _analysis_identity,
    _summary,
    line_axis_position,
    main as gold_analysis_main,
    optimization_stage_index,
    sequence_boundary_diagnostics,
    validate_gold_analysis_artifacts,
)


class GoldAnalysisContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.records = {
            row["sample_id"]: row
            for row in (
                json.loads(line)
                for line in DEVELOPMENT_GOLD_COHORT_PATH.read_text(
                    encoding="utf-8"
                ).splitlines()
                if line.strip()
            )
        }

    def test_stage_index_is_gold_only_and_keeps_irregular_nominal_separate(
        self,
    ) -> None:
        core = optimization_stage_index(self.records["S001"])
        irregular = optimization_stage_index(self.records["S098"])

        self.assertEqual(core["stage"], "stage1_core_nominal")
        self.assertEqual(core["reasons"], [])
        self.assertEqual(irregular["stage"], "stage2_harder_nominal")
        self.assertIn("gold_lattice_residual_over_2_percent", irregular["reasons"])

    def test_sequence_diagnostic_separates_binding_from_observation(self) -> None:
        geometry = self.records["S001"]["confirmed_geometry"]
        pool = {line["line_id"]: line for line in geometry["boundary_pool"]}
        first = geometry["slots"][0]["reference_geometry"]
        trace = (
            float(geometry["coordinate_system"]["canonical_extent"]["height"])
            - 1.0
        ) / 2.0
        start = line_axis_position(
            geometry,
            pool[first["start_boundary_id"]],
            axis="sequence",
            reference_trace_px=trace,
        )
        end = line_axis_position(
            geometry,
            pool[first["end_boundary_id"]],
            axis="sequence",
            reference_trace_px=trace,
        )

        def observation(identity: str, role: str, position: float) -> dict[str, object]:
            return {
                "observation_id": identity,
                "reference_trace_px": trace,
                "canonical_position_px": position,
                "full_position_interval_px": {
                    "minimum": position - 0.5,
                    "maximum": position + 0.5,
                },
                "qualified_anchor_roles": [role],
            }

        bindings: list[dict[str, str] | None] = [
            None
        ] * (2 * int(geometry["count"]))
        bindings[0] = {"observation_id": "start-observation"}
        frames = [
            {
                "start": {"canonical_position_px": 0.0},
                "end": {"canonical_position_px": 0.0},
            }
            for _ in geometry["slots"]
        ]
        frames[0]["start"]["canonical_position_px"] = start
        frames[0]["end"]["canonical_position_px"] = end
        lane = {
            "observations": {
                "sequence_edges": [
                    observation("start-observation", "start", start),
                    observation("unbound-end-observation", "end", end),
                ]
            },
            "phase_competition": {
                "status": "resolved",
                "best": {
                    "role_bindings": bindings,
                },
            },
            "placement_competition": {
                "selected_placement_id": "selected",
                "placements": [
                    {
                        "placement_id": "selected",
                        "frames": frames,
                    }
                ],
            },
        }

        diagnostics = sequence_boundary_diagnostics(
            geometry,
            lane,
            placement_state="supported",
        )

        self.assertEqual(diagnostics[0]["diagnostic_class"], "observed_and_bound")
        self.assertEqual(diagnostics[1]["diagnostic_class"], "observed_but_unbound")
        self.assertEqual(
            diagnostics[2]["diagnostic_class"],
            "template_inferred_without_gold_observation",
        )
        self.assertTrue(all(item["resolution"] == "resolved" for item in diagnostics))

    @staticmethod
    def _analysis_record(
        sample_id: str,
        *,
        source_sha256: str,
        role: str,
        decision: str,
        candidate: str,
        unsafe_auto: bool,
        physical_frame_id: str,
    ) -> dict[str, object]:
        contract_passed = not unsafe_auto and not (
            role == "nominal" and decision == "needs_review"
        )
        frame_unsafe = candidate == "unsafe"
        return {
            "record_schema": ANALYSIS_RECORD_SCHEMA,
            "sample_id": sample_id,
            "source_sha256": source_sha256,
            "format_id": "135",
            "count": 1,
            "cohort_role": role,
            "optimization_stage": {
                "stage": (
                    "stage3_challenge"
                    if role == "challenge"
                    else "stage1_core_nominal"
                )
            },
            "decision_status": decision,
            "final_review_reasons": [],
            "development_contract_passed": contract_passed,
            "development_contract_failure": (
                None if contract_passed else "synthetic contract failure"
            ),
            "candidate_geometry_conformance": candidate,
            "candidate_geometry_failure": (
                "synthetic candidate failure" if frame_unsafe else None
            ),
            "unsafe_approved_auto": unsafe_auto,
            "nominal_auto_goal_passed": (
                role == "nominal" and decision == "approved_auto" and not unsafe_auto
            ),
            "challenge_capability_outcome": (
                "needs_review_with_unsafe_candidate"
                if role == "challenge" and decision == "needs_review"
                else None
            ),
            "source_placement_state": "supported",
            "phase_status": "resolved",
            "phase_failure_kind": None,
            "cross_status": "resolved",
            "cross_failure_reason": None,
            "placement_failure_gap": None,
            "selected_cross_boundary_use": "aperture_pair",
            "duration_seconds": 1.0,
            "boundary_diagnostics": [],
            "frame_candidate_geometry_diagnostics": [
                {
                    "frame_index": 1,
                    "physical_frame_id": physical_frame_id,
                    "inward_failure_sides": (
                        ["sequence_start"] if frame_unsafe else []
                    ),
                    "outward_budget_failure_sides": [],
                }
            ],
            "physical_prior_diagnostic": {
                "source_sha256": source_sha256,
                "format_id": "135",
                "count": 1,
                "scan_canvas_outcome": "supported",
                "scan_canvas_matching_profile_ids": ["135_standard"],
                "scan_canvas_profile_id": "135_standard",
                "nearest_scan_canvas_profile_id": "135_standard",
                "scan_canvas_aspect_error_ratio": 0.0,
                "scan_canvas_scale_authority_supported": True,
                "frame_ratio_measurements": [1.5],
                "excluded_frame_count": 0,
                "separator_gap_measurements_mm": [2.0],
                "separator_gap_prior_containment": [True],
                "pitch_measurements_mm": [38.0],
                "pitch_prior_containment": [True],
                "excluded_separator_count": 0,
                "cross_corridor": {
                    "available": True,
                    "trace_count": 3,
                    "top_outside_trace_count": 0,
                    "bottom_outside_trace_count": 0,
                    "maximum_top_outside_px": 0.0,
                    "maximum_bottom_outside_px": 0.0,
                },
            },
        }

    def test_summary_separates_unsafe_auto_from_review_candidate(self) -> None:
        shared_sha = "a" * 64
        records = (
            self._analysis_record(
                "auto",
                source_sha256=shared_sha,
                role="nominal",
                decision="approved_auto",
                candidate="unsafe",
                unsafe_auto=True,
                physical_frame_id="B1|B2",
            ),
            self._analysis_record(
                "review",
                source_sha256=shared_sha,
                role="challenge",
                decision="needs_review",
                candidate="safe",
                unsafe_auto=False,
                physical_frame_id="B1|B2",
            ),
        )
        summary = _summary(records, {"fixture": True})

        self.assertEqual(summary["unsafe_approved_auto_count"], 1)
        self.assertEqual(summary["safe_approved_auto_count"], 0)
        self.assertEqual(
            summary["review_candidate_conformance_counts"],
            {"safe": 1},
        )
        self.assertEqual(
            summary["count_variant_candidate_safety_mismatch_count"],
            1,
        )
        self.assertEqual(summary["physical_prior_validation"]["source_count"], 1)
        self.assertEqual(
            summary["physical_prior_validation"]["formats"]["135"][
                "directly_visible_frame_ratio_within_catalog_count"
            ],
            1,
        )

    def test_analysis_artifact_binds_comparator_and_reaggregates(self) -> None:
        identity = _analysis_identity()
        self.assertEqual(len(identity["comparator_source_manifest_sha256"]), 64)
        self.assertIn("comparator_paths_match_head", identity)
        record = self._analysis_record(
            "single",
            source_sha256="b" * 64,
            role="challenge",
            decision="needs_review",
            candidate="not_available",
            unsafe_auto=False,
            physical_frame_id="B1|B2",
        )
        record["frame_candidate_geometry_diagnostics"] = []
        summary = _summary((record,), identity)
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "gold_analysis_records.jsonl").write_text(
                json.dumps(record, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            (root / "gold_analysis_summary.json").write_text(
                json.dumps(summary) + "\n",
                encoding="utf-8",
            )
            self.assertEqual(
                validate_gold_analysis_artifacts(root),
                summary,
            )

    def test_zero_unsafe_auto_gate_requires_the_complete_cohort(self) -> None:
        error = io.StringIO()
        with redirect_stderr(error):
            result = gold_analysis_main(
                [
                    "--output-root",
                    "/unused",
                    "--sample-id",
                    "S001",
                    "--gate",
                    "zero-unsafe-auto",
                ]
            )
        self.assertEqual(result, 2)
        self.assertIn("complete cohort", error.getvalue())

    def test_zero_unsafe_auto_gate_blocks_dangerous_output(self) -> None:
        output = io.StringIO()
        summary = {"analysis_error_count": 0, "unsafe_approved_auto_count": 1}
        with (
            patch(
                "tools.regression.gold_analysis.run_gold_analysis",
                return_value=summary,
            ),
            redirect_stdout(output),
        ):
            result = gold_analysis_main(
                [
                    "--output-root",
                    "/unused",
                    "--gate",
                    "zero-unsafe-auto",
                ]
            )
        self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()
