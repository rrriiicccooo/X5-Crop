from __future__ import annotations

import ast
from inspect import signature
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from tools.tests.architecture_contracts import PROJECT_ROOT
from tools.tests.decision_contract_support import final_detection_fixture
from x5crop.debug.status import debug_status_parts
from x5crop.detection.detail import candidate_signals_from_detail
from x5crop.domain import FinalDetection, ImageProfile
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
    return final_detection_fixture(
        status=status,
        final_review_reasons=final_review_reasons,
        detail=detail,
    )


def _report_record(
    detection: FinalDetection,
    *,
    analysis_cache_metadata: dict | None = None,
) -> dict:
    return report_record_for_final_detection(
        detection,
        source="input.tif",
        profile={},
        output_files=[],
        review_copy=None,
        warnings=[],
        deskew_detail={"applied": False},
        analysis_cache_metadata=analysis_cache_metadata or {},
    )


class OutputReadModelContractTest(unittest.TestCase):
    def test_current_schema_validator_rejects_missing_or_empty_canonical_sections(self) -> None:
        from x5crop.report.validation import current_report_record_errors

        record = _report_record(_detection())
        record["schema_validation"] = []
        record["decision_geometry"] = {
            "outer_box": dict(record["outer_box"]),
            "frame_boxes": list(record["frame_boxes"]),
        }
        self.assertEqual(current_report_record_errors(record), [])

        for key in ("count_selection", "candidate_table", "policy", "evidence", "analysis_cache"):
            incomplete = dict(record)
            incomplete.pop(key)
            self.assertTrue(current_report_record_errors(incomplete), key)

        empty_geometry = dict(record)
        empty_geometry["decision_geometry"] = {}
        self.assertTrue(current_report_record_errors(empty_geometry))
    def test_report_has_one_candidate_and_final_geometry_projection(self) -> None:
        detection = _detection(
            {
                "candidate_competition": {
                    "selected_candidate": {"format_id": "135"},
                    "top_candidates": [
                        {
                            "rank": 1,
                            "selected": True,
                            "format_id": "135",
                            "candidate_assessment": {"candidate_gate": {"passed": True}},
                        }
                    ],
                },
                "output_geometry": {
                    "outer_box": {"left": 10, "top": 10, "right": 90, "bottom": 90},
                    "frame_boxes": [],
                },
            }
        )
        record = _report_record(detection)

        self.assertNotIn("selected_candidate", record)
        self.assertNotIn("output_geometry", record)
        self.assertNotIn("candidate_assessment", record["candidate_table"][0])
    def test_count_selection_is_a_current_schema_section(self) -> None:
        detection = _detection({"count_selection": {"marker": "count-selection"}})
        record = _report_record(detection)
        self.assertEqual(record["count_selection"], {"marker": "count-selection"})

        validation_source = (
            PROJECT_ROOT / "x5crop" / "report" / "validation.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"count_selection",', validation_source)

    def test_process_result_has_one_canonical_record_surface(self) -> None:
        from x5crop.domain import ProcessResult

        self.assertEqual(set(ProcessResult.__dataclass_fields__), {"record"})

    def test_report_record_has_no_duplicate_detail_projection(self) -> None:
        detection = _detection()
        record = _report_record(detection)

        self.assertNotIn("detail", record)

    def test_cache_export_uses_final_frame_read_model_not_detection_models(self) -> None:
        reuse_source = (
            PROJECT_ROOT / "x5crop" / "runtime" / "analysis_reuse.py"
        ).read_text(encoding="utf-8")
        crop_source = (
            PROJECT_ROOT / "x5crop" / "export" / "crops.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("candidate_geometry_from_record", reuse_source)
        self.assertNotIn("DetectionCandidate", reuse_source)
        self.assertNotIn("DetectionCandidate", crop_source)

    def test_debug_does_not_reconstruct_decision_signals(self) -> None:
        source = (
            PROJECT_ROOT / "x5crop" / "debug" / "panels.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("decision_signals.items()", source)
        self.assertNotIn("isinstance(value, bool) and value", source)

    def test_cache_rejects_incomplete_current_gap_records(self) -> None:
        from x5crop.utils import gap_from_dict

        record = {
            "format_id": "135",
            "layout": "horizontal",
            "strip_mode": "full",
            "count": 2,
            "outer_box": {"left": 0, "top": 0, "right": 100, "bottom": 60},
            "frame_boxes": [
                {"left": 0, "top": 0, "right": 50, "bottom": 60},
                {"left": 50, "top": 0, "right": 100, "bottom": 60},
            ],
            "gaps": [
                {
                    "index": 1,
                    "center": 50.0,
                    "start": None,
                    "end": None,
                    "lane_box": None,
                }
            ],
            "confidence": 0.9,
            "detail": {},
            "status": "approved_auto",
            "final_review_reasons": [],
        }

        with self.assertRaises(KeyError):
            gap_from_dict(record["gaps"][0])

    def test_script_version_identity_has_one_canonical_key(self) -> None:
        cache_source = (
            PROJECT_ROOT / "x5crop" / "runtime" / "analysis_reuse.py"
        ).read_text(encoding="utf-8")
        output_source = (
            PROJECT_ROOT / "x5crop" / "report" / "outputs.py"
        ).read_text(encoding="utf-8")

        self.assertIn('"script_version": VERSION', cache_source)
        self.assertNotIn('"version": VERSION', cache_source)
        self.assertIn('"script_version",', output_source)
        self.assertNotIn('"version",', output_source)

    def test_report_schema_has_no_duplicate_section_projections(self) -> None:
        self.assertNotIn("result", signature(report_record_for_final_detection).parameters)

        detection = _detection()
        schema = _report_record(detection)

        self.assertEqual(schema["schema_revision"], "canonical_final_record")
        for duplicate in (
            "version",
            "format",
            "result",
            "decision_policy_detail",
        ):
            self.assertNotIn(duplicate, schema)
        self.assertIn("script_version", schema)
        self.assertIn("policy", schema)
        self.assertIn("schema_validation", schema)
        self.assertNotIn("schema_validation", schema["diagnostics"])
        self.assertNotIn("scan_calibration", schema["diagnostics"])
        source = (
            PROJECT_ROOT / "x5crop" / "report" / "record.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn('"status": result.status', source)

    def test_summary_writer_requires_current_schema_fields(self) -> None:
        path = PROJECT_ROOT / "x5crop" / "report" / "outputs.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "append_summary_csv"
        )
        fallback_reads = [
            node.lineno
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
        ]

        self.assertEqual(fallback_reads, [])

    def test_regression_tools_read_current_report_schema_only(self) -> None:
        from tools.regression.compare import report_key

        detection = _detection()
        current = _report_record(detection)
        current["source"] = "current.tif"
        current["schema_validation"] = []
        current["decision_geometry"] = {
            "outer_box": dict(current["outer_box"]),
            "frame_boxes": list(current["frame_boxes"]),
        }
        self.assertEqual(report_key(current), "current.tif")
        with self.assertRaises(ValueError):
            report_key({"input_file": "superseded.tif"})

    def test_report_builder_does_not_overwrite_policy_input(self) -> None:
        path = PROJECT_ROOT / "x5crop" / "report" / "record.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "report_record_for_final_detection"
        )
        assignments = {
            target.id
            for node in ast.walk(function)
            if isinstance(node, (ast.Assign, ast.AnnAssign))
            for target in (
                node.targets if isinstance(node, ast.Assign) else (node.target,)
            )
            if isinstance(target, ast.Name)
        }
        self.assertNotIn("policy", assignments)

    def _policy(self):
        return get_detection_policy("135", "full")

    def test_report_schema_uses_canonical_final_detection_status(self) -> None:
        decided = _detection(
            {
                "decision_summary": {
                    "status": "needs_review",
                    "final_review_reasons": ["separator_evidence_incomplete"],
                }
            },
            ["separator_evidence_incomplete"],
        )
        decided_schema = _report_record(decided)

        self.assertEqual(decided_schema["status"], "needs_review")
        self.assertEqual(
            decided_schema["final_review_reasons"],
            ["separator_evidence_incomplete"],
        )

        approved = _report_record(_detection(status="approved_auto"))
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

        schema = _report_record(detection)
        self.assertEqual(schema["final_review_reasons"], ["outer_content_mismatch"])

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
            deskew_detail={"applied": False},
            analysis_cache_metadata={},
        )
        self.assertEqual(result.record["final_review_reasons"], ["outer_content_mismatch"])

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
            deskew_detail={"applied": False},
            analysis_cache_metadata={
                "script": "X5_Crop.py",
                "script_version": "test",
            },
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
        self.assertEqual(record["format_id"], "135")
        self.assertEqual(record["analysis_cache"]["script"], "X5_Crop.py")

    def test_candidate_signals_do_not_fallback_to_final_review_reasons(self) -> None:
        detection = _detection(final_review_reasons=["outer_content_mismatch"])

        self.assertEqual(candidate_signals_from_detail(detection), [])

    def test_cache_reuse_does_not_fallback_to_nested_report_projections(self) -> None:
        reuse_source = (
            PROJECT_ROOT / "x5crop" / "runtime" / "analysis_reuse.py"
        ).read_text(encoding="utf-8")
        result_source = (
            PROJECT_ROOT / "x5crop" / "report" / "result_builder.py"
        ).read_text(encoding="utf-8")
        for source in (reuse_source, result_source):
            self.assertNotIn('record.get("format")', source)
            self.assertNotIn('cached_record.get("format")', source)
            self.assertNotIn('get("layout") or format_detail.get("layout")', source)
            self.assertNotIn('get("count") or format_detail.get("count")', source)
        for term in (
            'record.get("frame_boxes", [])',
            'record.get("gaps", [])',
            'record.get("detail", {})',
            'cached_record.get("review_copy")',
            'deskew_detail.get("angle", 0.0)',
        ):
            self.assertNotIn(term, reuse_source)
        for term in (
            'cached_record.get("detail", {})',
            'cached_record.get("policy_id", "")',
            'output_detail.get("output_files", [])',
        ):
            self.assertNotIn(term, result_source)

    def test_analysis_cache_identity_changes_with_runtime_policy(self) -> None:
        from dataclasses import replace

        from x5crop.runtime.analysis_reuse import analysis_policy_fingerprint

        policy = self._policy()
        changed = replace(
            policy,
            decision=replace(
                policy.decision,
                outer_mismatch_cap=policy.decision.outer_mismatch_cap - 0.01,
            ),
        )
        self.assertNotEqual(
            analysis_policy_fingerprint(policy),
            analysis_policy_fingerprint(changed),
        )

    def test_policy_id_has_no_secondary_detail_fallback(self) -> None:
        source = (
            PROJECT_ROOT / "x5crop" / "detection" / "detail.py"
        ).read_text(encoding="utf-8")
        function = source[source.index("def policy_id_from_detail"):]
        self.assertNotIn("runtime_policy_detail", function)

    def test_result_builder_does_not_wrap_policy_identity_accessor(self) -> None:
        source = (
            PROJECT_ROOT / "x5crop" / "report" / "result_builder.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("def policy_id_for_detection", source)

    def test_process_result_does_not_duplicate_detection_geometry_or_version(self) -> None:
        from x5crop.domain import ProcessResult

        fields = ProcessResult.__dataclass_fields__
        for name in ("outer_box", "frame_boxes", "gaps", "version"):
            self.assertNotIn(name, fields)

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
            "schema_revision": "canonical_final_record",
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
            "policy_id": "decision:135:full",
            "analysis_cache": {"script": "X5_Crop.py"},
            "analysis_reuse": {"used": False},
            "output": {"output_files": [], "review_copy": None, "warnings": []},
        }

        result = result_from_cached_record(
            Path("input.tif"),
            cached_record,
            profile,
            ["reused"],
            output_files=[],
        )

        self.assertEqual(result.record["schema_id"], "detection_report")
        self.assertNotIn("report_schema", result.record)
        self.assertTrue(result.record["analysis_reuse"]["used"])
        self.assertEqual(result.record["output"]["warnings"], ["reused"])

    def test_report_schema_uses_diagnostics_section_not_finalization(self) -> None:
        detection = _detection()
        schema = _report_record(detection)

        self.assertIn("diagnostics", schema)
        self.assertNotIn("finalization", schema)

    def test_report_schema_exposes_evidence_and_candidate_gate_sections(self) -> None:
        schema = _report_record(
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
            )
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
