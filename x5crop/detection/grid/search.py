from __future__ import annotations

from dataclasses import replace
import math

from ...configuration.grid import FrameGridSearchPrior
from ...configuration.model import FrameCountMode, FrameCountRequest
from ...domain import Box, EvidenceState, FiniteInterval
from ...formats import FrameDesignApertureMm
from ..evidence.separator import (
    LongAxisSeparatorMeasurementField,
    SeparatorCorridorObservation,
    separator_corridor_observations,
)
from ..source_core import SourceLaneEvidence
from .model import (
    DOMINANCE_DIMENSION_CODES,
    DOMINANCE_PARTICIPATING_CODES,
    G_MAX,
    K_MAX,
    O_MAX,
    P_MAX,
    DominanceRelation,
    DominanceDimensionRelation,
    FrameCountDominanceAssessment,
    FrameCountDominanceDimension,
    FrameGridProposal,
    FrameGridWorkStatistics,
    FrameSlot,
    GridAnchorClass,
    GridCandidateKind,
    GridCorridorCandidate,
    LaneGridSelection,
    PlacementSeed,
    PlacementSeedKind,
    SafeCropEnvelope,
    SlotInteraction,
)


BOUNDARY_MATCH_TOLERANCE_MM = 1.5


def _proposal_sort_dimensions(
    proposal: FrameGridProposal,
) -> tuple[int, ...]:
    values = proposal.dominance_dimensions
    result: list[int] = []
    for code, value in zip(
        DOMINANCE_DIMENSION_CODES,
        values,
        strict=True,
    ):
        if code not in DOMINANCE_PARTICIPATING_CODES or value is None:
            continue
        if isinstance(value, tuple):
            result.extend(value)
        else:
            result.append(value)
    return tuple(result)


def _bounded_interval(
    center: float,
    radius: float,
    lower: float,
    upper: float,
) -> FiniteInterval | None:
    minimum = max(lower, center - radius)
    maximum = min(upper, center + radius)
    if maximum < minimum:
        return None
    return FiniteInterval(minimum, maximum)


def _expanded_observed_interval(
    interval: FiniteInterval,
    uncertainty_px: float,
    upper_px: float,
) -> FiniteInterval:
    bounded = _bounded_interval(
        interval.center,
        uncertainty_px + interval.width / 2.0,
        0.0,
        upper_px,
    )
    if bounded is None:
        raise ValueError("observed interval lies outside lane authority")
    return bounded


def _clipped_interval(
    interval: FiniteInterval,
    lower: float,
    upper: float,
) -> FiniteInterval | None:
    minimum = max(lower, interval.minimum)
    maximum = min(upper, interval.maximum)
    if maximum < minimum:
        return None
    return FiniteInterval(minimum, maximum)


def _nearest_line(
    field: LongAxisSeparatorMeasurementField,
    expected_px: float,
    tolerance_px: float,
):
    eligible = tuple(
        line
        for line in field.lines
        if abs(line.boundary_px - expected_px) <= tolerance_px
    )
    if not eligible:
        return None
    return min(
        eligible,
        key=lambda line: (
            abs(line.boundary_px - expected_px),
            -line.support_fraction,
            str(line.observation_id),
        ),
    )


def _seed_ordering_measurement(
    origin_px: float,
    count: int,
    aperture_px: float,
    pitch_px: float,
    field: LongAxisSeparatorMeasurementField,
    tolerance_px: float,
) -> float:
    endpoint_support = 0
    two_sided = 0
    observed_boundaries = 0
    residual = 0.0
    for ordinal in range(count):
        start = origin_px + ordinal * pitch_px
        end = start + aperture_px
        start_line = _nearest_line(field, start, tolerance_px)
        end_line = _nearest_line(field, end, tolerance_px)
        if start_line is not None:
            observed_boundaries += 1
            residual += abs(start_line.boundary_px - start)
        if end_line is not None:
            observed_boundaries += 1
            residual += abs(end_line.boundary_px - end)
        if start_line is not None and end_line is not None:
            two_sided += 1
        if ordinal == 0 and start_line is not None:
            endpoint_support += 1
        if ordinal == count - 1 and end_line is not None:
            endpoint_support += 1
    evidence_tier = (
        endpoint_support * 1000.0
        + two_sided * 100.0
        + observed_boundaries * 10.0
    )
    return evidence_tier - residual / max(1.0, tolerance_px)


