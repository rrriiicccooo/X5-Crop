from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import os
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
import numpy as np
from dataclasses import asdict, fields, replace

from tools.tests.physical_gate_support import (
    final_detection_fixture,
    selection_fixture,
    transform_geometry_fixture,
)
from x5crop.detection.decision.model import FinalDetection
from x5crop.io.model import ImageProfile
from x5crop.configuration.registry import get_detection_configuration
from x5crop.report.configuration import detection_configuration_read_model
from x5crop.report.model import ReportResult
from x5crop.report.record import report_record_for_final_detection
from x5crop.report.restoration import final_detection_from_record
from x5crop.report.validation import current_report_record_errors
from tools.regression.compare import DEFAULT_FIELDS


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _profile() -> ImageProfile:
    return ImageProfile(
        (120, 240),
        "uint8",
        "YX",
        "MINISBLACK",
        "NONE",
        None,
        8,
        1,
        None,
        None,
        None,
        None,
    )


def _analysis_reuse_signature(
    format_id: str = "135",
    strip_mode: str = "full",
) -> dict:
    return {
        "script": "X5_Crop.py",
        "script_version": "4.9",
        "source": {
            "name": "input.tif",
            "size": 1,
            "mtime_ns": 1,
            "content_sha256": "0" * 64,
            "page": 0,
            "shape": [120, 240],
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
        profile=asdict(_profile()),
        output_files=[],
        review_copy=None,
        warnings=[],
        configuration=detection_configuration_read_model(
            get_detection_configuration("135", "full")
        ),
        transform_geometry=transform_geometry_fixture(),
        analysis_reuse_signature=_analysis_reuse_signature(),
    )


class OutputReadModelContractTest(unittest.TestCase):
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
            (1, 4),
            "uint8",
            "YX",
            "MINISBLACK",
            "NONE",
            None,
            8,
            1,
            None,
            None,
            None,
            None,
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

    def test_review_only_pipeline_produces_valid_current_report(self) -> None:
        from x5crop.cache.analysis import make_measurement_cache
        from x5crop.configuration.registry import get_detection_configuration
        from x5crop.detection.context import DetectionContext, DetectionRequest
        from x5crop.detection.decision.decision_gate import apply_decision_gate
        from x5crop.detection.final.finalize import finalize_detection
        from x5crop.detection.pipeline import choose_detection
        from x5crop.io.model import ImageProfile
        from x5crop.image.statistics import image_measurement_statistics
        from x5crop.report.configuration import detection_configuration_read_model
        from x5crop.report.record import report_record_for_final_detection
        from x5crop.report.validation import current_report_record_errors
        from x5crop.runtime.frame_bleed import prepare_frame_bleed
        from x5crop.output.model import AxisBleedParameters
        from x5crop.units import ScanCalibration
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
            gray.shape,
            "uint8",
            "YX",
            "MINISBLACK",
            "NONE",
            None,
            8,
            1,
            None,
            None,
            None,
            None,
        )
        context = DetectionContext(
            scan_calibration=ScanCalibration(None, None, "unavailable", False),
            request=DetectionRequest("horizontal", "partial", None),
            configuration=configuration,
            lane_configuration=None,
            measurement_cache=cache,
        )
        selection = choose_detection(context)
        from x5crop.detection.physical.model import ReviewOnlyGeometry
        from tools.tests.physical_gate_support import separator_observation

        self.assertIsInstance(selection.selected.geometry, ReviewOnlyGeometry)
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
            context.scan_calibration,
            image_width=240,
            image_height=120,
        )
        detection = finalize_detection(
            detection,
            image_width=240,
            image_height=120,
        )
        self.assertEqual(
            detection.final_review_reasons,
            ("automatic_processing_not_supported",),
        )
        record = report_record_for_final_detection(
            detection,
            selection,
            source="synthetic.tif",
            profile=asdict(profile),
            output_files=[],
            review_copy=None,
            warnings=[],
            configuration=detection_configuration_read_model(configuration),
            transform_geometry=transform_geometry_fixture(),
            analysis_reuse_signature=_analysis_reuse_signature(
                "135-dual",
                "partial",
            ),
        )
        self.assertEqual(current_report_record_errors(record), [])

    def test_cache_reuse_does_not_resolve_configuration_from_report_data(self) -> None:
        source = (
            PROJECT_ROOT / "x5crop/runtime/analysis_reuse.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("configuration_bundle.configuration_for(", source)

    def test_typed_read_model_serializes_every_typed_result_field(self) -> None:
        from x5crop.domain import MeasurementProvenance, PixelInterval
        from x5crop.domain import FrameDimensionPrior
        from x5crop.report.read_models import typed_read_model

        value = FrameDimensionPrior(
            width_px=PixelInterval.exact(100.0),
            height_px=PixelInterval.exact(80.0),
            frame_size_options_mm=((36.0, 24.0),),
            source="test",
            provenance=MeasurementProvenance("frame_dimensions", "test", ()),
        )
        self.assertEqual(
            set(typed_read_model(value)),
            {field.name for field in fields(FrameDimensionPrior)},
        )

    def test_final_detection_has_no_schema_restoration_wrapper(self) -> None:
        self.assertNotIn("restore", FinalDetection.__dict__)

    def test_fresh_record_is_current_schema_valid(self) -> None:
        self.assertEqual(current_report_record_errors(_record()), [])

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
            lambda record: record["output"]["frame_bleed_plan"].__setitem__(
                "global_overlap_bleed",
                0,
            ),
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

    def test_unavailable_transform_span_remains_explicitly_unavailable(self) -> None:
        transform = replace(
            transform_geometry_fixture(),
            span_px=None,
            span_threshold_px=None,
        )
        record = report_record_for_final_detection(
            final_detection_fixture(),
            selection_fixture(),
            source="input.tif",
            profile=asdict(_profile()),
            output_files=[],
            review_copy=None,
            warnings=[],
            configuration=detection_configuration_read_model(
                get_detection_configuration("135", "full")
            ),
            transform_geometry=transform,
            analysis_reuse_signature=_analysis_reuse_signature(),
        )
        self.assertIsNone(
            record["diagnostics"]["transform_geometry"]["span_px"]
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
        missing_transform["diagnostics"]["transform_geometry"].pop("state")
        self.assertIn(
            "transform_geometry_incomplete",
            current_report_record_errors(missing_transform),
        )

        missing_frame_sides = _record()
        missing_frame_sides["output"]["frame_bleed_plan"].pop("frame_sides")
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
            "physical_sequence_resolution",
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

        self.assertEqual(detection.status, record["decision"]["status"])
        self.assertEqual(
            detection.final_review_reasons,
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
