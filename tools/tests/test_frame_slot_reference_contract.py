from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import unittest

from tools.regression.frame_slot_reference import (
    ReferenceValidationOutcome,
    _reference_in_detection_workspace,
    compare_report_to_reference,
    frame_slot_reference_from_record,
)
from tools.tests.physical_gate_support import (
    detection_workspace_fixture,
    selection_fixture,
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
from x5crop.domain import EvidenceState, PixelInterval, WorkspaceExtent
from x5crop.geometry.affine import AffineCoordinateTransform
from x5crop.output.model import AxisBleedParameters
from x5crop.report.configuration import detection_configuration_read_model
from x5crop.report.read_models import typed_read_model
from x5crop.report.record import report_record_for_final_detection
from x5crop.detection.output_preparation import frame_bleed_plan_for_selection


def _reference_record(report: dict) -> dict:
    selected = report["selection"]["candidates"][
        int(report["selection"]["selected_rank"]) - 1
    ]["provisional_geometry"]
    shared = selected["shared_short_axis"]["span"]
    return {
        "schema_id": "frame_slot_reference",
        "schema_revision": "acceptable_sequence_intervals",
        "source": report["source"],
        "format_id": selected["format_id"],
        "strip_mode": selected["strip_mode"],
        "layout": selected["layout"],
        "shared_short_axis": {
            side: {
                "minimum": shared[side]["minimum"] - 1.0,
                "maximum": shared[side]["maximum"] + 1.0,
            }
            for side in ("top", "bottom")
        },
        "frame_slots": [
            {
                "index": slot["index"],
                **{
                    side: {
                        "minimum": slot[side]["position"]["minimum"] - 1.0,
                        "maximum": slot[side]["position"]["maximum"] + 1.0,
                    }
                    for side in ("leading", "trailing")
                },
            }
            for slot in selected["frame_slots"]
        ],
        "notes": [],
    }


def _unresolved_record(source: str = "input.tif") -> dict:
    selection = selection_fixture()
    selection = replace(
        selection,
        geometry_resolution=replace(
            selection.geometry_resolution,
            frame_slots_resolved=False,
        ),
    )
    bleed = frame_bleed_plan_for_selection(
        selection,
        AxisBleedParameters(20, 10),
    )
    workspace = detection_workspace_fixture()
    transform = workspace.transform_geometry
    detection = finalize_detection(
        apply_decision_gate(
            selection,
            bleed,
            workspace.scan_canvas_evidence,
            transform,
            automatic_processing_eligibility=EvidenceState.SUPPORTED,
        ),
        bleed,
        finalization_plan_for_selection(
            selection,
            workspace_extent=WorkspaceExtent(310, 100),
        ),
    )
    return report_record_for_final_detection(
        detection,
        selection,
        source=source,
        profile=typed_read_model(_profile()),
        workspace=workspace,
        output_files=[],
        review_copy=None,
        warnings=[],
        configuration=detection_configuration_read_model(
            get_detection_configuration("135", "partial")
        ),
        analysis_identity=_analysis_identity(
            source_name=Path(source).name,
            workspace_identity=workspace.identity,
        ),
    )


class FrameSlotReferenceContractTest(unittest.TestCase):
    def test_workspace_relative_reference_matches_absolute_report_source(self) -> None:
        workspace_root = Path("/project")
        relative_source = "Test/135/partial/pass_X5_99990.tif"
        report = _record(str(workspace_root / relative_source))
        reference_record = _reference_record(report)
        reference_record["source"] = relative_source

        result = compare_report_to_reference(
            report,
            frame_slot_reference_from_record(reference_record),
            workspace_root=workspace_root,
        )

        self.assertEqual(result.outcome, ReferenceValidationOutcome.MATCHED)

    def test_resolved_frame_slots_match_manual_intervals(self) -> None:
        report = _record()
        reference = frame_slot_reference_from_record(_reference_record(report))

        result = compare_report_to_reference(report, reference)

        self.assertEqual(result.outcome, ReferenceValidationOutcome.MATCHED)
        self.assertEqual(result.violations, ())

    def test_source_reference_uses_report_affine_coordinate_domain(self) -> None:
        reference = frame_slot_reference_from_record(_reference_record(_record()))
        transform = AffineCoordinateTransform.expanded_rotation(310, 100, 1.0)

        mapped = _reference_in_detection_workspace(reference, transform)

        self.assertNotEqual(mapped.shared_short_axis, reference.shared_short_axis)
        expected_leading, _ = transform.map_intervals(
            reference.frame_slots[0].leading,
            PixelInterval(
                reference.shared_short_axis.top.minimum,
                reference.shared_short_axis.bottom.maximum,
            ),
        )
        self.assertEqual(mapped.frame_slots[0].leading, expected_leading)

    def test_unresolved_geometry_is_honest(self) -> None:
        report = _unresolved_record()
        reference = frame_slot_reference_from_record(_reference_record(report))

        result = compare_report_to_reference(report, reference)

        self.assertEqual(result.outcome, ReferenceValidationOutcome.UNRESOLVED)

    def test_resolved_frame_boundary_outside_reference_is_a_violation(self) -> None:
        report = _record()
        reference_record = _reference_record(report)
        actual = report["selection"]["candidates"][0]["provisional_geometry"]
        leading = actual["frame_slots"][0]["leading"]["position"]
        reference_record["frame_slots"][0]["leading"] = {
            "minimum": leading["maximum"] + 10.0,
            "maximum": leading["maximum"] + 20.0,
        }

        result = compare_report_to_reference(
            report,
            frame_slot_reference_from_record(reference_record),
        )

        self.assertEqual(result.outcome, ReferenceValidationOutcome.VIOLATED)
        self.assertEqual(
            result.violations,
            ("frame:1:leading:outside_reference",),
        )

    def test_reference_schema_has_no_compatibility_fallback(self) -> None:
        obsolete = deepcopy(_reference_record(_record()))
        obsolete["schema_revision"] = "acceptable_aperture_intervals"

        with self.assertRaises(ValueError):
            frame_slot_reference_from_record(obsolete)

    def test_reference_schema_rejects_extra_fields_and_type_coercion(self) -> None:
        report = _record()
        extra = deepcopy(_reference_record(report))
        extra["frame_slots"][0]["aperture"] = {}
        wrong_note = deepcopy(_reference_record(report))
        wrong_note["notes"] = [7]
        wrong_index = deepcopy(_reference_record(report))
        wrong_index["frame_slots"][0]["index"] = "1"

        for record in (extra, wrong_note, wrong_index):
            with self.subTest(record=record):
                with self.assertRaises(ValueError):
                    frame_slot_reference_from_record(record)


if __name__ == "__main__":
    unittest.main()
