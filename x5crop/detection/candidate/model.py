from __future__ import annotations

from dataclasses import dataclass

from x5crop.domain import (
    EvidenceState,
    InterFrameSpacingBasis,
    InterFrameSpacingKind,
)

from ..physical.model import (
    CandidateGeometry,
    DualLaneFrameSolution,
    GeometryIdentityError,
    ReviewOnlyContainment,
    FrameSequenceSolution,
    ResolvedFrameBoundary,
    boundary_role_is_independent_physical_measurement,
)
from .assessment.evidence_independence import (
    EvidenceIndependenceEvidence,
    evidence_independence_evidence,
)
from ..evidence.separator_sequence import (
    SeparatorSequenceEvidence,
    separator_sequence_evidence,
)
from ..evidence.content.frame_content import FrameContentEvidence
from ..evidence.content.internal_frame_boundaries import (
    InternalFrameBoundaryPreservationEvidence,
    internal_frame_boundary_evidence_matches_geometry,
)
from ..evidence.holder_boundary import (
    HolderBoundaryEvidence,
    holder_boundary_evidence,
)
from ..evidence.frame_coverage import (
    FrameCoverageEvidence,
    frame_coverage_matches_geometry,
)
from ..evidence.frame_scale import (
    FrameScaleObservation,
    frame_scale_observations_match_geometry,
)
from ..evidence.frame_slot_topology import (
    FrameSlotTopologyEvidence,
    frame_slot_topology_evidence,
)
from ..evidence.holder_occupancy import (
    HolderOccupancyEvidence,
    HolderOccupancyState,
)
from ..evidence.content.external_frame_boundaries import (
    ExternalFramePreservationEvidence,
)
from ..evidence.partial_edge import (
    PartialEdgeSafetyEvidence,
    partial_edge_safety_evidence,
)
from ..physical.frame_dimensions import (
    FrameDimensionEvidence,
    frame_dimension_measurements_match_geometry,
)
from .assessment.model import CandidateGateAssessment, SequenceProofPath
from .plan.model import CountHypothesis
from ..physical.model import SequenceResiduals
from ..geometry_resolution import GeometryResolution


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
    frame_slot_topology: FrameSlotTopologyEvidence
    frame_coverage: FrameCoverageEvidence
    separator_sequence: SeparatorSequenceEvidence
    frame_dimensions: FrameDimensionEvidence
    frame_content: FrameContentEvidence
    internal_frame_boundary_preservation: InternalFrameBoundaryPreservationEvidence
    holder_boundary: HolderBoundaryEvidence
    frame_scale_observations: tuple[FrameScaleObservation, ...]
    external_frame_preservation: ExternalFramePreservationEvidence
    holder_occupancy: HolderOccupancyEvidence
    partial_edge_safety: PartialEdgeSafetyEvidence
    independence: EvidenceIndependenceEvidence

    @property
    def content_preservation_state(self) -> EvidenceState:
        return content_preservation_state(
            self.frame_coverage,
            self.internal_frame_boundary_preservation,
            self.external_frame_preservation,
            self.partial_edge_safety,
        )


@dataclass(frozen=True)
class DualLaneEvidence:
    lane_evidence: tuple[CandidateEvidence, ...]
    lane_gates: tuple[CandidateGateAssessment, ...]
    lane_geometry_resolutions: tuple[GeometryResolution, ...]

    def __post_init__(self) -> None:
        lane_count = len(self.lane_evidence)
        if lane_count <= 1:
            raise ValueError("dual-lane evidence requires multiple lane evidence sets")
        if (
            len(self.lane_gates) != lane_count
            or len(self.lane_geometry_resolutions) != lane_count
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
    internal_boundaries: InternalFrameBoundaryPreservationEvidence,
    external_boundaries: ExternalFramePreservationEvidence,
    partial_edge: PartialEdgeSafetyEvidence,
) -> EvidenceState:
    if frame_coverage.state == EvidenceState.CONTRADICTED:
        return EvidenceState.CONTRADICTED
    if internal_boundaries.state == EvidenceState.CONTRADICTED:
        return EvidenceState.CONTRADICTED
    if external_boundaries.state == EvidenceState.CONTRADICTED:
        return EvidenceState.CONTRADICTED
    if partial_edge.state == EvidenceState.CONTRADICTED:
        return EvidenceState.CONTRADICTED
    internal_boundaries_preserved = internal_boundaries.state in {
        EvidenceState.SUPPORTED,
        EvidenceState.NOT_APPLICABLE,
    }
    if (
        internal_boundaries_preserved
        and frame_coverage.state == EvidenceState.SUPPORTED
    ):
        return EvidenceState.SUPPORTED
    return EvidenceState.UNAVAILABLE


