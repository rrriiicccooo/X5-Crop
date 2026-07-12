from __future__ import annotations

from dataclasses import dataclass

from x5crop.domain import (
    BoundaryKind,
    BoundarySide,
    EvidenceState,
    MeasurementIdentity,
)

from ..physical.model import (
    CandidateGeometry,
    DualLaneSolution,
    ReviewOnlyGeometry,
    SequenceSolution,
)
from .assessment.evidence_independence import EvidenceIndependenceEvidence
from .assessment.separator_support import SeparatorSequenceEvidence
from ..evidence.content.frame_support import FrameContentEvidence
from ..evidence.content.holder_texture import HolderTextureEvidence
from ..evidence.frame_coverage import FrameCoverageEvidence
from ..evidence.holder_occupancy import HolderOccupancyEvidence
from ..evidence.sequence_content_alignment import SequenceContentAlignmentEvidence
from ..evidence.partial_edge import PartialEdgeSafetyEvidence
from ..physical.photo_size import FrameDimensionEvidence
from .assessment.candidate_gate import BoundaryProofPath, CandidateGateAssessment
from .plan.count_hypotheses import CountHypothesis
from ..physical.model import SequenceResiduals
from ..physical.spacing import SequenceConservationEvidence


@dataclass(frozen=True)
class BuiltCandidate:
    geometry: CandidateGeometry
    count_hypothesis: CountHypothesis
    build_diagnostics: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            self.count_hypothesis.count != self.geometry.count
            or self.count_hypothesis.strip_mode != self.geometry.strip_mode
        ):
            raise ValueError("built candidate count hypothesis must match geometry")
        if any(not item for item in self.build_diagnostics) or len(
            set(self.build_diagnostics)
        ) != len(self.build_diagnostics):
            raise ValueError("build diagnostics must be non-empty and unique")


@dataclass(frozen=True)
class CandidateEvidence:
    frame_coverage: FrameCoverageEvidence
    sequence_conservation: SequenceConservationEvidence
    separator_sequence: SeparatorSequenceEvidence
    frame_dimensions: FrameDimensionEvidence
    frame_content: FrameContentEvidence
    holder_texture: HolderTextureEvidence
    sequence_content_alignment: SequenceContentAlignmentEvidence
    holder_occupancy: HolderOccupancyEvidence
    partial_edge_safety: PartialEdgeSafetyEvidence
    independence: EvidenceIndependenceEvidence

    @property
    def content_preservation_state(self) -> EvidenceState:
        return content_preservation_state(
            self.frame_coverage,
            self.sequence_content_alignment,
            self.partial_edge_safety,
        )


@dataclass(frozen=True)
class DualLaneEvidence:
    lane_evidence: tuple[CandidateEvidence, ...]
    lane_gates: tuple[CandidateGateAssessment, ...]
    lane_geometry_resolved: tuple[bool, ...]

    def __post_init__(self) -> None:
        lane_count = len(self.lane_evidence)
        if lane_count <= 1:
            raise ValueError("dual-lane evidence requires multiple lane evidence sets")
        if (
            len(self.lane_gates) != lane_count
            or len(self.lane_geometry_resolved) != lane_count
        ):
            raise ValueError(
                "dual-lane evidence requires one gate and resolution per lane"
            )


@dataclass(frozen=True)
class ReviewOnlyEvidence:
    @property
    def quality_unavailable_code(self) -> str:
        return "review_only_geometry_not_measured"


CandidateEvidenceModel = CandidateEvidence | DualLaneEvidence | ReviewOnlyEvidence


def content_preservation_state(
    frame_coverage: FrameCoverageEvidence,
    sequence_alignment: SequenceContentAlignmentEvidence,
    partial_edge: PartialEdgeSafetyEvidence,
) -> EvidenceState:
    if frame_coverage.state == EvidenceState.CONTRADICTED:
        return EvidenceState.CONTRADICTED
    if sequence_alignment.content_outside_sides:
        return EvidenceState.UNAVAILABLE
    if partial_edge.state == EvidenceState.CONTRADICTED:
        return EvidenceState.CONTRADICTED
    if (
        frame_coverage.state == EvidenceState.SUPPORTED
        or sequence_alignment.state == EvidenceState.SUPPORTED
    ):
        return EvidenceState.SUPPORTED
    return EvidenceState.UNAVAILABLE