def _placement_seeds(
    count: int,
    prior: FrameGridSearchPrior,
    field: LongAxisSeparatorMeasurementField,
    px_per_mm: float,
) -> tuple[tuple[PlacementSeed, ...], bool]:
    aperture_px = prior.aperture_long_axis_mm * px_per_mm
    pitch_px = prior.pitch_mm.center * px_per_mm
    uncertainty_px = prior.boundary_uncertainty_mm * px_per_mm
    tolerance_px = BOUNDARY_MATCH_TOLERANCE_MM * px_per_mm
    total_span = (count - 1) * pitch_px + aperture_px
    maximum_origin = field.long_extent_px - total_span
    if maximum_origin < 0.0:
        return (), False

    raw: list[
        tuple[
            float,
            PlacementSeedKind,
            object | None,
            FiniteInterval,
        ]
    ] = []
    for line in field.lines:
        for kind, origin in (
            (PlacementSeedKind.OBSERVED_START, line.boundary_px),
            (
                PlacementSeedKind.OBSERVED_END,
                line.boundary_px - aperture_px,
            ),
        ):
            interval = _bounded_interval(
                origin,
                uncertainty_px,
                0.0,
                maximum_origin,
            )
            if interval is not None:
                raw.append((origin, kind, line, interval))

    if prior.strip_mode == "full":
        leading_center = prior.full_leading_margin_mm.center * px_per_mm
        trailing_center = (
            field.long_extent_px
            - prior.full_trailing_margin_mm.center * px_per_mm
            - total_span
        )
        model_values = (
            (PlacementSeedKind.FULL_LEADING, leading_center),
            (PlacementSeedKind.FULL_TRAILING, trailing_center),
            (
                PlacementSeedKind.CENTERED,
                (field.long_extent_px - total_span) / 2.0,
            ),
        )
    else:
        model_values = (
            (PlacementSeedKind.FULL_LEADING, 0.0),
            (PlacementSeedKind.FULL_TRAILING, maximum_origin),
            (PlacementSeedKind.CENTERED, maximum_origin / 2.0),
        )
    for kind, origin in model_values:
        interval = _bounded_interval(
            origin,
            uncertainty_px,
            0.0,
            maximum_origin,
        )
        if interval is not None:
            raw.append((origin, kind, None, interval))

    scored = tuple(
        (
            origin,
            kind,
            line,
            interval,
            _seed_ordering_measurement(
                interval.center,
                count,
                aperture_px,
                pitch_px,
                field,
                tolerance_px,
            ),
        )
        for origin, kind, line, interval in raw
    )
    ranked = sorted(
        scored,
        key=lambda item: (
            -item[4],
            item[3].center,
            item[1].value,
            "" if item[2] is None else str(item[2].observation_id),
        ),
    )
    deduplicated: list[
        tuple[
            float,
            PlacementSeedKind,
            object | None,
            FiniteInterval,
            float,
        ]
    ] = []
    equality_px = prior.equality_interval_mm * px_per_mm
    for item in ranked:
        if any(
            abs(item[3].center - existing[3].center) <= equality_px
            for existing in deduplicated
        ):
            continue
        deduplicated.append(item)
    truncated = len(deduplicated) > P_MAX
    retained = deduplicated[:P_MAX]
    seeds = tuple(
        PlacementSeed(
            seed_id=(
                f"seed:{index}:{kind.value}:"
                f"{interval.center:.6f}"
            ),
            kind=kind,
            origin_px=interval,
            scalar_ordering_score=score,
            source_line_id=(
                None if line is None else line.observation_id
            ),
        )
        for index, (
            _origin,
            kind,
            line,
            interval,
            score,
        ) in enumerate(
            retained
        )
    )
    return seeds, truncated


