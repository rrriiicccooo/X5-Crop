from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import os
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
from dataclasses import fields, replace

from tools.tests.physical_gate_support import (
    final_detection_fixture,
    selection_fixture,
    transform_geometry_fixture,
    unavailable_calibration_fixture,
)
from x5crop.detection.final.model import FinalDetection
from x5crop.detection.evidence.transform_geometry import (
    TransformGeometryEvidence,
    TransformOutcome,
)
from x5crop.io.model import ImageProfile, TiffMetadata
from x5crop.io.tiff import compression_for_write
from x5crop.configuration.registry import get_detection_configuration
from x5crop.report.configuration import detection_configuration_read_model
from x5crop.report.model import ReportResult
from x5crop.report.record import report_record_for_final_detection
from x5crop.report.read_models import typed_read_model
from x5crop.report.restoration import final_detection_from_record
from x5crop.report.validation import current_report_record_errors
from x5crop.domain import WorkspaceExtent
from tools.regression.compare import DEFAULT_FIELDS


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _profile() -> ImageProfile:
    return ImageProfile(
        shape=(100, 200),
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


def _analysis_reuse_signature(
    format_id: str = "135",
    strip_mode: str = "full",
    source_name: str = "input.tif",
    shape: tuple[int, int] = (100, 200),
) -> dict:
    return {
        "script": "X5_Crop.py",
        "script_version": "4.9",
        "source": {
            "name": source_name,
            "size": 1,
            "mtime_ns": 1,
            "content_sha256": "0" * 64,
            "page": 0,
            "shape": list(shape),
            "dtype": "uint8",
            "axes": "YX",
            "photometric": "MINISBLACK",
        },
        "config": {
            "format_id": format_id,
            "layout": "horizontal",
            "strip_mode": strip_mode,
            "requested_count": None,
            "page": 0,
            "deskew": "off",
            "deskew_fallback": "off",
            "deskew_min_angle": 0.03,
            "deskew_max_angle": 2.0,
            "bleed_x": 20,
            "bleed_y": 10,
        },
        "configuration_fingerprint": "0" * 64,
    }


def _record() -> dict:
    return report_record_for_final_detection(
        final_detection_fixture(),
        selection_fixture(),
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
        transform_geometry=transform_geometry_fixture(),
        analysis_reuse_signature=_analysis_reuse_signature(),
    )


class OutputReadModelContractTest(unittest.TestCase):
    def test_tiff_compression_mode_is_exhaustive(self) -> None:
        with self.assertRaises(ValueError):
            compression_for_write(_profile(), "invalid")

    def test_transform_geometry_is_preprocess_input_not_diagnostics(self) -> None:
        record = _record()
        self.assertIn("transform_geometry", record["input"])
        self.assertNotIn("diagnostics", record)

    def test_input_records_resolution_metadata_not_candidate_calibration(self) -> None:
        input_detail = _record()["input"]
        self.assertIn("resolution_metadata", input_detail)
        self.assertNotIn("scan_calibration", input_detail)
        candidate = _record()["selection"]["candidates"][0]
        self.assertIn("scan_calibration", candidate["evidence"])

    def test_configuration_report_includes_boundary_path_measurements(self) -> None:
        configuration = get_detection_configuration("135", "full")
        detail = detection_configuration_read_model(configuration)

        self.assertEqual(
            detail["measurement"]["boundary_path"],
            typed_read_model(configuration.boundary_path),
        )

    def test_current_schema_rejects_missing_or_changed_boundary_path_parameters(self) -> None:
        missing = _record()
        missing["configuration"]["measurement"].pop("boundary_path", None)
        self.assertTrue(current_report_record_errors(missing))

        changed = _record()
        changed["configuration"]["measurement"]["boundary_path"] = {}
        self.assertTrue(current_report_record_errors(changed))

    def test_output_has_one_canonical_finalization_plan(self) -> None:
        output = _record()["output"]
        self.assertIn("finalization_plan", output)
        self.assertNotIn("decision_geometry", output)
        self.assertNotIn("frame_bleed_plan", output)

    def test_candidate_report_owns_sequence_conservation_directly(self) -> None:
        candidate = _record()["selection"]["candidates"][0]
        self.assertIn("inter_frame_spacings", candidate["candidate_geometry"])
        self.assertIn("sequence_conservation", candidate["evidence"])
        self.assertNotIn("frame_sequence", candidate["evidence"])

    def test_cache_restoration_rejects_geometry_not_produced_by_finalization(
        self,
    ) -> None:
        record = _record()
        record["output"]["final_geometry"]["frame_boxes"][0]["left"] -= 1
        with self.assertRaises(ValueError):
            final_detection_from_record(record)

    def test_analysis_reuse_is_disabled_for_every_debug_surface(self) -> None:
        from x5crop.runtime.analysis_reuse import result_from_reusable_analysis

        for debug, debug_analysis in ((True, False), (False, True)):
            config = SimpleNamespace(
                reuse_analysis=True,
                dry_run=False,
                debug=debug,
                debug_analysis=debug_analysis,
            )
            with self.subTest(debug=debug, debug_analysis=debug_analysis):
                self.assertIsNone(
                    result_from_reusable_analysis(
                        Path("unused.tif"),
                        config,
                        None,
                        None,
                        [],
                        {},
                    )
                )

    def test_analysis_reuse_source_identity_includes_file_content(self) -> None:
        from x5crop.runtime.analysis_reuse import source_cache_signature

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
            first = source_cache_signature(source, profile, 0)
            source.write_bytes(b"bbbb")
            os.utime(source, ns=(fixed_time_ns, fixed_time_ns))
            second = source_cache_signature(source, profile, 0)

        self.assertNotEqual(first, second)

    def test_configuration_fingerprint_has_no_stringification_fallback(self) -> None:
        source = (PROJECT_ROOT / "x5crop/runtime/analysis_reuse.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("default=str", source)

    def test_review_only_pipeline_produces_valid_current_report(self) -> None:
        from x5crop.cache.analysis import make_measurement_cache
        from x5crop.configuration.registry import get_detection_configuration
        from x5crop.detection.context import DetectionContext, DetectionRequest
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
        from x5crop.runtime.frame_bleed import prepare_frame_bleed
        from x5crop.output.model import AxisBleedParameters
        from tools.tests.physical_gate_support import transform_geometry_fixture

        configuration = get_detection_configuration("135-dual", "partial")
        gray = np.full((120, 240), 255, dtype=np.uint8)
        statistics = image_measurement_statistics(
            gray,
            configuration.preprocess.image_statistics,
        )
        cache = make_measurement_cache(
            gray,
            "horizontal",
            configuration.preprocess.content_evidence_image,
            statistics,
        )
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
            scan_calibration=unavailable_calibration_fixture(),
            request=DetectionRequest("horizontal", "partial", None),
            configuration=configuration,
            lane_configuration=None,
            measurement_cache=cache,
        )
        selection = choose_detection(context)
        from x5crop.detection.candidate.model import ReviewOnlyEvidence
        from x5crop.detection.physical.model import ReviewOnlyGeometry
        from tools.tests.physical_gate_support import separator_observation

        self.assertIsInstance(selection.selected.geometry, ReviewOnlyGeometry)
        self.assertIsInstance(
            selection.selected.assessment.evidence,
            ReviewOnlyEvidence,
        )
        self.assertIsNone(selection.selected.assessment.gate)
        with self.assertRaises(ValueError):
            replace(
                selection.selected.geometry,
                separator_observations=(separator_observation(120.0),),
            )
        bleed = prepare_frame_bleed(
            selection.selected,
            AxisBleedParameters(20, 10),
        )
        detection = apply_decision_gate(
            selection,
            bleed,
            transform_geometry_fixture(),
        )
        detection = finalize_detection(
            detection,
            finalization_plan_for_selection(
                selection,
                bleed,
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
            workspace_extent=WorkspaceExtent(240, 120),
            output_files=[],
            review_copy=None,
            warnings=[],
            configuration=detection_configuration_read_model(configuration),
            resolution_metadata=context.scan_calibration.metadata,
            transform_geometry=transform_geometry_fixture(),
            analysis_reuse_signature=_analysis_reuse_signature(
                "135-dual",
                "partial",
                "synthetic.tif",
                (120, 240),
            ),
        )
        self.assertEqual(current_report_record_errors(record), [])
        candidate_record = record["selection"]["candidates"][0]
        self.assertEqual(
            candidate_record["evidence"],
            {},
        )
        self.assertIsNone(candidate_record["candidate_gate"])

    def test_cache_reuse_does_not_resolve_configuration_from_report_data(self) -> None:
        source = (
            PROJECT_ROOT / "x5crop/runtime/analysis_reuse.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("configuration_bundle.configuration_for(", source)

    def test_typed_read_model_serializes_every_typed_result_field(self) -> None:
        from x5crop.domain import (
            FrameDimensionPrior,
            FrameDimensionPriorSource,
            MeasurementIdentity,
            MeasurementProvenance,
            PixelInterval,
        )
        from x5crop.report.read_models import typed_read_model

        value = FrameDimensionPrior(
            width_px=PixelInterval.exact(100.0),
            height_px=PixelInterval.exact(80.0),
            frame_size_mm=(36.0, 24.0),
            source=FrameDimensionPriorSource.SHORT_AXIS_ASPECT,
            provenance=MeasurementProvenance(
                MeasurementIdentity.FRAME_DIMENSIONS,
                "test",
                (),
            ),
        )
        self.assertEqual(
            set(typed_read_model(value)),
            {field.name for field in fields(FrameDimensionPrior)},
        )

    def test_final_detection_has_no_schema_restoration_wrapper(self) -> None:
        self.assertNotIn("restore", FinalDetection.__dict__)

    def test_fresh_record_is_current_schema_valid(self) -> None:
        self.assertEqual(current_report_record_errors(_record()), [])

    def test_current_schema_has_no_write_only_validation_section(self) -> None:
        from x5crop.report.validation import CURRENT_REPORT_SECTIONS

        self.assertNotIn("schema_validation", CURRENT_REPORT_SECTIONS)
        self.assertNotIn("schema_validation", _record())

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
                "candidate_geometry"
            ].__setitem__("outer_box", {}),
            lambda record: record["selection"]["candidates"][0][
                "evidence"
            ].__setitem__("risk_summary", {}),
            lambda record: record["output"]["finalization_plan"][
                "frame_bleed_plan"
            ].__setitem__("global_overlap_bleed", 0),
        )
        baseline = _record()
        for mutation in mutations:
            record = deepcopy(baseline)
            mutation(record)
            with self.subTest(mutation=mutation):
                self.assertTrue(current_report_record_errors(record))

    def test_superseded_geometry_resolution_shape_is_not_current(self) -> None:
        record = _record()
        resolution = record["selection"]["geometry_resolution"]
        resolution["coverage_resolved"] = resolution.pop(
            "content_preservation_compatible"
        )
        self.assertIn(
            "selection_incomplete",
            current_report_record_errors(record),
        )

    def test_malformed_current_record_is_rejected_without_raising(self) -> None:
        record = _record()
        record["selection"]["candidates"][0]["candidate_geometry"][
            "count"
        ] = "not-an-integer"
        self.assertTrue(current_report_record_errors(record))

        invalid_counts = _record()
        invalid_counts["configuration"]["physical"]["allowed_counts"] = [[]]
        self.assertTrue(current_report_record_errors(invalid_counts))

        invalid_candidate = _record()
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
                "candidate_geometry"
            ].__setitem__("format_id", "half"),
            lambda record: record["analysis_reuse_signature"]["config"].__setitem__(
                "format_id",
                "half",
            ),
            lambda record: record["configuration"]["physical"].__setitem__(
                "frame_aspect",
                9.0,
            ),
            lambda record: record["analysis_reuse_signature"]["source"].__setitem__(
                "shape",
                [1, 1],
            ),
            lambda record: record["analysis_reuse_signature"]["source"].__setitem__(
                "name",
                "other.tif",
            ),
            lambda record: record["output"]["final_geometry"]["frame_boxes"][0].__setitem__(
                "left",
                1,
            ),
        )
        for mutation in mutations:
            record = _record()
            mutation(record)
            with self.subTest(mutation=mutation):
                self.assertTrue(current_report_record_errors(record))

    def test_invalid_current_record_is_a_cache_miss(self) -> None:
        from x5crop.runtime.analysis_reuse import cached_record_matches

        record = _record()
        record["selection"]["geometry_resolution"]["count_resolved"] = False
        self.assertFalse(
            cached_record_matches(record, record["analysis_reuse_signature"])
        )

    def test_cache_restoration_failure_falls_back_to_fresh_detection(self) -> None:
        from x5crop.runtime.analysis_reuse import result_from_reusable_analysis

        config = SimpleNamespace(
            reuse_analysis=True,
            dry_run=False,
            debug=False,
            debug_analysis=False,
        )
        with (
            patch(
                "x5crop.runtime.analysis_reuse.find_reusable_analysis",
                return_value=_record(),
            ),
            patch(
                "x5crop.runtime.analysis_reuse._final_detection_from_record",
                side_effect=ValueError("invalid typed restoration"),
            ),
        ):
            self.assertIsNone(
                result_from_reusable_analysis(
                    Path("input.tif"),
                    config,
                    SimpleNamespace(root=Path("output")),
                    _profile(),
                    [],
                    _analysis_reuse_signature(),
                )
            )

    def test_unavailable_transform_span_remains_explicitly_unavailable(self) -> None:
        transform = TransformGeometryEvidence(
            TransformOutcome.DISABLED,
            0.0,
            None,
            None,
        )
        record = report_record_for_final_detection(
            final_detection_fixture(),
            selection_fixture(),
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
        self.assertIsNone(
            record["input"]["transform_geometry"]["span_px"]
        )
        self.assertEqual(
            record["input"]["transform_geometry"]["outcome"],
            "deskew_disabled",
        )
        self.assertEqual(current_report_record_errors(record), [])

    def test_current_schema_requires_every_canonical_section(self) -> None:
        for key in (
            "input",
            "configuration",
            "selection",
            "decision",
            "output",
            "analysis_reuse_signature",
        ):
            record = _record()
            record.pop(key)
            self.assertTrue(current_report_record_errors(record), key)

    def test_unknown_final_reason_is_rejected(self) -> None:
        record = _record()
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
        record = _record()
        record["decision"]["gate"]["passed"] = False
        self.assertIn(
            "decision_gate_status_mismatch",
            current_report_record_errors(record),
        )

    def test_current_schema_rejects_duplicate_decision_check_codes(self) -> None:
        record = _record()
        record["decision"]["gate"]["checks"].append(
            deepcopy(record["decision"]["gate"]["checks"][0])
        )
        self.assertTrue(current_report_record_errors(record))

    def test_candidate_gate_cannot_carry_decision_stage_authority(self) -> None:
        record = _record()
        check = record["selection"]["candidates"][0]["candidate_gate"][
            "checks"
        ][0]
        check["stage"] = "decision"
        check["final_review_reason"] = "content_preservation_unresolved"
        self.assertTrue(current_report_record_errors(record))

    def test_final_reasons_are_derived_from_decision_checks(self) -> None:
        record = _record()
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

    def test_cache_restoration_fields_are_required_by_current_schema(self) -> None:
        missing_provenance = _record()
        missing_provenance["selection"]["candidates"][0][
            "candidate_geometry"
        ]["separator_observations"][0]["provenance"].pop("boundary_anchors")
        self.assertIn(
            "separator_observation_invalid",
            current_report_record_errors(missing_provenance),
        )

        missing_transform = _record()
        missing_transform["input"]["transform_geometry"].pop("state")
        self.assertIn(
            "input_incomplete",
            current_report_record_errors(missing_transform),
        )

        missing_frame_sides = _record()
        missing_frame_sides["output"]["finalization_plan"][
            "frame_bleed_plan"
        ].pop("frame_sides")
        self.assertIn(
            "output_incomplete",
            current_report_record_errors(missing_frame_sides),
        )

    def test_report_has_no_generic_detail_or_legacy_reason_surface(self) -> None:
        record = _record()
        self.assertNotIn("detail", record)
        self.assertNotIn("review_reasons", record)
        self.assertIn("final_review_reasons", record["decision"])
        self.assertNotIn("outer_box", record)
        self.assertNotIn("frame_boxes", record)
        self.assertNotIn("candidate_table", record)
        self.assertNotIn("evidence_summary", record)

    def test_schema_identity_is_descriptive_not_version_named(self) -> None:
        record = _record()
        self.assertEqual(record["schema_id"], "detection_report")
        self.assertEqual(
            record["schema_revision"],
            "gray_sequence_integrity",
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
                "decision.status",
                "decision.final_review_reasons",
                "selection.selected_rank",
                "selection.geometry_resolution",
                "output.final_geometry.crop_envelope",
                "output.final_geometry.frame_boxes",
            ),
        )

    def test_cache_reuse_validates_current_schema_before_use(self) -> None:
        source = (PROJECT_ROOT / "x5crop/runtime/analysis_reuse.py").read_text()
        self.assertIn("current_report_record_errors(record)", source)
        self.assertNotIn('"review_reasons"', source)

    def test_cache_reuse_restores_final_detection_for_shared_output_actions(self) -> None:
        record = _record()
        detection = final_detection_from_record(record)

        self.assertEqual(
            detection.decision.status,
            record["decision"]["status"],
        )
        self.assertEqual(
            detection.decision.final_review_reasons,
            tuple(record["decision"]["final_review_reasons"]),
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
