"""Classify selected adjacency material facts without choosing topology.

The registered measurement and the fixed-template placement already exist
before this module runs.  This owner maps those facts once per adjacency and
answers only whether the ordinary positive-separator interpretation remains
supported, contradicted, or unavailable.  Contact and overlap selection are
deliberately outside this stage.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ...domain import EvidenceState, FiniteInterval, ObservationId
from .model import BoundaryEvidenceState
from .observation_types import BoundaryEdgeObservation, SeparatorBandObservation
from .physical_identity import physical_fact_id
from .template_adjacency_coverage import (
    AdjacencyCoverageState,
    AdjacencyObservationCoverage,
)
from .template_model import SequenceFit
from .template_model import ContactRelation


_NUMERIC_EPSILON_PX = 1.0e-7


class AdjacencyContinuityKind(str, Enum):
    """Observed material state relevant to an ordinary adjacency."""

    SEPARATOR_MATERIAL = "separator_material"
    CONTACT = "contact"
    NO_COUNTEREVIDENCE_OBSERVED = "no_counterevidence_observed"
    NORMAL_SEPARATOR_COUNTEREVIDENCE = "normal_separator_counterevidence"
    SEPARATOR_MATERIAL_UNRESOLVED = "separator_material_unresolved"
    UNRESOLVED = "unresolved"
    COVERAGE_INCOMPLETE = "coverage_incomplete"


class AdjacencyContinuityBasis(str, Enum):
    """Physical fact behind one continuity state."""

    POSITIVE_SEPARATOR_BAND = "positive_separator_band"
    SHARED_PHYSICAL_EDGE = "shared_physical_edge"
    COMPLETE_REGISTERED_CORRIDOR = "complete_registered_corridor"
    REVERSED_DIRECT_EDGES = "reversed_direct_edges"


class AdjacencyContinuityFailureKind(str, Enum):
    """Why an ordinary material interpretation could not be resolved."""

    MULTIPLE_SEPARATOR_BANDS = "multiple_separator_bands"
    SEPARATOR_MATERIAL_UNRESOLVED = "separator_material_unresolved"
    SEPARATOR_ROLE_CONFLICT = "separator_role_conflict"
    SIGNED_GAP_CROSSES_ZERO = "signed_gap_crosses_zero"
    REGISTERED_COVERAGE_INCOMPLETE = "registered_coverage_incomplete"


@dataclass(frozen=True)
class AdjacencyContinuityObservation:
    """One selected adjacency mapped to already registered material facts."""

    observation_id: str
    relation_ordinal: int
    state: EvidenceState
    kind: AdjacencyContinuityKind
    basis: AdjacencyContinuityBasis | None
    required_interval_px: FiniteInterval
    covering_query_ids: tuple[str, ...]
    end_observation_id: ObservationId | None
    next_start_observation_id: ObservationId | None
    separator_band_observation_ids: tuple[ObservationId, ...]
    contact_observation_id: ObservationId | None
    signed_gap_interval_px: FiniteInterval | None
    failure_kind: AdjacencyContinuityFailureKind | None
    reason: str | None

    def __post_init__(self) -> None:
        supported = self.kind in {
            AdjacencyContinuityKind.SEPARATOR_MATERIAL,
            AdjacencyContinuityKind.CONTACT,
            AdjacencyContinuityKind.NO_COUNTEREVIDENCE_OBSERVED,
        }
        contradicted = (
            self.kind
            == AdjacencyContinuityKind.NORMAL_SEPARATOR_COUNTEREVIDENCE
        )
        failed = self.kind in {
            AdjacencyContinuityKind.SEPARATOR_MATERIAL_UNRESOLVED,
            AdjacencyContinuityKind.UNRESOLVED,
            AdjacencyContinuityKind.COVERAGE_INCOMPLETE,
        }
        direct_pair = (
            self.end_observation_id is not None
            and self.next_start_observation_id is not None
        )
        if (
            not self.observation_id
            or self.relation_ordinal <= 0
            or not isinstance(self.state, EvidenceState)
            or not isinstance(self.kind, AdjacencyContinuityKind)
            or not isinstance(self.required_interval_px, FiniteInterval)
            or tuple(sorted(set(self.covering_query_ids)))
            != self.covering_query_ids
            or tuple(sorted(set(self.separator_band_observation_ids)))
            != self.separator_band_observation_ids
            or supported != (self.state == EvidenceState.SUPPORTED)
            or contradicted != (self.state == EvidenceState.CONTRADICTED)
            or failed != (self.state == EvidenceState.UNAVAILABLE)
            or failed
            != (
                isinstance(
                    self.failure_kind,
                    AdjacencyContinuityFailureKind,
                )
                and bool(self.reason)
            )
            or (not failed)
            != (self.failure_kind is None and self.reason is None)
        ):
            raise ValueError("adjacency continuity observation is invalid")
        allowed_failures = {
            AdjacencyContinuityKind.SEPARATOR_MATERIAL_UNRESOLVED: {
                AdjacencyContinuityFailureKind.SEPARATOR_MATERIAL_UNRESOLVED,
            },
            AdjacencyContinuityKind.UNRESOLVED: {
                AdjacencyContinuityFailureKind.MULTIPLE_SEPARATOR_BANDS,
                AdjacencyContinuityFailureKind.SEPARATOR_ROLE_CONFLICT,
                AdjacencyContinuityFailureKind.SIGNED_GAP_CROSSES_ZERO,
            },
            AdjacencyContinuityKind.COVERAGE_INCOMPLETE: {
                AdjacencyContinuityFailureKind.REGISTERED_COVERAGE_INCOMPLETE,
            },
        }
        if failed and self.failure_kind not in allowed_failures[self.kind]:
            raise ValueError("adjacency continuity failure kind is invalid")
        if self.kind == AdjacencyContinuityKind.SEPARATOR_MATERIAL:
            if (
                self.basis
                != AdjacencyContinuityBasis.POSITIVE_SEPARATOR_BAND
                or not direct_pair
                or len(self.separator_band_observation_ids) != 1
                or self.signed_gap_interval_px is None
                or self.signed_gap_interval_px.minimum
                <= _NUMERIC_EPSILON_PX
            ):
                raise ValueError("separator continuity fact is incomplete")
        elif self.kind == AdjacencyContinuityKind.CONTACT:
            if (
                self.basis != AdjacencyContinuityBasis.SHARED_PHYSICAL_EDGE
                or not direct_pair
                or self.end_observation_id
                != self.next_start_observation_id
                or self.separator_band_observation_ids
                or self.signed_gap_interval_px != FiniteInterval.exact(0.0)
                or not isinstance(self.contact_observation_id, ObservationId)
            ):
                raise ValueError("contact continuity fact is incomplete")
        elif self.kind == (
            AdjacencyContinuityKind.NO_COUNTEREVIDENCE_OBSERVED
        ):
            if (
                self.basis
                != AdjacencyContinuityBasis.COMPLETE_REGISTERED_CORRIDOR
                or self.separator_band_observation_ids
            ):
                raise ValueError("neutral continuity fact is invalid")
        elif contradicted:
            if (
                self.basis
                != AdjacencyContinuityBasis.REVERSED_DIRECT_EDGES
                or not direct_pair
                or self.separator_band_observation_ids
                or self.signed_gap_interval_px is None
                or self.signed_gap_interval_px.maximum
                > _NUMERIC_EPSILON_PX
            ):
                raise ValueError("normal-separator counterevidence is invalid")
        elif self.basis is not None:
            raise ValueError("unresolved continuity cannot claim a basis")
        if (
            self.kind != AdjacencyContinuityKind.CONTACT
            and self.contact_observation_id is not None
        ):
            raise ValueError("non-contact continuity retained contact evidence")
        if (
            self.kind
            == AdjacencyContinuityKind.SEPARATOR_MATERIAL_UNRESOLVED
            and (
                not direct_pair
                or not self.separator_band_observation_ids
                or self.signed_gap_interval_px is None
                or self.signed_gap_interval_px.minimum
                <= _NUMERIC_EPSILON_PX
            )
        ):
            raise ValueError("unresolved material provenance is invalid")
        if self.failure_kind == (
            AdjacencyContinuityFailureKind.MULTIPLE_SEPARATOR_BANDS
        ) and (not direct_pair or len(self.separator_band_observation_ids) < 2):
            raise ValueError("multiple separator provenance is invalid")
        if self.failure_kind == (
            AdjacencyContinuityFailureKind.SEPARATOR_ROLE_CONFLICT
        ) and (
            not direct_pair
            or len(self.separator_band_observation_ids) != 1
            or self.signed_gap_interval_px is None
        ):
            raise ValueError("separator role-conflict provenance is invalid")
        if self.failure_kind == (
            AdjacencyContinuityFailureKind.SIGNED_GAP_CROSSES_ZERO
        ) and (
            not direct_pair
            or self.separator_band_observation_ids
            or self.signed_gap_interval_px is None
            or self.signed_gap_interval_px.minimum > _NUMERIC_EPSILON_PX
            or self.signed_gap_interval_px.maximum <= _NUMERIC_EPSILON_PX
        ):
            raise ValueError("cross-zero gap provenance is invalid")
        if self.failure_kind == (
            AdjacencyContinuityFailureKind.REGISTERED_COVERAGE_INCOMPLETE
        ) and self.separator_band_observation_ids:
            raise ValueError("incomplete coverage cannot retain a material band")

    @property
    def directly_observed_separator(self) -> bool:
        return self.kind == AdjacencyContinuityKind.SEPARATOR_MATERIAL


def _oriented_position_interval(
    interval: FiniteInterval,
    direction: int,
) -> FiniteInterval:
    if direction > 0:
        return interval
    return FiniteInterval(-interval.maximum, -interval.minimum)


def _signed_gap_interval(
    end: BoundaryEdgeObservation,
    next_start: BoundaryEdgeObservation,
    direction: int,
) -> FiniteInterval:
    oriented_end = _oriented_position_interval(
        end.full_position_interval_px,
        direction,
    )
    oriented_start = _oriented_position_interval(
        next_start.full_position_interval_px,
        direction,
    )
    return FiniteInterval(
        oriented_start.minimum - oriented_end.maximum,
        oriented_start.maximum - oriented_end.minimum,
    )


def _bands_by_pair(
    bands: tuple[SeparatorBandObservation, ...],
    edge_ids: set[ObservationId],
) -> dict[frozenset[ObservationId], tuple[SeparatorBandObservation, ...]]:
    values: dict[frozenset[ObservationId], list[SeparatorBandObservation]] = {}
    for band in bands:
        pair = frozenset(
            (band.left_edge_observation_id, band.right_edge_observation_id)
        )
        if len(pair) != 2:
            raise ValueError("separator band must bind two distinct edges")
        if not pair.issubset(edge_ids):
            raise ValueError("separator band references an unknown edge")
        values.setdefault(pair, []).append(band)
    return {
        key: tuple(
            sorted(items, key=lambda item: str(item.observation_id))
        )
        for key, items in values.items()
    }


def observe_adjacency_continuity(
    fit: SequenceFit,
    sequence_edges: tuple[BoundaryEdgeObservation, ...],
    separator_bands: tuple[SeparatorBandObservation, ...],
    coverage: tuple[AdjacencyObservationCoverage, ...],
) -> tuple[AdjacencyContinuityObservation, ...]:
    """Map one selected fit to ordinary-adjacency facts in O(count)."""

    if not isinstance(fit, SequenceFit):
        raise TypeError("adjacency continuity requires a sequence fit")
    if tuple(item.relation_ordinal for item in coverage) != tuple(
        range(1, fit.template.count)
    ):
        raise ValueError("adjacency continuity coverage is incomplete")
    by_id = {item.observation_id: item for item in sequence_edges}
    if len(by_id) != len(sequence_edges):
        raise ValueError("sequence edge identities must be unique")
    bands_by_pair = _bands_by_pair(
        separator_bands,
        set(by_id),
    )
    values: list[AdjacencyContinuityObservation] = []
    relations_by_ordinal = {
        item.relation_ordinal: item for item in fit.adjacency_relations
    }
    for item in coverage:
        adjacency_index = item.relation_ordinal - 1
        end_id = fit.binding_observation_ids[2 * adjacency_index + 1]
        next_start_id = fit.binding_observation_ids[2 * adjacency_index + 2]
        direct_pair = end_id is not None and next_start_id is not None
        end = None if end_id is None else by_id.get(end_id)
        next_start = None if next_start_id is None else by_id.get(next_start_id)
        if direct_pair and (end is None or next_start is None):
            raise ValueError("bound adjacency observation is not registered")
        direct_signed_gap = (
            None
            if end is None or next_start is None
            else _signed_gap_interval(
                end,
                next_start,
                fit.template.direction,
            )
        )
        exact_bands = (
            ()
            if not direct_pair
            else bands_by_pair.get(frozenset((end_id, next_start_id)), ())
        )
        exact_band_ids = tuple(
            band.observation_id for band in exact_bands
        )
        supported_bands = tuple(
            band
            for band in exact_bands
            if band.evidence_state == BoundaryEvidenceState.SUPPORT
        )
        material_conflicts = tuple(
            band
            for band in exact_bands
            if band.evidence_state == BoundaryEvidenceState.CONTRADICTION
        )
        identity_parts = (
            fit.template.template_id,
            fit.phase_lattice_fit.integer_slot_offset,
            item.relation_ordinal,
            end_id,
            next_start_id,
            exact_band_ids,
            item.state.value,
            item.covering_query_ids,
        )
        relation = relations_by_ordinal.get(item.relation_ordinal)
        contact = relation if isinstance(relation, ContactRelation) else None

        def observation(
            *,
            state: EvidenceState,
            kind: AdjacencyContinuityKind,
            basis: AdjacencyContinuityBasis | None = None,
            separator_band_observation_ids: tuple[ObservationId, ...] = (),
            contact_observation_id: ObservationId | None = None,
            signed_gap_interval_px: FiniteInterval | None = None,
            failure_kind: AdjacencyContinuityFailureKind | None = None,
            reason: str | None = None,
        ) -> AdjacencyContinuityObservation:
            return AdjacencyContinuityObservation(
                observation_id=physical_fact_id(
                    "adjacency-continuity",
                    *identity_parts,
                    kind.value,
                    None if basis is None else basis.value,
                    None
                    if failure_kind is None
                    else failure_kind.value,
                ),
                relation_ordinal=item.relation_ordinal,
                state=state,
                kind=kind,
                basis=basis,
                required_interval_px=item.required_interval_px,
                covering_query_ids=item.covering_query_ids,
                end_observation_id=end_id,
                next_start_observation_id=next_start_id,
                separator_band_observation_ids=separator_band_observation_ids,
                contact_observation_id=contact_observation_id,
                signed_gap_interval_px=signed_gap_interval_px,
                failure_kind=failure_kind,
                reason=reason,
            )

        if contact is not None:
            if (
                end_id != contact.shared_edge_observation_id
                or next_start_id != contact.shared_edge_observation_id
            ):
                raise ValueError("selected contact lost its shared edge binding")
            if item.state != AdjacencyCoverageState.COMPLETE:
                values.append(
                    observation(
                        state=EvidenceState.UNAVAILABLE,
                        kind=AdjacencyContinuityKind.COVERAGE_INCOMPLETE,
                        failure_kind=(
                            AdjacencyContinuityFailureKind
                            .REGISTERED_COVERAGE_INCOMPLETE
                        ),
                        reason=(
                            "registered queries do not cover the complete "
                            "contact corridor"
                        ),
                    )
                )
                continue
            if exact_bands:
                values.append(
                    observation(
                        state=EvidenceState.UNAVAILABLE,
                        kind=AdjacencyContinuityKind.UNRESOLVED,
                        failure_kind=(
                            AdjacencyContinuityFailureKind
                            .SEPARATOR_ROLE_CONFLICT
                        ),
                        reason=(
                            "positive separator material competes with the "
                            "shared-edge contact interpretation"
                        ),
                        separator_band_observation_ids=exact_band_ids,
                        signed_gap_interval_px=direct_signed_gap,
                    )
                )
                continue
            values.append(
                observation(
                    state=EvidenceState.SUPPORTED,
                    kind=AdjacencyContinuityKind.CONTACT,
                    basis=AdjacencyContinuityBasis.SHARED_PHYSICAL_EDGE,
                    contact_observation_id=contact.contact_observation_id,
                    signed_gap_interval_px=FiniteInterval.exact(0.0),
                )
            )
            continue

        if len(supported_bands) > 1 or (
            supported_bands and material_conflicts
        ):
            values.append(
                observation(
                    state=EvidenceState.UNAVAILABLE,
                    kind=AdjacencyContinuityKind.UNRESOLVED,
                    failure_kind=(
                        AdjacencyContinuityFailureKind
                        .MULTIPLE_SEPARATOR_BANDS
                    ),
                    reason=(
                        "multiple or conflicting separator bands bind one "
                        "adjacency"
                    ),
                    separator_band_observation_ids=exact_band_ids,
                    signed_gap_interval_px=direct_signed_gap,
                )
            )
            continue
        if not supported_bands and direct_signed_gap is not None:
            if direct_signed_gap.maximum <= _NUMERIC_EPSILON_PX:
                values.append(
                    observation(
                        state=EvidenceState.CONTRADICTED,
                        kind=(
                            AdjacencyContinuityKind
                            .NORMAL_SEPARATOR_COUNTEREVIDENCE
                        ),
                        basis=(
                            AdjacencyContinuityBasis.REVERSED_DIRECT_EDGES
                        ),
                        signed_gap_interval_px=direct_signed_gap,
                    )
                )
                continue
            if direct_signed_gap.minimum <= _NUMERIC_EPSILON_PX:
                values.append(
                    observation(
                        state=EvidenceState.UNAVAILABLE,
                        kind=AdjacencyContinuityKind.UNRESOLVED,
                        signed_gap_interval_px=direct_signed_gap,
                        failure_kind=(
                            AdjacencyContinuityFailureKind
                            .SIGNED_GAP_CROSSES_ZERO
                        ),
                        reason=(
                            "direct adjacency gap spans both ordinary and "
                            "non-ordinary topology"
                        ),
                    )
                )
                continue
        if material_conflicts:
            values.append(
                observation(
                    state=EvidenceState.UNAVAILABLE,
                    kind=(
                        AdjacencyContinuityKind
                        .SEPARATOR_MATERIAL_UNRESOLVED
                    ),
                    failure_kind=(
                        AdjacencyContinuityFailureKind
                        .SEPARATOR_MATERIAL_UNRESOLVED
                    ),
                    reason=(
                        "registered separator material does not resolve "
                        "consistently across the measured height regions"
                    ),
                    separator_band_observation_ids=tuple(
                        band.observation_id for band in material_conflicts
                    ),
                    signed_gap_interval_px=direct_signed_gap,
                )
            )
            continue
        if supported_bands:
            assert end_id is not None and next_start_id is not None
            band = supported_bands[0]
            expected_left_id, expected_right_id = (
                (end_id, next_start_id)
                if fit.template.direction > 0
                else (next_start_id, end_id)
            )
            if (
                band.left_edge_observation_id != expected_left_id
                or band.right_edge_observation_id != expected_right_id
                or band.gap_interval_px.minimum <= _NUMERIC_EPSILON_PX
            ):
                values.append(
                    observation(
                        state=EvidenceState.UNAVAILABLE,
                        kind=AdjacencyContinuityKind.UNRESOLVED,
                        failure_kind=(
                            AdjacencyContinuityFailureKind
                            .SEPARATOR_ROLE_CONFLICT
                        ),
                        reason=(
                            "separator material contradicts bound "
                            "END-then-START roles"
                        ),
                        separator_band_observation_ids=(
                            band.observation_id,
                        ),
                        signed_gap_interval_px=direct_signed_gap,
                    )
                )
                continue
            values.append(
                observation(
                    state=EvidenceState.SUPPORTED,
                    kind=AdjacencyContinuityKind.SEPARATOR_MATERIAL,
                    basis=(
                        AdjacencyContinuityBasis.POSITIVE_SEPARATOR_BAND
                    ),
                    separator_band_observation_ids=(band.observation_id,),
                    signed_gap_interval_px=band.gap_interval_px,
                )
            )
            continue
        if item.state != AdjacencyCoverageState.COMPLETE:
            values.append(
                observation(
                    state=EvidenceState.UNAVAILABLE,
                    kind=AdjacencyContinuityKind.COVERAGE_INCOMPLETE,
                    signed_gap_interval_px=direct_signed_gap,
                    failure_kind=(
                        AdjacencyContinuityFailureKind
                        .REGISTERED_COVERAGE_INCOMPLETE
                    ),
                    reason=(
                        "registered queries do not cover the complete "
                        "adjacency corridor"
                    ),
                )
            )
            continue
        values.append(
            observation(
                state=EvidenceState.SUPPORTED,
                kind=(
                    AdjacencyContinuityKind.NO_COUNTEREVIDENCE_OBSERVED
                ),
                basis=(
                    AdjacencyContinuityBasis.COMPLETE_REGISTERED_CORRIDOR
                ),
                signed_gap_interval_px=direct_signed_gap,
            )
        )
    return tuple(values)


__all__ = [
    "AdjacencyContinuityBasis",
    "AdjacencyContinuityFailureKind",
    "AdjacencyContinuityKind",
    "AdjacencyContinuityObservation",
    "observe_adjacency_continuity",
]
