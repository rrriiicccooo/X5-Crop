"""Observed local advance, normal gap, and long-axis fill authority."""

from __future__ import annotations

from ...domain import EvidenceState, FiniteInterval, ObservationId
from .chains import BoundRoleEvidence
from .chain_proposals import (
    FrameChainProposals,
)
from .sequence_models import (
    LocalAdvanceKind,
    LocalAdvanceRelation,
)
from .interval_math import add, intersect, multiply, subtract
from .model import BoundaryRole
from .observation_types import (
    SeparatorBandRoleProposal,
    SequenceRoleProposal,
)
from .sequence_evidence import role_evidence_intervals
from .lane_gap_model import LaneGapModel
from .source_geometry import SourceScanGeometry

def local_advance_delta_from_observed_gap(
    observed_gap_px: FiniteInterval,
    geometry: SourceScanGeometry,
    gap_model: LaneGapModel,
) -> FiniteInterval | None:
    """Constrain one observed gap by physical ordering, not a fixed gap."""

    width = geometry.width_state.extent_projection_px()
    allowed_gap_px = FiniteInterval(-width.maximum, observed_gap_px.maximum)
    constrained_gap = intersect(observed_gap_px, allowed_gap_px)
    if constrained_gap is None:
        return None
    if (
        gap_model.state != EvidenceState.SUPPORTED
        or gap_model.gap_interval_px is None
    ):
        # Algebraic zero is not a contact claim.  It lets a fully direct chain
        # encode the actual signed gap as its local relation; missing relations
        # are rejected below while G_source is unresolved.
        return constrained_gap
    nominal_gap_px = gap_model.gap_interval_px
    if intersect(constrained_gap, nominal_gap_px) is not None:
        return FiniteInterval.exact(0.0)
    return subtract(constrained_gap, nominal_gap_px)


