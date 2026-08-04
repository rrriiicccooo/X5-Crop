from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, replace
from hashlib import sha256
import math

from ...domain import FiniteInterval, ObservationId, PositiveInterval
from ...formats import FramePhysicalSpec
from ..output_geometry import resolve_shared_strip_direction
from .boundary_geometry import (
    canonical_boundary_line,
    canonical_source_cross_axis_slope,
    canonical_source_sequence_axis_slope,
    source_cross_axis_slope_interval,
    source_sequence_axis_slope_interval,
)
from .measurement import (
    fit_template_bound_boundary_observation,
    robust_scalar_location,
)
from .model import (
    BoundaryAxis,
    BoundaryRole,
    DirectionAuthority,
    FrameBoundaryGeometry,
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    PhotoBoundaryObservation,
    PhotoBoundaryTransition,
    PositionSource,
    SharedStripDirection,
)
from .source_geometry import (
    JointAxisGeometry,
    NominalPitch,
    SourceFrameGeometry,
)
from .template_model import (
    BoundRoleEvidence,
    CanonicalFormatPlacement,
    ComponentTemplateProposal,
    CrossPlacement,
    CrossRoleEvidence,
    EnhancedPhaseQuery,
    EnhancedQueryRegistry,
    FormatPlacement,
    FrameFormatPlacement,
    LocalAdvanceKind,
    LocalAdvanceRelation,
    ProvisionalHeightTemplate,
    SequencePlacement,
    SourcePlacementMaterialization,
    TemplateLaneInput,
    TemplateLaneProposal,
    TemplateSequenceSeed,
)
from .template_profiles import (
    PhaseVote,
    ProfileRun,
    TemplatePhaseGroup,
    TemplateRole,
    build_phase_groups,
    group_support_exclusion_authorized,
    ordered_template_roles,
)


def _stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}:{sha256(payload).hexdigest()[:24]}"


def _intersection(
    left: FiniteInterval,
    right: FiniteInterval,
    *,
    epsilon: float = 0.0,
) -> FiniteInterval | None:
    minimum = max(left.minimum, right.minimum)
    maximum = min(left.maximum, right.maximum)
    if maximum < minimum:
        if minimum - maximum > epsilon:
            return None
        return FiniteInterval.exact((minimum + maximum) / 2.0)
    return FiniteInterval(minimum, maximum)


def _hull(values: tuple[FiniteInterval, ...]) -> FiniteInterval:
    if not values:
        raise ValueError("interval hull requires values")
    return FiniteInterval(
        min(value.minimum for value in values),
        max(value.maximum for value in values),
    )


def _add(left: FiniteInterval, right: FiniteInterval) -> FiniteInterval:
    return FiniteInterval(
        left.minimum + right.minimum,
        left.maximum + right.maximum,
    )


def _subtract(left: FiniteInterval, right: FiniteInterval) -> FiniteInterval:
    return FiniteInterval(
        left.minimum - right.maximum,
        left.maximum - right.minimum,
    )


def _common(values: tuple[FiniteInterval, ...]) -> FiniteInterval | None:
    if not values:
        return None
    minimum = max(value.minimum for value in values)
    maximum = min(value.maximum for value in values)
    return None if maximum < minimum else FiniteInterval(minimum, maximum)


def direction_class_key(direction: SharedStripDirection) -> tuple[object, ...]:
    return (
        round(direction.canonical_angle_degrees, 12),
        round(direction.full_angle_interval_degrees.minimum, 12),
        round(direction.full_angle_interval_degrees.maximum, 12),
        tuple(map(str, direction.selected_observation_ids)),
    )


def merge_sampling_equivalent_direction_classes(
    directions: tuple[SharedStripDirection, ...],
) -> tuple[SharedStripDirection, ...]:
    """Merge only direction classes that produce the exact same transform.

    The interval hull preserves every template-bound direction interpretation;
    ordinary support or residual scores never collapse a distinct transform.
    """

    grouped: dict[float, list[SharedStripDirection]] = {}
    for direction in directions:
        grouped.setdefault(direction.canonical_angle_degrees, []).append(direction)
    merged: list[SharedStripDirection] = []
    for canonical_angle, members in grouped.items():
        observation_ids = tuple(
            sorted(
                {
                    observation_id
                    for member in members
                    for observation_id in member.selected_observation_ids
                },
                key=str,
            )
        )
        full_angle_interval = FiniteInterval(
            min(
                member.full_angle_interval_degrees.minimum
                for member in members
            ),
            max(
                member.full_angle_interval_degrees.maximum
                for member in members
            ),
        )
        merged.append(
            SharedStripDirection(
                direction_id=_stable_id(
                    "template-direction-class",
                    canonical_angle,
                    full_angle_interval.minimum,
                    full_angle_interval.maximum,
                    *(str(identity) for identity in observation_ids),
                ),
                selected_observation_ids=observation_ids,
                full_angle_interval_degrees=full_angle_interval,
                canonical_angle_degrees=canonical_angle,
            )
        )
    return tuple(sorted(merged, key=direction_class_key))


def _template_bound_direction_classes(
    templates: tuple[ProvisionalHeightTemplate, ...],
) -> tuple[SharedStripDirection, ...]:
    directions: list[SharedStripDirection] = []
    for template in templates:
        resolution = resolve_shared_strip_direction(template.raw_observations)
        if resolution.direction is not None:
            directions.append(resolution.direction)
    return merge_sampling_equivalent_direction_classes(tuple(directions))


def _role_relative_projection(
    role: TemplateRole,
    component: FramePhysicalSpec,
    width_state: JointAxisGeometry,
) -> FiniteInterval:
    index = role.lane_ordinal - 1
    width_count = index + (1 if role.role == BoundaryRole.END else 0)
    return width_state.project_affine(
        q_coefficient=width_count * component.frame_width_mm,
        scale_coefficient=index * component.nominal_gap_mm,
    )


def _role_canonical_relative(
    role: TemplateRole,
    component: FramePhysicalSpec,
    width_state: JointAxisGeometry,
) -> float:
    scale, normalized, _factor = width_state.canonical_state()
    index = role.lane_ordinal - 1
    return (
        (index + (1 if role.role == BoundaryRole.END else 0))
        * component.frame_width_mm
        * normalized
        + index * component.nominal_gap_mm * scale
    )


def _sequence_phase_votes(
    lane: TemplateLaneInput,
    geometry: SourceFrameGeometry,
    roles: tuple[TemplateRole, ...],
) -> tuple[PhaseVote, ...]:
    runs = {run.run_id: run for run in lane.sequence_profile.runs}
    values: list[PhaseVote] = []
    for region in lane.sequence_profile.runs:
        run = runs[region.run_id]
        for role in roles:
            if not run.anchor_qualified_for(role.role):
                continue
            relative = _role_relative_projection(
                role,
                geometry.component,
                geometry.width_state,
            )
            values.append(
                PhaseVote(
                    vote_id=_stable_id(
                        "phase-vote",
                        geometry.component.component_id,
                        run.run_id,
                        role.role_index,
                    ),
                    run_id=run.run_id,
                    role=role,
                    phase_interval_px=_subtract(
                        run.coordinate_interval_px,
                        relative,
                    ),
                    transition_ids=run.transition_ids,
                    template_coordinate_px=_role_canonical_relative(
                        role,
                        geometry.component,
                        geometry.width_state,
                    ),
                )
            )
    return tuple(
        sorted(values, key=lambda item: (item.role.role_index, item.vote_id))
    )


