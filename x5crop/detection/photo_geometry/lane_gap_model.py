"""Lane-owned normal-gap evidence and placement-pitch authority."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain import EvidenceState, FiniteInterval, ObservationId
from .interval_math import common
from .joint_axis_geometry import JointAxisGeometry
from .physical_identity import physical_fact_id


def _unique_strongest_compatible_indices(
    intervals: tuple[FiniteInterval, ...],
) -> frozenset[int]:
    """Return one uniquely strongest common interval group.

    Interval endpoints enumerate maximal one-dimensional overlap groups.  An
    equal-strength split stays unresolved instead of selecting by order.
    """

    overlap_groups = {
        frozenset(
            index
            for index, interval in enumerate(intervals)
            if interval.contains(coordinate)
        )
        for interval in intervals
        for coordinate in (interval.minimum, interval.maximum)
    }
    strongest_size = max((len(group) for group in overlap_groups), default=0)
    strongest = tuple(
        dict.fromkeys(
            group for group in overlap_groups if len(group) == strongest_size
        )
    )
    return strongest[0] if strongest_size >= 2 and len(strongest) == 1 else frozenset()


@dataclass(frozen=True)
class LaneGapModel:
    gap_model_id: str
    lane_id: str
    state: EvidenceState
    gap_interval_px: FiniteInterval | None
    direct_gap_proposals_px: tuple[FiniteInterval, ...]
    unresolved_gap_proposals_px: tuple[FiniteInterval, ...]
    supporting_observation_ids: tuple[ObservationId, ...]
    unresolved_observation_ids: tuple[ObservationId, ...]
    joint_width_geometry_id: str
    placement_pitch_interval_px: FiniteInterval | None
    canonical_placement_pitch_px: float | None

    @classmethod
    def from_ordinal_edges(
        cls,
        width_state: JointAxisGeometry,
        *,
        lane_id: str,
        edge_families: tuple[
            tuple[
                tuple[int, FiniteInterval, tuple[ObservationId, ...]], ...
            ], ...
        ],
        direct_separator_gaps: tuple[
            tuple[FiniteInterval, ObservationId], ...
        ],
    ) -> "LaneGapModel":
        if width_state.axis_name != "width" or not lane_id:
            raise ValueError("lane gap requires lane width geometry")
        width = width_state.extent_projection_px()
        proposals: list[
            tuple[FiniteInterval, tuple[ObservationId, ...], int]
        ] = []
        family_proposal_indices: list[tuple[int, ...]] = []
        for family in edge_families:
            indices: list[int] = []
            ordered = tuple(sorted(family, key=lambda item: item[0]))
            for left, right in zip(ordered, ordered[1:]):
                left_ordinal, left_interval, left_ids = left
                right_ordinal, right_interval, right_ids = right
                if right_ordinal != left_ordinal + 1:
                    continue
                indices.append(len(proposals))
                proposals.append(
                    (
                        FiniteInterval(
                            right_interval.minimum
                            - left_interval.maximum
                            - width.maximum,
                            right_interval.maximum
                            - left_interval.minimum
                            - width.minimum,
                        ),
                        tuple(
                            ObservationId(value)
                            for value in sorted(
                                {
                                    *(str(identity) for identity in left_ids),
                                    *(str(identity) for identity in right_ids),
                                }
                            )
                        ),
                        len(family_proposal_indices),
                    )
                )
            family_proposal_indices.append(tuple(indices))
        separator_proposal_indices: list[int] = []
        for interval, observation_id in direct_separator_gaps:
            separator_proposal_indices.append(len(proposals))
            proposals.append(
                (
                    interval,
                    (observation_id,),
                    len(edge_families),
                )
            )
        proposal_tuple = tuple(item[0] for item in proposals)

        # G_source needs at least two compatible pitch segments from the same
        # edge family.  Correlated START/END views may not be pooled to invent
        # two independent segments.  Contact and overlap remain local anomaly
        # evidence and never establish a negative normal gap.
        family_supported_indices: list[frozenset[int]] = []
        family_conflict = False
        for indices in family_proposal_indices:
            normal_indices = tuple(
                index
                for index in indices
                if proposal_tuple[index].minimum > 0.0
            )
            local_intervals = tuple(
                proposal_tuple[index] for index in normal_indices
            )
            if len(normal_indices) < 2:
                continue
            strongest = _unique_strongest_compatible_indices(local_intervals)
            if not strongest:
                family_conflict = True
            else:
                family_supported_indices.append(
                    frozenset(normal_indices[index] for index in strongest)
                )

        # Two distinct role-bound bands are also two direct g[i] segments.
        # Outliers stay in the unresolved ledger for possible local-advance
        # authority; they are not discarded or averaged.
        normal_separator_indices = tuple(
            index
            for index in separator_proposal_indices
            if proposal_tuple[index].minimum > 0.0
        )
        if len(normal_separator_indices) >= 2:
            separator_intervals = tuple(
                proposal_tuple[index]
                for index in normal_separator_indices
            )
            strongest = _unique_strongest_compatible_indices(
                separator_intervals
            )
            if not strongest:
                family_conflict = True
            else:
                family_supported_indices.append(
                    frozenset(
                        normal_separator_indices[index]
                        for index in strongest
                    )
                )

        supported_indices = frozenset(
            index
            for family_indices in family_supported_indices
            for index in family_indices
        )
        supported_proposals = tuple(
            proposal_tuple[index] for index in sorted(supported_indices)
        )
        common_gap = common(supported_proposals)
        if family_conflict or (supported_proposals and common_gap is None):
            # Conflicting samples leave G_source unresolved.  A fully direct
            # chain can still use every observed adjacency; only inference is
            # unauthorized.
            state = EvidenceState.UNAVAILABLE
            gap = None
            supported_indices = frozenset()
        elif supported_proposals and common_gap is not None:
            state = EvidenceState.SUPPORTED
            gap = common_gap
        elif len(proposal_tuple) == 1:
            # One segment is a proposal, never supported G_source.
            state = EvidenceState.UNAVAILABLE
            gap = proposal_tuple[0]
        else:
            state = EvidenceState.UNAVAILABLE
            gap = None
        unresolved_indices = tuple(
            index
            for index in range(len(proposal_tuple))
            if index not in supported_indices
        )
        supporting_observations = tuple(
            ObservationId(value)
            for value in sorted(
                {
                    str(identity)
                    for index in supported_indices
                    for identity in proposals[index][1]
                }
            )
        )
        unresolved_observations = tuple(
            ObservationId(value)
            for value in sorted(
                {
                    str(identity)
                    for index in unresolved_indices
                    for identity in proposals[index][1]
                }
            )
        )
        if state == EvidenceState.SUPPORTED and gap is not None:
            placement_pitch = FiniteInterval(
                width.minimum + gap.minimum,
                width.maximum + gap.maximum,
            )
            canonical = placement_pitch.center
        else:
            placement_pitch = None
            canonical = None
        encoded = "\x1f".join(
            (
                lane_id,
                state.value,
                *(value.minimum.hex() for value in proposal_tuple),
                *(value.maximum.hex() for value in proposal_tuple),
                *(str(value) for value in supporting_observations),
                *(str(value) for value in unresolved_observations),
            )
        ).encode("utf-8")
        return cls(
            gap_model_id=physical_fact_id("lane-gap", encoded.hex()),
            lane_id=lane_id,
            state=state,
            gap_interval_px=gap,
            direct_gap_proposals_px=proposal_tuple,
            unresolved_gap_proposals_px=tuple(
                proposal_tuple[index] for index in unresolved_indices
            ),
            supporting_observation_ids=supporting_observations,
            unresolved_observation_ids=unresolved_observations,
            joint_width_geometry_id=physical_fact_id(
                "joint-width-state",
                width_state.vertices,
                width_state.observation_ids,
            ),
            placement_pitch_interval_px=placement_pitch,
            canonical_placement_pitch_px=canonical,
        )

    def __post_init__(self) -> None:
        if (
            not self.gap_model_id
            or not self.lane_id
            or not self.joint_width_geometry_id
            or (self.state == EvidenceState.SUPPORTED) != (
                self.gap_interval_px is not None
                and len(self.direct_gap_proposals_px) >= 2
            )
            or (self.state == EvidenceState.SUPPORTED) != (
                self.placement_pitch_interval_px is not None
                and self.canonical_placement_pitch_px is not None
            )
            or (
                self.placement_pitch_interval_px is not None
                and not self.placement_pitch_interval_px.contains(
                    self.canonical_placement_pitch_px,
                    epsilon=1.0e-9,
                )
            )
            or len(set(self.supporting_observation_ids))
            != len(self.supporting_observation_ids)
            or len(set(self.unresolved_observation_ids))
            != len(self.unresolved_observation_ids)
            or len(self.unresolved_gap_proposals_px)
            > len(self.direct_gap_proposals_px)
        ):
            raise ValueError("lane gap model is invalid")
