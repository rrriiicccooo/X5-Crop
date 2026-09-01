"""Prove that every selected direct long-axis role may own its coordinate."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ...domain import EvidenceState, FiniteInterval, ObservationId
from .measurement_model import PhotoBoundaryMeasurementSet
from .model import (
    BoundaryRole,
    SPATIAL_SUPPORT_REGION_COUNT,
    independent_spatial_support_count,
)
from .observation_types import (
    BoundaryEdgeMeasurementBasis,
    BoundaryEdgeObservation,
    SeparatorBandObservation,
)
from .separator_material import (
    normal_separator_material_bands,
    normal_separator_material_conflicts,
)
from .template_model import SequenceFit


class DirectRoleAuthorityBasis(str, Enum):
    SOURCE_WIDE_EDGE = "source_wide_edge"
    AGGREGATE_UNION = "aggregate_union"
    SEPARATOR_PAIR = "separator_pair"
    PARTIAL_HEIGHT_SEPARATOR_PAIR = "partial_height_separator_pair"


_UNCONDITIONAL_DIRECT_ROLE_BASES = frozenset(
    {
        DirectRoleAuthorityBasis.SOURCE_WIDE_EDGE,
        DirectRoleAuthorityBasis.AGGREGATE_UNION,
        DirectRoleAuthorityBasis.SEPARATOR_PAIR,
    }
)


@dataclass(frozen=True)
class DirectRoleAuthorityFact:
    """The independent physical basis for one selected direct role."""

    role_index: int
    lane_ordinal: int
    role: BoundaryRole
    observation_id: ObservationId
    evidence_group_id: ObservationId
    independent_support_region_count: int
    bases: tuple[DirectRoleAuthorityBasis, ...]
    blocking_material_conflict_ids: tuple[ObservationId, ...]
    state: EvidenceState
    trace_coordinates_px: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if (
            self.role_index < 0
            or self.lane_ordinal != self.role_index // 2 + 1
            or self.role
            != (
                BoundaryRole.START
                if self.role_index % 2 == 0
                else BoundaryRole.END
            )
            or not isinstance(self.observation_id, ObservationId)
            or not isinstance(self.evidence_group_id, ObservationId)
            or not 1
            <= self.independent_support_region_count
            <= SPATIAL_SUPPORT_REGION_COUNT
            or tuple(dict.fromkeys(self.bases)) != self.bases
            or any(not isinstance(item, DirectRoleAuthorityBasis) for item in self.bases)
            or (
                DirectRoleAuthorityBasis.PARTIAL_HEIGHT_SEPARATOR_PAIR
                in self.bases
                and (
                    self.bases
                    != (
                        DirectRoleAuthorityBasis.PARTIAL_HEIGHT_SEPARATOR_PAIR,
                    )
                    or self.independent_support_region_count
                    != SPATIAL_SUPPORT_REGION_COUNT - 1
                )
            )
            or tuple(sorted(set(self.blocking_material_conflict_ids)))
            != self.blocking_material_conflict_ids
            or any(
                not isinstance(item, ObservationId)
                for item in self.blocking_material_conflict_ids
            )
            or self.state
            not in {
                EvidenceState.SUPPORTED,
                EvidenceState.CONTRADICTED,
                EvidenceState.UNAVAILABLE,
            }
            or (self.state == EvidenceState.CONTRADICTED)
            != bool(self.blocking_material_conflict_ids)
            or (self.state == EvidenceState.SUPPORTED)
            != (
                bool(self.bases)
                and not self.blocking_material_conflict_ids
            )
            or (self.state == EvidenceState.UNAVAILABLE)
            != (not self.bases and not self.blocking_material_conflict_ids)
            or (
                self.trace_coordinates_px
                and tuple(sorted(set(self.trace_coordinates_px)))
                != self.trace_coordinates_px
            )
            or any(
                not isinstance(item, int)
                for item in self.trace_coordinates_px
            )
            or (
                DirectRoleAuthorityBasis.PARTIAL_HEIGHT_SEPARATOR_PAIR
                in self.bases
                and not self.trace_coordinates_px
            )
        ):
            raise ValueError(
                "direct-role authority fact is invalid: "
                f"role={self.role_index}; "
                f"regions={self.independent_support_region_count}; "
                f"bases={tuple(item.value for item in self.bases)}; "
                f"state={self.state.value}"
            )


@dataclass(frozen=True)
class DirectRoleBindingAuthority:
    """Coordinate authority for every selected direct long-axis binding."""

    state: EvidenceState
    facts: tuple[DirectRoleAuthorityFact, ...]
    unsupported_role_indices: tuple[int, ...]
    reason: str | None

    def __post_init__(self) -> None:
        indices = tuple(item.role_index for item in self.facts)
        unsupported = tuple(
            item.role_index
            for item in self.facts
            if item.state != EvidenceState.SUPPORTED
        )
        expected_state = (
            EvidenceState.CONTRADICTED
            if any(
                item.state == EvidenceState.CONTRADICTED
                for item in self.facts
            )
            else EvidenceState.UNAVAILABLE
            if unsupported
            else EvidenceState.SUPPORTED
        )
        if (
            self.state != expected_state
            or indices != tuple(sorted(set(indices)))
            or self.unsupported_role_indices != unsupported
            or (self.state == EvidenceState.SUPPORTED) != (self.reason is None)
        ):
            raise ValueError("direct-role binding authority is invalid")

    @property
    def supported_role_indices(self) -> tuple[int, ...]:
        return tuple(
            item.role_index
            for item in self.facts
            if item.state == EvidenceState.SUPPORTED
        )

    @property
    def aperture_domain_required_role_indices(self) -> tuple[int, ...]:
        """Roles whose partial-height support needs a two-sided aperture domain."""

        return tuple(
            item.role_index
            for item in self.facts
            if item.state == EvidenceState.SUPPORTED
            and DirectRoleAuthorityBasis.PARTIAL_HEIGHT_SEPARATOR_PAIR
            in item.bases
        )


@dataclass(frozen=True)
class _DirectRoleAuthorityLedger:
    trace_lattice: tuple[float, ...]
    observations_by_id: dict[ObservationId, BoundaryEdgeObservation]
    support_region_counts: dict[ObservationId, int]
    source_wide_pairs: frozenset[tuple[ObservationId, ObservationId]]
    partial_height_pairs: frozenset[tuple[ObservationId, ObservationId]]
    reversed_normal_pair_conflicts: dict[
        tuple[ObservationId, ObservationId],
        tuple[ObservationId, ...],
    ]
    supported_material_roles: frozenset[tuple[ObservationId, BoundaryRole]]
    conflicts_by_edge_role: dict[
        tuple[ObservationId, BoundaryRole],
        tuple[tuple[ObservationId, ObservationId], ...],
    ]


def _ordered_separator_edge_pair(
    band: SeparatorBandObservation,
    direction: int,
) -> tuple[ObservationId, ObservationId]:
    """Return the physical END -> material -> START edge order."""

    if direction > 0:
        return (
            band.left_edge_observation_id,
            band.right_edge_observation_id,
        )
    return (
        band.right_edge_observation_id,
        band.left_edge_observation_id,
    )


def _trace_lattice_and_support_region_counts(
    observations: tuple[BoundaryEdgeObservation, ...],
    measurement_sets: tuple[PhotoBoundaryMeasurementSet, ...],
) -> tuple[tuple[float, ...], dict[ObservationId, int]]:
    """Return the one registered trace lattice and its per-edge coverage."""

    if not measurement_sets:
        raise ValueError("direct-role authority requires registered sequence queries")
    trace_lattice = measurement_sets[0].query.trace_positions_px
    if any(
        item.query.trace_positions_px != trace_lattice
        for item in measurement_sets[1:]
    ):
        raise ValueError("direct-role authority requires one trace lattice")
    by_id = {item.observation_id: item for item in observations}
    if len(by_id) != len(observations):
        raise ValueError("direct-role observations must be unique")
    return trace_lattice, {
        observation.observation_id: independent_spatial_support_count(
            trace_lattice,
            observation.trace_coordinates_px,
        )
        for observation in observations
    }


def intrinsic_direct_role_authority_bases(
    observations: tuple[BoundaryEdgeObservation, ...],
    measurement_sets: tuple[PhotoBoundaryMeasurementSet, ...],
) -> dict[ObservationId, tuple[DirectRoleAuthorityBasis, ...]]:
    """Identify edges that own coordinates without another selected edge.

    Separator-pair and partial-height transfer authority remain relational and
    are assessed only after a fixed role mapping exists.  This index contains
    the two observation-intrinsic bases so local refinement can ignore weak
    validation-only alternatives when an independently authoritative edge is
    already present in the same fixed role corridor.
    """

    _trace_lattice, region_counts = _trace_lattice_and_support_region_counts(
        observations,
        measurement_sets,
    )
    result: dict[ObservationId, tuple[DirectRoleAuthorityBasis, ...]] = {}
    for observation in observations:
        bases = tuple(
            basis
            for basis, eligible in (
                (
                    DirectRoleAuthorityBasis.SOURCE_WIDE_EDGE,
                    region_counts[observation.observation_id]
                    == SPATIAL_SUPPORT_REGION_COUNT
                    and observation.measurement_basis
                    == BoundaryEdgeMeasurementBasis.DIRECT_TRACE,
                ),
                (
                    DirectRoleAuthorityBasis.AGGREGATE_UNION,
                    observation.measurement_basis
                    == BoundaryEdgeMeasurementBasis.DIRECT_WITH_AGGREGATE,
                ),
            )
            if eligible
        )
        if bases:
            result[observation.observation_id] = bases
    return result


def _direct_role_authority_ledger(
    fit: SequenceFit,
    observations: tuple[BoundaryEdgeObservation, ...],
    separator_bands: tuple[SeparatorBandObservation, ...],
    measurement_sets: tuple[PhotoBoundaryMeasurementSet, ...],
) -> _DirectRoleAuthorityLedger:
    trace_lattice, region_counts = _trace_lattice_and_support_region_counts(
        observations,
        measurement_sets,
    )
    by_id = {item.observation_id: item for item in observations}
    role_authority_bands = normal_separator_material_bands(
        separator_bands,
        maximum_material_gap_px=fit.template.gap_prior_px.maximum,
    )
    ordered_role_authority_bands = tuple(
        (band, _ordered_separator_edge_pair(band, fit.template.direction))
        for band in role_authority_bands
    )
    source_wide_pairs = frozenset(
        ordered_pair
        for band, ordered_pair in ordered_role_authority_bands
        if band.material_support_region_count == SPATIAL_SUPPORT_REGION_COUNT
    )
    partial_height_pairs = frozenset(
        ordered_pair
        for band, ordered_pair in ordered_role_authority_bands
        if band.material_support_region_count
        == SPATIAL_SUPPORT_REGION_COUNT - 1
    )
    reversed_normal_pair_conflict_sets: dict[
        tuple[ObservationId, ObservationId],
        set[ObservationId],
    ] = {}
    for band, ordered_pair in ordered_role_authority_bands:
        reversed_normal_pair_conflict_sets.setdefault(
            (ordered_pair[1], ordered_pair[0]),
            set(),
        ).add(band.observation_id)
    supported_material_roles = frozenset(
        {
            (ordered_pair[0], BoundaryRole.END)
            for band, ordered_pair in ordered_role_authority_bands
            if band.material_support_region_count == SPATIAL_SUPPORT_REGION_COUNT
        }
        | {
            (ordered_pair[1], BoundaryRole.START)
            for band, ordered_pair in ordered_role_authority_bands
            if band.material_support_region_count == SPATIAL_SUPPORT_REGION_COUNT
        }
    )

    intrinsic_bases = intrinsic_direct_role_authority_bases(
        observations,
        measurement_sets,
    )
    potential_authority_roles = set(supported_material_roles)
    potential_authority_roles.update(
        (observation_id, role)
        for observation_id in intrinsic_bases
        for role in by_id[observation_id].qualified_anchor_roles
    )
    # A two-region band can transfer coordinate authority once, but only from
    # an intrinsically authoritative opposite edge.  Include that exact
    # potential role when deciding whether a material conflict is a legal
    # counter-explanation.
    for band, ordered_pair in ordered_role_authority_bands:
        if band.material_support_region_count != SPATIAL_SUPPORT_REGION_COUNT - 1:
            continue
        end_id, start_id = ordered_pair
        if end_id in intrinsic_bases:
            potential_authority_roles.add((start_id, BoundaryRole.START))
        if start_id in intrinsic_bases:
            potential_authority_roles.add((end_id, BoundaryRole.END))

    conflict_sets: dict[
        tuple[ObservationId, BoundaryRole],
        set[tuple[ObservationId, ObservationId]],
    ] = {}
    for conflict in normal_separator_material_conflicts(
        separator_bands,
        maximum_material_gap_px=fit.template.gap_prior_px.maximum,
    ):
        for edge_id, alternative_id in (
            (
                conflict.left_edge_observation_id,
                conflict.right_edge_observation_id,
            ),
            (
                conflict.right_edge_observation_id,
                conflict.left_edge_observation_id,
            ),
        ):
            alternative = by_id.get(alternative_id)
            if alternative is None:
                raise ValueError(
                    "separator material conflict references an unregistered edge"
                )
            for role in alternative.qualified_anchor_roles:
                if (alternative_id, role) in potential_authority_roles:
                    conflict_sets.setdefault((edge_id, role), set()).add(
                        (conflict.observation_id, alternative_id)
                    )
    return _DirectRoleAuthorityLedger(
        trace_lattice=trace_lattice,
        observations_by_id=by_id,
        support_region_counts=region_counts,
        source_wide_pairs=source_wide_pairs,
        partial_height_pairs=partial_height_pairs,
        reversed_normal_pair_conflicts={
            key: tuple(sorted(values))
            for key, values in reversed_normal_pair_conflict_sets.items()
        },
        supported_material_roles=supported_material_roles,
        conflicts_by_edge_role={
            key: tuple(
                sorted(values, key=lambda item: tuple(map(str, item)))
            )
            for key, values in conflict_sets.items()
        },
    )


def _assess_direct_role_binding_authority(
    fit: SequenceFit,
    ledger: _DirectRoleAuthorityLedger,
    *,
    authorized_source_frame_width_px: FiniteInterval | None = None,
) -> DirectRoleBindingAuthority:
    selected: dict[int, BoundaryEdgeObservation] = {}
    selected_evidence_groups: dict[int, ObservationId] = {}
    for role, binding in zip(fit.template.roles, fit.role_bindings, strict=True):
        if binding is None:
            continue
        observation = ledger.observations_by_id.get(binding.observation_id)
        if observation is None:
            raise ValueError("selected direct role is absent from the observation ledger")
        selected[role.role_index] = observation
        selected_evidence_groups[role.role_index] = binding.evidence_group_id

    def alternative_preserves_independent_width(
        role_index: int,
        alternative_id: ObservationId,
    ) -> bool:
        if authorized_source_frame_width_px is None:
            return True
        opposite_index = (
            role_index + 1 if role_index % 2 == 0 else role_index - 1
        )
        opposite = selected.get(opposite_index)
        if opposite is None:
            return True
        alternative = ledger.observations_by_id[alternative_id]
        if role_index % 2 == 0:
            start_interval = alternative.full_position_interval_px
            end_interval = opposite.full_position_interval_px
        else:
            start_interval = opposite.full_position_interval_px
            end_interval = alternative.full_position_interval_px
        if fit.template.direction > 0:
            possible_width = FiniteInterval(
                end_interval.minimum - start_interval.maximum,
                end_interval.maximum - start_interval.minimum,
            )
        else:
            possible_width = FiniteInterval(
                start_interval.minimum - end_interval.maximum,
                start_interval.maximum - end_interval.minimum,
            )
        return not (
            possible_width.maximum
            < authorized_source_frame_width_px.minimum
            or authorized_source_frame_width_px.maximum
            < possible_width.minimum
        )

    bases: dict[int, set[DirectRoleAuthorityBasis]] = {
        role_index: set() for role_index in selected
    }
    region_counts = {
        role_index: ledger.support_region_counts[observation.observation_id]
        for role_index, observation in selected.items()
    }
    for role_index, count in region_counts.items():
        observation = selected[role_index]
        if (
            count == SPATIAL_SUPPORT_REGION_COUNT
            and observation.measurement_basis
            == BoundaryEdgeMeasurementBasis.DIRECT_TRACE
        ):
            bases[role_index].add(DirectRoleAuthorityBasis.SOURCE_WIDE_EDGE)
        if (
            observation.measurement_basis
            == BoundaryEdgeMeasurementBasis.DIRECT_WITH_AGGREGATE
        ):
            bases[role_index].add(DirectRoleAuthorityBasis.AGGREGATE_UNION)

    for adjacency_index in range(max(0, fit.template.count - 1)):
        end_index = 2 * adjacency_index + 1
        start_index = end_index + 1
        end = selected.get(end_index)
        start = selected.get(start_index)
        if end is None or start is None:
            continue
        selected_pair = (end.observation_id, start.observation_id)
        if selected_pair in ledger.source_wide_pairs:
            bases[end_index].add(DirectRoleAuthorityBasis.SEPARATOR_PAIR)
            bases[start_index].add(DirectRoleAuthorityBasis.SEPARATOR_PAIR)

    # A two-region material band may transfer authority from one independently
    # authoritative side to the other side of the same normal adjacency.  The
    # pass is deliberately non-recursive.
    for adjacency_index in range(max(0, fit.template.count - 1)):
        end_index = 2 * adjacency_index + 1
        start_index = end_index + 1
        end = selected.get(end_index)
        start = selected.get(start_index)
        if end is None or start is None:
            continue
        selected_pair = (end.observation_id, start.observation_id)
        if (
            selected_pair not in ledger.partial_height_pairs
            or selected_pair in ledger.source_wide_pairs
            or region_counts[end_index] < SPATIAL_SUPPORT_REGION_COUNT - 1
            or region_counts[start_index] < SPATIAL_SUPPORT_REGION_COUNT - 1
        ):
            continue
        end_unconditional = bool(
            bases[end_index] & _UNCONDITIONAL_DIRECT_ROLE_BASES
        )
        start_unconditional = bool(
            bases[start_index] & _UNCONDITIONAL_DIRECT_ROLE_BASES
        )
        if end_unconditional and not start_unconditional:
            bases[start_index].add(
                DirectRoleAuthorityBasis.PARTIAL_HEIGHT_SEPARATOR_PAIR
            )
        elif start_unconditional and not end_unconditional:
            bases[end_index].add(
                DirectRoleAuthorityBasis.PARTIAL_HEIGHT_SEPARATOR_PAIR
            )

    reversed_pair_conflicts_by_role: dict[int, tuple[ObservationId, ...]] = {}
    for adjacency_index in range(max(0, fit.template.count - 1)):
        end_index = 2 * adjacency_index + 1
        start_index = end_index + 1
        end = selected.get(end_index)
        start = selected.get(start_index)
        if end is None or start is None:
            continue
        conflicts = ledger.reversed_normal_pair_conflicts.get(
            (end.observation_id, start.observation_id),
            (),
        )
        if conflicts:
            reversed_pair_conflicts_by_role[end_index] = conflicts
            reversed_pair_conflicts_by_role[start_index] = conflicts

    blocking_conflicts: dict[int, tuple[ObservationId, ...]] = {}
    for role_index, observation in selected.items():
        selected_role = fit.template.roles[role_index].role
        alternative_conflicts = (
            tuple(
                conflict_id
                for conflict_id, alternative_id
                in ledger.conflicts_by_edge_role.get(
                    (observation.observation_id, selected_role),
                    (),
                )
                if alternative_preserves_independent_width(
                    role_index,
                    alternative_id,
                )
            )
            if (observation.observation_id, selected_role)
            not in ledger.supported_material_roles
            else ()
        )
        blocking_conflicts[role_index] = tuple(
            sorted(
                set(alternative_conflicts)
                | set(reversed_pair_conflicts_by_role.get(role_index, ()))
            )
        )

    facts = tuple(
        DirectRoleAuthorityFact(
            role_index=role_index,
            lane_ordinal=role_index // 2 + 1,
            role=(BoundaryRole.START if role_index % 2 == 0 else BoundaryRole.END),
            observation_id=selected[role_index].observation_id,
            evidence_group_id=selected_evidence_groups[role_index],
            independent_support_region_count=region_counts[role_index],
            bases=tuple(
                item
                for item in DirectRoleAuthorityBasis
                if item in bases[role_index]
            ),
            blocking_material_conflict_ids=blocking_conflicts[role_index],
            state=(
                EvidenceState.CONTRADICTED
                if blocking_conflicts[role_index]
                else EvidenceState.SUPPORTED
                if bases[role_index]
                else EvidenceState.UNAVAILABLE
            ),
            trace_coordinates_px=selected[role_index].trace_coordinates_px,
        )
        for role_index in sorted(selected)
    )
    unsupported = tuple(
        item.role_index
        for item in facts
        if item.state != EvidenceState.SUPPORTED
    )
    contradicted = tuple(
        item.role_index
        for item in facts
        if item.state == EvidenceState.CONTRADICTED
    )
    unavailable = tuple(
        item.role_index
        for item in facts
        if item.state == EvidenceState.UNAVAILABLE
    )
    state = (
        EvidenceState.CONTRADICTED
        if contradicted
        else EvidenceState.UNAVAILABLE
        if unavailable
        else EvidenceState.SUPPORTED
    )
    reason = (
        "selected direct edge has an unresolved same-role separator-material "
        "alternative at role indices: " + ", ".join(map(str, contradicted))
        if contradicted
        else "selected short edge has no source-wide, cross-height-union, "
        "or separator-pair authority at role indices: "
        + ", ".join(map(str, unavailable))
        if unavailable
        else None
    )
    return DirectRoleBindingAuthority(
        state=state,
        facts=facts,
        unsupported_role_indices=unsupported,
        reason=reason,
    )


def assess_direct_role_binding_authorities(
    fits: tuple[SequenceFit, ...],
    observations: tuple[BoundaryEdgeObservation, ...],
    separator_bands: tuple[SeparatorBandObservation, ...],
    measurement_sets: tuple[PhotoBoundaryMeasurementSet, ...],
    *,
    authorized_source_frame_width_px: FiniteInterval | None = None,
) -> tuple[DirectRoleBindingAuthority, ...]:
    """Assess bounded phase candidates against one pre-indexed evidence ledger."""

    if any(not isinstance(fit, SequenceFit) for fit in fits):
        raise TypeError("direct-role authority requires sequence fits")
    if not fits:
        return ()
    template = fits[0].template
    if any(fit.template != template for fit in fits[1:]):
        raise ValueError("direct-role candidate batch requires one fixed template")
    ledger = _direct_role_authority_ledger(
        fits[0], observations, separator_bands, measurement_sets
    )
    return tuple(
        _assess_direct_role_binding_authority(
            fit,
            ledger,
            authorized_source_frame_width_px=(
                authorized_source_frame_width_px
            ),
        )
        for fit in fits
    )


def assess_direct_role_binding_authority(
    fit: SequenceFit,
    observations: tuple[BoundaryEdgeObservation, ...],
    separator_bands: tuple[SeparatorBandObservation, ...],
    measurement_sets: tuple[PhotoBoundaryMeasurementSet, ...],
    *,
    authorized_source_frame_width_px: FiniteInterval | None = None,
) -> DirectRoleBindingAuthority:
    """Authorize a short line only through a source W that excludes it."""

    if not isinstance(fit, SequenceFit):
        raise TypeError("direct-role authority requires a sequence fit")
    return assess_direct_role_binding_authorities(
        (fit,),
        observations,
        separator_bands,
        measurement_sets,
        authorized_source_frame_width_px=authorized_source_frame_width_px,
    )[0]


__all__ = [
    "DirectRoleAuthorityBasis",
    "DirectRoleAuthorityFact",
    "DirectRoleBindingAuthority",
    "assess_direct_role_binding_authorities",
    "assess_direct_role_binding_authority",
    "intrinsic_direct_role_authority_bases",
]