def boundary_proof_paths_for_geometry(
    geometry: SequenceSolution,
    evidence: CandidateEvidence,
) -> tuple[BoundaryProofPath, ...]:
    boundary_by_side = {
        observation.side: observation
        for observation in geometry.boundary_observations
    }
    sequence_boundary_supported = bool(
        geometry.sequence_provenance.root_measurement
        not in {
            MeasurementIdentity.HOLDER_CANVAS,
            MeasurementIdentity.SAFETY_GEOMETRY_MODEL,
            MeasurementIdentity.REVIEW_ONLY_MODE,
        }
        and all(
            side in boundary_by_side
            and boundary_by_side[side].kind != BoundaryKind.CANVAS_CLIP
            for side in (BoundarySide.LEADING, BoundarySide.TRAILING)
        )
    )
    common = bool(
        sequence_boundary_supported
        and evidence.sequence_conservation.state != EvidenceState.CONTRADICTED
        and evidence.independence.state
        in {EvidenceState.SUPPORTED, EvidenceState.NOT_APPLICABLE}
    )
    separator_led = bool(
        geometry.count > 1
        and common
        and evidence.separator_sequence.state == EvidenceState.SUPPORTED
    )
    hard_anchor_count = evidence.separator_sequence.hard_count
    single_frame_physical_boundaries = bool(
        geometry.count == 1
        and sequence_boundary_supported
        and evidence.frame_dimensions.state == EvidenceState.SUPPORTED
    )
    geometry_led = bool(
        evidence.frame_dimensions.state == EvidenceState.SUPPORTED
        and (
            single_frame_physical_boundaries
            or (common and geometry.count > 1 and hard_anchor_count >= 1)
        )
    )
    partial_occupancy_led = bool(
        geometry.strip_mode == "partial"
        and evidence.partial_edge_safety.state == EvidenceState.SUPPORTED
        and evidence.holder_occupancy.underfilled
        and common
    )
    return (
        BoundaryProofPath(
            "separator_led",
            (
                EvidenceState.SUPPORTED
                if separator_led
                else EvidenceState.UNAVAILABLE
            ),
            (
                "complete_hard_separator_sequence",
                "cross_axis_separator_pixel_paths",
                "frame_union_content_coverage",
            ),
        ),
        BoundaryProofPath(
            "geometry_led",
            (
                EvidenceState.SUPPORTED
                if geometry_led
                else EvidenceState.UNAVAILABLE
            ),
            (
                "physical_frame_dimensions",
                (
                    "calibrated_two_side_frame_boundaries"
                    if evidence.frame_dimensions.calibration_used
                    else "independent_two_side_frame_boundaries"
                    if single_frame_physical_boundaries
                    else "independent_separator_anchor"
                ),
            ),
        ),
        BoundaryProofPath(
            "partial_occupancy_led",
            (
                EvidenceState.SUPPORTED
                if partial_occupancy_led
                else EvidenceState.UNAVAILABLE
                if geometry.strip_mode == "partial"
                else EvidenceState.NOT_APPLICABLE
            ),
            (
                "partial_edge_content_preservation",
                "holder_occupancy",
                "resolved_frame_sequence",
            ),
        ),
    )


def boundary_proof_paths_for_dual_lane(
    geometry: DualLaneSolution,
    evidence: DualLaneEvidence,
) -> tuple[BoundaryProofPath, ...]:
    composition_supported = bool(
        geometry.lane_divider.state == EvidenceState.SUPPORTED
        and all(gate.passed for gate in evidence.lane_gates)
        and all(evidence.lane_geometry_resolved)
    )
    return (
        BoundaryProofPath(
            "mode_composition",
            (
                EvidenceState.SUPPORTED
                if composition_supported
                else EvidenceState.CONTRADICTED
            ),
            (
                "lane_divider",
                "lane_candidate_gates",
                "lane_geometry_resolution",
            ),
        ),
    )


def _combined_evidence_state(states: tuple[EvidenceState, ...]) -> EvidenceState:
    if any(state == EvidenceState.CONTRADICTED for state in states):
        return EvidenceState.CONTRADICTED
    if states and all(state == EvidenceState.SUPPORTED for state in states):
        return EvidenceState.SUPPORTED
    return EvidenceState.UNAVAILABLE


def _candidate_gate_evidence_states(
    evidence: CandidateEvidence | DualLaneEvidence,
) -> dict[str, EvidenceState]:
    evidence_sets = (
        evidence.lane_evidence
        if isinstance(evidence, DualLaneEvidence)
        else (evidence,)
    )

    def combined(attribute: str) -> EvidenceState:
        return _combined_evidence_state(
            tuple(getattr(item, attribute).state for item in evidence_sets)
        )

    content_preservation = _combined_evidence_state(
        tuple(item.content_preservation_state for item in evidence_sets)
    )
    return {
        "content_preservation": content_preservation,
        "photo_geometry_consistency": combined("frame_dimensions"),
        "frame_sequence_conservation": combined("sequence_conservation"),
        "evidence_independence": combined("independence"),
    }


@dataclass(frozen=True)
class EvidenceQuality:
    supported: tuple[str, ...]
    contradicted: tuple[str, ...]
    unavailable: tuple[str, ...]
    covered_content_px: int
    uncovered_content_px: int
    supported_proof_paths: tuple[str, ...]
    physical_residuals: SequenceResiduals | None


@dataclass(frozen=True)
class CandidateAssessment:
    evidence: CandidateEvidenceModel
    gate: CandidateGateAssessment | None

    def __post_init__(self) -> None:
        if isinstance(self.evidence, ReviewOnlyEvidence):
            if self.gate is not None:
                raise ValueError("review-only assessment cannot own CandidateGate")
        elif self.gate is None:
            raise ValueError("physical candidate assessment requires CandidateGate")
        else:
            expected = _candidate_gate_evidence_states(self.evidence)
            actual = {
                check.code: check.state
                for check in self.gate.checks
                if check.code in expected
            }
            if actual != expected:
                raise ValueError("CandidateGate checks must match candidate evidence")