def provisional_height_templates(
    lane: TemplateLaneInput,
    geometry: SourceFrameGeometry,
) -> tuple[ProvisionalHeightTemplate, ...]:
    allowance_mm = PHOTO_BOUNDARY_MEASUREMENT_SPEC.dimension_search_allowance_mm
    scale = geometry.height_state.scale_authority
    broad_height = FiniteInterval(
        max(0.0, geometry.component.frame_height_mm - allowance_mm)
        * scale.minimum,
        (geometry.component.frame_height_mm + allowance_mm) * scale.maximum,
    )
    fit_cache: dict[tuple[BoundaryRole, str], PhotoBoundaryObservation | None] = {}
    fitted: dict[
        BoundaryRole,
        list[tuple[ProfileRun, PhotoBoundaryObservation, FiniteInterval]],
    ] = {BoundaryRole.TOP: [], BoundaryRole.BOTTOM: []}
    for role, measurement_set in (
        (BoundaryRole.TOP, lane.top_measurement_set),
        (BoundaryRole.BOTTOM, lane.bottom_measurement_set),
    ):
        for run in lane.cross_profile.runs:
            if (
                run.role_hint != role
                or not run.anchor_qualified_for(role)
            ):
                continue
            key = (role, run.run_id)
            if key not in fit_cache:
                fit_cache[key] = fit_template_bound_boundary_observation(
                    measurement_set,
                    transition_ids=run.transition_ids,
                    role=role,
                    source_axis_long=lane.width_axis,
                    boundary_axis_scale_px_per_mm=(
                        lane.height_scale_px_per_mm
                    ),
                )
            observation = fit_cache[key]
            if observation is None:
                continue
            origin = (
                run.coordinate_interval_px
                if role == BoundaryRole.TOP
                else _subtract(run.coordinate_interval_px, broad_height)
            )
            fitted[role].append((run, observation, origin))
    for role in fitted:
        fitted[role].sort(
            key=lambda item: (item[2].center, item[0].run_id)
        )

    templates: list[ProvisionalHeightTemplate] = []
    paired_run_ids: set[str] = set()
    bottom_values = fitted[BoundaryRole.BOTTOM]
    bottom_centers = tuple(item[2].center for item in bottom_values)
    maximum_bottom_half_width = max(
        (item[2].width / 2.0 for item in bottom_values),
        default=0.0,
    )
    for top in fitted[BoundaryRole.TOP]:
        top_origin = top[2]
        start = bisect_left(
            bottom_centers,
            top_origin.minimum - maximum_bottom_half_width,
        )
        stop = bisect_right(
            bottom_centers,
            top_origin.maximum + maximum_bottom_half_width,
        )
        for bottom in bottom_values[start:stop]:
            origin = _intersection(top_origin, bottom[2])
            if origin is None:
                continue
            paired_run_ids.update((top[0].run_id, bottom[0].run_id))
            templates.append(
                ProvisionalHeightTemplate(
                    template_id=_stable_id(
                        "provisional-height-template",
                        geometry.component.component_id,
                        top[0].run_id,
                        bottom[0].run_id,
                    ),
                    component_id=geometry.component.component_id,
                    origin_interval_px=origin,
                    observed_runs=(top[0], bottom[0]),
                    raw_observations=(top[1], bottom[1]),
                )
            )
    for values in fitted.values():
        for run, observation, origin in values:
            if run.run_id in paired_run_ids:
                continue
            templates.append(
                ProvisionalHeightTemplate(
                    template_id=_stable_id(
                        "provisional-height-template",
                        geometry.component.component_id,
                        run.run_id,
                    ),
                    component_id=geometry.component.component_id,
                    origin_interval_px=origin,
                    observed_runs=(run,),
                    raw_observations=(observation,),
                )
            )
    unique = {item.template_id: item for item in templates}
    return tuple(unique[key] for key in sorted(unique))


def build_lane_template_proposal(
    lane: TemplateLaneInput,
    components: tuple[FramePhysicalSpec, ...],
) -> TemplateLaneProposal:
    component_proposals: list[ComponentTemplateProposal] = []
    all_height_templates: list[ProvisionalHeightTemplate] = []
    for component in components:
        geometry = SourceFrameGeometry.create(
            component,
            width_scale_px_per_mm=lane.width_scale_px_per_mm,
            height_scale_px_per_mm=lane.height_scale_px_per_mm,
        )
        roles = ordered_template_roles(lane.output_slot_count)
        votes = _sequence_phase_votes(lane, geometry, roles)
        groups, work = build_phase_groups(
            votes,
            roles,
            frame_width_lower_px=(
                geometry.width_state.extent_projection_px().minimum
            ),
        )
        if not groups:
            continue
        ambiguous_vote_ids = tuple(
            sorted(
                {
                    vote_id
                    for group in groups
                    for vote_id in group.ambiguous_vote_ids
                }
            )
        )
        heights = provisional_height_templates(lane, geometry)
        all_height_templates.extend(heights)
        component_proposals.append(
            ComponentTemplateProposal(
                component=component,
                initial_source_geometry=geometry,
                roles=roles,
                phase_votes=votes,
                phase_groups=groups,
                enhanced_phase_queries=tuple(
                    EnhancedPhaseQuery(
                        query_id=_stable_id(
                            "enhanced-phase-query",
                            component.component_id,
                            vote_id,
                        ),
                        vote_id=vote_id,
                    )
                    for vote_id in ambiguous_vote_ids
                ),
                height_templates=heights,
                grouping_work=work,
            )
        )
    observations = tuple(
        {
            str(observation.observation_id): observation
            for template in all_height_templates
            for observation in template.raw_observations
        }.values()
    )
    directions = _template_bound_direction_classes(
        tuple(all_height_templates)
    )
    return TemplateLaneProposal(
        lane=lane,
        components=tuple(component_proposals),
        raw_top_bottom_observations=tuple(
            sorted(observations, key=lambda item: str(item.observation_id))
        ),
        direction_classes=tuple(
            sorted(directions, key=direction_class_key)
        ),
    )


def shared_source_direction_classes(
    lane_proposals: tuple[TemplateLaneProposal, ...],
) -> tuple[SharedStripDirection, ...]:
    if not lane_proposals:
        return ()
    if any(not lane.direction_classes for lane in lane_proposals):
        return ()
    if any(len(lane.direction_classes) > 1 for lane in lane_proposals):
        return tuple(
            sorted(
                (
                    direction
                    for lane in lane_proposals
                    for direction in lane.direction_classes
                ),
                key=direction_class_key,
            )
        )
    selected_ids = {
        str(identity)
        for lane in lane_proposals
        for direction in lane.direction_classes
        for identity in direction.selected_observation_ids
    }
    observations = tuple(
        observation
        for lane in lane_proposals
        for observation in lane.raw_top_bottom_observations
        if str(observation.observation_id) in selected_ids
    )
    resolution = resolve_shared_strip_direction(observations)
    return () if resolution.direction is None else (resolution.direction,)


@dataclass(frozen=True)
class _BoundRunProjection:
    canonical_position_px: float
    fit_position_interval_px: FiniteInterval
    full_position_interval_px: FiniteInterval

    def __post_init__(self) -> None:
        if (
            not self.fit_position_interval_px.contains(
                self.canonical_position_px,
                epsilon=1.0e-8,
            )
            or not self.full_position_interval_px.contains(
                self.fit_position_interval_px.minimum,
                epsilon=1.0e-8,
            )
            or not self.full_position_interval_px.contains(
                self.fit_position_interval_px.maximum,
                epsilon=1.0e-8,
            )
        ):
            raise ValueError("bound run projection is invalid")


