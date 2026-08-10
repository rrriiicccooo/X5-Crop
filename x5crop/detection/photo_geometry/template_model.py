from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from ...domain import FiniteInterval, ObservationId, PositiveInterval
from ...formats import FramePhysicalSpec
from .model import (
    BoundaryAxis,
    BoundaryRole,
    FrameBoundaryGeometry,
    PhotoBoundaryMeasurementSet,
    PhotoBoundaryObservation,
    PhotoBoundaryTransition,
    SharedStripDirection,
)
from .source_geometry import LaneGapModel, SourceFrameGeometry
from .template_profiles import (
    BasicAxisProfile,
    PhaseGroupingWork,
    PhaseVote,
    ProfileRun,
    TemplatePhaseGroup,
    TemplateRole,
)


class LocalAdvanceKind(str, Enum):
    NOMINAL = "nominal"
    WIDE = "wide"
    NARROW = "narrow"
    CONTACT = "contact"
    OVERLAP = "overlap"


@dataclass(frozen=True)
class LocalAdvanceRelation:
    relation_ordinal: int
    kind: LocalAdvanceKind
    delta_interval_px: FiniteInterval
    canonical_delta_px: float
    observation_ids: tuple[ObservationId, ...]

    def __post_init__(self) -> None:
        if (
            self.relation_ordinal <= 0
            or not self.delta_interval_px.contains(
                self.canonical_delta_px,
                epsilon=1.0e-9,
            )
            or len(set(self.observation_ids)) != len(self.observation_ids)
            or (
                self.kind == LocalAdvanceKind.NOMINAL
                and (
                    self.delta_interval_px != FiniteInterval.exact(0.0)
                    or self.canonical_delta_px != 0.0
                )
            )
            or (
                self.kind != LocalAdvanceKind.NOMINAL
                and not self.observation_ids
            )
        ):
            raise ValueError("local advance relation is invalid")


@dataclass(frozen=True)
class TemplateSequenceSeed:
    """One bounded complete template interpretation with local phase steps."""

    seed_id: str
    phase_group_ids: tuple[str, ...]
    base_phase_interval_px: FiniteInterval
    votes: tuple[PhaseVote, ...]
    local_advance_votes: tuple[PhaseVote, ...]
    local_advance_relations: tuple[LocalAdvanceRelation, ...]
    exclusion_authorized: bool

    def __post_init__(self) -> None:
        if (
            not self.seed_id
            or not self.phase_group_ids
            or not self.votes
            or len({item.vote_id for item in self.votes}) != len(self.votes)
            or len(
                {item.vote_id for item in self.local_advance_votes}
            )
            != len(self.local_advance_votes)
            or not {
                item.vote_id for item in self.votes
            }.issubset(
                item.vote_id for item in self.local_advance_votes
            )
            or tuple(
                item.relation_ordinal for item in self.local_advance_relations
            )
            != tuple(range(1, len(self.local_advance_relations) + 1))
        ):
            raise ValueError("template sequence seed is invalid")


class EnhancedQueryRegistry:
    """Pre-registered typed enhanced work; selection cannot add coverage."""

    def __init__(self, query_ids: tuple[str, ...]) -> None:
        if not query_ids or len(set(query_ids)) != len(query_ids):
            raise ValueError("enhanced query registry requires unique identities")
        self._registered = frozenset(query_ids)
        self._consumed: set[str] = set()

    @property
    def registered_count(self) -> int:
        return len(self._registered)

    @property
    def consumed_count(self) -> int:
        return len(self._consumed)

    def consume(self, query_id: str) -> bool:
        if query_id not in self._registered:
            raise KeyError(query_id)
        if query_id in self._consumed:
            return False
        self._consumed.add(query_id)
        return True


@dataclass(frozen=True)
class EnhancedPhaseQuery:
    """A pre-registered exact reprojection of one ambiguous basic vote."""

    query_id: str
    vote_id: str

    def __post_init__(self) -> None:
        if not self.query_id or not self.vote_id:
            raise ValueError("enhanced phase query requires identities")


@dataclass(frozen=True)
class RegisteredSequenceRoleQuery:
    """One template role registered before direction-aware evidence binding."""

    query_id: str
    seed_id: str
    role: TemplateRole
    target_interval_px: FiniteInterval

    def __post_init__(self) -> None:
        if not self.query_id or not self.seed_id:
            raise ValueError("registered sequence role query requires identities")


