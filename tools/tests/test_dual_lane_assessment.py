from __future__ import annotations

from dataclasses import replace
import unittest

import numpy as np

from tools.tests.physical_gate_support import candidate_fixture
from x5crop.detection.candidate.assessment.dual_lane import assess_dual_lane_candidate
from x5crop.detection.candidate.model import BuiltCandidate
from x5crop.domain import EvidenceState
from x5crop.domain import PixelInterval
from x5crop.detection.physical.model import DualLaneSolution
from x5crop.detection.physical.spacing import observed_spacing_evidence
from x5crop.domain import CropEnvelope, HolderSpan, VisibleSequenceSpan
from x5crop.domain import Box, MeasurementProvenance
from x5crop.configuration.candidate import DualLaneDividerParameters
from x5crop.detection.modes.dual_lane_split import lane_divider_proposals


def _parent(lane):
    frames = tuple(Box(index * 100, 0, (index + 1) * 100, 100) for index in range(4))
    geometry = DualLaneSolution(
        format_id="135-dual",
        layout=lane.geometry.layout,
        strip_mode=lane.geometry.strip_mode,
        count=4,
        holder_span=HolderSpan(Box(0, 0, 400, 100)),
        visible_sequence_span=VisibleSequenceSpan(Box(0, 0, 400, 100)),
        crop_envelope=CropEnvelope(Box(0, 0, 400, 100)),
        photo_intervals=lane.geometry.photo_intervals * 2,
        frames=frames,
        separator_observations=lane.geometry.separator_observations * 2,
        separator_assignments=lane.geometry.separator_assignments * 2,
        frame_boundaries=lane.geometry.frame_boundaries * 2,
        inter_frame_spacings=lane.geometry.inter_frame_spacings * 2,
        holder_occlusion=lane.geometry.holder_occlusion,
        frame_dimension_prior=lane.geometry.frame_dimension_prior,
        residuals=lane.geometry.residuals,
        search_budget_exhausted=False,
        source=lane.geometry.source,
        automatic_processing_supported=True,
        sequence_hypothesis_name="dual_lane_fixture",
        sequence_hypothesis_strategy="dual_lane_sequence",
        sequence_provenance=MeasurementProvenance(
            "lane_divider_profile",
            "measured_gutter",
            ("gray_work",),
        ),
        boundary_observations=lane.geometry.boundary_observations,
        lane_solutions=(lane.geometry, lane.geometry),
        lane_boxes=(Box(0, 0, 400, 50), Box(0, 50, 400, 100)),
        lane_crop_envelopes=(
            CropEnvelope(Box(0, 0, 400, 50)),
            CropEnvelope(Box(0, 50, 400, 100)),
        ),
    )
    return BuiltCandidate(geometry, lane.count_hypothesis, ("dual_lane",))


class DualLaneAssessmentTest(unittest.TestCase):
    def test_lane_divider_proposal_budget_exhaustion_is_explicit(self) -> None:
        result = lane_divider_proposals(
            np.zeros((100, 10), dtype=np.float32),
            DualLaneDividerParameters(proposal_count=1),
        )
        self.assertTrue(result.budget_exhausted)

    def test_dual_lane_solution_requires_complete_flattened_geometry(self) -> None:
        geometry = _parent(candidate_fixture()).geometry
        with self.assertRaises(ValueError):
            replace(geometry, photo_intervals=())

    def test_dual_lane_builds_structured_evidence_quality(self) -> None:
        first = candidate_fixture()
        second = candidate_fixture()
        assessed = assess_dual_lane_candidate(
            _parent(first),
            (first, second),
            lane_geometry_resolved=(True, True),
        )
        self.assertTrue(assessed.assessment.quality.supported_proof_paths)
        self.assertTrue(assessed.assessment.gate.passed)

    def test_unresolved_lane_geometry_blocks_mode_composition(self) -> None:
        first = candidate_fixture()
        second = candidate_fixture()
        assessed = assess_dual_lane_candidate(
            _parent(first),
            (first, second),
            lane_geometry_resolved=(True, False),
        )
        self.assertFalse(assessed.assessment.gate.passed)
        self.assertEqual(
            assessed.assessment.gate.proof_paths[0].state,
            EvidenceState.CONTRADICTED,
        )

    def test_failed_lane_blocks_mode_composition_proof(self) -> None:
        first = candidate_fixture()
        second = candidate_fixture(
            failed_candidate_check="boundary_proof",
        )
        assessed = assess_dual_lane_candidate(
            _parent(first),
            (first, second),
            lane_geometry_resolved=(True, True),
        )
        path = assessed.assessment.gate.proof_paths[0]
        self.assertEqual(path.code, "mode_composition")
        self.assertEqual(path.state, EvidenceState.CONTRADICTED)
        self.assertFalse(assessed.assessment.gate.passed)

    def test_dual_lane_assessment_never_creates_final_status(self) -> None:
        assessed = assess_dual_lane_candidate(
            _parent(candidate_fixture()),
            (candidate_fixture(), candidate_fixture()),
            lane_geometry_resolved=(True, True),
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
        assessed = assess_dual_lane_candidate(
            _parent(first),
            (first, second),
            lane_geometry_resolved=(True, True),
        )
        spacings = assessed.assessment.evidence.frame_sequence.spacings
        overlap = next(spacing for spacing in spacings if spacing.kind == "overlap")
        self.assertEqual(overlap.lane_index, 2)
        self.assertEqual(overlap.signed_width_px, PixelInterval.exact(-8.0))


if __name__ == "__main__":
    unittest.main()
