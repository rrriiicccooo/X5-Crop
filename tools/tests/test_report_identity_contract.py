from __future__ import annotations

import unittest

from tools.tests.physical_gate_support import (
    frame_bleed_fixture,
    selection_fixture,
    transform_geometry_fixture,
    unavailable_calibration_fixture,
)
from tools.tests.test_output_read_model_contract import (
    _analysis_reuse_signature,
    _profile,
    _record,
)
from x5crop.configuration.registry import get_detection_configuration
from x5crop.detection.decision.decision_gate import apply_decision_gate
from x5crop.detection.final.finalize import (
    finalization_plan_for_selection,
    finalize_detection,
)
from x5crop.domain import EvidenceState
from x5crop.report.configuration import detection_configuration_read_model
from x5crop.report.read_models import typed_read_model
from x5crop.report.record import report_record_for_final_detection
from x5crop.report.validation import current_report_record_errors
from x5crop.domain import WorkspaceExtent


class ReportIdentityContractTest(unittest.TestCase):
    def test_deskew_workspace_extent_owns_output_identity(self) -> None:
        selection = selection_fixture()
        frame_bleed = frame_bleed_fixture()
        transform = transform_geometry_fixture(EvidenceState.SUPPORTED)
        final_detection = finalize_detection(
            apply_decision_gate(selection, frame_bleed, transform),
            frame_bleed,
            finalization_plan_for_selection(
                selection,
                workspace_extent=WorkspaceExtent(220, 120),
            ),
        )
        record = report_record_for_final_detection(
            final_detection,
            selection,
            source="input.tif",
            profile=typed_read_model(_profile()),
            workspace_extent=WorkspaceExtent(220, 120),
            output_files=[],
            review_copy=None,
            warnings=[],
            configuration=detection_configuration_read_model(
                get_detection_configuration("135", "full")
            ),
            resolution_metadata=unavailable_calibration_fixture().metadata,
            transform_geometry=transform,
            analysis_reuse_signature=_analysis_reuse_signature(),
        )

        self.assertEqual(
            record["input"]["workspace_extent"],
            {"width": 220, "height": 120},
        )
        self.assertEqual(current_report_record_errors(record), [])

    def test_current_schema_rejects_incomplete_decision_gate(self) -> None:
        record = _record()
        record["decision"]["gate"]["checks"] = record["decision"]["gate"][
            "checks"
        ][:1]

        self.assertTrue(current_report_record_errors(record))

    def test_current_schema_rejects_decision_detached_from_transform(self) -> None:
        selection = selection_fixture()
        frame_bleed = frame_bleed_fixture()
        transform = transform_geometry_fixture(EvidenceState.CONTRADICTED)
        final_detection = finalize_detection(
            apply_decision_gate(selection, frame_bleed, transform),
            frame_bleed,
            finalization_plan_for_selection(
                selection,
                workspace_extent=WorkspaceExtent(200, 100),
            ),
        )
        record = report_record_for_final_detection(
            final_detection,
            selection,
            source="input.tif",
            profile=typed_read_model(_profile()),
            workspace_extent=WorkspaceExtent(200, 100),
            output_files=[],
            review_copy=None,
            warnings=[],
            configuration=detection_configuration_read_model(
                get_detection_configuration("135", "full")
            ),
            resolution_metadata=unavailable_calibration_fixture().metadata,
            transform_geometry=transform,
            analysis_reuse_signature=_analysis_reuse_signature(),
        )
        transform_check = next(
            check
            for check in record["decision"]["gate"]["checks"]
            if check["code"] == "transform_geometry_integrity"
        )
        transform_check["state"] = "supported"
        transform_check["blocks"] = False
        record["decision"]["gate"]["passed"] = True
        record["decision"]["gate"]["reason_inputs"] = []
        record["decision"]["status"] = "approved_auto"
        record["decision"]["final_review_reasons"] = []

        self.assertTrue(current_report_record_errors(record))

    def test_current_schema_binds_output_geometry_to_selected_geometry(self) -> None:
        record = _record()
        record["output"]["finalization_plan"]["decision_geometry"][
            "frame_boxes"
        ].reverse()
        record["output"]["final_geometry"]["frame_boxes"].reverse()

        self.assertIn(
            "record_identity_mismatch",
            current_report_record_errors(record),
        )

    def test_current_schema_rejects_output_coordinate_drift(self) -> None:
        record = _record()
        record["output"]["finalization_plan"]["decision_geometry"][
            "frame_boxes"
        ][0]["right"] -= 1
        record["output"]["final_geometry"]["frame_boxes"][0]["right"] -= 1

        self.assertIn(
            "record_identity_mismatch",
            current_report_record_errors(record),
        )

    def test_current_schema_binds_separator_sequence_to_geometry(self) -> None:
        record = _record()
        sequence = record["selection"]["candidates"][0]["evidence"][
            "separator_sequence"
        ]
        sequence["hard_tonal_evidence"] = []

        self.assertTrue(current_report_record_errors(record))

    def test_current_schema_binds_holder_boundary_to_geometry(self) -> None:
        record = _record()
        path = record["selection"]["candidates"][0]["evidence"][
            "holder_boundary"
        ]["paths"][0]
        path["position"]["minimum"] += 1.0
        path["position"]["maximum"] += 1.0

        self.assertTrue(current_report_record_errors(record))

    def test_current_schema_rejects_photo_interval_geometry_drift(self) -> None:
        record = _record()
        interval = record["selection"]["candidates"][0]["candidate_geometry"][
            "photo_intervals"
        ][0]
        interval["start"]["minimum"] += 10.0
        interval["start"]["maximum"] += 10.0

        self.assertIn(
            "record_identity_mismatch",
            current_report_record_errors(record),
        )

    def test_current_schema_binds_dimension_evidence_to_photo_intervals(self) -> None:
        record = _record()
        interval = record["selection"]["candidates"][0]["candidate_geometry"][
            "photo_intervals"
        ][0]
        interval["end"]["minimum"] = 90.0
        interval["end"]["maximum"] = 90.0

        self.assertIn(
            "record_identity_mismatch",
            current_report_record_errors(record),
        )


if __name__ == "__main__":
    unittest.main()
