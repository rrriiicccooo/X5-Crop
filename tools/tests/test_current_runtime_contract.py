from __future__ import annotations

from tools.tests.current_only_support import *


class CurrentRuntimeContractTest(unittest.TestCase):
    def test_obsolete_detector_files_are_absent(self) -> None:
        forbidden_paths = (
            "x5crop/detection/physical",
            "x5crop/detection/evidence/photo_edges.py",
            "x5crop/detection/evidence/separator_sequence.py",
            "x5crop/detection/evidence/transform_geometry.py",
            "x5crop/detection/output_preparation.py",
            "x5crop/output/frame_bleed.py",
            "x5crop/image/separator_profile.py",
            "x5crop/configuration/grid.py",
            "x5crop/configuration/content.py",
            "x5crop/detection/grid",
            "x5crop/detection/evidence/separator.py",
            "x5crop/detection/protection.py",
            "x5crop/image/crop_pixels.py",
            "x5crop/image/evidence.py",
        )
        for relative in forbidden_paths:
            with self.subTest(path=relative):
                target = ROOT / relative
                if target.is_dir():
                    self.assertFalse(tuple(target.rglob("*.py")))
                else:
                    self.assertFalse(target.exists())

    def test_active_runtime_has_no_replaced_schema_or_placeholder_vocabulary(
        self,
    ) -> None:
        forbidden = (
            "source_core_grid_authority",
            "source_core_review",
            "resolved_frame_count",
            "allowed_partial_counts",
            "complete_strip_can_be_underfilled",
            "frame_grid_authority_unavailable",
            "source_content_measurement_unavailable",
            "no_independent_phase_authority",
            "not_applicable_frame_grid_unavailable",
            "not_applicable_core_unavailable",
            "FrameGridEvidence",
            "PhotoContainmentEvidence",
            "VisualDeskewOutcome",
            "write_crops_if_allowed",
            "copy_for_review_if_needed",
            "candidate_counts",
            "selected_count",
            "FrameCountDominanceAssessment",
            "DominanceRelation",
            "G_MAX",
            "automatic_count_unresolved",
            "bounded_safe_crop_grid",
            "bounded_ordered_grid_v4",
            "x5crop_run_manifest_v1",
            "x5crop_production_performance_v3",
            "x5crop_fixed_sample_profile_v1",
            "work_by_count_component",
            "lane_global_proposal_limit",
            "count_dominance",
            "SourceContentComponent",
            "ContentRowRunTable",
            "ContentConfiguration",
            "query_dp_memory",
            "unresolved_codes",
            "slot_ownership",
            "output_protection",
            "allow_grid_blank_identity",
            "grid_blank_no_photo_geometry",
            "format_physical_templates",
            "dp_states",
            "dp_transitions",
            "canonical_rank",
            "representative_cross_placement",
            "minimum_guard",
            "retained_placements",
            "placement_set_containment",
        )
        active_paths = tuple((ROOT / "x5crop").rglob("*.py")) + tuple(
            path
            for path in (ROOT / "tools").rglob("*.py")
            if "tests" not in path.relative_to(ROOT / "tools").parts
        )
        combined = "\n".join(
            path.read_text(encoding="utf-8") for path in active_paths
        )
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, combined)

    def test_diagnostic_verifier_wraps_the_production_cli(self) -> None:
        diagnostic = (
            ROOT / "tools/regression/diagnostic_cohort.py"
        ).read_text(encoding="utf-8")
        verifier = (ROOT / "tools/verify").read_text(encoding="utf-8")
        self.assertIn('"tools.regression.development_run"', diagnostic)
        self.assertIn("subprocess.run(", diagnostic)
        self.assertNotIn("runtime_invocation_from_options", diagnostic)
        self.assertNotIn("process_one", diagnostic)
        self.assertNotIn("diagnostics=True", diagnostic)
        self.assertNotIn('["transform_assessment"]', diagnostic)
        self.assertIn('"source_transform_assessment"', diagnostic)
        accuracy = (ROOT / "tools/regression/accuracy.py").read_text(
            encoding="utf-8"
        )
        gold_geometry = (
            ROOT / "tools/regression/gold_geometry.py"
        ).read_text(encoding="utf-8")
        accuracy_sources = accuracy + gold_geometry
        self.assertNotIn('["transform_assessment"]', accuracy_sources)
        self.assertIn('"source_transform_assessment"', accuracy_sources)
        self.assertIn(
            '"$PYTHON" -m tools.regression.diagnostic_cohort\n',
            verifier,
        )
        self.assertNotIn(
            "diagnostic_cohort --identity-only",
            verifier,
        )

    def test_only_current_debug_analysis_cli_and_runtime_surface_remain(
        self,
    ) -> None:
        parser = build_parser()
        help_text = parser.format_help()
        option_strings = {
            value
            for action in parser._actions
            for value in action.option_strings
        }
        self.assertNotIn("--debug", option_strings)
        self.assertIn("--debug-analysis", option_strings)
        self.assertNotIn("--preview", option_strings)
        self.assertNotIn("--debug-errors", option_strings)
        self.assertNotIn("--diagnostics", option_strings)
        self.assertNotIn("--overwrite", option_strings)
        self.assertNotIn("--allow-best-effort-output", option_strings)
        normalized_help = " ".join(help_text.split())
        self.assertIn(
            "three-panel JPG comparing detected and selected TOP/BOTTOM, "
            "detected and selected START/END, and final safe output envelopes",
            normalized_help,
        )
        self.assertIn(
            "analysis-only run writes no official TIFFs or review copies. "
            "A later normal run performs fresh detection",
            normalized_help,
        )
        analysis_options = options_from_args(
            parser.parse_args(
                ["input.tif", "--format", "135", "--debug-analysis"]
            )
        )
        self.assertTrue(analysis_options.debug_analysis)
        for runtime_type in (RuntimeOptions, RunConfig):
            with self.subTest(runtime_type=runtime_type.__name__):
                self.assertNotIn(
                    "debug",
                    {field.name for field in fields(runtime_type)},
                )
                self.assertNotIn(
                    "preview",
                    {field.name for field in fields(runtime_type)},
                )
        with (
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit),
        ):
            parser.parse_args(
                ["input.tif", "--format", "135", "--debug"]
            )
        for removed in (
            "--diagnostics",
            "--overwrite",
            "--debug-errors",
            "--preview",
        ):
            with (
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit),
            ):
                parser.parse_args(["input.tif", "--format", "135", removed])

    def test_schema_and_two_gate_status_authority_are_current(self) -> None:
        self.assertEqual(REPORT_SCHEMA_ID, "x5crop_detection_report_v5")
        self.assertEqual(
            REPORT_SCHEMA_REVISION,
            "x5crop_v5_lightweight_report_1",
        )
        candidate = candidate_gate_assessment(
            {
                code: TypedAssessment(EvidenceState.SUPPORTED, None)
                for code in CANDIDATE_GATE_CHECK_CODES
            }
        )
        self.assertTrue(
            all(check.final_review_reason is None for check in candidate.checks)
        )
        self.assertEqual(
            tuple(gate_check_read_model(candidate.checks[0])),
            (
                "code",
                "stage",
                "state",
                "gap",
                "final_review_reason",
                "evaluated",
                "blocks",
            ),
        )
        decision = apply_decision_gate(candidate)
        self.assertEqual(decision.status, "approved_auto")
        self.assertEqual(decision.final_review_reasons, ())

    def test_decision_reasons_distinguish_unavailable_from_exceeded(self) -> None:
        facts = {
            code: TypedAssessment(EvidenceState.SUPPORTED, None)
            for code in CANDIDATE_GATE_CHECK_CODES
        }
        facts["complete_chain"] = TypedAssessment(
            EvidenceState.UNAVAILABLE,
            GateGap.COMPLETE_CHAIN_UNAVAILABLE,
        )
        facts["direct_use_budget"] = TypedAssessment(
            EvidenceState.UNAVAILABLE,
            GateGap.DIRECT_USE_BUDGET_UNAVAILABLE,
        )
        candidate = candidate_gate_assessment(facts)
        self.assertEqual(
            tuple(check.code for check in candidate.blocking_checks),
            ("complete_chain",),
        )
        self.assertFalse(
            next(
                check
                for check in candidate.checks
                if check.code == "direct_use_budget"
            ).evaluated
        )
        decision = apply_decision_gate(candidate)
        self.assertEqual(decision.final_review_reasons, ("no_legal_placement",))

        facts["complete_chain"] = TypedAssessment(EvidenceState.SUPPORTED, None)
        facts["direct_use_budget"] = TypedAssessment(
            EvidenceState.CONTRADICTED,
            GateGap.DIRECT_USE_BUDGET_EXCEEDED,
        )
        decision = apply_decision_gate(candidate_gate_assessment(facts))
        self.assertEqual(
            decision.final_review_reasons,
            ("direct_use_budget_exceeded",),
        )


if __name__ == "__main__":
    unittest.main()
