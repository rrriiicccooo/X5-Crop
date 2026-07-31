from __future__ import annotations

from dataclasses import fields
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import numpy as np

from tools.regression.golden_baseline import (
    GOLD_ACCURACY_PATH,
    load_gold_records,
)
from tools.regression.safe_crop_acceptance import (
    AcceptancePreflightError,
    RESULT_SCHEMA,
    SUMMARY_SCHEMA,
    _validate_output_root,
    validate_acceptance_result_record,
    validate_acceptance_summary_record,
)
from x5crop.configuration.model import FrameCountMode
from x5crop.configuration.registry import get_detection_configuration
from x5crop.detection.candidate.assessment.candidate_gate import (
    candidate_gate_assessment,
)
from x5crop.detection.decision.decision_gate import apply_decision_gate
from x5crop.detection.photo_geometry.detector import (
    _rotation_coherent_short_candidates,
)
from x5crop.detection.photo_geometry.model import (
    FirstPhotoStartAssessment,
    FirstPhotoStartOutcome,
    FrameGeometryState,
    FrameSequenceGeometrySolution,
    GridInferredBlankOutputGeometry,
    GridSlotTranslationAssessment,
    GridSlotTranslationOutcome,
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    PhotoBoundaryCoverageReceipt,
    PhotoBoundaryMeasurementField,
    PhotoBoundaryMeasurementQuery,
    PhotoBoundaryMeasurementSet,
    PhotoSequenceTranslationAssessment,
    PhotoSequenceTranslationOutcome,
    QueryPurpose,
    BoundaryAxis,
    ResolvedOutputSlots,
    SequenceWorkReceipt,
)
from x5crop.detection.pipeline import choose_detection
from x5crop.detection.workspace import prepare_detection_workspace
from x5crop.domain import (
    EvidenceState,
    FiniteInterval,
    PositiveInterval,
)
from x5crop.io.model import ImageProfile, TiffMetadata


ROOT = Path(__file__).resolve().parents[2]
DIAGNOSTIC_COHORT_PATH = (
    ROOT
    / "tools"
    / "regression"
    / "cohorts"
    / "diagnostic_unreviewed.jsonl"
)


def _profile(shape: tuple[int, int]) -> ImageProfile:
    return ImageProfile(
        shape=shape,
        dtype="uint8",
        axes="YX",
        photometric="MINISBLACK",
        compression="NONE",
        sample_format=None,
        bits_per_sample=(8,),
        samples_per_pixel=1,
        planar_config=None,
        resolution=None,
        resolution_unit=None,
        icc_profile=None,
        metadata=TiffMetadata(None, None, None, ()),
    )


def _candidate(
    pixels: np.ndarray,
    *,
    format_id: str = "135",
    strip_mode: str = "partial",
    requested_count: int | None = None,
    layout: str = "horizontal",
):
    configuration = get_detection_configuration(
        format_id,
        strip_mode,
        requested_count,
    )
    workspace = prepare_detection_workspace(
        pixels,
        _profile(tuple(int(value) for value in pixels.shape)),
        layout,
        configuration,
        None,
    )
    return workspace, configuration, choose_detection(
        workspace,
        configuration,
        None,
    )


def _model_state(ordinal: int) -> FrameGeometryState:
    return FrameGeometryState(
        state_id=f"test:model:{ordinal}",
        lane_id="lane:0",
        lane_ordinal=ordinal,
        photo_geometry=None,
        aperture_label="36x24",
        rotation_class_id="model_only_no_rotation_evidence",
        ownership="unassigned",
        interaction_before=None,
        interaction_after=None,
        model_only=True,
        physical_residual_px=0.0,
        measurement_uncertainty_px=0.0,
    )