def _local_corridor_candidates(
    corridor_index: int,
    expected_end_px: float,
    expected_start_px: float,
    observations: tuple[SeparatorCorridorObservation, ...],
    prior: FrameGridSearchPrior,
    px_per_mm: float,
    upper_px: float,
) -> tuple[GridCorridorCandidate, ...]:
    tolerance_px = BOUNDARY_MATCH_TOLERANCE_MM * px_per_mm
    uncertainty_px = prior.boundary_uncertainty_mm * px_per_mm
    observed: list[GridCorridorCandidate] = []
    for observation in observations:
        previous = observation.previous_photo_end_px
        following = observation.next_photo_start_px
        if observation.kind == "edge_pair":
            previous_residual = abs(previous.center - expected_end_px)
            next_residual = abs(following.center - expected_start_px)
            if max(previous_residual, next_residual) > tolerance_px:
                continue
            kind = GridCandidateKind.OBSERVED_EDGE_PAIR
        else:
            learned_gutter = observation.learned_gutter_px
            if learned_gutter is None:
                raise ValueError(
                    "one-sided candidate requires learned gutter authority"
                )
            previous_residual = abs(previous.center - expected_end_px)
            next_residual = abs(previous.center - expected_start_px)
            if min(previous_residual, next_residual) > tolerance_px:
                continue
            if previous_residual <= next_residual:
                following = _clipped_interval(
                    FiniteInterval(
                        previous.minimum + learned_gutter.minimum,
                        previous.maximum + learned_gutter.maximum,
                    ),
                    0.0,
                    upper_px,
                )
                if following is None:
                    continue
            else:
                previous = _clipped_interval(
                    FiniteInterval(
                        following.minimum - learned_gutter.maximum,
                        following.maximum - learned_gutter.minimum,
                    ),
                    0.0,
                    upper_px,
                )
                if previous is None:
                    continue
            kind = GridCandidateKind.OBSERVED_ONE_SIDED
        observed.append(
            GridCorridorCandidate(
                corridor_index=corridor_index,
                kind=kind,
                previous_photo_end_px=_expanded_observed_interval(
                    previous,
                    uncertainty_px,
                    upper_px,
                ),
                next_photo_start_px=_expanded_observed_interval(
                    following,
                    uncertainty_px,
                    upper_px,
                ),
                observation=observation,
                residual_mm=(
                    previous_residual + next_residual
                )
                / px_per_mm,
            )
        )
    observed = sorted(
        observed,
        key=lambda item: (
            item.residual_mm
            - (
                0.0
                if item.observation is None
                else item.observation.support
            ),
            item.kind.value,
            ""
            if item.observation is None
            else str(item.observation.observation_id),
        ),
    )[:O_MAX]

    model_end = _bounded_interval(
        expected_end_px,
        uncertainty_px,
        0.0,
        upper_px,
    )
    model_start = _bounded_interval(
        expected_start_px,
        uncertainty_px,
        0.0,
        upper_px,
    )
    if model_end is None or model_start is None:
        return tuple(observed)
    model = GridCorridorCandidate(
        corridor_index=corridor_index,
        kind=GridCandidateKind.MODEL_ONLY,
        previous_photo_end_px=model_end,
        next_photo_start_px=model_start,
        observation=None,
        residual_mm=0.0,
    )
    return tuple((*observed, model))[:K_MAX]


def _ordered_corridor_path(
    candidates: tuple[tuple[GridCorridorCandidate, ...], ...],
) -> tuple[
    tuple[GridCorridorCandidate, ...],
    int,
    int,
]:
    if not candidates:
        return (), 0, 0
    states: list[
        tuple[float, tuple[GridCorridorCandidate, ...]]
    ] = []
    state_count = 0
    transition_count = 0
    for candidate in candidates[0]:
        support = (
            0.0
            if candidate.observation is None
            else candidate.observation.support
        )
        states.append(
            (
                candidate.residual_mm - support,
                (candidate,),
            )
        )
        transition_count += 1
    state_count += len(states)
    for corridor_candidates in candidates[1:]:
        following_states: list[
            tuple[float, tuple[GridCorridorCandidate, ...]]
        ] = []
        for cost, path in states:
            prior_start = path[-1].next_photo_start_px
            for candidate in corridor_candidates:
                transition_count += 1
                if (
                    candidate.previous_photo_end_px.minimum
                    <= prior_start.minimum
                ):
                    continue
                support = (
                    0.0
                    if candidate.observation is None
                    else candidate.observation.support
                )
                following_states.append(
                    (
                        cost + candidate.residual_mm - support,
                        (*path, candidate),
                    )
                )
        if not following_states:
            return (), state_count, transition_count
        following_states.sort(
            key=lambda item: (
                item[0],
                tuple(candidate.kind.value for candidate in item[1]),
            )
        )
        states = following_states[:K_MAX]
        state_count += len(states)
    states.sort(
        key=lambda item: (
            item[0],
            tuple(candidate.kind.value for candidate in item[1]),
        )
    )
    return states[0][1], state_count, transition_count


def _interaction(
    previous_end: FiniteInterval,
    next_start: FiniteInterval,
    equality_px: float,
) -> SlotInteraction:
    delta = next_start.center - previous_end.center
    if abs(delta) <= equality_px:
        return SlotInteraction.CONTACT
    if delta < 0.0:
        return SlotInteraction.OVERLAP
    return SlotInteraction.SEPARATED


