from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from functools import cached_property
from hashlib import sha256
import math
from types import MappingProxyType

import numpy as np

from ...configuration.photo_edges import PhotoEdgeDetectionParameters
from ...domain import (
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
)
from ..evidence.photo_edges import (
    LocalTransitionState,
    PhotoEdgeMeasurementSummary,
    PhotoEdgeObservation,
    PhotoEdgeSearchCorridor,
    PhotoEdgeSideStatistics,
    fragment_constraint_hash,
)


_HALF_PIXEL_POSITION_ENVELOPE = 0.5
_EVEN_DIVISOR = 2
_PREFIX_WORKING_BUFFER_COUNT = 2


@dataclass(frozen=True)
class PhotoEdgeRidgeNode:
    node_id: ObservationId
    observation: PhotoEdgeObservation

    def __post_init__(self) -> None:
        if self.node_id != self.observation.observation_id:
            raise ValueError(
                "photo-edge ridge node identity must match its observation"
            )


@dataclass(frozen=True, order=True)
class PhotoEdgeRidgeEdge:
    source_node_id: ObservationId
    target_node_id: ObservationId

    def __post_init__(self) -> None:
        if self.source_node_id == self.target_node_id:
            raise ValueError("photo-edge ridge edges cannot be self-referential")


@dataclass(frozen=True)
class PhotoEdgeFragment:
    fragment_id: ObservationId
    node_ids: tuple[ObservationId, ...]

    def __post_init__(self) -> None:
        if not self.node_ids:
            raise ValueError("photo-edge fragments require ridge node references")
        if len(set(self.node_ids)) != len(self.node_ids):
            raise ValueError("photo-edge fragment node references must be unique")


