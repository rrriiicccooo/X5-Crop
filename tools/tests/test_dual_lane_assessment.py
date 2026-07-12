from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.physical_gate_support import candidate_fixture, separator_observation
from x5crop.detection.candidate.assessment.dual_lane import assess_dual_lane_candidate
from x5crop.detection.candidate.model import BuiltCandidate
from x5crop.domain import EvidenceState
from x5crop.domain import PixelInterval
from x5crop.detection.physical.spacing import observed_spacing_evidence
from x5crop.domain import CropEnvelope, HolderSpan, VisibleSequenceSpan
from x5crop.domain import Box, MeasurementProvenance


def _parent(lane):
    frames = tuple(Box(index * 100, 0, (index + 1) * 100, 100) for index in range(4))
    geometry = replace(
        lane.geometry,
        format_id="135-dual",
        count=4,
        holder_span=HolderSpan(Box(0, 0, 400, 100)),
        visible_sequence_span=VisibleSequenceSpan(Box(0, 0, 400, 100)),
        crop_envelope=CropEnvelope(Box(0, 0, 400, 100)),
        frames=frames,
        separator_observations=(
            separator_observation(100.0, start=95.0, end=105.0),
            separator_observation(200.0, start=195.0, end=205.0),
        ),
        separator_assignments=(),
        frame_boundaries=(),
        sequence_provenance=MeasurementProvenance(
            "lane_divider_profile",
            "measured_gutter",
            ("gray_work",),
        ),
        lane_boxes=(Box(0, 0, 400, 50), Box(0, 50, 400, 100)),
    )
    return BuiltCandidate(geometry, lane.count_hypothesis, ("dual_lane",))


class DualLaneAssessmentTest(unittest.TestCase):
    def test_dual_lane_uses_minimum_component_scores(self) -> None:
        first = candidate_fixture(confidence=0.90)
        second = candidate_fixture(confidence=0.70)
        assessed = assess_dual_lane_candidate(_parent(first), (first, second))
        self.assertEqual(assessed.assessment.scores.confidence, 0.70)
        self.assertTrue(assessed.assessment.gate.passed)

    def test_failed_lane_blocks_mode_composition_proof(self) -> None:
        first = candidate_fixture()
        second = candidate_fixture(
            failed_candidate_check="boundary_proof",
        )
        assessed = assess_dual_lane_candidate(_parent(first), (first, second))
        path = assessed.assessment.gate.proof_paths[0]
        self.assertEqual(path.code, "mode_composition")
        self.assertEqual(path.state, EvidenceState.CONTRADICTED)
        self.assertFalse(assessed.assessment.gate.passed)

    def test_dual_lane_assessment_never_creates_final_status(self) -> None:
        assessed = assess_dual_lane_candidate(
            _parent(candidate_fixture()),
            (candidate_fixture(), candidate_fixture()),
        )
        self.assertFalse(hasattr(assessed, "status"))
        self.assertFalse(hasattr(assessed, "final_review_reasons"))

    def test_dual_lane_preserves_lane_scoped_overlap_spacing(self) -> None:
        first = candidate_fixture()
        second = candidate_fixture()
        second = replace(
            second,
            assessment=replace(
                second.assessment,
                evidence=replace(
                    second.assessment.evidence,
                    frame_sequence=replace(
                        second.assessment.evidence.frame_sequence,
                        spacings=(
                            observed_spacing_evidence(
                                1,
                                PixelInterval.exact(-8.0),
                                MeasurementProvenance(
                                    "photo_edges",
                                    "synthetic_overlap",
                                    ("gray_work",),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )
        assessed = assess_dual_lane_candidate(_parent(first), (first, second))
        spacings = assessed.assessment.evidence.frame_sequence.spacings
        overlap = next(spacing for spacing in spacings if spacing.kind == "overlap")
        self.assertEqual(overlap.lane_index, 2)
        self.assertEqual(overlap.signed_width_px, PixelInterval.exact(-8.0))


if __name__ == "__main__":
    unittest.main()
