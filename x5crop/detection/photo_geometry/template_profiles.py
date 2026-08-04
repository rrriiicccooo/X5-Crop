from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from hashlib import sha256
import math

from ...domain import FiniteInterval, ObservationId
from .model import (
    BoundaryRole,
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    PhotoBoundaryTransition,
    SideTransitionRegion,
)


def _stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}:{sha256(payload).hexdigest()[:24]}"


def _intersection(
    left: FiniteInterval,
    right: FiniteInterval,
) -> FiniteInterval | None:
    minimum = max(left.minimum, right.minimum)
    maximum = min(left.maximum, right.maximum)
    return (
        None
        if maximum < minimum
        else FiniteInterval(minimum, maximum)
    )


def _common(values: tuple[FiniteInterval, ...]) -> FiniteInterval | None:
    if not values:
        return None
    minimum = max(value.minimum for value in values)
    maximum = min(value.maximum for value in values)
    return None if maximum < minimum else FiniteInterval(minimum, maximum)


@dataclass(frozen=True)
class ProfileRun:
    run_id: str
    coordinate_interval_px: FiniteInterval
    transition_ids: tuple[ObservationId, ...]
    trace_coordinates_px: tuple[int, ...]
    role_hint: BoundaryRole | None
    qualified_anchor_roles: tuple[BoundaryRole, ...]
    support_fraction: float
    continuous_support_fraction: float
    fit_residual_px: float
    evidence_strength: float

    def __post_init__(self) -> None:
        if (
            not self.run_id
            or not self.transition_ids
            or len(set(self.transition_ids)) != len(self.transition_ids)
            or not self.trace_coordinates_px
            or tuple(sorted(set(self.trace_coordinates_px)))
            != self.trace_coordinates_px
            or self.role_hint
            not in {
                None,
                BoundaryRole.TOP,
                BoundaryRole.BOTTOM,
            }
            or len(set(self.qualified_anchor_roles))
            != len(self.qualified_anchor_roles)
            or any(
                role
                not in {
                    BoundaryRole.START,
                    BoundaryRole.END,
                    BoundaryRole.TOP,
                    BoundaryRole.BOTTOM,
                }
                for role in self.qualified_anchor_roles
            )
            or (
                self.role_hint is not None
                and any(
                    role != self.role_hint
                    for role in self.qualified_anchor_roles
                )
            )
            or not 0.0 <= self.support_fraction <= 1.0
            or not 0.0 <= self.continuous_support_fraction <= 1.0
            or not math.isfinite(self.fit_residual_px)
            or self.fit_residual_px < 0.0
            or not math.isfinite(self.evidence_strength)
            or self.evidence_strength < 0.0
        ):
            raise ValueError("profile run is invalid")

    def anchor_qualified_for(self, role: BoundaryRole) -> bool:
        return role in self.qualified_anchor_roles


@dataclass(frozen=True)
class BasicAxisProfile:
    """One lane/axis profile retaining fixed per-trace run identity."""

    axis_name: str
    coordinate_count: int
    trace_coordinates_px: tuple[int, ...]
    runs: tuple[ProfileRun, ...]
    _runs_by_trace: dict[int, tuple[ProfileRun, ...]] = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if (
            self.axis_name not in {"sequence", "cross"}
            or self.coordinate_count <= 0
            or tuple(sorted(set(self.trace_coordinates_px)))
            != self.trace_coordinates_px
            or tuple(
                sorted(
                    self.runs,
                    key=lambda item: (
                        item.coordinate_interval_px.center,
                        item.run_id,
                    ),
                )
            )
            != self.runs
        ):
            raise ValueError("basic axis profile is invalid")
        by_trace: dict[int, list[ProfileRun]] = {
            trace: [] for trace in self.trace_coordinates_px
        }
        for run in self.runs:
            for trace in run.trace_coordinates_px:
                by_trace.setdefault(trace, []).append(run)
        object.__setattr__(
            self,
            "_runs_by_trace",
            {
                trace: tuple(
                    sorted(
                        values,
                        key=lambda item: (
                            item.coordinate_interval_px.center,
                            item.run_id,
                        ),
                    )
                )
                for trace, values in by_trace.items()
            },
        )

    def runs_at_trace(self, trace_coordinate_px: int) -> tuple[ProfileRun, ...]:
        return self._runs_by_trace.get(trace_coordinate_px, ())


