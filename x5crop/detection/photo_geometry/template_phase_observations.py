"""Bounded sequence phase observations."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, replace
from typing import Sequence

from ...domain import EvidenceState, FiniteInterval, ObservationId
from .model import (
    BoundaryRole,
    MINIMUM_INDEPENDENT_SUPPORT_REGIONS,
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    SPATIAL_SUPPORT_REGION_COUNT,
    independent_spatial_support_count,
)
from .observation_types import (
    BoundaryEdgeMeasurementBasis,
    BoundaryEdgeObservation,
    SeparatorBandObservation,
)
from .trace_support import source_spanning_continuous_trace_support
from .separator_material import normal_separator_material_bands
from .template_contact import ContactEdgeObservation
from .template_overlap import OverlapEdgePairObservation
from .template_model import (
    AdjacencyRelation,
    ContactRelation,
    OverlapRelation,
    SeparatorRelation,
    SeparatorRelationKind,
    SequenceFit,
    SequenceBindingUse,
    SequenceRoleBinding,
    SequenceRoleLineEvidence,
    TemplateRole,
    TemplateSpec,
    adjacency_prefix_positions,
    template_role_refinement_radius_px,
)
from .template_separator_support import (
    SeparatorSupportResolution,
    resolve_separator_support,
)
from . import template_phase_candidate_model as _candidate_model


def _facts(
    observations: Sequence[BoundaryEdgeObservation],
    *,
    separator_support_ids: dict[ObservationId, ObservationId] | None = None,
    registered_trace_positions_px: tuple[float, ...] = (),
) -> tuple[_candidate_model._AnchorFact, ...]:
    separator_support_ids = separator_support_ids or {}
    result: list[_candidate_model._AnchorFact] = []
    for observation in observations:
        if not isinstance(observation, BoundaryEdgeObservation):
            raise TypeError("phase input requires typed boundary observations")
        result.append(
            _candidate_model._AnchorFact(
                observation_id=observation.observation_id,
                evidence_group_id=separator_support_ids.get(
                    observation.observation_id,
                    observation.observation_id,
                ),
                interval_px=observation.fit_position_interval_px,
                full_interval_px=observation.full_position_interval_px,
                direct=(
                    observation.support_fraction >= 0.35
                    or observation.observation_id in separator_support_ids
                )
                and bool(observation.qualified_anchor_roles),
                support_fraction=observation.support_fraction,
                fit_residual_px=observation.fit_residual_px,
                line_evidence=(
                    SequenceRoleLineEvidence(
                        observation_id=observation.observation_id,
                        reference_trace_px=observation.reference_trace_px,
                        fit_position_interval_px=(
                            observation.fit_position_interval_px
                        ),
                        fit_direction_interval_degrees=(
                            observation.fit_direction_interval_degrees
                        ),
                        physical_line_region=observation.physical_line_region,
                    )
                    if observation.fit_direction_interval_degrees is not None
                    else None
                ),
                polarity=observation.polarity,
                qualified_anchor_roles=observation.qualified_anchor_roles,
                source_spanning_direct_line=(
                    observation.measurement_basis
                    == BoundaryEdgeMeasurementBasis.DIRECT_TRACE
                    and independent_spatial_support_count(
                        registered_trace_positions_px,
                        observation.trace_coordinates_px,
                    ) == SPATIAL_SUPPORT_REGION_COUNT
                    and source_spanning_continuous_trace_support(
                        registered_trace_positions_px,
                        observation.trace_coordinates_px,
                        spec=PHOTO_BOUNDARY_MEASUREMENT_SPEC,
                    )
                ),
            )
        )
    if len({item.observation_id for item in result}) != len(result):
        raise ValueError("phase observations must have unique identities")
    return tuple(sorted(result, key=lambda item: (item.coordinate_px, str(item.observation_id))))


def _relations(
    values: Sequence[AdjacencyRelation],
    count: int,
) -> tuple[AdjacencyRelation, ...]:
    result = tuple(values)
    if tuple(item.relation_ordinal for item in result) != tuple(
        range(1, len(result) + 1)
    ) or len(result) > max(0, count - 1):
        raise ValueError(
            "adjacency relations must be ordered fixed adjacencies"
        )
    return result


def _contact_phase_seeds(
    contact_edges: Sequence[ContactEdgeObservation],
    direct: tuple[_candidate_model._AnchorFact, ...],
    roles: tuple[TemplateRole, ...],
    template: TemplateSpec,
    *,
    width: FiniteInterval,
    pitch: FiniteInterval,
    base_relations: tuple[AdjacencyRelation, ...],
) -> tuple[_candidate_model._PhaseSeed, ...]:
    """Project every registered shared edge onto every legal adjacency."""

    by_id = {item.observation_id: item for item in direct}
    existing_contacts = tuple(
        item for item in base_relations if isinstance(item, ContactRelation)
    )
    if len(existing_contacts) > 1:
        raise ValueError("contact stage supports one bounded contact relation")
    observations_by_id = {
        item.observation_id: item for item in contact_edges
    }
    hypotheses: list[tuple[ContactEdgeObservation, int]] = []
    if existing_contacts:
        relation = existing_contacts[0]
        observation = observations_by_id.get(relation.contact_observation_id)
        if observation is None:
            raise ValueError("contact relation left its registered observation")
        hypotheses.append((observation, relation.relation_ordinal))
    else:
        hypotheses.extend(
            (observation, ordinal)
            for observation in contact_edges
            for ordinal in range(1, template.count)
        )

    delta_interval = FiniteInterval(
        width.minimum - pitch.maximum,
        width.maximum - pitch.minimum,
    )
    seeds: set[_candidate_model._PhaseSeed] = set()
    for observation, ordinal in hypotheses:
        anchor = by_id.get(observation.shared_edge_observation_id)
        if anchor is None:
            continue
        relations = list(base_relations)
        while len(relations) < ordinal:
            relation_ordinal = len(relations) + 1
            relations.append(
                SeparatorRelation(
                    relation_ordinal=relation_ordinal,
                    kind=SeparatorRelationKind.NOMINAL,
                    delta_interval_px=FiniteInterval.exact(0.0),
                    canonical_delta_px=0.0,
                )
            )
        current = relations[ordinal - 1]
        if (
            isinstance(current, SeparatorRelation)
            and current.kind != SeparatorRelationKind.NOMINAL
        ):
            continue
        contact = ContactRelation(
            relation_ordinal=ordinal,
            contact_observation_id=observation.observation_id,
            physical_edge_id=observation.physical_edge_id,
            shared_edge_observation_id=(
                observation.shared_edge_observation_id
            ),
            delta_interval_px=delta_interval,
            canonical_delta_px=width.center - pitch.center,
            supporting_observation_ids=(
                observation.shared_edge_observation_id,
            ),
        )
        relations[ordinal - 1] = contact
        realized = tuple(relations)
        prefixes = adjacency_prefix_positions(realized, template.count)
        end_role_index = 2 * ordinal - 1
        start_role_index = 2 * ordinal
        end_role = roles[end_role_index]
        relative = (
            end_role.slot_index * pitch.center
            + prefixes[end_role.slot_index]
            + width.center
        )
        phase = anchor.coordinate_px - template.direction * relative
        seeds.add(
            _candidate_model._PhaseSeed(
                phase_px=round(phase, 9),
                pitch_px=round(pitch.center, 9),
                required_bindings=(
                    (end_role_index, anchor.observation_id),
                    (start_role_index, anchor.observation_id),
                ),
                adjacency_relations=realized,
            )
        )
    return tuple(
        sorted(
            seeds,
            key=lambda item: (
                item.phase_px,
                item.pitch_px,
                tuple(map(repr, item.adjacency_relations)),
            ),
        )
    )


def _overlap_phase_seeds(
    overlap_pairs: Sequence[OverlapEdgePairObservation],
    direct: tuple[_candidate_model._AnchorFact, ...],
    roles: tuple[TemplateRole, ...],
    template: TemplateSpec,
    *,
    width: FiniteInterval,
    pitch: FiniteInterval,
    base_relations: tuple[AdjacencyRelation, ...],
) -> tuple[_candidate_model._PhaseSeed, ...]:
    """Project every registered reversed pair onto each legal adjacency."""

    by_id = {item.observation_id: item for item in direct}
    existing = tuple(
        item for item in base_relations if isinstance(item, OverlapRelation)
    )
    observations_by_id = {
        item.observation_id: item for item in overlap_pairs
    }
    if existing:
        required_bindings: list[tuple[int, ObservationId]] = []
        phase_anchor: tuple[OverlapRelation, _candidate_model._AnchorFact] | None = None
        for relation in existing:
            observation = observations_by_id.get(
                relation.overlap_observation_id
            )
            if (
                observation is None
                or observation.end_edge_observation_id
                != relation.end_edge_observation_id
                or observation.next_start_edge_observation_id
                != relation.next_start_edge_observation_id
                or observation.signed_gap_interval_px
                != relation.signed_gap_interval_px
            ):
                raise ValueError(
                    "overlap relation left its registered observation"
                )
            end = by_id.get(observation.end_edge_observation_id)
            next_start = by_id.get(
                observation.next_start_edge_observation_id
            )
            if end is None or next_start is None:
                return ()
            end_role_index = 2 * relation.relation_ordinal - 1
            start_role_index = 2 * relation.relation_ordinal
            required_bindings.extend(
                (
                    (end_role_index, end.observation_id),
                    (start_role_index, next_start.observation_id),
                )
            )
            if phase_anchor is None:
                phase_anchor = (relation, end)
        assert phase_anchor is not None
        relation, end = phase_anchor
        prefixes = adjacency_prefix_positions(base_relations, template.count)
        end_role = roles[2 * relation.relation_ordinal - 1]
        relative = (
            end_role.slot_index * pitch.center
            + prefixes[end_role.slot_index]
            + width.center
        )
        phase = end.coordinate_px - template.direction * relative
        return (
            _candidate_model._PhaseSeed(
                phase_px=round(phase, 9),
                pitch_px=round(pitch.center, 9),
                required_bindings=tuple(required_bindings),
                adjacency_relations=base_relations,
            ),
        )

    hypotheses = tuple(
        (observation, ordinal)
        for observation in overlap_pairs
        for ordinal in range(1, template.count)
    )

    seeds: set[_candidate_model._PhaseSeed] = set()
    for observation, ordinal in hypotheses:
        end = by_id.get(observation.end_edge_observation_id)
        next_start = by_id.get(observation.next_start_edge_observation_id)
        if end is None or next_start is None:
            continue
        relations = list(base_relations)
        while len(relations) < ordinal:
            relation_ordinal = len(relations) + 1
            relations.append(
                SeparatorRelation(
                    relation_ordinal=relation_ordinal,
                    kind=SeparatorRelationKind.NOMINAL,
                    delta_interval_px=FiniteInterval.exact(0.0),
                    canonical_delta_px=0.0,
                )
            )
        current = relations[ordinal - 1]
        if (
            isinstance(current, SeparatorRelation)
            and current.kind != SeparatorRelationKind.NOMINAL
        ) or isinstance(current, ContactRelation):
            continue
        signed_gap = observation.signed_gap_interval_px
        delta_interval = FiniteInterval(
            signed_gap.minimum + width.minimum - pitch.maximum,
            signed_gap.maximum + width.maximum - pitch.minimum,
        )
        overlap = OverlapRelation(
            relation_ordinal=ordinal,
            overlap_observation_id=observation.observation_id,
            end_edge_observation_id=observation.end_edge_observation_id,
            next_start_edge_observation_id=(
                observation.next_start_edge_observation_id
            ),
            signed_gap_interval_px=signed_gap,
            canonical_signed_gap_px=(
                observation.canonical_signed_gap_px
            ),
            delta_interval_px=delta_interval,
            canonical_delta_px=(
                width.center
                - pitch.center
                + observation.canonical_signed_gap_px
            ),
            supporting_observation_ids=(
                observation.end_edge_observation_id,
                observation.next_start_edge_observation_id,
            ),
        )
        relations[ordinal - 1] = overlap
        realized = tuple(relations)
        prefixes = adjacency_prefix_positions(realized, template.count)
        end_role_index = 2 * ordinal - 1
        start_role_index = 2 * ordinal
        end_role = roles[end_role_index]
        relative = (
            end_role.slot_index * pitch.center
            + prefixes[end_role.slot_index]
            + width.center
        )
        phase = end.coordinate_px - template.direction * relative
        seeds.add(
            _candidate_model._PhaseSeed(
                phase_px=round(phase, 9),
                pitch_px=round(pitch.center, 9),
                required_bindings=(
                    (end_role_index, end.observation_id),
                    (start_role_index, next_start.observation_id),
                ),
                adjacency_relations=realized,
            )
        )
    return tuple(
        sorted(
            seeds,
            key=lambda item: (
                item.phase_px,
                item.pitch_px,
                tuple(map(repr, item.adjacency_relations)),
            ),
        )
    )


def _holder_limits(span: FiniteInterval | None) -> tuple[float, float] | None:
    if span is None:
        return None
    if span.width == 0.0 and span.minimum > 0.0:
        return (0.0, span.minimum)
    if span.width <= 0.0:
        raise ValueError("holder span must have a positive extent")
    return (span.minimum, span.maximum)


def _expected_polarity(role: TemplateRole) -> int:
    return 1 if role.role == BoundaryRole.START else -1


@dataclass(frozen=True)
class PreparedPhaseSeparatorSupport:
    """One pass-local material filter, component resolution and role ledger."""

    observations: tuple[BoundaryEdgeObservation, ...]
    bands: tuple[SeparatorBandObservation, ...]
    resolution: SeparatorSupportResolution


def prepare_phase_separator_support(
    observations: Sequence[BoundaryEdgeObservation],
    separator_bands: Sequence[SeparatorBandObservation],
    *,
    maximum_material_gap_px: float,
) -> PreparedPhaseSeparatorSupport:
    registered = tuple(observations)
    bands = normal_separator_material_bands(
        tuple(separator_bands),
        maximum_material_gap_px=maximum_material_gap_px,
    )
    resolution = resolve_separator_support(registered, bands)
    return PreparedPhaseSeparatorSupport(
        _with_separator_role_authority(
            registered,
            bands,
            maximum_material_gap_px=maximum_material_gap_px,
            support_resolution=resolution,
        ),
        bands,
        resolution,
    )


def _separator_role_authority(
    observations: Sequence[BoundaryEdgeObservation],
    separator_bands: Sequence[SeparatorBandObservation],
    *,
    support_resolution: SeparatorSupportResolution | None = None,
) -> dict[ObservationId, frozenset[BoundaryRole]]:
    """Return role facts proved by directly observed separator material.

    A separator's left edge is the END of one slot and its right edge is the
    START of the next slot.  This relation is stronger than a single edge's
    background hint, but it still carries no ordinal until the template is
    placed. An identity may occur in several bands; the canonical component
    resolver keeps them in one rank group and grants roles only to its unique
    compatible source-wide pair.
    """

    resolution = (
        support_resolution
        if support_resolution is not None
        else resolve_separator_support(tuple(observations), tuple(separator_bands))
    )
    if not isinstance(resolution, SeparatorSupportResolution):
        raise TypeError("separator support resolution must be typed")
    roles: dict[ObservationId, set[BoundaryRole]] = {}
    for component in resolution.components:
        pair = component.role_authority_pair_edge_observation_ids
        if pair is None:
            # Local material cannot create roles by itself. Multiple
            # source-wide pairs or an intrinsic endpoint-role conflict are
            # discrete contradictions rather than votes for either endpoint.
            continue
        left_id, right_id = pair
        roles.setdefault(left_id, set()).add(BoundaryRole.END)
        roles.setdefault(right_id, set()).add(BoundaryRole.START)
    return {identity: frozenset(value) for identity, value in roles.items()}


def _with_separator_role_authority(
    observations: Sequence[BoundaryEdgeObservation],
    separator_bands: Sequence[SeparatorBandObservation],
    *,
    maximum_material_gap_px: float,
    support_resolution: SeparatorSupportResolution | None = None,
) -> tuple[BoundaryEdgeObservation, ...]:
    eligible_bands = (
        normal_separator_material_bands(
            tuple(separator_bands),
            maximum_material_gap_px=maximum_material_gap_px,
        )
        if support_resolution is None
        else tuple(separator_bands)
    )
    resolution = (
        support_resolution
        if support_resolution is not None
        else resolve_separator_support(tuple(observations), eligible_bands)
    )
    authority = _separator_role_authority(
        observations, eligible_bands, support_resolution=resolution
    )
    if not authority and not eligible_bands:
        return tuple(observations)
    by_id = {
        observation.observation_id: observation
        for observation in observations
        if isinstance(observation, BoundaryEdgeObservation)
    }
    bands_by_id = {band.observation_id: band for band in eligible_bands}
    material_intervals: dict[ObservationId, FiniteInterval] = {}
    for component_fact in resolution.components:
        component = tuple(
            bands_by_id[identity]
            for identity in component_fact.band_observation_ids
        )
        # Only one locally observed END -> material -> START relation needs
        # the material center retained as output protection. Source-wide bands
        # already localize their edges directly; alternative pairings remain
        # discrete evidence and must not be hulled into a huge interval.
        if (
            component_fact.role_authority_state != EvidenceState.UNAVAILABLE
            or len(component_fact.pair_edge_observation_ids) != 1
            or any(
                band.gap_interval_px.maximum > maximum_material_gap_px
                for band in component
            )
        ):
            continue
        left_id, right_id = component_fact.pair_edge_observation_ids[0]
        left = by_id.get(left_id)
        right = by_id.get(right_id)
        if left is None or right is None:
            raise ValueError("separator band references an unregistered edge")
        center = FiniteInterval(
            (
                left.fit_position_interval_px.minimum
                + right.fit_position_interval_px.minimum
            )
            / 2.0,
            (
                left.fit_position_interval_px.maximum
                + right.fit_position_interval_px.maximum
            )
            / 2.0,
        )
        for identity in (left_id, right_id):
            observation = by_id[identity]
            # A strict trace majority already localizes that edge directly.
            # The material center is retained only for the weak side of an
            # otherwise unique local band, where it is output protection and
            # never additional phase authority.
            if observation.support_fraction <= 0.5:
                material_intervals[identity] = center
    values: list[BoundaryEdgeObservation] = []
    for observation in observations:
        if isinstance(observation, BoundaryEdgeObservation):
            roles = authority.get(observation.observation_id)
            material = material_intervals.get(observation.observation_id)
            if roles or material is not None:
                full = observation.full_position_interval_px
                if material is not None:
                    full = FiniteInterval(
                        min(full.minimum, material.minimum),
                        max(full.maximum, material.maximum),
                    )
                observation = replace(
                    observation,
                    # A narrow material strip can also lie inside an aperture
                    # edge. Keep its already qualified pixel-role alternative;
                    # both interpretations retain the same observation/group
                    # and must survive the existing placement authority checks.
                    qualified_anchor_roles=(
                        tuple(
                            role
                            for role in (BoundaryRole.START, BoundaryRole.END)
                            if role in roles
                            or role in observation.qualified_anchor_roles
                        )
                        if roles is not None
                        else observation.qualified_anchor_roles
                    ),
                    full_position_interval_px=full,
                )
        values.append(observation)
    return tuple(values)


def _separator_phase_seeds(
    separator_bands: Sequence[SeparatorBandObservation],
    direct: tuple[_candidate_model._AnchorFact, ...],
    roles: tuple[TemplateRole, ...],
    template: TemplateSpec,
    *,
    width: float,
    pitch: float,
    prefixes: tuple[float, ...],
) -> tuple[_candidate_model._PhaseSeed, ...]:
    """Project each direct material band onto every legal adjacency once.

    A separator proves END -> material -> START, but it does not know its
    ordinal. Each legal ordinal is therefore one bounded phase hypothesis.
    The template only projects that direct evidence; it never creates a phase
    from its own grid.
    """

    by_id = {item.observation_id: item for item in direct}
    seeds: set[_candidate_model._PhaseSeed] = set()
    for band in normal_separator_material_bands(
        tuple(separator_bands),
        maximum_material_gap_px=template.gap_prior_px.maximum,
    ):
        left = by_id.get(band.left_edge_observation_id)
        right = by_id.get(band.right_edge_observation_id)
        if (
            left is None
            or right is None
            or (
                (
                    BoundaryRole.END not in left.qualified_anchor_roles
                    or BoundaryRole.START not in right.qualified_anchor_roles
                )
                and band.material_support_region_count
                < MINIMUM_INDEPENDENT_SUPPORT_REGIONS
            )
        ):
            continue
        for adjacency_index in range(template.count - 1):
            end_role = roles[2 * adjacency_index + 1]
            start_role = roles[2 * (adjacency_index + 1)]
            required = (
                (end_role.role_index, left.observation_id),
                (start_role.role_index, right.observation_id),
            )
            for role, anchor in ((end_role, left), (start_role, right)):
                relative = role.slot_index * pitch + prefixes[role.slot_index]
                if role.role == BoundaryRole.END:
                    relative += width
                phase = anchor.coordinate_px - template.direction * relative
                seeds.add(
                    _candidate_model._PhaseSeed(
                        round(phase, 9),
                        round(pitch, 9),
                        required,
                    )
                )
    return tuple(seeds)


def _separator_pair_facts(
    separator_bands: Sequence[SeparatorBandObservation],
    direct: tuple[_candidate_model._AnchorFact, ...],
    *,
    maximum_material_gap_px: float,
) -> tuple[tuple[_candidate_model._AnchorFact, _candidate_model._AnchorFact], ...]:
    """Retain ordered material-pair hypotheses without granting roles."""

    by_id = {item.observation_id: item for item in direct}
    pairs: dict[
        tuple[ObservationId, ObservationId],
        tuple[_candidate_model._AnchorFact, _candidate_model._AnchorFact],
    ] = {}
    for band in normal_separator_material_bands(
        tuple(separator_bands),
        maximum_material_gap_px=maximum_material_gap_px,
    ):
        left = by_id.get(band.left_edge_observation_id)
        right = by_id.get(band.right_edge_observation_id)
        if (
            left is None
            or right is None
            or (
                (
                    BoundaryRole.END not in left.qualified_anchor_roles
                    or BoundaryRole.START not in right.qualified_anchor_roles
                )
                and band.material_support_region_count
                < MINIMUM_INDEPENDENT_SUPPORT_REGIONS
            )
        ):
            continue
        pairs[(left.observation_id, right.observation_id)] = (left, right)
    return tuple(
        pairs[key]
        for key in sorted(pairs, key=lambda value: tuple(map(str, value)))
    )


def prepare_projection_facts(
    observations: Sequence[BoundaryEdgeObservation],
    separator_bands: Sequence[SeparatorBandObservation],
    *,
    maximum_material_gap_px: float,
    registered_trace_positions_px: tuple[float, ...],
):
    """Compile immutable native inputs, without a selected mapping or W."""
    support = prepare_phase_separator_support(observations, separator_bands,
        maximum_material_gap_px=maximum_material_gap_px)
    facts = _facts(support.observations,
        separator_support_ids=support.resolution.edge_component_ids,
        registered_trace_positions_px=registered_trace_positions_px)
    pairs = _separator_pair_facts(support.bands,
        tuple(item for item in facts if item.direct),
        maximum_material_gap_px=maximum_material_gap_px)
    return facts, pairs


def _refine_local_role_bindings(
    fit: SequenceFit,
    observations: Sequence[BoundaryEdgeObservation],
    separator_bands: Sequence[SeparatorBandObservation],
    *,
    intrinsic_coordinate_authority_ids: frozenset[ObservationId] = frozenset(),
    frame_width_authority_px: FiniteInterval | None = None,
    excluded_role_bindings: frozenset[
        tuple[int, ObservationId]
    ] = frozenset(),
) -> _candidate_model._LocalRoleRefinement:
    """Bind uniquely closed local edges after global phase is immutable.

    The global fit remains the sole owner of phase and pitch.  This pass only
    replaces an unbound role near that fixed grid when source pixels provide
    one role-qualified fitted line and physical W or separator material makes
    its local interpretation unique.  It performs no pixel query, ranking, or
    candidate Cartesian product.

    ``excluded_role_bindings`` contains a bounded set of exact role/edge
    assignments already contradicted by ordered separator material in the
    rejected winner.  Those lines remain registered counterevidence, but the
    retained runner cannot attach the same illegal assignment again.
    """

    registered_observations = tuple(observations)
    separator_support = prepare_phase_separator_support(
        registered_observations,
        separator_bands,
        maximum_material_gap_px=fit.template.gap_prior_px.maximum,
    )
    eligible_bands = separator_support.bands
    observations = separator_support.observations
    support_resolution = separator_support.resolution
    support_ids = support_resolution.edge_component_ids
    facts = _facts(
        observations,
        separator_support_ids=support_ids,
    )
    by_id = {item.observation_id: item for item in facts}
    roles = fit.template.roles
    # Local observations must be allowed to contradict the current Grid fit.
    # The calibrated physical template bounds legal Frame widths unless an
    # independently observed source-level W has already been established.
    # The current fitted W is the answer being checked and therefore cannot
    # filter its own counterevidence.
    frame_width = (
        fit.template.frame_width_px
        if frame_width_authority_px is None
        else frame_width_authority_px
    )
    corridor = template_role_refinement_radius_px(
        fit.pitch_fit.canonical_pitch_px
    )
    bindings = list(fit.role_bindings)
    bound_ids = {
        binding.observation_id
        for binding in bindings
        if binding is not None
    }

    # One observation may refine at most one already placed role.  A line that
    # falls in more than one role corridor retains validation-only authority.
    candidate_roles: dict[ObservationId, list[int]] = {}
    registered_candidate_ids_by_role: dict[int, set[ObservationId]] = {
        role.role_index: set() for role in roles
    }
    for role, expected in zip(
        roles,
        fit.model_role_positions_px,
        strict=True,
    ):
        for fact in facts:
            if (
                fit.role_bindings[role.role_index] is None
                and fact.line_evidence is not None
                and role.role in fact.qualified_anchor_roles
                and abs(fact.coordinate_px - expected) <= corridor
            ):
                registered_candidate_ids_by_role[role.role_index].add(
                    fact.observation_id
                )
                if (
                    fact.observation_id not in bound_ids
                    and (role.role_index, fact.observation_id)
                    not in excluded_role_bindings
                ):
                    candidate_roles.setdefault(
                        fact.observation_id,
                        [],
                    ).append(role.role_index)
    candidate_lists: dict[int, list[_candidate_model._AnchorFact]] = {
        role.role_index: [] for role in roles
    }
    for identity, role_indices in candidate_roles.items():
        if len(role_indices) == 1:
            candidate_lists[role_indices[0]].append(by_id[identity])
    candidates_by_role = {}
    intrinsic_candidates_by_role = {}
    for role_index, values in candidate_lists.items():
        candidates_by_role[role_index] = tuple(
            sorted(
                values,
                key=lambda item: (
                    fit.template.direction * item.coordinate_px,
                    str(item.observation_id),
                ),
            )
        )
        intrinsic_candidates_by_role[role_index] = tuple(
            item
            for item in candidates_by_role[role_index]
            if item.observation_id in intrinsic_coordinate_authority_ids
        )

    def binding_for(fact: _candidate_model._AnchorFact) -> SequenceRoleBinding:
        return SequenceRoleBinding(
            use=SequenceBindingUse.LOCAL_REFINEMENT,
            observation_id=fact.observation_id,
            evidence_group_id=fact.evidence_group_id,
            canonical_position_px=fact.coordinate_px,
            fit_position_interval_px=fact.interval_px,
            full_position_interval_px=fact.full_interval_px,
            line_evidence=fact.line_evidence,
        )

    def width_compatible(start_px: float, end_px: float) -> bool:
        width = fit.template.direction * (end_px - start_px)
        return (
            frame_width.minimum - 1.0e-9
            <= width
            <= frame_width.maximum + 1.0e-9
        )

    def fact_fits_bound_frame(role_index: int, fact: _candidate_model._AnchorFact) -> bool:
        other_index = role_index + 1 if role_index % 2 == 0 else role_index - 1
        other = bindings[other_index]
        if other is None:
            return True
        if other.evidence_group_id == fact.evidence_group_id:
            return False
        if role_index % 2 == 0:
            return width_compatible(
                fact.coordinate_px,
                other.canonical_position_px,
            )
        return width_compatible(
            other.canonical_position_px,
            fact.coordinate_px,
        )

    def bind(role_index: int, fact: _candidate_model._AnchorFact) -> None:
        if bindings[role_index] is not None or fact.observation_id in bound_ids:
            raise ValueError("local refinement attempted a duplicate binding")
        bindings[role_index] = binding_for(fact)
        bound_ids.add(fact.observation_id)

    # A source-spanning separator is an atomic END -> material -> START fact.
    # Apply it before individual frame closure so its two sides cannot be
    # mixed with another band interpretation.
    bound_role_by_id = {
        binding.observation_id: role_index
        for role_index, binding in enumerate(bindings)
        if binding is not None
    }
    component_by_band_id = {
        identity: component
        for component in support_resolution.components
        for identity in component.band_observation_ids
    }
    role_authority_band_ids = {
        band.observation_id
        for band in eligible_bands
        for component in (component_by_band_id[band.observation_id],)
        if component.role_authority_state == EvidenceState.SUPPORTED
        and (
            band.left_edge_observation_id,
            band.right_edge_observation_id,
        )
        == component.role_authority_pair_edge_observation_ids
    }
    relation_pairs: dict[int, set[tuple[ObservationId, ObservationId]]] = {}
    for band in separator_bands:
        # Normal material eligibility already owns the upper gap bound.
        # A directly measured narrow separator need not equal nominal pitch-W.
        if band.observation_id not in role_authority_band_ids:
            continue
        left = by_id.get(band.left_edge_observation_id)
        right = by_id.get(band.right_edge_observation_id)
        if (
            left is None
            or right is None
            or left.line_evidence is None
            or right.line_evidence is None
            or left.evidence_group_id != right.evidence_group_id
        ):
            continue
        left_roles = (
            [bound_role_by_id[left.observation_id]]
            if left.observation_id in bound_role_by_id
            else candidate_roles.get(left.observation_id, [])
        )
        right_roles = (
            [bound_role_by_id[right.observation_id]]
            if right.observation_id in bound_role_by_id
            else candidate_roles.get(right.observation_id, [])
        )
        if len(left_roles) != 1 or len(right_roles) != 1:
            continue
        left_role = left_roles[0]
        right_role = right_roles[0]
        if (
            left_role % 2 != 1
            or right_role != left_role + 1
            or not fact_fits_bound_frame(left_role, left)
            or not fact_fits_bound_frame(right_role, right)
        ):
            continue
        relation_pairs.setdefault(left_role // 2, set()).add(
            (left.observation_id, right.observation_id)
        )
    for adjacency_index in range(max(0, fit.template.count - 1)):
        pairs = relation_pairs.get(adjacency_index, set())
        if len(pairs) != 1:
            continue
        left_id, right_id = next(iter(pairs))
        left_role = 2 * adjacency_index + 1
        right_role = left_role + 1
        if bindings[left_role] is None:
            bind(left_role, by_id[left_id])
        if bindings[right_role] is None:
            bind(right_role, by_id[right_id])

    def remaining(
        role_index: int,
        *,
        intrinsic: bool = False,
    ) -> tuple[_candidate_model._AnchorFact, ...]:
        return tuple(
            item
            for item in (
                intrinsic_candidates_by_role[role_index]
                if intrinsic
                else candidates_by_role[role_index]
            )
            if item.observation_id not in bound_ids
        )

    def normalized(value: float) -> float:
        return fit.template.direction * value

    def unique_missing(
        candidates: tuple[_candidate_model._AnchorFact, ...],
        *,
        other: SequenceRoleBinding,
        missing_start: bool,
    ) -> _candidate_model._AnchorFact | None:
        values = tuple(normalized(item.coordinate_px) for item in candidates)
        other_px = normalized(other.canonical_position_px)
        if missing_start:
            minimum = other_px - frame_width.maximum
            maximum = other_px - frame_width.minimum
        else:
            minimum = other_px + frame_width.minimum
            maximum = other_px + frame_width.maximum
        begin = bisect_left(values, minimum - 1.0e-9)
        end = bisect_right(values, maximum + 1.0e-9)
        if end - begin != 1:
            return None
        selected = candidates[begin]
        if selected.evidence_group_id == other.evidence_group_id:
            return None
        return selected

    def unique_pair(
        starts: tuple[_candidate_model._AnchorFact, ...],
        ends: tuple[_candidate_model._AnchorFact, ...],
    ) -> tuple[_candidate_model._AnchorFact, _candidate_model._AnchorFact] | None:
        end_values = tuple(normalized(item.coordinate_px) for item in ends)
        selected: tuple[_candidate_model._AnchorFact, _candidate_model._AnchorFact] | None = None
        for start in starts:
            start_px = normalized(start.coordinate_px)
            begin = bisect_left(
                end_values,
                start_px + frame_width.minimum - 1.0e-9,
            )
            end = bisect_right(
                end_values,
                start_px + frame_width.maximum + 1.0e-9,
            )
            if end - begin > 1:
                return None
            if end == begin:
                continue
            candidate = ends[begin]
            if candidate.evidence_group_id == start.evidence_group_id:
                continue
            if selected is not None:
                return None
            selected = (start, candidate)
        return selected

    for slot_index in range(fit.template.count):
        start_index = 2 * slot_index
        end_index = start_index + 1
        start = bindings[start_index]
        end = bindings[end_index]
        if start is None and end is None:
            remaining_starts = remaining(start_index)
            remaining_ends = remaining(end_index)
            intrinsic_starts = remaining(start_index, intrinsic=True)
            intrinsic_ends = remaining(end_index, intrinsic=True)
            pair = unique_pair(
                intrinsic_starts,
                intrinsic_ends,
            )
            if pair is None:
                pair = unique_pair(
                    remaining_starts,
                    remaining_ends,
                )
            if pair is not None:
                bind(start_index, pair[0])
                bind(end_index, pair[1])
            elif frame_width_authority_px is not None:
                # An independently closed source W may complete one Frame
                # from one native coordinate.  It cannot choose between two
                # observed sides: the opposite registered corridor must be
                # empty, and the retained side must own its coordinate
                # without relational transfer from that missing opposite.
                if (
                    len(intrinsic_starts) == 1
                    and not registered_candidate_ids_by_role[end_index]
                ):
                    bind(start_index, intrinsic_starts[0])
                elif (
                    len(intrinsic_ends) == 1
                    and not registered_candidate_ids_by_role[start_index]
                ):
                    bind(end_index, intrinsic_ends[0])
        elif start is None:
            candidate = unique_missing(
                remaining(start_index, intrinsic=True),
                other=end,
                missing_start=True,
            )
            if candidate is None:
                candidate = unique_missing(
                    remaining(start_index),
                    other=end,
                    missing_start=True,
                )
            if candidate is not None:
                bind(start_index, candidate)
        elif end is None:
            candidate = unique_missing(
                remaining(end_index, intrinsic=True),
                other=start,
                missing_start=False,
            )
            if candidate is None:
                candidate = unique_missing(
                    remaining(end_index),
                    other=start,
                    missing_start=False,
                )
            if candidate is not None:
                bind(end_index, candidate)

    added = tuple(
        binding
        for old, binding in zip(fit.role_bindings, bindings, strict=True)
        if old is None and binding is not None
    )
    if not added:
        return _candidate_model._LocalRoleRefinement(
            fit,
            len(roles) * len(facts),
            0,
        )
    added_ids = {item.observation_id for item in added}
    role_intervals = list(fit.model_role_intervals_px)
    full_role_intervals = list(fit.model_full_role_intervals_px)
    for role_index, binding in enumerate(bindings):
        if binding is None or binding.observation_id not in added_ids:
            continue
        canonical = fit.model_role_positions_px[role_index]
        current = role_intervals[role_index]
        role_intervals[role_index] = FiniteInterval(
            min(current.minimum, binding.fit_position_interval_px.minimum, canonical),
            max(current.maximum, binding.fit_position_interval_px.maximum, canonical),
        )
        current_full = full_role_intervals[role_index]
        full_role_intervals[role_index] = FiniteInterval(
            min(
                current_full.minimum,
                binding.full_position_interval_px.minimum,
                canonical,
            ),
            max(
                current_full.maximum,
                binding.full_position_interval_px.maximum,
                canonical,
            ),
        )
    direct_added = sum(by_id[item.observation_id].direct for item in added)
    refined = replace(
        fit,
        model_role_intervals_px=tuple(role_intervals),
        model_full_role_intervals_px=tuple(full_role_intervals),
        role_bindings=tuple(bindings),
        contradicted_observation_count=max(
            0,
            fit.contradicted_observation_count - direct_added,
        ),
    )
    return _candidate_model._LocalRoleRefinement(
        refined,
        len(roles) * len(facts),
        len(added),
    )
