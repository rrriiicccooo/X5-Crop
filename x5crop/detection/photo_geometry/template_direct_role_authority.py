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
from .observation_types import BoundaryEdgeObservation, SeparatorBandObservation
from .separator_material import (
    normal_separator_material_bands,
    normal_separator_material_conflicts,
)
from .template_model import SequenceFit


class DirectRoleAuthorityBasis(str, Enum):
    SOURCE_WIDE_EDGE = "source_wide_edge"
    SEPARATOR_PAIR = "separator_pair"
    FRAME_WIDTH_PAIR = "frame_width_pair"


@dataclass(frozen=True)
class DirectRoleAuthorityFact:
    """The independent physical basis for one selected direct role."""

    role_index: int
    lane_ordinal: int
    role: BoundaryRole
    observation_id: ObservationId
    independent_support_region_count: int
    bases: tuple[DirectRoleAuthorityBasis, ...]
    blocking_material_conflict_ids: tuple[ObservationId, ...]
    state: EvidenceState

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
            or not 1
            <= self.independent_support_region_count
            <= SPATIAL_SUPPORT_REGION_COUNT
            or tuple(dict.fromkeys(self.bases)) != self.bases
            or any(not isinstance(item, DirectRoleAuthorityBasis) for item in self.bases)
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
        ):
            raise ValueError("direct-role authority fact is invalid")


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


def _width_interval(
    start: BoundaryEdgeObservation,
    end: BoundaryEdgeObservation,
    *,
    direction: int,
) -> FiniteInterval:
    values = tuple(
        direction * (end_value - start_value)
        for start_value in (
            start.fit_position_interval_px.minimum,
            start.fit_position_interval_px.maximum,
        )
        for end_value in (
            end.fit_position_interval_px.minimum,
            end.fit_position_interval_px.maximum,
        )
    )
    return FiniteInterval(min(values), max(values))


def _overlaps(left: FiniteInterval, right: FiniteInterval) -> bool:
    return max(left.minimum, right.minimum) <= min(left.maximum, right.maximum)


def assess_direct_role_binding_authority(
    fit: SequenceFit,
    observations: tuple[BoundaryEdgeObservation, ...],
    separator_bands: tuple[SeparatorBandObservation, ...],
    measurement_sets: tuple[PhotoBoundaryMeasurementSet, ...],
) -> DirectRoleBindingAuthority:
    """Authorize a short line only through another independent physical fact.

    A source-wide edge owns its coordinate directly.  A source-wide separator
    atomically owns its END/START pair.  Two independent, role-opposite edges
    whose measured separation intersects fixed ``W`` own one complete Frame
    pair.  A short line without any of those relations remains observation,
    not final crop-coordinate authority.
    """

    if not isinstance(fit, SequenceFit):
        raise TypeError("direct-role authority requires a sequence fit")
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

    selected: dict[int, BoundaryEdgeObservation] = {}
    selected_support_ids: dict[int, ObservationId] = {}
    for role, binding in zip(fit.template.roles, fit.role_bindings, strict=True):
        if binding is None:
            continue
        observation = by_id.get(binding.observation_id)
        if observation is None:
            raise ValueError("selected direct role is absent from the observation ledger")
        selected[role.role_index] = observation
        selected_support_ids[role.role_index] = binding.independent_support_id

    bases: dict[int, set[DirectRoleAuthorityBasis]] = {
        role_index: set() for role_index in selected
    }
    region_counts = {
        role_index: independent_spatial_support_count(
            trace_lattice,
            observation.trace_coordinates_px,
        )
        for role_index, observation in selected.items()
    }
    for role_index, count in region_counts.items():
        if count == SPATIAL_SUPPORT_REGION_COUNT:
            bases[role_index].add(DirectRoleAuthorityBasis.SOURCE_WIDE_EDGE)

    role_authority_bands = normal_separator_material_bands(
        separator_bands,
        maximum_material_gap_px=fit.template.gap_prior_px.maximum,
    )
    source_wide_pairs = {
        frozenset(
            (band.left_edge_observation_id, band.right_edge_observation_id)
        )
        for band in role_authority_bands
        if band.material_support_region_count == SPATIAL_SUPPORT_REGION_COUNT
    }
    supported_material_roles = {
        (band.left_edge_observation_id, BoundaryRole.END)
        for band in role_authority_bands
        if band.material_support_region_count == SPATIAL_SUPPORT_REGION_COUNT
    } | {
        (band.right_edge_observation_id, BoundaryRole.START)
        for band in role_authority_bands
        if band.material_support_region_count == SPATIAL_SUPPORT_REGION_COUNT
    }
    for adjacency_index in range(max(0, fit.template.count - 1)):
        end_index = 2 * adjacency_index + 1
        start_index = end_index + 1
        end = selected.get(end_index)
        start = selected.get(start_index)
        if end is None or start is None:
            continue
        selected_pair = frozenset(
            (end.observation_id, start.observation_id)
        )
        if selected_pair in source_wide_pairs:
            bases[end_index].add(DirectRoleAuthorityBasis.SEPARATOR_PAIR)
            bases[start_index].add(DirectRoleAuthorityBasis.SEPARATOR_PAIR)

    width_authority = FiniteInterval(
        fit.template.frame_width_px.minimum,
        fit.template.frame_width_px.maximum,
    )
    for slot_index in range(fit.template.count):
        start_index = 2 * slot_index
        end_index = start_index + 1
        start = selected.get(start_index)
        end = selected.get(end_index)
        if (
            start is None
            or end is None
            or selected_support_ids[start_index]
            == selected_support_ids[end_index]
            or not _overlaps(
                _width_interval(start, end, direction=fit.template.direction),
                width_authority,
            )
        ):
            continue
        bases[start_index].add(DirectRoleAuthorityBasis.FRAME_WIDTH_PAIR)
        bases[end_index].add(DirectRoleAuthorityBasis.FRAME_WIDTH_PAIR)

    conflicts_by_edge_role: dict[
        tuple[ObservationId, BoundaryRole],
        set[ObservationId],
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
                conflicts_by_edge_role.setdefault((edge_id, role), set()).add(
                    conflict.observation_id
                )

    blocking_conflicts = {
        role_index: tuple(
            sorted(
                conflicts_by_edge_role.get(
                    (
                        observation.observation_id,
                        fit.template.roles[role_index].role,
                    ),
                    set(),
                )
            )
        )
        if (observation.observation_id, fit.template.roles[role_index].role)
        not in supported_material_roles
        else ()
        for role_index, observation in selected.items()
    }

    facts = tuple(
        DirectRoleAuthorityFact(
            role_index=role_index,
            lane_ordinal=role_index // 2 + 1,
            role=(BoundaryRole.START if role_index % 2 == 0 else BoundaryRole.END),
            observation_id=selected[role_index].observation_id,
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
        else "selected short edge has no source-wide, separator-pair, or "
        "fixed-W authority at role indices: "
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


__all__ = [
    "DirectRoleAuthorityBasis",
    "DirectRoleAuthorityFact",
    "DirectRoleBindingAuthority",
    "assess_direct_role_binding_authority",
]