def _build_proposal(
    lane: SourceLaneEvidence,
    field: LongAxisSeparatorMeasurementField,
    prior: FrameGridSearchPrior,
    component_id: str,
    count: int,
    seed: PlacementSeed,
    observations: tuple[SeparatorCorridorObservation, ...],
    px_per_mm: float,
) -> tuple[FrameGridProposal | None, int, int, int, int]:
    aperture_px = prior.aperture_long_axis_mm * px_per_mm
    pitch_px = prior.pitch_mm.center * px_per_mm
    uncertainty_px = prior.boundary_uncertainty_mm * px_per_mm
    equality_px = prior.equality_interval_mm * px_per_mm
    upper_px = float(field.long_extent_px)
    origin = seed.origin_px.center

    candidates_by_corridor = tuple(
        _local_corridor_candidates(
            corridor_index,
            origin + (corridor_index - 1) * pitch_px + aperture_px,
            origin + corridor_index * pitch_px,
            observations,
            prior,
            px_per_mm,
            upper_px,
        )
        for corridor_index in range(1, count)
    )
    if any(not values for values in candidates_by_corridor):
        return None, 0, 0, 0, 0
    path, states, transitions = _ordered_corridor_path(
        candidates_by_corridor
    )
    if count > 1 and len(path) != count - 1:
        return None, states, transitions, 0, 0

    tolerance_px = BOUNDARY_MATCH_TOLERANCE_MM * px_per_mm
    first_line = _nearest_line(field, origin, tolerance_px)
    first_start = (
        seed.origin_px
        if first_line is None
        else _expanded_observed_interval(
            first_line.interval_px,
            uncertainty_px,
            upper_px,
        )
    )
    last_start_center = origin + (count - 1) * pitch_px
    last_end_center = last_start_center + aperture_px
    last_line = _nearest_line(field, last_end_center, tolerance_px)
    last_end = (
        _bounded_interval(
            last_end_center,
            uncertainty_px,
            0.0,
            upper_px,
        )
        if last_line is None
        else _expanded_observed_interval(
            last_line.interval_px,
            uncertainty_px,
            upper_px,
        )
    )
    if last_end is None:
        return None, states, transitions, 0, 0

    starts: list[FiniteInterval] = [first_start]
    ends: list[FiniteInterval] = []
    interactions: list[SlotInteraction] = []
    observed_candidate_count = 0
    model_candidate_count = 0
    for candidate in path:
        if candidate.kind == GridCandidateKind.MODEL_ONLY:
            model_candidate_count += 1
        else:
            observed_candidate_count += 1
        shared = FiniteInterval(
            min(
                candidate.previous_photo_end_px.minimum,
                candidate.next_photo_start_px.minimum,
            ),
            max(
                candidate.previous_photo_end_px.maximum,
                candidate.next_photo_start_px.maximum,
            ),
        )
        ends.append(shared)
        starts.append(shared)
        interactions.append(
            _interaction(
                candidate.previous_photo_end_px,
                candidate.next_photo_start_px,
                equality_px,
            )
        )
    ends.append(last_end)

    if any(
        end.minimum <= start.maximum
        for start, end in zip(starts, ends, strict=True)
    ):
        return (
            None,
            states,
            transitions,
            observed_candidate_count,
            model_candidate_count,
        )

    domain = lane.domain.work_box
    lane_id = lane.domain.lane_id
    slots: list[FrameSlot] = []
    envelopes: list[SafeCropEnvelope] = []
    observed_boundary_count = 0
    two_sided_slot_count = 0
    for ordinal, (start, end) in enumerate(
        zip(starts, ends, strict=True),
        start=1,
    ):
        expected_start = origin + (ordinal - 1) * pitch_px
        expected_end = expected_start + aperture_px
        start_observed = _nearest_line(
            field,
            expected_start,
            tolerance_px,
        ) is not None
        end_observed = _nearest_line(
            field,
            expected_end,
            tolerance_px,
        ) is not None
        observed_boundary_count += int(start_observed) + int(end_observed)
        two_sided_slot_count += int(start_observed and end_observed)
        work_left = domain.left + math.floor(start.minimum)
        work_right = domain.left + math.ceil(end.maximum)
        work_box = Box(
            work_left,
            domain.top,
            work_right,
            domain.bottom,
        )
        if (
            not work_box.valid()
            or work_box.left < domain.left
            or work_box.right > domain.right
        ):
            return (
                None,
                states,
                transitions,
                observed_candidate_count,
                model_candidate_count,
            )
        content_support = any(
            component.footprint.right > work_box.left
            and component.footprint.left < work_box.right
            for component in lane.content.components
        )
        slots.append(
            FrameSlot(
                lane_id=lane_id,
                lane_ordinal=ordinal,
                start_px=start,
                end_px=end,
                appearance_state=(
                    EvidenceState.SUPPORTED
                    if content_support
                    else EvidenceState.UNAVAILABLE
                ),
                previous_interaction=(
                    SlotInteraction.NOT_APPLICABLE
                    if ordinal == 1
                    else interactions[ordinal - 2]
                ),
                next_interaction=(
                    SlotInteraction.NOT_APPLICABLE
                    if ordinal == count
                    else interactions[ordinal - 1]
                ),
            )
        )
        envelopes.append(
            SafeCropEnvelope(
                lane_id=lane_id,
                lane_ordinal=ordinal,
                work_box=work_box,
                provenance=(
                    "observed_and_model_outward_union"
                    if start_observed or end_observed
                    else "model_outward_union"
                ),
            )
        )

    endpoint_support_count = int(first_line is not None) + int(
        last_line is not None
    )
    model_only_boundary_count = 2 * count - observed_boundary_count
    residual_mm = sum(item.residual_mm for item in path)
    scalar = (
        endpoint_support_count * 1000.0
        + two_sided_slot_count * 100.0
        + observed_boundary_count * 10.0
        - model_only_boundary_count
        - residual_mm
    )
    anchor_count = sum(
        item.kind != GridCandidateKind.MODEL_ONLY for item in path
    )
    anchor_class = (
        GridAnchorClass.ZERO
        if anchor_count == 0
        else GridAnchorClass.ONE
        if anchor_count == 1
        else GridAnchorClass.TWO_PLUS
    )
    proposal = FrameGridProposal(
        proposal_id=(
            f"{lane_id}:{component_id}:count:{count}:"
            f"{seed.seed_id}"
        ),
        lane_id=lane_id,
        component_id=component_id,
        count=count,
        seed=seed,
        corridor_candidates=path,
        anchor_class=anchor_class,
        slots=tuple(slots),
        safe_envelopes=tuple(envelopes),
        observed_boundary_count=observed_boundary_count,
        two_sided_slot_count=two_sided_slot_count,
        endpoint_support_count=endpoint_support_count,
        model_only_boundary_count=model_only_boundary_count,
        residual_mm=residual_mm,
        scalar_ordering_score=scalar,
        geometry_state=EvidenceState.SUPPORTED,
        ordinal_state=EvidenceState.SUPPORTED,
        ownership_state=EvidenceState.SUPPORTED,
        containment_state=(
            EvidenceState.UNAVAILABLE
            if lane.content.state != EvidenceState.CONTRADICTED
            else EvidenceState.CONTRADICTED
        ),
    )
    return (
        proposal,
        states,
        transitions,
        observed_candidate_count,
        model_candidate_count,
    )


