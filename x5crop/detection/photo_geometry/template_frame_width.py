"""Consume one source-level common-Frame-width authority after closure."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

import numpy as np

from ...domain import (
    EvidenceState,
    FiniteInterval,
    ObservationId,
    PositiveInterval,
)
from .observation_types import BoundaryEdgeObservation
from .physical_identity import physical_fact_id
from .source_geometry import SourceScanGeometry
from .template_adjacency_coverage import AdjacencyCoverageState
from .template_direct_role_authority import (
    DirectRoleAuthorityBasis,
    DirectRoleBindingAuthority,
)
from .template_model import (
    ContactRelation,
    FrameWidthInferenceAssessment,
    FrameWidthInferenceFailureKind,
    OverlapRelation,
    SeparatorRelation,
    SequenceBindingUse,
    SequenceFit,
    SourceFrameWidthAuthorityBasis,
    realize_adjacency_relations,
)
from .template_lattice_authority import direct_lattice_constraint_basis
from .template_phase_model import (
    PhaseFailureKind,
    PhaseFitResult,
    PhaseFitStatus,
    SourceFrameWidthTopologyAssessment,
    SourceFrameWidthTopologyFact,
    SourceFrameWidthTopologyFailureKind,
)


_INDEPENDENT_WIDTH_ROLE_BASES = frozenset(
    {
        DirectRoleAuthorityBasis.SOURCE_WIDE_EDGE,
        DirectRoleAuthorityBasis.AGGREGATE_UNION,
        DirectRoleAuthorityBasis.SEPARATOR_PAIR,
    }
)


def _topology_frame_ordinals(fit: SequenceFit) -> frozenset[int]:
    return frozenset(
        ordinal
        for relation in fit.adjacency_relations
        if isinstance(relation, (ContactRelation, OverlapRelation))
        for ordinal in (
            relation.relation_ordinal,
            relation.relation_ordinal + 1,
        )
    )


class SourceFrameWidthAuthorityFailureKind(str, Enum):
    """Why selected-only source W cannot be established."""

    UNIQUE_PLACEMENT_UNAVAILABLE = "unique_placement_unavailable"
    DIRECT_ROLE_AUTHORITY_UNAVAILABLE = "direct_role_authority_unavailable"
    DIRECT_ROLE_AUTHORITY_CONTRADICTED = "direct_role_authority_contradicted"
    GLOBAL_LATTICE_RANK_INSUFFICIENT = "global_lattice_rank_insufficient"
    ADJACENCY_COVERAGE_INCOMPLETE = "adjacency_coverage_incomplete"
    SOURCE_WIDTH_CLOSURE_UNAVAILABLE = "source_width_closure_unavailable"
    PHYSICAL_WIDTH_CONFLICT = "physical_width_conflict"


@dataclass(frozen=True)
class SourceFrameWidthAuthority:
    """One source W derived only after discrete placement is fixed."""

    authority_id: str
    state: EvidenceState
    selected_integer_slot_offset: int | None
    selected_phase_anchor_observation_ids: tuple[ObservationId | None, ...]
    supporting_role_observation_ids: tuple[ObservationId | None, ...]
    basis: SourceFrameWidthAuthorityBasis | None
    supporting_frame_ordinals: tuple[int, ...]
    supporting_constraint_ids: tuple[str, ...]
    width_px: FiniteInterval | None
    canonical_width_px: float | None
    observation_ids: tuple[ObservationId, ...]
    failure_kind: SourceFrameWidthAuthorityFailureKind | None
    reason: str | None

    def __post_init__(self) -> None:
        supported = self.state == EvidenceState.SUPPORTED
        failed = self.state in {
            EvidenceState.UNAVAILABLE,
            EvidenceState.CONTRADICTED,
        }
        if (
            not self.authority_id
            or not (supported or failed)
            or tuple(sorted(set(self.supporting_frame_ordinals)))
            != self.supporting_frame_ordinals
            or any(ordinal <= 0 for ordinal in self.supporting_frame_ordinals)
            or tuple(sorted(set(self.supporting_constraint_ids)))
            != self.supporting_constraint_ids
            or any(not identity for identity in self.supporting_constraint_ids)
            or len(set(self.observation_ids)) != len(self.observation_ids)
            or tuple(sorted(self.observation_ids, key=str))
            != self.observation_ids
            or any(
                identity is not None and not isinstance(identity, ObservationId)
                for identity in (
                    *self.selected_phase_anchor_observation_ids,
                    *self.supporting_role_observation_ids,
                )
            )
            or any(
                not isinstance(identity, ObservationId)
                for identity in self.observation_ids
            )
            or supported
            != (
                self.selected_integer_slot_offset is not None
                and bool(self.selected_phase_anchor_observation_ids)
                and any(self.selected_phase_anchor_observation_ids)
                and len(self.supporting_role_observation_ids)
                == len(self.selected_phase_anchor_observation_ids)
                and any(self.supporting_role_observation_ids)
                and {
                    identity
                    for identity in self.supporting_role_observation_ids
                    if identity is not None
                }
                == set(self.observation_ids)
                and isinstance(self.basis, SourceFrameWidthAuthorityBasis)
                and isinstance(self.width_px, FiniteInterval)
                and self.canonical_width_px is not None
                and self.width_px.contains(
                    float(self.canonical_width_px), epsilon=1.0e-9
                )
                and (
                    (
                        self.basis
                        == SourceFrameWidthAuthorityBasis
                        .INDEPENDENT_COMPLETE_FRAMES
                        and len(self.supporting_frame_ordinals) >= 2
                        and not self.supporting_constraint_ids
                        and len(self.observation_ids) >= 4
                    )
                    or (
                        self.basis
                        == SourceFrameWidthAuthorityBasis
                        .DIRECT_LATTICE_CLOSURE
                        and not self.supporting_frame_ordinals
                        and len(self.supporting_constraint_ids) == 3
                        and len(self.observation_ids) == 3
                    )
                    or (
                        self.basis
                        == SourceFrameWidthAuthorityBasis
                        .RECONCILED_DIRECT_CONSTRAINTS
                        and len(self.supporting_frame_ordinals) >= 2
                        and len(self.supporting_constraint_ids) == 3
                        and len(self.observation_ids) >= 4
                    )
                )
                and self.failure_kind is None
                and self.reason is None
            )
            or failed
            != (
                self.width_px is None
                and self.canonical_width_px is None
                and self.basis is None
                and not self.selected_phase_anchor_observation_ids
                and not self.supporting_role_observation_ids
                and not self.supporting_constraint_ids
                and not self.observation_ids
                and isinstance(
                    self.failure_kind,
                    SourceFrameWidthAuthorityFailureKind,
                )
                and bool(self.reason)
            )
        ):
            raise ValueError("source Frame-width authority is invalid")

    def matches_selected_placement(self, fit: SequenceFit) -> bool:
        """Check immutable discrete identity and every W-owning role."""

        if self.state != EvidenceState.SUPPORTED:
            return False
        phase_anchor_ids = tuple(
            binding.observation_id
            if binding is not None
            and binding.use == SequenceBindingUse.PHASE_ANCHOR
            else None
            for binding in fit.role_bindings
        )
        if (
            self.selected_integer_slot_offset
            != fit.phase_lattice_fit.integer_slot_offset
            or phase_anchor_ids != self.selected_phase_anchor_observation_ids
        ):
            return False
        return all(
            expected is None
            or binding is not None
            and binding.observation_id == expected
            for expected, binding in zip(
                self.supporting_role_observation_ids,
                fit.role_bindings,
                strict=True,
            )
        )


def _failed_source_width_authority(
    phase: PhaseFitResult,
    state: EvidenceState,
    failure_kind: SourceFrameWidthAuthorityFailureKind,
    reason: str,
) -> SourceFrameWidthAuthority:
    fit = phase.best
    return SourceFrameWidthAuthority(
        authority_id=physical_fact_id(
            "source-frame-width-authority",
            phase.template.template_id,
            phase.status.value,
            failure_kind.value,
            () if fit is None else fit.binding_observation_ids,
        ),
        state=state,
        selected_integer_slot_offset=None,
        selected_phase_anchor_observation_ids=(),
        supporting_role_observation_ids=(),
        basis=None,
        supporting_frame_ordinals=(),
        supporting_constraint_ids=(),
        width_px=None,
        canonical_width_px=None,
        observation_ids=(),
        failure_kind=failure_kind,
        reason=reason,
    )


def _direct_lattice_width_projection(
    phase: PhaseFitResult,
) -> tuple[FiniteInterval, tuple[ObservationId, ...], tuple[str, ...]] | None:
    """Project a retained rank-three direct system onto its correlated W."""

    fit = phase.best
    lattice = phase.global_lattice_authority
    if (
        fit is None
        or lattice is None
        or any(
            isinstance(relation, (ContactRelation, OverlapRelation))
            for relation in fit.adjacency_relations
        )
    ):
        return None
    constraints = direct_lattice_constraint_basis(lattice)
    if not constraints:
        return None
    matrix = np.asarray(
        [constraint.coefficients for constraint in constraints],
        dtype=np.float64,
    )
    inverse = np.linalg.inv(matrix)
    width_coefficients = inverse[1]
    minimum = 0.0
    maximum = 0.0
    for coefficient, constraint in zip(
        width_coefficients,
        constraints,
        strict=True,
    ):
        interval = constraint.value_interval_px
        if interval is None:
            raise ValueError("direct lattice basis lacks a coordinate interval")
        values = (
            coefficient * interval.minimum,
            coefficient * interval.maximum,
        )
        minimum += min(values)
        maximum += max(values)
    fitted = fit.pitch_fit.frame_width_px
    minimum = max(minimum, fitted.minimum)
    maximum = min(maximum, fitted.maximum)
    if maximum < minimum:
        raise ValueError("direct lattice W leaves its fitted physical interval")
    observation_ids = tuple(
        sorted(
            {
                identity
                for constraint in constraints
                for identity in constraint.observation_ids
            },
            key=str,
        )
    )
    return (
        FiniteInterval(float(minimum), float(maximum)),
        observation_ids,
        tuple(sorted(constraint.constraint_id for constraint in constraints)),
    )


def calibrate_source_frame_width(
    source_geometry: SourceScanGeometry,
    phase: PhaseFitResult,
    sequence_edges: tuple[BoundaryEdgeObservation, ...],
) -> tuple[SourceScanGeometry, SourceFrameWidthAuthority]:
    """Narrow source W from authorized Frames after candidate selection.

    The candidate has already fixed ordinal ownership and exposed direct-role,
    coverage and pre-W lattice assessments.  Source W may add one correlated
    constraint afterwards; it never recompiles the template, deletes a runner
    or changes the selected ordinal mapping.  Outer-Frame authority remains a
    final Grid-inference Gate and is not a prerequisite for measuring W from
    other directly observed complete Frames.
    """

    fit = phase.best
    if phase.status != PhaseFitStatus.RESOLVED or fit is None:
        return source_geometry, _failed_source_width_authority(
            phase,
            EvidenceState.UNAVAILABLE,
            SourceFrameWidthAuthorityFailureKind.UNIQUE_PLACEMENT_UNAVAILABLE,
            "source W requires one uniquely resolved discrete placement",
        )
    direct = phase.direct_role_binding_authority
    if direct is None:
        return source_geometry, _failed_source_width_authority(
            phase,
            EvidenceState.UNAVAILABLE,
            SourceFrameWidthAuthorityFailureKind.DIRECT_ROLE_AUTHORITY_UNAVAILABLE,
            "source W requires typed direct-role authority facts",
        )
    if direct.state == EvidenceState.CONTRADICTED:
        return source_geometry, _failed_source_width_authority(
            phase,
            EvidenceState.CONTRADICTED,
            SourceFrameWidthAuthorityFailureKind.DIRECT_ROLE_AUTHORITY_CONTRADICTED,
            "source W cannot consume a material-contradicted role binding",
        )
    unavailable_phase_anchors = tuple(
        fact.role_index
        for fact in direct.facts
        if fact.state == EvidenceState.UNAVAILABLE
        and fit.role_bindings[fact.role_index] is not None
        and fit.role_bindings[fact.role_index].use
        == SequenceBindingUse.PHASE_ANCHOR
    )
    if unavailable_phase_anchors:
        return source_geometry, _failed_source_width_authority(
            phase,
            EvidenceState.UNAVAILABLE,
            SourceFrameWidthAuthorityFailureKind.DIRECT_ROLE_AUTHORITY_UNAVAILABLE,
            "source W cannot consume unavailable phase-anchor roles: "
            + ", ".join(map(str, unavailable_phase_anchors)),
        )
    lattice = phase.global_lattice_authority
    if lattice is None or lattice.joint_constraint_rank < 2:
        return source_geometry, _failed_source_width_authority(
            phase,
            EvidenceState.UNAVAILABLE,
            SourceFrameWidthAuthorityFailureKind.GLOBAL_LATTICE_RANK_INSUFFICIENT,
            "source W may close only the final unknown of an already rank-2 lattice",
        )
    inferred_coverage = tuple(
        item
        for item in phase.adjacency_observation_coverage
        if item.normal_inference_required
    )
    if any(
        item.state != AdjacencyCoverageState.COMPLETE
        for item in inferred_coverage
    ):
        return source_geometry, _failed_source_width_authority(
            phase,
            EvidenceState.UNAVAILABLE,
            SourceFrameWidthAuthorityFailureKind.ADJACENCY_COVERAGE_INCOMPLETE,
            "source W requires complete coverage for every inferred adjacency",
        )
    by_id = {item.observation_id: item for item in sequence_edges}
    facts = {item.role_index: item for item in direct.facts}
    physical = source_geometry.width_state.extent_projection_px()
    spans: list[
        tuple[int, FiniteInterval, tuple[ObservationId, ObservationId]]
    ] = []
    topology_frames = _topology_frame_ordinals(fit)
    for frame_index, (start, end) in enumerate(
        zip(
            fit.role_bindings[0::2],
            fit.role_bindings[1::2],
            strict=True,
        )
    ):
        start_index = 2 * frame_index
        end_index = start_index + 1
        if frame_index + 1 in topology_frames:
            continue
        start_fact = facts.get(start_index)
        end_fact = facts.get(end_index)
        if (
            start is None
            or end is None
            or start_fact is None
            or end_fact is None
            or start_fact.state != EvidenceState.SUPPORTED
            or end_fact.state != EvidenceState.SUPPORTED
            or not set(start_fact.bases) & _INDEPENDENT_WIDTH_ROLE_BASES
            or not set(end_fact.bases) & _INDEPENDENT_WIDTH_ROLE_BASES
            or start.evidence_group_id == end.evidence_group_id
        ):
            continue
        if (
            start.observation_id not in by_id
            or end.observation_id not in by_id
        ):
            raise ValueError("source W binding leaves the observation ledger")
        start_edge = by_id[start.observation_id]
        end_edge = by_id[end.observation_id]
        if fit.template.direction > 0:
            measured = FiniteInterval(
                end_edge.full_position_interval_px.minimum
                - start_edge.full_position_interval_px.maximum,
                end_edge.full_position_interval_px.maximum
                - start_edge.full_position_interval_px.minimum,
            )
        else:
            measured = FiniteInterval(
                start_edge.full_position_interval_px.minimum
                - end_edge.full_position_interval_px.maximum,
                start_edge.full_position_interval_px.maximum
                - end_edge.full_position_interval_px.minimum,
            )
        minimum = max(measured.minimum, physical.minimum)
        maximum = min(measured.maximum, physical.maximum)
        if maximum < minimum:
            return source_geometry, _failed_source_width_authority(
                phase,
                EvidenceState.CONTRADICTED,
                SourceFrameWidthAuthorityFailureKind.PHYSICAL_WIDTH_CONFLICT,
                "an authorized complete Frame contradicts the physical W interval",
            )
        spans.append(
            (
                frame_index + 1,
                FiniteInterval(minimum, maximum),
                (start.observation_id, end.observation_id),
            )
        )
    complete_frame_projection = (
        FiniteInterval(
            min(item[1].minimum for item in spans),
            max(item[1].maximum for item in spans),
        )
        if len(spans) >= 2
        else None
    )
    complete_frame_identities = tuple(
        sorted(
            {
                identity
                for _ordinal, _interval, pair in spans
                for identity in pair
            },
            key=str,
        )
    )
    try:
        lattice_projection = _direct_lattice_width_projection(phase)
    except ValueError:
        if complete_frame_projection is None:
            return source_geometry, _failed_source_width_authority(
                phase,
                EvidenceState.CONTRADICTED,
                SourceFrameWidthAuthorityFailureKind.PHYSICAL_WIDTH_CONFLICT,
                "retained direct lattice W contradicts its fitted physical state",
            )
        # A residual-compatible overdetermined direct system can have no
        # single exact rank-three projection.  It therefore contributes no
        # second W constraint; the independent complete-Frame authority
        # remains valid and retains its full conservative hull.
        lattice_projection = None
    if complete_frame_projection is not None and lattice_projection is not None:
        lattice_width, lattice_identities, constraint_ids = lattice_projection
        minimum = max(
            complete_frame_projection.minimum,
            lattice_width.minimum,
        )
        maximum = min(
            complete_frame_projection.maximum,
            lattice_width.maximum,
        )
        if maximum < minimum:
            return source_geometry, _failed_source_width_authority(
                phase,
                EvidenceState.CONTRADICTED,
                SourceFrameWidthAuthorityFailureKind.PHYSICAL_WIDTH_CONFLICT,
                "complete-Frame and direct-lattice W constraints do not intersect",
            )
        basis = (
            SourceFrameWidthAuthorityBasis.RECONCILED_DIRECT_CONSTRAINTS
        )
        supporting_frame_ordinals = tuple(item[0] for item in spans)
        observed = FiniteInterval(minimum, maximum)
        identities = tuple(
            sorted(
                {
                    *complete_frame_identities,
                    *lattice_identities,
                },
                key=str,
            )
        )
    elif complete_frame_projection is not None:
        basis = SourceFrameWidthAuthorityBasis.INDEPENDENT_COMPLETE_FRAMES
        supporting_frame_ordinals = tuple(item[0] for item in spans)
        observed = complete_frame_projection
        identities = complete_frame_identities
        constraint_ids = ()
    elif lattice_projection is not None:
        basis = SourceFrameWidthAuthorityBasis.DIRECT_LATTICE_CLOSURE
        supporting_frame_ordinals = ()
        observed, identities, constraint_ids = lattice_projection
    else:
        return source_geometry, _failed_source_width_authority(
            phase,
            EvidenceState.UNAVAILABLE,
            SourceFrameWidthAuthorityFailureKind
            .SOURCE_WIDTH_CLOSURE_UNAVAILABLE,
            "source W requires either two independent complete Frames "
            "or one retained rank-three direct lattice",
        )
    try:
        width_state = source_geometry.width_state.intersect_observed_extent(
            observed,
            observation_ids=identities,
        )
    except ValueError:
        return source_geometry, _failed_source_width_authority(
            phase,
            EvidenceState.CONTRADICTED,
            SourceFrameWidthAuthorityFailureKind.PHYSICAL_WIDTH_CONFLICT,
            "authorized Frame widths have no common physical source state",
        )
    try:
        # The selected fit is a compatibility constraint, not new pixel
        # evidence.  Clip the correlated source state before publishing the
        # authority so an incompatible W becomes typed counterevidence rather
        # than a runtime exception in the selected-only consumer.
        width_state = width_state.intersect_inferred_extent(
            FiniteInterval(
                fit.pitch_fit.frame_width_px.minimum,
                fit.pitch_fit.frame_width_px.maximum,
            )
        )
    except ValueError:
        return source_geometry, _failed_source_width_authority(
            phase,
            EvidenceState.CONTRADICTED,
            SourceFrameWidthAuthorityFailureKind.PHYSICAL_WIDTH_CONFLICT,
            "selected placement W contradicts the direct source W state",
        )
    calibrated = SourceScanGeometry.from_axis_states(
        source_geometry.frame_spec,
        width_state,
        source_geometry.height_state,
    )
    width_px = width_state.extent_projection_px()
    if basis == SourceFrameWidthAuthorityBasis.DIRECT_LATTICE_CLOSURE:
        canonical_width_px = fit.pitch_fit.canonical_frame_width_px
        if not width_px.contains(canonical_width_px, epsilon=1.0e-9):
            return source_geometry, _failed_source_width_authority(
                phase,
                EvidenceState.CONTRADICTED,
                SourceFrameWidthAuthorityFailureKind.PHYSICAL_WIDTH_CONFLICT,
                "direct lattice canonical W leaves the physical source state",
            )
    else:
        _scale, normalized, _factor = width_state.canonical_state()
        canonical_width_px = width_state.design_extent_mm * normalized
    phase_anchor_ids = tuple(
        binding.observation_id
        if binding is not None
        and binding.use == SequenceBindingUse.PHASE_ANCHOR
        else None
        for binding in fit.role_bindings
    )
    identity_set = set(identities)
    supporting_role_ids = tuple(
        binding.observation_id
        if binding is not None
        and binding.observation_id in identity_set
        else None
        for binding in fit.role_bindings
    )
    authority = SourceFrameWidthAuthority(
        authority_id=physical_fact_id(
            "source-frame-width-authority",
            phase.template.template_id,
            fit.phase_lattice_fit.integer_slot_offset,
            phase_anchor_ids,
            supporting_role_ids,
            basis.value,
            supporting_frame_ordinals,
            constraint_ids,
            width_px,
            identities,
        ),
        state=EvidenceState.SUPPORTED,
        selected_integer_slot_offset=(
            fit.phase_lattice_fit.integer_slot_offset
        ),
        selected_phase_anchor_observation_ids=phase_anchor_ids,
        supporting_role_observation_ids=supporting_role_ids,
        basis=basis,
        supporting_frame_ordinals=supporting_frame_ordinals,
        supporting_constraint_ids=constraint_ids,
        width_px=width_px,
        canonical_width_px=canonical_width_px,
        observation_ids=identities,
        failure_kind=None,
        reason=None,
    )
    return calibrated, authority


def _source_width_boundary(
    fit: SequenceFit,
    role_index: int,
    width_px: FiniteInterval,
    canonical_width_px: float,
) -> tuple[FiniteInterval, float, bool]:
    """Resolve one output role and identify correlated-W opposite inference."""

    binding = fit.role_bindings[role_index]
    if binding is not None:
        return (
            binding.full_position_interval_px,
            binding.canonical_position_px,
            False,
        )
    opposite_index = (
        role_index + 1 if role_index % 2 == 0 else role_index - 1
    )
    opposite = fit.role_bindings[opposite_index]
    if opposite is None:
        return (
            fit.model_full_role_intervals_px[role_index],
            fit.model_role_positions_px[role_index],
            False,
        )
    direction = fit.template.direction
    if role_index % 2 == 0:
        canonical = (
            opposite.canonical_position_px - direction * canonical_width_px
        )
        interval = (
            FiniteInterval(
                opposite.full_position_interval_px.minimum - width_px.maximum,
                opposite.full_position_interval_px.maximum - width_px.minimum,
            )
            if direction > 0
            else FiniteInterval(
                opposite.full_position_interval_px.minimum + width_px.minimum,
                opposite.full_position_interval_px.maximum + width_px.maximum,
            )
        )
    else:
        canonical = (
            opposite.canonical_position_px + direction * canonical_width_px
        )
        interval = (
            FiniteInterval(
                opposite.full_position_interval_px.minimum + width_px.minimum,
                opposite.full_position_interval_px.maximum + width_px.maximum,
            )
            if direction > 0
            else FiniteInterval(
                opposite.full_position_interval_px.minimum - width_px.maximum,
                opposite.full_position_interval_px.maximum - width_px.minimum,
            )
        )
    return interval, canonical, True


def _assess_source_frame_width_topology(
    fit: SequenceFit,
    authority: SourceFrameWidthAuthority,
) -> SourceFrameWidthTopologyAssessment:
    """Require every correlated-W opposite to preserve normal adjacency.

    This selected-only check does not choose a favorable width.  It evaluates
    the complete authorized W interval against the native adjacent boundaries;
    an interval spanning both normal and unproved-overlap states remains typed
    unresolved.
    """

    if (
        authority.state != EvidenceState.SUPPORTED
        or authority.width_px is None
        or authority.canonical_width_px is None
    ):
        raise ValueError("source-W topology requires one supported authority")
    inference = fit.frame_width_inference
    inferred_role_indices = (
        frozenset(inference.inferred_role_indices)
        if inference is not None
        and inference.state == EvidenceState.SUPPORTED
        else frozenset()
    )
    if inference is not None and inference.state == EvidenceState.SUPPORTED:
        if inference.authority_id != authority.authority_id:
            raise ValueError("source-W topology uses another inference authority")
    facts: list[SourceFrameWidthTopologyFact] = []
    relations = {
        relation.relation_ordinal: relation
        for relation in fit.adjacency_relations
    }
    direction = fit.template.direction
    for relation_ordinal in range(1, fit.template.count):
        relation = relations.get(relation_ordinal)
        if relation is not None and (
            not isinstance(relation, SeparatorRelation)
            or relation.is_measured
        ):
            continue
        end_index = 2 * relation_ordinal - 1
        start_index = 2 * relation_ordinal
        authorized_indices = inferred_role_indices.intersection(
            {end_index, start_index}
        )
        if not authorized_indices:
            continue
        end_interval, end_canonical, end_inferred = _source_width_boundary(
            fit,
            end_index,
            authority.width_px,
            authority.canonical_width_px,
        )
        start_interval, start_canonical, start_inferred = (
            _source_width_boundary(
                fit,
                start_index,
                authority.width_px,
                authority.canonical_width_px,
            )
        )
        inferred_indices = tuple(
            index
            for index, inferred in (
                (end_index, end_inferred),
                (start_index, start_inferred),
            )
            if inferred and index in authorized_indices
        )
        if inferred_indices != tuple(sorted(authorized_indices)):
            raise ValueError(
                "source-W inference ledger disagrees with its missing roles"
            )
        signed_gap = (
            FiniteInterval(
                start_interval.minimum - end_interval.maximum,
                start_interval.maximum - end_interval.minimum,
            )
            if direction > 0
            else FiniteInterval(
                end_interval.minimum - start_interval.maximum,
                end_interval.maximum - start_interval.minimum,
            )
        )
        canonical_signed_gap = direction * (
            start_canonical - end_canonical
        )
        state = (
            EvidenceState.SUPPORTED
            if signed_gap.minimum >= -1.0e-9
            else EvidenceState.CONTRADICTED
            if signed_gap.maximum < -1.0e-9
            else EvidenceState.UNAVAILABLE
        )
        facts.append(
            SourceFrameWidthTopologyFact(
                relation_ordinal=relation_ordinal,
                inferred_role_indices=inferred_indices,
                signed_gap_interval_px=signed_gap,
                canonical_signed_gap_px=canonical_signed_gap,
                state=state,
            )
        )
    state = (
        EvidenceState.CONTRADICTED
        if any(item.state == EvidenceState.CONTRADICTED for item in facts)
        else EvidenceState.UNAVAILABLE
        if any(item.state == EvidenceState.UNAVAILABLE for item in facts)
        else EvidenceState.SUPPORTED
    )
    blocked = tuple(
        item.relation_ordinal
        for item in facts
        if item.state != EvidenceState.SUPPORTED
    )
    return SourceFrameWidthTopologyAssessment(
        source_frame_width_authority_id=authority.authority_id,
        state=state,
        facts=tuple(facts),
        failure_kind=(
            SourceFrameWidthTopologyFailureKind
            .NORMAL_ADJACENCY_CONTRADICTED
            if state == EvidenceState.CONTRADICTED
            else SourceFrameWidthTopologyFailureKind
            .NORMAL_ADJACENCY_UNRESOLVED
            if state == EvidenceState.UNAVAILABLE
            else None
        ),
        reason=(
            None
            if state == EvidenceState.SUPPORTED
            else "source W and native boundaries do not preserve normal "
            "adjacency for every feasible state at relation ordinals: "
            + ", ".join(map(str, blocked))
        ),
    )


def apply_selected_source_frame_width(
    phase: PhaseFitResult,
    authority: SourceFrameWidthAuthority,
) -> PhaseFitResult:
    """Narrow only the selected fit's continuous W; preserve every runner."""

    if authority.state == EvidenceState.CONTRADICTED:
        return replace(
            phase,
            status=PhaseFitStatus.UNRESOLVED,
            ambiguity_reason=(
                authority.reason
                or "direct source W contradicts the selected placement"
            ),
            failure_kind=PhaseFailureKind.SOURCE_FRAME_WIDTH_CONFLICT,
            winner_basis=None,
        )
    if authority.state != EvidenceState.SUPPORTED:
        return phase
    fit = phase.best
    if phase.status != PhaseFitStatus.RESOLVED or fit is None:
        raise ValueError("supported source W requires its selected placement")
    if (
        not authority.matches_selected_placement(fit)
    ):
        raise ValueError("source W authority belongs to a different placement")
    assert authority.width_px is not None
    assert authority.canonical_width_px is not None
    old_width = fit.pitch_fit.frame_width_px
    minimum = max(old_width.minimum, authority.width_px.minimum)
    maximum = min(old_width.maximum, authority.width_px.maximum)
    if maximum < minimum:
        raise ValueError("selected source W contradicts the fitted width interval")
    selected_width = FiniteInterval(minimum, maximum)
    canonical = authority.canonical_width_px
    if not selected_width.contains(canonical, epsilon=1.0e-9):
        raise ValueError("selected source W canonical state leaves the fit interval")
    selected_pitch_fit = replace(
        fit.pitch_fit,
        frame_width_px=selected_width,
        canonical_frame_width_px=canonical,
    )
    selected_relations = realize_adjacency_relations(
        fit.adjacency_relations,
        frame_width_interval_px=selected_width,
        pitch_interval_px=fit.pitch_fit.pitch_interval_px,
        frame_width_px=canonical,
        pitch_px=fit.pitch_fit.canonical_pitch_px,
    )
    selected = replace(
        fit,
        pitch_fit=selected_pitch_fit,
        adjacency_relations=selected_relations,
    )
    return replace(
        phase,
        best=selected,
        source_frame_width_topology_assessment=None,
    )


