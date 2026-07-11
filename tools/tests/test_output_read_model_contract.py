from __future__ import annotations

from pathlib import Path
import unittest
from dataclasses import fields

from tools.tests.physical_gate_support import (
    final_detection_fixture,
    transform_geometry_fixture,
)
from x5crop.detection.decision.model import FinalDetection
from x5crop.domain import ProcessResult
from x5crop.report.record import report_record_for_final_detection
from x5crop.report.restoration import final_detection_from_record
from x5crop.report.validation import current_report_record_errors
from tools.regression.compare import DEFAULT_FIELDS


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _record() -> dict:
    return report_record_for_final_detection(
        final_detection_fixture(),
        source="input.tif",
        profile={},
        output_files=[],
        review_copy=None,
        warnings=[],
        policy_id="test_policy",
        runtime_policy={"test": True},
        transform_geometry=transform_geometry_fixture(),
        analysis_reuse_signature={},
    )


class OutputReadModelContractTest(unittest.TestCase):
    def test_typed_read_model_serializes_every_typed_result_field(self) -> None:
        from x5crop.domain import MeasurementProvenance, PixelInterval
        from x5crop.domain import FrameDimensionEstimate
        from x5crop.report.read_models import typed_read_model

        value = FrameDimensionEstimate(
            width_px=PixelInterval.exact(100.0),
            height_px=PixelInterval.exact(80.0),
            source="test",
            provenance=MeasurementProvenance("frame_dimensions", "test", ()),
        )
        self.assertEqual(
            set(typed_read_model(value)),
            {field.name for field in fields(FrameDimensionEstimate)},
        )

    def test_final_detection_has_no_schema_restoration_wrapper(self) -> None:
        self.assertNotIn("restore", FinalDetection.__dict__)

    def test_fresh_record_is_current_schema_valid(self) -> None:
        self.assertEqual(current_report_record_errors(_record()), [])

    def test_current_schema_requires_every_canonical_section(self) -> None:
        for key in (
            "candidate_table",
            "selection",
            "candidate_gate",
            "decision_gate",
            "evidence_summary",
            "analysis_reuse_signature",
        ):
            record = _record()
            record.pop(key)
            self.assertTrue(current_report_record_errors(record), key)

    def test_unknown_final_reason_is_rejected(self) -> None:
        record = _record()
        record["status"] = "needs_review"
        record["decision_gate"]["passed"] = False
        record["final_review_reasons"] = ["unknown_physical_reason"]
        self.assertIn(
            "unknown_final_review_reason:unknown_physical_reason",
            current_report_record_errors(record),
        )

    def test_status_and_decision_gate_must_agree(self) -> None:
        record = _record()
        record["decision_gate"]["passed"] = False
        self.assertIn(
            "decision_gate_status_mismatch",
            current_report_record_errors(record),
        )

    def test_final_reasons_are_derived_from_decision_checks(self) -> None:
        record = _record()
        record["status"] = "needs_review"
        record["decision_gate"]["passed"] = False
        record["decision_gate"]["checks"][0]["state"] = "contradicted"
        record["decision_gate"]["checks"][0]["blocks"] = True
        record["final_review_reasons"] = ["selection_geometry_disagreement"]

        self.assertIn(
            "decision_gate_reason_mismatch",
            current_report_record_errors(record),
        )

    def test_cache_restoration_fields_are_required_by_current_schema(self) -> None:
        missing_provenance = _record()
        missing_provenance["separator_observations"][0]["provenance"].pop(
            "boundary_anchors"
        )
        self.assertIn(
            "separator_observation_invalid",
            current_report_record_errors(missing_provenance),
        )

        missing_transform = _record()
        missing_transform["diagnostics"]["transform_geometry"].pop("state")
        self.assertIn(
            "transform_geometry_incomplete",
            current_report_record_errors(missing_transform),
        )

    def test_report_has_no_generic_detail_or_legacy_reason_surface(self) -> None:
        record = _record()
        self.assertNotIn("detail", record)
        self.assertNotIn("review_reasons", record)
        self.assertIn("final_review_reasons", record)
        self.assertNotIn("outer_box", record)
        self.assertNotIn("frame_boxes", record)

    def test_schema_identity_is_descriptive_not_version_named(self) -> None:
        record = _record()
        self.assertEqual(record["schema_id"], "detection_report")
        self.assertEqual(record["schema_revision"], "frame_sequence_geometry")
        self.assertNotIn("v4", record["schema_revision"])

    def test_process_result_has_one_record_surface(self) -> None:
        self.assertEqual(set(ProcessResult.__dataclass_fields__), {"record"})

    def test_regression_tool_reads_only_current_canonical_geometry(self) -> None:
        self.assertEqual(
            DEFAULT_FIELDS,
            (
                "status",
                "confidence",
                "final_review_reasons",
                "output_geometry.crop_envelope",
                "output_geometry.frame_boxes",
                "separator_observations",
                "separator_assignments",
                "frame_boundaries",
            ),
        )

    def test_cache_reuse_validates_current_schema_before_use(self) -> None:
        source = (PROJECT_ROOT / "x5crop/runtime/analysis_reuse.py").read_text()
        self.assertIn("current_report_record_errors(record)", source)
        self.assertNotIn('"review_reasons"', source)

    def test_cache_reuse_restores_final_detection_for_shared_output_actions(self) -> None:
        record = _record()
        detection = final_detection_from_record(record)

        self.assertEqual(detection.status, record["status"])
        self.assertEqual(
            detection.final_review_reasons,
            tuple(record["final_review_reasons"]),
        )
        self.assertEqual(
            detection.output_geometry.frames,
            final_detection_fixture().output_geometry.frames,
        )

        source = (PROJECT_ROOT / "x5crop/runtime/analysis_reuse.py").read_text()
        self.assertIn("copy_for_review_if_needed", source)
        self.assertIn("write_crops_if_allowed", source)
        self.assertNotIn("from ..export.crops import", source)
        self.assertNotIn("from ..export.review import", source)

    def test_report_and_debug_do_not_recompute_decision(self) -> None:
        source = "\n".join(
            path.read_text()
            for root in (PROJECT_ROOT / "x5crop/report", PROJECT_ROOT / "x5crop/debug")
            for path in root.rglob("*.py")
        )
        self.assertNotIn("apply_decision_gate", source)
        self.assertNotIn("candidate_gate_assessment", source)


if __name__ == "__main__":
    unittest.main()