def _best_for_count_component(
    lane: SourceLaneEvidence,
    field: LongAxisSeparatorMeasurementField,
    prior: FrameGridSearchPrior,
    component_id: str,
    count: int,
    px_per_mm: float,
    observations: tuple[SeparatorCorridorObservation, ...],
) -> tuple[FrameGridProposal | None, FrameGridWorkStatistics]:
    seeds, seeds_truncated = _placement_seeds(
        count,
        prior,
        field,
        px_per_mm,
    )
    proposals: list[FrameGridProposal] = []
    total_states = 0
    total_transitions = 0
    observed_candidates = 0
    model_candidates = 0
    for seed in seeds:
        (
            proposal,
            states,
            transitions,
            observed_count,
            model_count,
        ) = _build_proposal(
            lane,
            field,
            prior,
            component_id,
            count,
            seed,
            observations,
            px_per_mm,
        )
        total_states += states
        total_transitions += transitions
        observed_candidates += observed_count
        model_candidates += model_count
        if proposal is not None:
            proposals.append(proposal)
    assessments = tuple(
        _dominance(
            proposals[left_index],
            proposals[right_index],
            prior.equality_interval_mm,
        )
        for left_index in range(len(proposals))
        for right_index in range(left_index + 1, len(proposals))
    )
    retained = _non_dominated(tuple(proposals), assessments)
    best = _merge_count_component_proposals(
        retained,
        equality_interval_px=(
            prior.equality_interval_mm * px_per_mm
        ),
    )
    state_upper = FrameGridWorkStatistics.state_limit(count)
    transition_upper = FrameGridWorkStatistics.transition_limit(count)
    work = FrameGridWorkStatistics(
        lane_id=lane.domain.lane_id,
        component_id=component_id,
        count=count,
        seed_count=len(seeds),
        observed_candidate_count=observed_candidates,
        model_candidate_count=model_candidates,
        candidate_builds=len(seeds),
        dp_states=total_states,
        dp_transitions=total_transitions,
        state_upper=state_upper,
        transition_upper=transition_upper,
        retained_proposal_count=len(retained),
        search_incomplete=seeds_truncated,
        budget_exhausted=False,
        omitted_outcome_risk=False,
    )
    return best, work


