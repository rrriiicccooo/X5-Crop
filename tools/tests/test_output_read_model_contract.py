from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest

from x5crop.debug.status import debug_status_parts
from x5crop.detection.detail import candidate_signals_from_detail
from x5crop.domain import Box, Detection, ImageProfile
from x5crop.export.actions import copy_for_review_if_needed
from x5crop.policies.registry import get_detection_policy
from x5crop.report.result_builder import result_from_detection
from x5crop.report.schema import report_schema_for_detection


def _detection(detail: dict | None = None, review_reasons: list[str] | None = None) -> Detection:
    return Detection(
        film_format="135",
        layout="horizontal",
        strip_mode="full",
        count=1,
        outer=Box(10, 10, 90, 90),
        frames=[Box(10, 10, 90, 90)],
        gaps=[],
        confidence=0.99,
        review_reasons=list(review_reasons or []),
        detail=dict(detail or {}),
    )


class OutputReadModelContractTest(unittest.TestCase):
    def _policy(self):
        return get_detection_policy("135", "full")

    def test_report_schema_uses_decision_status_or_unknown(self) -> None:
        schema = report_schema_for_detection(_detection(), policy=self._policy())

        self.assertEqual(schema["status"], "unknown")
        self.assertEqual(schema["result"]["status"], "unknown")

        decided = _detection(
            {
                "decision_summary": {
                    "status": "needs_review",
                    "final_review_reasons": ["separator_evidence_insufficient"],
                }
            },
            ["separator_evidence_insufficient"],
        )
        decided_schema = report_schema_for_detection(decided, policy=self._policy())

        self.assertEqual(decided_schema["status"], "needs_review")
        self.assertEqual(decided_schema["result"]["status"], "needs_review")
        self.assertEqual(
            decided_schema["result"]["review_reasons"],
            ["separator_evidence_insufficient"],
        )

    def test_output_read_models_prefer_decision_summary_reasons(self) -> None:
        detection = _detection(
            {
                "decision_summary": {
                    "status": "needs_review",
                    "final_review_reasons": ["outer_content_mismatch"],
                }
            },
            ["candidate_level_stale_reason"],
        )

        status, detail, _color = debug_status_parts(detection, 0.85)

        self.assertEqual(status, "REVIEW")
        self.assertIn("outer_content_mismatch", detail)
        self.assertNotIn("candidate_level_stale_reason", detail)

        warnings: list[str] = []
        config = SimpleNamespace(
            confidence_threshold=0.85,
            copy_review_files=False,
        )
        copy_for_review_if_needed(
            Path("input.tif"),
            Path("out"),
            config,
            detection,
            "needs_review",
            warnings,
        )

        self.assertIn("outer_content_mismatch", warnings[0])
        self.assertNotIn("candidate_level_stale_reason", warnings[0])

        schema = report_schema_for_detection(detection, policy=self._policy())
        self.assertEqual(schema["result"]["review_reasons"], ["outer_content_mismatch"])

        profile = ImageProfile(
            shape=(100, 100),
            dtype="uint8",
            axes="YX",
            photometric="minisblack",
            compression=None,
            sample_format=None,
            bits_per_sample=8,
            samples_per_pixel=None,
            planar_config=None,
            resolution=None,
            resolution_unit=None,
            icc_profile=None,
        )
        result = result_from_detection(
            Path("input.tif"),
            detection,
            profile,
            "needs_review",
            [],
            None,
            [],
            self._policy(),
        )
        self.assertEqual(result.review_reasons, ["outer_content_mismatch"])

    def test_candidate_signals_do_not_fallback_to_final_review_reasons(self) -> None:
        detection = _detection(review_reasons=["outer_content_mismatch"])

        self.assertEqual(candidate_signals_from_detail(detection), [])

    def test_report_schema_uses_diagnostics_section_not_finalization(self) -> None:
        schema = report_schema_for_detection(_detection(), policy=self._policy())

        self.assertIn("diagnostics", schema)
        self.assertNotIn("finalization", schema)

    def test_report_schema_exposes_evidence_and_candidate_gate_sections(self) -> None:
        schema = report_schema_for_detection(
            _detection(
                {
                    "candidate_assessment": {
                        "candidate_gate": {
                            "passed": True,
                            "checks": [],
                            "blockers": [],
                            "diagnostics": [],
                            "confidence_caps": [],
                        }
                    },
                    "decision_summary": {
                        "decision_gate": {
                            "passed": True,
                            "checks": [],
                            "final_review_reasons": [],
                            "reason_inputs": [],
                            "confidence_caps": [],
                        }
                    },
                }
            ),
            policy=self._policy(),
        )

        self.assertIn("evidence", schema)
        self.assertIn("candidate_gate", schema)
        self.assertIn("decision_gate", schema)
        self.assertTrue(schema["candidate_gate"]["passed"])
        self.assertTrue(schema["decision_gate"]["passed"])
        self.assertNotIn("gates", schema)

    def test_debug_status_does_not_derive_pass_review_without_decision(self) -> None:
        status, detail, color = debug_status_parts(_detection(), 0.85)

        self.assertEqual(status, "UNKNOWN")
        self.assertIn("decision status unavailable", detail)
        self.assertEqual(color, (170, 170, 170))

    def test_debug_status_reads_decision_summary_when_available(self) -> None:
        status, detail, color = debug_status_parts(
            _detection({"decision_summary": {"status": "approved_auto"}}),
            0.85,
        )

        self.assertEqual(status, "PASS")
        self.assertIn("decision status approved_auto", detail)
        self.assertEqual(color, (40, 180, 90))

    def test_review_copy_warning_is_decision_neutral(self) -> None:
        warnings: list[str] = []
        config = SimpleNamespace(
            confidence_threshold=0.85,
            copy_review_files=False,
        )

        copy_for_review_if_needed(
            Path("input.tif"),
            Path("out"),
            config,
            _detection(review_reasons=["candidate_competition_close"]),
            "needs_review",
            warnings,
        )

        self.assertEqual(len(warnings), 1)
        self.assertIn("review required", warnings[0])
        self.assertIn("candidate_competition_close", warnings[0])
        self.assertNotIn("low confidence", warnings[0])


if __name__ == "__main__":
    unittest.main()
