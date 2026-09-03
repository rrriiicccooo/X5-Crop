from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
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
    _axis_guard_calibration,
    _enclosing_support_aperture_center_calibration,
    _fit_mixed_axis_guard,
    _nominal_pitch_calibration,
    _round_outward,
    _round_outward_lower,
    _source_variation_summary,
    _summary,
    line_axis_position,
    main as gold_analysis_main,
    optimization_stage_index,
    sequence_boundary_diagnostics,
    validate_gold_analysis_artifacts,
)
from x5crop.formats import (
    ENCLOSING_SUPPORT_APERTURE_CALIBRATION_SPEC,
    format_spec,
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
        proposal: str | None = None,
    ) -> dict[str, object]:
        proposal = candidate if proposal is None else proposal
        contract_passed = not unsafe_auto and not (
            role == "nominal" and decision == "needs_review"
        )
        frame_unsafe = candidate == "unsafe"
        proposal_frame_unsafe = proposal == "unsafe"
        source_placement_state = (
            "unavailable" if candidate == "not_available" else "supported"
        )
        runtime_pipeline_outcome = (
            "proposal_unavailable"
            if proposal == "not_available"
            else "proposal_generated_eligibility_withheld"
            if source_placement_state != "supported"
            else "eligible_candidate_needs_review"
            if decision == "needs_review"
            else "approved_auto"
        )
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
            "release_detection_gate_passed": contract_passed,
            "release_detection_gate_failure": (
                None if contract_passed else "synthetic contract failure"
            ),
            "proposal_generation_state": (
                "unavailable" if proposal == "not_available" else "generated"
            ),
            "proposal_generation_failure_gap": (
                "complete_placement_unavailable"
                if proposal == "not_available"
                else None
            ),
            "proposal_geometry_conformance": proposal,
            "proposal_geometry_failure": (
                "synthetic proposal failure" if proposal_frame_unsafe else None
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
            "runtime_pipeline_outcome": runtime_pipeline_outcome,
            "source_placement_state": source_placement_state,
            "phase_status": "resolved",
            "phase_failure_kind": None,
            "global_lattice_authority_state": "supported",
            "global_lattice_authority_basis": "direct_role_system",
            "source_frame_width_authority_state": "supported",
            "source_frame_width_authority_placement_scope": (
                "resolved_placement"
            ),
            "source_frame_width_authority_basis": (
                "independent_complete_frames"
            ),
            "source_frame_width_authority_failure_kind": None,
            "frame_width_inference_state": None,
            "frame_width_inference_authority_basis": None,
            "frame_width_inference_failure_kind": None,
            "coarse_enclosing_resolution_state": "supported",
            "coarse_enclosing_resolution_failure_kind": None,
            "coarse_enclosing_candidate_measurement_bases": [
                "sharp_transition"
            ],
            "coarse_enclosing_selected_measurement_basis": (
                "sharp_transition"
            ),
            "lattice_parameter_fit_basis": "bounded_direct_least_squares",
            "calibrated_nominal_grid_evidence_state": None,
            "calibrated_nominal_grid_evidence_failure_kind": None,
            "calibrated_nominal_grid_authority_state": "not_applicable",
            "calibrated_nominal_grid_authority_failure_kind": None,
            "enclosing_support_aperture_authority_state": "not_applicable",
            "enclosing_support_aperture_authority_failure_kind": None,
            "enclosing_support_aperture_center_observation": None,
            "candidate_nominal_grid_solve_count": 0,
            "candidate_nominal_grid_solve_success_count": 0,
            "selected_direct_role_projection_evaluation_count": 0,
            "selected_direct_role_projection_binding_count": 0,
            "selected_nominal_grid_solve_count": 0,
            "selected_nominal_grid_solve_success_count": 0,
            "cross_status": "resolved",
            "cross_failure_kind": None,
            "cross_failure_reason": None,
            "cross_longitudinal_projection_authority_state": "supported",
            "cross_longitudinal_projection_authority_basis": (
                "source_spanning_continuous"
            ),
            "cross_longitudinal_projection_failure_kind": None,
            "placement_failure_gap": None,
            "selected_cross_boundary_use": "aperture_pair",
            "duration_seconds": 1.0,
            "boundary_diagnostics": [],
            "frame_proposal_geometry_diagnostics": [
                {
                    "frame_index": 1,
                    "physical_frame_id": physical_frame_id,
                    "inward_failure_sides": (
                        ["sequence_start"] if proposal_frame_unsafe else []
                    ),
                    "outward_budget_failure_sides": [],
                }
            ] if proposal != "not_available" else [],
            "frame_candidate_geometry_diagnostics": [
                {
                    "frame_index": 1,
                    "physical_frame_id": physical_frame_id,
                    "inward_failure_sides": (
                        ["sequence_start"] if frame_unsafe else []
                    ),
                    "outward_budget_failure_sides": [],
                }
            ] if candidate != "not_available" else [],
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
                "dimension_estimate_basis": (
                    "gold_native_geometry_divided_by_selected_nominal_holder_axis_scale"
                ),
                "sequence_scale_px_per_nominal_mm": 100.0,
                "cross_scale_px_per_nominal_mm": 100.0,
                "frame_ratio_measurements": [1.5],
                "holder_normalized_frame_width_estimates_mm": [36.0],
                "holder_normalized_frame_height_estimates_mm": [24.0],
                "frame_width_prior_containment": [True],
                "frame_height_prior_containment": [True],
                "excluded_frame_count": 0,
                "holder_normalized_separator_gap_estimates_mm": [2.0],
                "separator_gap_prior_containment": [True],
                "holder_normalized_pitch_estimates_mm": [38.0],
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
        self.assertTrue(summary["development_diagnostic_complete"])
        self.assertFalse(summary["release_analysis_identity_ready"])
        self.assertFalse(summary["release_detection_gate_ready"])
        self.assertEqual(
            summary["result_disposition"],
            "development_only_not_release_ready",
        )
        self.assertEqual(
            summary["unsafe_approved_auto_diagnostics"][0]["sample_id"],
            "auto",
        )
        self.assertEqual(
            summary["unsafe_approved_auto_diagnostics"][0][
                "unsafe_frame_diagnostics"
            ][0]["inward_failure_sides"],
            ["sequence_start"],
        )
        self.assertEqual(summary["safe_approved_auto_count"], 0)
        self.assertEqual(
            summary["proposal_geometry_conformance_counts"],
            {"safe": 1, "unsafe": 1},
        )
        self.assertEqual(
            summary["review_candidate_conformance_counts"],
            {"safe": 1},
        )
        self.assertEqual(
            summary["proposal_candidate_conformance_matrix"],
            {"safe": {"safe": 1}, "unsafe": {"unsafe": 1}},
        )
        self.assertEqual(
            summary["count_variant_candidate_safety_mismatch_count"],
            1,
        )

    def test_summary_exposes_a_safe_proposal_withheld_by_eligibility(self) -> None:
        record = self._analysis_record(
            "withheld",
            source_sha256="c" * 64,
            role="nominal",
            decision="needs_review",
            proposal="safe",
            candidate="not_available",
            unsafe_auto=False,
            physical_frame_id="B1|B2",
        )

        summary = _summary((record,), {"fixture": True})

        self.assertEqual(
            summary["runtime_pipeline_outcome_counts"],
            {"proposal_generated_eligibility_withheld": 1},
        )
        self.assertEqual(
            summary["proposal_candidate_conformance_matrix"],
            {"safe": {"not_available": 1}},
        )
        self.assertEqual(
            summary["proposal_generation_failure_gap_counts"],
            {"None": 1},
        )
        self.assertEqual(summary["unsafe_approved_auto_diagnostics"], [])
        self.assertEqual(summary["physical_prior_validation"]["source_count"], 1)
        self.assertEqual(
            summary["physical_prior_validation"]["formats"]["135"][
                "aperture_aspect_ratio_calibration"
            ]["eligible_source_count"],
            1,
        )
        self.assertEqual(
            summary["physical_prior_validation"]["formats"]["135"][
                "holder_normalized_frame_width_mm"
            ]["measurement_count"],
            1,
        )

    def test_release_readiness_requires_current_calibration_provenance(
        self,
    ) -> None:
        record = self._analysis_record(
            "safe-auto",
            source_sha256="d" * 64,
            role="nominal",
            decision="approved_auto",
            candidate="safe",
            unsafe_auto=False,
            physical_frame_id="B1|B2",
        )

        summary = _summary((record,), {"fixture": True})

        self.assertFalse(summary["physical_prior_calibration_ready"])
        self.assertTrue(summary["physical_prior_calibration_failures"])
        self.assertFalse(summary["release_detection_gate_ready"])

    def test_physical_summary_separates_within_and_between_source_variation(
        self,
    ) -> None:
        summary = _source_variation_summary(
            (
                {"values": [35.9, 36.0, 36.1]},
                {"values": [36.8, 36.9, 37.0]},
            ),
            "values",
        )

        self.assertEqual(summary["measurement_count"], 6)
        self.assertEqual(summary["source_count"], 2)
        self.assertEqual(summary["multi_measurement_source_count"], 2)
        self.assertGreater(
            summary["between_source_relative_std"],
            summary["pooled_within_source_relative_rms"],
        )
        self.assertGreater(summary["between_to_within_ratio"], 1.0)

    def test_mixed_axis_guard_fit_keeps_one_shared_physical_formula(self) -> None:
        floor, ratio, _score = _fit_mixed_axis_guard(
            (
                (18.0, 0.9213557897170552),
                (36.0, 0.6425946864386389),
                (56.0, 1.2681724501607903),
                (70.0, 1.677706763109518),
            )
        )

        self.assertAlmostEqual(floor, 0.9213557897170552)
        self.assertAlmostEqual(ratio, 0.023967239472993115)
        self.assertAlmostEqual(_round_outward(floor, 0.05), 0.95)
        self.assertAlmostEqual(_round_outward(ratio, 0.001), 0.024)

    def test_axis_guard_uses_source_centers_and_keeps_single_frame_sources(
        self,
    ) -> None:
        calibration = _axis_guard_calibration(
            (
                {
                    "sample_id": "half-single",
                    "format_id": "half",
                    "holder_normalized_frame_width_estimates_mm": [17.0],
                },
                {
                    "sample_id": "135-multiple",
                    "format_id": "135",
                    "holder_normalized_frame_width_estimates_mm": [36.4, 36.6],
                },
            ),
            axis="width",
        )

        self.assertEqual(calibration["source_count"], 2)
        self.assertEqual(calibration["frame_count"], 3)
        groups = {
            item["nominal_axis_mm"]: item
            for item in calibration["nominal_groups"]
        }
        self.assertEqual(
            groups[18.0]["q95_source_center_deviation_mm"],
            1.0,
        )
        self.assertAlmostEqual(
            groups[36.0]["q95_source_center_deviation_mm"],
            0.5,
        )

    def test_nominal_pitch_calibration_is_source_level_and_reproducible(
        self,
    ) -> None:
        configured = format_spec("135").nominal_pitch_calibration
        assert configured is not None
        centers = [37.9] * 44
        centers[0] = 37.69292831335652
        centers[-1] = 38.18633241598057
        diagnostics = tuple(
            {
                "sample_id": f"S{index:03d}",
                "cohort_role": "nominal",
                "holder_normalized_pitch_estimates_mm": [
                    center
                ]
                * (5 if index <= 22 else 4),
            }
            for index, center in enumerate(centers, start=1)
        ) + (
            {
                "sample_id": "challenge",
                "cohort_role": "challenge",
                "holder_normalized_pitch_estimates_mm": [20.0, 60.0],
            },
        )

        calibration = _nominal_pitch_calibration(
            "135",
            diagnostics,
            cohort_sha256=configured.development_gold_cohort_sha256,
        )

        self.assertEqual(calibration["eligible_source_count"], 44)
        self.assertEqual(calibration["eligible_measurement_count"], 198)
        self.assertEqual(
            calibration["derived_outward_interval_mm"],
            {"minimum": 37.65, "maximum": 38.2},
        )
        self.assertTrue(calibration["configured_matches_calibration"])

    def test_enclosing_support_center_calibration_is_source_bound(
        self,
    ) -> None:
        configured = ENCLOSING_SUPPORT_APERTURE_CALIBRATION_SPEC
        ratios = [-0.008894822743034225, 0.006143972364182875] + [
            0.0
        ] * 18
        records = tuple(
            {
                "sample_id": f"S{index:03d}",
                "source_sha256": f"{index:064x}",
                "format_id": "135",
                "count": 6,
                "enclosing_support_aperture_center_observation": {
                    "eligibility_revision": configured.eligibility_revision,
                    "center_offset_ratio": ratio,
                },
            }
            for index, ratio in enumerate(ratios, start=1)
        )

        unregistered = _enclosing_support_aperture_center_calibration(
            records,
            cohort_sha256=configured.development_gold_cohort_sha256,
        )
        current = replace(
            configured,
            development_observation_set_sha256=unregistered[
                "actual_observation_set_sha256"
            ],
            development_source_count=20,
            development_task_count=20,
        )
        with patch(
            "tools.regression.gold_analysis."
            "ENCLOSING_SUPPORT_APERTURE_CALIBRATION_SPEC",
            current,
        ):
            calibration = _enclosing_support_aperture_center_calibration(
                records,
                cohort_sha256=current.development_gold_cohort_sha256,
            )

        self.assertAlmostEqual(
            _round_outward_lower(ratios[0], 0.001),
            -0.009,
        )
        self.assertEqual(calibration["eligible_source_count"], 20)
        self.assertEqual(calibration["eligible_task_count"], 20)
        self.assertEqual(
            calibration["actual_observation_set_sha256"],
            calibration["registered_observation_set_sha256"],
        )
        self.assertAlmostEqual(
            calibration["derived_outward_interval"]["minimum"],
            -0.009,
        )
        self.assertAlmostEqual(
            calibration["derived_outward_interval"]["maximum"],
            0.007,
        )
        self.assertTrue(calibration["configured_matches_calibration"])

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

    def test_release_gate_requires_the_complete_cohort(self) -> None:
        error = io.StringIO()
        with redirect_stderr(error):
            result = gold_analysis_main(
                [
                    "--output-root",
                    "/unused",
                    "--sample-id",
                    "S001",
                    "--gate",
                    "release",
                ]
            )
        self.assertEqual(result, 2)
        self.assertIn("complete cohort", error.getvalue())

    def test_release_gate_blocks_an_unready_development_result(self) -> None:
        output = io.StringIO()
        error = io.StringIO()
        summary = {
            "analysis_error_count": 0,
            "release_detection_gate_ready": False,
            "unsafe_approved_auto_count": 1,
        }
        with (
            patch(
                "tools.regression.gold_analysis.run_gold_analysis",
                return_value=summary,
            ),
            redirect_stdout(output),
            redirect_stderr(error),
        ):
            result = gold_analysis_main(
                [
                    "--output-root",
                    "/unused",
                    "--gate",
                    "release",
                ]
            )
        self.assertEqual(result, 1)
        self.assertIn("DEVELOPMENT ONLY", error.getvalue())
        self.assertIn("NOT RELEASE READY", error.getvalue())
        self.assertIn("not valid for formal delivery", error.getvalue())
        self.assertIn("known unsafe approved_auto=1", error.getvalue())

    def test_release_gate_can_use_a_temporary_receipt_directory(self) -> None:
        output = io.StringIO()
        summary = {
            "analysis_error_count": 0,
            "release_detection_gate_ready": True,
        }
        with (
            patch(
                "tools.regression.gold_analysis.run_gold_analysis",
                return_value=summary,
            ) as run,
            redirect_stdout(output),
        ):
            result = gold_analysis_main(["--gate", "release"])

        self.assertEqual(result, 0)
        receipt_root = run.call_args.args[0]
        self.assertIsInstance(receipt_root, Path)
        self.assertFalse(receipt_root.exists())

    def test_report_mode_keeps_an_unready_development_result_observable(
        self,
    ) -> None:
        output = io.StringIO()
        error = io.StringIO()
        summary = {
            "analysis_error_count": 0,
            "release_detection_gate_ready": False,
            "unsafe_approved_auto_count": 3,
        }
        with (
            patch(
                "tools.regression.gold_analysis.run_gold_analysis",
                return_value=summary,
            ),
            redirect_stdout(output),
            redirect_stderr(error),
        ):
            result = gold_analysis_main(
                [
                    "--output-root",
                    "/unused",
                    "--gate",
                    "report",
                ]
            )
        self.assertEqual(result, 0)
        self.assertIn("DEVELOPMENT ONLY", error.getvalue())
        self.assertIn("NOT RELEASE READY", error.getvalue())
        self.assertIn("not valid for formal delivery", error.getvalue())
        self.assertIn("known unsafe approved_auto=3", error.getvalue())


if __name__ == "__main__":
    unittest.main()