def assess_selected_source_frame_width_topology(
    phase: PhaseFitResult,
    authority: SourceFrameWidthAuthority,
) -> PhaseFitResult:
    """Assess only roles that correlated-W inference actually owns."""

    if authority.state != EvidenceState.SUPPORTED:
        return phase
    fit = phase.best
    if fit is None:
        raise ValueError("supported source W requires its selected placement")
    if not authority.matches_selected_placement(fit):
        raise ValueError("source W authority belongs to a different placement")
    topology = _assess_source_frame_width_topology(fit, authority)
    if (
        topology.state != EvidenceState.SUPPORTED
        and phase.status == PhaseFitStatus.RESOLVED
    ):
        return replace(
            phase,
            status=PhaseFitStatus.UNRESOLVED,
            ambiguity_reason=topology.reason,
            failure_kind=PhaseFailureKind.ADJACENCY_TOPOLOGY_UNRESOLVED,
            winner_basis=None,
            source_frame_width_topology_assessment=topology,
        )
    return replace(
        phase,
        source_frame_width_topology_assessment=topology,
    )


def _supporting_frame_ordinals(
    fit: SequenceFit,
    authority_ids: tuple[ObservationId, ...],
) -> tuple[int, ...]:
    registered = set(authority_ids)
    topology_frames = _topology_frame_ordinals(fit)
    ordinals: list[int] = []
    pairs = zip(
        fit.role_bindings[0::2],
        fit.role_bindings[1::2],
        strict=True,
    )
    for frame_ordinal, (start, end) in enumerate(pairs, start=1):
        if (
            frame_ordinal in topology_frames
            or start is None
            or end is None
            or start.evidence_group_id == end.evidence_group_id
            or start.observation_id not in registered
            or end.observation_id not in registered
        ):
            continue
        ordinals.append(frame_ordinal)
    return tuple(ordinals)


