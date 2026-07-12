from __future__ import annotations

from dataclasses import replace

from x5crop.detection.candidate.assessment.candidate_gate import (
    BoundaryProofPath,
    CandidateGateAssessment,
)
from x5crop.detection.candidate.assessment.evidence_independence import (
    EvidenceIndependenceEvidence,
)
from x5crop.detection.candidate.assessment.separator_support import (
    SeparatorSequenceEvidence,
)
from x5crop.detection.candidate.model import (
    AssessedCandidate,
    CandidateAssessment,
    CandidateEvidence,
)
from x5crop.detection.candidate.plan.count_hypotheses import CountHypothesis
from x5crop.detection.candidate.selection.model import (
    GeometryCluster,
    GeometryResolution,
    SelectionResult,
)
from x5crop.detection.decision.decision_gate import apply_decision_gate
from x5crop.detection.decision.model import DecisionGateAssessment
from x5crop.detection.final.model import FinalDetection
from x5crop.detection.final.finalize import (
    finalization_plan_for_selection,
    finalize_detection,
)
from x5crop.detection.evidence.content.frame_support import (
    FrameContentEvidence,
    FrameContentObservation,
)
from x5crop.detection.evidence.content.holder_texture import HolderTextureEvidence
from x5crop.detection.evidence.content.preservation import ContentPreservationEvidence
from x5crop.detection.evidence.frame_coverage import FrameCoverageEvidence
from x5crop.detection.evidence.frame_sequence import FrameSequenceEvidence
from x5crop.detection.evidence.frame_topology import FrameTopologyEvidence
from x5crop.detection.evidence.holder_occupancy import (
    HolderOccupancyEvidence,
    StripCompletenessEvidence,
)
from x5crop.detection.evidence.sequence_content_alignment import SequenceContentAlignmentEvidence
from x5crop.detection.evidence.partial_edge import PartialEdgeSafetyEvidence
from x5crop.domain import EvidenceState, FrameBoundaryReference
from x5crop.detection.evidence.transform_geometry import TransformGeometryEvidence
from x5crop.detection.gate_checks import GateCheck
from x5crop.detection.physical.model import (
    BoundaryAssignmentConsensus,
    PhotoInterval,
    SequenceResiduals,
    SequenceSolution,
)
from x5crop.detection.physical.photo_size import FrameDimensionEvidence
from x5crop.detection.physical.boundary import HolderOcclusionEvidence
from x5crop.domain import PixelInterval
from x5crop.detection.physical.spacing import (
    SequenceConservationEvidence,
    observed_spacing_evidence,
)
from x5crop.domain import BoundaryObservation
from x5crop.domain import CropEnvelope, HolderSpan, VisibleSequenceSpan
from x5crop.detection.physical.separator.assignment import (
    assign_observation_to_boundary,
    frame_boundary_from_assignment,
)
from x5crop.domain import (
    SeparatorBandObservation,
    SeparatorCrossAxisMeasurement,
)
from x5crop.domain import (
    BoundaryPositionConstraint,
    Box,
    FrameDimensionPrior,
    MeasurementProvenance,
    SeparatorWidthConstraint,
)
from x5crop.output.model import AxisBleedParameters, FrameBleedPlan, FrameSideBleed


def separator_observation(
    center: float,
    tonal_evidence: float = 1.0,
    start: float | None = None,
    end: float | None = None,
    cross_axis_state: EvidenceState = EvidenceState.SUPPORTED,
) -> SeparatorBandObservation:
    start = float(center - 1.0 if start is None else start)
    end = float(center + 1.0 if end is None else end)
    return SeparatorBandObservation(
        start=start,
        end=end,
        center=center,
        tonal_evidence=tonal_evidence,
        provenance=MeasurementProvenance(
            root_measurement="separator_profile",
            source="test_fixture",
            dependencies=("gray_work",),
        ),
        cross_axis=SeparatorCrossAxisMeasurement(
            state=cross_axis_state,
            coverage_ratio=(
                1.0 if cross_axis_state == EvidenceState.SUPPORTED else 0.0
            ),
            continuity_ratio=(
                1.0 if cross_axis_state == EvidenceState.SUPPORTED else 0.0
            ),
            break_count=0,
            straightness=(
                1.0 if cross_axis_state == EvidenceState.SUPPORTED else 0.0
            ),
            reason=(
                "supported"
                if cross_axis_state == EvidenceState.SUPPORTED
                else "cross_axis_continuity_weak"
            ),
        ),
    )