@dataclass(frozen=True)
class PhotoEdgeRidgeGraph:
    nodes: tuple[PhotoEdgeRidgeNode, ...]
    edges: tuple[PhotoEdgeRidgeEdge, ...]

    def __post_init__(self) -> None:
        node_ids = tuple(node.node_id for node in self.nodes)
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("photo-edge ridge graph node identities must be unique")
        if any(
            node.observation.state != LocalTransitionState.SUPPORTED
            for node in self.nodes
        ):
            raise ValueError(
                "photo-edge ridge graph contains unsupported observations"
            )
        if tuple(
            sorted(
                self.nodes,
                key=lambda node: (
                    node.observation.long_axis_footprint.minimum,
                    node.observation.short_axis_position_interval.minimum,
                    str(node.node_id),
                ),
            )
        ) != self.nodes:
            raise ValueError("photo-edge ridge graph nodes must be ordered")
        if len(set(self.edges)) != len(self.edges):
            raise ValueError("photo-edge ridge graph edges must be unique")
        node_map = {node.node_id: node for node in self.nodes}
        for edge in self.edges:
            if (
                edge.source_node_id not in node_map
                or edge.target_node_id not in node_map
            ):
                raise ValueError(
                    "photo-edge ridge graph edges require existing nodes"
                )
            source = node_map[edge.source_node_id].observation
            target = node_map[edge.target_node_id].observation
            if (
                target.long_axis_footprint.minimum
                <= source.long_axis_footprint.minimum
            ):
                raise ValueError(
                    "photo-edge ridge graph edges must advance the long axis"
                )
            if (
                target.long_axis_footprint.minimum
                > source.long_axis_footprint.maximum
            ):
                raise ValueError(
                    "photo-edge ridge graph edges cannot bridge observation gaps"
                )
            if not source.short_axis_position_interval.intersects(
                target.short_axis_position_interval
            ):
                raise ValueError(
                    "photo-edge ridge graph edges require direct position support"
                )

    @cached_property
    def node_map(self) -> Mapping[ObservationId, PhotoEdgeRidgeNode]:
        return MappingProxyType(
            {node.node_id: node for node in self.nodes}
        )

    @cached_property
    def _edge_pairs(
        self,
    ) -> frozenset[tuple[ObservationId, ObservationId]]:
        return frozenset(
            (edge.source_node_id, edge.target_node_id)
            for edge in self.edges
        )

    @cached_property
    def path_count(self) -> int:
        if not self.nodes:
            return 0
        outgoing = self._outgoing_nodes
        incoming = self._incoming_nodes
        counts: dict[ObservationId, int] = {}
        for node in reversed(self.nodes):
            targets = outgoing[node.node_id]
            counts[node.node_id] = (
                1
                if not targets
                else sum(counts[target] for target in targets)
            )
        return sum(
            counts[node.node_id]
            for node in self.nodes
            if not incoming[node.node_id]
        )

    def observations_for(
        self,
        fragment: PhotoEdgeFragment,
    ) -> tuple[PhotoEdgeObservation, ...]:
        node_map = self.node_map
        try:
            observations = tuple(
                node_map[node_id].observation
                for node_id in fragment.node_ids
            )
        except KeyError as exc:
            raise ValueError(
                "photo-edge fragment references a node outside its graph"
            ) from exc
        if any(
            pair not in self._edge_pairs
            for pair in zip(
                fragment.node_ids,
                fragment.node_ids[1:],
                strict=False,
            )
        ):
            raise ValueError(
                "photo-edge fragment is not a legal ridge-graph path"
            )
        incoming = self._incoming_nodes
        outgoing = self._outgoing_nodes
        if (
            incoming[fragment.node_ids[0]]
            or outgoing[fragment.node_ids[-1]]
        ):
            raise ValueError(
                "photo-edge fragments must be complete source-to-sink paths"
            )
        if any(
            observations[index].long_axis_footprint.minimum
            >= observations[index + 1].long_axis_footprint.minimum
            for index in range(len(observations) - 1)
        ):
            raise ValueError("photo-edge fragment node order is not monotone")
        return observations

    def long_axis_footprint(
        self,
        fragment: PhotoEdgeFragment,
    ) -> PixelInterval:
        observations = self.observations_for(fragment)
        return PixelInterval(
            min(item.long_axis_footprint.minimum for item in observations),
            max(item.long_axis_footprint.maximum for item in observations),
        )

    def short_axis_position_interval(
        self,
        fragment: PhotoEdgeFragment,
    ) -> PixelInterval:
        observations = self.observations_for(fragment)
        return PixelInterval(
            min(
                item.short_axis_position_interval.minimum
                for item in observations
            ),
            max(
                item.short_axis_position_interval.maximum
                for item in observations
            ),
        )

    def fragment_is_censored(self, fragment: PhotoEdgeFragment) -> bool:
        return any(
            observation.censored
            for observation in self.observations_for(fragment)
        )

    def fragment_constraint_sha256(
        self,
        fragment: PhotoEdgeFragment,
    ) -> str:
        return fragment_constraint_hash(self.observations_for(fragment))

    def iter_fragments(self, observation_prefix: str) -> Iterator[PhotoEdgeFragment]:
        outgoing = self._outgoing_nodes
        incoming = self._incoming_nodes
        sources = tuple(
            sorted(
                (
                    node.node_id
                    for node in self.nodes
                    if not incoming[node.node_id]
                ),
                key=str,
            )
        )
        stack: list[tuple[ObservationId, tuple[ObservationId, ...]]] = [
            (source, (source,))
            for source in reversed(sources)
        ]
        while stack:
            node_id, path = stack.pop()
            targets = outgoing[node_id]
            if not targets:
                digest = sha256(
                    "|".join(str(identity) for identity in path).encode("utf-8")
                ).hexdigest()[:16]
                yield PhotoEdgeFragment(
                    fragment_id=ObservationId(
                        f"{observation_prefix}:fragment:{digest}"
                    ),
                    node_ids=path,
                )
                continue
            for target in reversed(targets):
                stack.append((target, (*path, target)))

    @cached_property
    def _outgoing_nodes(
        self,
    ) -> Mapping[ObservationId, tuple[ObservationId, ...]]:
        values: dict[ObservationId, list[ObservationId]] = {
            node.node_id: [] for node in self.nodes
        }
        for edge in self.edges:
            values[edge.source_node_id].append(edge.target_node_id)
        return MappingProxyType(
            {
                node_id: tuple(sorted(targets, key=str))
                for node_id, targets in values.items()
            }
        )

    @cached_property
    def _incoming_nodes(
        self,
    ) -> Mapping[ObservationId, tuple[ObservationId, ...]]:
        values: dict[ObservationId, list[ObservationId]] = {
            node.node_id: [] for node in self.nodes
        }
        for edge in self.edges:
            values[edge.target_node_id].append(edge.source_node_id)
        return MappingProxyType(
            {
                node_id: tuple(sorted(sources, key=str))
                for node_id, sources in values.items()
            }
        )


