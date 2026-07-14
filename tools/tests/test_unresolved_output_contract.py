from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from tools.tests.physical_gate_support import (
    candidate_fixture,
    selection_fixture,
    transform_geometry_fixture,
    unavailable_calibration_fixture,
)
from tools.tests.test_output_read_model_contract import (
    _analysis_reuse_signature,
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
from x5crop.domain import WorkspaceExtent
from x5crop.image.workspace import WorkspaceIdentity
from x5crop.output.model import AxisBleedParameters
from x5crop.runtime.frame_bleed import prepare_frame_bleed
from x5crop.export.actions import write_crops_if_allowed
from x5crop.report.configuration import detection_configuration_read_model
from x5crop.report.read_models import typed_read_model
from x5crop.report.record import report_record_for_final_detection
from x5crop.report.restoration import final_detection_from_record
from x5crop.report.validation import current_report_record_errors
from x5crop.run_status import RunTerminalOutcome


class UnresolvedOutputContractTest(unittest.TestCase):
    def test_resolved_review_remains_explicitly_exportable(self) -> None:
        selection = selection_fixture(
            candidate_fixture(failed_candidate_check="boundary_proof")
        )
        bleed = prepare_frame_bleed(selection, AxisBleedParameters(20, 10))
        detection = finalize_detection(
            apply_decision_gate(
                selection,
                bleed,
                transform_geometry_fixture(),
            ),
            bleed,
            finalization_plan_for_selection(
                selection,
                workspace_extent=WorkspaceExtent(310, 100),
            ),
        )
        with patch(
            "x5crop.export.actions.write_crops",
            return_value=["output/frame.tif"],
        ) as writer:
            outputs = write_crops_if_allowed(
                Path("input.tif"),
                np.zeros((100, 310), dtype=np.uint8),
                np.zeros((100, 310), dtype=np.uint8),
                _profile(),
                detection,
                SimpleNamespace(export_review=True, dry_run=False),
                False,
                SimpleNamespace(ensure_root=lambda: Path("output")),
            )

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
        bleed = prepare_frame_bleed(selection, AxisBleedParameters(20, 10))
        transform = transform_geometry_fixture()
        detection = finalize_detection(
            apply_decision_gate(selection, bleed, transform),
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
                SimpleNamespace(ensure_root=lambda: Path("output")),
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

        record = report_record_for_final_detection(
            detection,
            selection,
            source="input.tif",
            profile=typed_read_model(_profile()),
            workspace_identity=WorkspaceIdentity(WorkspaceExtent(310, 100), "0" * 64),
            output_files=outputs,
            review_copy=None,
            warnings=[],
            configuration=detection_configuration_read_model(
                get_detection_configuration("135", "full")
            ),
            resolution_metadata=unavailable_calibration_fixture().metadata,
            transform_geometry=transform,
            analysis_reuse_signature=_analysis_reuse_signature(),
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
        self.assertIsNone(final_detection_from_record(record).output_geometry)


if __name__ == "__main__":
    unittest.main()
