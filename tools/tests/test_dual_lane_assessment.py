from __future__ import annotations

from dataclasses import fields, replace
import inspect
import unittest
from unittest.mock import patch

import numpy as np

from tools.tests.physical_gate_support import (
    candidate_fixture,
    selection_fixture,
)
from x5crop.cache import MeasurementCacheStatistics
from x5crop.cache.analysis import make_measurement_cache
from x5crop.configuration.candidate import DualLaneDividerParameters
from x5crop.configuration.registry import get_detection_configuration
from x5crop.detection.candidate.composition.dual_lane import (
    compose_dual_lane_candidate,
)
from x5crop.detection.candidate.assessment.review_only import (
    assess_review_only_candidate,
)
from x5crop.detection.candidate.model import BuiltCandidate, DualLaneEvidence
from x5crop.detection.candidate.proposal.hard_safety import hard_safety_candidate
from x5crop.detection.candidate.proposal.sequence import frame_sequence_search_scope
from x5crop.detection.candidate.selection.choose import select_candidates
from x5crop.detection.context import (
    DetectionContext,
    DetectionExecutionStatistics,
    DetectionRequest,
)
from x5crop.detection.modes.dual_lane import _lane_context, choose_dual_lane_detection
from x5crop.detection.physical.lane_divider import (
    LaneDividerEvidence,
    LaneDividerEvidenceSet,
    measure_lane_dividers,
)
from x5crop.detection.physical.model import (
    AssignmentConsensusOutcome,
    BoundaryAssignmentConsensus,
    DualLaneFrameSolution,
    ReviewOnlyContainment,
    SequenceResiduals,
    combined_assignment_consensus,
    combined_sequence_residuals,
)
from x5crop.domain import (
    Box,
    ContainmentFallback,
    EvidenceState,
    HolderSafetyEnvelope,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PhysicalSearchFact,
    PhysicalSearchOutcome,
)
from x5crop.image.statistics import image_measurement_statistics


def _parent(lane):
    lane_width = lane.geometry.holder_safety.box.width
    lane_height = lane.geometry.holder_safety.box.height
    lane_boxes = (
        Box(0, 0, lane_width, lane_height),
        Box(0, lane_height, lane_width, 2 * lane_height),
    )
    lane_solutions = (lane.geometry, lane.geometry)
    geometry = DualLaneFrameSolution(
        format_id="135-dual",
        layout=lane.geometry.layout,
        strip_mode=lane.geometry.strip_mode,
        count=sum(item.count for item in lane_solutions),
        holder_safety=HolderSafetyEnvelope(
            (),
            ContainmentFallback(
                Box(0, 0, lane_width, 2 * lane_height),
                MeasurementProvenance(
                    MeasurementIdentity.CANVAS,
                    ObservationId("dual_lane_containment"),
                    (MeasurementIdentity.CANVAS,),
                    "dual-lane test containment",
                ),
            ),
        ),
        residuals=combined_sequence_residuals(lane_solutions),
        assignment_consensus=combined_assignment_consensus(lane_solutions),
        lane_divider=LaneDividerEvidence(
            center=lane_height,
            gutter=Box(0, lane_height - 1, lane_width, lane_height + 1),
            normalized_gutter_residual=0.0,
            normalized_lane_residuals=(1.0, 1.0),
            provenance=MeasurementProvenance(
                MeasurementIdentity.LANE_DIVIDER_PROFILE,
                ObservationId("measured_gutter"),
                (MeasurementIdentity.CONTENT_EVIDENCE_IMAGE,),
                "measured dual-lane gutter",
            ),
        ),
        lane_solutions=lane_solutions,
        lane_boxes=lane_boxes,
    )
    return BuiltCandidate(
        geometry,
        replace(lane.count_hypothesis, count=geometry.count),
        ("dual_lane_composition",),
    )


def _lane_selection(candidate, *, resolved: bool = True):
    selection = selection_fixture(candidate)
    if resolved:
        return selection
    return replace(
        selection,
        geometry_resolution=replace(
            selection.geometry_resolution,
            frame_slots_resolved=False,
        ),
    )


