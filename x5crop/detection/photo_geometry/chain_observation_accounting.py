"""Explain raw boundary observations against one complete physical chain."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ...domain import FiniteInterval, ObservationId
from .chains import CompleteFormatChain
from .interval_math import intersect
from .line_observations import PhotoBoundaryObservation
from .observation_spatial_index import ChainObservationSpatialIndex


class ObservationDisposition(str, Enum):
    DIRECT_ROLE_BOUND = "direct_role_bound"
    INFERRED_SUPPORT = "inferred_support"
    EXPLAINED_NON_BOUNDARY = "explained_non_boundary"
    CONTRADICTION = "contradiction"
    UNOBSERVABLE = "unobservable"


@dataclass(frozen=True)
class ChainObservationFact:
    observation_id: ObservationId
    disposition: ObservationDisposition
    roles: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if not self.reason or len(set(self.roles)) != len(self.roles):
            raise ValueError("chain observation fact is invalid")


@dataclass(frozen=True)
class ChainObservationAccounting:
    accounted_observation_ids: tuple[ObservationId, ...]
    facts: tuple[ChainObservationFact, ...] = ()


def _strictly_inside(interval: FiniteInterval, outer: FiniteInterval) -> bool:
    return (
        interval.minimum > outer.minimum
        and interval.maximum < outer.maximum
    )


def account_chain_observations(
    placement: CompleteFormatChain,
    observations: ChainObservationSpatialIndex,
    *,
    include_facts: bool,
) -> ChainObservationAccounting:
    """Return observations the placement actually explains.

    An unrelated line is not silently accepted.  It is accounted for only
    when it is role-bound, agrees with a retained boundary, or lies completely
    inside one fixed frame where it has an explicit non-boundary explanation.
    Other displaced observations remain unaccounted and can prevent dominance.
    """

    frames = placement.fixed_frames.frames
    direct_roles: dict[ObservationId, set[str]] = {}

    def bind(identity: ObservationId, *roles: str) -> None:
        direct_roles.setdefault(identity, set()).update(roles)

    for band in placement.sequence.separator_bands:
        relation = band.relation_ordinal
        bind(
            band.observation.observation_id,
            f"end[{relation}]",
            f"start[{relation + 1}]",
        )
        bind(band.observation.left_edge_observation_id, f"end[{relation}]")
        bind(
            band.observation.right_edge_observation_id,
            f"start[{relation + 1}]",
        )
    for item in placement.sequence.observations:
        if item.observation_id is not None:
            bind(
                item.observation_id,
                f"{item.role.role.value}[{item.role.lane_ordinal}]",
            )
    for item in placement.cross.evidence:
        bind(item.observation.observation_id, item.role.value)

    boundary_support: set[ObservationId] = set()
    explicit_internal: set[ObservationId] = set()
    explicit_outer_cross: set[ObservationId] = set()
    explicit_outer_sequence: set[ObservationId] = set()
    explained_composite_bands: set[ObservationId] = set()
    frame_sequence_interiors = tuple(
        FiniteInterval(
            frame.start.full_position_interval_px.maximum,
            frame.end.full_position_interval_px.minimum,
        )
        for frame in frames
        if frame.start.full_position_interval_px.maximum
        < frame.end.full_position_interval_px.minimum
    )
    for frame in frames:
        for boundary in (
            frame.start.full_position_interval_px,
            frame.end.full_position_interval_px,
        ):
            boundary_support.update(
                observations.edge_intervals.intersecting(boundary)
            )
    boundary_support.difference_update(direct_roles)
    for interior in frame_sequence_interiors:
        explicit_internal.update(
            observations.edge_intervals.strictly_inside(interior)
        )
    explicit_internal.difference_update(direct_roles)
    explicit_internal.difference_update(boundary_support)
    explicit_outer_sequence.update(
        observations.edge_intervals.entirely_before(
            frames[0].start.full_position_interval_px.minimum
        )
    )
    explicit_outer_sequence.update(
        observations.edge_intervals.entirely_after(
            frames[-1].end.full_position_interval_px.maximum
        )
    )
    # Count and ordinal authority close the selected fixed-frame chain.  An
    # isolated edge wholly outside it is an explicit holder/film/non-target
    # limit unless another complete W-sized chain binds it.
    explicit_outer_sequence.difference_update(direct_roles)
    explicit_outer_sequence.difference_update(boundary_support)
    explicit_outer_sequence.difference_update(explicit_internal)

    for band in observations.separator_bands:
        if band.observation_id in direct_roles:
            continue
        left = observations.edge_by_id.get(band.left_edge_observation_id)
        right = observations.edge_by_id.get(band.right_edge_observation_id)
        if left is None or right is None:
            continue
        band_interval = FiniteInterval(
            left.coordinate_interval_px.minimum,
            right.coordinate_interval_px.maximum,
        )
        if any(
            intersect(
                left.coordinate_interval_px,
                frames[ordinal - 1].end.full_position_interval_px,
            )
            is not None
            and intersect(
                right.coordinate_interval_px,
                frames[ordinal].start.full_position_interval_px,
            )
            is not None
            for ordinal in range(1, len(frames))
        ):
            boundary_support.add(band.observation_id)
        elif (
            intersect(
                right.coordinate_interval_px,
                frames[0].start.full_position_interval_px,
            )
            is not None
            and left.coordinate_interval_px.maximum
            <= frames[0].start.full_position_interval_px.maximum
        ) or (
            intersect(
                left.coordinate_interval_px,
                frames[-1].end.full_position_interval_px,
            )
            is not None
            and right.coordinate_interval_px.minimum
            >= frames[-1].end.full_position_interval_px.minimum
        ):
            # A dark material band can terminate at the first visible START or
            # begin at the last visible END of a partial strip.  It is not an
            # internal adjacency and therefore cannot create another slot.
            explicit_outer_sequence.add(band.observation_id)
        elif any(
            _strictly_inside(band_interval, interior)
            for interior in frame_sequence_interiors
        ):
            explicit_internal.add(band.observation_id)

    explained_edge_ids = (
        set(direct_roles) | boundary_support | explicit_internal
    )
    for band in observations.separator_bands:
        if band.observation_id in direct_roles:
            continue
        if {
            band.left_edge_observation_id,
            band.right_edge_observation_id,
        }.issubset(explained_edge_ids):
            # A band is derived from its two canonical edge observations.  If
            # both edges already have explicit roles (for example one true
            # frame boundary plus one image-interior line), recombining them
            # cannot become an additional independent competing observation.
            explained_composite_bands.add(band.observation_id)

    def cross_coordinate_at_trace(
        observation: PhotoBoundaryObservation,
        trace_coordinate_px: float,
    ) -> FiniteInterval:
        line = observation.line
        if line.source_axis_long.value == "x":
            normal = line.normal_y
            other = line.normal_x * trace_coordinate_px
        else:
            normal = line.normal_x
            other = line.normal_y * trace_coordinate_px
        values = tuple(
            (offset - other) / normal
            for offset in (
                observation.offset_interval_px.minimum,
                observation.offset_interval_px.maximum,
            )
        )
        return FiniteInterval(min(values), max(values))

    for observation in observations.top_bottom_observations:
        if observation.observation_id in direct_roles:
            continue
        outside_every_frame = True
        for frame in frames:
            coordinate = cross_coordinate_at_trace(
                observation,
                frame.top.reference_trace_px,
            )
            if (
                intersect(coordinate, frame.top.full_position_interval_px)
                is not None
                or intersect(coordinate, frame.bottom.full_position_interval_px)
                is not None
            ):
                boundary_support.add(observation.observation_id)
                outside_every_frame = False
                break
            interior = FiniteInterval(
                frame.top.full_position_interval_px.maximum,
                frame.bottom.full_position_interval_px.minimum,
            )
            if interior.minimum < interior.maximum and _strictly_inside(
                coordinate,
                interior,
            ):
                explicit_internal.add(observation.observation_id)
                outside_every_frame = False
                break
            if not (
                coordinate.maximum
                < frame.top.full_position_interval_px.minimum
                or coordinate.minimum
                > frame.bottom.full_position_interval_px.maximum
            ):
                outside_every_frame = False
        if outside_every_frame:
            # A repeated line wholly outside the selected fixed-H rectangles
            # is explicitly explained as a holder/film visible limit.  The
            # negative-only content layer still vetoes the smaller pair if
            # recoverable picture content crosses it.
            explicit_outer_cross.add(observation.observation_id)

    accounted = tuple(
        sorted(
            set(direct_roles)
            | boundary_support
            | explicit_internal
            | explicit_outer_cross
            | explicit_outer_sequence
            | explained_composite_bands,
            key=str,
        )
    )
    if not include_facts:
        return ChainObservationAccounting(accounted)

    facts: list[ChainObservationFact] = []
    for identity in observations.raw_observation_ids:
        if identity in direct_roles:
            facts.append(
                ChainObservationFact(
                    identity,
                    ObservationDisposition.DIRECT_ROLE_BOUND,
                    tuple(sorted(direct_roles[identity])),
                    "observation is bound to a physical boundary role",
                )
            )
        elif identity in boundary_support:
            facts.append(
                ChainObservationFact(
                    identity,
                    ObservationDisposition.INFERRED_SUPPORT,
                    (),
                    "observation agrees with a propagated boundary",
                )
            )
        elif identity in (
            explicit_internal
            | explicit_outer_cross
            | explicit_outer_sequence
            | explained_composite_bands
        ):
            facts.append(
                ChainObservationFact(
                    identity,
                    ObservationDisposition.EXPLAINED_NON_BOUNDARY,
                    (),
                    (
                        "observation lies inside one fixed-format frame"
                        if identity in explicit_internal
                        else (
                            "observation is outside the first or last slot"
                            if identity in explicit_outer_sequence
                            else (
                                "band reuses two already explained edge observations"
                                if identity in explained_composite_bands
                                else "observation is an outer holder or film limit"
                            )
                        )
                    ),
                )
            )
        else:
            facts.append(
                ChainObservationFact(
                    identity,
                    ObservationDisposition.UNOBSERVABLE,
                    (),
                    "placement does not explain this displaced observation",
                )
            )
    return ChainObservationAccounting(accounted, tuple(facts))