def _project_profile_run(
    run: ProfileRun,
    *,
    transitions: dict[str, PhotoBoundaryTransition],
    direction: SharedStripDirection,
    boundary_axis: BoundaryAxis,
    source_width_axis: BoundaryAxis,
    reference_trace_px: float,
    boundary_scale_px_per_mm: PositiveInterval,
) -> _BoundRunProjection:
    try:
        bound = tuple(transitions[str(identity)] for identity in run.transition_ids)
    except KeyError as exc:
        raise ValueError("profile run transition is unavailable") from exc
    if not bound:
        raise ValueError("profile run has no transition evidence")
    if boundary_axis == source_width_axis:
        canonical_slope = canonical_source_sequence_axis_slope(
            direction,
            source_width_axis,
        )
        slope_interval = source_sequence_axis_slope_interval(
            direction,
            source_width_axis,
        )
    else:
        canonical_slope = canonical_source_cross_axis_slope(
            direction,
            boundary_axis,
        )
        slope_interval = source_cross_axis_slope_interval(
            direction,
            boundary_axis,
        )
    centers = tuple(
        transition.coordinate_px
        + canonical_slope
        * (reference_trace_px - float(transition.trace_coordinate_px))
        for transition in bound
    )
    weights = tuple(
        max(
            1.0,
            transition.gradient_z
            + max(transition.tone_z, transition.texture_z),
        )
        for transition in bound
    )
    canonical = robust_scalar_location(
        centers,
        weights,
        boundary_scale_px_per_mm,
    )
    residuals = tuple(value - canonical for value in centers)
    center = sorted(residuals)[len(residuals) // 2]
    absolute = sorted(abs(value - center) for value in residuals)
    mad = absolute[len(absolute) // 2]
    numeric = (
        PHOTO_BOUNDARY_MEASUREMENT_SPEC.transition_coordinate_sampling_uncertainty_px
    )
    fit_uncertainty = mad / math.sqrt(len(bound)) + numeric
    fit = FiniteInterval(
        canonical - fit_uncertainty,
        canonical + fit_uncertainty,
    )
    projected = tuple(
        coordinate
        + slope
        * (reference_trace_px - float(transition.trace_coordinate_px))
        for transition in bound
        for coordinate in (
            transition.coordinate_interval_px.minimum,
            transition.coordinate_interval_px.maximum,
        )
        for slope in (slope_interval.minimum, slope_interval.maximum)
    )
    full = FiniteInterval(
        min(projected) - numeric,
        max(projected) + numeric,
    )
    if not full.contains(canonical, epsilon=1.0e-8):
        raise ValueError("canonical run position escaped exact projection")
    full = _hull((full, fit))
    return _BoundRunProjection(canonical, fit, full)


def _background_preference(run: ProfileRun, role: BoundaryRole) -> float:
    del role
    # Directional role preference already belongs to anchor qualification.
    # Canonical ranking uses only the format-neutral strength retained here.
    return min(1.0, run.evidence_strength / 12.0)


def _ambiguous_singleton_group(
    group: TemplatePhaseGroup,
    vote_id: str,
) -> bool:
    return (
        len(group.votes) == 1
        and group.votes[0].vote_id == vote_id
        and vote_id in group.ambiguous_vote_ids
    )


def _refine_component_phase_groups(
    lane: TemplateLaneInput,
    proposal: ComponentTemplateProposal,
    direction: SharedStripDirection,
) -> tuple[ComponentTemplateProposal, int]:
    """Resolve pre-registered ambiguous votes against existing groups only."""

    queries = proposal.enhanced_phase_queries
    if not queries:
        return proposal, 0
    registry = EnhancedQueryRegistry(tuple(item.query_id for item in queries))
    vote_by_id = {item.vote_id: item for item in proposal.phase_votes}
    run_by_id = {item.run_id: item for item in lane.sequence_profile.runs}
    assignments: dict[str, list[PhaseVote]] = {}
    for query in queries:
        if not registry.consume(query.query_id):
            raise ValueError("enhanced phase query executed more than once")
        vote = vote_by_id[query.vote_id]
        run = run_by_id[vote.run_id]
        projection = _project_profile_run(
            run,
            transitions=lane.transition_by_id,
            direction=direction,
            boundary_axis=lane.width_axis,
            source_width_axis=lane.width_axis,
            reference_trace_px=lane.height_authority_px.center,
            boundary_scale_px_per_mm=lane.width_scale_px_per_mm,
        )
        relative = _role_relative_projection(
            vote.role,
            proposal.component,
            proposal.initial_source_geometry.width_state,
        )
        refined_vote = replace(
            vote,
            phase_interval_px=_subtract(
                projection.fit_position_interval_px,
                relative,
            ),
        )
        targets = tuple(
            group
            for group in proposal.phase_groups
            if not _ambiguous_singleton_group(group, vote.vote_id)
            and all(
                existing.run_id != vote.run_id
                and existing.role.role_index != vote.role.role_index
                and set(map(str, existing.transition_ids)).isdisjoint(
                    map(str, vote.transition_ids)
                )
                for existing in group.votes
            )
            and _intersection(
                group.phase_interval_px,
                refined_vote.phase_interval_px,
            )
            is not None
        )
        if len(targets) == 1:
            assignments.setdefault(targets[0].group_id, []).append(
                refined_vote
            )

    accepted: dict[str, tuple[PhaseVote, ...]] = {}
    for group in proposal.phase_groups:
        additions = tuple(assignments.get(group.group_id, ()))
        if not additions:
            continue
        combined = tuple((*group.votes, *additions))
        if _common(tuple(item.phase_interval_px for item in combined)) is not None:
            accepted[group.group_id] = additions
    accepted_vote_ids = {
        vote.vote_id for additions in accepted.values() for vote in additions
    }
    refined_groups: list[TemplatePhaseGroup] = []
    frame_width_lower = (
        proposal.initial_source_geometry.width_state.extent_projection_px().minimum
    )
    for group in proposal.phase_groups:
        if any(
            _ambiguous_singleton_group(group, vote_id)
            for vote_id in accepted_vote_ids
        ):
            continue
        additions = accepted.get(group.group_id, ())
        if not additions:
            refined_groups.append(group)
            continue
        combined = tuple(
            sorted(
                (*group.votes, *additions),
                key=lambda item: (item.role.role_index, item.vote_id),
            )
        )
        phase = _common(tuple(item.phase_interval_px for item in combined))
        if phase is None:
            raise ValueError("accepted enhanced phase evidence lost intersection")
        refined_groups.append(
            TemplatePhaseGroup(
                group_id=_stable_id(
                    "enhanced-template-phase-group",
                    group.group_id,
                    *(item.vote_id for item in additions),
                    phase.minimum,
                    phase.maximum,
                ),
                phase_interval_px=phase,
                votes=combined,
                ambiguous_vote_ids=tuple(
                    vote_id
                    for vote_id in group.ambiguous_vote_ids
                    if vote_id not in accepted_vote_ids
                ),
                exclusion_authorized=group_support_exclusion_authorized(
                    role_coordinates_px=tuple(
                        item.template_coordinate_px for item in combined
                    ),
                    role_identities=tuple(
                        (item.role.lane_ordinal, item.role.role)
                        for item in combined
                    ),
                    transition_id_sets=tuple(
                        item.transition_ids for item in combined
                    ),
                    frame_width_lower_px=frame_width_lower,
                ),
            )
        )
    unique = {item.group_id: item for item in refined_groups}
    return (
        replace(
            proposal,
            phase_groups=tuple(unique[key] for key in sorted(unique)),
        ),
        registry.consumed_count,
    )


def _materialized_vote_evidence(
    lane: TemplateLaneInput,
    votes: tuple[PhaseVote, ...],
    direction: SharedStripDirection,
) -> tuple[BoundRoleEvidence, ...]:
    run_by_id = {run.run_id: run for run in lane.sequence_profile.runs}
    values: list[BoundRoleEvidence] = []
    for vote in votes:
        run = run_by_id[vote.run_id]
        projection = _project_profile_run(
            run,
            transitions=lane.transition_by_id,
            direction=direction,
            boundary_axis=lane.width_axis,
            source_width_axis=lane.width_axis,
            reference_trace_px=lane.height_authority_px.center,
            boundary_scale_px_per_mm=lane.width_scale_px_per_mm,
        )
        values.append(
            BoundRoleEvidence(
                role=vote.role,
                run_id=run.run_id,
                canonical_position_px=projection.canonical_position_px,
                fit_position_interval_px=projection.fit_position_interval_px,
                full_position_interval_px=projection.full_position_interval_px,
                transition_ids=run.transition_ids,
                support_fraction=run.support_fraction,
                continuous_support_fraction=run.continuous_support_fraction,
                fit_residual_px=run.fit_residual_px,
                background_preference=_background_preference(
                    run,
                    vote.role.role,
                ),
            )
        )
    return tuple(
        sorted(values, key=lambda item: (item.role.role_index, item.run_id))
    )


def _role_evidence_intervals(
    observations: tuple[BoundRoleEvidence, ...],
) -> dict[int, tuple[FiniteInterval, FiniteInterval, tuple[ObservationId, ...]]]:
    by_role: dict[int, list[BoundRoleEvidence]] = {}
    for observation in observations:
        by_role.setdefault(observation.role.role_index, []).append(observation)
    result = {}
    for role_index, values in by_role.items():
        fit = _common(tuple(item.fit_position_interval_px for item in values))
        full = _common(tuple(item.full_position_interval_px for item in values))
        if fit is None or full is None:
            continue
        result[role_index] = (
            fit,
            _hull((fit, full)),
            tuple(
                ObservationId(identity)
                for identity in sorted(
                    {
                        str(transition_id)
                        for item in values
                        for transition_id in item.transition_ids
                    }
                )
            ),
        )
    return result


def _common_extent_constraint(
    constraints: tuple[tuple[FiniteInterval, tuple[ObservationId, ...]], ...],
) -> tuple[FiniteInterval, tuple[ObservationId, ...]] | None:
    if not constraints:
        return None
    common = _common(tuple(item[0] for item in constraints))
    if common is None:
        return None
    identities = tuple(
        ObservationId(value)
        for value in sorted(
            {
                str(identity)
                for _interval, values in constraints
                for identity in values
            }
        )
    )
    return common, identities


def _refine_source_geometry(
    lane: TemplateLaneInput,
    proposal: ComponentTemplateProposal,
    direction: SharedStripDirection,
    compatible_heights: tuple[ProvisionalHeightTemplate, ...],
    *,
    sequence_seeds: tuple[TemplateSequenceSeed, ...] | None = None,
) -> SourceFrameGeometry:
    geometry = proposal.initial_source_geometry
    width_constraints: list[
        tuple[FiniteInterval, tuple[ObservationId, ...]]
    ] = []
    for seed in (
        build_template_sequence_seeds(proposal)
        if sequence_seeds is None
        else sequence_seeds
    ):
        if not seed.exclusion_authorized:
            continue
        evidence = _materialized_vote_evidence(
            lane,
            seed.votes,
            direction,
        )
        by_role = _role_evidence_intervals(evidence)
        # Sequence endpoints may be holder-censored.  Only an internal frame
        # pair is allowed to refine the source-wide true dimension.
        for ordinal in range(2, lane.output_slot_count):
            start_index = (ordinal - 1) * 2
            end_index = start_index + 1
            if start_index not in by_role or end_index not in by_role:
                continue
            start_fit, _start_full, start_ids = by_role[start_index]
            end_fit, _end_full, end_ids = by_role[end_index]
            width_constraints.append(
                (
                    _subtract(end_fit, start_fit),
                    tuple(sorted((*start_ids, *end_ids), key=str)),
                )
            )
    width_common = _common_extent_constraint(tuple(width_constraints))
    width_state = geometry.width_state
    if width_common is not None:
        width_state = width_state.intersect_observed_extent(
            width_common[0],
            observation_ids=width_common[1],
        )

    height_constraints: list[
        tuple[FiniteInterval, tuple[ObservationId, ...]]
    ] = []
    run_by_id = {run.run_id: run for run in lane.cross_profile.runs}
    for template in compatible_heights:
        template_runs = {
            run.role_hint: run_by_id[run.run_id]
            for run in template.observed_runs
        }
        if set(template_runs) != {BoundaryRole.TOP, BoundaryRole.BOTTOM}:
            continue
        top = _project_profile_run(
            template_runs[BoundaryRole.TOP],
            transitions=lane.transition_by_id,
            direction=direction,
            boundary_axis=lane.height_axis,
            source_width_axis=lane.width_axis,
            reference_trace_px=lane.width_authority_px.center,
            boundary_scale_px_per_mm=lane.height_scale_px_per_mm,
        )
        bottom = _project_profile_run(
            template_runs[BoundaryRole.BOTTOM],
            transitions=lane.transition_by_id,
            direction=direction,
            boundary_axis=lane.height_axis,
            source_width_axis=lane.width_axis,
            reference_trace_px=lane.width_authority_px.center,
            boundary_scale_px_per_mm=lane.height_scale_px_per_mm,
        )
        height_constraints.append(
            (
                _subtract(
                    bottom.fit_position_interval_px,
                    top.fit_position_interval_px,
                ),
                tuple(
                    sorted(
                        (
                            *template_runs[BoundaryRole.TOP].transition_ids,
                            *template_runs[BoundaryRole.BOTTOM].transition_ids,
                        ),
                        key=str,
                    )
                ),
            )
        )
    height_common = _common_extent_constraint(tuple(height_constraints))
    height_state = geometry.height_state
    if height_common is not None:
        height_state = height_state.intersect_observed_extent(
            height_common[0],
            observation_ids=height_common[1],
        )
    return SourceFrameGeometry(
        geometry_id=_stable_id(
            "source-frame-geometry",
            proposal.component.component_id,
            width_state.vertices,
            height_state.vertices,
            width_state.observation_ids,
            height_state.observation_ids,
        ),
        component=proposal.component,
        width_state=width_state,
        height_state=height_state,
    )


def _interval_sum(values: tuple[FiniteInterval, ...]) -> FiniteInterval:
    result = FiniteInterval.exact(0.0)
    for value in values:
        result = _add(result, value)
    return result


def local_advance_delta_from_observed_gap(
    observed_gap_px: FiniteInterval,
    geometry: SourceFrameGeometry,
) -> FiniteInterval | None:
    """Constrain one observed gap by the format-owned local advance range."""

    scale = geometry.width_state.feasible_scale_interval()
    gap_mm = geometry.component.local_advance_gap_mm
    allowed_products = tuple(
        gap * pixels_per_mm
        for gap in (gap_mm.minimum, gap_mm.maximum)
        for pixels_per_mm in (scale.minimum, scale.maximum)
    )
    allowed_gap_px = FiniteInterval(
        min(allowed_products),
        max(allowed_products),
    )
    constrained_gap = _intersection(observed_gap_px, allowed_gap_px)
    if constrained_gap is None:
        return None
    nominal_gap_px = geometry.width_state.project_affine(
        q_coefficient=0.0,
        scale_coefficient=geometry.component.nominal_gap_mm,
    )
    if _intersection(constrained_gap, nominal_gap_px) is not None:
        return FiniteInterval.exact(0.0)
    return _subtract(constrained_gap, nominal_gap_px)


def local_advance_prefix(
    relations: tuple[LocalAdvanceRelation, ...],
    *,
    lane_ordinal: int,
) -> tuple[FiniteInterval, float]:
    """Return the one-time phase step accumulated before one frame."""

    if lane_ordinal <= 0 or tuple(
        item.relation_ordinal for item in relations
    ) != tuple(range(1, len(relations) + 1)):
        raise ValueError("local advance relations must be ordered")
    prefix = relations[: lane_ordinal - 1]
    return (
        _interval_sum(tuple(item.delta_interval_px for item in prefix)),
        sum(item.canonical_delta_px for item in prefix),
    )


def _local_advance_relations(
    proposal: ComponentTemplateProposal,
    geometry: SourceFrameGeometry,
    observations: tuple[BoundRoleEvidence, ...],
) -> tuple[LocalAdvanceRelation, ...]:
    by_role = _role_evidence_intervals(observations)
    relations: list[LocalAdvanceRelation] = []
    for ordinal in range(1, len(proposal.roles) // 2):
        end_index = ordinal * 2 - 1
        next_start_index = ordinal * 2
        end = by_role.get(end_index)
        start = by_role.get(next_start_index)
        if end is None or start is None:
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
        observed_gap = _subtract(start[0], end[0])
        observation_ids = tuple(
            ObservationId(value)
            for value in sorted(
                {
                    *(str(identity) for identity in end[2]),
                    *(str(identity) for identity in start[2]),
                }
            )
        )
        delta = local_advance_delta_from_observed_gap(
            observed_gap,
            geometry,
        )
        if delta is None:
            raise ValueError("observed gap exceeds format local advance authority")
        if delta == FiniteInterval.exact(0.0):
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
    return tuple(relations)


def _supported_role_subset(
    group: TemplatePhaseGroup,
    *,
    first_ordinal: int,
    last_ordinal: int,
    frame_width_lower_px: float,
) -> tuple[PhaseVote, ...]:
    votes = tuple(
        item
        for item in group.votes
        if first_ordinal <= item.role.lane_ordinal <= last_ordinal
    )
    if not votes or not group_support_exclusion_authorized(
        role_coordinates_px=tuple(item.template_coordinate_px for item in votes),
        role_identities=tuple(
            (item.role.lane_ordinal, item.role.role) for item in votes
        ),
        transition_id_sets=tuple(item.transition_ids for item in votes),
        frame_width_lower_px=frame_width_lower_px,
    ):
        return ()
    return votes


def _phase_step_relation(
    upstream: TemplatePhaseGroup,
    downstream: TemplatePhaseGroup,
    *,
    relation_ordinal: int,
    upstream_votes: tuple[PhaseVote, ...],
    downstream_votes: tuple[PhaseVote, ...],
) -> LocalAdvanceRelation | None:
    upstream_ids = {
        str(identity)
        for vote in upstream_votes
        for identity in vote.transition_ids
    }
    downstream_ids = {
        str(identity)
        for vote in downstream_votes
        for identity in vote.transition_ids
    }
    if (
        upstream is downstream
        or not upstream_ids.isdisjoint(downstream_ids)
        or _intersection(
            upstream.phase_interval_px,
            downstream.phase_interval_px,
        )
        is not None
    ):
        return None
    delta = _subtract(
        downstream.phase_interval_px,
        upstream.phase_interval_px,
    )
    if delta.contains(0.0):
        return None
    return LocalAdvanceRelation(
        relation_ordinal=relation_ordinal,
        kind=(
            LocalAdvanceKind.WIDE
            if delta.center > 0.0
            else LocalAdvanceKind.NARROW
        ),
        delta_interval_px=delta,
        canonical_delta_px=delta.center,
        observation_ids=tuple(
            ObservationId(value)
            for value in sorted(upstream_ids | downstream_ids)
        ),
    )


def build_template_sequence_seeds(
    proposal: ComponentTemplateProposal,
) -> tuple[TemplateSequenceSeed, ...]:
    groups = proposal.phase_groups
    slot_count = len(proposal.roles) // 2
    frame_width_lower = (
        proposal.initial_source_geometry.width_state.extent_projection_px().minimum
    )
    downstream_by_split: dict[
        int,
        tuple[TemplatePhaseGroup, tuple[PhaseVote, ...]] | None,
    ] = {}
    upstream_support: dict[tuple[str, int], tuple[PhaseVote, ...]] = {}
    for split in range(1, slot_count):
        downstream: list[
            tuple[TemplatePhaseGroup, tuple[PhaseVote, ...]]
        ] = []
        for group in groups:
            upstream_support[(group.group_id, split)] = _supported_role_subset(
                group,
                first_ordinal=1,
                last_ordinal=split,
                frame_width_lower_px=frame_width_lower,
            )
            votes = _supported_role_subset(
                group,
                first_ordinal=split + 1,
                last_ordinal=slot_count,
                frame_width_lower_px=frame_width_lower,
            )
            if votes:
                downstream.append((group, votes))
        downstream_by_split[split] = (
            downstream[0] if len(downstream) == 1 else None
        )

    seeds: list[TemplateSequenceSeed] = []
    for initial in groups:
        current = initial
        group_for_ordinal: list[TemplatePhaseGroup] = []
        relations: list[LocalAdvanceRelation] = []
        group_ids = [initial.group_id]
        for split in range(1, slot_count):
            group_for_ordinal.append(current)
            downstream = downstream_by_split[split]
            relation = None
            if downstream is not None:
                upstream_votes = upstream_support[(current.group_id, split)]
                if upstream_votes:
                    relation = _phase_step_relation(
                        current,
                        downstream[0],
                        relation_ordinal=split,
                        upstream_votes=upstream_votes,
                        downstream_votes=downstream[1],
                    )
            if relation is None:
                relation = LocalAdvanceRelation(
                    relation_ordinal=split,
                    kind=LocalAdvanceKind.NOMINAL,
                    delta_interval_px=FiniteInterval.exact(0.0),
                    canonical_delta_px=0.0,
                    observation_ids=(),
                )
            else:
                current = downstream[0]
                if current.group_id not in group_ids:
                    group_ids.append(current.group_id)
            relations.append(relation)
        group_for_ordinal.append(current)
        votes = tuple(
            sorted(
                {
                    vote.vote_id: vote
                    for ordinal, group in enumerate(group_for_ordinal, start=1)
                    for vote in group.votes
                    if vote.role.lane_ordinal == ordinal
                }.values(),
                key=lambda item: (item.role.role_index, item.vote_id),
            )
        )
        if not votes:
            continue
        seeds.append(
            TemplateSequenceSeed(
                seed_id=_stable_id(
                    "template-sequence-seed",
                    *(group_ids),
                    *(item.kind.value for item in relations),
                    *(item.delta_interval_px for item in relations),
                ),
                phase_group_ids=tuple(group_ids),
                base_phase_interval_px=initial.phase_interval_px,
                votes=votes,
                local_advance_relations=tuple(relations),
                exclusion_authorized=(
                    initial.exclusion_authorized
                    and all(
                        item.kind == LocalAdvanceKind.NOMINAL
                        or bool(item.observation_ids)
                        for item in relations
                    )
                ),
            )
        )
    unique = {item.seed_id: item for item in seeds}
    return tuple(unique[key] for key in sorted(unique))


def _merge_local_advance_relations(
    declared: tuple[LocalAdvanceRelation, ...],
    observed: tuple[LocalAdvanceRelation, ...],
) -> tuple[LocalAdvanceRelation, ...]:
    if len(declared) != len(observed):
        raise ValueError("local advance relation sets disagree")
    merged: list[LocalAdvanceRelation] = []
    for left, right in zip(declared, observed, strict=True):
        if left.relation_ordinal != right.relation_ordinal:
            raise ValueError("local advance relation ordinals disagree")
        left_is_nominal = left.kind == LocalAdvanceKind.NOMINAL
        right_is_nominal = right.kind == LocalAdvanceKind.NOMINAL
        if not left_is_nominal and right_is_nominal and right.observation_ids:
            raise ValueError("observed nominal gap contradicts phase step")
        if left_is_nominal:
            merged.append(right)
            continue
        if right_is_nominal:
            merged.append(left)
            continue
        common = _intersection(left.delta_interval_px, right.delta_interval_px)
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
                kind=(
                    left.kind
                    if left.kind == right.kind
                    else LocalAdvanceKind.WIDE
                    if common.center > 0.0
                    else LocalAdvanceKind.NARROW
                ),
                delta_interval_px=common,
                canonical_delta_px=common.center,
                observation_ids=identities,
            )
        )
    return tuple(merged)


def _materialize_sequence_placement(
    lane: TemplateLaneInput,
    proposal: ComponentTemplateProposal,
    seed: TemplateSequenceSeed,
    direction: SharedStripDirection,
    geometry: SourceFrameGeometry,
) -> SequencePlacement:
    observations = _materialized_vote_evidence(
        lane,
        seed.votes,
        direction,
    )
    if not observations:
        raise ValueError("sequence placement has no absolute pixel anchor")
    relations = _merge_local_advance_relations(
        seed.local_advance_relations,
        _local_advance_relations(proposal, geometry, observations),
    )
    fit_phases: list[FiniteInterval] = []
    full_phases: list[FiniteInterval] = []
    implied_canonical: list[float] = []
    weights: list[float] = []
    for observation in observations:
        prefix_interval, prefix_canonical = local_advance_prefix(
            relations,
            lane_ordinal=observation.role.lane_ordinal,
        )
        relative = _role_relative_projection(
            observation.role,
            proposal.component,
            geometry.width_state,
        )
        fit_phases.append(
            _subtract(
                _subtract(observation.fit_position_interval_px, relative),
                prefix_interval,
            )
        )
        full_phases.append(
            _subtract(
                _subtract(observation.full_position_interval_px, relative),
                prefix_interval,
            )
        )
        implied_canonical.append(
            observation.canonical_position_px
            - _role_canonical_relative(
                observation.role,
                proposal.component,
                geometry.width_state,
            )
            - prefix_canonical
        )
        weights.append(
            max(
                1.0,
                observation.support_fraction
                + observation.continuous_support_fraction,
            )
        )
    phase_fit = _common(tuple(fit_phases))
    phase_full = _common(tuple(full_phases))
    if phase_fit is None or phase_full is None:
        raise ValueError("template-bound observations disagree on phase")
    phase_full = _hull((phase_full, phase_fit))
    canonical_phase = robust_scalar_location(
        tuple(implied_canonical),
        tuple(weights),
        geometry.width_state.feasible_scale_interval(),
    )
    if not phase_fit.contains(canonical_phase, epsilon=1.0e-9):
        canonical_phase = phase_fit.center
    by_role = _role_evidence_intervals(observations)
    canonical_positions: list[float] = []
    fit_positions: list[FiniteInterval] = []
    full_positions: list[FiniteInterval] = []
    for role in proposal.roles:
        prefix_interval, prefix_canonical = local_advance_prefix(
            relations,
            lane_ordinal=role.lane_ordinal,
        )
        relative = _role_relative_projection(
            role,
            proposal.component,
            geometry.width_state,
        )
        relative_canonical = _role_canonical_relative(
            role,
            proposal.component,
            geometry.width_state,
        )
        fit = _add(_add(phase_fit, relative), prefix_interval)
        full = _add(_add(phase_full, relative), prefix_interval)
        observed = by_role.get(role.role_index)
        if observed is not None:
            fit_intersection = _intersection(fit, observed[0])
            full_intersection = _intersection(full, observed[1])
            if fit_intersection is None or full_intersection is None:
                raise ValueError("observed role contradicts propagated template")
            fit = fit_intersection
            full = _hull((fit, full_intersection))
        canonical = canonical_phase + relative_canonical + prefix_canonical
        if not fit.contains(canonical, epsilon=1.0e-8):
            # Canonical preference has no authority outside the conditional
            # feasible interval.  The midpoint is the deterministic fallback,
            # never a clamp of the invalid preference.
            canonical = fit.center
        canonical_positions.append(canonical)
        fit_positions.append(fit)
        full_positions.append(_hull((full, fit)))
    return SequencePlacement(
        placement_id=_stable_id(
            "sequence-placement",
            proposal.component.component_id,
            seed.seed_id,
            direction.direction_id,
            geometry.geometry_id,
        ),
        template_seed_id=seed.seed_id,
        phase_group_ids=seed.phase_group_ids,
        source_geometry_id=geometry.geometry_id,
        roles=proposal.roles,
        phase_fit_interval_px=phase_fit,
        phase_full_interval_px=phase_full,
        nominal_pitch=NominalPitch.from_geometry(
            geometry.width_state,
            nominal_gap_mm=proposal.component.nominal_gap_mm,
        ),
        local_advance_relations=relations,
        canonical_positions_px=tuple(canonical_positions),
        fit_positions_px=tuple(fit_positions),
        full_positions_px=tuple(full_positions),
        observations=observations,
        exclusion_authorized=seed.exclusion_authorized,
    )


def _slope_displacement_interval(
    slope: FiniteInterval,
    trace_delta_px: float,
) -> FiniteInterval:
    values = (
        slope.minimum * trace_delta_px,
        slope.maximum * trace_delta_px,
    )
    return FiniteInterval(min(values), max(values))


def _materialize_cross_placement(
    lane: TemplateLaneInput,
    template: ProvisionalHeightTemplate,
    direction: SharedStripDirection,
    geometry: SourceFrameGeometry,
    frame_reference_traces_px: tuple[float, ...],
    frame_reference_intervals_px: tuple[FiniteInterval, ...],
) -> CrossPlacement:
    run_by_id = {run.run_id: run for run in lane.cross_profile.runs}
    lane_reference = lane.width_authority_px.center
    observed_runs = {
        run.role_hint: run_by_id[run.run_id]
        for run in template.observed_runs
    }
    lane_projections = {
        role: _project_profile_run(
            run,
            transitions=lane.transition_by_id,
            direction=direction,
            boundary_axis=lane.height_axis,
            source_width_axis=lane.width_axis,
            reference_trace_px=lane_reference,
            boundary_scale_px_per_mm=lane.height_scale_px_per_mm,
        )
        for role, run in observed_runs.items()
    }
    extent = geometry.height_state.extent_projection_px()
    phase_fit = _common(
        tuple(
            projection.fit_position_interval_px
            if role == BoundaryRole.TOP
            else _subtract(projection.fit_position_interval_px, extent)
            for role, projection in lane_projections.items()
        )
    )
    phase_full = _common(
        tuple(
            projection.full_position_interval_px
            if role == BoundaryRole.TOP
            else _subtract(projection.full_position_interval_px, extent)
            for role, projection in lane_projections.items()
        )
    )
    if phase_fit is None or phase_full is None:
        raise ValueError("template-bound height roles disagree on source height")
    phase_full = _hull((phase_full, phase_fit))
    scale, normalized, _factor = geometry.height_state.canonical_state()
    del scale
    canonical_extent = geometry.height_state.design_extent_mm * normalized
    canonical_extent_interval = FiniteInterval.exact(canonical_extent)
    canonical_phase_interval = _common(
        tuple(
            projection.fit_position_interval_px
            if role == BoundaryRole.TOP
            else _subtract(
                projection.fit_position_interval_px,
                canonical_extent_interval,
            )
            for role, projection in lane_projections.items()
        )
    )
    if canonical_phase_interval is None:
        raise ValueError("canonical source height is outside observed roles")
    canonical_phase_preference = sum(
        projection.canonical_position_px
        - (canonical_extent if role == BoundaryRole.BOTTOM else 0.0)
        for role, projection in lane_projections.items()
    ) / len(lane_projections)
    canonical_phase = (
        canonical_phase_preference
        if canonical_phase_interval.contains(canonical_phase_preference)
        else canonical_phase_interval.center
    )
    canonical_slope = canonical_source_cross_axis_slope(
        direction,
        lane.height_axis,
    )
    slope_interval = source_cross_axis_slope_interval(
        direction,
        lane.height_axis,
    )
    top_canonical: list[float] = []
    bottom_canonical: list[float] = []
    top_fit: list[FiniteInterval] = []
    bottom_fit: list[FiniteInterval] = []
    top_full: list[FiniteInterval] = []
    bottom_full: list[FiniteInterval] = []
    if len(frame_reference_traces_px) != len(frame_reference_intervals_px):
        raise ValueError("cross placement frame references are incomplete")
    for reference, reference_interval in zip(
        frame_reference_traces_px,
        frame_reference_intervals_px,
        strict=True,
    ):
        delta = reference - lane_reference
        canonical_shift = canonical_slope * delta
        shift = _slope_displacement_interval(slope_interval, delta)
        model_top_fit = _add(phase_fit, shift)
        model_bottom_fit = _add(model_top_fit, extent)
        full_shifts = tuple(
            _slope_displacement_interval(
                slope_interval,
                endpoint - lane_reference,
            )
            for endpoint in (
                reference_interval.minimum,
                reference_interval.maximum,
            )
        )
        model_top_full = _add(phase_full, _hull(full_shifts))
        model_bottom_full = _add(model_top_full, extent)
        frame_fit = {
            BoundaryRole.TOP: model_top_fit,
            BoundaryRole.BOTTOM: model_bottom_fit,
        }
        frame_full = {
            BoundaryRole.TOP: model_top_full,
            BoundaryRole.BOTTOM: model_bottom_full,
        }
        for role, run in observed_runs.items():
            direct_values = tuple(
                _project_profile_run(
                    run,
                    transitions=lane.transition_by_id,
                    direction=direction,
                    boundary_axis=lane.height_axis,
                    source_width_axis=lane.width_axis,
                    reference_trace_px=endpoint,
                    boundary_scale_px_per_mm=lane.height_scale_px_per_mm,
                )
                for endpoint in (
                    reference,
                    reference_interval.minimum,
                    reference_interval.maximum,
                )
            )
            fit = _intersection(
                frame_fit[role],
                direct_values[0].fit_position_interval_px,
            )
            full = _intersection(
                frame_full[role],
                _hull(
                    tuple(
                        item.full_position_interval_px
                        for item in direct_values
                    )
                ),
            )
            if fit is None or full is None:
                raise ValueError("exact height projection contradicts template")
            frame_fit[role] = fit
            frame_full[role] = full
        frame_phase_interval = _common(
            (
                frame_fit[BoundaryRole.TOP],
                _subtract(
                    frame_fit[BoundaryRole.BOTTOM],
                    canonical_extent_interval,
                ),
            )
        )
        if frame_phase_interval is None:
            raise ValueError("canonical source height is infeasible at frame")
        predicted_phase = canonical_phase + canonical_shift
        frame_phase = (
            predicted_phase
            if frame_phase_interval.contains(predicted_phase)
            else frame_phase_interval.center
        )
        canonical_top = frame_phase
        canonical_bottom = frame_phase + canonical_extent
        if canonical_top >= canonical_bottom:
            raise ValueError("canonical height placement is unordered")
        top_canonical.append(canonical_top)
        bottom_canonical.append(canonical_bottom)
        top_fit.append(frame_fit[BoundaryRole.TOP])
        bottom_fit.append(frame_fit[BoundaryRole.BOTTOM])
        top_full.append(
            _hull((frame_fit[BoundaryRole.TOP], frame_full[BoundaryRole.TOP]))
        )
        bottom_full.append(
            _hull(
                (
                    frame_fit[BoundaryRole.BOTTOM],
                    frame_full[BoundaryRole.BOTTOM],
                )
            )
        )
    observation_by_role = {
        observation.role: observation for observation in template.raw_observations
    }
    return CrossPlacement(
        placement_id=_stable_id(
            "cross-placement",
            template.template_id,
            direction.direction_id,
            geometry.geometry_id,
        ),
        provisional_template_id=template.template_id,
        source_geometry_id=geometry.geometry_id,
        lane_reference_trace_px=lane_reference,
        frame_reference_traces_px=frame_reference_traces_px,
        top_canonical_positions_px=tuple(top_canonical),
        bottom_canonical_positions_px=tuple(bottom_canonical),
        top_fit_positions_px=tuple(top_fit),
        bottom_fit_positions_px=tuple(bottom_fit),
        top_full_positions_px=tuple(top_full),
        bottom_full_positions_px=tuple(bottom_full),
        evidence=tuple(
            CrossRoleEvidence(
                role=role,
                run_id=run.run_id,
                observation=observation_by_role[role],
                canonical_position_at_lane_reference_px=(
                    lane_projections[role].canonical_position_px
                ),
                fit_position_at_lane_reference_px=(
                    lane_projections[role].fit_position_interval_px
                ),
                full_position_at_lane_reference_px=(
                    lane_projections[role].full_position_interval_px
                ),
            )
            for role, run in observed_runs.items()
        ),
    )


def _boundary_geometry(
    *,
    role: BoundaryRole,
    canonical_position_px: float,
    full_position_interval_px: FiniteInterval,
    reference_trace_px: float,
    support_projection_px: FiniteInterval,
    boundary_axis: BoundaryAxis,
    source_width_axis: BoundaryAxis,
    direction: SharedStripDirection,
    observation_ids: tuple[ObservationId, ...],
    position_source: PositionSource,
    named_position_inference: str | None,
) -> FrameBoundaryGeometry:
    if not observation_ids:
        raise ValueError("frame boundary requires position evidence")
    return FrameBoundaryGeometry(
        role=role,
        line=canonical_boundary_line(
            direction,
            boundary_axis=boundary_axis,
            source_axis_long=source_width_axis,
            trace_coordinate_px=reference_trace_px,
            position_px=canonical_position_px,
            support_projection_px=support_projection_px,
        ),
        reference_trace_px=reference_trace_px,
        canonical_position_px=canonical_position_px,
        full_position_interval_px=full_position_interval_px,
        full_direction_interval_degrees=(
            direction.full_angle_interval_degrees
        ),
        position_source=position_source,
        position_observation_ids=observation_ids,
        named_position_inference=named_position_inference,
        direction_authority=(
            DirectionAuthority.ORTHOGONAL_TO_SHARED_DIRECTION
            if role in {BoundaryRole.START, BoundaryRole.END}
            else DirectionAuthority.SHARED_TOP_BOTTOM_DIRECTION
        ),
        direction_reference_id=direction.direction_id,
    )


def _canonical_frames(
    lane: TemplateLaneInput,
    direction: SharedStripDirection,
    sequence: SequencePlacement,
    cross: CrossPlacement,
) -> tuple[FrameFormatPlacement, ...]:
    sequence_observations: dict[int, tuple[ObservationId, ...]] = {}
    for role_index in range(len(sequence.roles)):
        identities = tuple(
            ObservationId(value)
            for value in sorted(
                {
                    str(identity)
                    for item in sequence.observations
                    if item.role.role_index == role_index
                    for identity in item.transition_ids
                }
            )
        )
        if identities:
            sequence_observations[role_index] = identities
    all_sequence_ids = tuple(
        ObservationId(value)
        for value in sorted(
            {
                str(identity)
                for item in sequence.observations
                for identity in item.transition_ids
            }
        )
    )
    cross_by_role = {
        item.role: tuple(item.observation.transition_ids)
        for item in cross.evidence
    }
    all_cross_ids = tuple(
        ObservationId(value)
        for value in sorted(
            {
                str(identity)
                for item in cross.evidence
                for identity in item.observation.transition_ids
            }
        )
    )
    frames: list[FrameFormatPlacement] = []
    for ordinal in range(1, len(sequence.roles) // 2 + 1):
        start_index = (ordinal - 1) * 2
        end_index = start_index + 1
        frame_reference = (
            sequence.canonical_positions_px[start_index]
            + sequence.canonical_positions_px[end_index]
        ) / 2.0
        width_support = FiniteInterval(
            sequence.full_positions_px[start_index].minimum,
            sequence.full_positions_px[end_index].maximum,
        )
        start_ids = sequence_observations.get(start_index, all_sequence_ids)
        end_ids = sequence_observations.get(end_index, all_sequence_ids)
        top_ids = cross_by_role.get(BoundaryRole.TOP, all_cross_ids)
        bottom_ids = cross_by_role.get(BoundaryRole.BOTTOM, all_cross_ids)
        start = _boundary_geometry(
            role=BoundaryRole.START,
            canonical_position_px=sequence.canonical_positions_px[start_index],
            full_position_interval_px=sequence.full_positions_px[start_index],
            reference_trace_px=lane.height_authority_px.center,
            support_projection_px=lane.height_authority_px,
            boundary_axis=lane.width_axis,
            source_width_axis=lane.width_axis,
            direction=direction,
            observation_ids=start_ids,
            position_source=(
                PositionSource.OBSERVED_TRANSITION
                if start_index in sequence_observations
                else PositionSource.INFERRED_SEQUENCE
            ),
            named_position_inference=(
                None
                if start_index in sequence_observations
                else "start_from_template_phase_and_nominal_pitch"
            ),
        )
        end = _boundary_geometry(
            role=BoundaryRole.END,
            canonical_position_px=sequence.canonical_positions_px[end_index],
            full_position_interval_px=sequence.full_positions_px[end_index],
            reference_trace_px=lane.height_authority_px.center,
            support_projection_px=lane.height_authority_px,
            boundary_axis=lane.width_axis,
            source_width_axis=lane.width_axis,
            direction=direction,
            observation_ids=end_ids,
            position_source=(
                PositionSource.OBSERVED_TRANSITION
                if end_index in sequence_observations
                else PositionSource.INFERRED_SEQUENCE
            ),
            named_position_inference=(
                None
                if end_index in sequence_observations
                else "end_from_template_phase_and_nominal_pitch"
            ),
        )
        top = _boundary_geometry(
            role=BoundaryRole.TOP,
            canonical_position_px=cross.top_canonical_positions_px[ordinal - 1],
            full_position_interval_px=cross.top_full_positions_px[ordinal - 1],
            reference_trace_px=frame_reference,
            support_projection_px=width_support,
            boundary_axis=lane.height_axis,
            source_width_axis=lane.width_axis,
            direction=direction,
            observation_ids=top_ids,
            position_source=(
                PositionSource.OBSERVED_TRANSITION
                if BoundaryRole.TOP in cross_by_role
                else PositionSource.INFERRED_OPPOSITE_EDGE
            ),
            named_position_inference=(
                None
                if BoundaryRole.TOP in cross_by_role
                else "top_from_observed_bottom_and_source_height"
            ),
        )
        bottom = _boundary_geometry(
            role=BoundaryRole.BOTTOM,
            canonical_position_px=(
                cross.bottom_canonical_positions_px[ordinal - 1]
            ),
            full_position_interval_px=(
                cross.bottom_full_positions_px[ordinal - 1]
            ),
            reference_trace_px=frame_reference,
            support_projection_px=width_support,
            boundary_axis=lane.height_axis,
            source_width_axis=lane.width_axis,
            direction=direction,
            observation_ids=bottom_ids,
            position_source=(
                PositionSource.OBSERVED_TRANSITION
                if BoundaryRole.BOTTOM in cross_by_role
                else PositionSource.INFERRED_OPPOSITE_EDGE
            ),
            named_position_inference=(
                None
                if BoundaryRole.BOTTOM in cross_by_role
                else "bottom_from_observed_top_and_source_height"
            ),
        )
        polygon = (
            top.line.intersection(start.line),
            top.line.intersection(end.line),
            bottom.line.intersection(end.line),
            bottom.line.intersection(start.line),
        )
        frames.append(
            FrameFormatPlacement(
                placement_geometry_id=_stable_id(
                    "frame-format-placement",
                    sequence.placement_id,
                    cross.placement_id,
                    ordinal,
                ),
                lane_id=lane.lane_id,
                lane_ordinal=ordinal,
                top=top,
                bottom=bottom,
                start=start,
                end=end,
                canonical_source_polygon=polygon,
            )
        )
    return tuple(frames)


def _sequence_within_authority(
    placement: SequencePlacement,
    authority: FiniteInterval,
) -> bool:
    return all(
        authority.contains(position.minimum, epsilon=1.0e-8)
        and authority.contains(position.maximum, epsilon=1.0e-8)
        for position in placement.full_positions_px
    )


def _cross_within_authority(
    placement: CrossPlacement,
    authority: FiniteInterval,
) -> bool:
    return all(
        authority.contains(position.minimum, epsilon=1.0e-8)
        and authority.contains(position.maximum, epsilon=1.0e-8)
        for position in (
            *placement.top_full_positions_px,
            *placement.bottom_full_positions_px,
        )
    )


def _compatible_height_templates(
    lane_proposal: TemplateLaneProposal,
    component_proposal: ComponentTemplateProposal,
    direction: SharedStripDirection,
) -> tuple[ProvisionalHeightTemplate, ...]:
    selected_ids = {str(identity) for identity in direction.selected_observation_ids}
    return tuple(
        template
        for template in component_proposal.height_templates
        if {
            str(observation.observation_id)
            for observation in template.raw_observations
        }.issubset(selected_ids)
    )


def _materialize_component_seed(
    lane_proposal: TemplateLaneProposal,
    component_proposal: ComponentTemplateProposal,
    seed: TemplateSequenceSeed,
    direction: SharedStripDirection,
    source_geometry: SourceFrameGeometry | None = None,
) -> FormatPlacement | None:
    """Materialize one complete template interpretation.

    A seed owns one correlated source-geometry and local-advance hypothesis.
    Conflicting interpretations remain separate physical placements.
    """

    lane = lane_proposal.lane
    compatible_heights = _compatible_height_templates(
        lane_proposal,
        component_proposal,
        direction,
    )
    if not compatible_heights:
        return None
    if source_geometry is None:
        try:
            geometry = _refine_source_geometry(
                lane,
                component_proposal,
                direction,
                compatible_heights,
                sequence_seeds=(seed,),
            )
        except ValueError:
            return None
    else:
        if source_geometry.component != component_proposal.component:
            raise ValueError("source geometry component disagrees")
        geometry = source_geometry
    try:
        sequence = _materialize_sequence_placement(
            lane,
            component_proposal,
            seed,
            direction,
            geometry,
        )
    except ValueError:
        return None
    if not _sequence_within_authority(sequence, lane.width_authority_px):
        return None
    frame_references = tuple(
        (
            sequence.canonical_positions_px[index * 2]
            + sequence.canonical_positions_px[index * 2 + 1]
        )
        / 2.0
        for index in range(lane.output_slot_count)
    )
    frame_reference_intervals = tuple(
        FiniteInterval(
            (
                sequence.full_positions_px[index * 2].minimum
                + sequence.full_positions_px[index * 2 + 1].minimum
            )
            / 2.0,
            (
                sequence.full_positions_px[index * 2].maximum
                + sequence.full_positions_px[index * 2 + 1].maximum
            )
            / 2.0,
        )
        for index in range(lane.output_slot_count)
    )
    crosses: list[CrossPlacement] = []
    for template in compatible_heights:
        try:
            crosses.append(
                _materialize_cross_placement(
                    lane,
                    template,
                    direction,
                    geometry,
                    frame_references,
                    frame_reference_intervals,
                )
            )
        except ValueError:
            continue
    if not crosses:
        return None
    unique_crosses = {item.placement_id: item for item in crosses}
    retained_crosses = tuple(
        unique_crosses[key]
        for key in sorted(unique_crosses)
        if _cross_within_authority(
            unique_crosses[key],
            lane.height_authority_px,
        )
    )
    if not retained_crosses:
        return None
    canonical_cross = min(
        retained_crosses,
        key=lambda item: item.canonical_rank,
    )
    frames = _canonical_frames(
        lane,
        direction,
        sequence,
        canonical_cross,
    )
    canonical = CanonicalFormatPlacement(
        canonical_id=_stable_id(
            "canonical-format-placement",
            sequence.placement_id,
            canonical_cross.placement_id,
        ),
        sequence_placement_id=sequence.placement_id,
        cross_placement_id=canonical_cross.placement_id,
        frames=frames,
        canonical_rank=(
            *sequence.canonical_rank,
            *canonical_cross.canonical_rank,
        ),
    )
    return FormatPlacement(
        placement_id=_stable_id(
            "format-placement",
            lane.lane_id,
            component_proposal.component.component_id,
            direction.direction_id,
            geometry.geometry_id,
            sequence.placement_id,
            *(item.placement_id for item in retained_crosses),
        ),
        lane_id=lane.lane_id,
        component=component_proposal.component,
        output_slot_count=lane.output_slot_count,
        direction=direction,
        source_frame_geometry=geometry,
        sequence_placements=(sequence,),
        cross_placements=retained_crosses,
        canonical=canonical,
    )


def _retain_component_placements(
    placements: tuple[FormatPlacement, ...],
) -> tuple[FormatPlacement, ...]:
    authorized = tuple(
        item
        for item in placements
        if item.canonical_sequence.exclusion_authorized
    )
    if len(authorized) != 1:
        return placements
    authority = authorized[0]

    def shares_source_geometry(item: FormatPlacement) -> bool:
        try:
            authority.source_frame_geometry.intersect_source_state(
                item.source_frame_geometry
            )
        except ValueError:
            return False
        return True

    return tuple(
        item
        for item in placements
        if item is authority
        or not (
            shares_source_geometry(item)
            and item.canonical_sequence.observed_role_count == 1
            and item.canonical_sequence.observed_opposite_pair_count == 0
            and not any(
                relation.kind != LocalAdvanceKind.NOMINAL
                for relation in item.canonical_sequence.local_advance_relations
            )
        )
    )


def _materialize_component_placements(
    proposal: TemplateLaneProposal,
    component: ComponentTemplateProposal,
    direction: SharedStripDirection,
) -> tuple[FormatPlacement, ...]:
    values = tuple(
        placement
        for seed in build_template_sequence_seeds(component)
        if (
            placement := _materialize_component_seed(
                proposal,
                component,
                seed,
                direction,
            )
        )
        is not None
    )
    return _retain_component_placements(
        tuple(sorted(values, key=lambda item: item.placement_id))
    )


def materialize_lane_placements(
    proposal: TemplateLaneProposal,
    direction: SharedStripDirection,
) -> tuple[FormatPlacement, ...]:
    values = tuple(
        placement
        for component in proposal.components
        for placement in _materialize_component_placements(
            proposal,
            component,
            direction,
        )
    )
    return tuple(sorted(values, key=lambda item: item.placement_id))


def materialize_source_placements(
    lane_proposals: tuple[TemplateLaneProposal, ...],
    direction: SharedStripDirection,
) -> SourcePlacementMaterialization:
    """Materialize every lane from one source-wide component geometry."""

    if not lane_proposals:
        return SourcePlacementMaterialization((), ())
    refined_lanes: list[TemplateLaneProposal] = []
    enhanced_counts: list[int] = []
    for lane in lane_proposals:
        components: list[ComponentTemplateProposal] = []
        count = 0
        for component in lane.components:
            refined, consumed = _refine_component_phase_groups(
                lane.lane,
                component,
                direction,
            )
            components.append(refined)
            count += consumed
        refined_lanes.append(replace(lane, components=tuple(components)))
        enhanced_counts.append(count)
    refined_lane_proposals = tuple(refined_lanes)
    independent = tuple(
        materialize_lane_placements(lane, direction)
        for lane in refined_lane_proposals
    )
    if len(refined_lane_proposals) == 1:
        return SourcePlacementMaterialization(
            independent,
            tuple(enhanced_counts),
        )
    if len(refined_lane_proposals) != 2:
        raise ValueError("template-first source supports at most two lanes")

    components_by_lane = tuple(
        {
            item.component.component_id: item
            for item in lane.components
        }
        for lane in refined_lane_proposals
    )
    retained: tuple[list[FormatPlacement], list[FormatPlacement]] = ([], [])
    for left in independent[0]:
        for right in independent[1]:
            if left.component != right.component:
                continue
            try:
                shared = left.source_frame_geometry.intersect_source_state(
                    right.source_frame_geometry
                )
            except ValueError:
                continue
            seed_ids = (
                left.canonical_sequence.template_seed_id,
                right.canonical_sequence.template_seed_id,
            )
            rematerialized: list[FormatPlacement] = []
            for lane_index, seed_id in enumerate(seed_ids):
                component = components_by_lane[lane_index][
                    left.component.component_id
                ]
                seed = next(
                    item
                    for item in build_template_sequence_seeds(component)
                    if item.seed_id == seed_id
                )
                value = _materialize_component_seed(
                    refined_lane_proposals[lane_index],
                    component,
                    seed,
                    direction,
                    source_geometry=shared,
                )
                if value is None:
                    rematerialized = []
                    break
                rematerialized.append(value)
            if len(rematerialized) == 2:
                retained[0].append(rematerialized[0])
                retained[1].append(rematerialized[1])
    return SourcePlacementMaterialization(
        placements_by_lane=tuple(
            tuple(
                {item.placement_id: item for item in values}[key]
                for key in sorted(
                    {item.placement_id: item for item in values}
                )
            )
            for values in retained
        ),
        enhanced_query_counts_by_lane=tuple(enhanced_counts),
    )