def _region_anchor_qualified(
    region: SideTransitionRegion,
    role: BoundaryRole,
) -> bool:
    if role not in {BoundaryRole.START, BoundaryRole.END}:
        return False
    spec = PHOTO_BOUNDARY_MEASUREMENT_SPEC
    role_preference = (
        region.left_background_preference_fraction
        if role == BoundaryRole.START
        else region.right_background_preference_fraction
    )
    return (
        not region.ambiguous
        and region.trace_support_count
        >= max(
            spec.minimum_trace_count,
            math.ceil(spec.minimum_trace_fraction * region.queried_trace_count),
        )
        and region.continuous_support_fraction
        >= spec.minimum_continuous_support_fraction
        and region.mean_gradient_z >= spec.gradient_z_minimum
        and region.mean_tone_or_texture_z
        >= spec.tone_or_texture_z_minimum
        and region.background_side_support_fraction
        >= spec.directional_background_support_minimum
        and role_preference >= spec.directional_sequence_support_minimum
    )


def sequence_profile_from_regions(
    regions: tuple[SideTransitionRegion, ...],
    *,
    coordinate_count: int,
    transition_by_id: dict[str, PhotoBoundaryTransition],
) -> BasicAxisProfile:
    runs = tuple(
        sorted(
            (
                ProfileRun(
                    run_id=region.region_id,
                    coordinate_interval_px=(
                        region.proposal_position_interval_px
                    ),
                    transition_ids=region.transition_ids,
                    trace_coordinates_px=tuple(
                        sorted(
                            {
                                transition_by_id[str(identity)].trace_coordinate_px
                                for identity in region.transition_ids
                            }
                        )
                    ),
                    role_hint=None,
                    qualified_anchor_roles=tuple(
                        role
                        for role in (BoundaryRole.START, BoundaryRole.END)
                        if _region_anchor_qualified(region, role)
                    ),
                    support_fraction=(
                        region.trace_support_count / region.queried_trace_count
                    ),
                    continuous_support_fraction=(
                        region.continuous_support_fraction
                    ),
                    fit_residual_px=region.fit_residual_px,
                    evidence_strength=(
                        region.mean_gradient_z
                        + region.mean_tone_or_texture_z
                    ),
                )
                for region in regions
            ),
            key=lambda item: (item.coordinate_interval_px.center, item.run_id),
        )
    )
    traces = tuple(
        sorted({trace for run in runs for trace in run.trace_coordinates_px})
    )
    return BasicAxisProfile("sequence", coordinate_count, traces, runs)


def cross_profile_from_regions(
    top_regions: tuple[SideTransitionRegion, ...],
    bottom_regions: tuple[SideTransitionRegion, ...],
    *,
    coordinate_count: int,
    transition_by_id: dict[str, PhotoBoundaryTransition],
) -> BasicAxisProfile:
    values: list[ProfileRun] = []
    for role, regions in (
        (BoundaryRole.TOP, top_regions),
        (BoundaryRole.BOTTOM, bottom_regions),
    ):
        for region in regions:
            traces = tuple(
                sorted(
                    {
                        transition_by_id[str(identity)].trace_coordinate_px
                        for identity in region.transition_ids
                    }
                )
            )
            values.append(
                ProfileRun(
                    run_id=f"{role.value}:{region.region_id}",
                    coordinate_interval_px=(
                        region.proposal_position_interval_px
                    ),
                    transition_ids=region.transition_ids,
                    trace_coordinates_px=traces,
                    role_hint=role,
                    qualified_anchor_roles=(
                        (role,)
                        if (
                            not region.ambiguous
                            and region.trace_support_count
                            >= max(
                                PHOTO_BOUNDARY_MEASUREMENT_SPEC.minimum_trace_count,
                                math.ceil(
                                    PHOTO_BOUNDARY_MEASUREMENT_SPEC.minimum_trace_fraction
                                    * region.queried_trace_count
                                ),
                            )
                            and region.continuous_support_fraction
                            >= PHOTO_BOUNDARY_MEASUREMENT_SPEC.minimum_continuous_support_fraction
                            and region.mean_gradient_z
                            >= PHOTO_BOUNDARY_MEASUREMENT_SPEC.gradient_z_minimum
                            and region.mean_tone_or_texture_z
                            >= PHOTO_BOUNDARY_MEASUREMENT_SPEC.tone_or_texture_z_minimum
                        )
                        else ()
                    ),
                    support_fraction=(
                        region.trace_support_count / region.queried_trace_count
                    ),
                    continuous_support_fraction=(
                        region.continuous_support_fraction
                    ),
                    fit_residual_px=region.fit_residual_px,
                    evidence_strength=(
                        region.mean_gradient_z
                        + region.mean_tone_or_texture_z
                    ),
                )
            )
    runs = tuple(
        sorted(
            values,
            key=lambda item: (item.coordinate_interval_px.center, item.run_id),
        )
    )
    traces = tuple(
        sorted({trace for run in runs for trace in run.trace_coordinates_px})
    )
    return BasicAxisProfile("cross", coordinate_count, traces, runs)


