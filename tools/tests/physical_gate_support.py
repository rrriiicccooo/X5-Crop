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
    CandidateScores,
)
from x5crop.detection.candidate.plan.count_hypotheses import CountHypothesis
from x5crop.detection.candidate.selection.model import (
    GeometryCluster,
    GeometryResolution,
    SelectionResult,
)
from x5crop.detection.decision.decision_gate import apply_decision_gate
from x5crop.detection.decision.model import FinalDetection
from x5crop.detection.evidence.content.frame_support import (
    FrameContentEvidence,
    FrameContentObservation,
)
from x5crop.detection.evidence.content.holder_texture import HolderTextureEvidence
from x5crop.detection.evidence.content.preservation import ContentPreservationEvidence
from x5crop.detection.evidence.exposure_overlap import ExposureOverlapEvidence
from x5crop.detection.evidence.frame_coverage import FrameCoverageEvidence
from x5crop.detection.evidence.frame_sequence import FrameSequenceEvidence
from x5crop.detection.evidence.frame_topology import FrameTopologyEvidence
from x5crop.detection.evidence.holder_occupancy import (
    HolderOccupancyEvidence,
    StripCompletenessEvidence,
)
from x5crop.detection.evidence.outer_alignment import OuterAlignmentEvidence
from x5crop.detection.evidence.partial_edge import PartialEdgeSafetyEvidence
from x5crop.detection.evidence.separator_continuity import SeparatorContinuityEvidence
from x5crop.detection.evidence.state import EvidenceState
from x5crop.detection.evidence.transform_geometry import TransformGeometryEvidence
from x5crop.detection.gate_checks import GateCheck
from x5crop.detection.geometry import CandidateGeometry
from x5crop.detection.physical.photo_size import FrameDimensionEvidence
from x5crop.detection.physical.boundary import HolderOcclusionEvidence
from x5crop.detection.physical.intervals import PixelInterval
from x5crop.detection.physical.spacing import (
    SequenceConservationEvidence,
    inter_frame_spacing_evidence,
)
from x5crop.detection.physical.spans import FilmSpan, HolderSpan
from x5crop.domain import (
    AxisBleedParameters,
    Box,
    MeasurementProvenance,
    OutputProtectionPlan,
    SeparatorBandObservation,
)
from x5crop.units import ScanCalibration