@dataclass(frozen=True)
class PhotoEdgeObservationResult:
    graph: PhotoEdgeRidgeGraph
    summary: PhotoEdgeMeasurementSummary


@dataclass(frozen=True)
class _ChannelScaleSupport:
    channel: str
    scale: float
    depth: int
    position: float
    support_interval: PixelInterval
    effect: float
    local_noise: float
    censored: bool

    @property
    def identity(self) -> tuple[object, ...]:
        return (
            self.channel,
            self.scale,
            self.depth,
            self.support_interval.minimum,
            self.support_interval.maximum,
        )


@dataclass(frozen=True)
class _AnchorTransition:
    long_axis_footprint: PixelInterval
    position_interval: PixelInterval
    negative: PhotoEdgeSideStatistics
    positive: PhotoEdgeSideStatistics
    intensity_effect: float
    texture_effect: float
    gradient_effect: float
    local_noise: float
    channels: tuple[str, ...]
    scales: tuple[float, ...]
    censored: bool


@dataclass(frozen=True)
class _MeasurementDomain:
    interval: PixelInterval
    uncensored_interval: PixelInterval | None


@dataclass(frozen=True)
class _ChunkAnchorProfiles:
    starts: tuple[int, ...]
    intensity: np.ndarray
    texture: np.ndarray
    gradient: np.ndarray
    temporary_buffer_upper_bound_bytes: int


def _rolling_mean(values: np.ndarray, width: int) -> np.ndarray:
    if width <= 0 or width > values.shape[0]:
        raise ValueError("rolling mean requires a valid width")
    cumulative = np.concatenate(
        (np.zeros(1, dtype=np.float64), np.cumsum(values, dtype=np.float64))
    )
    return (cumulative[width:] - cumulative[:-width]) / float(width)


def _deterministic_median(values: np.ndarray) -> float:
    ordered = np.sort(np.ravel(values))
    midpoint = ordered.shape[0] // _EVEN_DIVISOR
    if ordered.shape[0] % _EVEN_DIVISOR:
        return float(ordered[midpoint])
    return 0.5 * float(ordered[midpoint - 1] + ordered[midpoint])


def _local_noise_at_positions(
    values: np.ndarray,
    positions: np.ndarray,
    depth: int,
    floor: float,
) -> np.ndarray:
    if positions.size == 0:
        return np.empty(0, dtype=np.float64)
    if depth <= 1:
        return np.full(positions.shape, floor, dtype=np.float64)
    differences = np.abs(np.diff(values))
    offsets = np.arange(depth - 1, dtype=np.int64)
    left = differences[
        positions[:, None] - depth + offsets[None, :]
    ]
    right = differences[
        positions[:, None] + offsets[None, :]
    ]

    def row_mad(windows: np.ndarray) -> np.ndarray:
        medians = np.median(windows, axis=1)
        return np.median(
            np.abs(windows - medians[:, None]),
            axis=1,
        )

    return np.maximum(
        floor,
        np.maximum(row_mad(left), row_mad(right)),
    )


def _side_statistics(
    intensities: np.ndarray,
    textures: np.ndarray,
    gradients: np.ndarray,
) -> PhotoEdgeSideStatistics:
    median = _deterministic_median(intensities)
    return PhotoEdgeSideStatistics(
        intensity_median_u8=median,
        intensity_mad_u8=_deterministic_median(
            np.abs(intensities - median)
        ),
        texture_median_u8=_deterministic_median(textures),
        gradient_median_u8=_deterministic_median(gradients),
    )


def _window_means(
    values: np.ndarray,
    starts: np.ndarray,
    width: int,
) -> np.ndarray:
    prefix = np.concatenate(
        (
            np.zeros((values.shape[0], 1), dtype=np.float64),
            np.cumsum(values, axis=1, dtype=np.float64),
        ),
        axis=1,
    )
    return (
        prefix[:, starts + width] - prefix[:, starts]
    ) / float(width)