class DualLaneAssessmentTest(unittest.TestCase):
    def test_lane_caches_share_one_lookup_statistics_owner(self) -> None:
        configuration = get_detection_configuration("135-dual", "full")
        lane_configuration = get_detection_configuration("135", "full")
        gray = np.full((120, 240), 128, dtype=np.uint8)
        statistics = image_measurement_statistics(
            gray,
            configuration.preprocess.image_statistics,
        )
        context = DetectionContext(
            DetectionRequest("horizontal", "full", None),
            configuration,
            lane_configuration,
            make_measurement_cache(
                gray,
                "horizontal",
                statistics,
                0.0,
                MeasurementCacheStatistics(),
            ),
            DetectionExecutionStatistics(),
        )

        lane_context = _lane_context(context, Box(0, 0, 240, 60))

        self.assertIs(
            lane_context.measurement_cache.lookup_statistics,
            context.measurement_cache.lookup_statistics,
        )

    def test_dual_lane_assessment_consumes_lane_selections(self) -> None:
        parameters = inspect.signature(compose_dual_lane_candidate).parameters
        self.assertIn("lane_selections", parameters)
        self.assertNotIn("lane_geometry_resolved", parameters)

    def test_missing_lane_divider_keeps_review_only_geometry(self) -> None:
        configuration = get_detection_configuration("135-dual", "full")
        lane_configuration = get_detection_configuration("135", "full")
        gray = np.full((120, 240), 128, dtype=np.uint8)
        statistics = image_measurement_statistics(
            gray,
            configuration.preprocess.image_statistics,
        )
        context = DetectionContext(
            DetectionRequest("horizontal", "full", None),
            configuration,
            lane_configuration,
            make_measurement_cache(
                gray,
                "horizontal",
                statistics,
                0.0,
                MeasurementCacheStatistics(),
            ),
            DetectionExecutionStatistics(),
        )
        search_scope = frame_sequence_search_scope(
            context.measurement_cache,
            context.configuration.boundary_path,
        )
        with patch(
            "x5crop.detection.modes.dual_lane.measure_lane_dividers",
            return_value=LaneDividerEvidenceSet((), False),
        ), patch(
            "x5crop.detection.modes.review_only.frame_sequence_search_scope",
            return_value=search_scope,
        ):
            selection = choose_dual_lane_detection(
                context,
                lambda _: self.fail("lane detector must not run without a divider"),
            )

        self.assertIsInstance(selection.selected.geometry, ReviewOnlyContainment)
        self.assertEqual(
            selection.geometry_resolution.physical_search.state,
            EvidenceState.UNAVAILABLE,
        )
        self.assertIn(
            PhysicalSearchFact.MEASUREMENTS_UNAVAILABLE,
            selection.geometry_resolution.physical_search.facts,
        )

    def test_unresolved_lane_keeps_dual_lane_result_review_only(self) -> None:
        configuration = get_detection_configuration("135-dual", "full")
        lane_configuration = get_detection_configuration("135", "full")
        gray = np.full((120, 240), 128, dtype=np.uint8)
        statistics = image_measurement_statistics(
            gray,
            configuration.preprocess.image_statistics,
        )
        context = DetectionContext(
            DetectionRequest("horizontal", "full", None),
            configuration,
            lane_configuration,
            make_measurement_cache(
                gray,
                "horizontal",
                statistics,
                0.0,
                MeasurementCacheStatistics(),
            ),
            DetectionExecutionStatistics(),
        )
        divider_evidence = measure_lane_dividers(
            np.zeros((120, 240), dtype=np.float32),
            DualLaneDividerParameters(proposal_count=1),
        )
        self.assertTrue(divider_evidence.candidates)

        def unresolved_lane(lane_context: DetectionContext):
            count = lane_context.configuration.physical_spec.strip.default_count
            assessed = assess_review_only_candidate(
                hard_safety_candidate(
                    lane_context,
                    count,
                    frame_sequence_search_scope(
                        lane_context.measurement_cache,
                        lane_context.configuration.boundary_path,
                    ),
                    physical_search=PhysicalSearchOutcome(
                        (PhysicalSearchFact.MEASUREMENTS_UNAVAILABLE,),
                    ),
                )
            )
            return select_candidates(
                (assessed,),
                larger_count_search_complete=True,
                physical_search=PhysicalSearchOutcome(
                    (PhysicalSearchFact.MEASUREMENTS_UNAVAILABLE,),
                ),
            )

        with patch(
            "x5crop.detection.modes.dual_lane.measure_lane_dividers",
            return_value=divider_evidence,
        ):
            selection = choose_dual_lane_detection(context, unresolved_lane)

        self.assertIsInstance(selection.selected.geometry, ReviewOnlyContainment)

    def test_lane_divider_measurement_budget_is_explicit(self) -> None:
        parameters = DualLaneDividerParameters(proposal_count=1)
        result = measure_lane_dividers(
            np.zeros((100, 10), dtype=np.float32),
            parameters,
        )
        self.assertTrue(result.budget_exhausted)
        self.assertLessEqual(len(result.candidates), parameters.proposal_count)

    def test_content_across_divider_remains_unavailable(self) -> None:
        result = measure_lane_dividers(
            np.ones((100, 20), dtype=np.float32),
            DualLaneDividerParameters(proposal_count=2),
        )
        self.assertTrue(result.candidates)
        self.assertTrue(
            all(item.state == EvidenceState.UNAVAILABLE for item in result.candidates)
        )

    def test_local_content_valley_supports_lane_divider(self) -> None:
        evidence = np.ones((100, 20), dtype=np.float32)
        evidence[48:52, :] = 0.0
        result = measure_lane_dividers(
            evidence,
            DualLaneDividerParameters(proposal_count=1),
        )
        self.assertTrue(
            any(item.state == EvidenceState.SUPPORTED for item in result.candidates)
        )

    def test_lane_divider_provenance_is_acyclic(self) -> None:
        result = measure_lane_dividers(
            np.zeros((100, 20), dtype=np.float32),
            DualLaneDividerParameters(proposal_count=1),
        )
        self.assertTrue(result.candidates)
        self.assertTrue(
            all(
                item.provenance.root_measurement not in item.provenance.dependencies
                for item in result.candidates
            )
        )

    def test_dual_lane_solution_derives_all_aggregate_geometry(self) -> None:
        field_names = {field.name for field in fields(DualLaneFrameSolution)}
        self.assertEqual(
            field_names,
            {
                "format_id",
                "layout",
                "strip_mode",
                "count",
                "holder_safety",
                "residuals",
                "assignment_consensus",
                "lane_divider",
                "lane_solutions",
                "lane_boxes",
            },
        )
        geometry = _parent(candidate_fixture()).geometry
        with self.assertRaises(ValueError):
            replace(geometry, residuals=SequenceResiduals(None, 0.5))
        with self.assertRaises(ValueError):
            replace(
                geometry,
                assignment_consensus=BoundaryAssignmentConsensus(
                    AssignmentConsensusOutcome.COMPONENT_UNRESOLVED,
                    geometry.assignment_consensus.solution_count,
                    (),
                ),
            )

    def test_dual_lane_builds_structured_lane_evidence(self) -> None:
        lane = candidate_fixture()
        assessed = compose_dual_lane_candidate(
            _parent(lane),
            (_lane_selection(lane), _lane_selection(lane)),
        )

        self.assertIsInstance(assessed.assessment.evidence, DualLaneEvidence)
        self.assertTrue(assessed.assessment.gate.passed)
        self.assertTrue(assessed.evidence_quality.supported_proof_paths)

    def test_unresolved_lane_blocks_composition_proof(self) -> None:
        lane = candidate_fixture()
        assessed = compose_dual_lane_candidate(
            _parent(lane),
            (_lane_selection(lane), _lane_selection(lane, resolved=False)),
        )

        self.assertFalse(assessed.assessment.gate.passed)
        self.assertEqual(
            assessed.assessment.gate.proof_paths[0].state,
            EvidenceState.CONTRADICTED,
        )

    def test_component_geometry_must_match_parent_exactly(self) -> None:
        first = candidate_fixture()
        second = candidate_fixture(failed_candidate_check="sequence_proof")
        with self.assertRaises(ValueError):
            compose_dual_lane_candidate(
                _parent(first),
                (_lane_selection(first), _lane_selection(second)),
            )

    def test_unavailable_lane_divider_blocks_composition(self) -> None:
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

    def test_lane_scoped_spacing_identity_is_derived(self) -> None:
        geometry = _parent(candidate_fixture()).geometry
        self.assertEqual(
            tuple(item.boundary.lane_index for item in geometry.inter_frame_spacings),
            (1, 2),
        )

    def test_assessment_never_creates_final_status(self) -> None:
        lane = candidate_fixture()
        assessed = compose_dual_lane_candidate(
            _parent(lane),
            (_lane_selection(lane), _lane_selection(lane)),
        )
        self.assertFalse(hasattr(assessed, "status"))
        self.assertFalse(hasattr(assessed, "final_review_reasons"))


if __name__ == "__main__":
    unittest.main()
