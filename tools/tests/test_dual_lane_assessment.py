from __future__ import annotations

from dataclasses import fields, replace
import unittest

import numpy as np

from tools.tests.physical_gate_support import candidate_fixture
from x5crop.detection.candidate.assessment.dual_lane import assess_dual_lane_candidate
from x5crop.detection.candidate.assessment.separator_support import (
    SeparatorSequenceEvidence,
)
from x5crop.detection.candidate.model import BuiltCandidate
from x5crop.domain import EvidenceState, FrameBoundaryReference, MeasurementIdentity
from x5crop.domain import PixelInterval
from x5crop.detection.physical.lane_divider import (
    LaneDividerEvidence,
    measure_lane_dividers,
)
from x5crop.detection.physical.model import DualLaneSolution
from x5crop.detection.physical.model import (
    BoundaryAssignmentConsensus,
    SequenceResiduals,
    combined_assignment_consensus,
)
from x5crop.detection.physical.spacing import (
    ObservedSpacingEvidence,
    observed_spacing_evidence,
)
from x5crop.domain import CropEnvelope, HolderSpan, VisibleSequenceSpan
from x5crop.domain import Box, MeasurementProvenance
from x5crop.configuration.candidate import DualLaneDividerParameters


def _parent(lane):
    lane_width = lane.geometry.holder_span.box.width
    lane_height = lane.geometry.holder_span.box.height
    lane_boxes = (
        Box(0, 0, lane_width, lane_height),
        Box(0, lane_height, lane_width, 2 * lane_height),
    )
    frames = tuple(
        Box(
            frame.left + lane_box.left,
            frame.top + lane_box.top,
            frame.right + lane_box.left,
            frame.bottom + lane_box.top,
        )
        for lane_box in lane_boxes
        for frame in lane.geometry.frames
    )
    lane_crop_envelopes = tuple(
        CropEnvelope(
            Box(
                lane.geometry.crop_envelope.box.left + lane_box.left,
                lane.geometry.crop_envelope.box.top + lane_box.top,
                lane.geometry.crop_envelope.box.right + lane_box.left,
                lane.geometry.crop_envelope.box.bottom + lane_box.top,
            )
        )
        for lane_box in lane_boxes
    )
    visible = lane.geometry.visible_sequence_span.box
    geometry = DualLaneSolution(
        format_id="135-dual",
        layout=lane.geometry.layout,
        strip_mode=lane.geometry.strip_mode,
        count=2 * lane.geometry.count,
        holder_span=HolderSpan(Box(0, 0, lane_width, 2 * lane_height)),
        visible_sequence_span=VisibleSequenceSpan(
            Box(visible.left, visible.top, visible.right, visible.bottom + lane_height)
        ),
        crop_envelope=CropEnvelope(
            Box(
                lane_crop_envelopes[0].box.left,
                lane_crop_envelopes[0].box.top,
                lane_crop_envelopes[1].box.right,
                lane_crop_envelopes[1].box.bottom,
            )
        ),
        frames=frames,
        residuals=lane.geometry.residuals,
        assignment_consensus=combined_assignment_consensus(
            (lane.geometry, lane.geometry)
        ),
        search_budget_exhausted=False,
        lane_divider=LaneDividerEvidence(
            center=lane_height,
            gutter=Box(0, lane_height - 1, lane_width, lane_height + 1),
            normalized_gutter_residual=0.0,
            normalized_lane_residuals=(1.0, 1.0),
            provenance=MeasurementProvenance(
                MeasurementIdentity.LANE_DIVIDER_PROFILE,
                "measured_gutter",
                (MeasurementIdentity.CONTENT_EVIDENCE_IMAGE,),
            ),
        ),
        lane_solutions=(lane.geometry, lane.geometry),
        lane_boxes=lane_boxes,
        lane_crop_envelopes=lane_crop_envelopes,
    )
    return BuiltCandidate(
        geometry,
        replace(lane.count_hypothesis, count=geometry.count),
        ("dual_lane",),
    )