def _proposals_are_output_equivalent(
    proposals: tuple[FrameGridProposal, ...],
    *,
    equality_interval_px: float = 0.0,
) -> bool:
    if not proposals:
        raise ValueError("output equivalence requires proposals")
    if equality_interval_px < 0.0:
        raise ValueError("output equivalence interval cannot be negative")
    count = proposals[0].count
    if any(proposal.count != count for proposal in proposals):
        raise ValueError("output equivalence requires one frame count")
    if all(
        all(
            slot.appearance_state == EvidenceState.UNAVAILABLE
            for slot in proposal.slots
        )
        for proposal in proposals
    ):
        return True
    if count == 1:
        return True
    pitch_floor = min(
        following.start_px.center - previous.start_px.center
        for proposal in proposals
        for previous, following in zip(
            proposal.slots,
            proposal.slots[1:],
        )
    )
    if pitch_floor <= 0.0:
        return False
    maximum_ordinal_shift = max(
        max(
            proposal.slots[ordinal].start_px.center
            for proposal in proposals
        )
        - min(
            proposal.slots[ordinal].start_px.center
            for proposal in proposals
        )
        for ordinal in range(count)
    )
    return maximum_ordinal_shift + equality_interval_px < pitch_floor


def _outward_union_proposals(
    proposals: tuple[FrameGridProposal, ...],
    *,
    proposal_id: str,
    component_id: str,
    ownership_state: EvidenceState,
) -> FrameGridProposal:
    if not proposals:
        raise ValueError("proposal union requires proposals")
    count = proposals[0].count
    lane_id = proposals[0].lane_id
    if any(
        proposal.count != count or proposal.lane_id != lane_id
        for proposal in proposals
    ):
        raise ValueError("proposal union requires one lane and count")
    base = max(
        proposals,
        key=lambda item: (
            _proposal_sort_dimensions(item),
            item.scalar_ordering_score,
            -item.residual_mm,
            item.proposal_id,
        ),
    )
    envelopes = tuple(
        SafeCropEnvelope(
            lane_id=lane_id,
            lane_ordinal=ordinal + 1,
            work_box=Box(
                min(
                    item.safe_envelopes[ordinal].work_box.left
                    for item in proposals
                ),
                min(
                    item.safe_envelopes[ordinal].work_box.top
                    for item in proposals
                ),
                max(
                    item.safe_envelopes[ordinal].work_box.right
                    for item in proposals
                ),
                max(
                    item.safe_envelopes[ordinal].work_box.bottom
                    for item in proposals
                ),
            ),
            provenance="observed_and_model_outward_union",
        )
        for ordinal in range(count)
    )
    return replace(
        base,
        proposal_id=proposal_id,
        component_id=component_id,
        safe_envelopes=envelopes,
        ownership_state=ownership_state,
    )


def _merge_count_component_proposals(
    proposals: tuple[FrameGridProposal, ...],
    *,
    equality_interval_px: float = 0.0,
) -> FrameGridProposal | None:
    if not proposals:
        return None
    if len(proposals) == 1:
        return proposals[0]
    base = proposals[0]
    if any(
        proposal.lane_id != base.lane_id
        or proposal.component_id != base.component_id
        or proposal.count != base.count
        for proposal in proposals
    ):
        raise ValueError(
            "count/component proposal merge requires one canonical identity"
        )
    equivalent = _proposals_are_output_equivalent(
        proposals,
        equality_interval_px=equality_interval_px,
    )
    return _outward_union_proposals(
        proposals,
        proposal_id=(
            f"{base.lane_id}:{base.component_id}:count:{base.count}:"
            f"seed_union:{len(proposals)}"
        ),
        component_id=base.component_id,
        ownership_state=(
            EvidenceState.SUPPORTED
            if equivalent
            and all(
                item.ownership_state != EvidenceState.CONTRADICTED
                for item in proposals
            )
            else EvidenceState.CONTRADICTED
        ),
    )


def _union_component_proposals(
    proposals: tuple[FrameGridProposal, ...],
    *,
    equality_interval_px: float,
) -> FrameGridProposal:
    if not proposals:
        raise ValueError("component union requires proposals")
    if len(proposals) == 1:
        return proposals[0]
    count = proposals[0].count
    lane_id = proposals[0].lane_id
    if any(
        proposal.count != count or proposal.lane_id != lane_id
        for proposal in proposals
    ):
        raise ValueError("component union requires one lane and count")
    component_ids = ",".join(
        sorted(proposal.component_id for proposal in proposals)
    )
    equivalent = _proposals_are_output_equivalent(
        proposals,
        equality_interval_px=equality_interval_px,
    )
    merged = _outward_union_proposals(
        proposals,
        proposal_id=f"{lane_id}:component_union:{component_ids}:count:{count}",
        component_id=f"union:{component_ids}",
        ownership_state=(
            EvidenceState.SUPPORTED
            if equivalent
            and all(
                item.ownership_state != EvidenceState.CONTRADICTED
                for item in proposals
            )
            else EvidenceState.CONTRADICTED
        ),
    )
    return replace(
        merged,
        observed_boundary_count=max(
            item.observed_boundary_count for item in proposals
        ),
        two_sided_slot_count=max(
            item.two_sided_slot_count for item in proposals
        ),
        endpoint_support_count=max(
            item.endpoint_support_count for item in proposals
        ),
        model_only_boundary_count=min(
            item.model_only_boundary_count for item in proposals
        ),
        residual_mm=min(item.residual_mm for item in proposals),
        scalar_ordering_score=max(
            item.scalar_ordering_score for item in proposals
        ),
    )