def _dimension_spacing_is_compatible(
    geometry: FrameSequenceSolution,
    evidence: CandidateEvidence,
) -> bool:
    observations = {
        item.boundary.boundary_index: item
        for item in evidence.internal_frame_boundary_preservation.observations
    }
    for spacing in geometry.inter_frame_spacings:
        if not (
            spacing.kind == InterFrameSpacingKind.OVERLAP
            and spacing.basis == InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS
        ):
            continue
        observation = observations.get(spacing.boundary.boundary_index)
        if observation is None or not (
            observation.spacing_evidence.basis
            == InterFrameSpacingBasis.CORROBORATED_OVERLAP
            and observation.spacing_evidence.state == EvidenceState.SUPPORTED
        ):
            return False
    return True


def _boundary_role_is_dimension_independent(
    boundary: ResolvedFrameBoundary,
) -> bool:
    return boundary_role_is_independent_physical_measurement(boundary)


def _dimension_anchor_coverage_is_supported(
    geometry: FrameSequenceSolution,
) -> bool:
    anchor_indexes = tuple(
        index
        for index, (left, right) in enumerate(
            zip(geometry.frame_slots, geometry.frame_slots[1:]),
            start=1,
        )
        if _boundary_role_is_dimension_independent(left.trailing)
        and _boundary_role_is_dimension_independent(right.leading)
    )
    return bool(anchor_indexes)


def sequence_proof_paths_for_geometry(
    geometry: FrameSequenceSolution,
    evidence: CandidateEvidence,
) -> tuple[SequenceProofPath, ...]:
    slot_geometry_resolved = bool(
        evidence.frame_slot_topology.state == EvidenceState.SUPPORTED
        and geometry.shared_short_axis.supports_safe_crop
    )
    evidence_independent = bool(
        evidence.independence.state
        in {EvidenceState.SUPPORTED, EvidenceState.NOT_APPLICABLE}
    )
    separator_sequence_context = bool(
        evidence_independent and slot_geometry_resolved
    )
    separator_sequence_led = bool(
        geometry.count > 1
        and separator_sequence_context
        and evidence.separator_sequence.state == EvidenceState.SUPPORTED
    )
    dimension_anchor_coverage_supported = _dimension_anchor_coverage_is_supported(
        geometry
    )
    single_frame_physical_boundaries = bool(
        geometry.count == 1
        and geometry.frame_slots[0].leading.independently_observed
        and geometry.frame_slots[0].trailing.independently_observed
    )
    content_preservation_compatible = bool(
        evidence.content_preservation_state != EvidenceState.CONTRADICTED
    )
    dimension_spacing_compatible = _dimension_spacing_is_compatible(
        geometry,
        evidence,
    )
    dimension_sequence_led = bool(
        slot_geometry_resolved
        and evidence_independent
        and content_preservation_compatible
        and dimension_spacing_compatible
        and (
            single_frame_physical_boundaries
            or (
                geometry.count > 1
                and geometry.common_frame_width.state
                == EvidenceState.SUPPORTED
                and evidence.frame_dimensions.state == EvidenceState.SUPPORTED
                and dimension_anchor_coverage_supported
            )
        )
    )
    dimension_supporting_evidence = (
        (
            "independent_two_side_frame_boundaries",
            "content_preservation_compatible",
        )
        if single_frame_physical_boundaries
        else (
            "physical_frame_dimensions",
            "common_frame_width_resolution",
            "content_preservation_compatible",
            "inter_frame_spacing_physically_compatible",
            "independent_internal_boundary_anchor_coverage",
        )
    )
    partial_occupancy_led = bool(
        geometry.strip_mode == "partial"
        and evidence.partial_edge_safety.state == EvidenceState.SUPPORTED
        and evidence.holder_occupancy.occupancy_state
        == HolderOccupancyState.UNDERFILLED
        and slot_geometry_resolved
        and evidence_independent
    )
    return (
        SequenceProofPath(
            "separator_sequence_led",
            (
                EvidenceState.SUPPORTED
                if separator_sequence_led
                else EvidenceState.UNAVAILABLE
            ),
            (
                "complete_independent_separator_sequence",
                "separator_band_edge_binding",
                "cross_axis_separator_pixel_paths",
            ),
        ),
        SequenceProofPath(
            "dimension_sequence_led",
            (
                EvidenceState.SUPPORTED
                if dimension_sequence_led
                else EvidenceState.UNAVAILABLE
            ),
            dimension_supporting_evidence,
        ),
        SequenceProofPath(
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
                "resolved_frame_slot_sequence",
            ),
        ),
    )