class SourceCoordinateGeometryContractTest(unittest.TestCase):
    def test_rotation_class_sweep_uses_compatible_local_alternatives(
        self,
    ) -> None:
        def candidate(minimum: float, maximum: float):
            return SimpleNamespace(
                angle_interval_degrees=FiniteInterval(
                    minimum,
                    maximum,
                )
            )

        rows = (
            (candidate(1.0, 1.5), candidate(-0.2, 0.2)),
            (candidate(-1.5, -1.0), candidate(-0.1, 0.3)),
        )
        coherent, residual = _rotation_coherent_short_candidates(rows)
        self.assertTrue(all(row for row in coherent))
        self.assertTrue(
            all(
                item.angle_interval_degrees.contains(0.0)
                for row in coherent
                for item in row
            )
        )
        self.assertGreaterEqual(residual, 0.0)

    def test_measurement_spec_is_the_frozen_calibration_authority(self) -> None:
        spec = PHOTO_BOUNDARY_MEASUREMENT_SPEC
        self.assertEqual(spec.lattice_spacing_mm(12.0), 2.0)
        self.assertEqual(spec.lattice_spacing_mm(36.0), 3.0)
        self.assertEqual(spec.lattice_spacing_mm(120.0), 4.0)
        self.assertEqual(spec.local_window_mm, 0.25)
        self.assertEqual(spec.transition_gap_mm, 0.05)
        self.assertEqual(spec.maximum_transition_interval_mm, 1.0)
        self.assertEqual(spec.huber_irls_rounds, 4)
        self.assertEqual(spec.maximum_streaming_block_pixels, 1_048_576)
        self.assertEqual(len(spec.nominal_calibration_sample_ids), 8)
        self.assertEqual(spec.stress_excluded_sample_id, "S098")
        self.assertNotIn(
            spec.stress_excluded_sample_id,
            spec.nominal_calibration_sample_ids,
        )
        self.assertTrue(spec.calibration_receipt_id.startswith("sha256:"))

    def test_measurement_field_is_immutable_and_partial_query_is_unavailable(
        self,
    ) -> None:
        gray = np.zeros((20, 30), dtype=np.uint8)
        field = PhotoBoundaryMeasurementField(gray, "horizontal")
        self.assertFalse(field.source_gray.flags.writeable)
        query = PhotoBoundaryMeasurementQuery(
            query_id="query:test",
            registration_index=0,
            lane_id="lane:0",
            purpose=QueryPurpose.SEQUENCE_ANCHOR_TILE,
            boundary_axis=BoundaryAxis.X,
            trace_positions_px=(2, 4, 6, 8),
            search_intervals_px=(
                FiniteInterval(0.0, 29.0),
            )
            * 4,
            expected_support_px=20.0,
            boundary_axis_scale_px_per_mm=PositiveInterval(1.0, 1.1),
            trace_axis_scale_px_per_mm=PositiveInterval(1.0, 1.1),
            measurement_halo_px=2,
            search_proposal_ids=("anchor-domain:test",),
        )
        coverage = PhotoBoundaryCoverageReceipt(
            query_id=query.query_id,
            registered_trace_count=4,
            completed_trace_count=3,
            registered_coordinate_count=120,
            completed_coordinate_count=90,
            pixel_query_count=90,
            streaming_block_count=1,
            peak_temporary_bytes=4096,
            shared_measurement_reuse_count=0,
            complete=False,
        )
        measurement = PhotoBoundaryMeasurementSet(
            query=query,
            state=EvidenceState.UNAVAILABLE,
            transitions=(),
            coverage=coverage,
        )
        self.assertEqual(measurement.state, EvidenceState.UNAVAILABLE)
        with self.assertRaises(ValueError):
            PhotoBoundaryMeasurementSet(
                query=query,
                state=EvidenceState.SUPPORTED,
                transitions=(),
                coverage=coverage,
            )

    def test_capacity_auto_keeps_fixed_slots_and_complete_anchor_coverage(
        self,
    ) -> None:
        pixels = np.zeros((100, 720), dtype=np.uint8)
        pixels[:, 125:235] = 180
        pixels[:, 242:352] = 180
        workspace, configuration, candidate = _candidate(pixels)
        self.assertEqual(configuration.count_request.mode, FrameCountMode.AUTO)
        self.assertEqual(
            candidate.resolved_output_slots,
            ResolvedOutputSlots((6,)),
        )
        lane = candidate.geometry.lane_reconstructions[0]
        tiles = tuple(
            sorted(
                lane.anchor_domain.tiles,
                key=lambda item: item.core_px.minimum,
            )
        )
        self.assertEqual(tiles[0].core_px.minimum, 0.0)
        self.assertGreaterEqual(
            tiles[-1].core_px.maximum,
            lane.anchor_domain.long_axis_extent_px,
        )
        self.assertTrue(
            all(
                left.core_px.maximum == right.core_px.minimum
                for left, right in zip(tiles, tiles[1:])
            )
        )
        self.assertEqual(
            set(lane.anchor_domain.grid_execution_order),
            {tile.tile_id for tile in tiles},
        )
        self.assertEqual(
            set(lane.anchor_domain.outer_execution_order),
            {tile.tile_id for tile in tiles},
        )
        self.assertIs(
            workspace.boundary_measurement_field.source_gray,
            workspace.source_gray,
        )

    def test_all_blank_135_auto_uses_grid_geometry_without_photo_geometry(
        self,
    ) -> None:
        _workspace, _configuration, candidate = _candidate(
            np.zeros((100, 720), dtype=np.uint8),
        )
        self.assertTrue(candidate.gate.passed)
        self.assertEqual(candidate.output_slot_count, 6)
        lane = candidate.geometry.lane_reconstructions[0]
        assert lane.solution is not None
        self.assertEqual(
            lane.solution.photo_translation.outcome,
            PhotoSequenceTranslationOutcome
            .NOT_APPLICABLE_NO_PHOTO_GEOMETRY,
        )
        self.assertEqual(
            lane.solution.first_photo_start.outcome,
            FirstPhotoStartOutcome.NOT_APPLICABLE,
        )
        self.assertEqual(
            lane.solution.grid_translation.outcome,
            GridSlotTranslationOutcome.MODEL_BOUNDED_OUTPUT_EQUIVALENT,
        )
        self.assertTrue(
            all(
                state.photo_geometry is None
                for state in lane.solution.selected_states
            )
        )
        self.assertTrue(
            all(
                isinstance(item, GridInferredBlankOutputGeometry)
                and item.provenance == "grid_inferred_blank"
                for item in lane.resolved_output_geometries
            )
        )

    def test_dp_limit_applies_after_full_state_join(self) -> None:
        state = _model_state(1)
        translation = PhotoSequenceTranslationAssessment(
            outcome=(
                PhotoSequenceTranslationOutcome
                .NOT_APPLICABLE_NO_PHOTO_GEOMETRY
            ),
            interval_px=None,
            observation_ids=(),
            competing_class_ids=(),
        )
        grid = GridSlotTranslationAssessment(
            outcome=GridSlotTranslationOutcome.SCAN_CANVAS_PROFILE_BOUNDED,
            interval_px=FiniteInterval.exact(0.0),
            protected_footprint_equivalence_class_id=None,
            competing_class_ids=(),
        )
        first = FirstPhotoStartAssessment(
            outcome=FirstPhotoStartOutcome.NOT_APPLICABLE,
            lane_ordinal=None,
            interval_px=None,
            observation_ids=(),
        )
        work = SequenceWorkReceipt(*(0 for _ in range(12)))
        with self.assertRaises(ValueError):
            FrameSequenceGeometrySolution(
                solution_id="solution:test",
                lane_id="lane:0",
                aperture_label="36x24",
                selected_states=(state,),
                undominated_states_by_ordinal=(
                    tuple(_model_state(1) for _ in range(4)),
                ),
                photo_translation=translation,
                grid_translation=grid,
                first_photo_start=first,
                work=work,
                unresolved_codes=(),
            )

    def test_gate_maps_only_concrete_output_risk_to_review(self) -> None:
        base = dict(
            scan_canvas_state=EvidenceState.SUPPORTED,
            source_content_state=EvidenceState.UNAVAILABLE,
            grid_search_coverage_state=EvidenceState.SUPPORTED,
            output_slot_count_state=EvidenceState.SUPPORTED,
            slot_ordinal_state=EvidenceState.SUPPORTED,
            slot_ownership_state=EvidenceState.SUPPORTED,
            known_content_containment_state=EvidenceState.UNAVAILABLE,
            source_lane_geometry_state=EvidenceState.SUPPORTED,
            output_protection_state=EvidenceState.SUPPORTED,
            output_transform_state=EvidenceState.SUPPORTED,
        )
        safe = candidate_gate_assessment(**base)
        self.assertEqual(
            apply_decision_gate(safe, FrameCountMode.AUTO).status,
            "approved_auto",
        )
        risky = candidate_gate_assessment(
            **{
                **base,
                "slot_ordinal_state": EvidenceState.CONTRADICTED,
            }
        )
        decision = apply_decision_gate(risky, FrameCountMode.AUTO)
        self.assertEqual(decision.status, "needs_review")
        self.assertEqual(
            tuple(check.code for check in risky.blocking_checks),
            ("slot_ordinal_assignment",),
        )