def _chunk_anchor_profiles(
    gray_work: np.ndarray,
    starts: tuple[int, ...],
    support_width: int,
) -> _ChunkAnchorProfiles:
    if not starts:
        return _ChunkAnchorProfiles(
            starts=(),
            intensity=np.empty((gray_work.shape[0], 0), dtype=np.float64),
            texture=np.empty((gray_work.shape[0], 0), dtype=np.float64),
            gradient=np.empty((gray_work.shape[0], 0), dtype=np.float64),
            temporary_buffer_upper_bound_bytes=0,
        )
    read_start = starts[0]
    read_end = starts[-1] + support_width
    chunk_u8 = gray_work[:, read_start:read_end]
    chunk = chunk_u8.astype(np.float64)
    relative_starts = np.asarray(starts, dtype=np.int64) - read_start
    intensity = _window_means(
        chunk,
        relative_starts,
        support_width,
    )
    squared_mean = _window_means(
        chunk * chunk,
        relative_starts,
        support_width,
    )
    texture = np.sqrt(
        np.maximum(0.0, squared_mean - intensity * intensity)
    )
    if support_width > 1:
        horizontal_gradient = _window_means(
            np.abs(np.diff(chunk, axis=1)),
            relative_starts,
            support_width - 1,
        )
    else:
        horizontal_gradient = np.zeros_like(intensity)
    vertical_values = np.empty_like(chunk)
    vertical_values[0] = 0.0
    vertical_values[1:] = np.abs(np.diff(chunk, axis=0))
    vertical_gradient = _window_means(
        vertical_values,
        relative_starts,
        support_width,
    )
    gradient = np.maximum(horizontal_gradient, vertical_gradient)
    retained_bytes = sum(
        array.nbytes
        for array in (
            chunk_u8,
            chunk,
            intensity,
            squared_mean,
            texture,
            horizontal_gradient,
            vertical_values,
            vertical_gradient,
            gradient,
        )
    )
    prefix_upper_bound = _PREFIX_WORKING_BUFFER_COUNT * (
        chunk.shape[0] * (chunk.shape[1] + 1) * np.dtype(np.float64).itemsize
    )
    return _ChunkAnchorProfiles(
        starts=starts,
        intensity=intensity,
        texture=texture,
        gradient=gradient,
        temporary_buffer_upper_bound_bytes=(
            retained_bytes + prefix_upper_bound
        ),
    )


def _candidate_domains_at(
    coordinate: float,
    corridors: tuple[PhotoEdgeSearchCorridor, ...],
) -> tuple[PixelInterval, ...]:
    intervals = tuple(
        corridor.side_interval_at(coordinate, top=top)
        for corridor in corridors
        for top in (True, False)
    )
    if not intervals:
        return ()
    ordered = sorted(intervals)
    merged: list[PixelInterval] = []
    for interval in ordered:
        if not merged or interval.minimum > merged[-1].maximum:
            merged.append(interval)
        else:
            merged[-1] = PixelInterval(
                merged[-1].minimum,
                max(merged[-1].maximum, interval.maximum),
            )
    return tuple(merged)


def _measurement_domain(
    intervals: tuple[PixelInterval, ...],
    short_extent: int,
    halo: int,
) -> tuple[_MeasurementDomain, ...]:
    canvas = PixelInterval(0.0, float(short_extent - 1))
    domains: list[_MeasurementDomain] = []
    for interval in intervals:
        requested = PixelInterval(
            interval.minimum - float(halo),
            interval.maximum + float(halo),
        )
        measured = requested.intersection(canvas)
        if measured is not None:
            uncensored_minimum = (
                measured.minimum + float(halo)
                if requested.minimum < canvas.minimum
                else measured.minimum
            )
            uncensored_maximum = (
                measured.maximum - float(halo)
                if requested.maximum > canvas.maximum
                else measured.maximum
            )
            domains.append(
                _MeasurementDomain(
                    measured,
                    (
                        None
                        if uncensored_maximum < uncensored_minimum
                        else PixelInterval(
                            uncensored_minimum,
                            uncensored_maximum,
                        )
                    ),
                )
            )
    if not domains:
        return ()
    return tuple(sorted(domains, key=lambda item: item.interval))