@dataclass(frozen=True, order=True)
class TemplateRole:
    role_index: int
    lane_ordinal: int
    role: BoundaryRole

    def __post_init__(self) -> None:
        if (
            self.role_index < 0
            or self.lane_ordinal <= 0
            or self.role not in {BoundaryRole.START, BoundaryRole.END}
        ):
            raise ValueError("template role is invalid")


def ordered_template_roles(output_slot_count: int) -> tuple[TemplateRole, ...]:
    if output_slot_count <= 0:
        raise ValueError("template requires a positive output-slot count")
    return tuple(
        TemplateRole(
            role_index=(ordinal - 1) * 2 + role_offset,
            lane_ordinal=ordinal,
            role=role,
        )
        for ordinal in range(1, output_slot_count + 1)
        for role_offset, role in enumerate(
            (BoundaryRole.START, BoundaryRole.END)
        )
    )


@dataclass(frozen=True)
class PhaseVote:
    vote_id: str
    run_id: str
    role: TemplateRole
    phase_interval_px: FiniteInterval
    transition_ids: tuple[ObservationId, ...]
    template_coordinate_px: float

    def __post_init__(self) -> None:
        if (
            not self.vote_id
            or not self.run_id
            or not self.transition_ids
            or len(set(self.transition_ids)) != len(self.transition_ids)
            or not math.isfinite(self.template_coordinate_px)
        ):
            raise ValueError("phase vote is invalid")


@dataclass(frozen=True)
class TemplatePhaseGroup:
    group_id: str
    phase_interval_px: FiniteInterval
    votes: tuple[PhaseVote, ...]
    ambiguous_vote_ids: tuple[str, ...]
    exclusion_authorized: bool

    def __post_init__(self) -> None:
        if (
            not self.group_id
            or not self.votes
            or len({vote.vote_id for vote in self.votes}) != len(self.votes)
            or len(set(self.ambiguous_vote_ids)) != len(self.ambiguous_vote_ids)
        ):
            raise ValueError("template phase group is invalid")


@dataclass(frozen=True)
class PhaseGroupingWork:
    template_role_lookup_count: int
    template_role_match_count: int

    def __post_init__(self) -> None:
        if (
            self.template_role_lookup_count < 0
            or self.template_role_match_count < 0
        ):
            raise ValueError("phase grouping work is invalid")


def group_support_exclusion_authorized(
    *,
    role_coordinates_px: tuple[float, ...],
    role_identities: tuple[tuple[int, BoundaryRole], ...],
    transition_id_sets: tuple[tuple[ObservationId, ...], ...],
    frame_width_lower_px: float,
) -> bool:
    if (
        len(role_coordinates_px) != len(role_identities)
        or len(role_coordinates_px) != len(transition_id_sets)
        or not math.isfinite(frame_width_lower_px)
        or frame_width_lower_px <= 0.0
    ):
        raise ValueError("group support evidence is invalid")
    identities = [set(map(str, values)) for values in transition_id_sets]
    for left_index, left_ids in enumerate(identities):
        for right_index in range(left_index + 1, len(identities)):
            if not left_ids.isdisjoint(identities[right_index]):
                continue
            left_role = role_identities[left_index]
            right_role = role_identities[right_index]
            opposite_pair = (
                left_role[0] == right_role[0]
                and {left_role[1], right_role[1]}
                == {BoundaryRole.START, BoundaryRole.END}
            )
            separated = (
                abs(
                    role_coordinates_px[left_index]
                    - role_coordinates_px[right_index]
                )
                + 1.0e-9
                >= frame_width_lower_px
            )
            if opposite_pair or separated:
                return True
    return False