def gap_model_from_bound_roles(
    proposal: FrameChainProposals,
    geometry: SourceScanGeometry,
    lane_id: str,
    observations: tuple[BoundRoleEvidence, ...],
    role_proposals: tuple[SequenceRoleProposal, ...],
) -> LaneGapModel:
    separator_run_ids = {
        item.run_id
        for item in role_proposals
        if item.separator_band_observation_id is not None
    }
    # A separator band is one direct observation.  Its two material sides may
    # bind END/START roles, but reusing those same sides as pitch-minus-W
    # evidence would count one band twice and can manufacture a false conflict
    # between a direct gap and its correlated derivation.
    independent_edge_observations = tuple(
        item for item in observations if item.run_id not in separator_run_ids
    )
    by_role = role_evidence_intervals(independent_edge_observations)
    selected_band_ids = {
        str(item.separator_band_observation_id)
        for item in role_proposals
        if item.separator_band_observation_id is not None
    }
    direct_separator_gaps = {
        str(item.band_observation_id): (
            item.gap_interval_px,
            item.band_observation_id,
        )
        for item in proposal.separator_band_proposals
        if str(item.band_observation_id) in selected_band_ids
    }
    return LaneGapModel.from_ordinal_edges(
        geometry.width_state,
        lane_id=lane_id,
        edge_families=tuple(
            tuple(
                (
                    ordinal,
                    by_role[role_index][0],
                    by_role[role_index][2],
                )
                for ordinal in range(1, len(proposal.roles) // 2 + 1)
                for role_index in (
                    (ordinal - 1) * 2
                    + (1 if role == BoundaryRole.END else 0),
                )
                if role_index in by_role
            )
            for role in (BoundaryRole.START, BoundaryRole.END)
        ),
        direct_separator_gaps=tuple(
            direct_separator_gaps[key]
            for key in sorted(direct_separator_gaps)
        ),
    )


def local_advance_relations(
    proposal: FrameChainProposals,
    geometry: SourceScanGeometry,
    gap_model: LaneGapModel,
    observations: tuple[BoundRoleEvidence, ...],
    role_proposals: tuple[SequenceRoleProposal, ...] = (),
) -> tuple[LocalAdvanceRelation, ...]:
    by_role = role_evidence_intervals(observations)
    selected_band_roles: dict[
        tuple[ObservationId, int], set[int]
    ] = {}
    for item in role_proposals:
        if item.separator_band_observation_id is None:
            continue
        relation_ordinal = (
            item.role.lane_ordinal
            if item.role.role == BoundaryRole.END
            else item.role.lane_ordinal - 1
        )
        if relation_ordinal <= 0:
            continue
        selected_band_roles.setdefault(
            (item.separator_band_observation_id, relation_ordinal),
            set(),
        ).add(item.role.role_index)
    selected_band_by_relation: dict[int, SeparatorBandRoleProposal] = {}
    for item in proposal.separator_band_proposals:
        key = (item.band_observation_id, item.relation_ordinal)
        if selected_band_roles.get(key) != {
            item.left_role_proposal.role.role_index,
            item.right_role_proposal.role.role_index,
        }:
            continue
        if item.relation_ordinal in selected_band_by_relation:
            raise ValueError("one adjacency has multiple direct separator bands")
        selected_band_by_relation[item.relation_ordinal] = item
    relations: list[LocalAdvanceRelation] = []
    for ordinal in range(1, len(proposal.roles) // 2):
        end_index = ordinal * 2 - 1
        next_start_index = ordinal * 2
        end = by_role.get(end_index)
        start = by_role.get(next_start_index)
        if end is None or start is None:
            if gap_model.state != EvidenceState.SUPPORTED:
                raise ValueError(
                    "unresolved lane gap cannot infer a missing adjacency"
                )
            relations.append(
                LocalAdvanceRelation(
                    relation_ordinal=ordinal,
                    kind=LocalAdvanceKind.NOMINAL,
                    delta_interval_px=FiniteInterval.exact(0.0),
                    canonical_delta_px=0.0,
                    observation_ids=(),
                )
            )
            continue
        selected_band = selected_band_by_relation.get(ordinal)
        if selected_band is None:
            observed_gap = subtract(start[0], end[0])
            observation_ids = tuple(
                ObservationId(value)
                for value in sorted(
                    {
                        *(str(identity) for identity in end[2]),
                        *(str(identity) for identity in start[2]),
                    }
                )
            )
        else:
            # A complete separator band is the direct physical measurement of
            # this adjacency.  Re-subtracting its independently fitted peak
            # sides would throw away the wider observed material interval and
            # can turn ordinary gap variation into a fictitious local anomaly.
            observed_gap = selected_band.gap_interval_px
            observation_ids = (selected_band.band_observation_id,)
        delta = local_advance_delta_from_observed_gap(
            observed_gap,
            geometry,
            gap_model,
        )
        if delta is None:
            raise ValueError("observed gap exceeds format local advance authority")
        if (
            gap_model.state == EvidenceState.SUPPORTED
            and delta == FiniteInterval.exact(0.0)
        ):
            relations.append(
                LocalAdvanceRelation(
                    relation_ordinal=ordinal,
                    kind=LocalAdvanceKind.NOMINAL,
                    delta_interval_px=FiniteInterval.exact(0.0),
                    canonical_delta_px=0.0,
                    observation_ids=observation_ids,
                )
            )
            continue
        canonical_delta = delta.center
        gap_center = observed_gap.center
        if gap_center < 0.0:
            kind = LocalAdvanceKind.OVERLAP
        elif observed_gap.contains(0.0):
            kind = LocalAdvanceKind.CONTACT
        elif gap_model.state == EvidenceState.UNAVAILABLE:
            # The positive adjacency is directly located and, absent anomaly
            # evidence, consumes the normal default.  One observation does
            # not establish G_source and therefore cannot infer another gap.
            kind = LocalAdvanceKind.OBSERVED_NORMAL
        elif gap_model.state != EvidenceState.SUPPORTED:
            kind = LocalAdvanceKind.OBSERVED_UNCLASSIFIED
        elif canonical_delta > 0.0:
            kind = LocalAdvanceKind.WIDE
        else:
            kind = LocalAdvanceKind.NARROW
        relations.append(
            LocalAdvanceRelation(
                relation_ordinal=ordinal,
                kind=kind,
                delta_interval_px=delta,
                canonical_delta_px=canonical_delta,
                observation_ids=observation_ids,
            )
        )

    # A separator can be unobservable while its local advance is still
    # directly constrained by two surrounding separator anchors.  When those
    # anchors contain exactly one unobserved adjacency, their measured span,
    # the shared W and the supported normal gaps uniquely assign the residual
    # to that adjacency.  With two or more missing adjacencies the same total
    # residual would not identify a location and must remain unresolved.
    if (
        gap_model.state == EvidenceState.SUPPORTED
        and gap_model.gap_interval_px is not None
        and len(selected_band_by_relation) >= 2
    ):
        width = geometry.width_state.extent_projection_px()
        anchored_ordinals = tuple(sorted(selected_band_by_relation))
        for left_anchor, right_anchor in zip(
            anchored_ordinals,
            anchored_ordinals[1:],
        ):
            relation_indices = tuple(
                range(left_anchor + 1, right_anchor)
            )
            missing = tuple(
                index
                for index in relation_indices
                if not relations[index - 1].observation_ids
            )
            if len(missing) != 1:
                continue
            left_role = by_role.get(left_anchor * 2)
            right_role = by_role.get(right_anchor * 2 - 1)
            if left_role is None or right_role is None:
                continue
            observed_span = subtract(right_role[0], left_role[0])
            frame_count = right_anchor - left_anchor
            expected_span = add(
                multiply(width, frame_count),
                multiply(
                    gap_model.gap_interval_px,
                    max(0, frame_count - 1),
                ),
            )
            for relation_index in relation_indices:
                if relation_index == missing[0]:
                    continue
                expected_span = add(
                    expected_span,
                    relations[relation_index - 1].delta_interval_px,
                )
            delta = subtract(observed_span, expected_span)
            if delta.contains(0.0):
                continue
            missing_ordinal = missing[0]
            actual_gap = add(gap_model.gap_interval_px, delta)
            if actual_gap.center < 0.0:
                kind = LocalAdvanceKind.OVERLAP
            elif actual_gap.contains(0.0):
                kind = LocalAdvanceKind.CONTACT
            elif delta.center > 0.0:
                kind = LocalAdvanceKind.WIDE
            else:
                kind = LocalAdvanceKind.NARROW
            relations[missing_ordinal - 1] = LocalAdvanceRelation(
                relation_ordinal=missing_ordinal,
                kind=kind,
                delta_interval_px=delta,
                canonical_delta_px=delta.center,
                observation_ids=tuple(
                    sorted(
                        (
                            selected_band_by_relation[
                                left_anchor
                            ].band_observation_id,
                            selected_band_by_relation[
                                right_anchor
                            ].band_observation_id,
                        ),
                        key=str,
                    )
                ),
            )
    return tuple(relations)


def merge_local_advance_relations(
    declared: tuple[LocalAdvanceRelation, ...],
    observed: tuple[LocalAdvanceRelation, ...],
) -> tuple[LocalAdvanceRelation, ...]:
    def merged_kind(
        left_kind: LocalAdvanceKind,
        right_kind: LocalAdvanceKind,
    ) -> LocalAdvanceKind:
        if left_kind == right_kind:
            return left_kind
        concrete = {
            kind
            for kind in (left_kind, right_kind)
            if kind != LocalAdvanceKind.OBSERVED_UNCLASSIFIED
        }
        if len(concrete) == 1:
            return next(iter(concrete))
        # Conflicting direct classifications do not become a new guessed
        # anomaly.  The signed feasible gap, not the delta centre alone,
        # owns contact/overlap semantics.  Without that common gap here the
        # only honest merged state is observed but unclassified.
        return LocalAdvanceKind.OBSERVED_UNCLASSIFIED

    if len(declared) != len(observed):
        raise ValueError("local advance relation sets disagree")
    merged: list[LocalAdvanceRelation] = []
    for left, right in zip(declared, observed, strict=True):
        if left.relation_ordinal != right.relation_ordinal:
            raise ValueError("local advance relation ordinals disagree")
        left_is_nominal = left.kind == LocalAdvanceKind.NOMINAL
        right_is_nominal = right.kind == LocalAdvanceKind.NOMINAL
        if not left_is_nominal and right_is_nominal and right.observation_ids:
            # Local-advance classification is conditional on the current
            # source W/G state.  Once joint refinement makes the same direct
            # observation compatible with the normal model, the final normal
            # relation supersedes the provisional anomaly proposal.
            merged.append(right)
            continue
        if left_is_nominal:
            merged.append(right)
            continue
        if right_is_nominal:
            merged.append(left)
            continue
        common = intersect(left.delta_interval_px, right.delta_interval_px)
        if common is None:
            raise ValueError("local phase-step evidence conflicts")
        identities = tuple(
            ObservationId(value)
            for value in sorted(
                {
                    *(str(item) for item in left.observation_ids),
                    *(str(item) for item in right.observation_ids),
                }
            )
        )
        merged.append(
            LocalAdvanceRelation(
                relation_ordinal=left.relation_ordinal,
                kind=merged_kind(left.kind, right.kind),
                delta_interval_px=common,
                canonical_delta_px=common.center,
                observation_ids=identities,
            )
        )
    return tuple(merged)