def _channel_supports_for_scale(
    row_intensity: np.ndarray,
    row_texture: np.ndarray,
    row_gradient: np.ndarray,
    domains: tuple[_MeasurementDomain, ...],
    depth: int,
    scale: float,
    parameters: PhotoEdgeDetectionParameters,
) -> tuple[_ChannelScaleSupport, ...]:
    short_extent = row_intensity.shape[0]
    if 2 * depth + 1 >= short_extent:
        return ()
    candidate_positions = np.arange(
        depth,
        short_extent - depth + 1,
        dtype=np.int64,
    )
    expected = candidate_positions.shape[0]
    domain_mask = np.zeros(expected, dtype=bool)
    for domain in domains:
        domain_mask |= (
            (
                candidate_positions
                >= math.floor(domain.interval.minimum)
            )
            & (
                candidate_positions
                <= math.ceil(domain.interval.maximum)
            )
        )
    supports: list[_ChannelScaleSupport] = []
    for channel, profile in (
        ("gradient", row_gradient),
        ("intensity", row_intensity),
        ("texture", row_texture),
    ):
        rolling_mean = _rolling_mean(profile, depth)
        negative = rolling_mean[: -depth][:expected]
        positive = rolling_mean[depth:][:expected]
        effects = np.abs(positive - negative)
        eligible_indices = np.flatnonzero(
            (
                effects
                >= (
                    parameters.minimum_local_effect
                    + parameters.local_noise_floor_u8
                )
            )
            & domain_mask
        )
        eligible_positions = candidate_positions[eligible_indices]
        local_noise_values = _local_noise_at_positions(
            profile,
            eligible_positions,
            depth,
            parameters.local_noise_floor_u8,
        )
        supported_indices = eligible_indices[
            effects[eligible_indices]
            >= parameters.minimum_local_effect + local_noise_values
        ]
        components = tuple(
            component
            for component in np.split(
                supported_indices,
                np.flatnonzero(np.diff(supported_indices) > 1) + 1,
            )
            if component.size
        )
        for component in components:
            representative_index = min(
                (int(index) for index in component),
                key=lambda index: (
                    -float(effects[index]),
                    int(candidate_positions[index]),
                ),
            )
            position = int(candidate_positions[representative_index])
            support_interval = PixelInterval(
                float(candidate_positions[int(component[0])])
                - _HALF_PIXEL_POSITION_ENVELOPE,
                float(candidate_positions[int(component[-1])])
                + _HALF_PIXEL_POSITION_ENVELOPE,
            )
            containing_domains = tuple(
                domain
                for domain in domains
                if domain.interval.intersects(support_interval)
            )
            censored = not any(
                domain.uncensored_interval is not None
                and (
                    support_interval.minimum
                    > domain.uncensored_interval.minimum
                )
                and (
                    support_interval.maximum
                    < domain.uncensored_interval.maximum
                )
                for domain in containing_domains
            )
            supports.append(
                _ChannelScaleSupport(
                    channel=channel,
                    scale=scale,
                    depth=depth,
                    position=float(position),
                    support_interval=support_interval,
                    effect=float(effects[representative_index]),
                    local_noise=float(
                        local_noise_values[
                            np.searchsorted(
                                eligible_indices,
                                representative_index,
                            )
                        ]
                    ),
                    censored=censored,
                )
            )
    return tuple(supports)


