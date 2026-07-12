from __future__ import annotations

from dataclasses import fields, replace
import math
import unittest

from tools.tests.physical_gate_support import candidate_fixture, selection_fixture
from x5crop.detection.candidate.execution.model import CountHypothesisEvaluation
from x5crop.detection.candidate.model import AssessedCandidate, BuiltCandidate
from x5crop.detection.candidate.plan.count_hypotheses import (
    CountHypothesis,
    CountHypothesisPlan,
)
from x5crop.detection.candidate.selection.model import (
    CountResolution,
    GeometryCluster,
    GeometryResolution,
    SelectionResult,
)
from x5crop.detection.physical.model import (
    DualLaneSolution,
    ReviewOnlyGeometry,
    SequenceResiduals,
    SequenceSolution,
)
from x5crop.detection.evidence.transform_geometry import TransformGeometryEvidence
from x5crop.domain import (
    BoundaryPositionConstraint,
    Box,
    CropEnvelope,
    EvidenceState,
    FrameBoundary,
    FrameBoundaryReference,
    FrameDimensionPrior,
    HolderSpan,
    MeasurementProvenance,
    PixelInterval,
    SeparatorWidthConstraint,
    SequenceHypothesis,
    VisibleSequenceSpan,
)
from x5crop.output.model import (
    AxisBleedParameters,
    BoundaryOverlapProtection,
    FrameBleedPlan,
    FrameOverlapRequirement,
    FrameSideBleed,
    OutputGeometry,
)
from x5crop.units import ScanCalibration


def _provenance() -> MeasurementProvenance:
    return MeasurementProvenance("synthetic_measurement", "test", ())


