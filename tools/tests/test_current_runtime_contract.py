from __future__ import annotations

from tools.tests.current_only_support import *
from tools.regression.diagnostic_cohort import (
    RECORD_SCHEMA,
    SUMMARY_SCHEMA,
    _source_geometry_authority_is_explicit,
    load_diagnostic_sources,
)
from tools.regression.report_validation import validate_output_footprint_authority


def _boundary_protections():
    return [
        {
            "role": role,
            "measurement_expansion_px": 0.0,
            "base_bleed_px": 0.0,
            "topology_protection_px": 0.0,
            "topology_relation_id": None,
            "local_boundary_residual_px": 0.0,
            "joint_expansion_px": 0.0,
        }
        for role in ("start", "end", "top", "bottom")
    ]


class CurrentRuntimeContractTest(unittest.TestCase):
    def test_diagnostic_cohort_schema_is_current_and_complete(self) -> None:
        self.assertEqual(RECORD_SCHEMA, "x5crop_diagnostic_record_v5")
        self.assertEqual(SUMMARY_SCHEMA, "x5crop_diagnostic_summary_v5")
        self.assertGreater(
            len(load_diagnostic_sources(verify_source_files=False)),
            0,
        )

    def test_diagnostic_validates_current_output_footprint_overflow_facts(self) -> None:
        output = {
            "mandatory_source_footprint": [
                [0.0, 10.0],
                [80.0, 10.0],
                [80.0, 90.0],
                [0.0, 90.0],
            ],
            "requested_source_footprint": [
                [-2.0, 10.0],
                [80.0, 10.0],
                [80.0, 90.0],
                [-2.0, 90.0],
            ],
            "required_source_footprint": [
                [0.0, 10.0],
                [80.0, 10.0],
                [80.0, 90.0],
                [0.0, 90.0],
            ],
            "sampling_authority_box": {
                "left": 0,
                "top": 0,
                "right": 100,
                "bottom": 100,
            },
            "boundary_protections": _boundary_protections(),
            "saturation_facts": [
                {
                    "authority_side": "left",
                    "kind": "source_boundary_optional_bleed",
                    "requested_overflow_px": 2.0,
                    "mandatory_overflow_px": 0.0,
                }
            ],
        }
        report = {"photo_geometry": {"lanes": [{"output_footprints": [output]}]}}
        self.assertTrue(_source_geometry_authority_is_explicit(report))
        output["saturation_facts"] = []
        self.assertFalse(_source_geometry_authority_is_explicit(report))

    def test_current_report_rejects_duplicate_footprint_authority_sides(self) -> None:
        output = {
            "mandatory_source_footprint": [
                [-2.0, 10.0],
                [80.0, 10.0],
                [80.0, 90.0],
                [-2.0, 90.0],
            ],
            "requested_source_footprint": [
                [-2.0, 10.0],
                [80.0, 10.0],
                [80.0, 90.0],
                [-2.0, 90.0],
            ],
            "required_source_footprint": [
                [-2.0, 10.0],
                [80.0, 10.0],
                [80.0, 90.0],
                [-2.0, 90.0],
            ],
            "sampling_authority_box": {
                "left": 0,
                "top": 0,
                "right": 100,
                "bottom": 100,
            },
            "boundary_protections": _boundary_protections(),
            "saturation_facts": [
                {
                    "authority_side": "left",
                    "kind": "lane_boundary_joint_protection",
                    "requested_overflow_px": 2.0,
                    "mandatory_overflow_px": 2.0,
                },
                {
                    "authority_side": "left",
                    "kind": "lane_boundary_joint_protection",
                    "requested_overflow_px": 2.0,
                    "mandatory_overflow_px": 2.0,
                },
            ],
        }

        with self.assertRaisesRegex(ValueError, "authority side"):
            validate_output_footprint_authority(output)

    def test_current_report_needs_only_the_safe_source_footprint(self) -> None:
        output = {
            "mandatory_source_footprint": [
                [10.0, 10.0],
                [80.0, 10.0],
                [80.0, 90.0],
                [10.0, 90.0],
            ],
            "requested_source_footprint": [
                [10.0, 10.0],
                [80.0, 10.0],
                [80.0, 90.0],
                [10.0, 90.0],
            ],
            "required_source_footprint": [
                [10.0, 10.0],
                [80.0, 10.0],
                [80.0, 90.0],
                [10.0, 90.0],
            ],
            "sampling_authority_box": {
                "left": 0,
                "top": 0,
                "right": 100,
                "bottom": 100,
            },
            "boundary_protections": _boundary_protections(),
            "saturation_facts": [],
        }

        validate_output_footprint_authority(output)

    def test_diagnostic_verifier_wraps_the_production_cli(self) -> None:
        diagnostic = (
            ROOT / "tools/regression/diagnostic_cohort.py"
        ).read_text(encoding="utf-8")
        verifier = (ROOT / "tools/verify").read_text(encoding="utf-8")
        self.assertIn('"tools.regression.development_run"', diagnostic)
        self.assertIn("subprocess.run(", diagnostic)
        self.assertIn(
            '"$PYTHON" -m tools.regression.diagnostic_cohort "$@"\n',
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
        self.assertIn("--debug-analysis", option_strings)
        self.assertIn("--deskew", option_strings)
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
        self.assertEqual(analysis_options.deskew_mode, DeskewMode.AUTO)
        disabled_options = options_from_args(
            parser.parse_args(
                ["input.tif", "--format", "135", "--deskew", "off"]
            )
        )
        self.assertEqual(disabled_options.deskew_mode, DeskewMode.OFF)
        self.assertEqual(DESKEW_CHOICES, ("off", "auto"))
        with mock.patch(
            "x5crop.runtime.bootstrap.iter_input_files",
            return_value=[Path("input.tif")],
        ):
            self.assertEqual(
                runtime_invocation_from_options(
                    disabled_options
                ).config.deskew_mode,
                DeskewMode.OFF,
            )
    def test_schema_and_two_gate_status_authority_are_current(self) -> None:
        self.assertEqual(REPORT_SCHEMA_ID, "x5crop_detection_report_v5")
        self.assertEqual(
            REPORT_SCHEMA_REVISION,
            "x5crop_v5_template_report_35",
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
                "failure",
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
        facts["complete_placement"] = TypedAssessment(
            EvidenceState.UNAVAILABLE,
            GateGap.COMPLETE_PLACEMENT_UNAVAILABLE,
        )
        facts["direct_use_budget"] = TypedAssessment(
            EvidenceState.UNAVAILABLE,
            GateGap.DIRECT_USE_BUDGET_UNAVAILABLE,
        )
        candidate = candidate_gate_assessment(facts)
        self.assertEqual(
            tuple(check.code for check in candidate.blocking_checks),
            ("complete_placement",),
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

        facts["complete_placement"] = TypedAssessment(EvidenceState.SUPPORTED, None)
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
