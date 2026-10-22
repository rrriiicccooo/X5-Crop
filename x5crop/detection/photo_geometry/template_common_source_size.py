"""Independent native size evidence shared by every named interpretation."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum

from ...domain import EvidenceState, FiniteInterval, ObservationId
from .output_model import OutputBoundaryUse
from .source_geometry import SourceScanGeometry
from .template_cross import calibrate_source_frame_height
from .template_cross_model import CrossFitStatus
from .template_family_membership import MembershipState
from .template_frame_width import (
    DirectFrameWidthObservation, complete_frame_width_observations, independent_frame_width_pairs,
)


class CommonSourceSizeGap(str, Enum):
    MEMBER_EVIDENCE_UNAVAILABLE = "member_evidence_unavailable"
    INDEPENDENT_WIDTH_PAIRS_UNAVAILABLE = "independent_width_pairs_unavailable"
    INDEPENDENT_HEIGHT_PAIR_UNAVAILABLE = "independent_height_pair_unavailable"
    CONDITIONAL_SIZE_CONFLICT = "conditional_size_conflict"
    WORK_BOUND_EXCEEDED = "work_bound_exceeded"
    EMPTY_MEMBER_SET = "empty_member_set"


@dataclass(frozen=True)
class DirectFrameHeightObservation:
    observation_ids: tuple[ObservationId, ...]
    height_px: FiniteInterval

    def __post_init__(self) -> None:
        if (len(self.observation_ids) != 2 or len(set(self.observation_ids)) != 2
                or any(not isinstance(item, ObservationId) for item in self.observation_ids)
                or self.height_px.minimum <= 0):
            raise ValueError("common direct H requires two independent aperture boundaries")


@dataclass(frozen=True)
class CommonSourceSizeProof:
    member_keys: tuple[tuple[str, int], ...]
    placement_ids: tuple[str | None, ...]
    initial_source_geometry: SourceScanGeometry
    width_pairs: tuple[DirectFrameWidthObservation, ...]
    height_pair: DirectFrameHeightObservation | None
    conditional_extents: tuple[tuple[FiniteInterval, FiniteInterval] | None, ...]
    source_geometry: SourceScanGeometry | None
    gaps: tuple[CommonSourceSizeGap, ...]
    work_units: int
    state: EvidenceState = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "state", EvidenceState.SUPPORTED
            if self.source_geometry is not None and not self.gaps else EvidenceState.UNAVAILABLE)
        if ((not self.member_keys and self.gaps != (CommonSourceSizeGap.EMPTY_MEMBER_SET,))
                or self.member_keys and CommonSourceSizeGap.EMPTY_MEMBER_SET in self.gaps
                or len(set(self.member_keys)) != len(self.member_keys)
                or any(not scope or type(ordinal) is not int or ordinal < 0 for scope, ordinal in self.member_keys)
                or len(self.conditional_extents) != len(self.member_keys)
                or len(self.placement_ids) != len(self.member_keys)
                or self.initial_source_geometry.width_state.observation_ids
                or self.initial_source_geometry.height_state.observation_ids
                or len(set(self.width_pairs)) != len(self.width_pairs)
                or tuple(dict.fromkeys(self.gaps)) != self.gaps
                or any(not isinstance(item, CommonSourceSizeGap) for item in self.gaps)
                or type(self.work_units) is not int or self.work_units < 0
                or (self.source_geometry is None) != bool(self.gaps)):
            raise ValueError("common source size lost its complete named evidence set")
        if self.source_geometry is not None:
            if not independent_frame_width_pairs(self.width_pairs) or self.height_pair is None:
                raise ValueError("common source size requires independent native W/H measurements")
            expected = _source_from_measurements(self.initial_source_geometry, self.width_pairs, self.height_pair)
            expected = replace(expected, geometry_id=self.source_geometry.geometry_id)
            if expected != self.source_geometry:
                raise ValueError("common source size changed its native measurements")
            size = expected.fixed_output_size
            if any(extents is None or not extents[0].contains(size.frame_width_px, epsilon=1e-8)
                    or not extents[1].contains(size.frame_height_px, epsilon=1e-8)
                    for extents in self.conditional_extents):
                raise ValueError("common measured size contradicts a member's independent constraints")


def _source_from_measurements(initial, pairs, height):
    width = FiniteInterval(min(pair.width_px.minimum for pair in pairs),
                           max(pair.width_px.maximum for pair in pairs))
    ids = tuple(sorted({identity for pair in pairs
        for identity in (pair.start_observation_id, pair.end_observation_id)}, key=str))
    return SourceScanGeometry.from_axis_states(initial.frame_spec,
        initial.width_state.intersect_observed_extent(width, observation_ids=ids),
        initial.height_state.intersect_observed_extent(height.height_px, observation_ids=height.observation_ids))


def common_source_size_work_bound(phases, contexts, observation_count):
    """Compile work before raw-pair/H reconstruction; no new search or pixels.

    Each pair checks two bindings and native intervals. H and final source
    constructions have constant-size two-dimensional clipping domains. Both
    independent-pair checks are quadratic in the at-most count native pairs.
    """
    pair_bound = max((0 if phase is None else len(phase.best.role_bindings) // 2 for phase in phases), default=0)
    return (128 + 2 * len(phases) + 2 * pair_bound ** 2
        + sum(0 if phase is None else observation_count + 16 * len(phase.best.role_bindings) for phase in phases)
        + sum(0 if context is None else 128 + len(context.membership_scope_states) for context in contexts))


def unavailable_common_source_size(initial, member_keys, placement_ids):
    return CommonSourceSizeProof(tuple(member_keys), tuple(placement_ids), initial, (), None,
        (None,) * len(member_keys), None,
        (CommonSourceSizeGap.WORK_BOUND_EXCEEDED if member_keys else CommonSourceSizeGap.EMPTY_MEMBER_SET,), 0)


def prove_common_source_size(initial, member_keys, placement_ids, phases, contexts, observations) -> CommonSourceSizeProof:
    """Use identical native pairs, never an intersection of fitted W/H estimates.

    Every conditional state stays intact. Its narrower lattice or other Frame
    facts must admit the independently measured representative; incompatibility
    with any member withholds this proof instead of selecting another number.
    """
    if not (len(member_keys) == len(placement_ids) == len(phases) == len(contexts)):
        raise ValueError("common source size omitted a named interpretation")
    if not member_keys:
        return CommonSourceSizeProof((), (), initial, (), None, (), None,
                                     (CommonSourceSizeGap.EMPTY_MEMBER_SET,), 0)
    shared = None
    height = None
    height_complete = True
    missing = False
    extents = []
    work = common_source_size_work_bound(phases, contexts, len(observations))
    physical = initial.width_state.extent_projection_px()
    for phase, context in zip(phases, contexts, strict=True):
        if phase is None:
            pairs = set()
            missing = True
        else:
            measured, _ = complete_frame_width_observations(phase, observations, physical)
            pairs = {pair for _, pair in measured}
        shared = pairs if shared is None else shared & pairs
        if context is None:
            extents.append(None)
            missing = True
            height_complete = False
            continue
        source = context.source_scan_geometry
        extents.append((source.width_state.extent_projection_px(), source.height_state.extent_projection_px()))
        cross = context.competition
        fit = cross.best
        if (cross.status != CrossFitStatus.RESOLVED or fit is None or not fit.direct_pair
                or fit.height_compatibility_px is None
                or len(fit.bound_observation_ids) != 2
                or fit.boundary_use != OutputBoundaryUse.APERTURE_PAIR
                or not context.membership_projection_complete or not context.local_refinements_closed
                or context.membership_state != MembershipState.COMPLETE
                or any(state != MembershipState.COMPLETE for state in context.membership_scope_states)):
            height_complete = False
            continue
        # Recreate H from the initial state alone, without W-derived aspect H.
        try:
            direct = calibrate_source_frame_height(initial, cross)
        except ValueError:
            height_complete = False
            continue
        candidate = DirectFrameHeightObservation(fit.bound_observation_ids,
                                                 direct.height_state.extent_projection_px())
        if height is not None and candidate != height:
            height_complete = False
        height = candidate if height is None else height
    width_pairs = tuple(sorted(shared or (), key=lambda pair: (
        str(pair.start_observation_id), str(pair.end_observation_id))))
    if not height_complete:
        height = None
    gaps = []
    if missing:
        gaps.append(CommonSourceSizeGap.MEMBER_EVIDENCE_UNAVAILABLE)
    if not independent_frame_width_pairs(width_pairs):
        gaps.append(CommonSourceSizeGap.INDEPENDENT_WIDTH_PAIRS_UNAVAILABLE)
    if height is None:
        gaps.append(CommonSourceSizeGap.INDEPENDENT_HEIGHT_PAIR_UNAVAILABLE)
    source = None
    if not gaps:
        source = _source_from_measurements(initial, width_pairs, height)
        size = source.fixed_output_size
        if any(intervals is None or not intervals[0].contains(size.frame_width_px, epsilon=1e-8)
                or not intervals[1].contains(size.frame_height_px, epsilon=1e-8) for intervals in extents):
            gaps.append(CommonSourceSizeGap.CONDITIONAL_SIZE_CONFLICT)
            source = None
    return CommonSourceSizeProof(tuple(member_keys), tuple(placement_ids), initial, width_pairs, height, tuple(extents),
                                 source, tuple(gaps), work)