def _dominance(
    left: FrameGridProposal,
    right: FrameGridProposal,
    equality_interval_mm: float,
) -> FrameCountDominanceAssessment:
    left_dimensions = left.dominance_dimensions
    right_dimensions = right.dominance_dimensions
    dimensions = tuple(
        FrameCountDominanceDimension(
            code=code,
            left_value=left_value,
            right_value=right_value,
            relation=(
                DominanceDimensionRelation.NOT_APPLICABLE
                if left_value is None or right_value is None
                else DominanceDimensionRelation.LEFT_BETTER
                if left_value > right_value
                else DominanceDimensionRelation.RIGHT_BETTER
                if right_value > left_value
                else DominanceDimensionRelation.EQUIVALENT
            ),
            participates_in_dominance=(
                code in DOMINANCE_PARTICIPATING_CODES
            ),
        )
        for code, left_value, right_value in zip(
            DOMINANCE_DIMENSION_CODES,
            left_dimensions,
            right_dimensions,
            strict=True,
        )
    )
    applicable_relations = tuple(
        item.relation
        for item in dimensions
        if item.participates_in_dominance
        and item.relation != DominanceDimensionRelation.NOT_APPLICABLE
    )
    left_at_least = all(
        relation
        in {
            DominanceDimensionRelation.LEFT_BETTER,
            DominanceDimensionRelation.EQUIVALENT,
        }
        for relation in applicable_relations
    )
    right_at_least = all(
        relation
        in {
            DominanceDimensionRelation.RIGHT_BETTER,
            DominanceDimensionRelation.EQUIVALENT,
        }
        for relation in applicable_relations
    )
    left_strict = (
        DominanceDimensionRelation.LEFT_BETTER in applicable_relations
    )
    right_strict = (
        DominanceDimensionRelation.RIGHT_BETTER in applicable_relations
    )
    if left_at_least and left_strict:
        relation = DominanceRelation.LEFT_DOMINATES
    elif right_at_least and right_strict:
        relation = DominanceRelation.RIGHT_DOMINATES
    elif not left_strict and not right_strict:
        relation = DominanceRelation.EQUIVALENT
    else:
        relation = DominanceRelation.INCOMPARABLE
    residual_delta = left.residual_mm - right.residual_mm
    residual_relation = (
        "equal_interval"
        if abs(residual_delta) <= equality_interval_mm
        else "left_better"
        if residual_delta < 0.0
        else "right_better"
    )
    return FrameCountDominanceAssessment(
        left_proposal_id=left.proposal_id,
        right_proposal_id=right.proposal_id,
        equality_interval_mm=equality_interval_mm,
        dimensions=dimensions,
        residual_relation=residual_relation,
        relation=relation,
    )


def _non_dominated(
    proposals: tuple[FrameGridProposal, ...],
    assessments: tuple[FrameCountDominanceAssessment, ...],
) -> tuple[FrameGridProposal, ...]:
    dominated: set[str] = set()
    for assessment in assessments:
        if assessment.relation == DominanceRelation.LEFT_DOMINATES:
            dominated.add(assessment.right_proposal_id)
        elif assessment.relation == DominanceRelation.RIGHT_DOMINATES:
            dominated.add(assessment.left_proposal_id)
    return tuple(
        proposal
        for proposal in proposals
        if proposal.proposal_id not in dominated
    )


def _cross_count_selection_pool(
    proposals: tuple[FrameGridProposal, ...],
) -> tuple[FrameGridProposal, ...]:
    non_contradicted = tuple(
        proposal
        for proposal in proposals
        if all(
            state != EvidenceState.CONTRADICTED
            for state in (
                proposal.geometry_state,
                proposal.ordinal_state,
                proposal.ownership_state,
                proposal.containment_state,
            )
        )
    )
    return non_contradicted or proposals