def separator_constraints(
    index: int,
    position: PixelInterval,
    width: PixelInterval = PixelInterval(0.0, 1000.0),
) -> tuple[BoundaryPositionConstraint, SeparatorWidthConstraint]:
    provenance = MeasurementProvenance(
        "frame_dimensions",
        "test_constraint",
        ("physical_frame_size",),
    )
    return (
        BoundaryPositionConstraint(index, position, provenance),
        SeparatorWidthConstraint(index, width, provenance),
    )


def candidate_gate_fixture(
    *,
    passed: bool = True,
    failed_check: str = "boundary_proof",
) -> CandidateGateAssessment:
    codes = (
        "frame_topology_integrity",
        "content_preservation",
        "photo_geometry_consistency",
        "frame_sequence_conservation",
        "evidence_independence",
        "boundary_proof",
    )
    checks = tuple(
        GateCheck(
            code=code,
            stage="candidate",
            state=(
                EvidenceState.CONTRADICTED
                if not passed and code == failed_check
                else EvidenceState.SUPPORTED
            ),
        )
        for code in codes
    )
    proof_paths = (
        BoundaryProofPath(
            code="separator_led",
            state=(EvidenceState.SUPPORTED if passed else EvidenceState.UNAVAILABLE),
            supporting_evidence=("test_fixture",),
        ),
    )
    return CandidateGateAssessment(
        checks=checks,
        proof_paths=proof_paths,
        diagnostics=(),
    )


def candidate_evidence_fixture(
    *,
    content_preservation: EvidenceState = EvidenceState.SUPPORTED,
) -> CandidateEvidence:
    outer = Box(0, 0, 200, 100)
    frames = (Box(0, 0, 100, 100), Box(100, 0, 200, 100))
    holder = HolderSpan(outer)
    film = VisibleSequenceSpan(outer)
    completeness = StripCompletenessEvidence(True, True, 2, 2, 2, 1, 1, 1)
    return CandidateEvidence(
        frame_topology=FrameTopologyEvidence(
            EvidenceState.SUPPORTED,
            "sequence",
            2,
            2,
            True,
            True,
            True,
            True,
            (),
            (),
            (),
            frames,
        ),
        frame_coverage=FrameCoverageEvidence(
            EvidenceState.SUPPORTED,
            "content_runs_covered",
            (0, 200),
            (0, 200),
            ((0, 100), (100, 200)),
            ((10, 190),),
            (),
            0,
        ),
        frame_sequence=FrameSequenceEvidence(
            holder_occlusion=HolderOcclusionEvidence.not_applicable(),
            spacings=(
                observed_spacing_evidence(
                    FrameBoundaryReference(None, 1),
                    PixelInterval.exact(0.0),
                    MeasurementProvenance(
                        "separator_profile",
                        "test_fixture",
                        ("gray_work",),
                    ),
                ),
            ),
            conservation=SequenceConservationEvidence(
                EvidenceState.SUPPORTED,
                "frame_sequence_conserved",
                PixelInterval.exact(200.0),
                PixelInterval.zero(),
                PixelInterval.exact(200.0),
                PixelInterval.zero(),
                PixelInterval.exact(200.0),
            ),
        ),
        separator_sequence=SeparatorSequenceEvidence(
            1,
            1,
            0,
            (FrameBoundaryReference(None, 1),),
            (),
            (1.0,),
        ),
        frame_dimensions=FrameDimensionEvidence(
            frame_width_mm=36.0,
            frame_height_mm=24.0,
            frame_width_prior_px=PixelInterval.exact(95.0),
            photo_width_intervals_px=(
                PixelInterval.exact(95.0),
                PixelInterval.exact(95.0),
            ),
            separator_widths_px=(10.0,),
            observed_width_mm=None,
            observed_height_mm=None,
            observed_aspect=1.5,
            aspect_error_ratio=0.0,
            calibration_used=False,
        ),
        frame_content=FrameContentEvidence(
            EvidenceState.SUPPORTED,
            "supported",
            0.5,
            0.8,
            0.8,
            (
                FrameContentObservation(1, 0.8, 0.8, True, ()),
                FrameContentObservation(2, 0.8, 0.8, True, ()),
            ),
            "synthetic",
        ),
        holder_texture=HolderTextureEvidence(
            EvidenceState.UNAVAILABLE,
            "holder_slack_unavailable",
            (),
            None,
            None,
        ),
        content_preservation=ContentPreservationEvidence(
            content_preservation,
            (
                "content_undercrop_confirmed"
                if content_preservation == EvidenceState.CONTRADICTED
                else "supported"
            ),
            (
                ((0, 5),)
                if content_preservation == EvidenceState.CONTRADICTED
                else ()
            ),
            (),
            EvidenceState.NOT_APPLICABLE,
        ),
        sequence_content_alignment=SequenceContentAlignmentEvidence(
            EvidenceState.SUPPORTED,
            "content_contained",
            outer,
            Box(10, 10, 190, 90),
            (),
            False,
            False,
            10,
            10,
            10,
            10,
        ),
        holder_occupancy=HolderOccupancyEvidence(
            EvidenceState.SUPPORTED,
            completeness,
            None,
            200.0,
            0.0,
            0.0,
            None,
            None,
            1.0,
            "filled",
            False,
            True,
            EvidenceState.SUPPORTED,
            True,
            holder,
            film,
            False,
        ),
        partial_edge_safety=PartialEdgeSafetyEvidence(
            EvidenceState.NOT_APPLICABLE,
            "full_strip",
            False,
            1,
            1,
            EvidenceState.SUPPORTED,
            EvidenceState.SUPPORTED,
            False,
            (),
        ),
        independence=EvidenceIndependenceEvidence(
            EvidenceState.SUPPORTED,
            "independent_outer_and_separator_measurements",
            "holder_boundary_profile",
            ("separator_profile",),
            (),
        ),
    )