def _predicted_role_interval_from_opposite(
    fit: SequenceFit,
    role_index: int,
) -> FiniteInterval | None:
    opposite_index = role_index + 1 if role_index % 2 == 0 else role_index - 1
    opposite = fit.role_bindings[opposite_index]
    if opposite is None:
        return None
    width = fit.pitch_fit.frame_width_px
    interval = opposite.full_position_interval_px
    if role_index % 2 == 0:
        if fit.template.direction > 0:
            return FiniteInterval(
                interval.minimum - width.maximum,
                interval.maximum - width.minimum,
            )
        return FiniteInterval(
            interval.minimum + width.minimum,
            interval.maximum + width.maximum,
        )
    if fit.template.direction > 0:
        return FiniteInterval(
            interval.minimum + width.minimum,
            interval.maximum + width.maximum,
        )
    return FiniteInterval(
        interval.minimum - width.maximum,
        interval.maximum - width.minimum,
    )


def _overlaps(left: FiniteInterval, right: FiniteInterval) -> bool:
    return not (
        left.maximum < right.minimum or right.maximum < left.minimum
    )


def _yield_local_roles_to_correlated_width(
    fit: SequenceFit,
    direct_role_authority: DirectRoleBindingAuthority | None,
    sequence_edges: tuple[BoundaryEdgeObservation, ...],
    source_frame_width_authority: SourceFrameWidthAuthority | None,
) -> tuple[
    SequenceFit,
    tuple[int, ...],
    tuple[ObservationId, ...],
    tuple[int, ...],
]:
    """Remove only local weak coordinates that an independent W supersedes."""

    if (
        direct_role_authority is None
        or direct_role_authority.state == EvidenceState.CONTRADICTED
        or not direct_role_authority.unsupported_role_indices
        or not sequence_edges
        or source_frame_width_authority is None
        or source_frame_width_authority.state != EvidenceState.SUPPORTED
    ):
        return fit, (), (), ()
    facts = {
        item.role_index: item for item in direct_role_authority.facts
    }
    width_ids = set(source_frame_width_authority.observation_ids)
    strong_frames: list[int] = []
    topology_frames = _topology_frame_ordinals(fit)
    for slot_index in range(fit.template.count):
        start_index = 2 * slot_index
        end_index = start_index + 1
        if slot_index + 1 in topology_frames:
            continue
        start = fit.role_bindings[start_index]
        end = fit.role_bindings[end_index]
        start_fact = facts.get(start_index)
        end_fact = facts.get(end_index)
        if (
            start is None
            or end is None
            or start_fact is None
            or end_fact is None
            or start_fact.state != EvidenceState.SUPPORTED
            or end_fact.state != EvidenceState.SUPPORTED
            or not set(start_fact.bases) & _INDEPENDENT_WIDTH_ROLE_BASES
            or not set(end_fact.bases) & _INDEPENDENT_WIDTH_ROLE_BASES
            or start.observation_id not in width_ids
            or end.observation_id not in width_ids
            or start.evidence_group_id == end.evidence_group_id
        ):
            continue
        strong_frames.append(slot_index + 1)
    independent_complete_frames = (
        source_frame_width_authority.basis
        in {
            SourceFrameWidthAuthorityBasis.INDEPENDENT_COMPLETE_FRAMES,
            SourceFrameWidthAuthorityBasis.RECONCILED_DIRECT_CONSTRAINTS,
        }
        and len(strong_frames) >= 2
        and len(width_ids) >= 4
        and set(source_frame_width_authority.supporting_frame_ordinals)
        .issubset(strong_frames)
    )
    direct_lattice = (
        source_frame_width_authority.basis
        == SourceFrameWidthAuthorityBasis.DIRECT_LATTICE_CLOSURE
        and len(source_frame_width_authority.supporting_constraint_ids) == 3
        and len(width_ids) >= 3
    )
    if not (independent_complete_frames or direct_lattice):
        return fit, (), (), ()

    validation_only_indices: list[int] = []
    validation_ids: list[ObservationId] = []
    for role_index in direct_role_authority.unsupported_role_indices:
        fact = facts[role_index]
        binding = fit.role_bindings[role_index]
        opposite_index = (
            role_index + 1 if role_index % 2 == 0 else role_index - 1
        )
        opposite_fact = facts.get(opposite_index)
        if (
            binding is None
            or binding.use != SequenceBindingUse.LOCAL_REFINEMENT
            or binding.observation_id in width_ids
            or fact.state != EvidenceState.UNAVAILABLE
            or fact.independent_support_region_count != 2
            or opposite_fact is None
            or opposite_fact.state != EvidenceState.SUPPORTED
            or not set(opposite_fact.bases) & _INDEPENDENT_WIDTH_ROLE_BASES
        ):
            continue
        predicted = _predicted_role_interval_from_opposite(fit, role_index)
        if predicted is None:
            continue
        role = fit.template.roles[role_index].role
        compatible = tuple(
            item.observation_id
            for item in sequence_edges
            if role in item.qualified_anchor_roles
            and _overlaps(item.full_position_interval_px, predicted)
        )
        if compatible != (binding.observation_id,):
            continue
        validation_only_indices.append(role_index)
        validation_ids.append(binding.observation_id)
    if not validation_only_indices:
        return fit, (), (), ()
    bindings = list(fit.role_bindings)
    for role_index in validation_only_indices:
        bindings[role_index] = None
    if any(
        start is None and end is None
        for start, end in zip(bindings[0::2], bindings[1::2], strict=True)
    ):
        return fit, (), (), ()
    return (
        replace(
            fit,
            role_bindings=tuple(bindings),
            contradicted_observation_count=(
                fit.contradicted_observation_count
                + len(validation_only_indices)
            ),
        ),
        tuple(validation_only_indices),
        tuple(validation_ids),
        source_frame_width_authority.supporting_frame_ordinals,
    )