def search_lane_grid(
    lane: SourceLaneEvidence,
    separator_field: LongAxisSeparatorMeasurementField,
    count_request: FrameCountRequest,
    aperture_components: tuple[FrameDesignApertureMm, ...],
    priors: tuple[FrameGridSearchPrior, ...],
    maximum_frame_count: int,
) -> LaneGridSelection:
    if (
        len(aperture_components) != len(priors)
        or maximum_frame_count <= 0
        or separator_field.lane_id != lane.domain.lane_id
    ):
        raise ValueError("lane Grid search inputs are inconsistent")
    scale_authority = lane.scan_canvas.axis_scales
    if scale_authority is None:
        raise ValueError("lane Grid search requires scan-canvas scale authority")
    px_per_mm = scale_authority.long_axis_px_per_mm.maximum
    count_candidates = tuple(
        count
        for count in count_request.candidate_counts
        if count <= maximum_frame_count
    )
    if not count_candidates:
        return LaneGridSelection(
            lane_id=lane.domain.lane_id,
            count_candidates=count_request.candidate_counts,
            proposals_by_count=(),
            dominance_assessments=(),
            retained_global_proposals=(),
            selected_proposal=None,
            work_by_count_component=(),
            separator_work_by_component=(),
            grid_search_coverage_state=EvidenceState.SUPPORTED,
            frame_count_state=EvidenceState.CONTRADICTED,
            selection_reason="no_valid_proposal",
            global_truncated=False,
            omitted_outcome_risk=False,
        )

    component_proposals: dict[int, list[FrameGridProposal]] = {
        count: [] for count in count_candidates
    }
    work: list[FrameGridWorkStatistics] = []
    separator_work = []
    for component_index, (component, prior) in enumerate(
        zip(aperture_components, priors, strict=True)
    ):
        component_id = (
            f"component:{component_index}:"
            f"{component.long_axis_mm:g}x{component.short_axis_mm:g}"
        )
        gutter_px = FiniteInterval(
            prior.gutter_mm.minimum * px_per_mm,
            prior.gutter_mm.maximum * px_per_mm,
        )
        observation_set = separator_corridor_observations(
            separator_field,
            gutter_px,
            equality_interval_px=(
                prior.equality_interval_mm * px_per_mm
            ),
        )
        separator_work.append(observation_set.work)
        for count in count_candidates:
            proposal, statistics = _best_for_count_component(
                lane,
                separator_field,
                prior,
                component_id,
                count,
                px_per_mm,
                observation_set.corridors,
            )
            work.append(statistics)
            if proposal is not None:
                component_proposals[count].append(proposal)

    proposals_by_count = tuple(
        _union_component_proposals(
            tuple(component_proposals[count]),
            equality_interval_px=(
                min(prior.equality_interval_mm for prior in priors)
                * px_per_mm
            ),
        )
        for count in count_candidates
        if component_proposals[count]
    )
    selection_pool = _cross_count_selection_pool(proposals_by_count)
    assessments = tuple(
        _dominance(
            selection_pool[left_index],
            selection_pool[right_index],
            min(prior.equality_interval_mm for prior in priors),
        )
        for left_index in range(len(selection_pool))
        for right_index in range(left_index + 1, len(selection_pool))
    )
    retained = _non_dominated(selection_pool, assessments)
    retained = tuple(
        sorted(
            retained,
            key=lambda item: (
                tuple(-value for value in _proposal_sort_dimensions(item)),
                -item.scalar_ordering_score,
                item.count,
                item.proposal_id,
            ),
        )
    )
    global_truncated = len(retained) > G_MAX
    omitted = retained[G_MAX:]
    retained = retained[:G_MAX]
    global_omitted_outcome_risk = bool(
        omitted
        and len({item.count for item in (*retained, *omitted)}) > 1
    )
    omitted_outcome_risk = global_omitted_outcome_risk or any(
        item.omitted_outcome_risk for item in work
    )

    if count_request.mode != FrameCountMode.AUTO:
        selected = retained[0] if retained else None
        reason = "fixed_or_explicit" if selected is not None else "no_valid_proposal"
    elif len(retained) == 1 and not omitted_outcome_risk:
        selected = retained[0]
        reason = "unique_non_dominated_count"
    elif retained:
        selected = None
        reason = "non_dominated_count_competition"
    else:
        selected = None
        reason = "no_valid_proposal"

    return LaneGridSelection(
        lane_id=lane.domain.lane_id,
        count_candidates=count_candidates,
        proposals_by_count=proposals_by_count,
        dominance_assessments=assessments,
        retained_global_proposals=retained,
        selected_proposal=selected,
        work_by_count_component=tuple(work),
        separator_work_by_component=tuple(separator_work),
        grid_search_coverage_state=(
            EvidenceState.CONTRADICTED
            if omitted_outcome_risk
            else EvidenceState.SUPPORTED
        ),
        frame_count_state=(
            EvidenceState.SUPPORTED
            if selected is not None
            else EvidenceState.CONTRADICTED
        ),
        selection_reason=reason,
        global_truncated=global_truncated,
        omitted_outcome_risk=omitted_outcome_risk,
    )