def _endpoint_peak_intervals(
    votes: tuple[PhaseVote, ...],
) -> tuple[FiniteInterval, ...]:
    if not votes:
        return ()
    vote_by_id = {vote.vote_id: vote for vote in votes}
    starts: dict[float, list[str]] = {}
    ends: dict[float, list[str]] = {}
    for vote in votes:
        starts.setdefault(vote.phase_interval_px.minimum, []).append(
            vote.vote_id
        )
        ends.setdefault(vote.phase_interval_px.maximum, []).append(
            vote.vote_id
        )
    active: set[str] = set()
    candidate_sets: list[frozenset[str]] = []
    for coordinate in sorted(set(starts) | set(ends)):
        active.update(starts.get(coordinate, ()))
        if active and ends.get(coordinate):
            candidate_sets.append(frozenset(active))
        active.difference_update(ends.get(coordinate, ()))
    unique_sets = tuple(dict.fromkeys(candidate_sets))
    maximal_sets = tuple(
        active_set
        for active_set in unique_sets
        if not any(active_set < other for other in unique_sets)
    )
    maximal = tuple(
        FiniteInterval(
            max(
                vote_by_id[vote_id].phase_interval_px.minimum
                for vote_id in active_set
            ),
            min(
                vote_by_id[vote_id].phase_interval_px.maximum
                for vote_id in active_set
            ),
        )
        for active_set in maximal_sets
    )
    return tuple(
        FiniteInterval(minimum, maximum)
        for minimum, maximum in sorted(
            {(item.minimum, item.maximum) for item in maximal}
        )
    )


