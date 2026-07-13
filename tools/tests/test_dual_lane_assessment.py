from __future__ import annotations

from dataclasses import fields, replace
import inspect
import unittest
from unittest.mock import patch

import numpy as np

from tools.tests.physical_gate_support import candidate_fixture
from x5crop.detection.candidate.composition.dual_lane import (
    compose_dual_lane_candidate,
)
from x5crop.detection.candidate.assessment.candidate import (
    candidate_gate_for_evidence,
)
from x5crop.detection.candidate.assessment.evidence_independence import (
    evidence_independence_evidence,
)
from x5crop.detection.candidate.model import (
    AssessedCandidate,
    CandidateAssessment,
)
from x5crop.detection.evidence.frame_sequence import sequence_conservation_for_geometry
from x5crop.detection.evidence.content.internal_boundaries import (
    internal_boundary_preservation_evidence,
)
from x5crop.detection.evidence.partial_edge import partial_edge_safety_evidence
from x5crop.detection.physical.photo_size import frame_dimension_evidence
from x5crop.detection.evidence.separator_sequence import (
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
    AssignmentConsensusOutcome,
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
from x5crop.cache import MeasurementCacheStatistics
from x5crop.cache.analysis import make_measurement_cache
from x5crop.configuration.registry import get_detection_configuration
from x5crop.detection.context import (
    DetectionContext,
    DetectionExecutionStatistics,
    DetectionRequest,
)
from x5crop.detection.modes.dual_lane import _lane_context, choose_dual_lane_detection
from x5crop.detection.physical.lane_divider import LaneDividerEvidenceSet
from x5crop.detection.physical.model import ReviewOnlyGeometry
from x5crop.image.statistics import image_measurement_statistics
from tools.tests.physical_gate_support import (
    selection_fixture,
    unavailable_calibration_fixture,
)


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


def _lane_selection(candidate, *, resolved: bool = True):
    selection = selection_fixture(candidate)
    if resolved:
        return selection
    return replace(
        selection,
        geometry_resolution=replace(
            selection.geometry_resolution,
            boundaries_resolved=False,
        ),
    )


def _candidate_with_geometry(candidate, geometry):
    dimensions = frame_dimension_evidence(
        geometry,
        unavailable_calibration_fixture(),
    )
    evidence = replace(
        candidate.assessment.evidence,
        sequence_conservation=sequence_conservation_for_geometry(geometry),
        frame_dimensions=dimensions,
        holder_occupancy=replace(
            candidate.assessment.evidence.holder_occupancy,
            frame_dimension_state=dimensions.state,
        ),
        partial_edge_safety=partial_edge_safety_evidence(
            geometry,
            candidate.assessment.evidence.frame_coverage,
            dimensions,
            candidate.assessment.evidence.frame_content,
        ),
        internal_boundary_preservation=internal_boundary_preservation_evidence(
            geometry.count,
            geometry.frame_boundaries,
            geometry.inter_frame_spacings,
            candidate.assessment.evidence.frame_content,
        ),
        independence=evidence_independence_evidence(geometry),
    )
    built = BuiltCandidate(geometry, candidate.count_hypothesis, ())
    return AssessedCandidate(
        geometry,
        candidate.count_hypothesis,
        CandidateAssessment(
            evidence,
            candidate_gate_for_evidence(built, evidence),
        ),
    )


class DualLaneAssessmentTest(unittest.TestCase):
    def test_lane_caches_share_one_run_lookup_statistics_owner(self) -> None:
        configuration = get_detection_configuration("135-dual", "full")
        lane_configuration = get_detection_configuration("135", "full")
        gray = np.full((120, 240), 128, dtype=np.uint8)
        statistics = image_measurement_statistics(
            gray,
            configuration.preprocess.image_statistics,
        )
        context = DetectionContext(
            scan_calibration=unavailable_calibration_fixture(),
            request=DetectionRequest("horizontal", "full", None),
            configuration=configuration,
            lane_configuration=lane_configuration,
            measurement_cache=make_measurement_cache(
                gray,
                "horizontal",
                configuration.preprocess.content_evidence_image,
                statistics,
                MeasurementCacheStatistics(),
            ),
            execution_statistics=DetectionExecutionStatistics(),
        )

        lane_context = _lane_context(context, Box(0, 0, 240, 60))

        self.assertIs(
            lane_context.measurement_cache.lookup_statistics,
            context.measurement_cache.lookup_statistics,
        )

    def test_dual_lane_assessment_consumes_canonical_lane_selections(self) -> None:
        parameters = inspect.signature(compose_dual_lane_candidate).parameters
        self.assertIn("lane_selections", parameters)
        self.assertNotIn("lane_geometry_resolved", parameters)

    def test_missing_lane_divider_keeps_unresolved_dual_lane_identity(self) -> None:
        configuration = get_detection_configuration("135-dual", "full")
        lane_configuration = get_detection_configuration("135", "full")
        gray = np.full((120, 240), 128, dtype=np.uint8)
        statistics = image_measurement_statistics(
            gray,
            configuration.preprocess.image_statistics,
        )
        context = DetectionContext(
            scan_calibration=unavailable_calibration_fixture(),
            request=DetectionRequest("horizontal", "full", None),
            configuration=configuration,
            lane_configuration=lane_configuration,
            measurement_cache=make_measurement_cache(
                gray,
                "horizontal",
                configuration.preprocess.content_evidence_image,
                statistics,
                MeasurementCacheStatistics(),
            ),
            execution_statistics=DetectionExecutionStatistics(),
        )

        with patch(
            "x5crop.detection.modes.dual_lane.measure_lane_dividers",
            return_value=LaneDividerEvidenceSet((), False),
        ):
            selection = choose_dual_lane_detection(
                context,
                lambda _: self.fail("no lane detector should run without a divider"),
            )

        self.assertIsInstance(selection.selected.geometry, ReviewOnlyGeometry)
        self.assertEqual(selection.selected.geometry.format_id, "135-dual")
        self.assertEqual(selection.selected.geometry.strip_mode, "full")

    def test_dual_lane_resolution_cannot_be_forged_as_booleans(self) -> None:
        first = selection_fixture(candidate_fixture())
        second_candidate = candidate_fixture()
        second = replace(
            selection_fixture(second_candidate),
            geometry_resolution=replace(
                selection_fixture(second_candidate).geometry_resolution,
                boundaries_resolved=False,
            ),
        )
        assessed = compose_dual_lane_candidate(
            _parent(first.selected),
            lane_selections=(first, second),
        )

        self.assertFalse(
            assessed.assessment.evidence.lane_geometry_resolutions[1].supported
        )
        self.assertFalse(assessed.assessment.gate.passed)

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
                "boundary_paths",
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
                    AssignmentConsensusOutcome.COMPONENT_UNRESOLVED,
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
        assessed = compose_dual_lane_candidate(
            _parent(first),
            (_lane_selection(first), _lane_selection(second)),
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

    def test_dual_lane_proof_must_match_lane_facts(self) -> None:
        lane = candidate_fixture()
        assessed = compose_dual_lane_candidate(
            _parent(lane),
            (_lane_selection(lane), _lane_selection(lane)),
        )
        gate = assessed.assessment.gate
        forged_path = replace(
            gate.proof_paths[0],
            supporting_evidence=("forged",),
        )
        with self.assertRaises(ValueError):
            replace(
                assessed,
                assessment=replace(
                    assessed.assessment,
                    gate=replace(gate, proof_paths=(forged_path,)),
                ),
            )

    def test_dual_lane_assessment_requires_exact_component_geometry(self) -> None:
        first = candidate_fixture()
        second = candidate_fixture(failed_candidate_check="boundary_proof")
        with self.assertRaises(ValueError):
            compose_dual_lane_candidate(
                _parent(first),
                (_lane_selection(first), _lane_selection(second)),
            )

    def test_unresolved_lane_geometry_blocks_mode_composition(self) -> None:
        first = candidate_fixture()
        second = candidate_fixture()
        assessed = compose_dual_lane_candidate(
            _parent(first),
            (_lane_selection(first), _lane_selection(second, resolved=False)),
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
        assessed = compose_dual_lane_candidate(
            parent,
            (_lane_selection(first), _lane_selection(second)),
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
        assessed = compose_dual_lane_candidate(
            parent,
            (_lane_selection(lane), _lane_selection(lane)),
        )
        self.assertFalse(assessed.assessment.gate.passed)

    def test_dual_lane_assessment_never_creates_final_status(self) -> None:
        assessed = compose_dual_lane_candidate(
            _parent(candidate_fixture()),
            (
                _lane_selection(candidate_fixture()),
                _lane_selection(candidate_fixture()),
            ),
        )
        self.assertFalse(hasattr(assessed, "status"))
        self.assertFalse(hasattr(assessed, "final_review_reasons"))

    def test_dual_lane_preserves_lane_scoped_overlap_spacing(self) -> None:
        first = candidate_fixture()
        second = candidate_fixture()
        second = _candidate_with_geometry(
            second,
            replace(
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
        assessed = compose_dual_lane_candidate(
            parent,
            (_lane_selection(first), _lane_selection(second)),
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
        assessed = compose_dual_lane_candidate(
            _parent(first),
            tuple(_lane_selection(lane) for lane in lanes),
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