@dataclass(frozen=True)
class TemplateWorkReceipt:
    measurement_query_count: int
    pixel_query_count: int
    basic_profile_coordinate_count: int
    basic_profile_run_count: int
    phase_vote_count: int
    template_group_count: int
    template_role_lookup_count: int
    template_role_match_count: int
    local_relation_evaluation_count: int
    enhanced_query_count: int
    materialized_frame_geometry_count: int
    shared_measurement_reuse_count: int
    domain_pixels: int
    peak_temporary_bytes: int

    def __post_init__(self) -> None:
        if any(value < 0 for value in self.__dict__.values()):
            raise ValueError("template work receipt cannot be negative")

    def validate_bounds(
        self,
        *,
        ordered_role_count: int,
        slot_count: int,
        registered_enhanced_query_count: int,
    ) -> None:
        if (
            ordered_role_count <= 0
            or slot_count <= 0
            or registered_enhanced_query_count < 0
        ):
            raise ValueError("template work bound requires positive shape")
        if (
            self.template_role_lookup_count
            > self.template_group_count * ordered_role_count
            or self.template_role_match_count > self.phase_vote_count
            or self.enhanced_query_count > registered_enhanced_query_count
            or self.local_relation_evaluation_count
            > self.template_group_count * max(0, slot_count - 1)
        ):
            raise ValueError("template work exceeded its structural bound")


@dataclass(frozen=True)
class ProvisionalHeightTemplate:
    template_id: str
    component_id: str
    origin_interval_px: FiniteInterval
    observed_runs: tuple[ProfileRun, ...]
    raw_observations: tuple[PhotoBoundaryObservation, ...]

    def __post_init__(self) -> None:
        run_roles = tuple(run.role_hint for run in self.observed_runs)
        observation_roles = tuple(
            observation.role for observation in self.raw_observations
        )
        if (
            not self.template_id
            or not self.component_id
            or not 1 <= len(self.observed_runs) <= 2
            or len(self.raw_observations) != len(self.observed_runs)
            or run_roles != observation_roles
            or tuple(
                sorted(
                    run_roles,
                    key=lambda role: (
                        0 if role == BoundaryRole.TOP else 1
                    ),
                )
            )
            != run_roles
            or len(set(run_roles)) != len(run_roles)
            or any(
                role not in {BoundaryRole.TOP, BoundaryRole.BOTTOM}
                for role in run_roles
            )
            or any(
                set(run.transition_ids) != set(observation.transition_ids)
                for run, observation in zip(
                    self.observed_runs,
                    self.raw_observations,
                    strict=True,
                )
            )
        ):
            raise ValueError("provisional height template is invalid")


@dataclass(frozen=True)
class TemplateLaneInput:
    lane_id: str
    output_slot_count: int
    measurement_slot_count: int
    width_axis: BoundaryAxis
    height_axis: BoundaryAxis
    width_authority_px: FiniteInterval
    height_authority_px: FiniteInterval
    width_scale_px_per_mm: PositiveInterval
    height_scale_px_per_mm: PositiveInterval
    sequence_profile: BasicAxisProfile
    cross_profile: BasicAxisProfile
    sequence_measurement_sets: tuple[PhotoBoundaryMeasurementSet, ...]
    top_measurement_set: PhotoBoundaryMeasurementSet
    bottom_measurement_set: PhotoBoundaryMeasurementSet
    transition_by_id: dict[str, PhotoBoundaryTransition]

    def __post_init__(self) -> None:
        if (
            not self.lane_id
            or self.output_slot_count <= 0
            or self.measurement_slot_count < self.output_slot_count
            or self.width_axis == self.height_axis
            or self.sequence_profile.axis_name != "sequence"
            or self.cross_profile.axis_name != "cross"
            or any(
                item.query.boundary_axis != self.width_axis
                for item in self.sequence_measurement_sets
            )
        ):
            raise ValueError("template lane input is invalid")