@dataclass(frozen=True)
class AssessedCandidate:
    geometry: CandidateGeometry
    count_hypothesis: CountHypothesis
    assessment: CandidateAssessment

    def __post_init__(self) -> None:
        if (
            self.count_hypothesis.count != self.geometry.count
            or self.count_hypothesis.strip_mode != self.geometry.strip_mode
        ):
            raise ValueError("assessed candidate count hypothesis must match geometry")
        expected_evidence = (
            ReviewOnlyEvidence
            if isinstance(self.geometry, ReviewOnlyGeometry)
            else DualLaneEvidence
            if isinstance(self.geometry, DualLaneSolution)
            else CandidateEvidence
        )
        if not isinstance(self.assessment.evidence, expected_evidence):
            raise ValueError("candidate geometry and evidence model must match")
        if isinstance(self.geometry, SequenceSolution):
            gate = self.assessment.gate
            if gate is None or gate.proof_paths != boundary_proof_paths_for_geometry(
                self.geometry,
                self.assessment.evidence,
            ):
                raise ValueError(
                    "candidate boundary proof paths must match geometry and evidence"
                )
        elif isinstance(self.geometry, DualLaneSolution):
            evidence = self.assessment.evidence
            gate = self.assessment.gate
            if not isinstance(evidence, DualLaneEvidence) or gate is None:
                raise ValueError("dual-lane candidate requires physical assessment")
            if len(self.geometry.lane_solutions) != len(evidence.lane_evidence):
                raise ValueError("dual-lane assessment must match component geometry")
            for lane_geometry, lane_evidence, lane_gate in zip(
                self.geometry.lane_solutions,
                evidence.lane_evidence,
                evidence.lane_gates,
                strict=True,
            ):
                CandidateAssessment(lane_evidence, lane_gate)
                if lane_gate.proof_paths != boundary_proof_paths_for_geometry(
                    lane_geometry,
                    lane_evidence,
                ):
                    raise ValueError(
                        "dual-lane component proof paths must match lane facts"
                    )
            if gate.proof_paths != boundary_proof_paths_for_dual_lane(
                self.geometry,
                evidence,
            ):
                raise ValueError(
                    "dual-lane composition proof must match lane facts"
                )

    @property
    def evidence_quality(self) -> EvidenceQuality:
        evidence_model = self.assessment.evidence
        if isinstance(evidence_model, ReviewOnlyEvidence):
            return EvidenceQuality(
                supported=(),
                contradicted=(),
                unavailable=(evidence_model.quality_unavailable_code,),
                covered_content_px=0,
                uncovered_content_px=0,
                supported_proof_paths=(),
                physical_residuals=self.geometry.residuals,
            )
        evidence_sets = (
            evidence_model.lane_evidence
            if isinstance(evidence_model, DualLaneEvidence)
            else (evidence_model,)
        )
        named_states: list[tuple[str, EvidenceState]] = []
        content_total = 0
        uncovered = 0
        for lane_index, evidence in enumerate(evidence_sets, start=1):
            prefix = (
                f"lane_{lane_index}:"
                if isinstance(evidence_model, DualLaneEvidence)
                else ""
            )
            named_states.extend(
                (f"{prefix}{code}", state)
                for code, state in (
                    ("frame_coverage", evidence.frame_coverage.state),
                    (
                        "frame_sequence_conservation",
                        evidence.sequence_conservation.state,
                    ),
                    ("separator_sequence", evidence.separator_sequence.state),
                    ("frame_dimensions", evidence.frame_dimensions.state),
                    ("frame_content", evidence.frame_content.state),
                    ("holder_texture", evidence.holder_texture.state),
                    ("content_preservation", evidence.content_preservation_state),
                    (
                        "sequence_content_alignment",
                        evidence.sequence_content_alignment.state,
                    ),
                    ("partial_edge_safety", evidence.partial_edge_safety.state),
                    ("evidence_independence", evidence.independence.state),
                )
            )
            content_total += sum(
                max(0, int(end) - int(start))
                for start, end in evidence.frame_coverage.content_runs
            )
            uncovered += sum(
                max(0, int(end) - int(start))
                for start, end in evidence.frame_coverage.uncovered_content
            )
        gate = self.assessment.gate
        if gate is None:
            raise ValueError("physical evidence quality requires CandidateGate")
        return EvidenceQuality(
            supported=tuple(
                code
                for code, state in named_states
                if state == EvidenceState.SUPPORTED
            ),
            contradicted=tuple(
                code
                for code, state in named_states
                if state == EvidenceState.CONTRADICTED
            ),
            unavailable=tuple(
                code
                for code, state in named_states
                if state == EvidenceState.UNAVAILABLE
            ),
            covered_content_px=max(0, content_total - uncovered),
            uncovered_content_px=uncovered,
            supported_proof_paths=tuple(
                path.code
                for path in gate.proof_paths
                if path.state == EvidenceState.SUPPORTED
            ),
            physical_residuals=self.geometry.residuals,
        )