def _group_channel_scale_supports(
    supports: tuple[_ChannelScaleSupport, ...],
    row_intensity: np.ndarray,
    row_texture: np.ndarray,
    row_gradient: np.ndarray,
    base_depth: int,
    minimum_scales: int,
    position_tolerance_ratio: float,
    footprint: PixelInterval,
) -> tuple[tuple[_AnchorTransition, ...], int]:
    if not supports:
        return (), 0
    tolerance = max(
        1.0,
        position_tolerance_ratio * float(base_depth),
    )
    groups: list[list[_ChannelScaleSupport]] = []
    common_support: list[PixelInterval] = []
    support_identities: set[tuple[object, ...]] = set()
    duplicate_identity_count = 0
    for support in sorted(
        supports,
        key=lambda item: (
            item.support_interval.midpoint,
            item.identity,
            item.position,
        ),
    ):
        if support.identity in support_identities:
            duplicate_identity_count += 1
            continue
        support_identities.add(support.identity)
        if not groups:
            groups.append([support])
            common_support.append(support.support_interval)
            continue
        current = groups[-1]
        shared = common_support[-1].intersection(
            support.support_interval
        )
        if (
            shared is not None
            and (
                max(
                    support.position,
                    *(item.position for item in current),
                )
                - min(
                    support.position,
                    *(item.position for item in current),
                )
                <= tolerance
            )
        ):
            current.append(support)
            common_support[-1] = shared
        else:
            groups.append([support])
            common_support.append(support.support_interval)
    transitions: list[_AnchorTransition] = []
    merged_duplicate_count = duplicate_identity_count
    for group in groups:
        scales = tuple(sorted({item.scale for item in group}))
        if len(scales) < minimum_scales:
            continue
        merged_duplicate_count += max(0, len(group) - 1)
        interval = PixelInterval(
            min(item.support_interval.minimum for item in group),
            max(item.support_interval.maximum for item in group),
        )
        representative = min(
            group,
            key=lambda item: (
                abs(item.scale - 1.0),
                item.channel,
                item.position,
            ),
        )
        position = int(round(representative.position))
        negative_slice = slice(
            position - representative.depth,
            position,
        )
        positive_slice = slice(
            position,
            position + representative.depth,
        )
        transitions.append(
            _AnchorTransition(
                long_axis_footprint=footprint,
                position_interval=interval,
                negative=_side_statistics(
                    row_intensity[negative_slice],
                    row_texture[negative_slice],
                    row_gradient[negative_slice],
                ),
                positive=_side_statistics(
                    row_intensity[positive_slice],
                    row_texture[positive_slice],
                    row_gradient[positive_slice],
                ),
                intensity_effect=max(
                    (
                        item.effect
                        for item in group
                        if item.channel == "intensity"
                    ),
                    default=0.0,
                ),
                texture_effect=max(
                    (
                        item.effect
                        for item in group
                        if item.channel == "texture"
                    ),
                    default=0.0,
                ),
                gradient_effect=max(
                    (
                        item.effect
                        for item in group
                        if item.channel == "gradient"
                    ),
                    default=0.0,
                ),
                local_noise=max(item.local_noise for item in group),
                channels=tuple(
                    sorted({item.channel for item in group})
                ),
                scales=scales,
                censored=any(item.censored for item in group),
            )
        )
    return tuple(transitions), merged_duplicate_count


def _anchor_transitions(
    row_intensity: np.ndarray,
    row_texture: np.ndarray,
    row_gradient: np.ndarray,
    start: int,
    end: int,
    corridors: tuple[PhotoEdgeSearchCorridor, ...],
    parameters: PhotoEdgeDetectionParameters,
) -> tuple[tuple[_AnchorTransition, ...], int]:
    center = 0.5 * float(start + end - 1)
    proposal_domains = (
        _candidate_domains_at(center, corridors)
        if corridors
        else (PixelInterval(0.0, float(row_intensity.shape[0] - 1)),)
    )
    base_depth = max(
        parameters.local_window_min_px,
        int(round(row_intensity.shape[0] * parameters.local_window_height_ratio)),
    )
    maximum_depth = max(
        parameters.local_window_min_px,
        int(round(base_depth * max(parameters.multiscale_factors))),
    )
    domains = _measurement_domain(
        proposal_domains,
        row_intensity.shape[0],
        maximum_depth + 1,
    )
    scale_by_depth: dict[int, float] = {}
    for scale in parameters.multiscale_factors:
        depth = max(
            parameters.local_window_min_px,
            int(round(base_depth * scale)),
        )
        scale_by_depth.setdefault(depth, scale)
    supports = tuple(
        support
        for depth, scale in sorted(scale_by_depth.items())
        for support in _channel_supports_for_scale(
            row_intensity,
            row_texture,
            row_gradient,
            domains,
            depth,
            scale,
            parameters,
        )
    )
    transitions, duplicate_count = _group_channel_scale_supports(
        supports,
        row_intensity,
        row_texture,
        row_gradient,
        base_depth,
        parameters.minimum_supporting_scales,
        parameters.multiscale_position_tolerance_ratio,
        PixelInterval(float(start), float(end - 1)),
    )
    return transitions, duplicate_count


