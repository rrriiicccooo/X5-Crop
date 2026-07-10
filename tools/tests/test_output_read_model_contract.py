from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from x5crop.debug.status import debug_status_parts
from x5crop.detection.detail import candidate_signals_from_detail
from x5crop.domain import Box, FinalDetection, ImageProfile
from x5crop.export.actions import copy_for_review_if_needed
from x5crop.report.outputs import append_report_jsonl
from x5crop.policies.registry import get_detection_policy
from x5crop.report.result_builder import result_from_cached_record, result_from_detection
from x5crop.report.record import report_record_for_final_detection


def _detection(
    detail: dict | None = None,
    final_review_reasons: list[str] | None = None,
    *,
    status: str = "needs_review",
) -> FinalDetection:
    return FinalDetection(
        film_format="135",
        layout="horizontal",
        strip_mode="full",
        count=1,
        outer=Box(10, 10, 90, 90),
        frames=[Box(10, 10, 90, 90)],
        gaps=[],
        confidence=0.99,
        detail=dict(detail or {}),
        status=status,
        final_review_reasons=list(final_review_reasons or []),
    )


class OutputReadModelContractTest(unittest.TestCase):
    def _policy(self):
        return get_detection_policy("135", "full")

    def test_report_schema_uses_canonical_final_detection_status(self) -> None:
        decided = _detection(
            {
                "decision_summary": {
                    "status": "needs_review",
                    "final_review_reasons": ["separator_evidence_insufficient"],
                }
            },
            ["separator_evidence_insufficient"],
        )
        decided_schema = report_record_for_final_detection(decided, policy=self._policy())

        self.assertEqual(decided_schema["status"], "needs_review")
        self.assertEqual(decided_schema["result"]["status"], "needs_review")
        self.assertEqual(
            decided_schema["result"]["final_review_reasons"],
            ["separator_evidence_insufficient"],
        )

        approved = report_record_for_final_detection(
            _detection(status="approved_auto"),
            policy=self._policy(),
        )
        self.assertEqual(approved["status"], "approved_auto")

    def test_output_read_models_use_canonical_final_reasons(self) -> None:
        detection = _detection(
            {
                "decision_summary": {
                    "status": "needs_review",
                    "final_review_reasons": ["candidate_level_stale_reason"],
                }
            },
            ["outer_content_mismatch"],
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
            warnings,
        )

        self.assertIn("outer_content_mismatch", warnings[0])
        self.assertNotIn("candidate_level_stale_reason", warnings[0])

        schema = report_record_for_final_detection(detection, policy=self._policy())
        self.assertEqual(schema["result"]["final_review_reasons"], ["outer_content_mismatch"])

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
            [],
            None,
            [],
            self._policy(),
        )
        self.assertEqual(result.final_review_reasons, ["outer_content_mismatch"])

    def test_report_jsonl_writes_current_schema_without_legacy_wrapper(self) -> None:
        detection = _detection(
            {
                "decision_summary": {
                    "status": "needs_review",
                    "final_review_reasons": ["outer_content_mismatch"],
                }
            },
            ["outer_content_mismatch"],
        )
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
            [],
            None,
            [],
            self._policy(),
            detail_extra={"analysis_cache": {"script": "X5_Crop.py", "version": "test"}},
        )

        with TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "x5_crop_report.jsonl"
            append_report_jsonl(report_path, result)
            record = json.loads(report_path.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(record["schema_id"], "detection_report")
        self.assertIn("candidate_gate", record)
        self.assertIn("decision_gate", record)
        self.assertIn("final_review_reasons", record)
        self.assertNotIn("report_schema", record)
        self.assertNotIn("film_format", record)
        self.assertEqual(record["format_id"], "135")
        self.assertEqual(record["detail"]["analysis_cache"]["script"], "X5_Crop.py")

    def test_candidate_signals_do_not_fallback_to_final_review_reasons(self) -> None:
        detection = _detection(final_review_reasons=["outer_content_mismatch"])

        self.assertEqual(candidate_signals_from_detail(detection), [])

    def test_cached_record_result_keeps_current_schema_and_marks_reuse(self) -> None:
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
        cached_record = {
            "schema_id": "detection_report",
            "schema_revision": "physical_decision_output_bleed",
            "source": "input.tif",
            "status": "needs_review",
            "confidence": 0.84,
            "format_id": "135",
            "strip_mode": "full",
            "layout": "horizontal",
            "count": 6,
            "final_review_reasons": ["candidate_competition_close"],
            "outer_box": {"left": 0, "top": 0, "right": 10, "bottom": 10},
            "frame_boxes": [],
            "gaps": [],
            "detail": {"analysis_cache": {"script": "X5_Crop.py"}},
            "output": {"output_files": [], "review_copy": None, "warnings": []},
        }

        result = result_from_cached_record(Path("input.tif"), cached_record, profile, ["reused"])

        self.assertEqual(result.report_record["schema_id"], "detection_report")
        self.assertNotIn("report_schema", result.report_record)
        self.assertTrue(result.report_record["detail"]["reused_analysis"])
        self.assertEqual(result.report_record["output"]["warnings"], ["reused"])

    def test_report_schema_uses_diagnostics_section_not_finalization(self) -> None:
        schema = report_record_for_final_detection(_detection(), policy=self._policy())

        self.assertIn("diagnostics", schema)
        self.assertNotIn("finalization", schema)

    def test_report_schema_exposes_evidence_and_candidate_gate_sections(self) -> None:
        schema = report_record_for_final_detection(
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

    def test_debug_status_reads_canonical_final_status(self) -> None:
        status, detail, color = debug_status_parts(
            _detection(
                {"decision_summary": {"status": "stale_detail_value"}},
                status="approved_auto",
            ),
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
            _detection(
                {
                    "decision_summary": {
                        "final_review_reasons": ["candidate_competition_close"],
                    },
                },
                ["candidate_competition_close"],
            ),
            warnings,
        )

        self.assertEqual(len(warnings), 1)
        self.assertIn("review required", warnings[0])
        self.assertIn("candidate_competition_close", warnings[0])
        self.assertNotIn("low confidence", warnings[0])


if __name__ == "__main__":
    unittest.main()