def apply_correlated_frame_width_inference(
    fit: SequenceFit,
    *,
    source_frame_width_authority: SourceFrameWidthAuthority | None,
    direct_role_authority: DirectRoleBindingAuthority | None = None,
    sequence_edges: tuple[BoundaryEdgeObservation, ...] = (),
    projected_counterevidence_role_indices: tuple[int, ...] = (),
) -> SequenceFit:
    """Infer opposite roles from one shared W without promoting weak lines.

    A non-authoritative ``LOCAL_REFINEMENT`` may become validation-only when a
    canonical source W excludes that weak line and its opposite edge predicts
    one unique compatible coordinate.  The weak observation remains typed
    validation provenance, while the opposite edge plus the full correlated W
    interval owns output geometry.  Phase anchors never yield this way.
    """

    if fit.frame_width_inference is not None:
        raise ValueError("Frame width inference was already assessed")
    if (
        tuple(sorted(set(projected_counterevidence_role_indices)))
        != projected_counterevidence_role_indices
        or any(index < 0 for index in projected_counterevidence_role_indices)
    ):
        raise ValueError("projected W counterevidence roles are invalid")
    if (
        source_frame_width_authority is not None
        and source_frame_width_authority.state == EvidenceState.SUPPORTED
        and not source_frame_width_authority.matches_selected_placement(fit)
    ):
        raise ValueError("source W inference belongs to another placement")
    (
        fit,
        validation_only_indices,
        validation_ids,
        independently_supported_ordinals,
    ) = _yield_local_roles_to_correlated_width(
        fit,
        direct_role_authority,
        sequence_edges,
        source_frame_width_authority,
    )
    missing = fit.unbound_role_indices
    if not missing:
        return fit
    if fit.completely_unobserved_frame_ordinals:
        return replace(
            fit,
            frame_width_inference=FrameWidthInferenceAssessment(
                state=EvidenceState.UNAVAILABLE,
                inferred_role_indices=missing,
                supporting_frame_ordinals=(),
                width_px=None,
                canonical_width_px=None,
                observation_ids=(),
                authority_id=None,
                authority_basis=None,
                failure_kind=(
                    FrameWidthInferenceFailureKind.COMPLETE_FRAME_UNOBSERVED
                ),
            ),
        )
    if (
        projected_counterevidence_role_indices
        and source_frame_width_authority is not None
        and source_frame_width_authority.state == EvidenceState.SUPPORTED
        and source_frame_width_authority.basis
        == SourceFrameWidthAuthorityBasis.DIRECT_LATTICE_CLOSURE
    ):
        return replace(
            fit,
            frame_width_inference=FrameWidthInferenceAssessment(
                state=EvidenceState.UNAVAILABLE,
                inferred_role_indices=missing,
                supporting_frame_ordinals=(),
                width_px=None,
                canonical_width_px=None,
                observation_ids=(),
                authority_id=None,
                authority_basis=None,
                failure_kind=(
                    FrameWidthInferenceFailureKind
                    .DIRECT_LATTICE_COUNTEREVIDENCE
                ),
            ),
        )
    supported_authority = (
        source_frame_width_authority is not None
        and source_frame_width_authority.state == EvidenceState.SUPPORTED
    )
    if supported_authority:
        assert source_frame_width_authority is not None
        frame_width_observation_ids = (
            source_frame_width_authority.observation_ids
        )
        supporting_ordinals = (
            independently_supported_ordinals
            or source_frame_width_authority.supporting_frame_ordinals
            or _supporting_frame_ordinals(
                fit,
                frame_width_observation_ids,
            )
        )
    else:
        frame_width_observation_ids = ()
        supporting_ordinals = ()
    if (
        not supported_authority
        or source_frame_width_authority is None
        or (
            source_frame_width_authority.basis
            in {
                SourceFrameWidthAuthorityBasis.INDEPENDENT_COMPLETE_FRAMES,
                SourceFrameWidthAuthorityBasis.RECONCILED_DIRECT_CONSTRAINTS,
            }
            and len(supporting_ordinals) < 2
        )
    ):
        return replace(
            fit,
            frame_width_inference=FrameWidthInferenceAssessment(
                state=EvidenceState.UNAVAILABLE,
                inferred_role_indices=missing,
                supporting_frame_ordinals=(),
                width_px=None,
                canonical_width_px=None,
                observation_ids=(),
                authority_id=None,
                authority_basis=None,
                failure_kind=(
                    FrameWidthInferenceFailureKind.COMMON_WIDTH_AUTHORITY_UNAVAILABLE
                ),
            ),
        )
    assert source_frame_width_authority.width_px is not None
    assert source_frame_width_authority.canonical_width_px is not None
    selected_width = fit.pitch_fit.frame_width_px
    selected_canonical_width = fit.pitch_fit.canonical_frame_width_px
    if (
        selected_width.minimum
        < source_frame_width_authority.width_px.minimum - 1.0e-9
        or selected_width.maximum
        > source_frame_width_authority.width_px.maximum + 1.0e-9
        or abs(
            selected_canonical_width
            - source_frame_width_authority.canonical_width_px
        )
        > 1.0e-9
    ):
        raise ValueError("selected fit escaped its source W authority")
    assessment = FrameWidthInferenceAssessment(
        state=EvidenceState.SUPPORTED,
        inferred_role_indices=missing,
        supporting_frame_ordinals=supporting_ordinals,
        width_px=PositiveInterval(
            selected_width.minimum,
            selected_width.maximum,
        ),
        canonical_width_px=selected_canonical_width,
        observation_ids=frame_width_observation_ids,
        authority_id=source_frame_width_authority.authority_id,
        authority_basis=source_frame_width_authority.basis,
        failure_kind=None,
        validation_only_role_indices=validation_only_indices,
        validation_observation_ids=validation_ids,
    )
    return replace(
        fit,
        frame_width_inference=assessment,
    )


__all__ = [
    "apply_correlated_frame_width_inference",
    "apply_selected_source_frame_width",
    "assess_selected_source_frame_width_topology",
    "calibrate_source_frame_width",
    "SourceFrameWidthAuthority",
    "SourceFrameWidthAuthorityFailureKind",
]
