from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from tools.tests.physical_gate_support import (
    candidate_fixture,
    detection_workspace_fixture,
    frame_bleed_fixture,
    selection_fixture,
    transform_geometry_fixture,
    unavailable_resolution_metadata_fixture,
)
from tools.tests.test_output_read_model_contract import (
    _analysis_identity,
    _profile,
)
from x5crop.configuration.registry import get_detection_configuration
from x5crop.detection.decision.decision_gate import apply_decision_gate
from x5crop.detection.final.finalize import (
    finalization_plan_for_selection,
    finalize_detection,
)
from x5crop.debug.panels import debug_geometry
from x5crop.debug.status import debug_status_parts
from x5crop.domain import EvidenceState, WorkspaceExtent
from x5crop.output.model import AxisBleedParameters
from x5crop.output.surface import OutputSurface
from x5crop.detection.output_preparation import frame_bleed_plan_for_selection
from x5crop.export.actions import write_crops_if_allowed
from x5crop.report.configuration import detection_configuration_read_model
from x5crop.report.read_models import typed_read_model
from x5crop.report.record import report_record_for_final_detection
from x5crop.report.validation import current_report_record_errors
from x5crop.run_status import RunTerminalOutcome


class UnresolvedOutputContractTest(unittest.TestCase):
    def test_approved_detection_requires_export_eligible_output(self) -> None:
        selection = selection_fixture()
        safe_bleed = frame_bleed_fixture()
        unsafe_bleed = frame_bleed_fixture(feasible=False)
        approved = apply_decision_gate(
            selection,
            safe_bleed,
            transform_geometry_fixture(),
            automatic_processing_eligibility=EvidenceState.SUPPORTED,
        )

        with self.assertRaisesRegex(
            ValueError,
            "approved detection requires export-eligible output",
        ):
            finalize_detection(
                approved,
                unsafe_bleed,
                finalization_plan_for_selection(
                    selection,
                    workspace_extent=WorkspaceExtent(310, 100),
                ),
            )

    def test_export_review_cannot_bypass_unresolved_output_protection(self) -> None:
        selection = selection_fixture(
            candidate_fixture(failed_candidate_check="sequence_proof")
        )
        bleed = frame_bleed_fixture(feasible=False)
        transform = transform_geometry_fixture()
        detection = finalize_detection(
            apply_decision_gate(
                selection,
                bleed,
                transform,
                automatic_processing_eligibility=EvidenceState.SUPPORTED,
            ),
            bleed,
            finalization_plan_for_selection(
                selection,
                workspace_extent=WorkspaceExtent(310, 100),
            ),
        )

        self.assertFalse(detection.frame_export_eligible)
        self.assertEqual(
            detection.frame_export_reason,
            "output_protection_unresolved",
        )
        with TemporaryDirectory() as temporary_directory, patch(
            "x5crop.export.actions.write_crops",
            return_value=["output/frame.tif"],
        ) as writer:
            output_root = Path(temporary_directory) / "output"
            outputs = write_crops_if_allowed(
                Path("input.tif"),
                np.zeros((100, 310), dtype=np.uint8),
                np.zeros((100, 310), dtype=np.uint8),
                _profile(),
                detection,
                SimpleNamespace(export_review=True, dry_run=False),
                False,
                OutputSurface(output_root),
            )
            self.assertFalse(output_root.exists())

        self.assertEqual(outputs, [])
        writer.assert_not_called()
        self.assertIn(
            "NOT EXPORTABLE",
            debug_status_parts(
                detection,
                get_detection_configuration("135", "full").diagnostics.style,
                RunTerminalOutcome.COMPLETED,
            )[1],
        )
        geometry = debug_geometry(
            np.zeros((100, 310), dtype=np.uint8),
            detection,
            selection.selected,
        )
        self.assertEqual(
            geometry.frame_crop_envelopes,
            detection.output_geometry.frame_crop_envelopes,
        )
        self.assertEqual(geometry.final_boxes, ())

        workspace = detection_workspace_fixture()
        record = report_record_for_final_detection(
            detection,
            selection,
            source="input.tif",
            profile=typed_read_model(_profile()),
            workspace=workspace,
            output_files=outputs,
            review_copy=None,
            warnings=[],
            configuration=detection_configuration_read_model(
                get_detection_configuration("135", "partial")
            ),
            resolution_metadata=unavailable_resolution_metadata_fixture(),
            analysis_identity=_analysis_identity(
                workspace_identity=workspace.identity,
            ),
        )
        self.assertIsNotNone(record["output"]["finalization_plan"])
        self.assertIsNotNone(record["output"]["final_geometry"])
        self.assertEqual(
            record["output"]["export_eligibility"],
            {
                "frame_export_eligible": False,
                "reason": "output_protection_unresolved",
            },
        )
        self.assertEqual(current_report_record_errors(record), [])
        record["output"]["output_files"] = ["unsafe-review-frame.tif"]
        self.assertIn(
            "output_incomplete",
            current_report_record_errors(record),
        )

    def test_resolved_review_remains_explicitly_exportable(self) -> None:
        selection = selection_fixture(
            candidate_fixture(failed_candidate_check="sequence_proof")
        )
        bleed = frame_bleed_plan_for_selection(
            selection,
            AxisBleedParameters(20, 10),
        )
        detection = finalize_detection(
            apply_decision_gate(
                selection,
                bleed,
                transform_geometry_fixture(),
                automatic_processing_eligibility=EvidenceState.SUPPORTED,
            ),
            bleed,
            finalization_plan_for_selection(
                selection,
                workspace_extent=WorkspaceExtent(310, 100),
            ),
        )
        self.assertTrue(detection.frame_export_eligible)
        self.assertEqual(
            detection.frame_export_reason,
            "geometry_resolved_output_protected",
        )
        with TemporaryDirectory() as temporary_directory, patch(
            "x5crop.export.actions.write_crops",
            return_value=["output/frame.tif"],
        ) as writer:
            output_root = Path(temporary_directory) / "output"
            outputs = write_crops_if_allowed(
                Path("input.tif"),
                np.zeros((100, 310), dtype=np.uint8),
                np.zeros((100, 310), dtype=np.uint8),
                _profile(),
                detection,
                SimpleNamespace(export_review=True, dry_run=False),
                False,
                OutputSurface(output_root),
            )
            self.assertTrue(output_root.is_dir())

        self.assertEqual(outputs, ["output/frame.tif"])
        writer.assert_called_once()

    def test_export_review_cannot_write_unresolved_provisional_frames(self) -> None:
        selection = selection_fixture()
        selection = replace(
            selection,
            geometry_resolution=replace(
                selection.geometry_resolution,
                count_resolved=False,
            ),
        )
        bleed = frame_bleed_plan_for_selection(
            selection,
            AxisBleedParameters(20, 10),
        )
        transform = transform_geometry_fixture()
        detection = finalize_detection(
            apply_decision_gate(
                selection,
                bleed,
                transform,
                automatic_processing_eligibility=EvidenceState.SUPPORTED,
            ),
            bleed,
            finalization_plan_for_selection(
                selection,
                workspace_extent=WorkspaceExtent(310, 100),
            ),
        )
        with patch("x5crop.export.actions.write_crops") as writer:
            outputs = write_crops_if_allowed(
                Path("input.tif"),
                np.zeros((100, 310), dtype=np.uint8),
                np.zeros((100, 310), dtype=np.uint8),
                _profile(),
                detection,
                SimpleNamespace(export_review=True, dry_run=False),
                False,
                OutputSurface(Path("output")),
            )

        self.assertEqual(outputs, [])
        writer.assert_not_called()

        diagnostics = get_detection_configuration("135", "full").diagnostics
        geometry = debug_geometry(
            np.zeros((100, 310), dtype=np.uint8),
            detection,
            selection.selected,
        )
        self.assertEqual(
            tuple(item.box for item in geometry.frame_crop_envelopes),
            tuple(item.box for item in selection.selected.geometry.frame_crop_envelopes),
        )
        self.assertEqual(geometry.final_boxes, ())
        self.assertIn(
            "NOT EXPORTABLE",
            debug_status_parts(
                detection,
                diagnostics.style,
                RunTerminalOutcome.COMPLETED,
            )[1],
        )

        workspace = detection_workspace_fixture()
        record = report_record_for_final_detection(
            detection,
            selection,
            source="input.tif",
            profile=typed_read_model(_profile()),
            workspace=workspace,
            output_files=outputs,
            review_copy=None,
            warnings=[],
            configuration=detection_configuration_read_model(
                get_detection_configuration("135", "partial")
            ),
            resolution_metadata=unavailable_resolution_metadata_fixture(),
            analysis_identity=_analysis_identity(
                workspace_identity=workspace.identity,
            ),
        )
        self.assertIsNone(record["output"]["finalization_plan"])
        self.assertIsNone(record["output"]["final_geometry"])
        self.assertEqual(
            record["output"]["export_eligibility"],
            {
                "frame_export_eligible": False,
                "reason": "geometry_resolution_unavailable",
            },
        )
        self.assertEqual(current_report_record_errors(record), [])


if __name__ == "__main__":
    unittest.main()