def separator_observation(
    index: int,
    center: float,
    score: float = 1.0,
    method: str = "detected",
    start: float | None = None,
    end: float | None = None,
) -> SeparatorBandObservation:
    return SeparatorBandObservation(
        index=index,
        center=center,
        score=score,
        method=method,
        provenance=MeasurementProvenance(
            root_measurement="separator_profile",
            source="test_fixture",
            dependencies=("gray_work",),
        ),
        start=start,
        end=end,
        tonal_evidence=score if method != "equal" else None,
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
            consequence="blocker",
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
    film = FilmSpan(outer)
    completeness = StripCompletenessEvidence(True, True, 2, 2, 2, 1, 1)
    return CandidateEvidence(
        frame_topology=FrameTopologyEvidence(
            EvidenceState.SUPPORTED,
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
                inter_frame_spacing_evidence(1, PixelInterval.exact(0.0)),
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
            EvidenceState.SUPPORTED,
            "complete_hard_sequence",
            1,
            1,
            0,
            (1,),
            (),
            (1.0,),
        ),
        separator_continuity=SeparatorContinuityEvidence(
            EvidenceState.SUPPORTED,
            "supported",
            (),
            (separator_observation(1, 100.0, start=95.0, end=105.0),),
            0.62,
            0.55,
        ),
        frame_dimensions=FrameDimensionEvidence(
            EvidenceState.SUPPORTED,
            "photo_widths_consistent",
            36.0,
            24.0,
            1.5,
            (95.0, 95.0),
            0.0,
            (10.0,),
            0.0,
            None,
            None,
            2.0,
            0.0,
            0.0,
            False,
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
            (),
            (),
            (("left",) if content_preservation == EvidenceState.CONTRADICTED else ()),
            EvidenceState.NOT_APPLICABLE,
        ),
        outer_alignment=OuterAlignmentEvidence(
            EvidenceState.SUPPORTED,
            "content_contained",
            outer,
            Box(10, 10, 190, 90),
            ("synthetic",),
            (),
            (),
            False,
            False,
            10,
            10,
            10,
            10,
            (),
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
    confidence: float = 0.90,
    failed_candidate_check: str | None = None,
    automatic_processing_supported: bool = True,
    content_preservation: EvidenceState = EvidenceState.SUPPORTED,
) -> AssessedCandidate:
    outer = Box(0, 0, 200, 100)
    frames = (Box(0, 0, 100, 100), Box(100, 0, 200, 100))
    geometry = CandidateGeometry(
        format_id="135",
        layout="horizontal",
        strip_mode="full",
        count=2,
        holder_span=HolderSpan(outer),
        film_span=FilmSpan(outer),
        work_frames=frames,
        image_outer=outer,
        image_frames=frames,
        separators=(separator_observation(1, 100.0, start=95.0, end=105.0),),
        origin=0.0,
        pitch=100.0,
        offset_fraction=0.0,
        source="separator",
        automatic_processing_supported=automatic_processing_supported,
        contract="physical_boundary_evidence",
        outer_proposal_name="synthetic_outer",
        outer_proposal_strategy="base_outer",
        outer_provenance=MeasurementProvenance(
            "holder_boundary_profile",
            "synthetic_outer",
            ("gray_work",),
            ("left", "right"),
        ),
    )
    return AssessedCandidate(
        geometry=geometry,
        count_hypothesis=CountHypothesis(
            count=2,
            strip_mode="full",
            offsets=(0.0,),
            placement_source="test_fixture",
            source="test_fixture",
            allowed_by_physical_spec=True,
        ),
        assessment=CandidateAssessment(
            evidence=candidate_evidence_fixture(
                content_preservation=content_preservation,
            ),
            scores=CandidateScores(confidence, confidence, 1.0, 1.0, 1.0, confidence),
            gate=candidate_gate_fixture(
                passed=failed_candidate_check is None,
                failed_check=(
                    "boundary_proof"
                    if failed_candidate_check is None
                    else failed_candidate_check
                ),
            ),
            diagnostics=(),
        ),
    )


def selection_fixture(
    candidate: AssessedCandidate | None = None,
    *,
    geometry_disagreement: bool = False,
) -> SelectionResult:
    selected = candidate or candidate_fixture()
    cluster = GeometryCluster((selected,), selected)
    return SelectionResult(
        selected=selected,
        ranked_candidates=(selected,),
        clusters=(cluster,),
        consensus="disagreed" if geometry_disagreement else "uncontested",
        geometry_resolution=GeometryResolution(
            EvidenceState.SUPPORTED,
            True,
            True,
            True,
            True,
            True,
            True,
            (),
        ),
    )


def output_protection_fixture(*, feasible: bool = True) -> OutputProtectionPlan:
    return OutputProtectionPlan(
        AxisBleedParameters(20, 10),
        AxisBleedParameters(40 if feasible else 50, 10),
        True,
        40 if feasible else 80,
        50,
        feasible,
        (
            "exposure_overlap_protection_planned"
            if feasible
            else "exposure_overlap_exceeds_bleed_capacity"
        ),
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
) -> FinalDetection:
    return apply_decision_gate(
        selection_fixture(
            candidate,
            geometry_disagreement=geometry_disagreement,
        ),
        output_protection_fixture(feasible=output_protection_feasible),
        ExposureOverlapEvidence(
            EvidenceState.UNAVAILABLE,
            "no_exposure_overlap",
            False,
            0.0,
            (),
            (),
        ),
        transform_geometry_fixture(transform_state),
        ScanCalibration(None, None, "unavailable", False),
    )


def final_detection_fixture(
    *,
    confidence: float = 0.90,
    failed_candidate_check: str | None = None,
) -> FinalDetection:
    return decide_candidate(
        candidate_fixture(
            confidence=confidence,
            failed_candidate_check=failed_candidate_check,
        )
    )


def with_content_preservation(
    candidate: AssessedCandidate,
    state: EvidenceState,
) -> AssessedCandidate:
    evidence = replace(
        candidate.assessment.evidence,
        content_preservation=replace(
            candidate.assessment.evidence.content_preservation,
            state=state,
        ),
    )
    return replace(
        candidate,
        assessment=replace(candidate.assessment, evidence=evidence),
    )
