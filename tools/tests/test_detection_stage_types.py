from __future__ import annotations

from dataclasses import fields
from pathlib import Path
import inspect
import unittest

from x5crop.debug.status import debug_status_parts
from x5crop.detection.final import finalize
from x5crop.detection.pipeline import CandidatePipelineResult
from x5crop.domain import DetectionCandidate, FinalDetection
from x5crop.export.actions import copy_for_review_if_needed, write_crops_if_allowed
from x5crop.report.result_builder import result_from_detection
from x5crop.report.record import report_record_for_final_detection


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class DetectionStageTypeContractTests(unittest.TestCase):
    def test_candidate_and_final_fields_are_separate(self) -> None:
        candidate_fields = {field.name for field in fields(DetectionCandidate)}
        final_fields = {field.name for field in fields(FinalDetection)}

        self.assertNotIn("status", candidate_fields)
        self.assertNotIn("final_review_reasons", candidate_fields)
        self.assertIn("status", final_fields)
        self.assertIn("final_review_reasons", final_fields)

    def test_pipeline_result_names_its_candidate_surface(self) -> None:
        field_names = [field.name for field in fields(CandidatePipelineResult)]
        self.assertEqual(field_names, ["candidate", "policy"])

    def test_output_surfaces_require_final_detection(self) -> None:
        functions = (
            debug_status_parts,
            copy_for_review_if_needed,
            write_crops_if_allowed,
            result_from_detection,
            report_record_for_final_detection,
            finalize.finalize_detection,
        )
        for function in functions:
            with self.subTest(function=function.__name__):
                annotation = inspect.signature(function).parameters["detection"].annotation
                self.assertEqual(annotation, "FinalDetection")

    def test_candidate_layers_do_not_import_final_detection(self) -> None:
        checked_roots = (
            PROJECT_ROOT / "x5crop" / "detection" / "candidate",
            PROJECT_ROOT / "x5crop" / "detection" / "physical",
            PROJECT_ROOT / "x5crop" / "detection" / "guidance",
            PROJECT_ROOT / "x5crop" / "detection" / "evidence",
        )
        offenders = [
            str(path.relative_to(PROJECT_ROOT))
            for root in checked_roots
            for path in root.rglob("*.py")
            if "FinalDetection" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(offenders, [])

    def test_old_decision_and_finalization_wrappers_are_absent(self) -> None:
        self.assertFalse(
            (PROJECT_ROOT / "x5crop" / "detection" / "decision" / "final_decision.py").exists()
        )
        finalization_text = (
            PROJECT_ROOT / "x5crop" / "detection" / "final" / "finalize.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("DetectionFinalizationResult", finalization_text)


if __name__ == "__main__":
    unittest.main()
