from __future__ import annotations

import unittest

import numpy as np

from tools.tests.physical_gate_support import (
    frame_bleed_fixture,
    selection_fixture,
    transform_geometry_fixture,
    unavailable_resolution_metadata_fixture,
)
from tools.tests.test_output_read_model_contract import (
    _analysis_identity,
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
from x5crop.image.workspace import WorkspaceIdentity


class ReportIdentityContractTest(unittest.TestCase):
    def test_prepared_workspace_owns_exact_gray_identity(self) -> None:
        from x5crop.runtime.prepared_workspace import PreparedWorkspace

        transform = transform_geometry_fixture()
        first = PreparedWorkspace(
            pixels=np.zeros((2, 3), dtype=np.uint8),
            gray=np.zeros((2, 3), dtype=np.uint8),
            transform_geometry=transform,
        )
        changed = PreparedWorkspace(
            pixels=np.zeros((2, 3), dtype=np.uint8),
            gray=np.array(((0, 0, 0), (0, 0, 1)), dtype=np.uint8),
            transform_geometry=transform,
        )

        self.assertEqual(first.identity.extent, WorkspaceExtent(3, 2))
        self.assertNotEqual(first.identity.gray_sha256, changed.identity.gray_sha256)

    def test_implementation_fingerprint_covers_source_bytes(self) -> None:
        from x5crop.runtime.implementation import (
            implementation_fingerprint_for_sources,
        )

        first = implementation_fingerprint_for_sources({"x5crop.a": "value = 1\n"})
        changed = implementation_fingerprint_for_sources({"x5crop.a": "value = 2\n"})

        self.assertNotEqual(first, changed)

    def test_deskew_workspace_extent_owns_output_identity(self) -> None:
        selection = selection_fixture()
        frame_bleed = frame_bleed_fixture()
        transform = transform_geometry_fixture(EvidenceState.SUPPORTED)
        final_detection = finalize_detection(
            apply_decision_gate(
                selection,
                frame_bleed,
                transform,
                automatic_processing_eligibility=EvidenceState.SUPPORTED,
            ),
            frame_bleed,
            finalization_plan_for_selection(
                selection,
                workspace_extent=WorkspaceExtent(330, 120),
            ),
        )
        record = report_record_for_final_detection(
            final_detection,
            selection,
            source="input.tif",
            profile=typed_read_model(_profile()),
            workspace_identity=WorkspaceIdentity(WorkspaceExtent(330, 120), "0" * 64),
            output_files=[],
            review_copy=None,
            warnings=[],
            configuration=detection_configuration_read_model(
                get_detection_configuration("135", "partial")
            ),
            resolution_metadata=unavailable_resolution_metadata_fixture(),
            transform_geometry=transform,
            analysis_identity=_analysis_identity(
                workspace_shape=(120, 330)
            ),
        )

        self.assertEqual(
            record["input"]["workspace_identity"]["extent"],
            {"width": 330, "height": 120},
        )
        self.assertEqual(current_report_record_errors(record), [])

    def test_report_has_one_runtime_fact_fingerprint(self) -> None:
        record = _record()

        self.assertEqual(len(record["runtime_facts_sha256"]), 64)
        record["decision"]["status"] = "needs_review"
        self.assertIn(
            "runtime_facts_fingerprint_mismatch",
            current_report_record_errors(record),
        )

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
            apply_decision_gate(
                selection,
                frame_bleed,
                transform,
                automatic_processing_eligibility=EvidenceState.SUPPORTED,
            ),
            frame_bleed,
            finalization_plan_for_selection(
                selection,
                workspace_extent=WorkspaceExtent(310, 100),
            ),
        )
        record = report_record_for_final_detection(
            final_detection,
            selection,
            source="input.tif",
            profile=typed_read_model(_profile()),
            workspace_identity=WorkspaceIdentity(WorkspaceExtent(310, 100), "0" * 64),
            output_files=[],
            review_copy=None,
            warnings=[],
            configuration=detection_configuration_read_model(
                get_detection_configuration("135", "partial")
            ),
            resolution_metadata=unavailable_resolution_metadata_fixture(),
            transform_geometry=transform,
            analysis_identity=_analysis_identity(),
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
        record["output"]["finalization_plan"]["base_geometry"][
            "frame_crop_envelopes"
        ].reverse()
        record["output"]["final_geometry"]["frame_crop_envelopes"].reverse()

        self.assertTrue(current_report_record_errors(record))

    def test_current_schema_rejects_output_coordinate_drift(self) -> None:
        record = _record()
        record["output"]["finalization_plan"]["base_geometry"][
            "final_boxes"
        ][0]["right"] -= 1
        record["output"]["final_geometry"]["final_boxes"][0]["right"] -= 1

        self.assertTrue(current_report_record_errors(record))

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
        ]["boundaries"][0]
        path["position"]["minimum"] += 1.0
        path["position"]["maximum"] += 1.0

        self.assertTrue(current_report_record_errors(record))

    def test_current_schema_rejects_frame_slot_geometry_drift(self) -> None:
        record = _record()
        interval = record["selection"]["candidates"][0]["provisional_geometry"][
            "frame_slots"
        ][0]["leading"]["position"]
        interval["minimum"] += 10.0
        interval["maximum"] += 10.0

        errors = current_report_record_errors(record)
        self.assertTrue(errors)
        self.assertIn("runtime_facts_fingerprint_mismatch", errors)

    def test_current_schema_binds_dimension_evidence_to_frame_slots(self) -> None:
        record = _record()
        interval = record["selection"]["candidates"][0]["provisional_geometry"][
            "frame_slots"
        ][0]["trailing"]["position"]
        interval["minimum"] = 140.0
        interval["maximum"] = 140.0

        errors = current_report_record_errors(record)
        self.assertTrue(errors)
        self.assertIn("runtime_facts_fingerprint_mismatch", errors)


if __name__ == "__main__":
    unittest.main()