class ValidationRoleContractTest(unittest.TestCase):
    def test_tracked_gold_is_the_only_accuracy_owner(self) -> None:
        records = load_gold_records()
        self.assertEqual(len(records), 9)
        self.assertEqual(
            sum(len(record["count_modes"]) for record in records),
            14,
        )
        self.assertEqual(
            sum(
                expectation == "must_approve_safe"
                for record in records
                for expectation in record[
                    "decision_expectations"
                ].values()
            ),
            12,
        )
        self.assertEqual(
            sum(
                expectation == "must_review_with_competition"
                for record in records
                for expectation in record[
                    "decision_expectations"
                ].values()
            ),
            2,
        )
        stress = next(
            record for record in records if record["sample_id"] == "S098"
        )
        self.assertEqual(stress["calibration_role"], "stress_excluded")
        s055 = next(
            record for record in records if record["sample_id"] == "S055"
        )
        self.assertEqual(
            set(s055["decision_expectations"].values()),
            {"must_review_with_competition"},
        )
        self.assertTrue(GOLD_ACCURACY_PATH.is_file())
        self.assertFalse(
            GOLD_ACCURACY_PATH.with_name("safe_crop_acceptance.jsonl").exists()
        )

    def test_diagnostic_cohort_has_no_filename_expectation_authority(
        self,
    ) -> None:
        rows = tuple(
            json.loads(line)
            for line in DIAGNOSTIC_COHORT_PATH.read_text(
                encoding="utf-8"
            ).splitlines()
            if line.strip()
        )
        self.assertEqual(len(rows), 111)
        self.assertEqual(
            {row["validation_role"] for row in rows},
            {"diagnostic_unreviewed"},
        )
        forbidden = {
            "expected_status",
            "acceptance_class",
            "filename_count",
            "must_approve",
        }
        self.assertTrue(
            all(forbidden.isdisjoint(row) for row in rows)
        )

    def test_current_gold_result_and_summary_schemas_are_strict(self) -> None:
        result = {
            "result_schema": RESULT_SCHEMA,
            "decision_status": "terminal_failure",
            "passed": False,
            "expectation": "must_approve_safe",
        }
        validate_acceptance_result_record(result)
        summary = {
            "summary_schema": SUMMARY_SCHEMA,
            "accuracy_authority": (
                "nine_source_sha_bound_user_confirmed_gold"
            ),
            "diagnostic_111_accuracy_verdict": "not_applicable",
            "passed": False,
        }
        validate_acceptance_summary_record(summary)
        with self.assertRaises(ValueError):
            validate_acceptance_result_record(
                {**result, "expectation": "filename_pass"}
            )

    def test_gold_output_root_must_be_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "existing").write_text("occupied", encoding="utf-8")
            with self.assertRaises(AcceptancePreflightError):
                _validate_output_root(root)


if __name__ == "__main__":
    unittest.main()
