from __future__ import annotations

from dataclasses import replace
from inspect import signature
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.tests.support.physical_gates import (
    candidate_evidence_fixture,
    candidate_fixture,
    detection_workspace_fixture,
    frame_bleed_fixture,
    selection_fixture,
    transform_geometry_fixture,
)
from x5crop.detection.candidate.selection.model import (
    SelectionConsensus,
)
from x5crop.detection.geometry_resolution import GeometryResolution
from x5crop.detection.decision.decision_gate import apply_decision_gate
from x5crop.detection.evidence.separator_sequence import separator_sequence_evidence
from x5crop.detection.candidate.selection.choose import select_candidates
from x5crop.detection.candidate.selection.choose import geometry_clusters
from x5crop.detection.candidate.selection.choose import geometry_equivalent
from x5crop.detection.candidate.selection.choose import _sequence_frame_slots_resolved
from x5crop.detection.candidate.plan.model import CountHypothesisSource
from x5crop.detection.candidate.assessment.candidate import (
    candidate_gate_for_evidence,
)
from x5crop.detection.candidate.model import (
    AssessedCandidate,
    BuiltCandidate,
    CandidateAssessment,
)
from x5crop.domain import (
    BoundaryAxis,
    BoundaryKind,
    BoundaryPathSample,
    BoundarySide,
    Box,
    ContainmentFallback,
    EvidenceState,
    HolderSafetyEnvelope,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
    PhysicalSearchFact,
    PhysicalSearchOutcome,
)
from tools.tests.support.photo_edges import shared_short_axis_fixture_from_edges
from x5crop.detection.physical.model import (
    FrameBoundarySource,
    SequenceResiduals,
)
from x5crop.entry.cli import build_parser
from x5crop.run_config import RunConfig
from x5crop.runtime.options import RuntimeOptions


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _geometry_hypothesis(source: str) -> MeasurementProvenance:
    return MeasurementProvenance(
        MeasurementIdentity.FRAME_GEOMETRY,
        ObservationId(source),
        (MeasurementIdentity.FRAME_DIMENSIONS,),
        "synthetic frame-slot geometry hypothesis",
    )


def _candidate_with_geometry(candidate, geometry):
    evidence = candidate_evidence_fixture(geometry=geometry)
    built = BuiltCandidate(geometry, candidate.count_hypothesis, ())
    return AssessedCandidate(
        geometry,
        candidate.count_hypothesis,
        CandidateAssessment(
            evidence,
            candidate_gate_for_evidence(built, evidence),
        ),
    )


def _with_leading_interval(candidate, interval: PixelInterval, source: str):
    geometry = candidate.geometry
    first_slot = geometry.frame_slots[0]
    leading = replace(
        first_slot.leading,
        position=interval,
        source=FrameBoundarySource.DIMENSION_CONSTRAINED,
        boundary_anchor=None,
        inference_provenance=_geometry_hypothesis(source),
    )
    first = replace(
        first_slot,
        leading=leading,
        visible_long_axis=PixelInterval(
            interval.minimum,
            first_slot.visible_long_axis.maximum,
        ),
    )
    updated = replace(
        geometry,
        frame_slots=(first, *geometry.frame_slots[1:]),
        long_axis_assignments=tuple(
            item
            for item in geometry.long_axis_assignments
            if not (
                item.frame_index == 1 and item.side == BoundarySide.LEADING
            )
        ),
    )
    return _candidate_with_geometry(candidate, updated)


def _with_shifted_short_axis(candidate, offset: float):
    geometry = candidate.geometry
    short_axis = geometry.shared_short_axis
    photo_edges = tuple(
        sorted(
            (
                path
                for path in geometry.raw_boundary_paths
                if path.axis == BoundaryAxis.SHORT
                and path.kind != BoundaryKind.EDGE_ADJACENT_TRANSITION
            ),
            key=lambda path: path.position.midpoint,
        )
    )
    top_photo_edge, bottom_photo_edge = photo_edges[0], photo_edges[-1]

    def shifted(path):
        return replace(
            path,
            samples=tuple(
                BoundaryPathSample(
                    sample.orthogonal_interval,
                    sample.position.plus(PixelInterval.exact(offset)),
                )
                for sample in path.samples
            ),
        )

    shifted_short_axis = shared_short_axis_fixture_from_edges(
        shifted(top_photo_edge),
        shifted(bottom_photo_edge),
    )
    updated = replace(
        geometry,
        holder_safety=HolderSafetyEnvelope(
            (),
            ContainmentFallback(
                Box(0, 0, 310, 120),
                _geometry_hypothesis("shifted_holder_containment"),
            ),
        ),
        shared_short_axis=shifted_short_axis,
        separator_assignments=tuple(
            replace(
                assignment,
                cross_axis_measurement=replace(
                    assignment.cross_axis_measurement,
                    short_axis_span=shifted_short_axis.measurement_span,
                ),
            )
            for assignment in geometry.separator_assignments
        ),
    )
    return _candidate_with_geometry(candidate, updated)


