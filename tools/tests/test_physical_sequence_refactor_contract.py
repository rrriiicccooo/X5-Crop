from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.physical_gate_support import (
    candidate_fixture,
    selection_fixture,
    separator_constraints,
    separator_observation,
    transform_geometry_fixture,
)
from x5crop.detection.candidate.selection.model import GeometryResolution
from x5crop.detection.decision.decision_gate import apply_decision_gate
from x5crop.detection.evidence.content.frame_support import (
    FrameContentEvidence,
    FrameContentObservation,
)
from x5crop.detection.evidence.content.preservation import (
    content_preservation_evidence,
)
from x5crop.detection.evidence.frame_coverage import FrameCoverageEvidence
from x5crop.detection.evidence.partial_edge import PartialEdgeSafetyEvidence
from x5crop.detection.evidence.sequence_content_alignment import (
    SequenceContentAlignmentEvidence,
)
from x5crop.detection.physical.boundary import HolderOcclusionEvidence
from x5crop.detection.physical.separator.assignment import (
    assign_observation_to_boundary,
)
from x5crop.detection.physical.sequence_solver import solve_frame_sequence
from x5crop.detection.physical.spacing import spacing_hypothesis
from x5crop.domain import (
    AxisBleedParameters,
    Box,
    EvidenceState,
    FrameDimensionPrior,
    MeasurementProvenance,
    PixelInterval,
    VisibleSequenceSpan,
)
from x5crop.output.bleed_plan import output_bleed_plan
from x5crop.policies.registry import get_detection_policy
from x5crop.units import ScanCalibration


class PhysicalSequenceRefactorContractTest(unittest.TestCase):
    def test_sequence_solver_reports_assignment_budget_exhaustion(self) -> None:
        result = solve_frame_sequence(
            (
                separator_observation(100.0),
                separator_observation(200.0),
            ),
            (),
            VisibleSequenceSpan(Box(0, 0, 300, 100)),
            3,
            FrameDimensionPrior(
                PixelInterval.exact(100.0),
                PixelInterval.exact(100.0),
                ((36.0, 24.0),),
                "synthetic",
                MeasurementProvenance(
                    "frame_dimensions",
                    "synthetic",
                    ("physical_frame_size",),
                ),
            ),
            HolderOcclusionEvidence.not_applicable(),
            (),
            1,
        )
        self.assertTrue(result.search_budget_exhausted)

    def test_broad_tonal_band_cannot_become_independent_separator(self) -> None:
        observation = separator_observation(
            325.0,
            start=250.0,
            end=400.0,
        )
        assignment = assign_observation_to_boundary(
            3,
            observation,
            *separator_constraints(
                3,
                PixelInterval(246.0, 404.0),
                PixelInterval(0.0, 50.0),
            ),
        )
        self.assertFalse(assignment.independent)

    def test_geometry_derived_negative_spacing_is_not_supported_overlap(self) -> None:
        spacing = spacing_hypothesis(
            1,
            PixelInterval(-20.0, -10.0),
            MeasurementProvenance(
                "frame_geometry",
                "synthetic",
                ("frame_dimensions",),
            ),
        )
        self.assertEqual(spacing.kind, "overlap")
        self.assertEqual(spacing.state, EvidenceState.UNAVAILABLE)

    def test_sequence_solver_cannot_emit_non_monotonic_frames(self) -> None:
        result = solve_frame_sequence(
            (separator_observation(280.0, start=275.0, end=285.0),),
            (),
            VisibleSequenceSpan(Box(0, 0, 300, 100)),
            3,
            FrameDimensionPrior(
                PixelInterval(10.0, 290.0),
                PixelInterval.exact(100.0),
                ((36.0, 24.0),),
                "synthetic",
                MeasurementProvenance(
                    "frame_dimensions",
                    "synthetic",
                    ("physical_frame_size",),
                ),
            ),
            HolderOcclusionEvidence.not_applicable(),
            (),
            10_000,
        )
        self.assertTrue(all(frame.valid() for frame in result.frames))
        self.assertTrue(
            all(
                left.right <= right.left
                for left, right in zip(result.frames, result.frames[1:])
            )
        )

    def test_content_at_frame_edges_is_not_undercrop(self) -> None:
        frame_content = FrameContentEvidence(
            EvidenceState.SUPPORTED,
            "content_observed",
            0.2,
            0.4,
            0.4,
            (
                FrameContentObservation(1, 0.4, 0.4, True, ("right",)),
                FrameContentObservation(2, 0.4, 0.4, True, ("left",)),
            ),
            "synthetic",
        )
        alignment = SequenceContentAlignmentEvidence(
            EvidenceState.SUPPORTED,
            "content_inside_visible_sequence",
            Box(0, 0, 200, 100),
            Box(0, 0, 200, 100),
            ("synthetic",),
            (),
            (),
            False,
            False,
            0,
            0,
            0,
            0,
            (),
        )
        partial = PartialEdgeSafetyEvidence(
            EvidenceState.NOT_APPLICABLE,
            "not_partial",
            False,
            1,
            1,
            EvidenceState.SUPPORTED,
            EvidenceState.NOT_APPLICABLE,
            False,
            (),
        )
        coverage = FrameCoverageEvidence(
            EvidenceState.SUPPORTED,
            "content_runs_covered",
            (0, 200),
            (0, 200),
            ((0, 100), (100, 200)),
            ((0, 200),),
            (),
            0,
        )
        evidence = content_preservation_evidence(
            frame_content,
            alignment,
            partial,
            coverage,
        )
        self.assertEqual(evidence.state, EvidenceState.SUPPORTED)

    def test_unresolved_auto_count_cannot_be_approved(self) -> None:
        candidate = candidate_fixture()
        selection = replace(
            selection_fixture(candidate),
            geometry_resolution=GeometryResolution(
                EvidenceState.UNAVAILABLE,
                False,
                False,
                False,
                False,
                True,
                True,
                ("count_unresolved",),
            ),
        )
        bleed = output_bleed_plan(
            False,
            0.0,
            AxisBleedParameters(20, 10),
            get_detection_policy("135", "partial").output,
            long_axis_bleed_capacity_px=50,
        )
        detection = apply_decision_gate(
            selection,
            bleed,
            transform_geometry_fixture(),
            ScanCalibration(None, None, "unavailable", False),
            image_width=200,
            image_height=100,
        )
        self.assertEqual(detection.status, "needs_review")


if __name__ == "__main__":
    unittest.main()