def candidate_fixture(
    *,
    failed_candidate_check: str | None = None,
    automatic_processing_supported: bool = True,
    content_preservation: EvidenceState = EvidenceState.SUPPORTED,
) -> AssessedCandidate:
    outer = Box(0, 0, 200, 100)
    frames = (Box(0, 0, 100, 100), Box(100, 0, 200, 100))
    observation = separator_observation(100.0, start=95.0, end=105.0)
    assignment = assign_observation_to_boundary(
        1,
        observation,
        *separator_constraints(1, PixelInterval(80.0, 120.0)),
    )
    assignment = replace(assignment, used_for_boundary=True)
    boundary = frame_boundary_from_assignment(assignment)
    relation = observed_spacing_evidence(
        FrameBoundaryReference(None, 1),
        PixelInterval.exact(observation.width),
        observation.provenance,
    )
    geometry = SequenceSolution(
        format_id="135",
        layout="horizontal",
        strip_mode="full",
        count=2,
        holder_span=HolderSpan(outer),
        visible_sequence_span=VisibleSequenceSpan(outer),
        crop_envelope=CropEnvelope(outer),
        photo_intervals=(
            PhotoInterval(
                1,
                PixelInterval.exact(0.0),
                PixelInterval.exact(95.0),
                MeasurementProvenance("photo_edges", "test_fixture", ("separator_profile",)),
                MeasurementProvenance("photo_edges", "test_fixture", ("separator_profile",)),
                True,
                True,
            ),
            PhotoInterval(
                2,
                PixelInterval.exact(105.0),
                PixelInterval.exact(200.0),
                MeasurementProvenance("photo_edges", "test_fixture", ("separator_profile",)),
                MeasurementProvenance("photo_edges", "test_fixture", ("separator_profile",)),
                True,
                True,
            ),
        ),
        frames=frames,
        separator_observations=(observation,),
        separator_assignments=(assignment,),
        frame_boundaries=(boundary,),
        inter_frame_spacings=(relation,),
        holder_occlusion=HolderOcclusionEvidence.not_applicable(),
        frame_dimension_prior=FrameDimensionPrior(
            PixelInterval.exact(100.0),
            PixelInterval.exact(100.0),
            (36.0, 24.0),
            "test_fixture",
            MeasurementProvenance(
                "frame_dimensions",
                "test_fixture",
                ("format_physical_spec",),
            ),
        ),
        residuals=SequenceResiduals(0.05, 0.0, 0.0),
        assignment_consensus=BoundaryAssignmentConsensus(
            EvidenceState.SUPPORTED,
            "synthetic_assignment_consensus",
            1,
            (),
        ),
        search_budget_exhausted=False,
        automatic_processing_supported=automatic_processing_supported,
        sequence_hypothesis_name="synthetic_sequence",
        sequence_hypothesis_strategy="boundary_led",
        sequence_provenance=MeasurementProvenance(
            "holder_boundary_profile",
            "synthetic_outer",
            ("gray_work",),
            ("left", "right"),
        ),
        boundary_observations=tuple(
            BoundaryObservation(
                side,
                PixelInterval.exact(position),
                "tonal_transition",
                MeasurementProvenance(
                    "holder_boundary_profile",
                    "synthetic_boundary",
                    ("gray_work",),
                    (side,),
                ),
            )
            for side, position in (
                ("leading", 1.0),
                ("trailing", 199.0),
                ("top", 1.0),
                ("bottom", 99.0),
            )
        ),
    )
    evidence = candidate_evidence_fixture(
        content_preservation=content_preservation,
    )
    gate = candidate_gate_fixture(
        passed=failed_candidate_check is None,
        failed_check=(
            "boundary_proof"
            if failed_candidate_check is None
            else failed_candidate_check
        ),
    )
    return AssessedCandidate(
        geometry=geometry,
        count_hypothesis=CountHypothesis(
            count=2,
            strip_mode="full",
            source="test_fixture",
        ),
        assessment=CandidateAssessment(
            evidence=evidence,
            gate=gate,
        ),
    )