class PhysicalGateModelContractTest(unittest.TestCase):
    def _decision_for_resolution(
        self,
        resolution: GeometryResolution,
        *,
        consensus: SelectionConsensus = SelectionConsensus.UNCONTESTED,
    ):
        selection = replace(
            selection_fixture(),
            consensus=consensus,
            geometry_resolution=resolution,
        )
        return apply_decision_gate(
            selection,
            frame_bleed_fixture(),
            detection_workspace_fixture().scan_canvas_evidence,
            transform_geometry_fixture(),
            automatic_processing_eligibility=EvidenceState.SUPPORTED,
        )

    def test_unresolved_count_does_not_duplicate_generic_geometry_reason(
        self,
    ) -> None:
        detection = self._decision_for_resolution(
            GeometryResolution(
                False,
                False,
                False,
                True,
                True,
                True,
                True,
                PhysicalSearchOutcome(
                    (PhysicalSearchFact.SOLUTION_FOUND,),
                ),
            )
        )
        self.assertEqual(
            detection.final_review_reasons,
            ("count_resolution_unavailable",),
        )

    def test_selection_disagreement_owns_its_final_reason(self) -> None:
        detection = self._decision_for_resolution(
            GeometryResolution(
                True,
                True,
                True,
                True,
                True,
                False,
                True,
                PhysicalSearchOutcome(
                    (PhysicalSearchFact.SOLUTION_FOUND,),
                ),
            ),
            consensus=SelectionConsensus.DISAGREED,
        )
        self.assertEqual(
            detection.final_review_reasons,
            ("selection_geometry_disagreement",),
        )

    def test_evidence_state_has_explicit_non_failure_states(self) -> None:
        self.assertEqual(
            {state.value for state in EvidenceState},
            {"supported", "contradicted", "unavailable", "not_applicable"},
        )

    def test_separator_support_does_not_accept_confidence(self) -> None:
        self.assertNotIn("confidence", signature(separator_sequence_evidence).parameters)

    def test_selection_does_not_accept_format_spec(self) -> None:
        self.assertNotIn("fmt", signature(select_candidates).parameters)

    def test_equivalent_geometry_is_consensus(self) -> None:
        candidate = candidate_fixture()
        corroborating_candidate = replace(
            candidate,
            count_hypothesis=replace(
                candidate.count_hypothesis,
                source=CountHypothesisSource.REQUESTED,
            ),
        )
        result = select_candidates(
            (candidate, corroborating_candidate),
            larger_count_search_complete=True,
            physical_search=PhysicalSearchOutcome(
                (PhysicalSearchFact.SOLUTION_FOUND,),
            ),
        )
        self.assertEqual(result.consensus, SelectionConsensus.AGREED)
        self.assertEqual(len(result.clusters), 1)

    def test_failed_candidate_does_not_create_equal_rank_disagreement(self) -> None:
        good = candidate_fixture()
        bad = candidate_fixture(
            failed_candidate_check="sequence_proof",
        )
        bad = _with_leading_interval(
            bad,
            PixelInterval(10.0, 20.0),
            "failed_candidate_leading_edge",
        )
        result = select_candidates(
            (good, bad),
            larger_count_search_complete=True,
            physical_search=PhysicalSearchOutcome(
                (PhysicalSearchFact.SOLUTION_FOUND,),
            ),
        )
        self.assertNotEqual(result.consensus, SelectionConsensus.DISAGREED)

    def test_geometry_cluster_requires_common_interval_consensus(self) -> None:
        center = candidate_fixture()
        left = _with_leading_interval(
            center,
            PixelInterval(0.0, 4.0),
            "left_geometry_leading_edge",
        )
        right = _with_leading_interval(
            center,
            PixelInterval(12.0, 16.0),
            "right_geometry_leading_edge",
        )
        bridge = _with_leading_interval(
            center,
            PixelInterval(3.0, 13.0),
            "bridge_geometry_leading_edge",
        )
        self.assertEqual(len(geometry_clusters((bridge, left, right))), 2)

    def test_geometry_cluster_preserves_slot_topology_and_visible_extent(self) -> None:
        class SyntheticSequenceGeometry:
            def __init__(
                self,
                second_slot_inferred: bool,
                second_visible: PixelInterval | None = None,
            ) -> None:
                def boundary(position: float):
                    return SimpleNamespace(position=PixelInterval.exact(position))

                self.count = 2
                self.strip_mode = "full"
                self.shared_short_axis = SimpleNamespace(
                    top=PixelInterval.exact(0.0),
                    bottom=PixelInterval.exact(100.0),
                )
                self.frame_slots = (
                    SimpleNamespace(
                        sequence_inferred=False,
                        visible_long_axis=PixelInterval(0.0, 100.0),
                        leading=boundary(0.0),
                        trailing=boundary(100.0),
                    ),
                    SimpleNamespace(
                        sequence_inferred=second_slot_inferred,
                        visible_long_axis=(
                            second_visible
                            if second_visible is not None
                            else PixelInterval(110.0, 210.0)
                        ),
                        leading=boundary(110.0),
                        trailing=boundary(210.0),
                    ),
                )

        measured = SimpleNamespace(geometry=SyntheticSequenceGeometry(False))
        inferred = SimpleNamespace(geometry=SyntheticSequenceGeometry(True))

        with patch(
            "x5crop.detection.candidate.selection.choose.FrameSequenceSolution",
            SyntheticSequenceGeometry,
        ):
            self.assertFalse(geometry_equivalent(measured, inferred))
            self.assertFalse(
                geometry_equivalent(
                    SimpleNamespace(
                        geometry=SyntheticSequenceGeometry(
                            False,
                            PixelInterval(110.0, 150.0),
                        )
                    ),
                    SimpleNamespace(
                        geometry=SyntheticSequenceGeometry(
                            False,
                            PixelInterval(170.0, 210.0),
                        )
                    ),
                )
            )

    def test_repeated_width_roles_do_not_resolve_single_frame_geometry(self) -> None:
        repeated_width_role = MeasurementProvenance(
            MeasurementIdentity.PHOTO_EDGES,
            ObservationId("single_frame_resolution_repeated_width_role"),
            (
                MeasurementIdentity.GRAY_WORK,
                MeasurementIdentity.FRAME_WIDTH_PATTERN,
            ),
            "photo-edge role assigned by repeated-width geometry",
        )
        boundary = SimpleNamespace(
            geometry_resolved=True,
            independently_observed=True,
            role_provenance=repeated_width_role,
            position=PixelInterval.exact(50.0),
        )
        geometry = SimpleNamespace(
            count=1,
            frame_slots=(
                SimpleNamespace(leading=boundary, trailing=boundary),
            ),
            frame_crop_envelopes=(
                SimpleNamespace(box=Box(0, 0, 100, 100)),
            ),
            holder_safety=SimpleNamespace(
                containment_fallback=SimpleNamespace(box=Box(0, 0, 100, 100)),
            ),
        )

        self.assertFalse(_sequence_frame_slots_resolved(geometry))

    def test_common_width_does_not_resolve_incompatible_ordinary_slot(self) -> None:
        boundary = SimpleNamespace(
            geometry_resolved=True,
            position=PixelInterval.exact(50.0),
        )
        geometry = SimpleNamespace(
            count=2,
            frame_slots=(
                SimpleNamespace(
                    leading=boundary,
                    trailing=boundary,
                    width_px=PixelInterval(40.0, 50.0),
                    sequence_inferred=False,
                    edge_occlusion=None,
                ),
                SimpleNamespace(
                    leading=boundary,
                    trailing=boundary,
                    width_px=PixelInterval(100.0, 110.0),
                    sequence_inferred=False,
                    edge_occlusion=None,
                ),
            ),
            frame_crop_envelopes=(
                SimpleNamespace(box=Box(0, 0, 50, 100)),
                SimpleNamespace(box=Box(60, 0, 170, 100)),
            ),
            common_frame_width=SimpleNamespace(
                state=EvidenceState.SUPPORTED,
                width_px=PixelInterval(100.0, 110.0),
            ),
            holder_safety=SimpleNamespace(
                containment_fallback=SimpleNamespace(box=Box(0, 0, 170, 100)),
            ),
        )

        self.assertFalse(_sequence_frame_slots_resolved(geometry))

    def test_occlusion_outside_workspace_does_not_resolve_geometry(self) -> None:
        def boundary(position: PixelInterval):
            return SimpleNamespace(geometry_resolved=True, position=position)

        geometry = SimpleNamespace(
            count=2,
            frame_slots=(
                SimpleNamespace(
                    leading=boundary(PixelInterval(-10.0, -5.0)),
                    trailing=boundary(PixelInterval.exact(100.0)),
                    width_px=PixelInterval(105.0, 110.0),
                    sequence_inferred=False,
                    edge_occlusion=object(),
                ),
                SimpleNamespace(
                    leading=boundary(PixelInterval.exact(110.0)),
                    trailing=boundary(PixelInterval.exact(215.0)),
                    width_px=PixelInterval.exact(105.0),
                    sequence_inferred=False,
                    edge_occlusion=None,
                ),
            ),
            frame_crop_envelopes=(
                SimpleNamespace(box=Box(0, 0, 100, 100)),
                SimpleNamespace(box=Box(110, 0, 215, 100)),
            ),
            common_frame_width=SimpleNamespace(
                state=EvidenceState.SUPPORTED,
                width_px=PixelInterval(100.0, 110.0),
            ),
            holder_safety=SimpleNamespace(
                containment_fallback=SimpleNamespace(box=Box(0, 0, 220, 100)),
            ),
        )

        self.assertFalse(_sequence_frame_slots_resolved(geometry))

    def test_candidate_residual_tradeoffs_preserve_geometry_disagreement(self) -> None:
        selected = candidate_fixture()
        alternative = _with_shifted_short_axis(selected, 1.0)
        alternative = replace(
            alternative,
            geometry=replace(
                alternative.geometry,
                residuals=SequenceResiduals(0.10, 0.01),
            ),
        )
        selected = replace(
            selected,
            geometry=replace(
                selected.geometry,
                residuals=SequenceResiduals(0.01, 0.10),
            ),
        )
        self.assertEqual(
            selected.evidence_quality.physical_residuals,
            selected.geometry.residuals,
        )
        self.assertEqual(
            alternative.evidence_quality.physical_residuals,
            alternative.geometry.residuals,
        )
        result = select_candidates(
            (selected, alternative),
            larger_count_search_complete=True,
            physical_search=PhysicalSearchOutcome(
                (PhysicalSearchFact.SOLUTION_FOUND,),
            ),
        )
        self.assertIs(result.selected, selected)
        self.assertEqual(result.consensus, SelectionConsensus.DISAGREED)
        self.assertFalse(result.geometry_resolution.alternative_geometries_resolved)

    def test_gate_flow_has_no_confidence_caps_or_generic_fallback(self) -> None:
        source = "\n".join(
            path.read_text()
            for path in (PROJECT_ROOT / "x5crop/detection").rglob("*.py")
        )
        for forbidden in (
            "apply_confidence_cap",
            "confidence_floor",
            "candidate_signal_gate_checks",
            "candidate_gate_failed",
        ):
            self.assertNotIn(forbidden, source)

    def test_runtime_has_no_auto_confidence_threshold(self) -> None:
        self.assertNotIn("confidence_threshold", RunConfig.__dataclass_fields__)
        self.assertNotIn("confidence_threshold", RuntimeOptions.__dataclass_fields__)
        self.assertNotIn("--confidence-threshold", build_parser().format_help())

    def test_final_reason_vocabulary_is_finite_and_physical(self) -> None:
        from x5crop.detection.decision.vocabulary import FINAL_REVIEW_REASONS

        self.assertEqual(len(FINAL_REVIEW_REASONS), 12)
        self.assertIn("content_preservation_unresolved", FINAL_REVIEW_REASONS)
        self.assertIn("sequence_evidence_insufficient", FINAL_REVIEW_REASONS)
        self.assertIn("count_resolution_unavailable", FINAL_REVIEW_REASONS)
        self.assertIn("geometry_resolution_unavailable", FINAL_REVIEW_REASONS)
        self.assertIn("scan_canvas_profile_unresolved", FINAL_REVIEW_REASONS)


if __name__ == "__main__":
    unittest.main()