def _transition_observation(
    transition: _AnchorTransition,
    source_sha256: str,
    observation_prefix: str,
) -> PhotoEdgeObservation:
    identity_payload = (
        f"{transition.long_axis_footprint.minimum:.16g}|"
        f"{transition.long_axis_footprint.maximum:.16g}|"
        f"{transition.position_interval.minimum:.16g}|"
        f"{transition.position_interval.maximum:.16g}|"
        f"{transition.intensity_effect:.16g}|"
        f"{transition.texture_effect:.16g}|"
        f"{transition.gradient_effect:.16g}|"
        f"{transition.local_noise:.16g}|"
        f"{','.join(transition.channels)}|"
        f"{','.join(f'{scale:.16g}' for scale in transition.scales)}|"
        f"{int(transition.censored)}"
    )
    digest = sha256(identity_payload.encode("utf-8")).hexdigest()[:20]
    observation_id = ObservationId(
        f"{observation_prefix}:ridge_node:{digest}"
    )
    return PhotoEdgeObservation(
        observation_id=observation_id,
        source_sha256=source_sha256,
        long_axis_footprint=transition.long_axis_footprint,
        short_axis_position_interval=transition.position_interval,
        negative_side_statistics=transition.negative,
        positive_side_statistics=transition.positive,
        absolute_intensity_effect=transition.intensity_effect,
        absolute_texture_effect=transition.texture_effect,
        absolute_gradient_effect=transition.gradient_effect,
        local_noise_u8=transition.local_noise,
        multiscale_position_interval=transition.position_interval,
        state=LocalTransitionState.SUPPORTED,
        measurement_channels=transition.channels,
        measurement_scales=transition.scales,
        censored=transition.censored,
        provenance=MeasurementProvenance(
            root_measurement=MeasurementIdentity.PHOTO_EDGES,
            observation_id=observation_id,
            dependencies=(MeasurementIdentity.GRAY_WORK,),
            description="channel-local multiscale photo-edge transition",
        ),
    )


def _ridge_graph(
    transitions: tuple[_AnchorTransition, ...],
    source_sha256: str,
    observation_prefix: str,
    anchor_stride: int,
) -> PhotoEdgeRidgeGraph:
    observations = {
        observation.observation_id: observation
        for observation in (
            _transition_observation(
                transition,
                source_sha256,
                observation_prefix,
            )
            for transition in transitions
        )
    }
    nodes = tuple(
        PhotoEdgeRidgeNode(
            node_id=observation.observation_id,
            observation=observation,
        )
        for observation in sorted(
            observations.values(),
            key=lambda item: (
                item.long_axis_footprint.minimum,
                item.short_axis_position_interval.minimum,
                str(item.observation_id),
            ),
        )
    )
    by_start: dict[float, list[PhotoEdgeRidgeNode]] = {}
    for node in nodes:
        by_start.setdefault(
            node.observation.long_axis_footprint.minimum,
            [],
        ).append(node)
    edges: set[PhotoEdgeRidgeEdge] = set()
    for start, source_nodes in by_start.items():
        target_nodes = by_start.get(start + float(anchor_stride), ())
        target_minima = tuple(
            node.observation.short_axis_position_interval.minimum
            for node in target_nodes
        )
        prefix_maxima: list[float] = []
        for target in target_nodes:
            maximum = (
                target.observation.short_axis_position_interval.maximum
            )
            prefix_maxima.append(
                maximum
                if not prefix_maxima
                else max(prefix_maxima[-1], maximum)
            )
        for source in source_nodes:
            source_interval = (
                source.observation.short_axis_position_interval
            )
            upper = bisect_right(target_minima, source_interval.maximum)
            lower = bisect_left(
                prefix_maxima,
                source_interval.minimum,
                0,
                upper,
            )
            for target in target_nodes[lower:upper]:
                if (
                    target.observation.short_axis_position_interval.maximum
                    >= source_interval.minimum
                ):
                    edges.add(
                        PhotoEdgeRidgeEdge(
                            source.node_id,
                            target.node_id,
                        )
                    )
    return PhotoEdgeRidgeGraph(
        nodes=nodes,
        edges=tuple(sorted(edges)),
    )


