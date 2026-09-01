"""Consume one source-level common-Frame-width authority after closure."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from ...domain import EvidenceState, FiniteInterval, ObservationId
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
    SequenceBindingUse,
    SequenceFit,
)
from .template_phase_model import (
    PhaseFailureKind,
    PhaseFitResult,
    PhaseFitStatus,
)


_INDEPENDENT_WIDTH_ROLE_BASES = frozenset(
    {
        DirectRoleAuthorityBasis.SOURCE_WIDE_EDGE,
        DirectRoleAuthorityBasis.AGGREGATE_UNION,
        DirectRoleAuthorityBasis.SEPARATOR_PAIR,
    }
)


def _contact_frame_ordinals(fit: SequenceFit) -> frozenset[int]:
    return frozenset(
        ordinal
        for relation in fit.adjacency_relations
        if isinstance(relation, ContactRelation)
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
    INDEPENDENT_COMPLETE_FRAMES_UNAVAILABLE = (
        "independent_complete_frames_unavailable"
    )
    PHYSICAL_WIDTH_CONFLICT = "physical_width_conflict"


@dataclass(frozen=True)
class SourceFrameWidthAuthority:
    """One source W derived only after discrete placement is fixed."""

    authority_id: str
    state: EvidenceState
    selected_integer_slot_offset: int | None
    selected_role_observation_ids: tuple[ObservationId | None, ...]
    supporting_frame_ordinals: tuple[int, ...]
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
            or len(set(self.observation_ids)) != len(self.observation_ids)
            or tuple(sorted(self.observation_ids, key=str))
            != self.observation_ids
            or any(
                identity is not None and not isinstance(identity, ObservationId)
                for identity in self.selected_role_observation_ids
            )
            or any(
                not isinstance(identity, ObservationId)
                for identity in self.observation_ids
            )
            or supported
            != (
                self.selected_integer_slot_offset is not None
                and bool(self.selected_role_observation_ids)
                and len(self.supporting_frame_ordinals) >= 2
                and isinstance(self.width_px, FiniteInterval)
                and self.canonical_width_px is not None
                and self.width_px.contains(
                    float(self.canonical_width_px), epsilon=1.0e-9
                )
                and len(self.observation_ids) >= 4
                and self.failure_kind is None
                and self.reason is None
            )
            or failed
            != (
                self.width_px is None
                and self.canonical_width_px is None
                and not self.observation_ids
                and isinstance(
                    self.failure_kind,
                    SourceFrameWidthAuthorityFailureKind,
                )
                and bool(self.reason)
            )
        ):
            raise ValueError("source Frame-width authority is invalid")


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
        selected_role_observation_ids=(),
        supporting_frame_ordinals=(),
        width_px=None,
        canonical_width_px=None,
        observation_ids=(),
        failure_kind=failure_kind,
        reason=reason,
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
    contact_frames = _contact_frame_ordinals(fit)
    for frame_index, (start, end) in enumerate(
        zip(
            fit.role_bindings[0::2],
            fit.role_bindings[1::2],
            strict=True,
        )
    ):
        start_index = 2 * frame_index
        end_index = start_index + 1
        if frame_index + 1 in contact_frames:
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
    if len(spans) < 2:
        return source_geometry, _failed_source_width_authority(
            phase,
            EvidenceState.UNAVAILABLE,
            SourceFrameWidthAuthorityFailureKind.INDEPENDENT_COMPLETE_FRAMES_UNAVAILABLE,
            "source W requires at least two independently authorized complete Frames",
        )
    observed = FiniteInterval(
        min(item[1].minimum for item in spans),
        max(item[1].maximum for item in spans),
    )
    identities = tuple(
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
    _scale, normalized, _factor = width_state.canonical_state()
    canonical_width_px = width_state.design_extent_mm * normalized
    authority = SourceFrameWidthAuthority(
        authority_id=physical_fact_id(
            "source-frame-width-authority",
            phase.template.template_id,
            fit.phase_lattice_fit.integer_slot_offset,
            fit.binding_observation_ids,
            tuple(item[0] for item in spans),
            width_px,
            identities,
        ),
        state=EvidenceState.SUPPORTED,
        selected_integer_slot_offset=(
            fit.phase_lattice_fit.integer_slot_offset
        ),
        selected_role_observation_ids=fit.binding_observation_ids,
        supporting_frame_ordinals=tuple(item[0] for item in spans),
        width_px=width_px,
        canonical_width_px=canonical_width_px,
        observation_ids=identities,
        failure_kind=None,
        reason=None,
    )
    return calibrated, authority


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
        authority.selected_integer_slot_offset
        != fit.phase_lattice_fit.integer_slot_offset
        or authority.selected_role_observation_ids
        != fit.binding_observation_ids
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
    selected = replace(
        fit,
        pitch_fit=replace(
            fit.pitch_fit,
            frame_width_px=selected_width,
            canonical_frame_width_px=canonical,
        ),
    )
    return replace(phase, best=selected)


def _supporting_frame_ordinals(
    fit: SequenceFit,
    authority_ids: tuple[ObservationId, ...],
) -> tuple[int, ...]:
    registered = set(authority_ids)
    contact_frames = _contact_frame_ordinals(fit)
    ordinals: list[int] = []
    pairs = zip(
        fit.role_bindings[0::2],
        fit.role_bindings[1::2],
        strict=True,
    )
    for frame_ordinal, (start, end) in enumerate(pairs, start=1):
        if (
            frame_ordinal in contact_frames
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
    frame_width_observation_ids: tuple[ObservationId, ...],
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
    ):
        return fit, (), (), ()
    facts = {
        item.role_index: item for item in direct_role_authority.facts
    }
    width_ids = set(frame_width_observation_ids)
    strong_frames: list[int] = []
    strong_observations: set[ObservationId] = set()
    contact_frames = _contact_frame_ordinals(fit)
    for slot_index in range(fit.template.count):
        start_index = 2 * slot_index
        end_index = start_index + 1
        if slot_index + 1 in contact_frames:
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
        strong_observations.update(
            (start.observation_id, end.observation_id)
        )
    if (
        len(strong_frames) < 2
        or len(frame_width_observation_ids) < 4
        or not width_ids.issubset(strong_observations)
    ):
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
        tuple(strong_frames),
    )


def apply_correlated_frame_width_inference(
    fit: SequenceFit,
    *,
    frame_width_observation_ids: tuple[ObservationId, ...],
    direct_role_authority: DirectRoleBindingAuthority | None = None,
    sequence_edges: tuple[BoundaryEdgeObservation, ...] = (),
) -> SequenceFit:
    """Infer opposite roles from one shared W without promoting weak lines.

    A non-authoritative ``LOCAL_REFINEMENT`` may become validation-only when
    every W observation belongs to at least two other complete Frames whose
    edges have unconditional coordinate authority.  The weak observation
    remains typed validation provenance, while the opposite edge plus the
    full correlated W interval owns output geometry.  Phase anchors never
    yield this way.
    """

    if fit.frame_width_inference is not None:
        raise ValueError("Frame width inference was already assessed")
    (
        fit,
        validation_only_indices,
        validation_ids,
        independently_supported_ordinals,
    ) = _yield_local_roles_to_correlated_width(
        fit,
        direct_role_authority,
        sequence_edges,
        frame_width_observation_ids,
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
                failure_kind=(
                    FrameWidthInferenceFailureKind.COMPLETE_FRAME_UNOBSERVED
                ),
            ),
        )
    supporting_ordinals = (
        independently_supported_ordinals
        or _supporting_frame_ordinals(
            fit,
            frame_width_observation_ids,
        )
    )
    if (
        len(frame_width_observation_ids) < 4
        or len(set(frame_width_observation_ids))
        != len(frame_width_observation_ids)
        or len(supporting_ordinals) < 2
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
                failure_kind=(
                    FrameWidthInferenceFailureKind.COMMON_WIDTH_AUTHORITY_UNAVAILABLE
                ),
            ),
        )
    assessment = FrameWidthInferenceAssessment(
        state=EvidenceState.SUPPORTED,
        inferred_role_indices=missing,
        supporting_frame_ordinals=supporting_ordinals,
        width_px=fit.pitch_fit.frame_width_px,
        canonical_width_px=fit.pitch_fit.canonical_frame_width_px,
        observation_ids=frame_width_observation_ids,
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
    "calibrate_source_frame_width",
    "SourceFrameWidthAuthority",
    "SourceFrameWidthAuthorityFailureKind",
]
