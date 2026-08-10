"""Candidate-independent bounded edge and separator observations."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from hashlib import sha256
import math

from ...domain import FiniteInterval, ObservationId
from .model import (
    BoundaryEvidenceState,
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
    pair_qualified: bool = False

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
class BoundaryEdgeObservation:
    observation_id: ObservationId
    run_id: str
    coordinate_interval_px: FiniteInterval
    transition_ids: tuple[ObservationId, ...]
    trace_coordinates_px: tuple[int, ...]
    polarity: int
    support_fraction: float
    continuous_support_fraction: float
    fit_residual_px: float
    evidence_state: BoundaryEvidenceState = BoundaryEvidenceState.SUPPORT

    def __post_init__(self) -> None:
        if (
            not self.run_id
            or not self.transition_ids
            or self.polarity not in {-1, 1}
            or not self.trace_coordinates_px
            or not 0.0 <= self.support_fraction <= 1.0
            or not 0.0 <= self.continuous_support_fraction <= 1.0
            or not math.isfinite(self.fit_residual_px)
            or self.fit_residual_px < 0.0
            or self.evidence_state != BoundaryEvidenceState.SUPPORT
        ):
            raise ValueError("boundary edge observation is invalid")


@dataclass(frozen=True)
class SeparatorBandObservation:
    observation_id: ObservationId
    left_edge_observation_id: ObservationId
    right_edge_observation_id: ObservationId
    left_run_id: str
    right_run_id: str
    gap_interval_px: FiniteInterval
    transition_ids: tuple[ObservationId, ...]
    continuous_support_fraction: float
    darkness_contrast: float
    texture_contrast: float
    evidence_state: BoundaryEvidenceState = BoundaryEvidenceState.SUPPORT

    def __post_init__(self) -> None:
        if (
            not self.left_run_id
            or not self.right_run_id
            or self.gap_interval_px.minimum < 0.0
            or not self.transition_ids
            or len(set(self.transition_ids)) != len(self.transition_ids)
            or not 0.0 <= self.continuous_support_fraction <= 1.0
            or not math.isfinite(self.darkness_contrast)
            or not math.isfinite(self.texture_contrast)
            or self.darkness_contrast < 0.0
            or self.texture_contrast < 0.0
            or self.evidence_state != BoundaryEvidenceState.SUPPORT
        ):
            raise ValueError("separator band observation is invalid")


def _dominant_polarity(
    run: ProfileRun,
    transitions: dict[str, PhotoBoundaryTransition],
) -> int:
    value = sum(
        transitions[str(identity)].polarity for identity in run.transition_ids
    )
    return 1 if value > 0 else -1 if value < 0 else 0


def _median_transition_value(
    run: ProfileRun,
    transitions: dict[str, PhotoBoundaryTransition],
    field_name: str,
) -> float:
    values = sorted(
        float(getattr(transitions[str(identity)], field_name))
        for identity in run.transition_ids
    )
    return values[len(values) // 2]


def build_sequence_observations(
    profile: "BasicAxisProfile",
    transitions: dict[str, PhotoBoundaryTransition],
) -> tuple[
    tuple[BoundaryEdgeObservation, ...],
    tuple[SeparatorBandObservation, ...],
]:
    edges: list[BoundaryEdgeObservation] = []
    for run in profile.runs:
        polarity = _dominant_polarity(run, transitions)
        if polarity == 0:
            continue
        identity = ObservationId(
            _stable_id(
                "boundary-edge",
                run.run_id,
                run.coordinate_interval_px.minimum.hex(),
                run.coordinate_interval_px.maximum.hex(),
                polarity,
            )
        )
        edges.append(
            BoundaryEdgeObservation(
                observation_id=identity,
                run_id=run.run_id,
                coordinate_interval_px=run.coordinate_interval_px,
                transition_ids=run.transition_ids,
                trace_coordinates_px=run.trace_coordinates_px,
                polarity=polarity,
                support_fraction=run.support_fraction,
                continuous_support_fraction=run.continuous_support_fraction,
                fit_residual_px=run.fit_residual_px,
            )
        )
    ordered = tuple(
        sorted(edges, key=lambda item: (item.coordinate_interval_px.center, str(item.observation_id)))
    )
    bands: list[SeparatorBandObservation] = []
    for left, right in zip(ordered, ordered[1:]):
        if left.polarity == right.polarity:
            continue
        gap = FiniteInterval(
            max(0.0, right.coordinate_interval_px.minimum - left.coordinate_interval_px.maximum),
            max(0.0, right.coordinate_interval_px.maximum - left.coordinate_interval_px.minimum),
        )
        left_run = next(run for run in profile.runs if run.run_id == left.run_id)
        right_run = next(run for run in profile.runs if run.run_id == right.run_id)
        core_tone = 0.5 * (
            _median_transition_value(left_run, transitions, "right_tone_mean")
            + _median_transition_value(right_run, transitions, "left_tone_mean")
        )
        outer_tone = 0.5 * (
            _median_transition_value(left_run, transitions, "left_tone_mean")
            + _median_transition_value(right_run, transitions, "right_tone_mean")
        )
        core_texture = 0.5 * (
            _median_transition_value(left_run, transitions, "right_texture_mean")
            + _median_transition_value(right_run, transitions, "left_texture_mean")
        )
        outer_texture = 0.5 * (
            _median_transition_value(left_run, transitions, "left_texture_mean")
            + _median_transition_value(right_run, transitions, "right_texture_mean")
        )
        darkness = max(0.0, outer_tone - core_tone)
        texture = max(0.0, outer_texture - core_texture)
        if darkness == 0.0 and texture == 0.0:
            continue
        transition_ids = tuple(
            sorted(set((*left.transition_ids, *right.transition_ids)), key=str)
        )
        identity = ObservationId(
            _stable_id(
                "separator-band",
                left.observation_id,
                right.observation_id,
                gap.minimum.hex(),
                gap.maximum.hex(),
            )
        )
        bands.append(
            SeparatorBandObservation(
                observation_id=identity,
                left_edge_observation_id=left.observation_id,
                right_edge_observation_id=right.observation_id,
                left_run_id=left.run_id,
                right_run_id=right.run_id,
                gap_interval_px=gap,
                transition_ids=transition_ids,
                continuous_support_fraction=min(
                    left.continuous_support_fraction,
                    right.continuous_support_fraction,
                ),
                darkness_contrast=darkness,
                texture_contrast=texture,
            )
        )
    return ordered, tuple(bands)


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
    spec = PHOTO_BOUNDARY_MEASUREMENT_SPEC
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
                    pair_qualified=(
                        not region.ambiguous
                        and region.trace_support_count
                        >= max(
                            spec.minimum_trace_count,
                            math.ceil(
                                spec.minimum_trace_fraction
                                * region.queried_trace_count
                            ),
                        )
                        and region.continuous_support_fraction
                        >= spec.minimum_continuous_support_fraction
                        and region.mean_gradient_z >= spec.gradient_z_minimum
                        and region.mean_tone_or_texture_z
                        >= spec.tone_or_texture_z_minimum
                        and region.background_side_support_fraction
                        >= spec.directional_background_support_minimum
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
    spec = PHOTO_BOUNDARY_MEASUREMENT_SPEC
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
                                spec.minimum_trace_count,
                                math.ceil(
                                    spec.minimum_cross_trace_fraction
                                    * region.queried_trace_count
                                ),
                            )
                            and region.continuous_support_fraction
                            >= spec.minimum_continuous_support_fraction
                            and region.mean_gradient_z
                            >= spec.gradient_z_minimum
                            and region.mean_tone_or_texture_z
                            >= spec.tone_or_texture_z_minimum
                            and region.background_side_support_fraction
                            >= spec.directional_background_support_minimum
                            and (
                                region.left_background_preference_fraction
                                if role == BoundaryRole.TOP
                                else region.right_background_preference_fraction
                            )
                            >= spec.directional_sequence_support_minimum
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
                    pair_qualified=(
                        not region.ambiguous
                        and region.trace_support_count
                        >= max(
                            spec.minimum_trace_count,
                            math.ceil(
                                spec.minimum_cross_trace_fraction
                                * region.queried_trace_count
                            ),
                        )
                        and region.continuous_support_fraction
                        >= spec.minimum_continuous_support_fraction
                        and region.mean_gradient_z >= spec.gradient_z_minimum
                        and region.mean_tone_or_texture_z
                        >= spec.tone_or_texture_z_minimum
                        and region.background_side_support_fraction
                        >= spec.directional_background_support_minimum
                        and (
                            region.left_background_preference_fraction
                            if role == BoundaryRole.TOP
                            else region.right_background_preference_fraction
                        )
                        >= spec.directional_role_preference_minimum
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
class OrdinalBoundaryRole:
    role_index: int
    lane_ordinal: int
    role: BoundaryRole

    def __post_init__(self) -> None:
        if (
            self.role_index < 0
            or self.lane_ordinal <= 0
            or self.role not in {BoundaryRole.START, BoundaryRole.END}
        ):
            raise ValueError("cross_proposal role is invalid")


def ordered_ordinal_roles(output_slot_count: int) -> tuple[OrdinalBoundaryRole, ...]:
    if output_slot_count <= 0:
        raise ValueError("cross_proposal requires a positive output-slot count")
    return tuple(
        OrdinalBoundaryRole(
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
class SequenceRoleProposal:
    proposal_id: str
    run_id: str
    role: OrdinalBoundaryRole
    phase_interval_px: FiniteInterval
    transition_ids: tuple[ObservationId, ...]
    role_coordinate_px: float

    def __post_init__(self) -> None:
        if (
            not self.proposal_id
            or not self.run_id
            or not self.transition_ids
            or len(set(self.transition_ids)) != len(self.transition_ids)
            or not math.isfinite(self.role_coordinate_px)
        ):
            raise ValueError("sequence-role proposal is invalid")


@dataclass(frozen=True)
class SequenceHypothesisGroup:
    group_id: str
    phase_interval_px: FiniteInterval
    role_proposals: tuple[SequenceRoleProposal, ...]
    ambiguous_proposal_ids: tuple[str, ...]
    exclusion_authorized: bool

    def __post_init__(self) -> None:
        if (
            not self.group_id
            or not self.role_proposals
            or len({proposal.proposal_id for proposal in self.role_proposals}) != len(self.role_proposals)
            or len(set(self.ambiguous_proposal_ids)) != len(self.ambiguous_proposal_ids)
        ):
            raise ValueError("sequence hypothesis group is invalid")


@dataclass(frozen=True)
class SequenceGroupingWork:
    ordinal_role_lookup_count: int
    ordinal_role_match_count: int

    def __post_init__(self) -> None:
        if (
            self.ordinal_role_lookup_count < 0
            or self.ordinal_role_match_count < 0
        ):
            raise ValueError("sequence grouping work is invalid")


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
    proposals: tuple[SequenceRoleProposal, ...],
) -> tuple[FiniteInterval, ...]:
    if not proposals:
        return ()
    proposal_by_id = {proposal.proposal_id: proposal for proposal in proposals}
    starts: dict[float, list[str]] = {}
    ends: dict[float, list[str]] = {}
    for proposal in proposals:
        starts.setdefault(proposal.phase_interval_px.minimum, []).append(
            proposal.proposal_id
        )
        ends.setdefault(proposal.phase_interval_px.maximum, []).append(
            proposal.proposal_id
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
                proposal_by_id[proposal_id].phase_interval_px.minimum
                for proposal_id in active_set
            ),
            min(
                proposal_by_id[proposal_id].phase_interval_px.maximum
                for proposal_id in active_set
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


def build_sequence_groups(
    proposals: tuple[SequenceRoleProposal, ...],
    roles: tuple[OrdinalBoundaryRole, ...],
    *,
    frame_width_lower_px: float = 1.0,
) -> tuple[tuple[SequenceHypothesisGroup, ...], SequenceGroupingWork]:
    """Assign sequence-role proposals through one endpoint sweep and indexed role lookup."""

    if not proposals or not roles:
        return (), SequenceGroupingWork(0, 0)
    if len({proposal.proposal_id for proposal in proposals}) != len(proposals):
        raise ValueError("sequence-role proposal identities must be unique")
    seeds = _endpoint_peak_intervals(proposals)
    by_role: dict[int, tuple[tuple[float, SequenceRoleProposal], ...]] = {}
    centers_by_role: dict[int, tuple[float, ...]] = {}
    maximum_half_width: dict[int, float] = {}
    for role in roles:
        indexed = tuple(
            sorted(
                (
                    (proposal.phase_interval_px.center, proposal)
                    for proposal in proposals
                    if proposal.role == role
                ),
                key=lambda item: (item[0], item[1].proposal_id),
            )
        )
        by_role[role.role_index] = indexed
        centers_by_role[role.role_index] = tuple(
            center for center, _proposal in indexed
        )
        maximum_half_width[role.role_index] = max(
            (proposal.phase_interval_px.width / 2.0 for _center, proposal in indexed),
            default=0.0,
        )
    claims: dict[str, list[int]] = {proposal.proposal_id: [] for proposal in proposals}
    candidates_by_seed: list[list[SequenceRoleProposal]] = [[] for _seed in seeds]
    lookup_count = 0
    for seed_index, seed in enumerate(seeds):
        for role in roles:
            lookup_count += 1
            indexed = by_role[role.role_index]
            centers = centers_by_role[role.role_index]
            allowance = maximum_half_width[role.role_index]
            start = bisect_left(centers, seed.minimum - allowance)
            stop = bisect_right(centers, seed.maximum + allowance)
            for _center, proposal in indexed[start:stop]:
                if _intersection(seed, proposal.phase_interval_px) is None:
                    continue
                claims[proposal.proposal_id].append(seed_index)
    proposal_by_id = {proposal.proposal_id: proposal for proposal in proposals}
    ambiguous = tuple(
        sorted(proposal_id for proposal_id, values in claims.items() if len(values) > 1)
    )
    for proposal_id, seed_indices in claims.items():
        if len(seed_indices) == 1:
            candidates_by_seed[seed_indices[0]].append(
                proposal_by_id[proposal_id]
            )
    groups: list[SequenceHypothesisGroup] = []
    matched = 0
    structurally_ambiguous: set[str] = set(ambiguous)
    for seed, assigned in zip(seeds, candidates_by_seed, strict=True):
        if not assigned:
            continue
        distance = {
            proposal.proposal_id: abs(
                proposal.phase_interval_px.center - seed.center
            )
            for proposal in assigned
        }
        by_run: dict[str, list[SequenceRoleProposal]] = {}
        by_role_index: dict[int, list[SequenceRoleProposal]] = {}
        for proposal in assigned:
            by_run.setdefault(proposal.run_id, []).append(proposal)
            by_role_index.setdefault(proposal.role.role_index, []).append(proposal)

        def unique_nearest(values: list[SequenceRoleProposal]) -> str | None:
            ordered = sorted(
                values,
                key=lambda item: (distance[item.proposal_id], item.proposal_id),
            )
            if len(ordered) > 1 and math.isclose(
                distance[ordered[0].proposal_id],
                distance[ordered[1].proposal_id],
                rel_tol=0.0,
                abs_tol=1.0e-12,
            ):
                return None
            return ordered[0].proposal_id

        run_choices = {
            run_id: unique_nearest(values)
            for run_id, values in by_run.items()
        }
        role_choices = {
            role_index: unique_nearest(values)
            for role_index, values in by_role_index.items()
        }
        selected = [
            proposal
            for proposal in assigned
            if run_choices[proposal.run_id] == proposal.proposal_id
            and role_choices[proposal.role.role_index] == proposal.proposal_id
        ]
        selected_ids = {proposal.proposal_id for proposal in selected}
        structurally_ambiguous.update(
            proposal.proposal_id
            for proposal in assigned
            if proposal.proposal_id not in selected_ids
        )
        if not selected:
            continue
        phase = _common(tuple(proposal.phase_interval_px for proposal in selected))
        if phase is None:
            continue
        selected.sort(key=lambda proposal: (proposal.role.role_index, proposal.proposal_id))
        matched += len(selected)
        role_coordinates = tuple(
            proposal.role_coordinate_px for proposal in selected
        )
        exclusion = group_support_exclusion_authorized(
            role_coordinates_px=role_coordinates,
            role_identities=tuple(
                (proposal.role.lane_ordinal, proposal.role.role)
                for proposal in selected
            ),
            transition_id_sets=tuple(
                proposal.transition_ids for proposal in selected
            ),
            frame_width_lower_px=frame_width_lower_px,
        )
        groups.append(
            SequenceHypothesisGroup(
                group_id=_stable_id(
                    "cross_proposal-phase-group",
                    *(proposal.proposal_id for proposal in selected),
                    phase.minimum,
                    phase.maximum,
                ),
                phase_interval_px=phase,
                role_proposals=tuple(selected),
                ambiguous_proposal_ids=tuple(
                    proposal_id
                    for proposal_id in ambiguous
                    if proposal_by_id[proposal_id].phase_interval_px.minimum
                    <= seed.maximum
                    and proposal_by_id[proposal_id].phase_interval_px.maximum
                    >= seed.minimum
                ),
                exclusion_authorized=exclusion,
            )
        )
    # A wide proposal that touches multiple separated groups remains a bounded,
    # single-role conservative proposal.  It never gains exclusion authority.
    for proposal_id in sorted(structurally_ambiguous):
        proposal = proposal_by_id[proposal_id]
        groups.append(
            SequenceHypothesisGroup(
                group_id=_stable_id("ambiguous-phase-proposal", proposal.proposal_id),
                phase_interval_px=proposal.phase_interval_px,
                role_proposals=(proposal,),
                ambiguous_proposal_ids=(proposal.proposal_id,),
                exclusion_authorized=False,
            )
        )
    unique = {group.group_id: group for group in groups}
    ordered = tuple(unique[key] for key in sorted(unique))
    return ordered, SequenceGroupingWork(lookup_count, matched)