def build_phase_groups(
    votes: tuple[PhaseVote, ...],
    roles: tuple[TemplateRole, ...],
    *,
    frame_width_lower_px: float = 1.0,
) -> tuple[tuple[TemplatePhaseGroup, ...], PhaseGroupingWork]:
    """Assign phase votes through one endpoint sweep and indexed role lookup."""

    if not votes or not roles:
        return (), PhaseGroupingWork(0, 0)
    if len({vote.vote_id for vote in votes}) != len(votes):
        raise ValueError("phase vote identities must be unique")
    seeds = _endpoint_peak_intervals(votes)
    by_role: dict[int, tuple[tuple[float, PhaseVote], ...]] = {}
    centers_by_role: dict[int, tuple[float, ...]] = {}
    maximum_half_width: dict[int, float] = {}
    for role in roles:
        indexed = tuple(
            sorted(
                (
                    (vote.phase_interval_px.center, vote)
                    for vote in votes
                    if vote.role == role
                ),
                key=lambda item: (item[0], item[1].vote_id),
            )
        )
        by_role[role.role_index] = indexed
        centers_by_role[role.role_index] = tuple(
            center for center, _vote in indexed
        )
        maximum_half_width[role.role_index] = max(
            (vote.phase_interval_px.width / 2.0 for _center, vote in indexed),
            default=0.0,
        )
    claims: dict[str, list[int]] = {vote.vote_id: [] for vote in votes}
    candidates_by_seed: list[list[PhaseVote]] = [[] for _seed in seeds]
    lookup_count = 0
    for seed_index, seed in enumerate(seeds):
        for role in roles:
            lookup_count += 1
            indexed = by_role[role.role_index]
            centers = centers_by_role[role.role_index]
            allowance = maximum_half_width[role.role_index]
            start = bisect_left(centers, seed.minimum - allowance)
            stop = bisect_right(centers, seed.maximum + allowance)
            for _center, vote in indexed[start:stop]:
                if _intersection(seed, vote.phase_interval_px) is None:
                    continue
                claims[vote.vote_id].append(seed_index)
    vote_by_id = {vote.vote_id: vote for vote in votes}
    ambiguous = tuple(
        sorted(vote_id for vote_id, values in claims.items() if len(values) > 1)
    )
    for vote_id, seed_indices in claims.items():
        if len(seed_indices) == 1:
            candidates_by_seed[seed_indices[0]].append(vote_by_id[vote_id])
    groups: list[TemplatePhaseGroup] = []
    matched = 0
    structurally_ambiguous: set[str] = set(ambiguous)
    for seed, assigned in zip(seeds, candidates_by_seed, strict=True):
        if not assigned:
            continue
        distance = {
            vote.vote_id: abs(
                vote.phase_interval_px.center - seed.center
            )
            for vote in assigned
        }
        by_run: dict[str, list[PhaseVote]] = {}
        by_role_index: dict[int, list[PhaseVote]] = {}
        for vote in assigned:
            by_run.setdefault(vote.run_id, []).append(vote)
            by_role_index.setdefault(vote.role.role_index, []).append(vote)

        def unique_nearest(values: list[PhaseVote]) -> str | None:
            ordered = sorted(
                values,
                key=lambda item: (distance[item.vote_id], item.vote_id),
            )
            if len(ordered) > 1 and math.isclose(
                distance[ordered[0].vote_id],
                distance[ordered[1].vote_id],
                rel_tol=0.0,
                abs_tol=1.0e-12,
            ):
                return None
            return ordered[0].vote_id

        run_choices = {
            run_id: unique_nearest(values)
            for run_id, values in by_run.items()
        }
        role_choices = {
            role_index: unique_nearest(values)
            for role_index, values in by_role_index.items()
        }
        selected = [
            vote
            for vote in assigned
            if run_choices[vote.run_id] == vote.vote_id
            and role_choices[vote.role.role_index] == vote.vote_id
        ]
        selected_ids = {vote.vote_id for vote in selected}
        structurally_ambiguous.update(
            vote.vote_id
            for vote in assigned
            if vote.vote_id not in selected_ids
        )
        if not selected:
            continue
        phase = _common(tuple(vote.phase_interval_px for vote in selected))
        if phase is None:
            continue
        selected.sort(key=lambda vote: (vote.role.role_index, vote.vote_id))
        matched += len(selected)
        role_coordinates = tuple(
            vote.template_coordinate_px for vote in selected
        )
        exclusion = group_support_exclusion_authorized(
            role_coordinates_px=role_coordinates,
            role_identities=tuple(
                (vote.role.lane_ordinal, vote.role.role)
                for vote in selected
            ),
            transition_id_sets=tuple(
                vote.transition_ids for vote in selected
            ),
            frame_width_lower_px=frame_width_lower_px,
        )
        groups.append(
            TemplatePhaseGroup(
                group_id=_stable_id(
                    "template-phase-group",
                    *(vote.vote_id for vote in selected),
                    phase.minimum,
                    phase.maximum,
                ),
                phase_interval_px=phase,
                votes=tuple(selected),
                ambiguous_vote_ids=tuple(
                    vote_id
                    for vote_id in ambiguous
                    if vote_by_id[vote_id].phase_interval_px.minimum
                    <= seed.maximum
                    and vote_by_id[vote_id].phase_interval_px.maximum
                    >= seed.minimum
                ),
                exclusion_authorized=exclusion,
            )
        )
    # A wide vote that touches multiple separated groups remains a bounded,
    # single-role conservative proposal.  It never gains exclusion authority.
    for vote_id in sorted(structurally_ambiguous):
        vote = vote_by_id[vote_id]
        groups.append(
            TemplatePhaseGroup(
                group_id=_stable_id("ambiguous-phase-vote", vote.vote_id),
                phase_interval_px=vote.phase_interval_px,
                votes=(vote,),
                ambiguous_vote_ids=(vote.vote_id,),
                exclusion_authorized=False,
            )
        )
    unique = {group.group_id: group for group in groups}
    ordered = tuple(unique[key] for key in sorted(unique))
    return ordered, PhaseGroupingWork(lookup_count, matched)