@dataclass(frozen=True)
class ComponentTemplateProposal:
    component: FramePhysicalSpec
    initial_source_geometry: SourceFrameGeometry
    roles: tuple[TemplateRole, ...]
    phase_votes: tuple[PhaseVote, ...]
    phase_groups: tuple[TemplatePhaseGroup, ...]
    enhanced_phase_queries: tuple[EnhancedPhaseQuery, ...]
    registered_sequence_role_queries: tuple[RegisteredSequenceRoleQuery, ...]
    height_templates: tuple[ProvisionalHeightTemplate, ...]
    grouping_work: PhaseGroupingWork

    def __post_init__(self) -> None:
        if (
            self.initial_source_geometry.component != self.component
            or not self.roles
            or not self.phase_votes
            or not self.phase_groups
            or len({item.query_id for item in self.enhanced_phase_queries})
            != len(self.enhanced_phase_queries)
            or len(
                {
                    item.query_id
                    for item in self.registered_sequence_role_queries
                }
            )
            != len(self.registered_sequence_role_queries)
            or not {
                item.vote_id for item in self.enhanced_phase_queries
            }.issubset({item.vote_id for item in self.phase_votes})
        ):
            raise ValueError("component template proposal is invalid")


@dataclass(frozen=True)
class TemplateLaneProposal:
    lane: TemplateLaneInput
    components: tuple[ComponentTemplateProposal, ...]
    raw_top_bottom_observations: tuple[PhotoBoundaryObservation, ...]
    direction_classes: tuple[SharedStripDirection, ...]

    def __post_init__(self) -> None:
        if any(
            component.component.component_id
            != component.initial_source_geometry.component.component_id
            for component in self.components
        ):
            raise ValueError("lane proposal component identity is invalid")


@dataclass(frozen=True)
class SourcePlacementMaterialization:
    placements_by_lane: tuple[tuple[FormatPlacement, ...], ...]
    enhanced_query_counts_by_lane: tuple[int, ...]
    lane_proposals: tuple[TemplateLaneProposal, ...]

    def __post_init__(self) -> None:
        if (
            len(self.placements_by_lane)
            != len(self.enhanced_query_counts_by_lane)
            or len(self.placements_by_lane) != len(self.lane_proposals)
            or any(value < 0 for value in self.enhanced_query_counts_by_lane)
        ):
            raise ValueError("source placement materialization is invalid")