class PhysicalModelInvariantTest(unittest.TestCase):
    def test_candidate_gate_evidence_rejects_state_measurement_drift(self) -> None:
        evidence = candidate_fixture().assessment.evidence
        for derived in (
            evidence.frame_dimensions,
            evidence.separator_sequence,
        ):
            with self.subTest(derived=type(derived).__name__):
                self.assertFalse(derived.__dataclass_fields__["state"].init)
                self.assertFalse(derived.__dataclass_fields__["reason"].init)
        invalid_factories = (
            lambda: replace(
                evidence.frame_topology,
                count_matches=False,
            ),
            lambda: replace(
                evidence.content_preservation,
                state=EvidenceState.SUPPORTED,
                uncovered_content=((0, 5),),
            ),
            lambda: replace(
                evidence.frame_dimensions,
                state=EvidenceState.SUPPORTED,
                photo_widths_px=(),
            ),
            lambda: replace(
                evidence.frame_sequence.conservation,
                state=EvidenceState.SUPPORTED,
                physical_sequence_px=PixelInterval.zero(),
            ),
            lambda: replace(
                evidence.independence,
                state=EvidenceState.SUPPORTED,
                cyclic_measurements=("synthetic_cycle",),
            ),
        )
        for factory in invalid_factories:
            with self.subTest(factory=factory), self.assertRaises(
                (TypeError, ValueError)
            ):
                factory()

    def test_transform_geometry_rejects_inconsistent_measurements(self) -> None:
        invalid_factories = (
            lambda: TransformGeometryEvidence(
                EvidenceState.SUPPORTED,
                False,
                math.nan,
                0.0,
                "non_finite_angle",
                None,
                None,
            ),
            lambda: TransformGeometryEvidence(
                EvidenceState.SUPPORTED,
                False,
                1.0,
                -1.0,
                "unapplied_angle",
                1.0,
                2.0,
            ),
            lambda: TransformGeometryEvidence(
                EvidenceState.CONTRADICTED,
                True,
                1.0,
                -1.0,
                "contradicted_applied_transform",
                1.0,
                2.0,
            ),
            lambda: TransformGeometryEvidence(
                EvidenceState.SUPPORTED,
                False,
                0.0,
                0.0,
                "incomplete_span_pair",
                1.0,
                None,
            ),
        )
        for factory in invalid_factories:
            with self.subTest(factory=factory), self.assertRaises(ValueError):
                factory()

    def test_candidate_geometry_has_no_duplicate_source_identity(self) -> None:
        for geometry_type in (
            SequenceSolution,
            DualLaneSolution,
            ReviewOnlyGeometry,
        ):
            with self.subTest(geometry_type=geometry_type):
                self.assertNotIn("source", geometry_type.__dataclass_fields__)

    def test_count_hypothesis_contains_identity_not_derived_eligibility(self) -> None:
        self.assertEqual(
            {field.name for field in fields(CountHypothesis)},
            {"count", "strip_mode", "source"},
        )

    def test_candidate_lifecycle_rejects_count_identity_drift(self) -> None:
        candidate = candidate_fixture()
        hypothesis = candidate.count_hypothesis
        mismatched = replace(hypothesis, count=hypothesis.count + 1)
        invalid_factories = (
            lambda: CountHypothesisPlan((), True, None),
            lambda: BuiltCandidate(candidate.geometry, mismatched, ()),
            lambda: AssessedCandidate(
                candidate.geometry,
                mismatched,
                candidate.assessment,
            ),
            lambda: CountHypothesisEvaluation(
                hypothesis,
                (candidate,),
                None,
            ),
            lambda: CountHypothesisEvaluation(
                CountHypothesis(
                    hypothesis.count + 1,
                    hypothesis.strip_mode,
                    hypothesis.source,
                ),
                (candidate,),
                selection_fixture(candidate),
            ),
        )
        for factory in invalid_factories:
            with self.subTest(factory=factory), self.assertRaises(ValueError):
                factory()

    def test_selection_models_reject_internally_inconsistent_states(self) -> None:
        candidate = candidate_fixture()
        selection = selection_fixture()
        invalid_factories = (
            lambda: GeometryResolution(
                EvidenceState.SUPPORTED,
                False,
                True,
                True,
                True,
                True,
                True,
                (),
            ),
            lambda: GeometryCluster((), candidate),
            lambda: CountResolution(0, (1,), (1,), None, "synthetic"),
            lambda: SelectionResult(
                candidate,
                (),
                selection.clusters,
                "uncontested",
                selection.geometry_resolution,
            ),
        )
        for factory in invalid_factories:
            with self.subTest(factory=factory), self.assertRaises(ValueError):
                factory()

    def test_pixel_intervals_and_residuals_require_finite_values(self) -> None:
        with self.assertRaises(ValueError):
            PixelInterval(math.nan, 1.0)
        with self.assertRaises(ValueError):
            SequenceResiduals(math.nan, None, 0.0)
        with self.assertRaises(ValueError):
            SequenceResiduals(None, None, -1.0)

    def test_physical_spans_and_priors_reject_impossible_geometry(self) -> None:
        with self.assertRaises(ValueError):
            replace(candidate_fixture().geometry, layout="diagonal")
        for span_type in (HolderSpan, VisibleSequenceSpan, CropEnvelope):
            with self.subTest(span_type=span_type), self.assertRaises(ValueError):
                span_type(Box(10, 0, 5, 10))
        with self.assertRaises(ValueError):
            FrameDimensionPrior(
                PixelInterval(0.0, 10.0),
                PixelInterval(1.0, 10.0),
                (36.0, 24.0),
                "synthetic",
                _provenance(),
            )

    def test_sequence_hypothesis_envelope_must_cover_visible_sequence(self) -> None:
        with self.assertRaises(ValueError):
            SequenceHypothesis(
                "invalid",
                VisibleSequenceSpan(Box(0, 0, 100, 100)),
                CropEnvelope(Box(10, 0, 90, 100)),
                "boundary_led",
                _provenance(),
                (),
            )

    def test_boundary_constraints_and_sources_have_consistent_identity(self) -> None:
        with self.assertRaises(ValueError):
            BoundaryPositionConstraint(0, PixelInterval.exact(10.0), _provenance())
        with self.assertRaises(ValueError):
            SeparatorWidthConstraint(1, PixelInterval(-1.0, 2.0), _provenance())
        with self.assertRaises(ValueError):
            FrameBoundary(
                1,
                PixelInterval.exact(10.0),
                "observed_separator",
                _provenance(),
            )
        with self.assertRaises(ValueError):
            FrameBoundary(
                1,
                PixelInterval.exact(10.0),
                "dimension_constrained",
                _provenance(),
            )

    def test_scan_calibration_rejects_impossible_trusted_state_and_axis(self) -> None:
        with self.assertRaises(ValueError):
            ScanCalibration(None, None, "tiff_resolution", True)
        calibration = ScanCalibration(10.0, 10.0, "tiff_resolution", True)
        with self.assertRaises(ValueError):
            calibration.px_per_mm("long")

    def test_output_models_reject_invalid_geometry_and_plan_state(self) -> None:
        with self.assertRaises(ValueError):
            OutputGeometry(
                CropEnvelope(Box(0, 0, 100, 100)),
                (Box(0, 0, 0, 100),),
            )
        with self.assertRaises(ValueError):
            FrameSideBleed(0, -1, 0, 0)
        with self.assertRaises(ValueError):
            BoundaryOverlapProtection(
                FrameBoundaryReference(None, 1),
                0,
                1,
                5,
                -1,
                5,
                "synthetic",
            )
        with self.assertRaises(ValueError):
            FrameBleedPlan(
                user_bleed=AxisBleedParameters(0, 0),
                frame_output_bounds=(Box(0, 0, 100, 100),),
                frame_sides=(FrameSideBleed(0, 0, 0, 0),),
                overlap_protection=(),
                unresolved_overlap_boundaries=(FrameBoundaryReference(None, 1),),
                feasible=True,
                reason="no_output_overlap",
            )

        boundary = FrameBoundaryReference(None, 1)
        complete = BoundaryOverlapProtection(
            boundary,
            0,
            1,
            5,
            5,
            5,
            "synthetic",
        )
        invalid_factories = (
            lambda: FrameOverlapRequirement(boundary, 0, 2, 5, True, "synthetic"),
            lambda: FrameOverlapRequirement(boundary, 0, 1, 5, True, ""),
            lambda: FrameBleedPlan(
                user_bleed=AxisBleedParameters(5, 2),
                frame_output_bounds=(Box(0, 0, 100, 100),),
                frame_sides=(FrameSideBleed(0, 4, 5, 2),),
                overlap_protection=(),
                unresolved_overlap_boundaries=(),
                feasible=True,
                reason="no_output_overlap",
            ),
            lambda: FrameBleedPlan(
                user_bleed=AxisBleedParameters(0, 0),
                frame_output_bounds=(
                    Box(0, 0, 100, 100),
                    Box(0, 0, 100, 100),
                ),
                frame_sides=(
                    FrameSideBleed(0, 0, 0, 0),
                    FrameSideBleed(1, 0, 0, 0),
                ),
                overlap_protection=(complete,),
                unresolved_overlap_boundaries=(boundary,),
                feasible=False,
                reason="output_overlap_unresolved",
            ),
            lambda: FrameBleedPlan(
                user_bleed=AxisBleedParameters(0, 0),
                frame_output_bounds=(
                    Box(0, 0, 100, 100),
                    Box(0, 0, 100, 100),
                ),
                frame_sides=(
                    FrameSideBleed(0, 0, 5, 0),
                    FrameSideBleed(1, 5, 0, 0),
                ),
                overlap_protection=(complete, complete),
                unresolved_overlap_boundaries=(),
                feasible=True,
                reason="output_overlap_protected",
            ),
            lambda: FrameBleedPlan(
                user_bleed=AxisBleedParameters(0, 0),
                frame_output_bounds=(Box(0, 0, 100, 100),),
                frame_sides=(FrameSideBleed(0, 0, 0, 0),),
                overlap_protection=(),
                unresolved_overlap_boundaries=(),
                feasible=True,
                reason="output_overlap_protected",
            ),
        )
        for factory in invalid_factories:
            with self.subTest(factory=factory), self.assertRaises(ValueError):
                factory()


if __name__ == "__main__":
    unittest.main()