class DualLaneAssessmentTest(unittest.TestCase):
    def test_lane_divider_measurement_budget_exhaustion_is_explicit(self) -> None:
        parameters = DualLaneDividerParameters(proposal_count=1)
        result = measure_lane_dividers(
            np.zeros((100, 10), dtype=np.float32),
            parameters,
        )
        self.assertTrue(result.budget_exhausted)
        self.assertLessEqual(len(result.candidates), parameters.proposal_count)

    def test_content_across_divider_is_unavailable_and_never_discarded(self) -> None:
        result = measure_lane_dividers(
            np.ones((100, 20), dtype=np.float32),
            DualLaneDividerParameters(proposal_count=2),
        )
        self.assertTrue(result.candidates)
        for divider in result.candidates:
            with self.subTest(center=divider.center):
                self.assertEqual(divider.state, EvidenceState.UNAVAILABLE)
                upper, lower = divider.lane_boxes(20, 100)
                self.assertEqual(upper.top, 0)
                self.assertEqual(upper.bottom, lower.top)
                self.assertEqual(lower.bottom, 100)

    def test_local_content_valley_supports_lane_divider(self) -> None:
        evidence = np.ones((100, 20), dtype=np.float32)
        evidence[48:52, :] = 0.0
        result = measure_lane_dividers(
            evidence,
            DualLaneDividerParameters(proposal_count=1),
        )
        self.assertTrue(
            any(
                divider.state == EvidenceState.SUPPORTED
                for divider in result.candidates
            )
        )

    def test_lane_divider_provenance_is_acyclic(self) -> None:
        result = measure_lane_dividers(
            np.zeros((100, 20), dtype=np.float32),
            DualLaneDividerParameters(proposal_count=1),
        )
        for divider in result.candidates:
            self.assertNotIn(
                divider.provenance.root_measurement,
                divider.provenance.dependencies,
            )

    def test_dual_lane_solution_does_not_duplicate_lane_sequence_facts(self) -> None:
        field_names = {field.name for field in fields(DualLaneSolution)}
        self.assertTrue(
            {
                "photo_intervals",
                "separator_observations",
                "separator_assignments",
                "frame_boundaries",
                "inter_frame_spacings",
                "holder_occlusion",
                "frame_dimension_prior",
                "boundary_observations",
            }.isdisjoint(field_names)
        )

    def test_dual_lane_aggregate_geometry_is_derived_from_lane_solutions(self) -> None:
        geometry = _parent(candidate_fixture()).geometry
        invalid_geometries = (
            lambda: replace(
                geometry,
                visible_sequence_span=VisibleSequenceSpan(
                    replace(geometry.visible_sequence_span.box, right=geometry.visible_sequence_span.box.right - 1)
                ),
            ),
            lambda: replace(
                geometry,
                crop_envelope=CropEnvelope(
                    replace(geometry.crop_envelope.box, right=geometry.crop_envelope.box.right - 1)
                ),
            ),
            lambda: replace(
                geometry,
                residuals=SequenceResiduals(None, None, 0.5),
            ),
            lambda: replace(
                geometry,
                assignment_consensus=BoundaryAssignmentConsensus(
                    EvidenceState.UNAVAILABLE,
                    "synthetic_mismatch",
                    geometry.assignment_consensus.solution_count,
                    (),
                ),
            ),
        )
        for factory in invalid_geometries:
            with self.subTest(factory=factory), self.assertRaises(ValueError):
                factory()

    def test_separator_evidence_uses_lane_aware_boundary_references(self) -> None:
        field_names = {field.name for field in fields(SeparatorSequenceEvidence)}
        self.assertIn("hard_boundaries", field_names)
        self.assertIn("missing_boundaries", field_names)
        self.assertNotIn("hard_boundary_indexes", field_names)
        self.assertNotIn("missing_boundary_indexes", field_names)

    def test_spacing_uses_one_typed_boundary_identity(self) -> None:
        field_names = {field.name for field in fields(ObservedSpacingEvidence)}
        self.assertIn("boundary", field_names)
        self.assertNotIn("index", field_names)
        self.assertNotIn("lane_index", field_names)

    def test_dual_lane_builds_structured_evidence_quality(self) -> None:
        from x5crop.detection.candidate.model import DualLaneEvidence

        first = candidate_fixture()
        second = candidate_fixture()
        assessed = assess_dual_lane_candidate(
            _parent(first),
            (first, second),
            lane_geometry_resolved=(True, True),
        )
        self.assertIsInstance(assessed.assessment.evidence, DualLaneEvidence)
        self.assertEqual(
            assessed.assessment.evidence.lane_evidence,
            (first.assessment.evidence, second.assessment.evidence),
        )
        self.assertTrue(assessed.evidence_quality.supported_proof_paths)
        self.assertTrue(assessed.assessment.gate.passed)
        self.assertEqual(
            {
                (lane_index, reference.boundary_index)
                for lane_index, evidence in enumerate(
                    assessed.assessment.evidence.lane_evidence,
                    start=1,
                )
                for reference in evidence.separator_sequence.hard_boundaries
            },
            {(1, 1), (2, 1)},
        )

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
        parent = _parent(first)
        parent = replace(
            parent,
            geometry=replace(
                parent.geometry,
                lane_solutions=(first.geometry, second.geometry),
            ),
        )
        assessed = assess_dual_lane_candidate(
            parent,
            (first, second),
            lane_geometry_resolved=(True, True),
        )
        path = assessed.assessment.gate.proof_paths[0]
        self.assertEqual(path.code, "mode_composition")
        self.assertEqual(path.state, EvidenceState.CONTRADICTED)
        self.assertFalse(assessed.assessment.gate.passed)

    def test_unavailable_lane_divider_blocks_mode_composition_proof(self) -> None:
        lane = candidate_fixture()
        parent = _parent(lane)
        parent = replace(
            parent,
            geometry=replace(
                parent.geometry,
                lane_divider=replace(
                    parent.geometry.lane_divider,
                    normalized_gutter_residual=1.0,
                    normalized_lane_residuals=(1.0, 1.0),
                ),
            ),
        )
        assessed = assess_dual_lane_candidate(
            parent,
            (lane, lane),
            lane_geometry_resolved=(True, True),
        )
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
            geometry=replace(
                second.geometry,
                inter_frame_spacings=(
                    observed_spacing_evidence(
                        FrameBoundaryReference(None, 1),
                        PixelInterval.exact(-8.0),
                        MeasurementProvenance(
                            MeasurementIdentity.PHOTO_EDGES,
                            "synthetic_overlap",
                            (MeasurementIdentity.GRAY_WORK,),
                        ),
                    ),
                ),
            ),
        )
        parent = _parent(first)
        parent = replace(
            parent,
            geometry=replace(
                parent.geometry,
                lane_solutions=(first.geometry, second.geometry),
            ),
        )
        assessed = assess_dual_lane_candidate(
            parent,
            (first, second),
            lane_geometry_resolved=(True, True),
        )
        spacings = assessed.geometry.inter_frame_spacings
        overlap = next(spacing for spacing in spacings if spacing.kind == "overlap")
        self.assertEqual(overlap.boundary, FrameBoundaryReference(2, 1))
        self.assertEqual(overlap.signed_width_px, PixelInterval.exact(-8.0))

    def test_lane_content_contacts_keep_their_lane_evidence_identity(self) -> None:
        first = candidate_fixture()
        second = candidate_fixture()
        lanes = tuple(
            replace(
                lane,
                assessment=replace(
                    lane.assessment,
                    evidence=replace(
                        lane.assessment.evidence,
                        frame_content=replace(
                            lane.assessment.evidence.frame_content,
                            observations=tuple(
                                replace(
                                    observation,
                                    boundary_contact_sides=("left",),
                                )
                                if observation.index == 1
                                else observation
                                for observation in lane.assessment.evidence.frame_content.observations
                            ),
                        ),
                    ),
                ),
            )
            for lane in (first, second)
        )
        assessed = assess_dual_lane_candidate(
            _parent(first),
            lanes,
            lane_geometry_resolved=(True, True),
        )
        self.assertEqual(
            tuple(
                tuple(
                    observation.index
                    for observation in evidence.frame_content.observations
                    if observation.boundary_contact_sides
                )
                for evidence in assessed.assessment.evidence.lane_evidence
            ),
            ((1,), (1,)),
        )


if __name__ == "__main__":
    unittest.main()