def selection_fixture(
    candidate: AssessedCandidate | None = None,
    *,
    geometry_disagreement: bool = False,
) -> SelectionResult:
    selected = candidate or candidate_fixture()
    cluster = GeometryCluster((selected,), selected)
    resolution = GeometryResolution(
        (
            EvidenceState.UNAVAILABLE
            if geometry_disagreement
            else EvidenceState.SUPPORTED
        ),
        True,
        True,
        True,
        True,
        True,
        not geometry_disagreement,
        ("geometry_clusters_disagree",) if geometry_disagreement else (),
    )
    return SelectionResult(
        selected=selected,
        ranked_candidates=(selected,),
        clusters=(cluster,),
        consensus="disagreed" if geometry_disagreement else "uncontested",
        geometry_resolution=resolution,
    )


def frame_bleed_fixture(*, feasible: bool = True) -> FrameBleedPlan:
    return FrameBleedPlan(
        user_bleed=AxisBleedParameters(20, 10),
        frame_output_bounds=(
            Box(0, 0, 200, 100),
            Box(0, 0, 200, 100),
        ),
        frame_sides=(
            FrameSideBleed(0, 20, 20, 10),
            FrameSideBleed(1, 20, 20, 10),
        ),
        overlap_protection=(),
        unresolved_overlap_boundaries=(
            () if feasible else (FrameBoundaryReference(None, 1),)
        ),
        feasible=feasible,
        reason="no_output_overlap" if feasible else "output_overlap_unresolved",
    )


def transform_geometry_fixture(
    state: EvidenceState = EvidenceState.SUPPORTED,
) -> TransformGeometryEvidence:
    return TransformGeometryEvidence(state, False, 0.0, 0.0, "test_fixture", 0.0, 1.0)


def decide_candidate(
    candidate: AssessedCandidate | None = None,
    *,
    geometry_disagreement: bool = False,
    output_protection_feasible: bool = True,
    transform_state: EvidenceState = EvidenceState.SUPPORTED,
) -> DecisionGateAssessment:
    return apply_decision_gate(
        selection_fixture(
            candidate,
            geometry_disagreement=geometry_disagreement,
        ),
        frame_bleed_fixture(feasible=output_protection_feasible),
        transform_geometry_fixture(transform_state),
    )


def final_detection_fixture(
    *,
    failed_candidate_check: str | None = None,
) -> FinalDetection:
    selection = selection_fixture(
        candidate_fixture(
            failed_candidate_check=failed_candidate_check,
        )
    )
    bleed = frame_bleed_fixture()
    decision = apply_decision_gate(
        selection,
        bleed,
        transform_geometry_fixture(),
    )
    return finalize_detection(
        decision,
        finalization_plan_for_selection(
            selection,
            bleed,
            image_width=200,
            image_height=100,
        ),
    )