@dataclass(frozen=True)
class BoundRoleEvidence:
    role: TemplateRole
    run_id: str
    canonical_position_px: float
    fit_position_interval_px: FiniteInterval
    full_position_interval_px: FiniteInterval
    transition_ids: tuple[ObservationId, ...]
    support_fraction: float
    continuous_support_fraction: float
    fit_residual_px: float
    background_preference: float

    def __post_init__(self) -> None:
        if (
            not self.run_id
            or not self.fit_position_interval_px.contains(
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
            or not self.transition_ids
            or not 0.0 <= self.support_fraction <= 1.0
            or not 0.0 <= self.continuous_support_fraction <= 1.0
            or not math.isfinite(self.fit_residual_px)
            or self.fit_residual_px < 0.0
            or not 0.0 <= self.background_preference <= 1.0
        ):
            raise ValueError("bound role evidence is invalid")


@dataclass(frozen=True)
class SequencePlacement:
    placement_id: str
    template_seed_id: str
    phase_group_ids: tuple[str, ...]
    source_geometry_id: str
    roles: tuple[TemplateRole, ...]
    phase_fit_interval_px: FiniteInterval
    phase_full_interval_px: FiniteInterval
    lane_gap_model: LaneGapModel
    local_advance_relations: tuple[LocalAdvanceRelation, ...]
    canonical_positions_px: tuple[float, ...]
    fit_positions_px: tuple[FiniteInterval, ...]
    full_positions_px: tuple[FiniteInterval, ...]
    sequence_edge_direction_intervals_degrees: tuple[FiniteInterval, ...]
    safety_support_transition_ids: tuple[tuple[ObservationId, ...], ...]
    observations: tuple[BoundRoleEvidence, ...]
    exclusion_authorized: bool

    def __post_init__(self) -> None:
        role_count = len(self.roles)
        if (
            not self.placement_id
            or not self.template_seed_id
            or not self.phase_group_ids
            or not self.source_geometry_id
            or role_count <= 0
            or len(self.canonical_positions_px) != role_count
            or len(self.fit_positions_px) != role_count
            or len(self.full_positions_px) != role_count
            or len(
                self.sequence_edge_direction_intervals_degrees
            )
            != role_count
            or len(self.safety_support_transition_ids) != role_count
            or any(
                len(set(values)) != len(values)
                for values in self.safety_support_transition_ids
            )
            or len(self.local_advance_relations) != max(0, role_count // 2 - 1)
            or any(
                not fit.contains(canonical, epsilon=1.0e-8)
                or not full.contains(fit.minimum, epsilon=1.0e-8)
                or not full.contains(fit.maximum, epsilon=1.0e-8)
                for canonical, fit, full in zip(
                    self.canonical_positions_px,
                    self.fit_positions_px,
                    self.full_positions_px,
                    strict=True,
                )
            )
        ):
            raise ValueError("sequence placement is invalid")

    @property
    def observed_role_count(self) -> int:
        return len({item.role.role_index for item in self.observations})

    @property
    def observed_opposite_pair_count(self) -> int:
        roles_by_ordinal: dict[int, set[BoundaryRole]] = {}
        for observation in self.observations:
            roles_by_ordinal.setdefault(
                observation.role.lane_ordinal,
                set(),
            ).add(observation.role.role)
        return sum(
            roles == {BoundaryRole.START, BoundaryRole.END}
            for roles in roles_by_ordinal.values()
        )

    @property
    def canonical_rank(self) -> tuple[object, ...]:
        support = sum(item.support_fraction for item in self.observations)
        continuity = sum(
            item.continuous_support_fraction for item in self.observations
        )
        residual = sum(item.fit_residual_px for item in self.observations)
        background = sum(
            item.background_preference for item in self.observations
        )
        return (
            -self.observed_role_count,
            -self.observed_opposite_pair_count,
            -support,
            -continuity,
            residual,
            sum(item.width for item in self.full_positions_px),
            -background,
            self.placement_id,
        )


@dataclass(frozen=True)
class CrossRoleEvidence:
    role: BoundaryRole
    run_id: str
    observation: PhotoBoundaryObservation
    canonical_position_at_lane_reference_px: float
    fit_position_at_lane_reference_px: FiniteInterval
    full_position_at_lane_reference_px: FiniteInterval

    def __post_init__(self) -> None:
        if (
            self.role not in {BoundaryRole.TOP, BoundaryRole.BOTTOM}
            or self.observation.role != self.role
            or not self.run_id
            or not self.fit_position_at_lane_reference_px.contains(
                self.canonical_position_at_lane_reference_px,
                epsilon=1.0e-8,
            )
            or not self.full_position_at_lane_reference_px.contains(
                self.fit_position_at_lane_reference_px.minimum,
                epsilon=1.0e-8,
            )
            or not self.full_position_at_lane_reference_px.contains(
                self.fit_position_at_lane_reference_px.maximum,
                epsilon=1.0e-8,
            )
        ):
            raise ValueError("cross role evidence is invalid")


@dataclass(frozen=True)
class CrossPlacement:
    placement_id: str
    provisional_template_id: str
    source_geometry_id: str
    lane_reference_trace_px: float
    frame_reference_traces_px: tuple[float, ...]
    top_canonical_positions_px: tuple[float, ...]
    bottom_canonical_positions_px: tuple[float, ...]
    top_fit_positions_px: tuple[FiniteInterval, ...]
    bottom_fit_positions_px: tuple[FiniteInterval, ...]
    top_full_positions_px: tuple[FiniteInterval, ...]
    bottom_full_positions_px: tuple[FiniteInterval, ...]
    evidence: tuple[CrossRoleEvidence, ...]

    def __post_init__(self) -> None:
        count = len(self.frame_reference_traces_px)
        values = (
            self.top_canonical_positions_px,
            self.bottom_canonical_positions_px,
            self.top_fit_positions_px,
            self.bottom_fit_positions_px,
            self.top_full_positions_px,
            self.bottom_full_positions_px,
        )
        if (
            not self.placement_id
            or not self.provisional_template_id
            or not self.source_geometry_id
            or count <= 0
            or any(len(value) != count for value in values)
            or not self.evidence
            or any(
                top >= bottom
                for top, bottom in zip(
                    self.top_canonical_positions_px,
                    self.bottom_canonical_positions_px,
                    strict=True,
                )
            )
            or any(
                not top_fit.contains(top, epsilon=1.0e-8)
                or not bottom_fit.contains(bottom, epsilon=1.0e-8)
                or not top_full.contains(top_fit.minimum, epsilon=1.0e-8)
                or not top_full.contains(top_fit.maximum, epsilon=1.0e-8)
                or not bottom_full.contains(bottom_fit.minimum, epsilon=1.0e-8)
                or not bottom_full.contains(bottom_fit.maximum, epsilon=1.0e-8)
                for top, bottom, top_fit, bottom_fit, top_full, bottom_full in zip(
                    self.top_canonical_positions_px,
                    self.bottom_canonical_positions_px,
                    self.top_fit_positions_px,
                    self.bottom_fit_positions_px,
                    self.top_full_positions_px,
                    self.bottom_full_positions_px,
                    strict=True,
                )
            )
        ):
            raise ValueError("cross placement is invalid")

    @property
    def observed_role_count(self) -> int:
        return len({item.role for item in self.evidence})

    @property
    def canonical_rank(self) -> tuple[object, ...]:
        support = sum(
            item.observation.trace_support_count for item in self.evidence
        )
        continuity = sum(
            item.observation.continuous_support_fraction
            for item in self.evidence
        )
        residual = sum(
            item.observation.fit_residual_px for item in self.evidence
        )
        uncertainty = sum(
            value.width
            for value in (*self.top_full_positions_px, *self.bottom_full_positions_px)
        )
        return (
            -self.observed_role_count,
            -support,
            -continuity,
            residual,
            uncertainty,
            self.placement_id,
        )


def _polygon_area(points: tuple[tuple[float, float], ...]) -> float:
    return 0.5 * sum(
        left[0] * right[1] - right[0] * left[1]
        for left, right in zip(points, points[1:] + points[:1], strict=True)
    )


@dataclass(frozen=True)
class FrameFormatPlacement:
    placement_geometry_id: str
    lane_id: str
    lane_ordinal: int
    top: FrameBoundaryGeometry
    bottom: FrameBoundaryGeometry
    start: FrameBoundaryGeometry
    end: FrameBoundaryGeometry
    canonical_source_polygon: tuple[tuple[float, float], ...]

    def __post_init__(self) -> None:
        if (
            not self.placement_geometry_id
            or not self.lane_id
            or self.lane_ordinal <= 0
            or tuple(
                item.role for item in (self.top, self.bottom, self.start, self.end)
            )
            != (
                BoundaryRole.TOP,
                BoundaryRole.BOTTOM,
                BoundaryRole.START,
                BoundaryRole.END,
            )
            or len(self.canonical_source_polygon) != 4
            or abs(_polygon_area(self.canonical_source_polygon)) <= 1.0e-9
        ):
            raise ValueError("frame format placement is invalid")


@dataclass(frozen=True)
class CanonicalFormatPlacement:
    canonical_id: str
    sequence_placement_id: str
    cross_placement_id: str
    frames: tuple[FrameFormatPlacement, ...]
    canonical_rank: tuple[object, ...]

    def __post_init__(self) -> None:
        if (
            not self.canonical_id
            or not self.sequence_placement_id
            or not self.cross_placement_id
            or not self.frames
            or tuple(frame.lane_ordinal for frame in self.frames)
            != tuple(range(1, len(self.frames) + 1))
        ):
            raise ValueError("canonical format placement is invalid")


@dataclass(frozen=True)
class FormatPlacement:
    placement_id: str
    lane_id: str
    component: FramePhysicalSpec
    output_slot_count: int
    direction: SharedStripDirection
    source_frame_geometry: SourceFrameGeometry
    sequence_placements: tuple[SequencePlacement, ...]
    cross_placements: tuple[CrossPlacement, ...]
    canonical_cross_placement: CrossPlacement
    canonical: CanonicalFormatPlacement

    def __post_init__(self) -> None:
        if (
            not self.placement_id
            or not self.lane_id
            or self.output_slot_count <= 0
            or not self.sequence_placements
            or not self.cross_placements
            or self.canonical_cross_placement.source_geometry_id
            != self.source_frame_geometry.geometry_id
            or self.canonical.cross_placement_id
            != self.canonical_cross_placement.placement_id
            or len(self.canonical.frames) != self.output_slot_count
            or self.source_frame_geometry.component != self.component
            or any(
                item.source_geometry_id
                != self.source_frame_geometry.geometry_id
                for item in (
                    *self.sequence_placements,
                    *self.cross_placements,
                )
            )
        ):
            raise ValueError("format placement is invalid")

    @property
    def canonical_sequence(self) -> SequencePlacement:
        return next(
            item
            for item in self.sequence_placements
            if item.placement_id == self.canonical.sequence_placement_id
        )

    @property
    def canonical_cross(self) -> CrossPlacement:
        return self.canonical_cross_placement
