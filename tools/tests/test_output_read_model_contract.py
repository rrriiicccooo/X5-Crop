from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import os
from tempfile import TemporaryDirectory
import unittest
import numpy as np
from dataclasses import fields, replace

from tools.tests.support.physical_gates import (
    detection_workspace_fixture,
    final_detection_fixture,
    frame_bleed_fixture,
    selection_fixture,
    transform_geometry_fixture,
)
from tools.tests.support.report import (
    analysis_identity_fixture,
    image_profile_fixture,
    report_record_fixture,
)
from x5crop.detection.decision.decision_gate import apply_decision_gate
from x5crop.detection.evidence.scan_canvas import observe_scan_canvas
from x5crop.detection.final.finalize import (
    finalization_plan_for_selection,
    finalize_detection,
)
from x5crop.detection.final.model import FinalDetection
from x5crop.io.model import ImageProfile, TiffMetadata
from x5crop.io.tiff import compression_for_write
from x5crop.configuration.registry import get_detection_configuration
from x5crop.report.configuration import detection_configuration_read_model
from x5crop.report.model import ReportResult
from x5crop.report.record import report_record_for_final_detection
from x5crop.report.read_models import typed_read_model
from x5crop.report.validation import current_report_record_errors
from x5crop.domain import EvidenceState, WorkspaceExtent
from tools.regression.compare import DEFAULT_FIELDS


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class OutputReadModelContractTest(unittest.TestCase):
    def test_tiff_compression_mode_is_exhaustive(self) -> None:
        with self.assertRaises(ValueError):
            compression_for_write(image_profile_fixture(), "invalid")

    def test_transform_geometry_is_detection_input_not_diagnostics(self) -> None:
        record = report_record_fixture()
        self.assertIn("transform_geometry", record["input"])
        self.assertNotIn("diagnostics", record)

    def test_input_records_effective_scan_canvas_not_tiff_dpi(self) -> None:
        input_detail = report_record_fixture()["input"]
        self.assertIn("scan_canvas_evidence", input_detail)
        scale = input_detail["scan_canvas_evidence"]["pixel_scale"]
        if scale is None:
            self.assertNotIn(
                "effective_ppi",
                input_detail["scan_canvas_evidence"],
            )
        else:
            effective_ppi = input_detail["scan_canvas_evidence"][
                "effective_ppi"
            ]
            self.assertAlmostEqual(
                effective_ppi["long_axis"],
                scale["long_axis_px_per_mm"] * 25.4,
            )
            self.assertAlmostEqual(
                effective_ppi["short_axis"],
                scale["short_axis_px_per_mm"] * 25.4,
            )
        self.assertNotIn("resolution_metadata", input_detail)
        self.assertNotIn("scan_calibration", input_detail)

    def test_current_schema_validates_canvas_derived_ppi(self) -> None:
        configuration = get_detection_configuration("135", "partial")
        workspace = detection_workspace_fixture(width=720, height=100)
        scan_canvas = observe_scan_canvas(
            720,
            100,
            "horizontal",
            configuration.scan_canvas,
        )
        workspace = replace(
            workspace,
            scan_canvas_evidence=scan_canvas,
        )
        selection = selection_fixture()
        bleed = frame_bleed_fixture()
        detection = finalize_detection(
            apply_decision_gate(
                selection,
                bleed,
                scan_canvas,
                workspace.transform_geometry,
                automatic_processing_eligibility=EvidenceState.SUPPORTED,
            ),
            bleed,
            finalization_plan_for_selection(
                selection,
                workspace_extent=WorkspaceExtent(720, 100),
            ),
        )
        profile = replace(image_profile_fixture(), shape=(100, 720))
        record = report_record_for_final_detection(
            detection,
            selection,
            source="input.tif",
            profile=typed_read_model(profile),
            workspace=workspace,
            output_files=[],
            review_copy=None,
            warnings=[],
            configuration=detection_configuration_read_model(
                configuration
            ),
            analysis_identity=analysis_identity_fixture(
                shape=(100, 720),
                workspace_shape=(100, 720),
                workspace_identity=workspace.identity,
            ),
        )

        scale = record["input"]["scan_canvas_evidence"]["pixel_scale"]
        effective_ppi = record["input"]["scan_canvas_evidence"][
            "effective_ppi"
        ]
        self.assertAlmostEqual(
            effective_ppi["long_axis"],
            scale["long_axis_px_per_mm"] * 25.4,
        )
        self.assertAlmostEqual(
            effective_ppi["short_axis"],
            scale["short_axis_px_per_mm"] * 25.4,
        )
        self.assertEqual(current_report_record_errors(record), [])

    def test_configuration_report_includes_boundary_path_measurements(self) -> None:
        configuration = get_detection_configuration("135", "full")
        detail = detection_configuration_read_model(configuration)

        self.assertEqual(
            detail["measurement"]["boundary_path"],
            typed_read_model(configuration.boundary_path),
        )

    def test_current_schema_rejects_missing_or_changed_boundary_path_parameters(self) -> None:
        missing = report_record_fixture()
        missing["configuration"]["measurement"].pop("boundary_path", None)
        self.assertTrue(current_report_record_errors(missing))

        changed = report_record_fixture()
        changed["configuration"]["measurement"]["boundary_path"] = {}
        self.assertTrue(current_report_record_errors(changed))

    def test_output_has_one_canonical_finalization_plan(self) -> None:
        output = report_record_fixture()["output"]
        self.assertIn("finalization_plan", output)
        self.assertIn("frame_bleed_plan", output)
        self.assertNotIn("decision_geometry", output)
        self.assertNotIn("frame_bleed_plan", output["finalization_plan"])

    def test_candidate_report_does_not_duplicate_geometry_invariants(self) -> None:
        candidate = report_record_fixture()["selection"]["candidates"][0]
        self.assertIn("inter_frame_spacings", candidate["provisional_geometry"])
        self.assertNotIn("sequence_conservation", candidate["evidence"])
        self.assertNotIn("frame_sequence", candidate["evidence"])

    def test_analysis_source_identity_includes_file_content(self) -> None:
        from x5crop.runtime.analysis_identity import source_analysis_identity

        profile = ImageProfile(
            shape=(1, 4),
            dtype="uint8",
            axes="YX",
            photometric="MINISBLACK",
            compression="NONE",
            sample_format=None,
            bits_per_sample=8,
            samples_per_pixel=1,
            planar_config=None,
            resolution=None,
            resolution_unit=None,
            icc_profile=None,
            metadata=TiffMetadata(None, None, None, ()),
        )
        fixed_time_ns = 1_700_000_000_000_000_000
        with TemporaryDirectory() as directory:
            source = Path(directory) / "source.tif"
            source.write_bytes(b"aaaa")
            os.utime(source, ns=(fixed_time_ns, fixed_time_ns))
            first = source_analysis_identity(source, profile, 0)
            source.write_bytes(b"bbbb")
            os.utime(source, ns=(fixed_time_ns, fixed_time_ns))
            second = source_analysis_identity(source, profile, 0)

        self.assertNotEqual(first, second)

    def test_configuration_fingerprint_has_no_stringification_fallback(self) -> None:
        source = (PROJECT_ROOT / "x5crop/runtime/analysis_identity.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("default=str", source)

    def test_review_only_pipeline_produces_valid_current_report(self) -> None:
        from x5crop.cache.analysis import make_measurement_cache
        from x5crop.cache import MeasurementCacheStatistics
        from x5crop.configuration.registry import get_detection_configuration
        from x5crop.detection.context import (
            DetectionContext,
            DetectionExecutionStatistics,
            DetectionRequest,
        )
        from x5crop.detection.decision.decision_gate import apply_decision_gate
        from x5crop.detection.final.finalize import (
            finalization_plan_for_selection,
            finalize_detection,
        )
        from x5crop.detection.pipeline import choose_detection
        from x5crop.io.model import ImageProfile
        from x5crop.image.statistics import image_measurement_statistics
        from x5crop.report.configuration import detection_configuration_read_model
        from x5crop.report.record import report_record_for_final_detection
        from x5crop.report.validation import current_report_record_errors
        from x5crop.detection.output_preparation import (
            frame_bleed_plan_for_selection,
        )
        from x5crop.output.model import AxisBleedParameters
        from tools.tests.support.physical_gates import transform_geometry_fixture

        configuration = get_detection_configuration("135-dual", "partial")
        gray = np.full((120, 240), 255, dtype=np.uint8)
        workspace = detection_workspace_fixture(width=240, height=120)
        profile = ImageProfile(
            shape=gray.shape,
            dtype="uint8",
            axes="YX",
            photometric="MINISBLACK",
            compression="NONE",
            sample_format=None,
            bits_per_sample=8,
            samples_per_pixel=1,
            planar_config=None,
            resolution=None,
            resolution_unit=None,
            icc_profile=None,
            metadata=TiffMetadata(None, None, None, ()),
        )
        context = DetectionContext(
            request=DetectionRequest("horizontal", "partial", None),
            configuration=configuration,
            lane_configuration=None,
            workspace=workspace,
            execution_statistics=DetectionExecutionStatistics(),
        )
        selection = choose_detection(context)
        from x5crop.detection.candidate.model import ReviewOnlyEvidence
        from x5crop.detection.physical.model import ReviewOnlyContainment
        self.assertIsInstance(selection.selected.geometry, ReviewOnlyContainment)
        self.assertIsInstance(
            selection.selected.assessment.evidence,
            ReviewOnlyEvidence,
        )
        self.assertIsNone(selection.selected.assessment.gate)
        self.assertNotIn(
            "separator_observations",
            selection.selected.geometry.__dataclass_fields__,
        )
        bleed = frame_bleed_plan_for_selection(
            selection,
            AxisBleedParameters(20, 10),
        )
        detection = apply_decision_gate(
            selection,
            bleed,
            detection_workspace_fixture().scan_canvas_evidence,
            transform_geometry_fixture(),
            automatic_processing_eligibility=EvidenceState.CONTRADICTED,
        )
        detection = finalize_detection(
            detection,
            bleed,
            finalization_plan_for_selection(
                selection,
                workspace_extent=WorkspaceExtent(240, 120),
            ),
        )
        self.assertEqual(
            detection.decision.final_review_reasons,
            ("automatic_processing_not_supported",),
        )
        record = report_record_for_final_detection(
            detection,
            selection,
            source="synthetic.tif",
            profile=typed_read_model(profile),
            workspace=workspace,
            output_files=[],
            review_copy=None,
            warnings=[],
            configuration=detection_configuration_read_model(configuration),
            analysis_identity=analysis_identity_fixture(
                "135-dual",
                "partial",
                "synthetic.tif",
                (120, 240),
                workspace_identity=workspace.identity,
            ),
        )
        self.assertEqual(current_report_record_errors(record), [])
        candidate_record = record["selection"]["candidates"][0]
        self.assertEqual(
            candidate_record["evidence"],
            {},
        )
        self.assertIsNone(candidate_record["candidate_gate"])

    def test_analysis_identity_does_not_resolve_configuration_from_report_data(self) -> None:
        source = (
            PROJECT_ROOT / "x5crop/runtime/analysis_identity.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("configuration_bundle.configuration_for(", source)

    def test_typed_read_model_serializes_every_typed_result_field(self) -> None:
        from x5crop.domain import (
            FrameDimensionPrior,
            MeasurementIdentity,
            MeasurementProvenance,
            ObservationId,
            PixelInterval,
        )
        from x5crop.report.read_models import typed_read_model

        value = FrameDimensionPrior(
            frame_size_mm=(36.0, 24.0),
            provenance=MeasurementProvenance(
                MeasurementIdentity.PHYSICAL_FRAME_ASPECT,
                ObservationId("test"),
                (MeasurementIdentity.FORMAT_PHYSICAL_SPEC,),
                "test provenance",
            ),
        )
        self.assertEqual(
            set(typed_read_model(value)),
            {field.name for field in fields(FrameDimensionPrior)},
        )

    def test_final_detection_has_no_schema_restoration_wrapper(self) -> None:
        self.assertNotIn("restore", FinalDetection.__dict__)

    def test_fresh_record_is_current_schema_valid(self) -> None:
        self.assertEqual(current_report_record_errors(report_record_fixture()), [])

    def test_json_round_trip_preserves_current_schema_identity(self) -> None:
        persisted = json.loads(json.dumps(report_record_fixture()))

        self.assertEqual(current_report_record_errors(persisted), [])

    def test_current_schema_has_no_write_only_validation_section(self) -> None:
        from x5crop.report.validation import CURRENT_REPORT_SECTIONS

        self.assertNotIn("schema_validation", CURRENT_REPORT_SECTIONS)
        self.assertNotIn("schema_validation", report_record_fixture())

    def test_report_uses_one_typed_projection_path(self) -> None:
        configuration_source = (
            PROJECT_ROOT / "x5crop/report/configuration.py"
        ).read_text(encoding="utf-8")
        record_source = (
            PROJECT_ROOT / "x5crop/report/record.py"
        ).read_text(encoding="utf-8")
        outputs_source = (
            PROJECT_ROOT / "x5crop/report/outputs.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("def _plain", configuration_source)
        self.assertIn("typed_read_model", configuration_source)
        self.assertNotIn("json_safe", record_source)
        self.assertNotIn("json_safe", outputs_source)

    def test_current_schema_rejects_unknown_fields_at_every_runtime_boundary(
        self,
    ) -> None:
        mutations = (
            lambda record: record.__setitem__("legacy_top_level", {}),
            lambda record: record["decision"].__setitem__(
                "review_reasons",
                [],
            ),
            lambda record: record["selection"]["candidates"][0][
                "provisional_geometry"
            ].__setitem__("outer_box", {}),
            lambda record: record["selection"]["candidates"][0][
                "evidence"
            ].__setitem__("risk_summary", {}),
            lambda record: record["output"]["frame_bleed_plan"].__setitem__(
                "global_overlap_bleed", 0
            ),
        )
        baseline = report_record_fixture()
        for mutation in mutations:
            record = deepcopy(baseline)
            mutation(record)
            with self.subTest(mutation=mutation):
                self.assertTrue(current_report_record_errors(record))

    def test_superseded_geometry_resolution_shape_is_not_current(self) -> None:
        record = report_record_fixture()
        resolution = record["selection"]["geometry_resolution"]
        resolution["coverage_resolved"] = resolution.pop(
            "content_preservation_compatible"
        )
        self.assertIn(
            "selection_incomplete",
            current_report_record_errors(record),
        )

    def test_malformed_current_record_is_rejected_without_raising(self) -> None:
        record = report_record_fixture()
        record["selection"]["candidates"][0]["provisional_geometry"][
            "count"
        ] = "not-an-integer"
        self.assertTrue(current_report_record_errors(record))

        invalid_counts = report_record_fixture()
        invalid_counts["configuration"]["physical"]["allowed_partial_counts"] = [[]]
        self.assertTrue(current_report_record_errors(invalid_counts))

        invalid_candidate = report_record_fixture()
        invalid_candidate["selection"]["candidates"][0] = None
        self.assertTrue(current_report_record_errors(invalid_candidate))

    def test_current_schema_executes_typed_cross_field_invariants(self) -> None:
        mutations = (
            lambda record: record["selection"]["geometry_resolution"].__setitem__(
                "count_resolved",
                False,
            ),
            lambda record: record["selection"]["candidates"][0][
                "count_hypothesis"
            ].__setitem__("count", 1),
            lambda record: record["selection"]["candidates"][0][
                "provisional_geometry"
            ].__setitem__("format_id", "half"),
            lambda record: record["analysis_identity"]["runtime_configuration"].__setitem__(
                "format_id",
                "half",
            ),
            lambda record: record["configuration"]["physical"].__setitem__(
                "frame_aspect",
                9.0,
            ),
            lambda record: record["analysis_identity"]["source"].__setitem__(
                "shape",
                [1, 1],
            ),
            lambda record: record["analysis_identity"]["source"].__setitem__(
                "name",
                "other.tif",
            ),
            lambda record: record["output"]["final_geometry"]["final_boxes"][0].__setitem__(
                "left",
                1,
            ),
        )
        for mutation in mutations:
            record = report_record_fixture()
            mutation(record)
            with self.subTest(mutation=mutation):
                self.assertTrue(current_report_record_errors(record))

    def test_unavailable_transform_drift_remains_explicitly_unavailable(self) -> None:
        workspace = detection_workspace_fixture(EvidenceState.UNAVAILABLE)
        record = report_record_for_final_detection(
            final_detection_fixture(),
            selection_fixture(),
            source="input.tif",
            profile=typed_read_model(image_profile_fixture()),
            workspace=workspace,
            output_files=[],
            review_copy=None,
            warnings=[],
            configuration=detection_configuration_read_model(
                get_detection_configuration("135", "partial")
            ),
            analysis_identity=analysis_identity_fixture(
                workspace_identity=workspace.identity,
            ),
        )
        self.assertIsNone(
            record["input"]["transform_geometry"]["projected_edge_drift_px"]
        )
        self.assertEqual(
            record["input"]["transform_geometry"]["outcome"],
            "photo_edge_pair_unavailable",
        )
        self.assertEqual(current_report_record_errors(record), [])

    def test_current_schema_requires_every_canonical_section(self) -> None:
        for key in (
            "input",
            "configuration",
            "selection",
            "decision",
            "output",
            "analysis_identity",
        ):
            record = report_record_fixture()
            record.pop(key)
            self.assertTrue(current_report_record_errors(record), key)

    def test_unknown_final_reason_is_rejected(self) -> None:
        record = report_record_fixture()
        record["decision"]["status"] = "needs_review"
        record["decision"]["gate"]["passed"] = False
        record["decision"]["final_review_reasons"] = [
            "unknown_physical_reason"
        ]
        self.assertIn(
            "unknown_final_review_reason:unknown_physical_reason",
            current_report_record_errors(record),
        )

    def test_status_and_decision_gate_must_agree(self) -> None:
        record = report_record_fixture()
        record["decision"]["gate"]["passed"] = False
        self.assertIn(
            "decision_gate_status_mismatch",
            current_report_record_errors(record),
        )

    def test_current_schema_rejects_duplicate_decision_check_codes(self) -> None:
        record = report_record_fixture()
        record["decision"]["gate"]["checks"].append(
            deepcopy(record["decision"]["gate"]["checks"][0])
        )
        self.assertTrue(current_report_record_errors(record))

    def test_current_schema_rejects_conflicting_observation_identity(self) -> None:
        record = report_record_fixture()
        provenances: list[dict] = []

        def collect(value) -> None:
            if isinstance(value, dict):
                if {
                    "root_measurement",
                    "observation_id",
                    "dependencies",
                    "description",
                    "boundary_anchors",
                } <= value.keys():
                    provenances.append(value)
                for child in value.values():
                    collect(child)
            elif isinstance(value, list):
                for child in value:
                    collect(child)

        collect(record)
        first = provenances[0]
        conflicting = next(
            item
            for item in provenances[1:]
            if item["observation_id"] != first["observation_id"]
            and any(
                item[field] != first[field]
                for field in (
                    "root_measurement",
                    "dependencies",
                    "description",
                    "boundary_anchors",
                )
            )
        )
        conflicting["observation_id"] = first["observation_id"]

        self.assertIn(
            "observation_identity_collision",
            current_report_record_errors(record),
        )

    def test_candidate_gate_cannot_carry_decision_stage_authority(self) -> None:
        record = report_record_fixture()
        check = record["selection"]["candidates"][0]["candidate_gate"][
            "checks"
        ][0]
        check["stage"] = "decision"
        check["final_review_reason"] = "content_preservation_unresolved"
        self.assertTrue(current_report_record_errors(record))

    def test_final_reasons_are_derived_from_decision_checks(self) -> None:
        record = report_record_fixture()
        record["decision"]["status"] = "needs_review"
        record["decision"]["gate"]["passed"] = False
        record["decision"]["gate"]["checks"][0]["state"] = "contradicted"
        record["decision"]["gate"]["checks"][0]["blocks"] = True
        record["decision"]["final_review_reasons"] = [
            "selection_geometry_disagreement"
        ]

        self.assertIn(
            "decision_gate_reason_mismatch",
            current_report_record_errors(record),
        )

    def test_current_schema_fields_are_required(self) -> None:
        missing_provenance = report_record_fixture()
        missing_provenance["selection"]["candidates"][0][
            "provisional_geometry"
        ]["separator_observations"][0]["provenance"].pop("boundary_anchors")
        self.assertIn(
            "separator_observation_invalid",
            current_report_record_errors(missing_provenance),
        )

        missing_transform = report_record_fixture()
        missing_transform["input"]["transform_geometry"].pop("outcome")
        self.assertIn(
            "input_incomplete",
            current_report_record_errors(missing_transform),
        )

        missing_frame_sides = report_record_fixture()
        missing_frame_sides["output"]["frame_bleed_plan"].pop("frame_sides")
        self.assertIn(
            "output_incomplete",
            current_report_record_errors(missing_frame_sides),
        )

    def test_report_has_no_generic_detail_or_legacy_reason_surface(self) -> None:
        record = report_record_fixture()
        self.assertNotIn("detail", record)
        self.assertNotIn("review_reasons", record)
        self.assertIn("final_review_reasons", record["decision"])
        self.assertNotIn("outer_box", record)
        self.assertNotIn("frame_boxes", record)
        self.assertNotIn("candidate_table", record)
        self.assertNotIn("evidence_summary", record)

    def test_report_excludes_temporary_photo_edge_section_turns(self) -> None:
        serialized = json.dumps(report_record_fixture(), sort_keys=True)

        self.assertNotIn("section_index", serialized)
        self.assertNotIn("local_short_axis_boundary_pair", serialized)

    def test_schema_identity_is_descriptive_not_version_named(self) -> None:
        record = report_record_fixture()
        self.assertEqual(record["schema_id"], "detection_report")
        self.assertEqual(
            record["schema_revision"],
            "cross_region_photo_edge_geometry",
        )
        self.assertNotIn("v4", record["schema_revision"])

    def test_report_result_has_one_record_surface(self) -> None:
        self.assertEqual(set(ReportResult.__dataclass_fields__), {"record"})
        with self.assertRaises(ValueError):
            ReportResult({})

    def test_runtime_names_report_results_by_their_actual_surface(self) -> None:
        source = (PROJECT_ROOT / "x5crop/runtime/app.py").read_text()
        self.assertNotIn("process_result", source)

    def test_output_preferences_are_not_foundation_domain_types(self) -> None:
        source = (PROJECT_ROOT / "x5crop/domain.py").read_text()
        self.assertNotIn("class AxisBleedParameters", source)

    def test_regression_tool_reads_only_current_canonical_geometry(self) -> None:
        self.assertEqual(
            DEFAULT_FIELDS,
            (
                "input.scan_canvas_evidence",
                "input.transform_geometry",
                "input.source_photo_edge_pairs",
                "input.mapped_photo_edge_pairs",
                "input.shared_short_axes",
                "input.source_lane_divider",
                "input.lane_divider",
                "decision.status",
                "decision.final_review_reasons",
                "selection.selected_rank",
                "selection.geometry_resolution",
                "output.final_geometry.frame_crop_envelopes",
                "output.final_geometry.final_boxes",
            ),
        )

    def test_analysis_identity_binds_implementation_and_workspace(self) -> None:
        identity = report_record_fixture()["analysis_identity"]

        self.assertEqual(len(identity["implementation_fingerprint"]), 64)
        self.assertEqual(
            identity["workspace_identity"],
            report_record_fixture()["input"]["workspace_identity"],
        )

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
