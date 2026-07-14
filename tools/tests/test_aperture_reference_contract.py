from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import unittest

from tools.regression.aperture_reference import (
    ReferenceValidationOutcome,
    compare_report_to_reference,
    photo_aperture_reference_from_record,
)
from tools.tests.physical_gate_support import (
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
from x5crop.domain import WorkspaceExtent
from x5crop.image.workspace import WorkspaceIdentity
from x5crop.output.model import AxisBleedParameters
from x5crop.runtime.frame_bleed import prepare_frame_bleed
from x5crop.report.configuration import detection_configuration_read_model
from x5crop.report.read_models import typed_read_model
from x5crop.report.record import report_record_for_final_detection


def _reference_record(report: dict) -> dict:
    selected = report["selection"]["candidates"][
        int(report["selection"]["selected_rank"]) - 1
    ]["provisional_geometry"]
    return {
        "schema_id": "photo_aperture_reference",
        "schema_revision": "acceptable_boundary_intervals",
        "source": report["source"],
        "format_id": selected["format_id"],
        "strip_mode": selected["strip_mode"],
        "layout": selected["layout"],
        "apertures": [
            {
                "index": aperture["index"],
                **{
                    side: {
                        "minimum": aperture[side]["position"]["minimum"] - 1.0,
                        "maximum": aperture[side]["position"]["maximum"] + 1.0,
                    }
                    for side in ("leading", "trailing", "top", "bottom")
                },
            }
            for aperture in selected["photo_apertures"]
        ],
        "notes": [],
    }


def _unresolved_record() -> dict:
    selection = selection_fixture()
    selection = replace(
        selection,
        geometry_resolution=replace(
            selection.geometry_resolution,
            placement_resolved=False,
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
    return report_record_for_final_detection(
        detection,
        selection,
        source="input.tif",
        profile=typed_read_model(_profile()),
        workspace_identity=WorkspaceIdentity(WorkspaceExtent(310, 100), "0" * 64),
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


class ApertureReferenceContractTest(unittest.TestCase):
    def test_resolved_apertures_must_remain_inside_manual_intervals(self) -> None:
        report = _record()
        reference = photo_aperture_reference_from_record(_reference_record(report))

        result = compare_report_to_reference(report, reference)

        self.assertEqual(result.outcome, ReferenceValidationOutcome.MATCHED)
        self.assertEqual(result.violations, ())

    def test_unresolved_geometry_is_honest_not_a_wrong_aperture(self) -> None:
        report = _unresolved_record()
        reference = photo_aperture_reference_from_record(_reference_record(report))

        result = compare_report_to_reference(report, reference)

        self.assertEqual(result.outcome, ReferenceValidationOutcome.UNRESOLVED)
        self.assertEqual(result.violations, ())

    def test_resolved_aperture_outside_manual_interval_is_a_violation(self) -> None:
        report = _record()
        reference_record = _reference_record(report)
        actual = report["selection"]["candidates"][0]["provisional_geometry"]
        actual_leading = actual["photo_apertures"][0]["leading"]["position"]
        reference_record["apertures"][0]["leading"] = {
            "minimum": actual_leading["maximum"] + 10.0,
            "maximum": actual_leading["maximum"] + 20.0,
        }

        result = compare_report_to_reference(
            report,
            photo_aperture_reference_from_record(reference_record),
        )

        self.assertEqual(result.outcome, ReferenceValidationOutcome.VIOLATED)
        self.assertEqual(
            result.violations,
            ("photo:1:leading:outside_reference",),
        )

    def test_reference_schema_has_no_compatibility_fallback(self) -> None:
        obsolete = deepcopy(_reference_record(_record()))
        obsolete["schema_revision"] = "legacy_outer_boxes"

        with self.assertRaises(ValueError):
            photo_aperture_reference_from_record(obsolete)

    def test_reference_schema_rejects_nested_extra_fields_and_type_coercion(self) -> None:
        report = _record()
        extra = deepcopy(_reference_record(report))
        extra["apertures"][0]["legacy_outer_box"] = {}
        wrong_note = deepcopy(_reference_record(report))
        wrong_note["notes"] = [7]
        wrong_index = deepcopy(_reference_record(report))
        wrong_index["apertures"][0]["index"] = "1"

        for record in (extra, wrong_note, wrong_index):
            with self.subTest(record=record):
                with self.assertRaises(ValueError):
                    photo_aperture_reference_from_record(record)


if __name__ == "__main__":
    unittest.main()