def sequence_proof_paths_for_dual_lane(
    geometry: DualLaneFrameSolution,
    evidence: DualLaneEvidence,
) -> tuple[SequenceProofPath, ...]:
    composition_supported = bool(
        geometry.lane_divider.state == EvidenceState.SUPPORTED
        and all(gate.passed for gate in evidence.lane_gates)
        and all(
            resolution.supported
            for resolution in evidence.lane_geometry_resolutions
        )
    )
    return (
        SequenceProofPath(
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
    if states and all(state == EvidenceState.NOT_APPLICABLE for state in states):
        return EvidenceState.NOT_APPLICABLE
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
        "frame_slot_topology": combined("frame_slot_topology"),
        "content_preservation": content_preservation,
        "frame_dimension_consistency": combined("frame_dimensions"),
        "evidence_independence": combined("independence"),
    }


@dataclass(frozen=True)
class EvidenceQuality:
    supported: tuple[str, ...]
    contradicted: tuple[str, ...]
    unavailable: tuple[str, ...]
    internal_boundary_contradiction_count: int
    other_contradiction_count: int
    uncovered_content_px: int
    supported_proof_paths: tuple[str, ...]
    physical_residuals: SequenceResiduals | None

    def __post_init__(self) -> None:
        if min(
            self.internal_boundary_contradiction_count,
            self.other_contradiction_count,
            self.uncovered_content_px,
        ) < 0:
            raise ValueError("evidence quality counts cannot be negative")
        if (
            self.internal_boundary_contradiction_count
            + self.other_contradiction_count
            != len(self.contradicted)
        ):
            raise ValueError(
                "typed contradiction counts must match diagnostic contradictions"
            )


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


def _separator_and_holder_evidence_matches_geometry(
    geometry: FrameSequenceSolution,
    evidence: CandidateEvidence,
) -> bool:
    expected_holder = holder_boundary_evidence(
        geometry,
        evidence.holder_boundary.edge_texture_limit,
    )
    return bool(
        evidence.holder_boundary == expected_holder
        and evidence.separator_sequence == separator_sequence_evidence(geometry)
    )


def _candidate_evidence_matches_geometry(
    geometry: FrameSequenceSolution,
    evidence: CandidateEvidence,
) -> bool:
    content_indexes = tuple(
        observation.frame_index
        for observation in evidence.frame_content.observations
    )
    completeness = evidence.holder_occupancy.strip_completeness
    independent_separator_count = len(geometry.separator_assignments)
    return bool(
        evidence.frame_slot_topology == frame_slot_topology_evidence(geometry)
        and frame_coverage_matches_geometry(
            geometry,
            evidence.frame_coverage,
        )
        and (
            not content_indexes
            or content_indexes == tuple(range(1, geometry.count + 1))
        )
        and evidence.external_frame_preservation.frame_sequence_envelope
        == geometry.frame_sequence_envelope
        and evidence.external_frame_preservation.frame_count == geometry.count
        and evidence.holder_occupancy.holder_safety == geometry.holder_safety
        and evidence.holder_occupancy.sequence_leading_boundary
        == geometry.frame_slots[0].leading.position
        and evidence.holder_occupancy.sequence_trailing_boundary
        == geometry.frame_slots[-1].trailing.position
        and evidence.holder_occupancy.content_support_available
        == evidence.frame_content.support_available
        and evidence.holder_occupancy.frame_coverage_state
        == evidence.frame_coverage.state
        and evidence.holder_occupancy.frame_dimension_state
        == evidence.frame_dimensions.state
        and completeness.count == geometry.count
        and completeness.valid_frame_slot_count == len(geometry.frame_slots)
        and completeness.resolved_internal_boundary_count
        == sum(
            left.trailing.geometry_resolved
            and right.leading.geometry_resolved
            for left, right in zip(
                geometry.frame_slots,
                geometry.frame_slots[1:],
            )
        )
        and completeness.independent_separator_count
        == independent_separator_count
        and evidence.partial_edge_safety
        == partial_edge_safety_evidence(
            geometry,
            evidence.frame_coverage,
            evidence.frame_dimensions,
            evidence.frame_content,
        )
        and evidence.internal_frame_boundary_preservation
        and internal_frame_boundary_evidence_matches_geometry(
            geometry.frame_slots,
            geometry.inter_frame_spacings,
            evidence.internal_frame_boundary_preservation,
        )
        and evidence.independence == evidence_independence_evidence(geometry)
        and frame_scale_observations_match_geometry(
            geometry,
            evidence.frame_scale_observations,
        )
    )


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
            if isinstance(self.geometry, ReviewOnlyContainment)
            else DualLaneEvidence
            if isinstance(self.geometry, DualLaneFrameSolution)
            else CandidateEvidence
        )
        if not isinstance(self.assessment.evidence, expected_evidence):
            raise ValueError("candidate geometry and evidence model must match")
        if isinstance(self.geometry, FrameSequenceSolution):
            if not _candidate_evidence_matches_geometry(
                self.geometry,
                self.assessment.evidence,
            ):
                raise GeometryIdentityError(
                    "candidate evidence must match geometry"
                )
            if not frame_dimension_measurements_match_geometry(
                self.geometry,
                self.assessment.evidence.frame_dimensions,
            ):
                raise GeometryIdentityError(
                    "candidate frame dimension evidence must match geometry"
                )
            if not _separator_and_holder_evidence_matches_geometry(
                self.geometry,
                self.assessment.evidence,
            ):
                raise GeometryIdentityError(
                    "candidate separator and holder evidence must match geometry"
                )
            gate = self.assessment.gate
            if gate is None or gate.proof_paths != sequence_proof_paths_for_geometry(
                self.geometry,
                self.assessment.evidence,
            ):
                raise ValueError(
                    "candidate boundary proof paths must match geometry and evidence"
                )
        elif isinstance(self.geometry, DualLaneFrameSolution):
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
                if not _candidate_evidence_matches_geometry(
                    lane_geometry,
                    lane_evidence,
                ):
                    raise GeometryIdentityError(
                        "dual-lane evidence must match lane geometry"
                    )
                if not frame_dimension_measurements_match_geometry(
                    lane_geometry,
                    lane_evidence.frame_dimensions,
                ):
                    raise GeometryIdentityError(
                        "dual-lane frame dimension evidence must match lane geometry"
                    )
                if not _separator_and_holder_evidence_matches_geometry(
                    lane_geometry,
                    lane_evidence,
                ):
                    raise GeometryIdentityError(
                        "dual-lane separator and holder evidence must match lane geometry"
                    )
                CandidateAssessment(lane_evidence, lane_gate)
                if lane_gate.proof_paths != sequence_proof_paths_for_geometry(
                    lane_geometry,
                    lane_evidence,
                ):
                    raise ValueError(
                        "dual-lane component proof paths must match lane facts"
                    )
            if gate.proof_paths != sequence_proof_paths_for_dual_lane(
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
                internal_boundary_contradiction_count=0,
                other_contradiction_count=0,
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
        uncovered = 0
        internal_boundary_contradictions = 0
        for lane_index, evidence in enumerate(evidence_sets, start=1):
            prefix = (
                f"lane_{lane_index}:"
                if isinstance(evidence_model, DualLaneEvidence)
                else ""
            )
            named_states.extend(
                (f"{prefix}{code}", state)
                for code, state in (
                    ("frame_slot_topology", evidence.frame_slot_topology.state),
                    (
                        "frame_coverage",
                        evidence.frame_coverage.state,
                    ),
                    ("separator_sequence", evidence.separator_sequence.state),
                    ("frame_dimensions", evidence.frame_dimensions.state),
                    ("frame_content", evidence.frame_content.state),
                    (
                        "internal_frame_boundary_preservation",
                        evidence.internal_frame_boundary_preservation.state,
                    ),
                    ("holder_boundary", evidence.holder_boundary.state),
                    (
                        "external_frame_preservation",
                        evidence.external_frame_preservation.state,
                    ),
                    ("evidence_independence", evidence.independence.state),
                )
            )
            uncovered += sum(
                max(0, int(end) - int(start))
                for start, end in evidence.frame_coverage.uncovered_content
            )
            internal_boundary_contradictions += int(
                evidence.internal_frame_boundary_preservation.state
                == EvidenceState.CONTRADICTED
            )
        gate = self.assessment.gate
        if gate is None:
            raise ValueError("physical evidence quality requires CandidateGate")
        contradicted = tuple(
            code
            for code, state in named_states
            if state == EvidenceState.CONTRADICTED
        )
        return EvidenceQuality(
            supported=tuple(
                code
                for code, state in named_states
                if state == EvidenceState.SUPPORTED
            ),
            contradicted=contradicted,
            unavailable=tuple(
                code
                for code, state in named_states
                if state == EvidenceState.UNAVAILABLE
            ),
            internal_boundary_contradiction_count=(
                internal_boundary_contradictions
            ),
            other_contradiction_count=(
                len(contradicted) - internal_boundary_contradictions
            ),
            uncovered_content_px=uncovered,
            supported_proof_paths=tuple(
                path.code
                for path in gate.proof_paths
                if path.state == EvidenceState.SUPPORTED
            ),
            physical_residuals=self.geometry.residuals,
        )