def _censored_component_count(graph: PhotoEdgeRidgeGraph) -> int:
    if not graph.nodes:
        return 0
    adjacent = {
        node.node_id: set[ObservationId]() for node in graph.nodes
    }
    node_map = graph.node_map
    for edge in graph.edges:
        adjacent[edge.source_node_id].add(edge.target_node_id)
        adjacent[edge.target_node_id].add(edge.source_node_id)
    unseen = set(adjacent)
    count = 0
    while unseen:
        start = min(unseen, key=str)
        component: set[ObservationId] = set()
        pending = [start]
        while pending:
            node_id = pending.pop()
            if node_id not in unseen:
                continue
            unseen.remove(node_id)
            component.add(node_id)
            pending.extend(
                sorted(adjacent[node_id] & unseen, key=str, reverse=True)
            )
        if any(node_map[node_id].observation.censored for node_id in component):
            count += 1
    return count


def observe_photo_edge_ridge_graph(
    gray_work: np.ndarray,
    corridors: tuple[PhotoEdgeSearchCorridor, ...],
    parameters: PhotoEdgeDetectionParameters,
    *,
    source_sha256: str,
    observation_prefix: str,
) -> PhotoEdgeObservationResult:
    if gray_work.ndim != 2 or gray_work.dtype != np.uint8:
        raise ValueError(
            "photo-edge observation requires canonical base_gray_u8"
        )
    if (
        len(source_sha256) != 64
        or any(character not in "0123456789abcdef" for character in source_sha256)
    ):
        raise ValueError("photo-edge observation requires a source SHA-256")
    width = gray_work.shape[1]
    transitions: list[_AnchorTransition] = []
    raw_anchor_count = 0
    neutral_anchor_count = 0
    merged_duplicate_count = 0
    peak_buffer_bytes = 0
    for chunk_start in range(0, width, parameters.chunk_size_px):
        chunk_end = min(width, chunk_start + parameters.chunk_size_px)
        anchor_start = (
            chunk_start
            if chunk_start == 0
            else max(0, chunk_start - parameters.long_support_width_px)
        )
        first = (
            (
                anchor_start + parameters.long_anchor_stride_px - 1
            )
            // parameters.long_anchor_stride_px
        ) * parameters.long_anchor_stride_px
        starts = tuple(
            start
            for start in range(
                first,
                chunk_end,
                parameters.long_anchor_stride_px,
            )
            if (
                (start >= chunk_start or chunk_start == 0)
                and start + parameters.long_support_width_px <= width
            )
        )
        incomplete_anchor_count = sum(
            1
            for start in range(
                first,
                chunk_end,
                parameters.long_anchor_stride_px,
            )
            if start + parameters.long_support_width_px > width
        )
        neutral_anchor_count += incomplete_anchor_count
        profiles = _chunk_anchor_profiles(
            gray_work,
            starts,
            parameters.long_support_width_px,
        )
        peak_buffer_bytes = max(
            peak_buffer_bytes,
            profiles.temporary_buffer_upper_bound_bytes,
        )
        for profile_index, start in enumerate(profiles.starts):
            end = start + parameters.long_support_width_px
            raw_anchor_count += 1
            observed, duplicate_count = _anchor_transitions(
                profiles.intensity[:, profile_index],
                profiles.texture[:, profile_index],
                profiles.gradient[:, profile_index],
                start,
                end,
                corridors,
                parameters,
            )
            merged_duplicate_count += duplicate_count
            if not observed:
                neutral_anchor_count += 1
            transitions.extend(observed)
    graph = _ridge_graph(
        tuple(transitions),
        source_sha256,
        observation_prefix,
        parameters.long_anchor_stride_px,
    )
    return PhotoEdgeObservationResult(
        graph=graph,
        summary=PhotoEdgeMeasurementSummary(
            raw_anchor_count=raw_anchor_count,
            supported_transition_count=len(transitions),
            neutral_anchor_count=neutral_anchor_count,
            censored_component_count=_censored_component_count(graph),
            merged_duplicate_count=merged_duplicate_count,
            fragment_count=graph.path_count,
            canonical_observation_count=len(graph.nodes),
            chunk_size_px=parameters.chunk_size_px,
            peak_temporary_buffer_bytes=peak_buffer_bytes,
        ),
    )
