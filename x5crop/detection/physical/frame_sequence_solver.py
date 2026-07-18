from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, replace
from functools import lru_cache
import hashlib
from math import ceil, floor, isfinite

import numpy as np

from ...domain import (
    BoundaryAxis,
    BoundaryPathFit,
    BoundarySide,
    Box,
    EvidenceState,
    FrameDimensionPrior,
    GrayBoundaryPathObservation,
    HolderBoundaryObservation,
    InterFrameBoundaryReference,
    InterFrameSpacing,
    InterFrameSpacingBasis,
    InterFrameSpacingKind,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    FrameSequenceSearchScope,
    PhysicalSearchFact,
    PhysicalSearchOutcome,
    PixelInterval,
    SeparatorBandCrossAxisSupport,
    SeparatorBandObservation,
    SeparatorCrossAxisMeasurement,
)
from ...image.content import ContentRegionObservation
from ...strip_modes import FULL, PARTIAL
from .model import (
    AssignmentConsensusOutcome,
    BoundaryAnchor,
    BoundaryAssignmentConsensus,
    BoundaryGeometryState,
    BoundaryRoleAuthority,
    boundary_role_is_independent_physical_measurement,
    CommonFrameWidthResolution,
    ContentExtentConstraint,
    FrameEdgeOcclusionInference,
    FrameContentOccupancy,
    FrameWidthMeasurementConstraint,
    FrameWidthPhysicalScaleConstraint,
    FrameWidthSearchHint,
    HolderSpanScaleHint,
    IndexedAnchorDistanceConstraint,
    FrameSlot,
    FrameEdgeAssignment,
    FrameBoundarySource,
    ResolvedFrameBoundary,
    PhotoHeightEvidence,
    SeparatorBandAssignment,
    SequenceResiduals,
    SharedShortAxisSafetySpan,
)
from .sequence_completion import (
    infer_sequence_frame_slot,
    measured_sequence_supports_slot_inference,
)
from .frame_dimensions import MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS
from .separator.observations import SeparatorSupportSet
from .short_axis import (
    SharedShortAxisPlan,
    frame_width_search_hint,
)


MINIMUM_POSITIVE_PIXEL_EXTENT = 1.0
MINIMUM_COUNT_WITH_INTERIOR_FRAME = 3
BIDIRECTIONAL_REFINEMENT_PASSES = 2
STRICT_MAJORITY_DIVISOR = 2
INTERVAL_ENDPOINT_COUNT = 2


@dataclass(frozen=True)
class FrameSequenceSolveResult:
    shared_short_axis: SharedShortAxisSafetySpan
    photo_height_evidence: PhotoHeightEvidence
    frame_width_search_hint: FrameWidthSearchHint
    holder_span_scale_hint: HolderSpanScaleHint
    content_extent_constraint: ContentExtentConstraint
    indexed_anchor_distance_constraints: tuple[IndexedAnchorDistanceConstraint, ...]
    frame_slots: tuple[FrameSlot, ...]
    long_axis_assignments: tuple[FrameEdgeAssignment, ...]
    separator_assignments: tuple[SeparatorBandAssignment, ...]
    inter_frame_spacings: tuple[InterFrameSpacing, ...]
    common_frame_width: CommonFrameWidthResolution
    residuals: SequenceResiduals
    assignment_consensus: BoundaryAssignmentConsensus
    search_outcome: PhysicalSearchOutcome
    assignment_evaluations: int

    def __post_init__(self) -> None:
        if self.assignment_evaluations < 0:
            raise ValueError("assignment evaluation count cannot be negative")
        if PhysicalSearchFact.SOLUTION_FOUND not in self.search_outcome.facts:
            raise ValueError("frame sequence result requires a found solution")
        if not self.frame_slots:
            raise ValueError("frame sequence result requires frame slots")
        if not _frame_slots_are_strictly_monotonic(self.frame_slots):
            raise ValueError("frame sequence result requires monotonic slots")


@dataclass(frozen=True)
class FrameSequenceSolveFailure:
    search_outcome: PhysicalSearchOutcome
    assignment_evaluations: int

    def __post_init__(self) -> None:
        if self.assignment_evaluations < 0:
            raise ValueError("assignment evaluation count cannot be negative")
        if PhysicalSearchFact.SOLUTION_FOUND in self.search_outcome.facts:
            raise ValueError("frame sequence failure cannot contain a solution")


def _holder_span_scale_hint(
    search_scope: FrameSequenceSearchScope,
    count: int,
) -> HolderSpanScaleHint:
    leading = search_scope.holder_safety.boundary(BoundarySide.LEADING)
    trailing = search_scope.holder_safety.boundary(BoundarySide.TRAILING)
    span = (
        trailing.position.minus(leading.position)
        if leading is not None and trailing is not None
        else PixelInterval.exact(float(search_scope.holder_safety.box.width))
    )
    return HolderSpanScaleHint(
        holder_span_px=span,
        count=count,
        provenance=MeasurementProvenance(
            root_measurement=MeasurementIdentity.FRAME_GEOMETRY,
            observation_id=ObservationId(f"holder_span_scale_hint:{count}"),
            dependencies=tuple(
                dict.fromkeys(
                    (
                        search_scope.holder_safety.provenance.root_measurement,
                        *search_scope.holder_safety.provenance.dependencies,
                    )
                )
            ),
            description="count-dependent holder-span search hint",
            boundary_anchors=search_scope.holder_safety.provenance.boundary_anchors,
        ),
    )


def _content_extent_constraint(
    visible_content: ContentRegionObservation,
) -> ContentExtentConstraint:
    return ContentExtentConstraint(
        long_axis_extent_px=PixelInterval(
            float(visible_content.region.left),
            float(visible_content.region.right),
        ),
        reliable_runs_px=tuple(
            PixelInterval(float(start), float(end))
            for start, end in visible_content.reliable_runs
        ),
        position_uncertainty_px=visible_content.position_uncertainty_px,
        provenance=MeasurementProvenance(
            root_measurement=MeasurementIdentity.CONTENT_EVIDENCE_IMAGE,
            observation_id=ObservationId("content_extent_constraint"),
            dependencies=(MeasurementIdentity.GRAY_WORK,),
            description="count-independent visible-content extent constraint",
        ),
    )


@dataclass(frozen=True)
class _EdgeConstraint:
    position: PixelInterval
    basis: FrameBoundarySource
    state: EvidenceState
    geometry_state: BoundaryGeometryState
    provenance: MeasurementProvenance
    path: GrayBoundaryPathObservation | None = None
    separator: SeparatorBandObservation | None = None
    separator_cross_axis: SeparatorCrossAxisMeasurement | None = None
    external_side: BoundarySide | None = None

    def __post_init__(self) -> None:
        if self.basis == FrameBoundarySource.GRAY_PATH_OBSERVATION:
            if (
                self.path is None
                or self.separator is not None
                or self.separator_cross_axis is not None
            ):
                raise ValueError("measured frame-slot constraint requires one raw path")
            if self.path.axis != BoundaryAxis.LONG:
                raise ValueError("long-axis frame-slot constraint requires a long path")
            if self.state != EvidenceState.UNAVAILABLE:
                raise ValueError(
                    "generic gray path cannot claim a supported photo-edge role"
                )
            if not self.path.position.intersects(self.position):
                raise ValueError("measured frame-slot constraint must preserve its path")
        elif self.basis == FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION:
            if (
                self.separator is None
                or self.separator_cross_axis is None
                or self.path is not None
            ):
                raise ValueError("separator frame-slot constraint requires one band")
            if self.state not in {
                EvidenceState.UNAVAILABLE,
                EvidenceState.SUPPORTED,
            }:
                raise ValueError(
                    "separator edge role must be unavailable or supported"
                )
            if self.external_side is not None:
                if self.external_side == BoundarySide.LEADING:
                    expected = self.separator.trailing_edge
                elif self.external_side == BoundarySide.TRAILING:
                    expected = self.separator.leading_edge
                else:
                    raise ValueError(
                        "holder-adjacent separator edge requires a long-axis side"
                    )
                if self.position != expected:
                    raise ValueError(
                        "holder-adjacent band must expose its photo-facing edge"
                    )
        elif self.basis == FrameBoundarySource.DIMENSION_CONSTRAINED:
            if (
                self.separator is not None
                or self.separator_cross_axis is not None
                or self.path is not None
                or self.external_side is not None
            ):
                raise ValueError(
                    "dimension-constrained frame-slot edge cannot claim an observation"
                )
            if self.state != EvidenceState.UNAVAILABLE:
                raise ValueError("dimension-constrained frame-slot edge must be unavailable")
        else:
            raise ValueError("unsupported frame slot constraint basis")
        if not isinstance(self.geometry_state, BoundaryGeometryState):
            raise TypeError("frame-slot constraint requires typed geometry state")
        if (
            self.basis != FrameBoundarySource.DIMENSION_CONSTRAINED
            and self.geometry_state != BoundaryGeometryState.RESOLVED
        ):
            raise ValueError("observed frame-slot constraints have resolved positions")

    @property
    def measurement_quality(self) -> float:
        return (
            self.observation_quality
            if self.state == EvidenceState.SUPPORTED
            else 0.0
        )

    @property
    def observation_quality(self) -> float:
        if self.path is not None:
            return min(
                self.path.lower_appearance.spatial_continuity,
                self.path.upper_appearance.spatial_continuity,
            )
        if self.separator is None or self.separator_cross_axis is None:
            return 0.0
        return float(
            _separator_edge_path_measurement(self).longest_supported_ratio or 0.0
        )


@dataclass(frozen=True)
class _BandSequenceHypothesis:
    supports: tuple[SeparatorBandCrossAxisSupport, ...]
    band_edges: tuple[tuple[_EdgeConstraint, _EdgeConstraint], ...]
    short_axis: SharedShortAxisSafetySpan
    frame_width_px: PixelInterval
    indexed_anchor_count: int
    paired_band_count: int
    measurement_quality: float
    search_order_residual: float
    uncertainty_px: float

    def __post_init__(self) -> None:
        if not self.supports or len(self.supports) != len(self.band_edges):
            raise ValueError(
                "separator sequence hypothesis requires one edge pair per band"
            )
        if self.frame_width_px.minimum < MINIMUM_POSITIVE_PIXEL_EXTENT:
            raise ValueError("separator sequence frame width must be positive")
        if self.indexed_anchor_count < 0:
            raise ValueError("indexed anchor count cannot be negative")
        if not 0 <= self.paired_band_count <= len(self.supports):
            raise ValueError("paired separator count exceeds sequence length")
        measurements = (
            self.measurement_quality,
            self.search_order_residual,
            self.uncertainty_px,
        )
        if any(not isfinite(value) or value < 0.0 for value in measurements):
            raise ValueError(
                "separator sequence measurements must be finite and non-negative"
            )


@dataclass(frozen=True)
class _SequenceBuildObjectives:
    uncorroborated_overlap_extent_px: float
    unexplained_spacing_extent_px: float
    supported_separator_count: int
    internal_boundary_measurement_quality: float
    dimension_residual: float
    external_boundary_measurement_quality: float
    boundary_uncertainty_ratio: float
    frame_width_hint_residual: float = 0.0
    uncorroborated_contact_count: int = 0
    inferred_boundary_count: int = 0

    def __post_init__(self) -> None:
        measurements = (
            self.uncorroborated_overlap_extent_px,
            self.unexplained_spacing_extent_px,
            self.internal_boundary_measurement_quality,
            self.dimension_residual,
            self.external_boundary_measurement_quality,
            self.boundary_uncertainty_ratio,
            self.frame_width_hint_residual,
        )
        if any(not isfinite(value) or value < 0.0 for value in measurements):
            raise ValueError("sequence build objectives must be finite and non-negative")
        if self.supported_separator_count < 0:
            raise ValueError("supported separator count cannot be negative")
        if self.uncorroborated_contact_count < 0:
            raise ValueError("uncorroborated contact count cannot be negative")
        if self.inferred_boundary_count < 0:
            raise ValueError("inferred boundary count cannot be negative")

    def dominance_axes(
        self,
    ) -> tuple[float, ...]:
        return (
            -self.uncorroborated_overlap_extent_px,
            -self.unexplained_spacing_extent_px,
            self.supported_separator_count,
            -self.dimension_residual,
            -self.boundary_uncertainty_ratio,
            -float(self.uncorroborated_contact_count),
        )

    def dominates(self, other: "_SequenceBuildObjectives") -> bool:
        left = self.dominance_axes()
        right = other.dominance_axes()
        return all(a >= b for a, b in zip(left, right, strict=True)) and any(
            a > b for a, b in zip(left, right, strict=True)
        )


@dataclass(frozen=True)
class _SeparatorBandBinding:
    boundary_index: int
    observation: SeparatorBandObservation
    cross_axis_measurement: SeparatorCrossAxisMeasurement
    preceding_trailing_edge: ResolvedFrameBoundary
    following_leading_edge: ResolvedFrameBoundary

    def __post_init__(self) -> None:
        if self.boundary_index <= 0:
            raise ValueError("separator binding boundary index must be positive")
        if (
            self.cross_axis_measurement.observation_id
            != self.observation.provenance.observation_id
            or not self.cross_axis_measurement.complete_separator_supported
        ):
            raise ValueError("separator binding requires its cross-axis measurement")
        if (
            self.preceding_trailing_edge.position != self.observation.leading_edge
            or self.following_leading_edge.position
            != self.observation.trailing_edge
        ):
            raise ValueError("separator binding must preserve both observed band edges")


@dataclass(frozen=True)
class _SequenceBuild:
    slots: tuple[FrameSlot, ...]
    long_axis_assignments: tuple[FrameEdgeAssignment, ...]
    separator_bindings: tuple[_SeparatorBandBinding, ...]
    spacings: tuple[InterFrameSpacing, ...]
    frame_width_px: PixelInterval
    short_axis: SharedShortAxisSafetySpan
    residuals: SequenceResiduals
    objectives: _SequenceBuildObjectives


@dataclass(frozen=True)
class _MeasuredFrameConstraint:
    leading: _EdgeConstraint
    trailing: _EdgeConstraint
    width_px: PixelInterval
    full_width_hypothesis_admissible: bool
    leading_holder_clip_supported: bool
    trailing_holder_clip_supported: bool
    search_order_residual: float
    frame_width_hint_residual: float = 0.0

    def allowed_at(self, frame_index: int, count: int) -> bool:
        return bool(
            self.full_width_hypothesis_admissible
            or (frame_index == 1 and self.leading_holder_clip_supported)
            or (frame_index == count and self.trailing_holder_clip_supported)
        )


@dataclass(frozen=True)
class _CommonWidthHypothesis:
    width_px: PixelInterval
    boundary_anchors: tuple[ObservationId, ...]
    contributor_count: int

    def __post_init__(self) -> None:
        if self.width_px.minimum < MINIMUM_POSITIVE_PIXEL_EXTENT:
            raise ValueError("common-width hypothesis must be positive")
        if self.contributor_count < MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS:
            raise ValueError("common-width hypothesis requires independent slots")
        if not self.boundary_anchors:
            raise ValueError("common-width hypothesis requires measured anchors")


@dataclass(frozen=True)
class _RecurringBoundaryWidthHypothesis:
    width_px: PixelInterval
    contributor_count: int

    def __post_init__(self) -> None:
        if self.width_px.minimum < MINIMUM_POSITIVE_PIXEL_EXTENT:
            raise ValueError("recurring boundary width must be positive")
        if self.contributor_count < MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS:
            raise ValueError("recurring boundary width requires repeated slots")


@dataclass(frozen=True)
class _DimensionPlacementHypothesis:
    width_px: PixelInterval
    boundary_anchors: tuple[ObservationId, ...]
    repeated_slot_count: int = 0

    def __post_init__(self) -> None:
        if self.width_px.minimum < MINIMUM_POSITIVE_PIXEL_EXTENT:
            raise ValueError("dimension placement hypothesis must be positive")
        if self.repeated_slot_count < 0:
            raise ValueError("repeated slot count cannot be negative")


@dataclass(frozen=True)
class _MeasuredFrameSearchSpace:
    leading_candidates: tuple[tuple[_EdgeConstraint, bool], ...]
    trailing_candidates: tuple[tuple[_EdgeConstraint, bool], ...]
    observed_constraints: tuple[_MeasuredFrameConstraint, ...]
    width_hypotheses: tuple[_CommonWidthHypothesis, ...]
    recurring_width_hypotheses: tuple[_RecurringBoundaryWidthHypothesis, ...]


def _width_satisfies_physical_scale(
    width: PixelInterval,
    constraint: FrameWidthPhysicalScaleConstraint | None,
) -> bool:
    return constraint is None or width.intersects(constraint.width_px)


def _dimension_placement_hypotheses(
    measured_widths: tuple[_CommonWidthHypothesis, ...],
    recurring_widths: tuple[_RecurringBoundaryWidthHypothesis, ...],
    search_hints: tuple[PixelInterval, ...],
    physical_scale_constraint: FrameWidthPhysicalScaleConstraint | None,
) -> tuple[_DimensionPlacementHypothesis, ...]:
    measured = tuple(
        _DimensionPlacementHypothesis(
            hypothesis.width_px,
            hypothesis.boundary_anchors,
            hypothesis.contributor_count,
        )
        for hypothesis in measured_widths
    )
    recurring = tuple(
        _DimensionPlacementHypothesis(
            hypothesis.width_px,
            (),
            hypothesis.contributor_count,
        )
        for hypothesis in _non_dominated_recurring_width_hypotheses(
            recurring_widths
        )
    )
    hints = tuple(
        _DimensionPlacementHypothesis(width, ())
        for width in search_hints
    )
    by_width: dict[PixelInterval, _DimensionPlacementHypothesis] = {}
    for hypothesis in (*measured, *recurring, *hints):
        if not _width_satisfies_physical_scale(
            hypothesis.width_px,
            physical_scale_constraint,
        ):
            continue
        existing = by_width.get(hypothesis.width_px)
        if existing is None:
            by_width[hypothesis.width_px] = hypothesis
            continue
        by_width[hypothesis.width_px] = _DimensionPlacementHypothesis(
            hypothesis.width_px,
            existing.boundary_anchors or hypothesis.boundary_anchors,
            max(existing.repeated_slot_count, hypothesis.repeated_slot_count),
        )
    return tuple(by_width.values())


def _non_dominated_recurring_width_hypotheses(
    hypotheses: tuple[_RecurringBoundaryWidthHypothesis, ...],
) -> tuple[_RecurringBoundaryWidthHypothesis, ...]:
    ranked = tuple(
        sorted(
            hypotheses,
            key=lambda item: (
                -item.contributor_count,
                item.width_px.maximum - item.width_px.minimum,
                item.width_px.midpoint,
            ),
        )
    )
    selected: list[_RecurringBoundaryWidthHypothesis] = []
    for hypothesis in ranked:
        uncertainty = hypothesis.width_px.maximum - hypothesis.width_px.minimum
        if any(
            existing.contributor_count >= hypothesis.contributor_count
            and hypothesis.width_px.minimum <= existing.width_px.minimum
            and existing.width_px.maximum <= hypothesis.width_px.maximum
            and (
                existing.width_px.maximum - existing.width_px.minimum
            )
            <= uncertainty
            for existing in selected
        ):
            continue
        selected.append(hypothesis)
    return tuple(selected)


@dataclass(frozen=True)
class FrameSequenceSearchIndex:
    separator_supports: SeparatorSupportSet
    leading_candidates: tuple[tuple[_EdgeConstraint, bool], ...]
    trailing_candidates: tuple[tuple[_EdgeConstraint, bool], ...]
    observed_constraints: tuple[_MeasuredFrameConstraint, ...]
    width_hypotheses: tuple[_CommonWidthHypothesis, ...]
    recurring_width_hypotheses: tuple[_RecurringBoundaryWidthHypothesis, ...]
    preparation_evaluations: int

    def __post_init__(self) -> None:
        if self.preparation_evaluations < 0:
            raise ValueError("frame-sequence search preparation cannot be negative")


def _boundary_path_fits(
    paths: tuple[GrayBoundaryPathObservation, ...],
) -> dict[ObservationId, BoundaryPathFit]:
    observations: dict[ObservationId, GrayBoundaryPathObservation] = {}
    fits: dict[ObservationId, BoundaryPathFit] = {}
    for path in paths:
        observation_id = path.provenance.observation_id
        existing = observations.get(observation_id)
        if existing is not None and existing != path:
            raise ValueError(
                "distinct boundary paths cannot share one observation identity"
            )
        if existing is None:
            observations[observation_id] = path
            fits[observation_id] = BoundaryPathFit(path)
    return fits


def _holder_boundaries(
    search_scope: FrameSequenceSearchScope,
) -> dict[BoundarySide, HolderBoundaryObservation]:
    return {
        boundary.side: boundary
        for boundary in search_scope.holder_safety.boundaries
    }


def _axis_paths(
    search_scope: FrameSequenceSearchScope,
    axis: BoundaryAxis,
) -> tuple[GrayBoundaryPathObservation, ...]:
    paths = tuple(
        dict.fromkeys(
            path
            for path in search_scope.raw_boundary_paths
            if path.axis == axis
        )
    )
    holder_path_ids = {
        path.provenance.observation_id
        for boundary in _holder_boundaries(search_scope).values()
        for path in boundary.supporting_paths
    }
    ranked = sorted(
        paths,
        key=lambda path: (
            -(path.provenance.observation_id in holder_path_ids),
            -(
                path.orthogonal_extent.maximum
                - path.orthogonal_extent.minimum
            ),
            -min(
                path.lower_appearance.spatial_continuity,
                path.upper_appearance.spatial_continuity,
            ),
            path.position.maximum - path.position.minimum,
            path.kind.value,
            path.provenance.observation_id,
        ),
    )
    path_fits = _boundary_path_fits(paths)
    canonical: list[GrayBoundaryPathObservation] = []
    for path in ranked:
        if any(
            _paths_geometrically_equivalent(
                path_fits[path.provenance.observation_id],
                path_fits[item.provenance.observation_id],
            )
            for item in canonical
        ):
            continue
        canonical.append(path)
    return tuple(
        sorted(
            canonical,
            key=lambda path: (
                path.position.midpoint,
                path.position.maximum - path.position.minimum,
                path.kind.value,
                path.provenance.observation_id,
            ),
        )
    )


def _paths_geometrically_equivalent(
    left_fit: BoundaryPathFit,
    right_fit: BoundaryPathFit,
) -> bool:
    left = left_fit.observation
    right = right_fit.observation
    if left.axis != right.axis:
        return False
    shared = left.orthogonal_extent.intersection(right.orthogonal_extent)
    if shared is None or shared.maximum <= shared.minimum:
        return False
    coordinates = (shared.minimum, shared.midpoint, shared.maximum)
    return all(
        left_position is not None
        and right_position is not None
        and left_position == right_position
        for coordinate in coordinates
        for left_position, right_position in (
            (
                left_fit.position_within(PixelInterval.exact(coordinate)),
                right_fit.position_within(PixelInterval.exact(coordinate)),
            ),
        )
    )


def _positive_interval(interval: PixelInterval) -> PixelInterval | None:
    if interval.minimum < MINIMUM_POSITIVE_PIXEL_EXTENT:
        return None
    return interval


def _interval_envelope(
    intervals: tuple[PixelInterval, ...],
) -> PixelInterval:
    if not intervals:
        raise ValueError("interval envelope requires at least one measurement")
    return PixelInterval(
        min(interval.minimum for interval in intervals),
        max(interval.maximum for interval in intervals),
    )


def _measurement_intervals_are_compatible(
    first: PixelInterval,
    second: PixelInterval,
) -> bool:
    if first.intersects(second):
        return True
    measurement_uncertainty = max(
        first.maximum - first.minimum,
        second.maximum - second.minimum,
    )
    return _interval_distance(first, second) <= measurement_uncertainty


def _strict_majority_width_consensus(
    intervals: tuple[PixelInterval, ...],
) -> tuple[PixelInterval, int] | None:
    if not intervals:
        return None
    contributor_indexes = _largest_strict_intersection_indexes(
        intervals,
        len(intervals) // STRICT_MAJORITY_DIVISOR + 1,
    )
    if not contributor_indexes:
        return None
    contributors = tuple(intervals[index] for index in contributor_indexes)
    return _interval_envelope(contributors), len(contributors)


def _non_dominated_width_hypotheses(
    hypotheses: tuple[_CommonWidthHypothesis, ...],
) -> tuple[_CommonWidthHypothesis, ...]:
    ranked = tuple(
        sorted(
            hypotheses,
            key=lambda item: (
                -item.contributor_count,
                item.width_px.maximum - item.width_px.minimum,
                item.width_px.midpoint,
                item.boundary_anchors,
            ),
        )
    )
    selected: list[_CommonWidthHypothesis] = []
    for hypothesis in ranked:
        uncertainty = hypothesis.width_px.maximum - hypothesis.width_px.minimum
        if any(
            existing.width_px.intersects(hypothesis.width_px)
            and existing.contributor_count >= hypothesis.contributor_count
            and (
                (
                    existing.width_px.minimum <= hypothesis.width_px.minimum
                    and existing.width_px.maximum >= hypothesis.width_px.maximum
                )
                or (
                    existing.width_px.maximum - existing.width_px.minimum
                ) <= uncertainty
            )
            for existing in selected
        ):
            continue
        selected.append(hypothesis)
    return tuple(selected)


def _interior_separator_observations(
    supports: tuple[SeparatorBandCrossAxisSupport, ...],
    search_scope: FrameSequenceSearchScope,
) -> tuple[SeparatorBandCrossAxisSupport, ...]:
    holder = search_scope.holder_safety.box
    return tuple(
        sorted(
            dict.fromkeys(
                support
                for support in supports
                if support.observation.leading_edge.minimum > float(holder.left)
                and support.observation.trailing_edge.maximum < float(holder.right)
            ),
            key=lambda support: (
                support.observation.leading_edge.midpoint,
                support.observation.trailing_edge.midpoint,
                support.observation.provenance.observation_id,
            ),
        )
    )


def _interior_separator_supports(
    supports: tuple[SeparatorBandCrossAxisSupport, ...],
    search_scope: FrameSequenceSearchScope,
) -> tuple[SeparatorBandCrossAxisSupport, ...]:
    return tuple(
        support
        for support in _interior_separator_observations(supports, search_scope)
        if support.measurement.complete_separator_supported
    )


def _raw_separator_frame_width_search_hints(
    supports: tuple[SeparatorBandCrossAxisSupport, ...],
    search_scope: FrameSequenceSearchScope,
    count: int,
) -> tuple[PixelInterval, ...]:
    if count <= MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS:
        return ()
    interior = _interior_separator_supports(supports, search_scope)
    if len(interior) < count - 1:
        return ()
    candidate_widths = tuple(
        width
        for left, right in zip(interior, interior[1:])
        if (
            width := _positive_interval(
                right.observation.leading_edge.minus(
                    left.observation.trailing_edge
                )
            )
        )
        is not None
    )
    contributor_indexes = _largest_strict_intersection_indexes(
        candidate_widths,
        MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS,
    )
    if not contributor_indexes:
        return ()
    return (
        _interval_envelope(
            tuple(candidate_widths[index] for index in contributor_indexes)
        ),
    )


def _separator_band_edge_constraint(
    support: SeparatorBandCrossAxisSupport,
    position: PixelInterval,
) -> _EdgeConstraint:
    observation = support.observation
    if position not in {observation.leading_edge, observation.trailing_edge}:
        raise ValueError("separator edge constraint must preserve one observed edge")
    return _EdgeConstraint(
        position=position,
        basis=FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION,
        state=EvidenceState.UNAVAILABLE,
        geometry_state=BoundaryGeometryState.RESOLVED,
        provenance=observation.provenance,
        separator=observation,
        separator_cross_axis=support.measurement,
    )


def _separator_edge_path_measurement(
    constraint: _EdgeConstraint,
):
    observation = constraint.separator
    measurement = constraint.separator_cross_axis
    if (
        constraint.basis != FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION
        or observation is None
        or measurement is None
    ):
        raise ValueError("separator edge measurement requires a raw band constraint")
    if constraint.position == observation.leading_edge:
        return measurement.edge_path(BoundarySide.LEADING)
    if constraint.position == observation.trailing_edge:
        return measurement.edge_path(BoundarySide.TRAILING)
    raise ValueError("separator edge constraint must preserve one observed band edge")


def _separator_edge_path_is_supported(constraint: _EdgeConstraint) -> bool:
    return bool(
        constraint.basis == FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION
        and constraint.separator is not None
        and constraint.separator_cross_axis is not None
        and _separator_edge_path_measurement(constraint).state
        == EvidenceState.SUPPORTED
    )


def _observed_band_edges(
    support: SeparatorBandCrossAxisSupport,
) -> tuple[_EdgeConstraint, _EdgeConstraint]:
    observation = support.observation
    return (
        _separator_band_edge_constraint(
            support,
            observation.leading_edge,
        ),
        _separator_band_edge_constraint(
            support,
            observation.trailing_edge,
        ),
    )


def _separator_band_edges(
    edges: tuple[_EdgeConstraint, _EdgeConstraint],
) -> bool:
    return all(
        edge.basis == FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION
        for edge in edges
    )


def _band_edge_options(
    support: SeparatorBandCrossAxisSupport,
) -> tuple[tuple[_EdgeConstraint, _EdgeConstraint], ...]:
    return (_observed_band_edges(support),)


def _width_between_bands(
    left: SeparatorBandObservation,
    right: SeparatorBandObservation,
    left_edges: tuple[_EdgeConstraint, _EdgeConstraint],
    right_edges: tuple[_EdgeConstraint, _EdgeConstraint],
) -> PixelInterval | None:
    if right.leading_edge.minimum <= left.trailing_edge.maximum:
        return None
    return _positive_interval(
        right_edges[0].position.minus(left_edges[1].position)
    )


def _interval_distance(left: PixelInterval, right: PixelInterval) -> float:
    if left.intersects(right):
        return 0.0
    if left.maximum < right.minimum:
        return right.minimum - left.maximum
    return left.minimum - right.maximum


def _interval_midpoint_residual(
    measured: PixelInterval,
    reference: PixelInterval,
) -> float:
    return abs(measured.midpoint - reference.midpoint) / max(
        MINIMUM_POSITIVE_PIXEL_EXTENT,
        reference.midpoint,
    )


def _normalized_interval_contradiction(
    measured: PixelInterval,
    reference: PixelInterval,
) -> float:
    return _interval_distance(measured, reference) / max(
        MINIMUM_POSITIVE_PIXEL_EXTENT,
        reference.midpoint,
    )


def _minimum_width_residual(
    width: PixelInterval,
    search_widths: tuple[PixelInterval, ...],
) -> float:
    if not search_widths:
        raise ValueError("frame-width search requires at least one interval")
    return min(
        _normalized_interval_contradiction(width, candidate)
        for candidate in search_widths
    )


def _width_search_order_key(
    width: PixelInterval,
    search_widths: tuple[PixelInterval, ...],
) -> tuple[float, ...]:
    return tuple(
        _interval_distance(width, candidate)
        / max(MINIMUM_POSITIVE_PIXEL_EXTENT, candidate.midpoint)
        for candidate in search_widths
    )


def _band_edge_interpretation_is_admissible(
    band_index: int,
    supports: tuple[SeparatorBandCrossAxisSupport, ...],
    selected_edges: tuple[tuple[_EdgeConstraint, _EdgeConstraint], ...],
    physical_width: PixelInterval,
) -> bool:
    band = supports[band_index].observation
    chosen = selected_edges[band_index]
    if _separator_band_edges(chosen):
        return bool(
            band.width_px.minimum > 0.0
            and band.width_px.maximum < physical_width.minimum
        )
    return True


def _indexed_anchor_widths(
    supports: tuple[SeparatorBandCrossAxisSupport, ...],
    selected_edges: tuple[tuple[_EdgeConstraint, _EdgeConstraint], ...],
) -> tuple[PixelInterval, ...] | None:
    widths: list[PixelInterval] = []
    for left_index in range(len(supports) - 1):
        width = _width_between_bands(
            supports[left_index].observation,
            supports[left_index + 1].observation,
            selected_edges[left_index],
            selected_edges[left_index + 1],
        )
        if width is None:
            return None
        widths.append(width)
    return tuple(widths)


def _band_search_order(
    supports: tuple[SeparatorBandCrossAxisSupport, ...],
    edge_options: tuple[tuple[tuple[_EdgeConstraint, _EdgeConstraint], ...], ...],
    start_index: int,
    remaining_count: int,
) -> tuple[int, ...]:
    maximum_index = len(supports) - remaining_count
    return tuple(
        sorted(
            range(start_index, maximum_index + 1),
            key=lambda index: (
                max(
                    all(edge.state == EvidenceState.SUPPORTED for edge in pair)
                    for pair in edge_options[index]
                ),
                max(
                    sum(edge.observation_quality for edge in pair)
                    for pair in edge_options[index]
                ),
                -min(
                    sum(
                        edge.position.maximum - edge.position.minimum
                        for edge in pair
                    )
                    for pair in edge_options[index]
                ),
                -supports[index].observation.leading_edge.midpoint,
            ),
            reverse=True,
        )
    )


def _band_sequence_hypothesis(
    supports: tuple[SeparatorBandCrossAxisSupport, ...],
    band_edges: tuple[tuple[_EdgeConstraint, _EdgeConstraint], ...],
    short_axis: SharedShortAxisSafetySpan,
    frame_width_px: PixelInterval,
    frame_width_hint: PixelInterval,
    indexed_anchor_count: int,
) -> _BandSequenceHypothesis:
    return _BandSequenceHypothesis(
        supports=supports,
        band_edges=band_edges,
        short_axis=short_axis,
        frame_width_px=frame_width_px,
        indexed_anchor_count=indexed_anchor_count,
        paired_band_count=sum(
            _separator_band_edges(pair)
            for pair in band_edges
        ),
        measurement_quality=sum(
            min(
                float(
                    support.measurement.leading_edge_path.longest_supported_ratio
                    or 0.0
                ),
                float(
                    support.measurement.trailing_edge_path.longest_supported_ratio
                    or 0.0
                ),
            )
            for support in supports
            if support.measurement.complete_separator_supported
        ),
        search_order_residual=float(
            _interval_distance(frame_width_px, frame_width_hint)
            / max(MINIMUM_POSITIVE_PIXEL_EXTENT, frame_width_hint.midpoint)
        ),
        uncertainty_px=sum(
            edge.position.maximum - edge.position.minimum
            for pair in band_edges
            for edge in pair
        ),
    )


def _band_sequence_hypotheses(
    supports: tuple[SeparatorBandCrossAxisSupport, ...],
    search_scope: FrameSequenceSearchScope,
    count: int,
    short_axis: SharedShortAxisSafetySpan,
    frame_width: PixelInterval,
    evaluation_budget: int,
) -> tuple[tuple[_BandSequenceHypothesis, ...], int, bool]:
    required = count - 1
    if required <= 0:
        raise ValueError(
            "separator sequence hypotheses require an internal frame boundary"
        )
    interior = _interior_separator_supports(supports, search_scope)
    if len(interior) < required:
        return (), 0, False
    hypotheses: list[_BandSequenceHypothesis] = []
    evaluations = 0
    search_truncated = False
    search_width = PixelInterval(
        MINIMUM_POSITIVE_PIXEL_EXTENT,
        float(search_scope.holder_safety.box.width),
    )
    edge_options = tuple(_band_edge_options(item) for item in interior)

    def search(
        start_index: int,
        selected_supports: tuple[SeparatorBandCrossAxisSupport, ...],
        selected_edges: tuple[tuple[_EdgeConstraint, _EdgeConstraint], ...],
    ) -> None:
        nonlocal evaluations, search_truncated
        if search_truncated:
            return
        if len(selected_supports) == required:
            indexed_widths = _indexed_anchor_widths(
                selected_supports,
                selected_edges,
            )
            if indexed_widths is None:
                return
            width_consensus = (
                _strict_majority_width_consensus(indexed_widths)
                if indexed_widths
                else (search_width, 0)
            )
            if width_consensus is None:
                return
            anchor_width, indexed_anchor_count = width_consensus
            if indexed_widths and not all(
                _band_edge_interpretation_is_admissible(
                    band_index,
                    selected_supports,
                    selected_edges,
                    anchor_width,
                )
                for band_index in range(len(selected_supports))
            ):
                return
            hypothesis = _band_sequence_hypothesis(
                selected_supports,
                selected_edges,
                short_axis,
                anchor_width,
                frame_width,
                indexed_anchor_count,
            )
            hypotheses.append(hypothesis)
            return

        remaining_count = required - len(selected_supports)
        for observation_index in _band_search_order(
            interior,
            edge_options,
            start_index,
            remaining_count,
        ):
            support = interior[observation_index]
            observation = support.observation
            for edges in edge_options[observation_index]:
                if evaluations >= evaluation_budget:
                    search_truncated = True
                    return
                evaluations += 1
                if selected_supports:
                    measured_width = _width_between_bands(
                        selected_supports[-1].observation,
                        observation,
                        selected_edges[-1],
                        edges,
                    )
                    if measured_width is None:
                        continue
                    existing_widths = _indexed_anchor_widths(
                        next_supports := (*selected_supports, support),
                        next_edges := (*selected_edges, edges),
                    )
                    width_consensus = (
                        None
                        if existing_widths is None
                        else _strict_majority_width_consensus(existing_widths)
                    )
                    if width_consensus is None:
                        continue
                else:
                    next_supports = (support,)
                    next_edges = (edges,)
                    width_consensus = (search_width, 0)
                resolved_neighbor_index = len(selected_supports) - 1
                if (
                    selected_supports
                    and not _band_edge_interpretation_is_admissible(
                        resolved_neighbor_index,
                        next_supports,
                        next_edges,
                        width_consensus[0],
                    )
                ):
                    continue
                search(
                    observation_index + 1,
                    next_supports,
                    next_edges,
                )
                if search_truncated:
                    return

    search(0, (), ())
    return tuple(hypotheses), evaluations, search_truncated


def _external_constraint(
    path: GrayBoundaryPathObservation,
    *,
    position: PixelInterval | None = None,
) -> _EdgeConstraint:
    return _EdgeConstraint(
        position=path.position if position is None else position,
        basis=FrameBoundarySource.GRAY_PATH_OBSERVATION,
        state=EvidenceState.UNAVAILABLE,
        geometry_state=BoundaryGeometryState.RESOLVED,
        provenance=path.provenance,
        path=path,
    )


def _holder_axis_interval(holder: Box, axis: BoundaryAxis) -> PixelInterval:
    if axis == BoundaryAxis.LONG:
        return PixelInterval(float(holder.left), float(holder.right))
    return PixelInterval(float(holder.top), float(holder.bottom))


def _holder_boundary_supports_path(
    path: GrayBoundaryPathObservation,
    boundary: HolderBoundaryObservation | None,
) -> bool:
    return bool(
        boundary is not None
        and any(
            supporting.provenance.observation_id
            == path.provenance.observation_id
            for supporting in boundary.supporting_paths
        )
    )


def _external_constraint_with_holder_consensus(
    path: GrayBoundaryPathObservation,
    boundary: HolderBoundaryObservation | None,
    holder: Box,
) -> tuple[_EdgeConstraint | None, bool]:
    supports_holder_boundary = _holder_boundary_supports_path(path, boundary)
    position = (
        boundary.position
        if supports_holder_boundary and boundary is not None
        else path.position
    ).intersection(_holder_axis_interval(holder, path.axis))
    if position is None:
        return None, supports_holder_boundary
    constraint = _external_constraint(path, position=position)
    if supports_holder_boundary and boundary is not None:
        constraint = replace(constraint, external_side=boundary.side)
    return constraint, supports_holder_boundary


def _visible_width(
    leading: _EdgeConstraint,
    trailing: _EdgeConstraint,
) -> PixelInterval | None:
    return _positive_interval(trailing.position.minus(leading.position))


def _endpoint_residual(
    visible_width: PixelInterval,
    frame_width: PixelInterval,
) -> float:
    if visible_width.intersects(frame_width):
        return 0.0
    return _interval_distance(visible_width, frame_width) / max(
        MINIMUM_POSITIVE_PIXEL_EXTENT,
        frame_width.midpoint,
    )


def _admissible_frame_endpoints(
    paths: tuple[GrayBoundaryPathObservation, ...],
    inner: _EdgeConstraint,
    frame_width: PixelInterval,
    holder_boundary: HolderBoundaryObservation | None,
    holder: Box,
    *,
    leading: bool,
    additional_constraints: tuple[_EdgeConstraint, ...] = (),
) -> tuple[_EdgeConstraint, ...]:
    ranked: list[tuple[tuple[float, float, float, float], _EdgeConstraint]] = []
    candidates: list[tuple[_EdgeConstraint, bool]] = []
    for path in paths:
        constraint, holder_clip_supported = (
            _external_constraint_with_holder_consensus(
                path,
                holder_boundary,
                holder,
            )
        )
        if constraint is None:
            continue
        candidates.append((constraint, holder_clip_supported))
    expected_side = BoundarySide.LEADING if leading else BoundarySide.TRAILING
    candidates.extend(
        (constraint, constraint.external_side == expected_side)
        for constraint in additional_constraints
    )
    for constraint, holder_clip_supported in dict.fromkeys(candidates):
        if leading:
            if constraint.position.minimum >= inner.position.maximum:
                continue
            visible = _visible_width(constraint, inner)
        else:
            if constraint.position.maximum <= inner.position.minimum:
                continue
            visible = _visible_width(inner, constraint)
        if visible is None:
            continue
        residual = _endpoint_residual(visible, frame_width)
        if (
            residual > 0.0
            and not holder_clip_supported
            and not _measurement_intervals_are_compatible(
                visible,
                frame_width,
            )
        ):
            continue
        rank = (
            -float(residual),
            min(visible.midpoint, frame_width.midpoint),
            constraint.measurement_quality,
            -(constraint.position.maximum - constraint.position.minimum),
        )
        ranked.append((rank, constraint))
    return tuple(
        constraint
        for _, constraint in sorted(
            ranked,
            key=lambda item: item[0],
            reverse=True,
        )
    )


def _endpoint_supports_holder(
    endpoint: _EdgeConstraint,
    boundary: HolderBoundaryObservation | None,
) -> bool:
    return bool(
        endpoint.path is not None
        and _holder_boundary_supports_path(endpoint.path, boundary)
    )


def _frame_width_for_endpoints(
    hypothesis: _BandSequenceHypothesis,
    leading_endpoint: _EdgeConstraint,
    trailing_endpoint: _EdgeConstraint,
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
) -> PixelInterval | None:
    first_edges = hypothesis.band_edges[0]
    last_edges = hypothesis.band_edges[-1]
    leading_width = _visible_width(leading_endpoint, first_edges[0])
    trailing_width = _visible_width(last_edges[1], trailing_endpoint)
    if leading_width is None or trailing_width is None:
        return None

    if hypothesis.indexed_anchor_count == 0:
        shared = leading_width.intersection(trailing_width)
        if shared is not None:
            return _positive_interval(shared)
        if _measurement_intervals_are_compatible(
            leading_width,
            trailing_width,
        ):
            return _positive_interval(
                _interval_envelope((leading_width, trailing_width))
            )
        leading_clipped = _endpoint_supports_holder(
            leading_endpoint,
            holder_boundaries.get(BoundarySide.LEADING),
        )
        trailing_clipped = _endpoint_supports_holder(
            trailing_endpoint,
            holder_boundaries.get(BoundarySide.TRAILING),
        )
        if leading_clipped == trailing_clipped:
            return None
        return trailing_width if leading_clipped else leading_width

    shared = hypothesis.frame_width_px
    for visible_width, clipped in (
        (
            leading_width,
            _endpoint_supports_holder(
                leading_endpoint,
                holder_boundaries.get(BoundarySide.LEADING),
            ),
        ),
        (
            trailing_width,
            _endpoint_supports_holder(
                trailing_endpoint,
                holder_boundaries.get(BoundarySide.TRAILING),
            ),
        ),
    ):
        if _measurement_intervals_are_compatible(shared, visible_width):
            continue
        if not clipped or visible_width.minimum > shared.maximum:
            return None
    return _positive_interval(shared)


def _refine_dimension_constraint(
    constraint: _EdgeConstraint,
    position: PixelInterval,
) -> _EdgeConstraint | None:
    if constraint.basis != FrameBoundarySource.DIMENSION_CONSTRAINED:
        return (
            constraint
            if _measurement_intervals_are_compatible(
                constraint.position,
                position,
            )
            else None
        )
    refined = constraint.position.intersection(position)
    if refined is None:
        return None
    return _EdgeConstraint(
        position=refined,
        basis=constraint.basis,
        state=constraint.state,
        geometry_state=constraint.geometry_state,
        provenance=constraint.provenance,
    )


def _refine_frame_edges(
    leading: _EdgeConstraint,
    trailing: _EdgeConstraint,
    frame_width: PixelInterval,
    *,
    allow_underwidth: bool,
) -> tuple[_EdgeConstraint, _EdgeConstraint] | None:
    current_leading = leading
    current_trailing = trailing
    for _ in range(BIDIRECTIONAL_REFINEMENT_PASSES):
        refined_trailing = _refine_dimension_constraint(
            current_trailing,
            current_leading.position.plus(frame_width),
        )
        if refined_trailing is None:
            if not allow_underwidth:
                return None
        else:
            current_trailing = refined_trailing
        refined_leading = _refine_dimension_constraint(
            current_leading,
            current_trailing.position.minus(frame_width),
        )
        if refined_leading is None:
            if not allow_underwidth:
                return None
        else:
            current_leading = refined_leading
    width = _visible_width(current_leading, current_trailing)
    if width is None:
        return None
    if (
        not allow_underwidth
        and not _measurement_intervals_are_compatible(width, frame_width)
    ):
        return None
    return current_leading, current_trailing


def _sequence_constraints_fit_physical_scale(
    constraints: tuple[_MeasuredFrameConstraint, ...],
    physical_scale: FrameWidthPhysicalScaleConstraint,
) -> bool:
    return all(
        constraint.leading_holder_clip_supported
        or constraint.trailing_holder_clip_supported
        or constraint.width_px.intersects(physical_scale.width_px)
        for constraint in constraints
    )


def _resolution(
    frame_index: int,
    side: BoundarySide,
    constraint: _EdgeConstraint,
) -> tuple[ResolvedFrameBoundary, FrameEdgeAssignment | None]:
    observation = constraint.path or constraint.separator
    observed = constraint.basis in {
        FrameBoundarySource.GRAY_PATH_OBSERVATION,
        FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION,
    }
    anchor = (
        BoundaryAnchor(
            observation=observation,
            physical_role=side,
            role_state=constraint.state,
            role_authority=(
                BoundaryRoleAuthority.DIRECT_MEASUREMENT
                if constraint.state == EvidenceState.SUPPORTED
                else BoundaryRoleAuthority.UNAVAILABLE
            ),
            role_provenance=constraint.provenance,
        )
        if observed and observation is not None
        else None
    )
    resolution = ResolvedFrameBoundary(
        position=constraint.position,
        source=constraint.basis,
        geometry_state=constraint.geometry_state,
        boundary_anchor=anchor,
        inference_provenance=(None if anchor is not None else constraint.provenance),
    )
    if constraint.path is None:
        return resolution, None
    return (
        resolution,
        FrameEdgeAssignment(
            frame_index=frame_index,
            side=side,
            observation=constraint.path,
            resolution=resolution,
        ),
    )


def _separator_edge_with_supported_role(
    constraint: _EdgeConstraint,
) -> _EdgeConstraint:
    if (
        constraint.basis != FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION
        or constraint.separator is None
        or constraint.separator_cross_axis is None
        or not _separator_edge_path_is_supported(constraint)
    ):
        raise ValueError("separator role requires a supported raw band observation")
    return replace(constraint, state=EvidenceState.SUPPORTED)


def _separator_pair_fits_sequence(
    trailing: _EdgeConstraint,
    leading: _EdgeConstraint,
    frame_width: PixelInterval,
) -> bool:
    band = trailing.separator
    return bool(
        band is not None
        and band is leading.separator
        and trailing.separator_cross_axis is leading.separator_cross_axis
        and trailing.external_side is None
        and leading.external_side is None
        and trailing.separator_cross_axis is not None
        and trailing.separator_cross_axis.complete_separator_supported
        and trailing.position == band.leading_edge
        and leading.position == band.trailing_edge
        and band.width_px.minimum > 0.0
        and band.width_px.maximum < frame_width.minimum
    )


def _candidate_specific_separator_edge_roles(
    constraints: tuple[_MeasuredFrameConstraint, ...],
) -> tuple[_MeasuredFrameConstraint, ...]:
    updated = list(constraints)
    for boundary_index in range(1, len(updated)):
        left = updated[boundary_index - 1]
        right = updated[boundary_index]
        if _separator_edge_path_is_supported(left.trailing):
            updated[boundary_index - 1] = replace(
                left,
                trailing=_separator_edge_with_supported_role(left.trailing),
            )
        if _separator_edge_path_is_supported(right.leading):
            updated[boundary_index] = replace(
                right,
                leading=_separator_edge_with_supported_role(right.leading),
            )
    return tuple(updated)


def _candidate_specific_holder_band_roles(
    constraints: tuple[_MeasuredFrameConstraint, ...],
    frame_width: PixelInterval,
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
) -> tuple[_MeasuredFrameConstraint, ...]:
    updated = list(constraints)
    internal_sequence_complete = len(updated) > 1 and all(
        _separator_pair_fits_sequence(
            updated[boundary_index - 1].trailing,
            updated[boundary_index].leading,
            frame_width,
        )
        for boundary_index in range(1, len(updated))
    )
    if internal_sequence_complete:
        for slot_index, side in (
            (0, BoundarySide.LEADING),
            (len(updated) - 1, BoundarySide.TRAILING),
        ):
            boundary = (
                updated[slot_index].leading
                if side == BoundarySide.LEADING
                else updated[slot_index].trailing
            )
            band = boundary.separator
            holder_boundary = holder_boundaries.get(side)
            if (
                band is None
                or boundary.external_side != side
                or boundary.separator_cross_axis is None
                or not _separator_edge_path_is_supported(boundary)
                or holder_boundary is None
                or band.width_px.maximum >= frame_width.minimum
                or not PixelInterval(
                    band.leading_edge.minimum,
                    band.trailing_edge.maximum,
                ).intersects(holder_boundary.position)
            ):
                continue
            supported = _separator_edge_with_supported_role(boundary)
            if side == BoundarySide.LEADING:
                updated[slot_index] = replace(
                    updated[slot_index],
                    leading=supported,
                )
            else:
                updated[slot_index] = replace(
                    updated[slot_index],
                    trailing=supported,
                )
    return tuple(updated)


def _dimension_constraint(
    anchor: _EdgeConstraint,
    hypothesis: _DimensionPlacementHypothesis,
    position: PixelInterval,
    side: BoundarySide,
) -> _EdgeConstraint:
    dependencies = tuple(
        sorted(
            {
                MeasurementIdentity.FRAME_DIMENSIONS,
                anchor.provenance.root_measurement,
                *anchor.provenance.dependencies,
            },
            key=lambda item: item.value,
        )
    )
    return _EdgeConstraint(
        position=position,
        basis=FrameBoundarySource.DIMENSION_CONSTRAINED,
        state=EvidenceState.UNAVAILABLE,
        geometry_state=(
            BoundaryGeometryState.RESOLVED
            if hypothesis.boundary_anchors
            else BoundaryGeometryState.UNRESOLVED
        ),
        provenance=MeasurementProvenance(
            root_measurement=MeasurementIdentity.FRAME_GEOMETRY,
            observation_id=ObservationId(
                "dimension_boundary:"
                f"{side.value}:{anchor.provenance.observation_id}:"
                f"{hypothesis.width_px.minimum:.6f}:"
                f"{hypothesis.width_px.maximum:.6f}:"
                f"{position.minimum:.6f}:{position.maximum:.6f}"
            ),
            dependencies=dependencies,
            description="frame boundary inferred from candidate common width",
            boundary_anchors=tuple(
                dict.fromkeys(
                    (
                        anchor.provenance.observation_id,
                        *hypothesis.boundary_anchors,
                    )
                )
            ),
        ),
    )


def _focused_edge_constraints(
    inferred: _EdgeConstraint,
    candidates: tuple[tuple[_EdgeConstraint, bool], ...],
) -> tuple[_EdgeConstraint, ...]:
    observed = tuple(
        candidate
        for candidate, _ in candidates
        if candidate.position.intersects(inferred.position)
    )
    return tuple(dict.fromkeys((*observed, inferred)))


def _dimension_seed_candidates(
    candidates: tuple[tuple[_EdgeConstraint, bool], ...],
) -> tuple[tuple[_EdgeConstraint, bool], ...]:
    return tuple(
        item
        for item in candidates
        if (
            item[0].external_side is not None
            or _separator_edge_path_is_supported(item[0])
        )
    )


def _has_supported_internal_separator_edge_seed(
    candidates: tuple[tuple[_EdgeConstraint, bool], ...],
) -> bool:
    return any(
        edge.external_side is None
        and _separator_edge_path_is_supported(edge)
        for edge, _ in candidates
    )


def _dimension_frame_constraints(
    leading_seeds: tuple[tuple[_EdgeConstraint, bool], ...],
    trailing_seeds: tuple[tuple[_EdgeConstraint, bool], ...],
    leading_candidates: tuple[tuple[_EdgeConstraint, bool], ...],
    trailing_candidates: tuple[tuple[_EdgeConstraint, bool], ...],
    width_hypotheses: tuple[_DimensionPlacementHypothesis, ...],
    holder_axis: PixelInterval,
    search_widths: tuple[PixelInterval, ...],
    frame_width_hint: PixelInterval,
) -> tuple[_MeasuredFrameConstraint, ...]:
    constraints: list[_MeasuredFrameConstraint] = []
    for hypothesis in width_hypotheses:
        search_order_residual = _minimum_width_residual(
            hypothesis.width_px,
            search_widths,
        )
        for leading, _ in leading_seeds:
            for offset in (0,):
                leading_position = leading.position.plus(
                    hypothesis.width_px.scaled(float(offset))
                ).intersection(holder_axis)
                trailing_position = leading.position.plus(
                    hypothesis.width_px.scaled(float(offset + 1))
                ).intersection(holder_axis)
                if leading_position is None or trailing_position is None:
                    continue
                frame_leading = (
                    leading
                    if offset == 0
                    else _dimension_constraint(
                        leading,
                        hypothesis,
                        leading_position,
                        BoundarySide.LEADING,
                    )
                )
                inferred_trailing = _dimension_constraint(
                    leading,
                    hypothesis,
                    trailing_position,
                    BoundarySide.TRAILING,
                )
                leading_options = (
                    (frame_leading,)
                    if offset == 0
                    else _focused_edge_constraints(
                        frame_leading,
                        leading_candidates,
                    )
                )
                trailing_options = _focused_edge_constraints(
                    inferred_trailing,
                    trailing_candidates,
                )
                for focused_leading in leading_options:
                    for focused_trailing in trailing_options:
                        width = _visible_width(focused_leading, focused_trailing)
                        if width is None:
                            continue
                        shared = width.intersection(hypothesis.width_px)
                        if shared is None:
                            continue
                        constraints.append(
                            _MeasuredFrameConstraint(
                                leading=focused_leading,
                                trailing=focused_trailing,
                                width_px=shared,
                                full_width_hypothesis_admissible=True,
                                leading_holder_clip_supported=False,
                                trailing_holder_clip_supported=False,
                                search_order_residual=search_order_residual,
                                frame_width_hint_residual=_minimum_width_residual(
                                    shared,
                                    (frame_width_hint,),
                                ),
                            )
                        )
        for trailing, _ in trailing_seeds:
            for offset in (0,):
                trailing_position = trailing.position.minus(
                    hypothesis.width_px.scaled(float(offset))
                ).intersection(holder_axis)
                leading_position = trailing.position.minus(
                    hypothesis.width_px.scaled(float(offset + 1))
                ).intersection(holder_axis)
                if leading_position is None or trailing_position is None:
                    continue
                inferred_leading = _dimension_constraint(
                    trailing,
                    hypothesis,
                    leading_position,
                    BoundarySide.LEADING,
                )
                frame_trailing = (
                    trailing
                    if offset == 0
                    else _dimension_constraint(
                        trailing,
                        hypothesis,
                        trailing_position,
                        BoundarySide.TRAILING,
                    )
                )
                leading_options = _focused_edge_constraints(
                    inferred_leading,
                    leading_candidates,
                )
                trailing_options = (
                    (frame_trailing,)
                    if offset == 0
                    else _focused_edge_constraints(
                        frame_trailing,
                        trailing_candidates,
                    )
                )
                for focused_leading in leading_options:
                    for focused_trailing in trailing_options:
                        width = _visible_width(focused_leading, focused_trailing)
                        if width is None:
                            continue
                        shared = width.intersection(hypothesis.width_px)
                        if shared is None:
                            continue
                        constraints.append(
                            _MeasuredFrameConstraint(
                                leading=focused_leading,
                                trailing=focused_trailing,
                                width_px=shared,
                                full_width_hypothesis_admissible=True,
                                leading_holder_clip_supported=False,
                                trailing_holder_clip_supported=False,
                                search_order_residual=search_order_residual,
                                frame_width_hint_residual=_minimum_width_residual(
                                    shared,
                                    (frame_width_hint,),
                                ),
                            )
                        )
    return tuple(dict.fromkeys(constraints))


def _separator_edge_candidates(
    separator_supports: tuple[SeparatorBandCrossAxisSupport, ...],
    search_scope: FrameSequenceSearchScope,
) -> tuple[
    tuple[tuple[_EdgeConstraint, bool], ...],
    tuple[tuple[_EdgeConstraint, bool], ...],
]:
    holder_boundaries = _holder_boundaries(search_scope)
    interior_observations = set(
        _interior_separator_observations(separator_supports, search_scope)
    )
    leading_holder = holder_boundaries.get(BoundarySide.LEADING)
    trailing_holder = holder_boundaries.get(BoundarySide.TRAILING)
    leading_candidates: list[tuple[_EdgeConstraint, bool]] = []
    trailing_candidates: list[tuple[_EdgeConstraint, bool]] = []
    for support in separator_supports:
        preceding_trailing, following_leading = _observed_band_edges(support)
        band_span = PixelInterval(
            support.observation.leading_edge.minimum,
            support.observation.trailing_edge.maximum,
        )
        touches_leading_holder = bool(
            leading_holder is not None
            and band_span.intersects(leading_holder.position)
        )
        touches_trailing_holder = bool(
            trailing_holder is not None
            and band_span.intersects(trailing_holder.position)
        )
        if support in interior_observations and _separator_edge_path_is_supported(
            preceding_trailing
        ):
            trailing_candidates.append((preceding_trailing, False))
        if support in interior_observations and _separator_edge_path_is_supported(
            following_leading
        ):
            leading_candidates.append((following_leading, False))
        if _separator_edge_path_is_supported(following_leading):
            leading_candidates.append(
                (
                    replace(
                        following_leading,
                        external_side=BoundarySide.LEADING,
                        state=EvidenceState.UNAVAILABLE,
                    ),
                    touches_leading_holder,
                )
            )
        if _separator_edge_path_is_supported(preceding_trailing):
            trailing_candidates.append(
                (
                    replace(
                        preceding_trailing,
                        external_side=BoundarySide.TRAILING,
                        state=EvidenceState.UNAVAILABLE,
                    ),
                    touches_trailing_holder,
                )
            )
    return tuple(dict.fromkeys(leading_candidates)), tuple(
        dict.fromkeys(trailing_candidates)
    )


def _separator_geometry_edge_candidates(
    separator_supports: tuple[SeparatorBandCrossAxisSupport, ...],
    search_scope: FrameSequenceSearchScope,
) -> tuple[
    tuple[tuple[_EdgeConstraint, bool], ...],
    tuple[tuple[_EdgeConstraint, bool], ...],
]:
    holder = search_scope.holder_safety.box
    leading_candidates: list[tuple[_EdgeConstraint, bool]] = []
    trailing_candidates: list[tuple[_EdgeConstraint, bool]] = []
    for support in separator_supports:
        observation = support.observation
        if (
            observation.leading_edge.minimum <= float(holder.left)
            or observation.trailing_edge.maximum >= float(holder.right)
        ):
            continue
        preceding_trailing, following_leading = _observed_band_edges(support)
        trailing_candidates.append((preceding_trailing, False))
        leading_candidates.append((following_leading, False))
    return tuple(dict.fromkeys(leading_candidates)), tuple(
        dict.fromkeys(trailing_candidates)
    )


def prepare_frame_sequence_search_index(
    search_scope: FrameSequenceSearchScope,
    separator_supports: SeparatorSupportSet,
) -> FrameSequenceSearchIndex:
    paths = _axis_paths(search_scope, BoundaryAxis.LONG)
    holder_boundaries = _holder_boundaries(search_scope)
    leading_candidates: list[tuple[_EdgeConstraint, bool]] = []
    trailing_candidates: list[tuple[_EdgeConstraint, bool]] = []
    for path in paths:
        leading, leading_holder_supported = _external_constraint_with_holder_consensus(
            path,
            holder_boundaries.get(BoundarySide.LEADING),
            search_scope.holder_safety.box,
        )
        trailing, trailing_holder_supported = _external_constraint_with_holder_consensus(
            path,
            holder_boundaries.get(BoundarySide.TRAILING),
            search_scope.holder_safety.box,
        )
        if leading is not None:
            leading_candidates.append((leading, leading_holder_supported))
        if trailing is not None:
            trailing_candidates.append((trailing, trailing_holder_supported))
    separator_leading, separator_trailing = _separator_edge_candidates(
        separator_supports.canonical_supports,
        search_scope,
    )
    leading_candidates.extend(separator_leading)
    trailing_candidates.extend(separator_trailing)
    leading_candidates.sort(
        key=lambda item: (
            item[0].position.midpoint,
            item[0].provenance.observation_id,
        )
    )
    trailing_candidates.sort(
        key=lambda item: (
            item[0].position.midpoint,
            item[0].provenance.observation_id,
        )
    )
    observed_constraints: list[_MeasuredFrameConstraint] = []
    evaluations = 0
    for leading, leading_holder_supported in leading_candidates:
        for trailing, trailing_holder_supported in trailing_candidates:
            if trailing.position.minimum <= leading.position.maximum:
                continue
            width = _visible_width(leading, trailing)
            if width is None:
                continue
            leading_clip_supported = leading_holder_supported
            trailing_clip_supported = trailing_holder_supported
            evaluations += 1
            observed_constraints.append(
                _MeasuredFrameConstraint(
                    leading=leading,
                    trailing=trailing,
                    width_px=width,
                    full_width_hypothesis_admissible=True,
                    leading_holder_clip_supported=leading_clip_supported,
                    trailing_holder_clip_supported=trailing_clip_supported,
                    search_order_residual=0.0,
                    frame_width_hint_residual=0.0,
                )
            )
    canonical_observed = _canonical_measured_frame_constraints(
        tuple(observed_constraints)
    )
    width_hypotheses = _non_dominated_width_hypotheses(
        _measured_width_hypotheses(canonical_observed)
    )
    recurring_width_hypotheses = _recurring_boundary_width_hypotheses(
        tuple(
            dict.fromkeys(
                edge
                for edge, _ in (*leading_candidates, *trailing_candidates)
            )
        )
    )
    return FrameSequenceSearchIndex(
        separator_supports=separator_supports,
        leading_candidates=tuple(leading_candidates),
        trailing_candidates=tuple(trailing_candidates),
        observed_constraints=canonical_observed,
        width_hypotheses=width_hypotheses,
        recurring_width_hypotheses=recurring_width_hypotheses,
        preparation_evaluations=evaluations,
    )


def _measured_frame_search_space(
    search_index: FrameSequenceSearchIndex,
    search_widths: tuple[PixelInterval, ...],
    frame_width_hint: PixelInterval,
    physical_scale_constraint: FrameWidthPhysicalScaleConstraint | None,
) -> _MeasuredFrameSearchSpace:
    canonical_observed = tuple(
        replace(
            constraint,
            search_order_residual=_minimum_width_residual(
                constraint.width_px,
                search_widths,
            ),
            frame_width_hint_residual=_minimum_width_residual(
                constraint.width_px,
                (frame_width_hint,),
            ),
        )
        for constraint in search_index.observed_constraints
        if (
            constraint.leading_holder_clip_supported
            or constraint.trailing_holder_clip_supported
            or _width_satisfies_physical_scale(
                constraint.width_px,
                physical_scale_constraint,
            )
        )
    )
    width_hypotheses = tuple(
        sorted(
            (
                hypothesis
                for hypothesis in search_index.width_hypotheses
                if _width_satisfies_physical_scale(
                    hypothesis.width_px,
                    physical_scale_constraint,
                )
            ),
            key=lambda hypothesis: (
                _width_search_order_key(hypothesis.width_px, search_widths),
                -hypothesis.contributor_count,
                hypothesis.width_px.maximum - hypothesis.width_px.minimum,
                hypothesis.width_px.midpoint,
                hypothesis.boundary_anchors,
            ),
        )
    )
    recurring_width_hypotheses = tuple(
        sorted(
            (
                hypothesis
                for hypothesis in search_index.recurring_width_hypotheses
                if _width_satisfies_physical_scale(
                    hypothesis.width_px,
                    physical_scale_constraint,
                )
            ),
            key=lambda hypothesis: (
                _width_search_order_key(
                    hypothesis.width_px,
                    search_widths,
                ),
                _interval_distance(
                    hypothesis.width_px,
                    frame_width_hint,
                )
                / max(
                    MINIMUM_POSITIVE_PIXEL_EXTENT,
                    frame_width_hint.midpoint,
                ),
                -hypothesis.contributor_count,
                _interval_midpoint_residual(
                    hypothesis.width_px,
                    frame_width_hint,
                ),
                hypothesis.width_px.maximum - hypothesis.width_px.minimum,
                hypothesis.width_px.midpoint,
            ),
        )
    )
    return _MeasuredFrameSearchSpace(
        leading_candidates=search_index.leading_candidates,
        trailing_candidates=search_index.trailing_candidates,
        observed_constraints=canonical_observed,
        width_hypotheses=width_hypotheses,
        recurring_width_hypotheses=recurring_width_hypotheses,
    )


def _spacing_from_frame_edges(
    boundary_index: int,
    trailing: ResolvedFrameBoundary,
    leading: ResolvedFrameBoundary,
    *,
    separator_observation_supported: bool = True,
) -> InterFrameSpacing:
    trailing_provenance = trailing.measurement_provenance
    leading_provenance = leading.measurement_provenance
    same_observation = bool(
        trailing.boundary_anchor is not None
        and leading.boundary_anchor is not None
        and trailing_provenance.observation_id
        == leading_provenance.observation_id
    )
    shared_photo_edge = bool(
        same_observation
        and trailing.source == FrameBoundarySource.GRAY_PATH_OBSERVATION
        and leading.source == FrameBoundarySource.GRAY_PATH_OBSERVATION
        and boundary_role_is_independent_physical_measurement(trailing)
        and boundary_role_is_independent_physical_measurement(leading)
    )
    signed_width = (
        PixelInterval.exact(0.0)
        if shared_photo_edge
        else leading.position.minus(trailing.position)
    )
    measured_separator = bool(
        separator_observation_supported
        and
        signed_width.minimum > 0.0
        and same_observation
        and trailing.source == FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION
        and leading.source == FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION
    )
    measured_contact = bool(
        shared_photo_edge
        or (
            signed_width.minimum == 0.0
            and signed_width.maximum == 0.0
            and same_observation
        )
    )
    distinct_observed_edges = bool(
        boundary_role_is_independent_physical_measurement(trailing)
        and boundary_role_is_independent_physical_measurement(leading)
        and trailing_provenance.observation_id
        != leading_provenance.observation_id
    )
    observed = bool(
        boundary_role_is_independent_physical_measurement(trailing)
        and boundary_role_is_independent_physical_measurement(leading)
        and (
            measured_separator
            or measured_contact
            or distinct_observed_edges
        )
    )
    provenance = MeasurementProvenance(
        root_measurement=(
            MeasurementIdentity.PHOTO_EDGES
            if observed
            else MeasurementIdentity.FRAME_GEOMETRY
        ),
        observation_id=ObservationId(
            f"inter_frame_spacing:{boundary_index}:"
            f"{trailing_provenance.observation_id}:"
            f"{leading_provenance.observation_id}"
        ),
        dependencies=tuple(
            dict.fromkeys(
                (
                    trailing_provenance.root_measurement,
                    leading_provenance.root_measurement,
                )
            )
        ),
        description=(
            "measured inter-frame spacing"
            if observed
            else "inter-frame spacing hypothesis"
        ),
        boundary_anchors=tuple(
            dict.fromkeys(
                (
                    trailing_provenance.observation_id,
                    leading_provenance.observation_id,
                )
            )
        ),
    )
    return InterFrameSpacing(
        boundary=InterFrameBoundaryReference(None, boundary_index),
        signed_width_px=signed_width,
        provenance=provenance,
        basis=(
            InterFrameSpacingBasis.OBSERVED
            if observed
            else InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS
        ),
    )


def _measured_spacing(
    boundary_index: int,
    left: FrameSlot,
    right: FrameSlot,
) -> InterFrameSpacing:
    return _spacing_from_frame_edges(
        boundary_index,
        left.trailing,
        right.leading,
    )


def _uncorroborated_overlap_extent(
    spacings: tuple[InterFrameSpacing, ...],
) -> float:
    return sum(
        max(0.0, -spacing.signed_width_px.maximum)
        for spacing in spacings
        if spacing.basis == InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS
    )


def _unexplained_spacing_extent(
    spacings: tuple[InterFrameSpacing, ...],
) -> float:
    return sum(
        max(0.0, spacing.signed_width_px.minimum)
        for spacing in spacings
        if spacing.basis == InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS
    )


def _uncorroborated_contact_count(
    spacings: tuple[InterFrameSpacing, ...],
) -> int:
    return sum(
        spacing.kind == InterFrameSpacingKind.CONTACT
        and spacing.basis == InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS
        for spacing in spacings
    )


def _inferred_boundary_count(slots: tuple[FrameSlot, ...]) -> int:
    observed_sources = {
        FrameBoundarySource.GRAY_PATH_OBSERVATION,
        FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION,
    }
    return sum(
        boundary.source not in observed_sources
        for slot in slots
        for boundary in (slot.leading, slot.trailing)
    )


def _indexed_anchor_distance_constraints(
    assignments: tuple[SeparatorBandAssignment, ...],
    spacings: tuple[InterFrameSpacing, ...],
    frame_width: PixelInterval,
) -> tuple[IndexedAnchorDistanceConstraint, ...]:
    by_boundary = {
        spacing.boundary.boundary_index: spacing for spacing in spacings
    }
    ordered = tuple(
        sorted(assignments, key=lambda item: item.boundary_index)
    )
    constraints: list[IndexedAnchorDistanceConstraint] = []
    for first, second in zip(ordered, ordered[1:]):
        if second.boundary_index <= first.boundary_index:
            raise ValueError("indexed separator assignments must be unique")
        intermediate_spacing = PixelInterval.exact(0.0)
        spacing_complete = True
        for boundary_index in range(
            first.boundary_index + 1,
            second.boundary_index,
        ):
            spacing = by_boundary.get(boundary_index)
            if spacing is None:
                spacing_complete = False
                break
            intermediate_spacing = intermediate_spacing.plus(
                spacing.signed_width_px
            )
        if not spacing_complete:
            continue
        anchor_span = second.preceding_trailing_edge.position.minus(
            first.following_leading_edge.position
        )
        frame_index_distance = second.boundary_index - first.boundary_index
        implied_frame_width = anchor_span.minus(
            intermediate_spacing
        ).scaled(1.0 / float(frame_index_distance))
        if (
            implied_frame_width.minimum <= 0.0
            or not _measurement_intervals_are_compatible(
                implied_frame_width,
                frame_width,
            )
            or first.observation.provenance.observation_id
            == second.observation.provenance.observation_id
        ):
            continue
        constraints.append(
            IndexedAnchorDistanceConstraint(
                first_boundary_index=first.boundary_index,
                second_boundary_index=second.boundary_index,
                anchor_span_px=anchor_span,
                intermediate_spacing_px=intermediate_spacing,
                implied_frame_width_px=implied_frame_width,
                provenance=MeasurementProvenance(
                    root_measurement=MeasurementIdentity.FRAME_GEOMETRY,
                    observation_id=ObservationId(
                        "indexed_anchor_distance:"
                        f"{first.boundary_index}:{second.boundary_index}:"
                        f"{first.observation.provenance.observation_id}:"
                        f"{second.observation.provenance.observation_id}"
                    ),
                    dependencies=(
                        MeasurementIdentity.SEPARATOR_PROFILE,
                        MeasurementIdentity.FRAME_DIMENSIONS,
                    ),
                    description=(
                        "candidate-indexed separator anchors with retained "
                        "intermediate spacing"
                    ),
                    boundary_anchors=(
                        first.observation.provenance.observation_id,
                        second.observation.provenance.observation_id,
                    ),
                ),
            )
        )
    return tuple(constraints)


def _common_measured_width_interval(
    intervals: tuple[PixelInterval, ...],
) -> PixelInterval | None:
    return PixelInterval.common_intersection(intervals)


def _largest_strict_intersection_indexes(
    intervals: tuple[PixelInterval, ...],
    minimum_count: int,
) -> tuple[int, ...]:
    if minimum_count <= 0:
        raise ValueError("strict interval group requires a positive minimum count")
    if len(intervals) < minimum_count:
        return ()
    coordinates = tuple(
        dict.fromkeys(
            coordinate
            for interval in intervals
            for coordinate in (
                interval.minimum,
                interval.midpoint,
                interval.maximum,
            )
        )
    )
    candidates: list[tuple[tuple[int, float, tuple[int, ...]], tuple[int, ...]]] = []
    for coordinate in coordinates:
        indexes = tuple(
            index
            for index, interval in enumerate(intervals)
            if interval.minimum <= coordinate <= interval.maximum
        )
        if len(indexes) < minimum_count:
            continue
        shared = _common_measured_width_interval(
            tuple(intervals[index] for index in indexes)
        )
        if shared is None:
            continue
        candidates.append(
            (
                (
                    len(indexes),
                    -(shared.maximum - shared.minimum),
                    tuple(-index for index in indexes),
                ),
                indexes,
            )
        )
    return () if not candidates else max(candidates, key=lambda item: item[0])[1]


def _largest_measurement_compatible_interval_indexes(
    intervals: tuple[PixelInterval, ...],
    minimum_count: int,
) -> tuple[int, ...]:
    if minimum_count <= 0:
        raise ValueError("common interval group requires a positive minimum count")
    if len(intervals) < minimum_count:
        return ()
    coordinates = tuple(
        dict.fromkeys(
            coordinate
            for interval in intervals
            for coordinate in (
                interval.minimum,
                interval.midpoint,
                interval.maximum,
            )
        )
    )
    candidates: list[tuple[tuple[int, float, tuple[int, ...]], tuple[int, ...]]] = []
    for coordinate in coordinates:
        center = PixelInterval.exact(coordinate)
        indexes = tuple(
            index
            for index, interval in enumerate(intervals)
            if _measurement_intervals_are_compatible(interval, center)
        )
        if len(indexes) < minimum_count:
            continue
        envelope = _interval_envelope(
            tuple(intervals[index] for index in indexes)
        )
        candidates.append(
            (
                (
                    len(indexes),
                    -(envelope.maximum - envelope.minimum),
                    tuple(-index for index in indexes),
                ),
                indexes,
            )
        )
    return () if not candidates else max(candidates, key=lambda item: item[0])[1]


def _role_supported_frame_constraint(
    constraint: _MeasuredFrameConstraint,
) -> bool:
    return bool(
        all(
            edge.basis
            in {
                FrameBoundarySource.GRAY_PATH_OBSERVATION,
                FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION,
            }
            for edge in (constraint.leading, constraint.trailing)
        )
        and all(
            edge.state == EvidenceState.SUPPORTED
            for edge in (constraint.leading, constraint.trailing)
        )
    )


def _measured_constraint_common_width(
    constraints: tuple[_MeasuredFrameConstraint, ...],
    count: int,
) -> PixelInterval | None:
    if not constraints or count < len(constraints):
        raise ValueError("measured constraint sequence must fit its frame count")
    contributor_indexes = _largest_measurement_compatible_interval_indexes(
        tuple(constraint.width_px for constraint in constraints),
        MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS,
    )
    if not contributor_indexes:
        return None
    shared = _interval_envelope(
        tuple(constraints[index].width_px for index in contributor_indexes)
    )
    contributor_set = set(contributor_indexes)
    for index, constraint in enumerate(constraints):
        if index in contributor_set or constraint.width_px.intersects(shared):
            continue
        leading_clip = bool(
            index == 0
            and constraint.leading_holder_clip_supported
            and constraint.width_px.maximum < shared.minimum
        )
        trailing_clip = bool(
            index == count - 1
            and len(constraints) == count
            and constraint.trailing_holder_clip_supported
            and constraint.width_px.maximum < shared.minimum
        )
        if not leading_clip and not trailing_clip:
            return None
    return shared


def _measured_sequence_build(
    constraints: tuple[_MeasuredFrameConstraint, ...],
    short_axis: SharedShortAxisSafetySpan,
    holder: Box,
    *,
    allow_nominal_slot_sized_gap: bool,
) -> _SequenceBuild | None:
    frame_width = (
        constraints[0].width_px
        if len(constraints) == 1
        else _measured_constraint_common_width(
            constraints,
            len(constraints),
        )
    )
    if frame_width is None:
        return None
    if not allow_nominal_slot_sized_gap and any(
        right.leading.position.minus(left.trailing.position).maximum
        >= frame_width.minimum
        for left, right in zip(constraints, constraints[1:])
    ):
        return None
    constraints = _candidate_specific_separator_edge_roles(constraints)
    slots: list[FrameSlot] = []
    assignments: list[FrameEdgeAssignment] = []
    for frame_index, constraint in enumerate(constraints, start=1):
        leading, leading_assignment = _resolution(
            frame_index,
            BoundarySide.LEADING,
            constraint.leading,
        )
        trailing, trailing_assignment = _resolution(
            frame_index,
            BoundarySide.TRAILING,
            constraint.trailing,
        )
        assignments.extend(
            item
            for item in (
                leading_assignment,
                trailing_assignment,
            )
            if item is not None
        )
        slots.append(
            FrameSlot(
                index=frame_index,
                visible_long_axis=PixelInterval(
                    leading.position.minimum,
                    trailing.position.maximum,
                ),
                leading=leading,
                trailing=trailing,
                content_occupancy=FrameContentOccupancy.UNAVAILABLE,
                edge_occlusion=None,
            )
        )
    slots = tuple(slots)
    assignments = tuple(assignments)
    spacings: list[InterFrameSpacing] = []
    separator_bindings: list[_SeparatorBandBinding] = []
    for boundary_index, (left, right) in enumerate(
        zip(slots, slots[1:]),
        start=1,
    ):
        trailing_constraint = constraints[boundary_index - 1].trailing
        leading_constraint = constraints[boundary_index].leading
        same_separator = bool(
            trailing_constraint.separator is not None
            and trailing_constraint.separator is leading_constraint.separator
            and trailing_constraint.separator_cross_axis
            is leading_constraint.separator_cross_axis
        )
        if same_separator:
            assert trailing_constraint.separator is not None
            assert trailing_constraint.separator_cross_axis is not None
            spacing, assignment = _spacing_for_band(
                boundary_index,
                SeparatorBandCrossAxisSupport(
                    trailing_constraint.separator,
                    trailing_constraint.separator_cross_axis,
                ),
                left.trailing,
                right.leading,
            )
        else:
            spacing = _measured_spacing(boundary_index, left, right)
            assignment = None
        spacings.append(spacing)
        if assignment is not None:
            separator_bindings.append(assignment)
    uncertainty_px = sum(
        edge.position.maximum - edge.position.minimum
        for slot in slots
        for edge in (
            slot.leading,
            slot.trailing,
        )
    ) + short_axis.uncertainty_px
    full_width_constraints = tuple(
        constraint
        for constraint in constraints
        if constraint.full_width_hypothesis_admissible
    )
    dimension_residual = float(
        sum(
            _normalized_interval_contradiction(
                constraint.width_px,
                frame_width,
            )
            for constraint in full_width_constraints
        )
        / len(full_width_constraints)
        if full_width_constraints
        else 0.0
    )
    frame_width_hint_residual = float(
        sum(constraint.frame_width_hint_residual for constraint in constraints)
        / len(constraints)
    )
    residuals = SequenceResiduals(
        dimension=dimension_residual,
        boundary_uncertainty=uncertainty_px
        / max(
            MINIMUM_POSITIVE_PIXEL_EXTENT,
            float(holder.width + holder.height),
        ),
    )
    internal_boundary_quality = float(
        sum(
            boundary.independently_observed
            for left, right in zip(slots, slots[1:])
            for boundary in (left.trailing, right.leading)
        )
    )
    external_boundary_quality = float(
        slots[0].leading.independently_observed
        + slots[-1].trailing.independently_observed
    )
    return _SequenceBuild(
        slots=slots,
        long_axis_assignments=assignments,
        separator_bindings=tuple(separator_bindings),
        spacings=tuple(spacings),
        frame_width_px=frame_width,
        short_axis=short_axis,
        residuals=residuals,
        objectives=_SequenceBuildObjectives(
            uncorroborated_overlap_extent_px=_uncorroborated_overlap_extent(
                tuple(spacings)
            ),
            unexplained_spacing_extent_px=_unexplained_spacing_extent(
                tuple(spacings)
            ),
            supported_separator_count=len(separator_bindings),
            internal_boundary_measurement_quality=internal_boundary_quality,
            dimension_residual=dimension_residual,
            external_boundary_measurement_quality=external_boundary_quality,
            boundary_uncertainty_ratio=residuals.boundary_uncertainty,
            frame_width_hint_residual=frame_width_hint_residual,
            uncorroborated_contact_count=_uncorroborated_contact_count(
                tuple(spacings)
            ),
            inferred_boundary_count=_inferred_boundary_count(slots),
        ),
    )


def _measured_frame_precedes(
    left: _MeasuredFrameConstraint,
    right: _MeasuredFrameConstraint,
) -> bool:
    return bool(
        right.leading.position.minimum > left.leading.position.maximum
        and right.trailing.position.minimum > left.trailing.position.maximum
    )


def _measured_frame_option_rank(
    option: _MeasuredFrameConstraint,
) -> tuple[bool, int, int, int, float, float, float, float, float]:
    return (
        option.full_width_hypothesis_admissible,
        sum(
            edge.state == EvidenceState.SUPPORTED
            for edge in (option.leading, option.trailing)
        ),
        sum(
            edge.basis == FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION
            and _separator_edge_path_is_supported(edge)
            for edge in (option.leading, option.trailing)
        ),
        sum(
            edge.basis == FrameBoundarySource.GRAY_PATH_OBSERVATION
            for edge in (option.leading, option.trailing)
        ),
        -option.search_order_residual,
        -option.frame_width_hint_residual,
        option.leading.observation_quality + option.trailing.observation_quality,
        -(
            option.leading.position.maximum
            - option.leading.position.minimum
            + option.trailing.position.maximum
            - option.trailing.position.minimum
        ),
        -option.leading.position.midpoint,
    )


def _canonical_measured_frame_constraints(
    options: tuple[_MeasuredFrameConstraint, ...],
) -> tuple[_MeasuredFrameConstraint, ...]:
    by_geometry: dict[
        tuple[
            tuple[PixelInterval, BoundarySide | None],
            tuple[PixelInterval, BoundarySide | None],
        ],
        _MeasuredFrameConstraint,
    ] = {}
    for option in options:
        key = (
            (option.leading.position, option.leading.external_side),
            (option.trailing.position, option.trailing.external_side),
        )
        existing = by_geometry.get(key)
        if (
            existing is None
            or _measured_frame_option_rank(option)
            > _measured_frame_option_rank(existing)
        ):
            by_geometry[key] = option
    return tuple(by_geometry.values())


def _recurring_boundary_width_hypotheses(
    edges: tuple[_EdgeConstraint, ...],
) -> tuple[_RecurringBoundaryWidthHypothesis, ...]:
    ordered_edges = tuple(
        sorted(
            edges,
            key=lambda edge: (
                edge.position.midpoint,
                edge.position.minimum,
                edge.position.maximum,
                edge.provenance.observation_id,
            ),
        )
    )
    samples: list[tuple[PixelInterval, _EdgeConstraint, _EdgeConstraint]] = []
    for left_index, left in enumerate(ordered_edges):
        for right in ordered_edges[left_index + 1 :]:
            if right.position.minimum <= left.position.maximum:
                continue
            width = right.position.minus(left.position)
            if width.minimum < MINIMUM_POSITIVE_PIXEL_EXTENT:
                continue
            samples.append((width, left, right))
    samples.sort(
        key=lambda item: (
            item[0].midpoint,
            item[0].maximum - item[0].minimum,
            item[1].position.midpoint,
            item[2].position.midpoint,
        )
    )

    grouped: list[
        tuple[PixelInterval, list[tuple[PixelInterval, _EdgeConstraint, _EdgeConstraint]]]
    ] = []
    for sample in samples:
        width = sample[0]
        if grouped:
            shared = grouped[-1][0].intersection(width)
            if shared is not None:
                grouped_samples = grouped[-1][1]
                grouped_samples.append(sample)
                grouped[-1] = (shared, grouped_samples)
                continue
        grouped.append((width, [sample]))

    candidates: dict[
        PixelInterval,
        _RecurringBoundaryWidthHypothesis,
    ] = {}
    for _, group in grouped:
        contributors: list[
            tuple[PixelInterval, _EdgeConstraint, _EdgeConstraint]
        ] = []
        for sample in sorted(
            group,
            key=lambda item: (
                item[2].position.maximum,
                item[1].position.minimum,
                item[1].provenance.observation_id,
                item[2].provenance.observation_id,
            ),
        ):
            if (
                contributors
                and sample[1].position.minimum
                < contributors[-1][2].position.maximum
            ):
                continue
            contributors.append(sample)
        if len(contributors) < MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS:
            continue
        shared = PixelInterval.common_intersection(
            tuple(sample[0] for sample in contributors)
        )
        if shared is None:
            continue
        hypothesis = _RecurringBoundaryWidthHypothesis(
            shared,
            len(contributors),
        )
        existing = candidates.get(shared)
        if existing is None or hypothesis.contributor_count > existing.contributor_count:
            candidates[shared] = hypothesis
    return tuple(
        sorted(
            candidates.values(),
            key=lambda hypothesis: (
                -hypothesis.contributor_count,
                hypothesis.width_px.maximum - hypothesis.width_px.minimum,
                hypothesis.width_px.midpoint,
            ),
        )
    )


def _width_compatibility_matrix(
    constraints: tuple[_MeasuredFrameConstraint, ...],
    coordinates: tuple[float, ...],
) -> np.ndarray:
    if not constraints or not coordinates:
        return np.zeros((len(coordinates), len(constraints)), dtype=bool)
    minima = np.fromiter(
        (constraint.width_px.minimum for constraint in constraints),
        dtype=np.float64,
        count=len(constraints),
    )
    maxima = np.fromiter(
        (constraint.width_px.maximum for constraint in constraints),
        dtype=np.float64,
        count=len(constraints),
    )
    candidate_coordinates = np.asarray(coordinates, dtype=np.float64)
    return (
        (candidate_coordinates[:, np.newaxis] >= minima[np.newaxis, :])
        & (candidate_coordinates[:, np.newaxis] <= maxima[np.newaxis, :])
    )


def _repeated_width_contributor_sets(
    constraints: tuple[_MeasuredFrameConstraint, ...],
    minimum_contributors: int,
) -> tuple[tuple[PixelInterval, tuple[_MeasuredFrameConstraint, ...]], ...]:
    if minimum_contributors < MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS:
        raise ValueError("repeated width search requires multiple contributors")
    coordinates = tuple(
        dict.fromkeys(
            coordinate
            for constraint in constraints
            for coordinate in (
                constraint.width_px.minimum,
                constraint.width_px.midpoint,
                constraint.width_px.maximum,
            )
        )
    )
    ordered_constraints = tuple(
        sorted(
            constraints,
            key=lambda item: (
                item.trailing.position.maximum,
                item.leading.position.minimum,
                item.leading.provenance.observation_id,
                item.trailing.provenance.observation_id,
            ),
        )
    )
    compatibility_matrix = _width_compatibility_matrix(
        ordered_constraints,
        coordinates,
    )
    candidates: dict[
        tuple[float, float],
        tuple[PixelInterval, tuple[_MeasuredFrameConstraint, ...]],
    ] = {}
    for coordinate, compatibility in zip(
        coordinates,
        compatibility_matrix,
        strict=True,
    ):
        contributors: list[_MeasuredFrameConstraint] = []
        for index in np.flatnonzero(compatibility):
            constraint = ordered_constraints[int(index)]
            if contributors and (
                constraint.leading.position.minimum
                < contributors[-1].trailing.position.maximum
            ):
                continue
            contributors.append(constraint)
        if len(contributors) < minimum_contributors:
            continue
        shared = PixelInterval.common_intersection(
            tuple(constraint.width_px for constraint in contributors)
        )
        if shared is None:
            continue
        key = (shared.minimum, shared.maximum)
        existing = candidates.get(key)
        if (
            existing is None
            or len(contributors) > len(existing[1])
        ):
            candidates[key] = (shared, tuple(contributors))
    return tuple(
        sorted(
            candidates.values(),
            key=lambda item: (
                -len(item[1]),
                item[0].maximum - item[0].minimum,
                item[0].midpoint,
                tuple(
                    boundary.provenance.observation_id
                    for constraint in item[1]
                    for boundary in (constraint.leading, constraint.trailing)
                ),
            ),
        )
    )


def _measured_width_hypotheses(
    constraints: tuple[_MeasuredFrameConstraint, ...],
) -> tuple[_CommonWidthHypothesis, ...]:
    measured = tuple(
        constraint
        for constraint in constraints
        if _role_supported_frame_constraint(constraint)
    )
    return tuple(
        _CommonWidthHypothesis(
            width_px=width,
            boundary_anchors=tuple(
                dict.fromkeys(
                    boundary.provenance.observation_id
                    for constraint in contributors
                    for boundary in (constraint.leading, constraint.trailing)
                )
            ),
            contributor_count=len(contributors),
        )
        for width, contributors in _repeated_width_contributor_sets(
            measured,
            MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS,
        )
    )


def _option_is_valid_at_frame_index(
    option: _MeasuredFrameConstraint,
    frame_index: int,
    count: int,
) -> bool:
    return bool(
        option.allowed_at(frame_index, count)
        and not (
            option.leading.external_side is not None
            and (
                frame_index != 1
                or option.leading.external_side != BoundarySide.LEADING
            )
        )
        and not (
            option.trailing.external_side is not None
            and (
                frame_index != count
                or option.trailing.external_side != BoundarySide.TRAILING
            )
        )
        and not (
            frame_index == 1
            and option.leading.separator is not None
            and option.leading.external_side != BoundarySide.LEADING
        )
        and not (
            frame_index == count
            and option.trailing.separator is not None
            and option.trailing.external_side != BoundarySide.TRAILING
        )
    )


def _separator_boundary_key(edge: _EdgeConstraint) -> ObservationId | None:
    return (
        None
        if edge.separator is None or edge.external_side is not None
        else edge.separator.provenance.observation_id
    )


def _separator_edges_pair_at_boundary(
    left: _MeasuredFrameConstraint,
    right: _MeasuredFrameConstraint,
) -> bool:
    left_key = _separator_boundary_key(left.trailing)
    right_key = _separator_boundary_key(right.leading)
    if left_key != right_key:
        return False
    if left_key is None:
        return True
    return bool(
        left.trailing.separator == right.leading.separator
        and left.trailing.separator_cross_axis
        == right.leading.separator_cross_axis
    )


def _separator_boundary_keys_are_compatible(
    left: _MeasuredFrameConstraint,
    right: _MeasuredFrameConstraint,
) -> bool:
    left_key = _separator_boundary_key(left.trailing)
    right_key = _separator_boundary_key(right.leading)
    return bool(
        left_key == right_key
        or left_key is None
        or right_key is None
    )


def _common_width_coordinate_span(
    option: _MeasuredFrameConstraint,
    frame_index: int,
    count: int,
    coordinates: tuple[float, ...],
) -> tuple[int, int] | None:
    holder_clipped_endpoint = bool(
        (frame_index == 1 and option.leading_holder_clip_supported)
        or (frame_index == count and option.trailing_holder_clip_supported)
    )
    measurement_uncertainty = (
        option.width_px.maximum - option.width_px.minimum
    )
    start = bisect_left(
        coordinates,
        (
            option.width_px.minimum
            if holder_clipped_endpoint
            else option.width_px.minimum - measurement_uncertainty
        ),
    )
    end = (
        len(coordinates)
        if holder_clipped_endpoint
        else bisect_right(
            coordinates,
            option.width_px.maximum + measurement_uncertainty,
        )
    )
    return None if start >= end else (start, end)


def _options_from_mask(
    mask: int,
    lookup: dict[int, _MeasuredFrameConstraint],
) -> tuple[tuple[int, _MeasuredFrameConstraint], ...]:
    selected: list[tuple[int, _MeasuredFrameConstraint]] = []
    remaining = mask
    while remaining:
        bit = remaining & -remaining
        option_index = bit.bit_length() - 1
        selected.append((option_index, lookup[option_index]))
        remaining ^= bit
    return tuple(selected)


@dataclass(frozen=True)
class _CommonWidthOptionIndex:
    option_lookups: tuple[dict[int, _MeasuredFrameConstraint], ...]
    group_masks: tuple[tuple[int, ...], ...]


def _maximal_common_width_group_masks(
    groups: tuple[tuple[int, ...], ...],
) -> tuple[tuple[int, ...], ...]:
    return tuple(
        group
        for index, group in enumerate(groups)
        if not any(
            index != other_index
            and all(mask & ~other_mask == 0 for mask, other_mask in zip(group, other))
            and any(mask != other_mask for mask, other_mask in zip(group, other))
            for other_index, other in enumerate(groups)
        )
    )


def _separator_pair_option_masks(
    option_lookups: tuple[dict[int, _MeasuredFrameConstraint], ...],
) -> tuple[tuple[tuple[int, int], ...], ...]:
    pairs: list[tuple[tuple[int, int], ...]] = []
    for left_lookup, right_lookup in zip(
        option_lookups,
        option_lookups[1:],
    ):
        trailing_masks: dict[object, int] = {}
        leading_masks: dict[object, int] = {}
        for option_index, option in left_lookup.items():
            key = _separator_boundary_key(option.trailing)
            if key is not None:
                trailing_masks[key] = trailing_masks.get(key, 0) | (
                    1 << option_index
                )
        for option_index, option in right_lookup.items():
            key = _separator_boundary_key(option.leading)
            if key is not None:
                leading_masks[key] = leading_masks.get(key, 0) | (
                    1 << option_index
                )
        pairs.append(
            tuple(
                (trailing_masks[key], leading_masks[key])
                for key in trailing_masks.keys() & leading_masks.keys()
            )
        )
    return tuple(pairs)


def _separator_assignment_upper_bound(
    group_masks: tuple[int, ...],
    pair_masks: tuple[tuple[tuple[int, int], ...], ...],
) -> int:
    return sum(
        any(
            group_masks[boundary_index] & trailing_mask
            and group_masks[boundary_index + 1] & leading_mask
            for trailing_mask, leading_mask in boundary_pairs
        )
        for boundary_index, boundary_pairs in enumerate(pair_masks)
    )


def _common_width_option_index(
    options_by_frame: tuple[
        tuple[tuple[int, _MeasuredFrameConstraint], ...],
        ...,
    ],
    count: int,
    width_hypotheses: tuple[PixelInterval, ...],
) -> _CommonWidthOptionIndex:
    option_lookups = tuple(dict(frame_options) for frame_options in options_by_frame)
    if count == 1:
        group_masks = (
            (
                sum(
                    1 << option_index
                    for option_index in option_lookups[0]
                ),
            ),
        ) if option_lookups and option_lookups[0] else ()
        return _CommonWidthOptionIndex(
            option_lookups,
            group_masks,
        )
    ordered_coordinates = tuple(
        dict.fromkeys(
            coordinate
            for width in width_hypotheses
            for coordinate in (
                width.minimum,
                width.midpoint,
                width.maximum,
            )
        )
    )
    if not ordered_coordinates:
        return _CommonWidthOptionIndex(option_lookups, ())
    coordinates = tuple(sorted(ordered_coordinates))
    additions: list[list[tuple[int, int]]] = [
        [] for _ in range(len(coordinates))
    ]
    removals: list[list[tuple[int, int]]] = [
        [] for _ in range(len(coordinates) + 1)
    ]
    for frame_index, frame_options in enumerate(options_by_frame, start=1):
        for option_index, option in frame_options:
            span = _common_width_coordinate_span(
                option,
                frame_index,
                count,
                coordinates,
            )
            if span is None:
                continue
            start, end = span
            additions[start].append((frame_index - 1, option_index))
            removals[end].append((frame_index - 1, option_index))

    active_masks = [0] * count
    membership_by_coordinate: dict[float, tuple[int, ...]] = {}
    for coordinate_index, coordinate in enumerate(coordinates):
        for frame_offset, option_index in removals[coordinate_index]:
            active_masks[frame_offset] &= ~(1 << option_index)
        for frame_offset, option_index in additions[coordinate_index]:
            active_masks[frame_offset] |= 1 << option_index
        membership_by_coordinate[coordinate] = tuple(active_masks)

    group_masks: list[tuple[int, ...]] = []
    seen: set[tuple[int, ...]] = set()
    for coordinate in ordered_coordinates:
        key = membership_by_coordinate[coordinate]
        if any(mask == 0 for mask in key) or key in seen:
            continue
        seen.add(key)
        group_masks.append(key)
    return _CommonWidthOptionIndex(
        option_lookups,
        _maximal_common_width_group_masks(tuple(group_masks)),
    )


def _materialize_common_width_group(
    index: _CommonWidthOptionIndex,
    masks: tuple[int, ...],
) -> tuple[tuple[tuple[int, _MeasuredFrameConstraint], ...], ...]:
    return tuple(
        _options_from_mask(mask, lookup)
        for mask, lookup in zip(masks, index.option_lookups, strict=True)
    )


def _content_coverage_interval(
    option: _MeasuredFrameConstraint,
    visible_content: ContentRegionObservation,
) -> tuple[int, int] | None:
    start = max(
        visible_content.region.left,
        int(floor(option.leading.position.minimum)),
    )
    end = min(
        visible_content.region.right,
        int(ceil(option.trailing.position.maximum)),
    )
    return None if end <= start else (start, end)


def _expanded_content_coverage_interval(
    option: _MeasuredFrameConstraint,
    visible_content: ContentRegionObservation,
) -> tuple[int, int] | None:
    interval = _content_coverage_interval(option, visible_content)
    if interval is None:
        return None
    start, end = interval
    uncertainty = visible_content.position_uncertainty_px
    return (
        max(visible_content.region.left, start - uncertainty),
        min(visible_content.region.right, end + uncertainty),
    )


def _width_hypothesis_can_cover_reliable_content(
    hypothesis: _DimensionPlacementHypothesis,
    count: int,
    visible_content: ContentRegionObservation,
) -> bool:
    if not visible_content.reliable_runs:
        return True
    uncertainty = visible_content.position_uncertainty_px
    required_extent = sum(
        max(0, end - start - INTERVAL_ENDPOINT_COUNT * uncertainty)
        for start, end in visible_content.reliable_runs
    )
    return hypothesis.width_px.maximum * count >= required_extent


@dataclass(frozen=True)
class _SequenceGraphContext:
    coverages: tuple[tuple[int, int] | None, ...]
    run_starts: tuple[int, ...]
    run_ends: tuple[int, ...]
    first_mask: int
    last_mask: int
    allow_nominal_slot_sized_gap: bool
    edge_support_cache: dict[tuple[int, int], bool]


def _sequence_graph_context(
    ordered: tuple[_MeasuredFrameConstraint, ...],
    visible_content: ContentRegionObservation,
    *,
    allow_nominal_slot_sized_gap: bool,
) -> _SequenceGraphContext:
    coverages = tuple(
        _expanded_content_coverage_interval(option, visible_content)
        for option in ordered
    )
    runs = tuple(sorted(visible_content.reliable_runs))
    first_content_start = min((start for start, _ in runs), default=None)
    last_content_end = max((end for _, end in runs), default=None)
    first_mask = 0
    last_mask = 0
    for option_index, coverage in enumerate(coverages):
        bit = 1 << option_index
        if not runs or (
            coverage is not None
            and first_content_start is not None
            and first_content_start >= coverage[0]
        ):
            first_mask |= bit
        if not runs or (
            coverage is not None
            and last_content_end is not None
            and last_content_end <= coverage[1]
        ):
            last_mask |= bit
    return _SequenceGraphContext(
        coverages=coverages,
        run_starts=tuple(start for start, _ in runs),
        run_ends=tuple(end for _, end in runs),
        first_mask=first_mask,
        last_mask=last_mask,
        allow_nominal_slot_sized_gap=allow_nominal_slot_sized_gap,
        edge_support_cache={},
    )


def _sequence_graph_edge_is_interval_feasible(
    left_index: int,
    right_index: int,
    ordered: tuple[_MeasuredFrameConstraint, ...],
    context: _SequenceGraphContext,
) -> bool:
    left = ordered[left_index]
    right = ordered[right_index]
    if not _separator_boundary_keys_are_compatible(left, right):
        return False
    if not _measured_frame_precedes(left, right):
        return False
    if not context.allow_nominal_slot_sized_gap:
        common_width = left.width_px.intersection(right.width_px)
        if (
            common_width is None
            or right.leading.position.minus(left.trailing.position).maximum
            >= common_width.minimum
        ):
            return False
    left_coverage = context.coverages[left_index]
    right_coverage = context.coverages[right_index]
    if left_coverage is None or right_coverage is None:
        return not context.run_starts
    gap_start = left_coverage[1]
    gap_end = right_coverage[0]
    if gap_end <= gap_start:
        return True
    run_index = bisect_right(context.run_ends, gap_start)
    return bool(
        run_index >= len(context.run_starts)
        or context.run_starts[run_index] >= gap_end
    )


def _cached_sequence_graph_edge_supported(
    left_index: int,
    right_index: int,
    ordered: tuple[_MeasuredFrameConstraint, ...],
    context: _SequenceGraphContext,
) -> bool:
    key = (left_index, right_index)
    supported = context.edge_support_cache.get(key)
    if supported is None:
        supported = _sequence_graph_edge_is_interval_feasible(
            left_index,
            right_index,
            ordered,
            context,
        )
        context.edge_support_cache[key] = supported
    return supported


def _fenwick_update(
    tree: list[tuple[float, int, int] | None],
    index: int,
    value: tuple[float, int, int],
) -> None:
    current = index + 1
    while current < len(tree):
        existing = tree[current]
        if existing is None or value > existing:
            tree[current] = value
        current += current & -current


def _fenwick_query(
    tree: list[tuple[float, int, int] | None],
    count: int,
) -> tuple[float, int, int] | None:
    best: tuple[float, int, int] | None = None
    current = count
    while current > 0:
        candidate = tree[current]
        if candidate is not None and (best is None or candidate > best):
            best = candidate
        current -= current & -current
    return best


def _reachable_predecessors_for_boundary(
    previous_indexes: tuple[int, ...],
    current_indexes: tuple[int, ...],
    ordered: tuple[_MeasuredFrameConstraint, ...],
    context: _SequenceGraphContext,
) -> dict[int, int]:
    eligible_previous = tuple(
        index
        for index in previous_indexes
        if not context.run_starts or context.coverages[index] is not None
    )
    if not eligible_previous:
        return {}
    trailing_coordinates = tuple(
        sorted(
            {
                ordered[index].trailing.position.maximum
                for index in eligible_previous
            }
        )
    )
    tree: list[tuple[float, int, int] | None] = [
        None
    ] * (len(trailing_coordinates) + 1)
    sorted_previous = tuple(
        sorted(
            eligible_previous,
            key=lambda index: (
                ordered[index].leading.position.maximum,
                ordered[index].trailing.position.maximum,
                index,
            ),
        )
    )
    cursor = 0
    reachable: dict[int, int] = {}
    for current_index in sorted(
        current_indexes,
        key=lambda index: (
            ordered[index].leading.position.minimum,
            ordered[index].trailing.position.minimum,
            index,
        ),
    ):
        current = ordered[current_index]
        while (
            cursor < len(sorted_previous)
            and ordered[sorted_previous[cursor]].leading.position.maximum
            < current.leading.position.minimum
        ):
            previous_index = sorted_previous[cursor]
            coverage = context.coverages[previous_index]
            coverage_end = (
                float(ordered[previous_index].trailing.position.maximum)
                if coverage is None
                else float(coverage[1])
            )
            trailing_rank = bisect_left(
                trailing_coordinates,
                ordered[previous_index].trailing.position.maximum,
            )
            _fenwick_update(
                tree,
                trailing_rank,
                (coverage_end, -previous_index, previous_index),
            )
            cursor += 1
        candidate = _fenwick_query(
            tree,
            bisect_left(
                trailing_coordinates,
                current.trailing.position.minimum,
            ),
        )
        if candidate is None:
            continue
        previous_index = candidate[2]
        if _cached_sequence_graph_edge_supported(
            previous_index,
            current_index,
            ordered,
            context,
        ):
            reachable[current_index] = previous_index
            continue
        fallback_indexes = sorted(
            (
                index
                for index in eligible_previous
                if index != previous_index
                and ordered[index].leading.position.maximum
                < current.leading.position.minimum
                and ordered[index].trailing.position.maximum
                < current.trailing.position.minimum
            ),
            key=lambda index: (
                (
                    float(ordered[index].trailing.position.maximum)
                    if context.coverages[index] is None
                    else float(context.coverages[index][1])
                ),
                -index,
            ),
            reverse=True,
        )
        fallback_index = next(
            (
                index
                for index in fallback_indexes
                if _cached_sequence_graph_edge_supported(
                    index,
                    current_index,
                    ordered,
                    context,
                )
            ),
            None,
        )
        if fallback_index is not None:
            reachable[current_index] = fallback_index
    return reachable


def _reachable_predecessors(
    previous_indexes: tuple[int, ...],
    current_indexes: tuple[int, ...],
    ordered: tuple[_MeasuredFrameConstraint, ...],
    context: _SequenceGraphContext,
) -> dict[int, int]:
    previous_by_separator: dict[ObservationId | None, list[int]] = {}
    current_by_separator: dict[ObservationId | None, list[int]] = {}
    for index in previous_indexes:
        previous_by_separator.setdefault(
            _separator_boundary_key(ordered[index].trailing),
            [],
        ).append(index)
    for index in current_indexes:
        current_by_separator.setdefault(
            _separator_boundary_key(ordered[index].leading),
            [],
        ).append(index)
    reachable: dict[int, int] = {}
    for separator_key in sorted(
        previous_by_separator.keys() & current_by_separator.keys(),
        key=lambda item: "" if item is None else str(item),
    ):
        reachable.update(
            _reachable_predecessors_for_boundary(
                tuple(previous_by_separator[separator_key]),
                tuple(current_by_separator[separator_key]),
                ordered,
                context,
            )
        )
    unassigned_previous = tuple(previous_by_separator.get(None, ()))
    if unassigned_previous:
        for separator_key, indexes in current_by_separator.items():
            if separator_key is None:
                continue
            reachable.update(
                _reachable_predecessors_for_boundary(
                    unassigned_previous,
                    tuple(indexes),
                    ordered,
                    context,
                )
            )
    unassigned_current = tuple(current_by_separator.get(None, ()))
    assigned_previous = tuple(
        index
        for separator_key, indexes in previous_by_separator.items()
        if separator_key is not None
        for index in indexes
    )
    if assigned_previous and unassigned_current:
        reachable.update(
            _reachable_predecessors_for_boundary(
                assigned_previous,
                unassigned_current,
                ordered,
                context,
            )
        )
    return reachable


def _reachable_successors_for_boundary(
    current_indexes: tuple[int, ...],
    following_indexes: tuple[int, ...],
    ordered: tuple[_MeasuredFrameConstraint, ...],
    context: _SequenceGraphContext,
) -> dict[int, int]:
    eligible_following = tuple(
        index
        for index in following_indexes
        if not context.run_starts or context.coverages[index] is not None
    )
    if not eligible_following:
        return {}
    reversed_trailing_coordinates = tuple(
        sorted(
            {
                -ordered[index].trailing.position.minimum
                for index in eligible_following
            }
        )
    )
    tree: list[tuple[float, int, int] | None] = [
        None
    ] * (len(reversed_trailing_coordinates) + 1)
    sorted_following = tuple(
        sorted(
            eligible_following,
            key=lambda index: (
                ordered[index].leading.position.minimum,
                ordered[index].trailing.position.minimum,
                -index,
            ),
            reverse=True,
        )
    )
    cursor = 0
    reachable: dict[int, int] = {}
    for current_index in sorted(
        current_indexes,
        key=lambda index: (
            ordered[index].leading.position.maximum,
            ordered[index].trailing.position.maximum,
            -index,
        ),
        reverse=True,
    ):
        current = ordered[current_index]
        while (
            cursor < len(sorted_following)
            and ordered[sorted_following[cursor]].leading.position.minimum
            > current.leading.position.maximum
        ):
            following_index = sorted_following[cursor]
            coverage = context.coverages[following_index]
            coverage_start = (
                float(ordered[following_index].leading.position.minimum)
                if coverage is None
                else float(coverage[0])
            )
            trailing_rank = bisect_left(
                reversed_trailing_coordinates,
                -ordered[following_index].trailing.position.minimum,
            )
            _fenwick_update(
                tree,
                trailing_rank,
                (-coverage_start, -following_index, following_index),
            )
            cursor += 1
        candidate = _fenwick_query(
            tree,
            bisect_left(
                reversed_trailing_coordinates,
                -current.trailing.position.maximum,
            ),
        )
        if candidate is None:
            continue
        following_index = candidate[2]
        if _cached_sequence_graph_edge_supported(
            current_index,
            following_index,
            ordered,
            context,
        ):
            reachable[current_index] = following_index
            continue
        fallback_indexes = sorted(
            (
                index
                for index in eligible_following
                if index != following_index
                and ordered[index].leading.position.minimum
                > current.leading.position.maximum
                and ordered[index].trailing.position.minimum
                > current.trailing.position.maximum
            ),
            key=lambda index: (
                -(
                    float(ordered[index].leading.position.minimum)
                    if context.coverages[index] is None
                    else float(context.coverages[index][0])
                ),
                -index,
            ),
            reverse=True,
        )
        fallback_index = next(
            (
                index
                for index in fallback_indexes
                if _cached_sequence_graph_edge_supported(
                    current_index,
                    index,
                    ordered,
                    context,
                )
            ),
            None,
        )
        if fallback_index is not None:
            reachable[current_index] = fallback_index
    return reachable


def _reachable_successors(
    current_indexes: tuple[int, ...],
    following_indexes: tuple[int, ...],
    ordered: tuple[_MeasuredFrameConstraint, ...],
    context: _SequenceGraphContext,
) -> dict[int, int]:
    current_by_separator: dict[ObservationId | None, list[int]] = {}
    following_by_separator: dict[ObservationId | None, list[int]] = {}
    for index in current_indexes:
        current_by_separator.setdefault(
            _separator_boundary_key(ordered[index].trailing),
            [],
        ).append(index)
    for index in following_indexes:
        following_by_separator.setdefault(
            _separator_boundary_key(ordered[index].leading),
            [],
        ).append(index)
    reachable: dict[int, int] = {}
    for separator_key in sorted(
        current_by_separator.keys() & following_by_separator.keys(),
        key=lambda item: "" if item is None else str(item),
    ):
        reachable.update(
            _reachable_successors_for_boundary(
                tuple(current_by_separator[separator_key]),
                tuple(following_by_separator[separator_key]),
                ordered,
                context,
            )
        )
    unassigned_current = tuple(current_by_separator.get(None, ()))
    assigned_following = tuple(
        index
        for separator_key, indexes in following_by_separator.items()
        if separator_key is not None
        for index in indexes
    )
    if unassigned_current and assigned_following:
        reachable.update(
            _reachable_successors_for_boundary(
                unassigned_current,
                assigned_following,
                ordered,
                context,
            )
        )
    unassigned_following = tuple(following_by_separator.get(None, ()))
    if unassigned_following:
        for separator_key, indexes in current_by_separator.items():
            if separator_key is None:
                continue
            reachable.update(
                _reachable_successors_for_boundary(
                    tuple(indexes),
                    unassigned_following,
                    ordered,
                    context,
                )
            )
    return reachable


def _graph_sequence_for_target(
    target_layer: int,
    target_index: int,
    forward: list[dict[int, int | None]],
    backward: list[dict[int, int | None]],
    ordered: tuple[_MeasuredFrameConstraint, ...],
) -> tuple[_MeasuredFrameConstraint, ...]:
    selected = [target_index]
    current = target_index
    for layer_index in range(target_layer, 0, -1):
        predecessor = forward[layer_index][current]
        if predecessor is None:
            raise ValueError("feasible sequence node lacks a leading path")
        selected.insert(0, predecessor)
        current = predecessor
    current = target_index
    for layer_index in range(target_layer, len(forward) - 1):
        successor = backward[layer_index][current]
        if successor is None:
            raise ValueError("feasible sequence node lacks a trailing path")
        selected.append(successor)
        current = successor
    return tuple(ordered[index] for index in selected)


@dataclass(frozen=True)
class _GraphPathState:
    observation_candidate_count: int
    supported_separator_count: int
    internal_measurement_quality: float
    uncorroborated_overlap_extent_px: float
    frame_sized_unexplained_gap_count: int
    unexplained_spacing_extent_px: float
    uncorroborated_contact_count: int
    frame_width_hint_residual: float
    boundary_uncertainty_px: float
    external_leading_quality: float
    coordinate_key: tuple[float, ...]
    predecessor: int | None


@dataclass(frozen=True)
class _GraphLayerStateIndex:
    option_indexes: tuple[int, ...]
    leading_maxima: np.ndarray
    trailing_minima: np.ndarray
    trailing_maxima: np.ndarray
    frame_width_minima: np.ndarray
    frame_width_maxima: np.ndarray
    separator_offsets: dict[ObservationId | None, np.ndarray]
    coverage_ends: np.ndarray
    observation_candidate_counts: np.ndarray
    supported_separator_counts: np.ndarray
    internal_measurement_qualities: np.ndarray
    uncorroborated_overlap_extents: np.ndarray
    frame_sized_unexplained_gap_counts: np.ndarray
    unexplained_spacing_extents: np.ndarray
    uncorroborated_contact_counts: np.ndarray
    frame_width_hint_residuals: np.ndarray
    boundary_uncertainties: np.ndarray
    external_leading_qualities: np.ndarray
    coordinate_keys: tuple[tuple[float, ...], ...]


def _graph_layer_state_index(
    states: dict[int, _GraphPathState],
    ordered: tuple[_MeasuredFrameConstraint, ...],
    context: _SequenceGraphContext,
) -> _GraphLayerStateIndex:
    option_indexes = tuple(states)
    separator_offsets: dict[ObservationId | None, list[int]] = {}
    for offset, option_index in enumerate(option_indexes):
        separator_offsets.setdefault(
            _separator_boundary_key(ordered[option_index].trailing),
            [],
        ).append(offset)

    def state_array(name: str, dtype: np.dtype) -> np.ndarray:
        return np.fromiter(
            (getattr(states[index], name) for index in option_indexes),
            dtype=dtype,
            count=len(option_indexes),
        )

    return _GraphLayerStateIndex(
        option_indexes=option_indexes,
        leading_maxima=np.fromiter(
            (ordered[index].leading.position.maximum for index in option_indexes),
            dtype=np.float64,
            count=len(option_indexes),
        ),
        trailing_minima=np.fromiter(
            (ordered[index].trailing.position.minimum for index in option_indexes),
            dtype=np.float64,
            count=len(option_indexes),
        ),
        trailing_maxima=np.fromiter(
            (ordered[index].trailing.position.maximum for index in option_indexes),
            dtype=np.float64,
            count=len(option_indexes),
        ),
        frame_width_minima=np.fromiter(
            (ordered[index].width_px.minimum for index in option_indexes),
            dtype=np.float64,
            count=len(option_indexes),
        ),
        frame_width_maxima=np.fromiter(
            (ordered[index].width_px.maximum for index in option_indexes),
            dtype=np.float64,
            count=len(option_indexes),
        ),
        separator_offsets={
            key: np.asarray(offsets, dtype=np.int64)
            for key, offsets in separator_offsets.items()
        },
        coverage_ends=np.asarray(
            [
                (
                    np.nan
                    if context.coverages[index] is None
                    else context.coverages[index][1]
                )
                for index in option_indexes
            ],
            dtype=np.float64,
        ),
        observation_candidate_counts=state_array(
            "observation_candidate_count",
            np.int64,
        ),
        supported_separator_counts=state_array(
            "supported_separator_count",
            np.int64,
        ),
        internal_measurement_qualities=state_array(
            "internal_measurement_quality",
            np.float64,
        ),
        uncorroborated_overlap_extents=state_array(
            "uncorroborated_overlap_extent_px",
            np.float64,
        ),
        frame_sized_unexplained_gap_counts=state_array(
            "frame_sized_unexplained_gap_count",
            np.int64,
        ),
        unexplained_spacing_extents=state_array(
            "unexplained_spacing_extent_px",
            np.float64,
        ),
        uncorroborated_contact_counts=state_array(
            "uncorroborated_contact_count",
            np.int64,
        ),
        frame_width_hint_residuals=state_array(
            "frame_width_hint_residual",
            np.float64,
        ),
        boundary_uncertainties=state_array(
            "boundary_uncertainty_px",
            np.float64,
        ),
        external_leading_qualities=state_array(
            "external_leading_quality",
            np.float64,
        ),
        coordinate_keys=tuple(states[index].coordinate_key for index in option_indexes),
    )


@dataclass(frozen=True)
class _SequenceGraphEvaluations:
    states: frozenset[tuple[int, int]]
    edge_queries: frozenset[tuple[int, int]]
    completion_transitions: frozenset[tuple[int, int, int]]

    def incremental_cost(self, previous: "_SequenceGraphEvaluations") -> int:
        return (
            len(self.states - previous.states)
            + len(self.edge_queries - previous.edge_queries)
            + len(
                self.completion_transitions
                - previous.completion_transitions
            )
        )

    def merged(
        self,
        other: "_SequenceGraphEvaluations",
    ) -> "_SequenceGraphEvaluations":
        return _SequenceGraphEvaluations(
            self.states | other.states,
            self.edge_queries | other.edge_queries,
            self.completion_transitions | other.completion_transitions,
        )


def _sequence_graph_evaluations(
    feasible: tuple[tuple[int, ...], ...],
    ordered: tuple[_MeasuredFrameConstraint, ...],
    context: _SequenceGraphContext,
) -> _SequenceGraphEvaluations:
    if context.allow_nominal_slot_sized_gap:
        completion_transitions = frozenset(
            (layer_index, left_index, right_index)
            for layer_index, (left_indexes, right_indexes) in enumerate(
                zip(feasible, feasible[1:])
            )
            for left_index in left_indexes
            for right_index in right_indexes
            if _cached_sequence_graph_edge_supported(
                left_index,
                right_index,
                ordered,
                context,
            )
        )
    else:
        completion_transitions = frozenset()
    return _SequenceGraphEvaluations(
        states=frozenset(
            (layer_index, option_index)
            for layer_index, indexes in enumerate(feasible)
            for option_index in indexes
        ),
        edge_queries=frozenset(
            key
            for key, supported in context.edge_support_cache.items()
            if supported
        ),
        completion_transitions=completion_transitions,
    )


def _constraint_uncertainty(option: _MeasuredFrameConstraint) -> float:
    return sum(
        edge.position.maximum - edge.position.minimum
        for edge in (option.leading, option.trailing)
    )


def _observation_candidate_count(option: _MeasuredFrameConstraint) -> int:
    return len(
        {
            edge.provenance.observation_id
            for edge in (option.leading, option.trailing)
            if edge.basis
            in {
                FrameBoundarySource.GRAY_PATH_OBSERVATION,
                FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION,
            }
        }
    )


def _best_graph_predecessor(
    current_index: int,
    previous: _GraphLayerStateIndex,
    ordered: tuple[_MeasuredFrameConstraint, ...],
    context: _SequenceGraphContext,
) -> tuple[int, int, int, float, float, int, float, int] | None:
    current = ordered[current_index]
    separator_key = _separator_boundary_key(current.leading)
    previous_indexes = previous.option_indexes
    if not previous_indexes:
        return None
    valid = np.logical_and(
        previous.leading_maxima < current.leading.position.minimum,
        previous.trailing_maxima < current.trailing.position.minimum,
    )
    common_width_minima = np.maximum(
        previous.frame_width_minima,
        current.width_px.minimum,
    )
    common_width_maxima = np.minimum(
        previous.frame_width_maxima,
        current.width_px.maximum,
    )
    common_width_available = common_width_maxima >= common_width_minima
    if separator_key is not None:
        separator_compatible = np.zeros(len(previous_indexes), dtype=bool)
        for key in (None, separator_key):
            offsets = previous.separator_offsets.get(key)
            if offsets is not None:
                separator_compatible[offsets] = True
        valid &= separator_compatible
    if not context.allow_nominal_slot_sized_gap:
        valid &= common_width_available
        valid &= (
            current.leading.position.maximum - previous.trailing_minima
            < common_width_minima
        )
    if context.run_starts:
        current_coverage = context.coverages[current_index]
        if current_coverage is None:
            return None
        previous_coverage_end = previous.coverage_ends
        valid &= np.isfinite(previous_coverage_end)
        gap_end = float(current_coverage[0])
        uncovered = gap_end > previous_coverage_end
        if np.any(uncovered):
            run_ends = np.asarray(context.run_ends, dtype=np.float64)
            run_starts = np.asarray(context.run_starts, dtype=np.float64)
            run_indexes = np.searchsorted(
                run_ends,
                previous_coverage_end,
                side="right",
            )
            next_run_start = np.full(len(previous_indexes), np.inf, dtype=np.float64)
            has_following_run = run_indexes < len(run_starts)
            next_run_start[has_following_run] = run_starts[
                run_indexes[has_following_run]
            ]
            valid &= np.logical_or(~uncovered, next_run_start >= gap_end)
    candidate_offsets = np.flatnonzero(valid)
    if not len(candidate_offsets):
        return None

    separator_supported = np.zeros(len(previous_indexes), dtype=np.int64)
    observation_increment = _observation_candidate_count(current)
    internal_quality = np.zeros(len(previous_indexes), dtype=np.float64)
    unexplained_spacing = np.maximum(
        0.0,
        current.leading.position.minimum - previous.trailing_maxima,
    )
    frame_sized_unexplained_gap = np.zeros(len(previous_indexes), dtype=np.int64)
    uncorroborated_overlap = np.maximum(
        0.0,
        previous.trailing_minima - current.leading.position.maximum,
    )
    uncorroborated_contact = np.logical_and(
        previous.trailing_minima == current.leading.position.minimum,
        previous.trailing_maxima == current.leading.position.maximum,
    ).astype(np.int64)
    if separator_key is not None:
        for offset in candidate_offsets:
            previous_option = ordered[previous_indexes[int(offset)]]
            if (
                common_width_available[offset]
                and _separator_edges_pair_at_boundary(previous_option, current)
                and previous_option.trailing.separator is not None
                and previous_option.trailing.separator_cross_axis is not None
                and previous_option.trailing.separator_cross_axis
                .complete_separator_supported
                and previous_option.trailing.separator.width_px.minimum > 0.0
                and previous_option.trailing.separator.width_px.maximum
                < common_width_minima[offset]
            ):
                separator_supported[offset] = 1
                internal_quality[offset] = (
                    previous_option.trailing.observation_quality
                    + current.leading.observation_quality
                )
                unexplained_spacing[offset] = 0.0
                uncorroborated_overlap[offset] = 0.0
                uncorroborated_contact[offset] = 0
    frame_sized_unexplained_gap = np.logical_and(
        common_width_available,
        unexplained_spacing >= common_width_minima,
    ).astype(np.int64)
    frame_sized_unexplained_gap[separator_supported.astype(bool)] = 0
    observation_counts = (
        previous.observation_candidate_counts + observation_increment
    )
    supported_counts = previous.supported_separator_counts + separator_supported
    qualities = previous.internal_measurement_qualities + internal_quality
    overlaps = previous.uncorroborated_overlap_extents + uncorroborated_overlap
    frame_sized_gaps = (
        previous.frame_sized_unexplained_gap_counts
        + frame_sized_unexplained_gap
    )
    unexplained = previous.unexplained_spacing_extents + unexplained_spacing
    contacts = previous.uncorroborated_contact_counts + uncorroborated_contact
    width_hint_residuals = previous.frame_width_hint_residuals
    uncertainties = previous.boundary_uncertainties
    leading_qualities = previous.external_leading_qualities

    remaining = candidate_offsets
    minimum_overlap = np.min(overlaps[remaining])
    remaining = remaining[overlaps[remaining] == minimum_overlap]
    minimum_frame_sized_gaps = np.min(frame_sized_gaps[remaining])
    remaining = remaining[
        frame_sized_gaps[remaining] == minimum_frame_sized_gaps
    ]
    maximum_count = np.max(supported_counts[remaining])
    remaining = remaining[supported_counts[remaining] == maximum_count]
    maximum_quality = np.max(qualities[remaining])
    remaining = remaining[qualities[remaining] == maximum_quality]
    minimum_contacts = np.min(contacts[remaining])
    remaining = remaining[contacts[remaining] == minimum_contacts]
    minimum_unexplained = np.min(unexplained[remaining])
    remaining = remaining[unexplained[remaining] == minimum_unexplained]
    maximum_leading_quality = np.max(leading_qualities[remaining])
    remaining = remaining[
        leading_qualities[remaining] == maximum_leading_quality
    ]
    minimum_width_hint_residual = np.min(width_hint_residuals[remaining])
    remaining = remaining[
        width_hint_residuals[remaining] == minimum_width_hint_residual
    ]
    maximum_observation_count = np.max(observation_counts[remaining])
    remaining = remaining[
        observation_counts[remaining] == maximum_observation_count
    ]
    minimum_uncertainty = np.min(uncertainties[remaining])
    remaining = remaining[uncertainties[remaining] == minimum_uncertainty]
    best_offset = max(
        (int(offset) for offset in remaining),
        key=lambda offset: previous.coordinate_keys[offset],
    )
    return (
        previous_indexes[best_offset],
        observation_increment,
        int(separator_supported[best_offset]),
        float(internal_quality[best_offset]),
        float(uncorroborated_overlap[best_offset]),
        int(frame_sized_unexplained_gap[best_offset]),
        float(unexplained_spacing[best_offset]),
        int(uncorroborated_contact[best_offset]),
    )


def _sequence_graph_best_path(
    grouped_options: tuple[
        tuple[tuple[int, _MeasuredFrameConstraint], ...],
        ...,
    ],
    ordered: tuple[_MeasuredFrameConstraint, ...],
    context: _SequenceGraphContext,
) -> tuple[_MeasuredFrameConstraint, ...] | None:
    states: list[dict[int, _GraphPathState]] = [
        {
            option_index: _GraphPathState(
                observation_candidate_count=_observation_candidate_count(option),
                supported_separator_count=0,
                internal_measurement_quality=0.0,
                uncorroborated_overlap_extent_px=0.0,
                frame_sized_unexplained_gap_count=0,
                unexplained_spacing_extent_px=0.0,
                uncorroborated_contact_count=0,
                frame_width_hint_residual=option.frame_width_hint_residual,
                boundary_uncertainty_px=_constraint_uncertainty(option),
                external_leading_quality=option.leading.measurement_quality,
                coordinate_key=(
                    -option.leading.position.midpoint,
                    -option.trailing.position.midpoint,
                ),
                predecessor=None,
            )
            for option_index, option in grouped_options[0]
            if context.first_mask & (1 << option_index)
        }
    ]
    for frame_options in grouped_options[1:]:
        previous_index = _graph_layer_state_index(
            states[-1],
            ordered,
            context,
        )
        current_states: dict[int, _GraphPathState] = {}
        for option_index, option in frame_options:
            predecessor = _best_graph_predecessor(
                option_index,
                previous_index,
                ordered,
                context,
            )
            if predecessor is None:
                continue
            (
                predecessor_index,
                observation_increment,
                separator_increment,
                quality_increment,
                overlap_increment,
                frame_sized_gap_increment,
                unexplained_increment,
                contact_increment,
            ) = predecessor
            previous = states[-1][predecessor_index]
            current_states[option_index] = _GraphPathState(
                observation_candidate_count=(
                    previous.observation_candidate_count
                    + observation_increment
                ),
                supported_separator_count=(
                    previous.supported_separator_count + separator_increment
                ),
                internal_measurement_quality=(
                    previous.internal_measurement_quality + quality_increment
                ),
                uncorroborated_overlap_extent_px=(
                    previous.uncorroborated_overlap_extent_px
                    + overlap_increment
                ),
                frame_sized_unexplained_gap_count=(
                    previous.frame_sized_unexplained_gap_count
                    + frame_sized_gap_increment
                ),
                unexplained_spacing_extent_px=(
                    previous.unexplained_spacing_extent_px
                    + unexplained_increment
                ),
                uncorroborated_contact_count=(
                    previous.uncorroborated_contact_count + contact_increment
                ),
                frame_width_hint_residual=(
                    previous.frame_width_hint_residual
                    + option.frame_width_hint_residual
                ),
                boundary_uncertainty_px=(
                    previous.boundary_uncertainty_px
                    + _constraint_uncertainty(option)
                ),
                external_leading_quality=previous.external_leading_quality,
                coordinate_key=(
                    *previous.coordinate_key,
                    -option.leading.position.midpoint,
                    -option.trailing.position.midpoint,
                ),
                predecessor=predecessor_index,
            )
        if not current_states:
            return None
        states.append(current_states)
    terminal_indexes = tuple(
        option_index
        for option_index in states[-1]
        if context.last_mask & (1 << option_index)
    )
    if not terminal_indexes:
        return None
    terminal_index = max(
        terminal_indexes,
        key=lambda option_index: (
            -states[-1][option_index].uncorroborated_overlap_extent_px,
            -states[-1][option_index].frame_sized_unexplained_gap_count,
            states[-1][option_index].supported_separator_count,
            states[-1][option_index].internal_measurement_quality,
            -states[-1][option_index].uncorroborated_contact_count,
            -states[-1][option_index].unexplained_spacing_extent_px,
            states[-1][option_index].external_leading_quality
            + ordered[option_index].trailing.measurement_quality,
            -states[-1][option_index].frame_width_hint_residual,
            states[-1][option_index].observation_candidate_count,
            -states[-1][option_index].boundary_uncertainty_px,
            states[-1][option_index].coordinate_key,
        ),
    )
    selected = [terminal_index]
    for layer_index in reversed(range(1, len(states))):
        predecessor = states[layer_index][selected[-1]].predecessor
        if predecessor is None:
            raise ValueError("graph path state lacks its predecessor")
        selected.append(predecessor)
    selected.reverse()
    sequence = tuple(ordered[index] for index in selected)
    return (
        sequence
        if _measured_constraint_common_width(sequence, len(sequence)) is not None
        else None
    )


def _sequence_boundary_has_supported_separator(
    left: _MeasuredFrameConstraint,
    right: _MeasuredFrameConstraint,
) -> bool:
    common_width = left.width_px.intersection(right.width_px)
    return bool(
        common_width is not None
        and _separator_edges_pair_at_boundary(left, right)
        and left.trailing.separator is not None
        and left.trailing.separator_cross_axis is not None
        and left.trailing.separator_cross_axis.complete_separator_supported
        and left.trailing.separator.width_px.minimum > 0.0
        and left.trailing.separator.width_px.maximum < common_width.minimum
    )


def _sequence_supported_separator_count(
    sequence: tuple[_MeasuredFrameConstraint, ...],
) -> int:
    return sum(
        _sequence_boundary_has_supported_separator(left, right)
        for left, right in zip(sequence, sequence[1:])
    )


def _graph_sequence_rank(
    sequence: tuple[_MeasuredFrameConstraint, ...],
) -> tuple[object, ...]:
    supported_separator_count = 0
    internal_measurement_quality = 0.0
    uncorroborated_overlap_extent_px = 0.0
    frame_sized_unexplained_gap_count = 0
    unexplained_spacing_extent_px = 0.0
    uncorroborated_contact_count = 0
    for left, right in zip(sequence, sequence[1:]):
        common_width = left.width_px.intersection(right.width_px)
        separator_supported = _sequence_boundary_has_supported_separator(
            left,
            right,
        )
        if separator_supported:
            supported_separator_count += 1
            internal_measurement_quality += (
                left.trailing.observation_quality
                + right.leading.observation_quality
            )
            continue
        uncorroborated_overlap_extent_px += max(
            0.0,
            left.trailing.position.minimum - right.leading.position.maximum,
        )
        unexplained_spacing_extent_px += max(
            0.0,
            right.leading.position.minimum - left.trailing.position.maximum,
        )
        if (
            common_width is not None
            and right.leading.position.minimum - left.trailing.position.maximum
            >= common_width.minimum
        ):
            frame_sized_unexplained_gap_count += 1
        uncorroborated_contact_count += int(
            left.trailing.position == right.leading.position
        )
    return (
        -uncorroborated_overlap_extent_px,
        -frame_sized_unexplained_gap_count,
        supported_separator_count,
        internal_measurement_quality,
        -uncorroborated_contact_count,
        -unexplained_spacing_extent_px,
        sequence[0].leading.measurement_quality
        + sequence[-1].trailing.measurement_quality,
        -sum(option.frame_width_hint_residual for option in sequence),
        sum(_observation_candidate_count(option) for option in sequence),
        -sum(_constraint_uncertainty(option) for option in sequence),
        tuple(
            coordinate
            for option in sequence
            for coordinate in (
                -option.leading.position.midpoint,
                -option.trailing.position.midpoint,
            )
        ),
    )


def _contact_neutral_sequence_rank(
    sequence: tuple[_MeasuredFrameConstraint, ...],
) -> tuple[object, ...]:
    rank = _graph_sequence_rank(sequence)
    return (*rank[:4], *rank[5:])


@dataclass(frozen=True)
class _SequenceGraphFeasibility:
    forward: tuple[dict[int, int | None], ...]
    backward: tuple[dict[int, int | None], ...]
    feasible: tuple[tuple[int, ...], ...]
    evaluations: _SequenceGraphEvaluations


def _sequence_graph_feasibility(
    grouped_options: tuple[
        tuple[tuple[int, _MeasuredFrameConstraint], ...],
        ...,
    ],
    ordered: tuple[_MeasuredFrameConstraint, ...],
    context: _SequenceGraphContext,
) -> _SequenceGraphFeasibility | None:
    forward: list[dict[int, int | None]] = [
        {
            option_index: None
            for option_index, _ in grouped_options[0]
            if context.first_mask & (1 << option_index)
        }
    ]
    for frame_options in grouped_options[1:]:
        forward.append(
            _reachable_predecessors(
                tuple(forward[-1]),
                tuple(option_index for option_index, _ in frame_options),
                ordered,
                context,
            )
        )

    backward: list[dict[int, int | None]] = [
        {} for _ in grouped_options
    ]
    backward[-1] = {
        option_index: None
        for option_index, _ in grouped_options[-1]
        if context.last_mask & (1 << option_index)
    }
    for layer_index in reversed(range(len(grouped_options) - 1)):
        backward[layer_index] = _reachable_successors(
            tuple(option_index for option_index, _ in grouped_options[layer_index]),
            tuple(backward[layer_index + 1]),
            ordered,
            context,
        )

    feasible = tuple(
        tuple(
            option_index
            for option_index, _ in frame_options
            if option_index in forward[layer_index]
            and option_index in backward[layer_index]
        )
        for layer_index, frame_options in enumerate(grouped_options)
    )
    if any(not indexes for indexes in feasible):
        return None
    return _SequenceGraphFeasibility(
        tuple(forward),
        tuple(backward),
        feasible,
        _sequence_graph_evaluations(
            feasible,
            ordered,
            context,
        ),
    )


def _graph_sequence_for_transition(
    layer_index: int,
    left_index: int,
    right_index: int,
    forward: list[dict[int, int | None]],
    backward: list[dict[int, int | None]],
    ordered: tuple[_MeasuredFrameConstraint, ...],
) -> tuple[_MeasuredFrameConstraint, ...]:
    selected = [left_index]
    current = left_index
    for prefix_layer in range(layer_index, 0, -1):
        predecessor = forward[prefix_layer][current]
        if predecessor is None:
            raise ValueError("feasible contact transition lacks a leading path")
        selected.insert(0, predecessor)
        current = predecessor
    selected.append(right_index)
    current = right_index
    for suffix_layer in range(layer_index + 1, len(backward) - 1):
        successor = backward[suffix_layer][current]
        if successor is None:
            raise ValueError("feasible contact transition lacks a trailing path")
        selected.append(successor)
        current = successor
    return tuple(ordered[index] for index in selected)


def _contact_transition_witnesses(
    forward: list[dict[int, int | None]],
    backward: list[dict[int, int | None]],
    ordered: tuple[_MeasuredFrameConstraint, ...],
) -> tuple[tuple[_MeasuredFrameConstraint, ...], ...]:
    best: tuple[_MeasuredFrameConstraint, ...] | None = None
    transitions = tuple(
        dict.fromkeys(
            (
                layer_index,
                left_index,
                right_index,
            )
            for layer_index in range(len(forward) - 1)
            for left_index, right_index in backward[layer_index].items()
            if right_index is not None
            and left_index in forward[layer_index]
            and right_index in forward[layer_index + 1]
            and right_index in backward[layer_index + 1]
            and ordered[left_index].trailing.position
            == ordered[right_index].leading.position
        )
    )
    for layer_index, left_index, right_index in transitions:
        sequence = _graph_sequence_for_transition(
            layer_index,
            left_index,
            right_index,
            forward,
            backward,
            ordered,
        )
        if (
            best is None
            or _contact_neutral_sequence_rank(sequence)
            > _contact_neutral_sequence_rank(best)
        ):
            best = sequence
    return () if best is None else (best,)


def _sequence_graph_witnesses(
    grouped_options: tuple[
        tuple[tuple[int, _MeasuredFrameConstraint], ...],
        ...,
    ],
    ordered: tuple[_MeasuredFrameConstraint, ...],
    context: _SequenceGraphContext,
    *,
    feasibility: _SequenceGraphFeasibility | None = None,
) -> tuple[tuple[_MeasuredFrameConstraint, ...], ...]:
    resolved = feasibility or _sequence_graph_feasibility(
        grouped_options,
        ordered,
        context,
    )
    if resolved is None:
        return ()
    forward = list(resolved.forward)
    backward = list(resolved.backward)
    feasible = resolved.feasible
    feasible_sets = tuple(set(indexes) for indexes in feasible)
    feasible_grouped_options = tuple(
        tuple(
            (option_index, option)
            for option_index, option in frame_options
            if option_index in feasible_sets[layer_index]
        )
        for layer_index, frame_options in enumerate(grouped_options)
    )
    physical_witness = _sequence_graph_best_path(
        feasible_grouped_options,
        ordered,
        context,
    )
    contact_witnesses = _contact_transition_witnesses(
        forward,
        backward,
        ordered,
    )
    targets: list[tuple[int, int]] = []
    targets.append((0, feasible[0][0]))
    if context.allow_nominal_slot_sized_gap:
        targets.extend(
            (layer_index, option_index)
            for layer_index, indexes in enumerate(feasible)
            for option_index in indexes
        )
    else:
        for layer_index, indexes in enumerate(feasible):
            for key in (
                lambda index: ordered[index].leading.position.minimum,
                lambda index: -ordered[index].leading.position.maximum,
                lambda index: ordered[index].trailing.position.minimum,
                lambda index: -ordered[index].trailing.position.maximum,
            ):
                targets.append((layer_index, max(indexes, key=key)))
    sequences: list[tuple[_MeasuredFrameConstraint, ...]] = []
    if physical_witness is not None:
        sequences.append(physical_witness)
    sequences.extend(contact_witnesses)
    for target_layer, target_index in dict.fromkeys(targets):
        sequences.append(
            _graph_sequence_for_target(
                target_layer,
                target_index,
                forward,
                backward,
                ordered,
            )
        )
    if context.allow_nominal_slot_sized_gap:
        @lru_cache(maxsize=None)
        def best_prefix(
            layer_index: int,
            option_index: int,
        ) -> tuple[_MeasuredFrameConstraint, ...] | None:
            option = ordered[option_index]
            if layer_index == 0:
                return (option,)
            candidates = tuple(
                (*prefix, option)
                for previous_index in feasible[layer_index - 1]
                if _cached_sequence_graph_edge_supported(
                    previous_index,
                    option_index,
                    ordered,
                    context,
                )
                and (
                    prefix := best_prefix(layer_index - 1, previous_index)
                )
                is not None
            )
            return max(candidates, key=_graph_sequence_rank, default=None)

        @lru_cache(maxsize=None)
        def best_suffix(
            layer_index: int,
            option_index: int,
        ) -> tuple[_MeasuredFrameConstraint, ...] | None:
            option = ordered[option_index]
            if layer_index == len(feasible) - 1:
                return (option,)
            candidates = tuple(
                (option, *suffix)
                for next_index in feasible[layer_index + 1]
                if _cached_sequence_graph_edge_supported(
                    option_index,
                    next_index,
                    ordered,
                    context,
                )
                and (
                    suffix := best_suffix(layer_index + 1, next_index)
                )
                is not None
            )
            return max(candidates, key=_graph_sequence_rank, default=None)

        for left_layer in range(len(feasible) - 1):
            for left_index in feasible[left_layer]:
                left = ordered[left_index]
                for right_index in feasible[left_layer + 1]:
                    right = ordered[right_index]
                    if not _cached_sequence_graph_edge_supported(
                        left_index,
                        right_index,
                        ordered,
                        context,
                    ):
                        continue
                    common_width = left.width_px.intersection(right.width_px)
                    if common_width is None:
                        continue
                    spacing = right.leading.position.minus(left.trailing.position)
                    if spacing.minimum < common_width.minimum:
                        continue
                    prefix = best_prefix(left_layer, left_index)
                    suffix = best_suffix(left_layer + 1, right_index)
                    if prefix is not None and suffix is not None:
                        sequences.append((*prefix, *suffix))
    return tuple(
        sequence
        for sequence in dict.fromkeys(sequences)
        if (
            len(sequence) == 1
            or _measured_constraint_common_width(sequence, len(sequence)) is not None
        )
    )


def _measured_frame_sequences(
    options: tuple[_MeasuredFrameConstraint, ...],
    count: int,
    visible_content: ContentRegionObservation,
    evaluation_budget: int,
    width_hypotheses: tuple[PixelInterval, ...],
    *,
    allow_nominal_slot_sized_gap: bool,
    minimum_supported_separator_count: int = 0,
) -> tuple[tuple[tuple[_MeasuredFrameConstraint, ...], ...], int, bool]:
    if minimum_supported_separator_count < 0:
        raise ValueError("separator support lower bound cannot be negative")
    ordered = tuple(
        sorted(
            options,
            key=_measured_frame_option_rank,
            reverse=True,
        )
    )
    evaluations = 0
    graph_evaluations = _SequenceGraphEvaluations(
        frozenset(),
        frozenset(),
        frozenset(),
    )
    sequences: list[tuple[_MeasuredFrameConstraint, ...]] = []
    truncated = False
    graph_context = _sequence_graph_context(
        ordered,
        visible_content,
        allow_nominal_slot_sized_gap=allow_nominal_slot_sized_gap,
    )
    options_by_frame = tuple(
        tuple(
            (option_index, option)
            for option_index, option in enumerate(ordered)
            if _option_is_valid_at_frame_index(option, frame_index, count)
        )
        for frame_index in range(1, count + 1)
    )
    if any(not frame_options for frame_options in options_by_frame):
        return (), evaluations, False
    width_index = _common_width_option_index(
        options_by_frame,
        count,
        width_hypotheses,
    )
    separator_pair_masks = _separator_pair_option_masks(
        width_index.option_lookups
    )
    for group_masks in width_index.group_masks:
        if (
            minimum_supported_separator_count
            and _separator_assignment_upper_bound(
                group_masks,
                separator_pair_masks,
            )
            < minimum_supported_separator_count
        ):
            continue
        grouped_options = _materialize_common_width_group(
            width_index,
            group_masks,
        )
        feasibility = _sequence_graph_feasibility(
            grouped_options,
            ordered,
            graph_context,
        )
        if feasibility is None:
            continue
        group_evaluations = feasibility.evaluations.incremental_cost(
            graph_evaluations
        )
        if evaluations + group_evaluations > evaluation_budget:
            truncated = True
            break
        evaluations += group_evaluations
        graph_evaluations = graph_evaluations.merged(feasibility.evaluations)
        sequences.extend(
            sequence
            for sequence in _sequence_graph_witnesses(
                grouped_options,
                ordered,
                graph_context,
                feasibility=feasibility,
            )
            if _sequence_supported_separator_count(sequence)
            >= minimum_supported_separator_count
        )
    return tuple(dict.fromkeys(sequences)), evaluations, truncated


def _content_preserving_complete_separator_builds(
    builds: tuple[_SequenceBuild, ...],
    visible_content: ContentRegionObservation,
) -> tuple[_SequenceBuild, ...]:
    return tuple(
        build
        for build in builds
        if _build_preserves_visible_content(build, visible_content)
        and len(build.separator_bindings) == max(0, len(build.slots) - 1)
        and len(build.spacings) == max(0, len(build.slots) - 1)
        and all(
            spacing.basis == InterFrameSpacingBasis.OBSERVED
            for spacing in build.spacings
        )
        and (
            len(build.slots) > 1
            or all(
                boundary.independently_observed
                for slot in build.slots
                for boundary in (slot.leading, slot.trailing)
            )
        )
    )


def _complete_separator_sequence_builds_dominate_dimension_inference(
    builds: tuple[_SequenceBuild, ...],
    visible_content: ContentRegionObservation,
) -> bool:
    return bool(
        _content_preserving_complete_separator_builds(builds, visible_content)
    )


def _measured_builds_for_options(
    options: tuple[_MeasuredFrameConstraint, ...],
    short_axis: SharedShortAxisSafetySpan,
    holder: Box,
    count: int,
    visible_content: ContentRegionObservation,
    evaluation_budget: int,
    width_hypotheses: tuple[PixelInterval, ...],
    *,
    allow_nominal_slot_sized_gap: bool,
    minimum_supported_separator_count: int = 0,
) -> tuple[tuple[_SequenceBuild, ...], int, bool]:
    states, evaluations, truncated = _measured_frame_sequences(
        options,
        count,
        visible_content,
        evaluation_budget,
        width_hypotheses,
        allow_nominal_slot_sized_gap=allow_nominal_slot_sized_gap,
        minimum_supported_separator_count=(
            minimum_supported_separator_count
        ),
    )
    return (
        tuple(
            build
            for state in states
            if (
                build := _measured_sequence_build(
                    state,
                    short_axis,
                    holder,
                    allow_nominal_slot_sized_gap=allow_nominal_slot_sized_gap,
                )
            )
            is not None
        ),
        evaluations,
        truncated,
    )


def _supported_separator_incumbent(
    builds: tuple[_SequenceBuild, ...],
    visible_content: ContentRegionObservation,
) -> int:
    return max(
        (
            build.objectives.supported_separator_count
            for build in builds
            if build.objectives.uncorroborated_overlap_extent_px == 0.0
            and _build_preserves_visible_content(build, visible_content)
        ),
        default=0,
    )


def _measured_path_builds(
    search_scope: FrameSequenceSearchScope,
    search_index: FrameSequenceSearchIndex,
    short_axis_spans: tuple[SharedShortAxisSafetySpan, ...],
    search_widths: tuple[PixelInterval, ...],
    frame_width_hint: PixelInterval,
    count: int,
    visible_content: ContentRegionObservation,
    evaluation_budget: int,
    placement_widths: tuple[PixelInterval, ...],
    *,
    physical_scale_constraint: FrameWidthPhysicalScaleConstraint | None,
    allow_nominal_slot_sized_gap: bool,
) -> tuple[tuple[_SequenceBuild, ...], int, bool]:
    holder = search_scope.holder_safety.box
    builds: list[_SequenceBuild] = []
    evaluations = 0
    search_truncated = False
    for short_axis_index, short_axis in enumerate(short_axis_spans):
        remaining = evaluation_budget - evaluations
        if remaining <= 0:
            return tuple(builds), evaluations, True
        search_space = _measured_frame_search_space(
            search_index,
            search_widths,
            frame_width_hint,
            physical_scale_constraint,
        )
        geometry_separator_leading, geometry_separator_trailing = (
            _separator_geometry_edge_candidates(
                search_index.separator_supports.canonical_supports,
                search_scope,
            )
        )
        dimension_leading_candidates = tuple(
            dict.fromkeys(
                (*search_space.leading_candidates, *geometry_separator_leading)
            )
        )
        dimension_trailing_candidates = tuple(
            dict.fromkeys(
                (*search_space.trailing_candidates, *geometry_separator_trailing)
            )
        )
        dimension_leading_seeds = dimension_leading_candidates
        dimension_trailing_seeds = dimension_trailing_candidates
        strong_dimension_seed_search = _has_supported_internal_separator_edge_seed(
            (*dimension_leading_candidates, *dimension_trailing_candidates)
        )
        if strong_dimension_seed_search:
            dimension_leading_seeds = _dimension_seed_candidates(
                dimension_leading_candidates
            )
            dimension_trailing_seeds = _dimension_seed_candidates(
                dimension_trailing_candidates
            )

        observed_widths = tuple(
            hypothesis.width_px
            for hypothesis in search_space.width_hypotheses
        )

        observed_builds: list[_SequenceBuild] = []
        observed_evaluations = 0
        separator_incumbent = 0
        observed_truncated = False
        if count == 1 or observed_widths:
            (
                observed_builds,
                observed_evaluations,
                observed_truncated,
            ) = _measured_builds_for_options(
                search_space.observed_constraints,
                short_axis,
                holder,
                count,
                visible_content,
                remaining,
                observed_widths,
                allow_nominal_slot_sized_gap=allow_nominal_slot_sized_gap,
                minimum_supported_separator_count=separator_incumbent,
            )
        evaluations += observed_evaluations
        builds.extend(observed_builds)
        separator_incumbent = _supported_separator_incumbent(
            tuple(observed_builds),
            visible_content,
        )
        if observed_truncated:
            search_truncated = True

        complete_separator_sequence_build = (
            _complete_separator_sequence_builds_dominate_dimension_inference(
                tuple(observed_builds),
                visible_content,
            )
        )

        dimension_hypotheses: tuple[_DimensionPlacementHypothesis, ...] = ()
        if count > 1 and not complete_separator_sequence_build:
            dimension_hypotheses = _dimension_placement_hypotheses(
                search_space.width_hypotheses,
                search_space.recurring_width_hypotheses,
                placement_widths,
                physical_scale_constraint,
            )

        holder_axis = _holder_axis_interval(
            search_scope.holder_safety.box,
            BoundaryAxis.LONG,
        )
        for hypothesis in dimension_hypotheses if not search_truncated else ():
            if not _width_hypothesis_can_cover_reliable_content(
                hypothesis,
                count,
                visible_content,
            ):
                continue
            remaining = evaluation_budget - evaluations
            if remaining <= 0:
                search_truncated = True
                break
            seed_passes = (
                (
                    dimension_leading_seeds,
                    dimension_trailing_seeds,
                ),
                *(
                    (
                        (
                            dimension_leading_candidates,
                            dimension_trailing_candidates,
                        ),
                    )
                    if strong_dimension_seed_search
                    else ()
                ),
            )
            hypothesis_builds: list[_SequenceBuild] = []
            states_truncated = False
            for leading_seeds, trailing_seeds in seed_passes:
                remaining = evaluation_budget - evaluations
                if remaining <= 0:
                    states_truncated = True
                    break
                dimension_constraints = _dimension_frame_constraints(
                    leading_seeds,
                    trailing_seeds,
                    dimension_leading_candidates,
                    dimension_trailing_candidates,
                    (hypothesis,),
                    holder_axis,
                    search_widths,
                    frame_width_hint,
                )
                if len(dimension_constraints) > remaining:
                    states_truncated = True
                    break
                evaluations += len(dimension_constraints)
                options = _canonical_measured_frame_constraints(
                    dimension_constraints
                )
                if not options:
                    continue
                branch_builds, state_evaluations, branch_truncated = (
                    _measured_builds_for_options(
                        options,
                        short_axis,
                        holder,
                        count,
                        visible_content,
                        evaluation_budget - evaluations,
                        (hypothesis.width_px,),
                        allow_nominal_slot_sized_gap=(
                            allow_nominal_slot_sized_gap
                        ),
                        minimum_supported_separator_count=(
                            separator_incumbent
                        ),
                    )
                )
                evaluations += state_evaluations
                hypothesis_builds.extend(branch_builds)
                if branch_truncated:
                    states_truncated = True
                    break
                if strong_dimension_seed_search and separator_incumbent:
                    break
                if _supported_separator_incumbent(
                    tuple(branch_builds),
                    visible_content,
                ):
                    break
            branch_builds = tuple(dict.fromkeys(hypothesis_builds))
            builds.extend(branch_builds)
            separator_incumbent = max(
                separator_incumbent,
                _supported_separator_incumbent(
                    tuple(branch_builds),
                    visible_content,
                ),
            )
            if states_truncated:
                search_truncated = True
                break

        if complete_separator_sequence_build:
            return tuple(dict.fromkeys(builds)), evaluations, search_truncated

        if search_truncated:
            break

        if evaluations >= evaluation_budget:
            search_truncated = bool(
                search_truncated
                or short_axis_index + 1 < len(short_axis_spans)
            )
            break
    return tuple(dict.fromkeys(builds)), evaluations, search_truncated


def _spacing_for_band(
    boundary_index: int,
    support: SeparatorBandCrossAxisSupport,
    trailing: ResolvedFrameBoundary,
    leading: ResolvedFrameBoundary,
) -> tuple[InterFrameSpacing, _SeparatorBandBinding | None]:
    band = support.observation
    measurement = support.measurement
    supported = bool(
        measurement.complete_separator_supported
        and trailing.role_state == EvidenceState.SUPPORTED
        and leading.role_state == EvidenceState.SUPPORTED
        and trailing.source == FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION
        and leading.source == FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION
    )
    assignment = (
        _SeparatorBandBinding(
            boundary_index,
            band,
            measurement,
            trailing,
            leading,
        )
        if supported
        else None
    )
    if assignment is not None:
        provenance = band.provenance
        basis = InterFrameSpacingBasis.OBSERVED
    elif (
        trailing.source == FrameBoundarySource.GRAY_PATH_OBSERVATION
        and leading.source == FrameBoundarySource.GRAY_PATH_OBSERVATION
    ):
        return (
            _spacing_from_frame_edges(
                boundary_index,
                trailing,
                leading,
            ),
            None,
        )
    else:
        provenance = MeasurementProvenance(
            root_measurement=MeasurementIdentity.FRAME_GEOMETRY,
            observation_id=ObservationId(
                f"dimension_spacing:{boundary_index}:"
                f"{trailing.measurement_provenance.observation_id}:"
                f"{leading.measurement_provenance.observation_id}"
            ),
            dependencies=tuple(
                dict.fromkeys(
                    (
                        MeasurementIdentity.FRAME_DIMENSIONS,
                        band.provenance.root_measurement,
                    )
                )
            ),
            description="dimension-constrained inter-frame spacing",
            boundary_anchors=tuple(
                dict.fromkeys(
                    (
                        trailing.measurement_provenance.observation_id,
                        leading.measurement_provenance.observation_id,
                    )
                )
            ),
        )
        basis = InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS
    return (
        InterFrameSpacing(
            boundary=InterFrameBoundaryReference(None, boundary_index),
            signed_width_px=leading.position.minus(trailing.position),
            provenance=provenance,
            basis=basis,
        ),
        assignment,
    )


def _build_sequence(
    band_hypothesis: _BandSequenceHypothesis,
    short_axis: SharedShortAxisSafetySpan,
    leading_endpoint: _EdgeConstraint,
    trailing_endpoint: _EdgeConstraint,
    frame_width: PixelInterval,
    count: int,
    holder: Box,
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
    physical_scale_constraint: FrameWidthPhysicalScaleConstraint | None,
) -> _SequenceBuild | None:
    band_edges = band_hypothesis.band_edges
    leading_constraints = (
        leading_endpoint,
        *tuple(following for _, following in band_edges),
    )
    trailing_constraints = (
        *tuple(preceding for preceding, _ in band_edges),
        trailing_endpoint,
    )
    if len(leading_constraints) != count or len(trailing_constraints) != count:
        raise ValueError("frame sequence constraints must match requested count")

    refined_constraints: list[_MeasuredFrameConstraint] = []
    for frame_index, (leading_constraint, trailing_constraint) in enumerate(
        zip(leading_constraints, trailing_constraints, strict=True),
        start=1,
    ):
        leading_clip_supported = bool(
            frame_index == 1
            and leading_constraint.path is not None
            and _holder_boundary_supports_path(
                leading_constraint.path,
                holder_boundaries.get(BoundarySide.LEADING),
            )
        )
        trailing_clip_supported = bool(
            frame_index == count
            and trailing_constraint.path is not None
            and _holder_boundary_supports_path(
                trailing_constraint.path,
                holder_boundaries.get(BoundarySide.TRAILING),
            )
        )
        refined = _refine_frame_edges(
            leading_constraint,
            trailing_constraint,
            frame_width,
            allow_underwidth=leading_clip_supported or trailing_clip_supported,
        )
        if refined is None:
            return None
        refined_leading, refined_trailing = refined
        visible_width = _visible_width(refined_leading, refined_trailing)
        if visible_width is None:
            return None
        refined_constraints.append(
            _MeasuredFrameConstraint(
                leading=refined_leading,
                trailing=refined_trailing,
                width_px=visible_width,
                full_width_hypothesis_admissible=True,
                leading_holder_clip_supported=leading_clip_supported,
                trailing_holder_clip_supported=trailing_clip_supported,
                search_order_residual=band_hypothesis.search_order_residual,
            )
        )

    separator_roles_are_physically_feasible = bool(
        physical_scale_constraint is None
        or _sequence_constraints_fit_physical_scale(
            tuple(refined_constraints),
            physical_scale_constraint,
        )
    )
    if separator_roles_are_physically_feasible:
        refined_constraints = list(
            _candidate_specific_separator_edge_roles(tuple(refined_constraints))
        )
        refined_constraints = list(
            _candidate_specific_holder_band_roles(
                tuple(refined_constraints),
                frame_width,
                holder_boundaries,
            )
        )
    slots: list[FrameSlot] = []
    assignments: list[FrameEdgeAssignment] = []
    for frame_index, constraint in enumerate(refined_constraints, start=1):
        leading, leading_assignment = _resolution(
            frame_index,
            BoundarySide.LEADING,
            constraint.leading,
        )
        trailing, trailing_assignment = _resolution(
            frame_index,
            BoundarySide.TRAILING,
            constraint.trailing,
        )
        assignments.extend(
            item
            for item in (
                leading_assignment,
                trailing_assignment,
            )
            if item is not None
        )
        slots.append(
            FrameSlot(
                index=frame_index,
                visible_long_axis=PixelInterval(
                    leading.position.minimum,
                    trailing.position.maximum,
                ),
                leading=leading,
                trailing=trailing,
                content_occupancy=FrameContentOccupancy.UNAVAILABLE,
                edge_occlusion=None,
            )
        )

    spacings: list[InterFrameSpacing] = []
    separator_bindings: list[_SeparatorBandBinding] = []
    for boundary_index, support in enumerate(band_hypothesis.supports, start=1):
        signed_width = slots[boundary_index].leading.position.minus(
            slots[boundary_index - 1].trailing.position
        )
        if signed_width.maximum < 0.0:
            return None
        spacing, assignment = _spacing_for_band(
            boundary_index,
            support,
            slots[boundary_index - 1].trailing,
            slots[boundary_index].leading,
        )
        spacings.append(spacing)
        if assignment is not None:
            separator_bindings.append(assignment)

    frame_widths = tuple(
        slot.trailing.position.minus(slot.leading.position)
        for slot in slots
    )
    interior_widths = (
        frame_widths[1:-1]
        if count >= MINIMUM_COUNT_WITH_INTERIOR_FRAME
        else frame_widths
    )
    dimension_residual = max(
        (
            _normalized_interval_contradiction(width, frame_width)
            for width in interior_widths
        ),
        default=0.0,
    )
    uncertainty_px = sum(
        edge.position.maximum - edge.position.minimum
        for slot in slots
        for edge in (
            slot.leading,
            slot.trailing,
        )
    ) + short_axis.uncertainty_px
    residuals = SequenceResiduals(
        dimension=float(dimension_residual),
        boundary_uncertainty=float(uncertainty_px)
        / max(
            MINIMUM_POSITIVE_PIXEL_EXTENT,
            float(holder.width + holder.height),
        ),
    )
    endpoint_quality = (
        leading_endpoint.measurement_quality + trailing_endpoint.measurement_quality
    )
    return _SequenceBuild(
        slots=tuple(slots),
        long_axis_assignments=tuple(assignments),
        separator_bindings=tuple(separator_bindings),
        spacings=tuple(spacings),
        frame_width_px=frame_width,
        short_axis=short_axis,
        residuals=residuals,
        objectives=_SequenceBuildObjectives(
            uncorroborated_overlap_extent_px=_uncorroborated_overlap_extent(
                tuple(spacings)
            ),
            unexplained_spacing_extent_px=_unexplained_spacing_extent(
                tuple(spacings)
            ),
            supported_separator_count=len(separator_bindings),
            internal_boundary_measurement_quality=(
                band_hypothesis.measurement_quality
            ),
            dimension_residual=float(dimension_residual),
            external_boundary_measurement_quality=(
                endpoint_quality
            ),
            boundary_uncertainty_ratio=float(residuals.boundary_uncertainty),
            frame_width_hint_residual=band_hypothesis.search_order_residual,
            uncorroborated_contact_count=_uncorroborated_contact_count(
                tuple(spacings)
            ),
            inferred_boundary_count=_inferred_boundary_count(tuple(slots)),
        ),
    )


def _builds_for_hypotheses(
    band_hypotheses: tuple[_BandSequenceHypothesis, ...],
    search_scope: FrameSequenceSearchScope,
    long_paths: tuple[GrayBoundaryPathObservation, ...],
    separator_supports: tuple[SeparatorBandCrossAxisSupport, ...],
    count: int,
    evaluation_budget: int,
    physical_scale_constraint: FrameWidthPhysicalScaleConstraint | None,
) -> tuple[tuple[_SequenceBuild, ...], int, bool]:
    holder = search_scope.holder_safety.box
    holder_boundaries = _holder_boundaries(search_scope)
    separator_leading, separator_trailing = _separator_edge_candidates(
        separator_supports,
        search_scope,
    )
    leading_separator_endpoints = tuple(
        constraint
        for constraint, _ in separator_leading
        if constraint.external_side == BoundarySide.LEADING
    )
    trailing_separator_endpoints = tuple(
        constraint
        for constraint, _ in separator_trailing
        if constraint.external_side == BoundarySide.TRAILING
    )
    builds: list[_SequenceBuild] = []
    evaluations = 0
    exhausted = False
    ordered_hypotheses = tuple(
        sorted(
            band_hypotheses,
            key=lambda item: (
                item.paired_band_count,
                item.measurement_quality,
                -item.search_order_residual,
                -item.uncertainty_px,
            ),
            reverse=True,
        )
    )
    for band_hypothesis in ordered_hypotheses:
        short_axis = band_hypothesis.short_axis
        if evaluations >= evaluation_budget:
            exhausted = True
            break
        evaluations += 1
        endpoint_search_width = (
            band_hypothesis.frame_width_px
            if band_hypothesis.indexed_anchor_count > 0
            else PixelInterval(
                MINIMUM_POSITIVE_PIXEL_EXTENT,
                float(holder.width),
            )
        )
        first_edges = band_hypothesis.band_edges[0]
        last_edges = band_hypothesis.band_edges[-1]
        leading_options = _admissible_frame_endpoints(
            long_paths,
            first_edges[0],
            endpoint_search_width,
            holder_boundaries.get(BoundarySide.LEADING),
            holder,
            leading=True,
            additional_constraints=leading_separator_endpoints,
        )
        trailing_options = _admissible_frame_endpoints(
            long_paths,
            last_edges[1],
            endpoint_search_width,
            holder_boundaries.get(BoundarySide.TRAILING),
            holder,
            leading=False,
            additional_constraints=trailing_separator_endpoints,
        )
        for leading_endpoint in leading_options:
            for trailing_endpoint in trailing_options:
                if evaluations >= evaluation_budget:
                    exhausted = True
                    break
                evaluations += 1
                if trailing_endpoint.position.minimum <= leading_endpoint.position.maximum:
                    continue
                frame_width = _frame_width_for_endpoints(
                    band_hypothesis,
                    leading_endpoint,
                    trailing_endpoint,
                    holder_boundaries,
                )
                if frame_width is None:
                    continue
                if not all(
                    _band_edge_interpretation_is_admissible(
                        band_index,
                        band_hypothesis.supports,
                        band_hypothesis.band_edges,
                        frame_width,
                    )
                    for band_index in range(len(band_hypothesis.supports))
                ):
                    continue
                build = _build_sequence(
                    band_hypothesis,
                    short_axis,
                    leading_endpoint,
                    trailing_endpoint,
                    frame_width,
                    count,
                    holder,
                    holder_boundaries,
                    physical_scale_constraint,
                )
                if build is not None:
                    builds.append(build)
            if exhausted:
                break
        if exhausted:
            break
    return tuple(builds), evaluations, exhausted


def _boundaries_share_one_placement(
    boundaries: tuple[ResolvedFrameBoundary, ...],
) -> bool:
    if PixelInterval.common_intersection(
        tuple(boundary.position for boundary in boundaries)
    ) is not None:
        return True
    return all(
        boundary.source == FrameBoundarySource.DIMENSION_CONSTRAINED
        and not boundary.independently_observed
        for boundary in boundaries
    )


def _conflicting_internal_frame_indexes(
    builds: tuple[_SequenceBuild, ...],
) -> tuple[int, ...]:
    reference = builds[0]
    has_internal_geometry = len(reference.slots) > 1
    conflicts: list[int] = []
    for frame_index in range(1, len(reference.slots) + 1):
        slots = tuple(build.slots[frame_index - 1] for build in builds)
        if all(slot.sequence_inferred for slot in slots):
            continue
        sides = tuple(
            side
            for side in (BoundarySide.LEADING, BoundarySide.TRAILING)
            if not (
                (
                    has_internal_geometry
                    and
                    frame_index == 1
                    and side == BoundarySide.LEADING
                    and all(not slot.sequence_inferred for slot in slots)
                )
                or (
                    has_internal_geometry
                    and
                    frame_index == len(reference.slots)
                    and side == BoundarySide.TRAILING
                    and all(not slot.sequence_inferred for slot in slots)
                )
            )
        )
        if any(
            not _boundaries_share_one_placement(
                tuple(
                    slot.leading
                    if side == BoundarySide.LEADING
                    else slot.trailing
                    for slot in slots
                )
            )
            for side in sides
        ):
            conflicts.append(frame_index)
    return tuple(conflicts)


def _external_endpoint_alternatives(
    builds: tuple[_SequenceBuild, ...],
) -> bool:
    if (
        len(builds) <= 1
        or any(build.slots[0].sequence_inferred or build.slots[-1].sequence_inferred for build in builds)
    ):
        return False
    return any(
        PixelInterval.common_intersection(
            tuple(
                (
                    build.slots[0].leading.position
                    if side == BoundarySide.LEADING
                    else build.slots[-1].trailing.position
                )
                for build in builds
            )
        )
        is None
        for side in (BoundarySide.LEADING, BoundarySide.TRAILING)
    )


def _sequence_inference_signature(
    build: _SequenceBuild,
) -> tuple[int, ...]:
    return (
        tuple(slot.index for slot in build.slots if slot.sequence_inferred)
        if len(build.slots) > 1
        else ()
    )


def _internal_boundary_role_map(
    build: _SequenceBuild,
) -> dict[tuple[int, BoundarySide], ResolvedFrameBoundary]:
    roles: dict[tuple[int, BoundarySide], ResolvedFrameBoundary] = {}
    for left, right in zip(build.slots, build.slots[1:]):
        if boundary_role_is_independent_physical_measurement(left.trailing):
            roles[(left.index, BoundarySide.TRAILING)] = left.trailing
        if boundary_role_is_independent_physical_measurement(right.leading):
            roles[(right.index, BoundarySide.LEADING)] = right.leading
    return roles


def _boundary_role_map_strictly_dominates(
    left: _SequenceBuild,
    right: _SequenceBuild,
) -> bool:
    if _sequence_inference_signature(left) != _sequence_inference_signature(right):
        return False
    left_roles = _internal_boundary_role_map(left)
    right_roles = _internal_boundary_role_map(right)
    return bool(
        left_roles.keys() > right_roles.keys()
        and all(
            left_roles[key].position.intersects(boundary.position)
            for key, boundary in right_roles.items()
        )
    )


def _build_has_independent_boundary_support(build: _SequenceBuild) -> bool:
    return bool(
        build.objectives.supported_separator_count
        or _internal_boundary_role_map(build)
    )


def _physically_preferred_builds(
    builds: tuple[_SequenceBuild, ...],
) -> tuple[_SequenceBuild, ...]:
    if not builds:
        raise ValueError("physical sequence ranking requires builds")
    independently_supported = tuple(
        build
        for build in builds
        if _build_has_independent_boundary_support(build)
    )
    if not independently_supported:
        return builds
    builds = independently_supported
    builds = tuple(
        build
        for build in builds
        if not any(
            other is not build
            and _boundary_role_map_strictly_dominates(other, build)
            for other in builds
        )
    )
    minimum_uncorroborated_overlap = min(
        build.objectives.uncorroborated_overlap_extent_px
        for build in builds
    )
    non_overlapping = tuple(
        build
        for build in builds
        if build.objectives.uncorroborated_overlap_extent_px
        == minimum_uncorroborated_overlap
    )
    strongest_separator_support = max(
        build.objectives.supported_separator_count
        for build in non_overlapping
    )
    physically_anchored = tuple(
        build
        for build in non_overlapping
        if build.objectives.supported_separator_count
        == strongest_separator_support
    )
    return tuple(
        build
        for build in physically_anchored
        if not any(
            other is not build
            and other.objectives.dominates(build.objectives)
            for other in physically_anchored
        )
    )


def _representative_build(
    builds: tuple[_SequenceBuild, ...],
) -> _SequenceBuild:
    if not builds:
        raise ValueError("representative sequence requires physical builds")
    return max(
        builds,
        key=lambda build: (
            _build_has_independent_boundary_support(build),
            -build.objectives.uncorroborated_overlap_extent_px,
            -build.objectives.uncorroborated_contact_count,
            build.objectives.supported_separator_count,
            build.objectives.internal_boundary_measurement_quality,
            build.objectives.external_boundary_measurement_quality,
            -build.objectives.inferred_boundary_count,
            -build.objectives.unexplained_spacing_extent_px,
            -build.objectives.dimension_residual,
            -build.objectives.frame_width_hint_residual,
            -build.objectives.boundary_uncertainty_ratio,
            tuple(
                -edge.position.midpoint
                for slot in build.slots
                for edge in (slot.leading, slot.trailing)
            ),
        ),
    )


def _assignment_consensus(
    builds: tuple[_SequenceBuild, ...],
) -> BoundaryAssignmentConsensus:
    conflicting = _conflicting_internal_frame_indexes(builds)
    if conflicting:
        outcome = AssignmentConsensusOutcome.DISAGREED
    elif len(builds) == 1:
        outcome = AssignmentConsensusOutcome.UNCONTESTED
    elif _external_endpoint_alternatives(builds):
        outcome = AssignmentConsensusOutcome.EXTERNAL_SAFETY_ENVELOPE
    else:
        outcome = AssignmentConsensusOutcome.AGREED
    return BoundaryAssignmentConsensus(outcome, len(builds), conflicting)


def _sequence_assignment_consensus(
    preferred_builds: tuple[_SequenceBuild, ...],
) -> BoundaryAssignmentConsensus:
    inferred_positions = {
        slot.index
        for build in preferred_builds
        for slot in build.slots
        if slot.sequence_inferred
    }
    if len(inferred_positions) > 1:
        return BoundaryAssignmentConsensus(
            AssignmentConsensusOutcome.DISAGREED,
            len(preferred_builds),
            tuple(sorted(inferred_positions)),
        )
    return _assignment_consensus(preferred_builds)


def _external_safety_provenance(
    side: BoundarySide,
    boundaries: tuple[ResolvedFrameBoundary, ...],
) -> MeasurementProvenance:
    inputs = tuple(
        dict.fromkeys(
            (
                *(boundary.measurement_provenance for boundary in boundaries),
                *(
                    boundary.role_provenance
                    for boundary in boundaries
                    if boundary.role_provenance is not None
                ),
            )
        )
    )
    dependencies = tuple(
        sorted(
            {
                dependency
                for item in inputs
                for dependency in (item.root_measurement, *item.dependencies)
                if dependency != MeasurementIdentity.FRAME_GEOMETRY
            },
            key=lambda item: item.value,
        )
    )
    anchors = tuple(
        dict.fromkeys(
            anchor
            for item in inputs
            for anchor in (item.observation_id, *item.boundary_anchors)
        )
    )
    digest = hashlib.sha256(
        "\x1f".join(
            (
                side.value,
                *(
                    f"{boundary.position.minimum:.12g}:"
                    f"{boundary.position.maximum:.12g}:"
                    f"{boundary.measurement_provenance.observation_id}"
                    for boundary in boundaries
                ),
            )
        ).encode("utf-8")
    ).hexdigest()
    return MeasurementProvenance(
        root_measurement=MeasurementIdentity.FRAME_GEOMETRY,
        observation_id=ObservationId(f"external_safety_envelope:{digest}"),
        dependencies=dependencies,
        description=(
            "conservative external crop boundary spanning physically equivalent "
            "endpoint observations"
        ),
        boundary_anchors=anchors,
    )


def _internal_geometry_uncertainty_boundary(
    side: BoundarySide,
    boundaries: tuple[ResolvedFrameBoundary, ...],
) -> ResolvedFrameBoundary:
    if side not in {BoundarySide.LEADING, BoundarySide.TRAILING}:
        raise ValueError("internal geometry uncertainty requires a long-axis side")
    if not boundaries or any(
        boundary.source != FrameBoundarySource.DIMENSION_CONSTRAINED
        or boundary.independently_observed
        for boundary in boundaries
    ):
        raise ValueError(
            "internal geometry uncertainty can combine only dimension constraints"
        )
    inputs = tuple(
        dict.fromkeys(boundary.measurement_provenance for boundary in boundaries)
    )
    dependencies = tuple(
        sorted(
            {
                dependency
                for item in inputs
                for dependency in (item.root_measurement, *item.dependencies)
                if dependency != MeasurementIdentity.FRAME_GEOMETRY
            },
            key=lambda item: item.value,
        )
    )
    anchors = tuple(
        dict.fromkeys(
            anchor
            for item in inputs
            for anchor in (item.observation_id, *item.boundary_anchors)
        )
    )
    digest = hashlib.sha256(
        "\x1f".join(
            (
                side.value,
                *(
                    f"{boundary.position.minimum:.12g}:"
                    f"{boundary.position.maximum:.12g}:"
                    f"{boundary.measurement_provenance.observation_id}"
                    for boundary in boundaries
                ),
            )
        ).encode("utf-8")
    ).hexdigest()
    return ResolvedFrameBoundary(
        position=PixelInterval(
            min(boundary.position.minimum for boundary in boundaries),
            max(boundary.position.maximum for boundary in boundaries),
        ),
        source=FrameBoundarySource.DIMENSION_CONSTRAINED,
        geometry_state=BoundaryGeometryState.RESOLVED,
        boundary_anchor=None,
        inference_provenance=MeasurementProvenance(
            root_measurement=MeasurementIdentity.FRAME_GEOMETRY,
            observation_id=ObservationId(
                f"internal_geometry_uncertainty:{side.value}:{digest}"
            ),
            dependencies=dependencies,
            description=(
                "conservative internal boundary interval across equivalent "
                "dimension-constrained sequence solutions"
            ),
            boundary_anchors=anchors,
        ),
    )


def _apply_internal_geometry_uncertainty(
    slots: tuple[FrameSlot, ...],
    assignments: tuple[FrameEdgeAssignment, ...],
    preferred_builds: tuple[_SequenceBuild, ...],
) -> tuple[tuple[FrameSlot, ...], tuple[FrameEdgeAssignment, ...]] | None:
    if len(preferred_builds) <= 1:
        return slots, assignments
    updated = list(slots)
    replaced: set[tuple[int, BoundarySide]] = set()
    for offset, slot in enumerate(slots):
        sides = tuple(
            side
            for side in (BoundarySide.LEADING, BoundarySide.TRAILING)
            if not (
                (offset == 0 and side == BoundarySide.LEADING)
                or (
                    offset == len(slots) - 1
                    and side == BoundarySide.TRAILING
                )
            )
        )
        for side in sides:
            boundaries = tuple(
                (
                    build.slots[offset].leading
                    if side == BoundarySide.LEADING
                    else build.slots[offset].trailing
                )
                for build in preferred_builds
            )
            if PixelInterval.common_intersection(
                tuple(boundary.position for boundary in boundaries)
            ) is not None:
                continue
            if any(
                boundary.source != FrameBoundarySource.DIMENSION_CONSTRAINED
                or boundary.independently_observed
                for boundary in boundaries
            ):
                return None
            envelope = _internal_geometry_uncertainty_boundary(side, boundaries)
            current = updated[offset]
            updated[offset] = replace(
                current,
                leading=(envelope if side == BoundarySide.LEADING else current.leading),
                trailing=(envelope if side == BoundarySide.TRAILING else current.trailing),
                visible_long_axis=PixelInterval(
                    (
                        envelope.position.minimum
                        if side == BoundarySide.LEADING
                        else current.visible_long_axis.minimum
                    ),
                    (
                        envelope.position.maximum
                        if side == BoundarySide.TRAILING
                        else current.visible_long_axis.maximum
                    ),
                ),
            )
            replaced.add((slot.index, side))
    result = tuple(updated)
    if not _frame_slots_are_strictly_monotonic(result):
        return None
    return (
        result,
        tuple(
            assignment
            for assignment in assignments
            if (assignment.frame_index, assignment.side) not in replaced
        ),
    )


def _external_safety_boundary(
    side: BoundarySide,
    boundaries: tuple[ResolvedFrameBoundary, ...],
    holder_safety: PixelInterval,
) -> ResolvedFrameBoundary | None:
    position = PixelInterval(
        min(boundary.position.minimum for boundary in boundaries),
        max(boundary.position.maximum for boundary in boundaries),
    ).intersection(holder_safety)
    if position is None:
        return None
    return ResolvedFrameBoundary(
        position=position,
        source=FrameBoundarySource.EXTERNAL_SAFETY_ENVELOPE,
        geometry_state=BoundaryGeometryState.RESOLVED,
        boundary_anchor=None,
        inference_provenance=_external_safety_provenance(side, boundaries),
    )


def _apply_external_safety_envelope(
    slots: tuple[FrameSlot, ...],
    assignments: tuple[FrameEdgeAssignment, ...],
    preferred_builds: tuple[_SequenceBuild, ...],
    consensus: BoundaryAssignmentConsensus,
    holder_safety: PixelInterval,
) -> tuple[tuple[FrameSlot, ...], tuple[FrameEdgeAssignment, ...]] | None:
    if (
        consensus.outcome != AssignmentConsensusOutcome.EXTERNAL_SAFETY_ENVELOPE
        or not slots
    ):
        return slots, assignments
    updated = list(slots)
    replaced: set[tuple[int, BoundarySide]] = set()
    for offset, side in (
        (0, BoundarySide.LEADING),
        (len(slots) - 1, BoundarySide.TRAILING),
    ):
        slot = updated[offset]
        if slot.sequence_inferred or slot.edge_occlusion is not None:
            continue
        boundaries = tuple(
            (
                build.slots[offset].leading
                if side == BoundarySide.LEADING
                else build.slots[offset].trailing
            )
            for build in preferred_builds
        )
        if PixelInterval.common_intersection(
            tuple(boundary.position for boundary in boundaries)
        ) is not None:
            continue
        safe_boundary = _external_safety_boundary(
            side,
            boundaries,
            holder_safety,
        )
        if safe_boundary is None:
            return None
        updated[offset] = replace(
            slot,
            leading=(safe_boundary if side == BoundarySide.LEADING else slot.leading),
            trailing=(safe_boundary if side == BoundarySide.TRAILING else slot.trailing),
            visible_long_axis=PixelInterval(
                (
                    safe_boundary.position.minimum
                    if side == BoundarySide.LEADING
                    else slot.visible_long_axis.minimum
                ),
                (
                    safe_boundary.position.maximum
                    if side == BoundarySide.TRAILING
                    else slot.visible_long_axis.maximum
                ),
            ),
        )
        replaced.add((slot.index, side))
    return (
        tuple(updated),
        tuple(
            assignment
            for assignment in assignments
            if (assignment.frame_index, assignment.side) not in replaced
        ),
    )


def _build_preserves_visible_content(
    build: _SequenceBuild,
    visible_content: ContentRegionObservation,
) -> bool:
    if not build.slots:
        return False
    sequence_interval = (
        max(
            visible_content.region.left,
            int(floor(build.slots[0].leading.position.minimum)),
        ),
        min(
            visible_content.region.right,
            int(ceil(build.slots[-1].trailing.position.maximum)),
        ),
    )
    if sequence_interval[1] <= sequence_interval[0]:
        return False
    return not visible_content.uncovered_by((sequence_interval,))


def _boundary_matches_holder(
    boundary: ResolvedFrameBoundary,
    holder_boundary: HolderBoundaryObservation | None,
) -> bool:
    if holder_boundary is None or boundary.boundary_anchor is None:
        return False
    observation = boundary.boundary_anchor.observation
    if isinstance(observation, SeparatorBandObservation):
        band_span = PixelInterval(
            observation.leading_edge.minimum,
            observation.trailing_edge.maximum,
        )
        photo_facing_edge = (
            observation.trailing_edge
            if holder_boundary.side == BoundarySide.LEADING
            else observation.leading_edge
        )
        return bool(
            boundary.boundary_anchor.physical_role == holder_boundary.side
            and boundary.position == photo_facing_edge
            and band_span.intersects(holder_boundary.position)
        )
    return bool(
        boundary.position.intersects(holder_boundary.position)
        and boundary.measurement_provenance.observation_id
        in {
            path.provenance.observation_id
            for path in holder_boundary.supporting_paths
        }
    )


def _frame_width_physical_scale_constraint(
    photo_height_evidence: PhotoHeightEvidence,
    dimensions: FrameDimensionPrior,
) -> FrameWidthPhysicalScaleConstraint | None:
    if (
        photo_height_evidence.state != EvidenceState.SUPPORTED
        or photo_height_evidence.height_px is None
    ):
        return None
    photo_inputs = {
        photo_height_evidence.provenance.root_measurement,
        *photo_height_evidence.provenance.dependencies,
    }
    if (
        MeasurementIdentity.FRAME_GEOMETRY in photo_inputs
        or not {
            MeasurementIdentity.PHOTO_EDGES,
            MeasurementIdentity.BOUNDARY_PATHS,
        }.intersection(photo_inputs)
    ):
        return None
    dependencies = tuple(
        sorted(
            {
                *photo_inputs,
                dimensions.provenance.root_measurement,
                *dimensions.provenance.dependencies,
            }
            - {
                MeasurementIdentity.FRAME_DIMENSIONS,
                MeasurementIdentity.FRAME_GEOMETRY,
            },
            key=lambda item: item.value,
        )
    )
    return FrameWidthPhysicalScaleConstraint(
        width_px=photo_height_evidence.height_px.scaled(dimensions.aspect),
        provenance=MeasurementProvenance(
            root_measurement=MeasurementIdentity.FRAME_DIMENSIONS,
            observation_id=ObservationId(
                "frame_width_physical_scale:"
                f"{photo_height_evidence.provenance.observation_id}:"
                f"{dimensions.provenance.observation_id}"
            ),
            dependencies=dependencies,
            description="independent photo-height and physical-aspect width constraint",
            boundary_anchors=photo_height_evidence.provenance.boundary_anchors,
        ),
    )


def _constraint_has_internal_anchor(
    constraint: FrameWidthMeasurementConstraint,
    slot_count: int,
) -> bool:
    return bool(
        (
            constraint.frame_index > 1
            and boundary_role_is_independent_physical_measurement(
                constraint.leading
            )
        )
        or (
            constraint.frame_index < slot_count
            and boundary_role_is_independent_physical_measurement(
                constraint.trailing
            )
        )
    )


def _boundary_role_can_contribute_to_width_geometry(
    boundary: ResolvedFrameBoundary,
) -> bool:
    provenance = boundary.role_provenance
    return bool(
        boundary.independently_observed
        and provenance is not None
        and provenance.root_measurement != MeasurementIdentity.FRAME_DIMENSIONS
        and MeasurementIdentity.FRAME_DIMENSIONS not in provenance.dependencies
    )


def _constraint_has_scale_independent_internal_anchor(
    constraint: FrameWidthMeasurementConstraint,
    slot_count: int,
) -> bool:
    return bool(
        (
            constraint.frame_index > 1
            and boundary_role_is_independent_physical_measurement(
                constraint.leading
            )
        )
        or (
            constraint.frame_index < slot_count
            and boundary_role_is_independent_physical_measurement(
                constraint.trailing
            )
        )
    )


def _common_frame_width(
    slots: tuple[FrameSlot, ...],
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
    photo_height_evidence: PhotoHeightEvidence,
    dimensions: FrameDimensionPrior,
) -> CommonFrameWidthResolution:
    all_measured_constraints = tuple(
        FrameWidthMeasurementConstraint(slot.index, slot.leading, slot.trailing)
        for slot in slots
        if not slot.sequence_inferred
        and slot.leading.position_independently_observed
        and slot.trailing.position_independently_observed
        and slot.leading.role_state == EvidenceState.SUPPORTED
        and slot.trailing.role_state == EvidenceState.SUPPORTED
        and not (
            slot.index == 1
            and slot.leading.source == FrameBoundarySource.GRAY_PATH_OBSERVATION
            and _boundary_matches_holder(
                slot.leading,
                holder_boundaries.get(BoundarySide.LEADING),
            )
        )
        and not (
            slot.index == len(slots)
            and slot.trailing.source == FrameBoundarySource.GRAY_PATH_OBSERVATION
            and _boundary_matches_holder(
                slot.trailing,
                holder_boundaries.get(BoundarySide.TRAILING),
            )
        )
        and all(
            boundary.role_provenance is not None
            for boundary in (slot.leading, slot.trailing)
        )
    )
    geometry_constraints = tuple(
        constraint
        for constraint in all_measured_constraints
        if all(
            _boundary_role_can_contribute_to_width_geometry(boundary)
            for boundary in (constraint.leading, constraint.trailing)
        )
    )
    contributor_indexes = _largest_measurement_compatible_interval_indexes(
        tuple(
            constraint.width_px
            for constraint in geometry_constraints
        ),
        MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS,
    )
    measured_constraints = tuple(
        geometry_constraints[index]
        for index in contributor_indexes
    )
    if not measured_constraints and len(geometry_constraints) == 1:
        measured_constraints = geometry_constraints
    scale_constraint = _frame_width_physical_scale_constraint(
        photo_height_evidence,
        dimensions,
    )
    shared: PixelInterval | None = None
    contributors: tuple[FrameWidthMeasurementConstraint, ...] = ()
    used_scale: FrameWidthPhysicalScaleConstraint | None = None
    if len(measured_constraints) >= MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS:
        shared = _interval_envelope(
            tuple(constraint.width_px for constraint in measured_constraints)
        )
        contributors = measured_constraints
    elif (
        len(measured_constraints) == 1
        and scale_constraint is not None
        and _constraint_has_internal_anchor(
            measured_constraints[0],
            len(slots),
        )
    ):
        shared = PixelInterval.common_intersection(
            (
                measured_constraints[0].width_px,
                scale_constraint.width_px,
            )
        )
        if shared is not None:
            contributors = measured_constraints
            used_scale = scale_constraint
    elif scale_constraint is not None:
        scale_corroborated_constraints = tuple(
            constraint
            for constraint in all_measured_constraints
            if constraint.width_px.intersects(scale_constraint.width_px)
            and _constraint_has_scale_independent_internal_anchor(
                constraint,
                len(slots),
            )
        )
        scale_corroborated_width = PixelInterval.common_intersection(
            (
                *(
                    constraint.width_px
                    for constraint in scale_corroborated_constraints
                ),
                scale_constraint.width_px,
            )
        )
        if (
            scale_corroborated_width is not None
            and scale_corroborated_constraints
        ):
            shared = scale_corroborated_width
            contributors = scale_corroborated_constraints
            used_scale = scale_constraint
    anchors = tuple(
        boundary.measurement_provenance.observation_id
        for constraint in contributors
        for boundary in (constraint.leading, constraint.trailing)
    )
    role_inputs = tuple(
        boundary.role_provenance
        for constraint in contributors
        for boundary in (constraint.leading, constraint.trailing)
        if boundary.role_provenance is not None
    )
    provenance_dependencies = {
        dependency
        for constraint in contributors
        for boundary in (constraint.leading, constraint.trailing)
        for input_provenance in (
            boundary.measurement_provenance,
            boundary.role_provenance,
        )
        if input_provenance is not None
        for dependency in (
            input_provenance.root_measurement,
            *input_provenance.dependencies,
        )
        if dependency
        not in {
            MeasurementIdentity.FRAME_DIMENSIONS,
            MeasurementIdentity.FRAME_GEOMETRY,
        }
    }
    if used_scale is not None:
        provenance_dependencies.update(
            dependency
            for dependency in (
                used_scale.provenance.root_measurement,
                *used_scale.provenance.dependencies,
            )
            if dependency
            not in {
                MeasurementIdentity.FRAME_DIMENSIONS,
                MeasurementIdentity.FRAME_GEOMETRY,
            }
        )
    provenance = MeasurementProvenance(
        root_measurement=MeasurementIdentity.FRAME_DIMENSIONS,
        observation_id=ObservationId(
            "common_frame_width:"
            + ":".join(
                map(str, (item.frame_index for item in contributors) or (0,))
            )
        ),
        dependencies=tuple(
            sorted(provenance_dependencies, key=lambda item: item.value)
        ),
        description=(
            "common frame width from independently observed complete slots"
            if used_scale is None
            else "common frame width from one observed slot and independent scale"
        ),
        boundary_anchors=tuple(
            dict.fromkeys(
                (
                    *anchors,
                    *(
                        anchor
                        for provenance in role_inputs
                        for anchor in provenance.boundary_anchors
                    ),
                    *(
                        ()
                        if used_scale is None
                        else used_scale.provenance.boundary_anchors
                    ),
                )
            )
        ),
    )
    return CommonFrameWidthResolution(
        width_px=shared,
        constraints=contributors,
        physical_scale_constraint=used_scale,
        state=(
            EvidenceState.SUPPORTED
            if shared is not None
            else EvidenceState.UNAVAILABLE
        ),
        provenance=provenance,
    )


def _slot_can_contribute_repeated_width_measurement(
    slot: FrameSlot,
    slot_count: int,
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
) -> bool:
    if slot.sequence_inferred or slot.index in {1, slot_count}:
        return False
    if any(
        boundary.source
        not in {
            FrameBoundarySource.GRAY_PATH_OBSERVATION,
            FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION,
        }
        or boundary.boundary_anchor is None
        or not boundary.position_independently_observed
        for boundary in (slot.leading, slot.trailing)
    ):
        return False
    if any(
        boundary.source == FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION
        and not boundary.independently_observed
        for boundary in (slot.leading, slot.trailing)
    ):
        return False
    if (
        slot.index == 1
        and _boundary_matches_holder(
            slot.leading,
            holder_boundaries.get(BoundarySide.LEADING),
        )
    ) or (
        slot.index == slot_count
        and _boundary_matches_holder(
            slot.trailing,
            holder_boundaries.get(BoundarySide.TRAILING),
        )
    ):
        return False
    return slot.width_px.minimum >= MINIMUM_POSITIVE_PIXEL_EXTENT


def _repeated_width_role_provenance(
    slot_index: int,
    side: BoundarySide,
    contributors: tuple[FrameSlot, ...],
) -> MeasurementProvenance:
    measurements = tuple(
        candidate.measurement_provenance
        for slot in contributors
        for candidate in (slot.leading, slot.trailing)
    )
    anchors = tuple(
        dict.fromkeys(
            provenance.observation_id
            for provenance in measurements
        )
    )
    dependencies = tuple(
        sorted(
            {
                MeasurementIdentity.FRAME_WIDTH_PATTERN,
                *(
                    dependency
                    for provenance in measurements
                    for dependency in (
                        provenance.root_measurement,
                        *provenance.dependencies,
                    )
                    if dependency
                    not in {
                        MeasurementIdentity.FRAME_DIMENSIONS,
                        MeasurementIdentity.FRAME_GEOMETRY,
                    }
                ),
            },
            key=lambda item: item.value,
        )
    )
    digest = hashlib.sha256(
        "\x1f".join(map(str, anchors)).encode("utf-8")
    ).hexdigest()
    return MeasurementProvenance(
        root_measurement=MeasurementIdentity.PHOTO_EDGES,
        observation_id=ObservationId(
            f"repeated_frame_width_photo_edge:{slot_index}:{side.value}:{digest}"
        ),
        dependencies=dependencies,
        description=(
            "photo-edge role corroborated by repeated complete frame-width "
            "measurements"
        ),
        boundary_anchors=anchors,
    )


def _corroborate_build_roles_from_repeated_frame_width(
    build: _SequenceBuild,
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
) -> _SequenceBuild:
    candidates = tuple(
        slot
        for slot in build.slots
        if _slot_can_contribute_repeated_width_measurement(
            slot,
            len(build.slots),
            holder_boundaries,
        )
    )
    contributor_indexes = _largest_measurement_compatible_interval_indexes(
        tuple(slot.width_px for slot in candidates),
        MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS,
    )
    if not contributor_indexes:
        return build
    contributors = tuple(candidates[index] for index in contributor_indexes)
    contributor_slot_indexes = {slot.index for slot in contributors}
    slots: list[FrameSlot] = []
    for slot in build.slots:
        if slot.index not in contributor_slot_indexes:
            slots.append(slot)
            continue
        boundaries: dict[BoundarySide, ResolvedFrameBoundary] = {}
        for side, boundary in (
            (BoundarySide.LEADING, slot.leading),
            (BoundarySide.TRAILING, slot.trailing),
        ):
            if boundary.boundary_anchor is None:
                raise ValueError("repeated frame-width role requires raw boundaries")
            if boundary.independently_observed:
                boundaries[side] = boundary
                continue
            boundaries[side] = replace(
                boundary,
                boundary_anchor=replace(
                    boundary.boundary_anchor,
                    role_state=EvidenceState.SUPPORTED,
                    role_authority=BoundaryRoleAuthority.MEASUREMENT_CORROBORATED,
                    role_provenance=_repeated_width_role_provenance(
                        slot.index,
                        side,
                        contributors,
                    ),
                ),
            )
        slots.append(
            replace(
                slot,
                leading=boundaries[BoundarySide.LEADING],
                trailing=boundaries[BoundarySide.TRAILING],
            )
        )
    return _rebuild_sequence_build(build, tuple(slots))


def _physical_scale_corroborated_role_provenance(
    boundary: ResolvedFrameBoundary,
    opposite: ResolvedFrameBoundary,
    side: BoundarySide,
    scale_constraint: FrameWidthPhysicalScaleConstraint,
) -> MeasurementProvenance:
    opposite_role = opposite.role_provenance
    assert opposite_role is not None
    measurement = boundary.measurement_provenance
    dependencies = tuple(
        sorted(
            {
                measurement.root_measurement,
                *measurement.dependencies,
                opposite.measurement_provenance.root_measurement,
                *opposite.measurement_provenance.dependencies,
                opposite_role.root_measurement,
                *opposite_role.dependencies,
                scale_constraint.provenance.root_measurement,
                *scale_constraint.provenance.dependencies,
            }
            - {MeasurementIdentity.FRAME_GEOMETRY},
            key=lambda item: item.value,
        )
    )
    return MeasurementProvenance(
        root_measurement=MeasurementIdentity.PHOTO_EDGES,
        observation_id=ObservationId(
            "physical_scale_corroborated_photo_edge:"
            f"{side.value}:{measurement.observation_id}:"
            f"{opposite.measurement_provenance.observation_id}:"
            f"{scale_constraint.provenance.observation_id}"
        ),
        dependencies=dependencies,
        description=(
            "measured gray boundary corroborated as a photo edge by an "
            "independent internal anchor and physical frame scale"
        ),
        boundary_anchors=tuple(
            dict.fromkeys(
                (
                    measurement.observation_id,
                    opposite.measurement_provenance.observation_id,
                    *opposite_role.boundary_anchors,
                    *scale_constraint.provenance.boundary_anchors,
                )
            )
        ),
    )


def _corroborate_boundary_role_from_physical_scale(
    boundary: ResolvedFrameBoundary,
    opposite: ResolvedFrameBoundary,
    side: BoundarySide,
    scale_constraint: FrameWidthPhysicalScaleConstraint | None,
    *,
    opposite_is_internal: bool,
) -> ResolvedFrameBoundary:
    opposite_role = opposite.role_provenance
    if (
        scale_constraint is None
        or not opposite_is_internal
        or boundary.source
        not in {
            FrameBoundarySource.GRAY_PATH_OBSERVATION,
            FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION,
        }
        or boundary.boundary_anchor is None
        or boundary.role_state == EvidenceState.SUPPORTED
        or not boundary_role_is_independent_physical_measurement(opposite)
        or opposite_role is None
    ):
        return boundary
    expected = (
        opposite.position.minus(scale_constraint.width_px)
        if side == BoundarySide.LEADING
        else opposite.position.plus(scale_constraint.width_px)
    )
    if not boundary.position.intersects(expected):
        return boundary
    return replace(
        boundary,
        boundary_anchor=replace(
            boundary.boundary_anchor,
            role_state=EvidenceState.SUPPORTED,
            role_authority=BoundaryRoleAuthority.GEOMETRY_CORROBORATED,
            role_provenance=_physical_scale_corroborated_role_provenance(
                boundary,
                opposite,
                side,
                scale_constraint,
            ),
        ),
    )


def _corroborate_build_roles_from_physical_scale(
    build: _SequenceBuild,
    scale_constraint: FrameWidthPhysicalScaleConstraint | None,
) -> _SequenceBuild:
    original = build.slots
    count = len(original)
    slots = tuple(
        replace(
            slot,
            leading=_corroborate_boundary_role_from_physical_scale(
                slot.leading,
                slot.trailing,
                BoundarySide.LEADING,
                scale_constraint,
                opposite_is_internal=slot.index < count,
            ),
            trailing=_corroborate_boundary_role_from_physical_scale(
                slot.trailing,
                slot.leading,
                BoundarySide.TRAILING,
                scale_constraint,
                opposite_is_internal=slot.index > 1,
            ),
        )
        for slot in original
    )
    return build if slots == original else _rebuild_sequence_build(build, slots)


def _dimension_corroborated_role_provenance(
    boundary: ResolvedFrameBoundary,
    opposite: ResolvedFrameBoundary,
    side: BoundarySide,
    common_width: CommonFrameWidthResolution,
) -> MeasurementProvenance:
    measurement = boundary.measurement_provenance
    opposite_role = opposite.role_provenance
    assert opposite_role is not None
    dependencies = tuple(
        sorted(
            {
                measurement.root_measurement,
                common_width.provenance.root_measurement,
                *common_width.provenance.dependencies,
                opposite_role.root_measurement,
                *opposite_role.dependencies,
            }
            - {MeasurementIdentity.FRAME_GEOMETRY},
            key=lambda item: item.value,
        )
    )
    return MeasurementProvenance(
        root_measurement=MeasurementIdentity.PHOTO_EDGES,
        observation_id=ObservationId(
            "dimension_corroborated_photo_edge:"
            f"{side.value}:{measurement.observation_id}:"
            f"{common_width.provenance.observation_id}"
        ),
        dependencies=dependencies,
        description=(
            "measured gray boundary corroborated as a photo edge by independent "
            "common frame width"
        ),
        boundary_anchors=tuple(
            dict.fromkeys(
                (
                    measurement.observation_id,
                    opposite.measurement_provenance.observation_id,
                    *common_width.provenance.boundary_anchors,
                )
            )
        ),
    )


def _corroborate_boundary_role_from_common_width(
    boundary: ResolvedFrameBoundary,
    opposite: ResolvedFrameBoundary,
    side: BoundarySide,
    common_width: CommonFrameWidthResolution,
) -> ResolvedFrameBoundary:
    if (
        boundary.source
        not in {
            FrameBoundarySource.GRAY_PATH_OBSERVATION,
            FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION,
        }
        or boundary.boundary_anchor is None
        or boundary.role_state == EvidenceState.SUPPORTED
        or not opposite.independently_observed
        or common_width.state != EvidenceState.SUPPORTED
        or common_width.width_px is None
    ):
        return boundary
    expected = (
        opposite.position.minus(common_width.width_px)
        if side == BoundarySide.LEADING
        else opposite.position.plus(common_width.width_px)
    )
    if not boundary.position.intersects(expected):
        return boundary
    return replace(
        boundary,
        boundary_anchor=replace(
            boundary.boundary_anchor,
            role_state=EvidenceState.SUPPORTED,
            role_authority=BoundaryRoleAuthority.GEOMETRY_CORROBORATED,
            role_provenance=_dimension_corroborated_role_provenance(
                boundary,
                opposite,
                side,
                common_width,
            ),
        ),
    )


def _adjacent_boundary_role_provenance(
    supported: ResolvedFrameBoundary,
    target: ResolvedFrameBoundary,
) -> MeasurementProvenance:
    supported_role = supported.role_provenance
    assert supported_role is not None
    target_measurement = target.measurement_provenance
    supported_measurement = supported.measurement_provenance
    dependencies = tuple(
        sorted(
            {
                target_measurement.root_measurement,
                *target_measurement.dependencies,
                supported_measurement.root_measurement,
                *supported_measurement.dependencies,
                supported_role.root_measurement,
                *supported_role.dependencies,
            }
            - {
                MeasurementIdentity.FRAME_DIMENSIONS,
                MeasurementIdentity.FRAME_GEOMETRY,
            },
            key=lambda item: item.value,
        )
    )
    anchors = tuple(
        dict.fromkeys(
            (
                target_measurement.observation_id,
                supported_measurement.observation_id,
                *supported_role.boundary_anchors,
            )
        )
    )
    digest = hashlib.sha256(
        "\x1f".join(map(str, anchors)).encode("utf-8")
    ).hexdigest()
    return MeasurementProvenance(
        root_measurement=MeasurementIdentity.PHOTO_EDGES,
        observation_id=ObservationId(
            f"adjacent_frame_edge_role:{digest}"
        ),
        dependencies=dependencies,
        description=(
            "photo-edge role corroborated by an independent coincident "
            "adjacent-frame measurement"
        ),
        boundary_anchors=anchors,
    )


def _corroborate_adjacent_boundary(
    target: ResolvedFrameBoundary,
    supported: ResolvedFrameBoundary,
) -> ResolvedFrameBoundary:
    supported_role = supported.role_provenance
    if (
        target.boundary_anchor is None
        or target.role_state == EvidenceState.SUPPORTED
        or not supported.independently_observed
        or supported_role is None
        or supported_role.root_measurement
        in {
            MeasurementIdentity.FRAME_DIMENSIONS,
            MeasurementIdentity.FRAME_GEOMETRY,
        }
        or any(
            dependency
            in {
                MeasurementIdentity.FRAME_DIMENSIONS,
                MeasurementIdentity.FRAME_GEOMETRY,
            }
            for dependency in supported_role.dependencies
        )
        or target.measurement_provenance.root_measurement
        == supported.measurement_provenance.root_measurement
        or target.measurement_provenance.observation_id
        == supported.measurement_provenance.observation_id
        or not target.position.intersects(supported.position)
    ):
        return target
    return replace(
        target,
        boundary_anchor=replace(
            target.boundary_anchor,
            role_state=EvidenceState.SUPPORTED,
            role_authority=BoundaryRoleAuthority.MEASUREMENT_CORROBORATED,
            role_provenance=_adjacent_boundary_role_provenance(
                supported,
                target,
            ),
        ),
    )


def _corroborate_adjacent_boundary_pair(
    trailing: ResolvedFrameBoundary,
    leading: ResolvedFrameBoundary,
) -> tuple[ResolvedFrameBoundary, ResolvedFrameBoundary]:
    return (
        _corroborate_adjacent_boundary(trailing, leading),
        _corroborate_adjacent_boundary(leading, trailing),
    )


def _separator_bindings_for_resolved_slots(
    bindings: tuple[_SeparatorBandBinding, ...],
    slots: tuple[FrameSlot, ...],
) -> tuple[_SeparatorBandBinding, ...]:
    resolved: list[_SeparatorBandBinding] = []
    for binding in bindings:
        trailing = slots[binding.boundary_index - 1].trailing
        leading = slots[binding.boundary_index].leading
        if (
            trailing.source != FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION
            or leading.source != FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION
            or trailing.measurement_provenance != binding.observation.provenance
            or leading.measurement_provenance != binding.observation.provenance
        ):
            continue
        resolved.append(
            replace(
                binding,
                preceding_trailing_edge=trailing,
                following_leading_edge=leading,
            )
        )
    return tuple(resolved)


def _rebuild_sequence_build(
    build: _SequenceBuild,
    slots: tuple[FrameSlot, ...],
) -> _SequenceBuild:
    long_axis_assignments = _long_axis_assignments_for_slots(
        build.long_axis_assignments,
        slots,
    )
    separator_bindings = _separator_bindings_for_resolved_slots(
        build.separator_bindings,
        slots,
    )
    spacings = tuple(
        _spacing_from_frame_edges(index, left.trailing, right.leading)
        for index, (left, right) in enumerate(zip(slots, slots[1:]), start=1)
    )
    return replace(
        build,
        slots=slots,
        long_axis_assignments=long_axis_assignments,
        separator_bindings=separator_bindings,
        spacings=spacings,
        objectives=replace(
            build.objectives,
            uncorroborated_overlap_extent_px=_uncorroborated_overlap_extent(spacings),
            unexplained_spacing_extent_px=_unexplained_spacing_extent(spacings),
            supported_separator_count=len(separator_bindings),
            internal_boundary_measurement_quality=float(
                sum(
                    boundary.independently_observed
                    for left, right in zip(slots, slots[1:])
                    for boundary in (left.trailing, right.leading)
                )
            ),
            external_boundary_measurement_quality=float(
                slots[0].leading.independently_observed
                + slots[-1].trailing.independently_observed
            ),
            inferred_boundary_count=_inferred_boundary_count(slots),
        ),
    )


def _separator_observation_assignment(
    build: _SequenceBuild,
    boundary_index: int,
    support: SeparatorBandCrossAxisSupport,
    common_width: CommonFrameWidthResolution,
) -> tuple[tuple[FrameSlot, ...], _SeparatorBandBinding] | None:
    if (
        common_width.state != EvidenceState.SUPPORTED
        or common_width.width_px is None
        or not support.measurement.complete_separator_supported
        or support.observation.width_px.maximum >= common_width.width_px.minimum
        or not 1 <= boundary_index < len(build.slots)
    ):
        return None
    left = build.slots[boundary_index - 1]
    right = build.slots[boundary_index]
    if left.sequence_inferred or right.sequence_inferred:
        return None
    replaceable_sources = {
        FrameBoundarySource.DIMENSION_CONSTRAINED,
        FrameBoundarySource.GRAY_PATH_OBSERVATION,
    }
    if (
        left.trailing.source not in replaceable_sources
        or right.leading.source not in replaceable_sources
        or (
            left.trailing.role_state == EvidenceState.SUPPORTED
            and boundary_role_is_independent_physical_measurement(left.trailing)
        )
        or (
            right.leading.role_state == EvidenceState.SUPPORTED
            and boundary_role_is_independent_physical_measurement(right.leading)
        )
    ):
        return None
    observed_trailing, observed_leading = tuple(
        _separator_edge_with_supported_role(edge)
        for edge in _observed_band_edges(support)
    )
    trailing, _ = _resolution(
        left.index,
        BoundarySide.TRAILING,
        observed_trailing,
    )
    leading, _ = _resolution(
        right.index,
        BoundarySide.LEADING,
        observed_leading,
    )
    left_width = trailing.position.minus(left.leading.position)
    right_width = right.trailing.position.minus(leading.position)
    if (
        _positive_interval(left_width) is None
        or _positive_interval(right_width) is None
        or not _measurement_intervals_are_compatible(
            left_width,
            common_width.width_px,
        )
        or not _measurement_intervals_are_compatible(
            right_width,
            common_width.width_px,
        )
    ):
        return None
    slots = list(build.slots)
    slots[boundary_index - 1] = replace(
        left,
        trailing=trailing,
        visible_long_axis=PixelInterval(
            left.leading.position.minimum,
            trailing.position.maximum,
        ),
    )
    slots[boundary_index] = replace(
        right,
        leading=leading,
        visible_long_axis=PixelInterval(
            leading.position.minimum,
            right.trailing.position.maximum,
        ),
    )
    resolved_slots = tuple(slots)
    if not _frame_slots_are_strictly_monotonic(resolved_slots):
        return None
    return (
        resolved_slots,
        _SeparatorBandBinding(
            boundary_index=boundary_index,
            observation=support.observation,
            cross_axis_measurement=support.measurement,
            preceding_trailing_edge=trailing,
            following_leading_edge=leading,
        ),
    )


def _assign_unique_separator_observations(
    build: _SequenceBuild,
    common_width: CommonFrameWidthResolution,
    supports: tuple[SeparatorBandCrossAxisSupport, ...],
) -> _SequenceBuild:
    resolved = build
    remaining = tuple(
        support
        for support in supports
        if support.observation.provenance.observation_id
        not in {
            binding.observation.provenance.observation_id
            for binding in build.separator_bindings
        }
    )
    while remaining:
        candidates: dict[
            int,
            list[
                tuple[
                    SeparatorBandCrossAxisSupport,
                    tuple[FrameSlot, ...],
                    _SeparatorBandBinding,
                ]
            ],
        ] = {}
        support_boundaries: dict[ObservationId, list[int]] = {}
        for boundary_index in range(1, len(resolved.slots)):
            if any(
                binding.boundary_index == boundary_index
                for binding in resolved.separator_bindings
            ):
                continue
            for support in remaining:
                assignment = _separator_observation_assignment(
                    resolved,
                    boundary_index,
                    support,
                    common_width,
                )
                if assignment is None:
                    continue
                slots, binding = assignment
                candidates.setdefault(boundary_index, []).append(
                    (support, slots, binding)
                )
                support_boundaries.setdefault(
                    support.observation.provenance.observation_id,
                    [],
                ).append(boundary_index)
        unique = tuple(
            items[0]
            for boundary_index, items in sorted(candidates.items())
            if len(items) == 1
            and len(
                support_boundaries[
                    items[0][0].observation.provenance.observation_id
                ]
            )
            == 1
        )
        if not unique:
            break
        support, slots, binding = unique[0]
        resolved = _rebuild_sequence_build(
            replace(
                resolved,
                separator_bindings=(
                    *resolved.separator_bindings,
                    binding,
                ),
            ),
            slots,
        )
        assigned_id = support.observation.provenance.observation_id
        remaining = tuple(
            item
            for item in remaining
            if item.observation.provenance.observation_id != assigned_id
        )
    return resolved


def _boundary_path_assignment(
    build: _SequenceBuild,
    slot_offset: int,
    side: BoundarySide,
    path: GrayBoundaryPathObservation,
    common_width: CommonFrameWidthResolution,
) -> tuple[tuple[FrameSlot, ...], FrameEdgeAssignment] | None:
    if (
        common_width.state != EvidenceState.SUPPORTED
        or common_width.width_px is None
        or path.axis != BoundaryAxis.LONG
        or not 0 <= slot_offset < len(build.slots)
    ):
        return None
    slot = build.slots[slot_offset]
    if slot.sequence_inferred:
        return None
    boundary = slot.leading if side == BoundarySide.LEADING else slot.trailing
    if boundary.source != FrameBoundarySource.DIMENSION_CONSTRAINED:
        return None
    if not _measurement_intervals_are_compatible(
        boundary.position,
        path.position,
    ):
        return None
    constraint = _EdgeConstraint(
        position=path.position,
        basis=FrameBoundarySource.GRAY_PATH_OBSERVATION,
        state=EvidenceState.UNAVAILABLE,
        geometry_state=BoundaryGeometryState.RESOLVED,
        provenance=path.provenance,
        path=path,
    )
    resolution, assignment = _resolution(slot.index, side, constraint)
    assert assignment is not None
    updated_slot = replace(
        slot,
        leading=(resolution if side == BoundarySide.LEADING else slot.leading),
        trailing=(resolution if side == BoundarySide.TRAILING else slot.trailing),
        visible_long_axis=PixelInterval(
            (
                resolution.position.minimum
                if side == BoundarySide.LEADING
                else slot.leading.position.minimum
            ),
            (
                resolution.position.maximum
                if side == BoundarySide.TRAILING
                else slot.trailing.position.maximum
            ),
        ),
    )
    if (
        not _measurement_intervals_are_compatible(
            updated_slot.width_px,
            common_width.width_px,
        )
        or updated_slot.trailing.position.minimum
        <= updated_slot.leading.position.maximum
    ):
        return None
    slots = list(build.slots)
    slots[slot_offset] = updated_slot
    resolved_slots = tuple(slots)
    if not _frame_slots_are_strictly_monotonic(resolved_slots):
        return None
    return resolved_slots, assignment


def _assign_unique_boundary_path_observations(
    build: _SequenceBuild,
    common_width: CommonFrameWidthResolution,
    paths: tuple[GrayBoundaryPathObservation, ...],
) -> _SequenceBuild:
    resolved = build
    remaining = tuple(
        path
        for path in paths
        if path.provenance.observation_id
        not in {
            assignment.observation.provenance.observation_id
            for assignment in build.long_axis_assignments
        }
    )
    while remaining:
        candidates: dict[
            tuple[int, BoundarySide],
            list[
                tuple[
                    GrayBoundaryPathObservation,
                    tuple[FrameSlot, ...],
                    FrameEdgeAssignment,
                ]
            ],
        ] = {}
        path_boundaries: dict[
            ObservationId,
            list[tuple[int, BoundarySide]],
        ] = {}
        for slot_offset in range(len(resolved.slots)):
            for side in (BoundarySide.LEADING, BoundarySide.TRAILING):
                key = slot_offset, side
                for path in remaining:
                    assignment = _boundary_path_assignment(
                        resolved,
                        slot_offset,
                        side,
                        path,
                        common_width,
                    )
                    if assignment is None:
                        continue
                    slots, edge_assignment = assignment
                    candidates.setdefault(key, []).append(
                        (path, slots, edge_assignment)
                    )
                    path_boundaries.setdefault(
                        path.provenance.observation_id,
                        [],
                    ).append(key)
        unique = tuple(
            items[0]
            for key, items in sorted(
                candidates.items(),
                key=lambda item: (item[0][0], item[0][1].value),
            )
            if len(items) == 1
            and len(
                path_boundaries[items[0][0].provenance.observation_id]
            )
            == 1
        )
        if not unique:
            break
        path, slots, assignment = unique[0]
        resolved = _rebuild_sequence_build(
            replace(
                resolved,
                long_axis_assignments=(
                    *resolved.long_axis_assignments,
                    assignment,
                ),
            ),
            slots,
        )
        assigned_id = path.provenance.observation_id
        remaining = tuple(
            item
            for item in remaining
            if item.provenance.observation_id != assigned_id
        )
    return resolved


def _corroborate_build_adjacent_boundary_roles(
    build: _SequenceBuild,
) -> _SequenceBuild:
    slots = list(build.slots)
    for index in range(len(slots) - 1):
        trailing, leading = _corroborate_adjacent_boundary_pair(
            build.slots[index].trailing,
            build.slots[index + 1].leading,
        )
        slots[index] = replace(slots[index], trailing=trailing)
        slots[index + 1] = replace(slots[index + 1], leading=leading)
    resolved_slots = tuple(slots)
    return (
        build
        if resolved_slots == build.slots
        else _rebuild_sequence_build(build, resolved_slots)
    )


def _corroborate_build_boundary_roles(
    build: _SequenceBuild,
    common_width: CommonFrameWidthResolution,
) -> _SequenceBuild:
    original_slots = build.slots
    slots = tuple(
        replace(
            slot,
            leading=_corroborate_boundary_role_from_common_width(
                slot.leading,
                slot.trailing,
                BoundarySide.LEADING,
                common_width,
            ),
            trailing=_corroborate_boundary_role_from_common_width(
                slot.trailing,
                slot.leading,
                BoundarySide.TRAILING,
                common_width,
            ),
        )
        for slot in original_slots
    )
    return (
        build
        if slots == build.slots
        else _rebuild_sequence_build(build, slots)
    )


def _common_width_dimension_provenance(
    frame_index: int,
    side: BoundarySide,
    anchor: ResolvedFrameBoundary,
    common_width: CommonFrameWidthResolution,
) -> MeasurementProvenance:
    dependencies = tuple(
        sorted(
            {
                anchor.measurement_provenance.root_measurement,
                *anchor.measurement_provenance.dependencies,
                common_width.provenance.root_measurement,
                *common_width.provenance.dependencies,
            },
            key=lambda item: item.value,
        )
    )
    return MeasurementProvenance(
        root_measurement=MeasurementIdentity.FRAME_GEOMETRY,
        observation_id=ObservationId(
            "common_width_dimension_boundary:"
            f"{frame_index}:{side.value}:"
            f"{anchor.measurement_provenance.observation_id}:"
            f"{common_width.provenance.observation_id}"
        ),
        dependencies=dependencies,
        description="frame boundary resolved from a positional anchor and common width",
        boundary_anchors=tuple(
            dict.fromkeys(
                (
                    anchor.measurement_provenance.observation_id,
                    *common_width.provenance.boundary_anchors,
                )
            )
        ),
    )


def _resolved_dimension_boundary(
    frame_index: int,
    side: BoundarySide,
    boundary: ResolvedFrameBoundary,
    anchor: ResolvedFrameBoundary,
    common_width: CommonFrameWidthResolution,
    holder_boundary: HolderBoundaryObservation | None,
) -> ResolvedFrameBoundary:
    unproven_observation_assignment = bool(
        boundary.source
        in {
            FrameBoundarySource.GRAY_PATH_OBSERVATION,
            FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION,
        }
        and boundary.role_state == EvidenceState.UNAVAILABLE
    )
    dimension_candidate = bool(
        boundary.source == FrameBoundarySource.DIMENSION_CONSTRAINED
        or unproven_observation_assignment
    )
    if (
        not dimension_candidate
        or common_width.state != EvidenceState.SUPPORTED
        or common_width.width_px is None
        or not anchor.geometry_resolved
    ):
        return boundary
    if unproven_observation_assignment and _boundary_matches_holder(
        boundary,
        holder_boundary,
    ):
        return boundary
    expected = (
        anchor.position.minus(common_width.width_px)
        if side == BoundarySide.LEADING
        else anchor.position.plus(common_width.width_px)
    )
    if (
        unproven_observation_assignment
        and boundary.position.intersects(expected)
    ):
        return boundary
    resolved_position = boundary.position.intersection(expected)
    if resolved_position is None and unproven_observation_assignment:
        resolved_position = expected
    if resolved_position is None:
        return boundary
    return ResolvedFrameBoundary(
        position=resolved_position,
        source=FrameBoundarySource.DIMENSION_CONSTRAINED,
        geometry_state=BoundaryGeometryState.RESOLVED,
        boundary_anchor=None,
        inference_provenance=_common_width_dimension_provenance(
            frame_index,
            side,
            anchor,
            common_width,
        ),
    )


def _resolve_dimension_boundaries_from_common_width(
    slots: tuple[FrameSlot, ...],
    common_width: CommonFrameWidthResolution,
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
) -> tuple[FrameSlot, ...]:
    resolved: list[FrameSlot] = []
    for slot in slots:
        leading = _resolved_dimension_boundary(
            slot.index,
            BoundarySide.LEADING,
            slot.leading,
            slot.trailing,
            common_width,
            (
                holder_boundaries.get(BoundarySide.LEADING)
                if slot.index == 1
                else None
            ),
        )
        trailing = _resolved_dimension_boundary(
            slot.index,
            BoundarySide.TRAILING,
            slot.trailing,
            slot.leading,
            common_width,
            (
                holder_boundaries.get(BoundarySide.TRAILING)
                if slot.index == len(slots)
                else None
            ),
        )
        if trailing.position.minimum <= leading.position.maximum:
            resolved.append(slot)
            continue
        resolved.append(
            replace(
                slot,
                leading=leading,
                trailing=trailing,
                visible_long_axis=PixelInterval(
                    leading.position.minimum,
                    trailing.position.maximum,
                ),
            )
        )
    candidate = tuple(resolved)
    return candidate if _frame_slots_are_strictly_monotonic(candidate) else slots


def _frame_slots_are_strictly_monotonic(
    slots: tuple[FrameSlot, ...],
) -> bool:
    return bool(
        slots
        and all(
            right.leading.position.minimum > left.leading.position.maximum
            and right.trailing.position.minimum > left.trailing.position.maximum
            for left, right in zip(slots, slots[1:])
        )
    )


def _long_axis_assignments_for_slots(
    assignments: tuple[FrameEdgeAssignment, ...],
    slots: tuple[FrameSlot, ...],
) -> tuple[FrameEdgeAssignment, ...]:
    boundaries = {
        (slot.index, side): boundary
        for slot in slots
        for side, boundary in (
            (BoundarySide.LEADING, slot.leading),
            (BoundarySide.TRAILING, slot.trailing),
        )
    }
    retained: list[FrameEdgeAssignment] = []
    for assignment in assignments:
        boundary = boundaries[(assignment.frame_index, assignment.side)]
        if (
            boundary.source != FrameBoundarySource.GRAY_PATH_OBSERVATION
            or boundary.boundary_anchor is None
            or boundary.boundary_anchor.observation != assignment.observation
        ):
            continue
        retained.append(replace(assignment, resolution=boundary))
    return tuple(retained)


def _resolve_build_dimension_boundaries(
    build: _SequenceBuild,
    common_width: CommonFrameWidthResolution,
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
) -> _SequenceBuild:
    slots = _resolve_dimension_boundaries_from_common_width(
        build.slots,
        common_width,
        holder_boundaries,
    )
    if slots == build.slots:
        return build
    return _rebuild_sequence_build(build, slots)


def _resolve_build_physical_boundaries(
    build: _SequenceBuild,
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
    photo_height_evidence: PhotoHeightEvidence,
    dimensions: FrameDimensionPrior,
) -> tuple[_SequenceBuild, CommonFrameWidthResolution]:
    resolved = _corroborate_build_roles_from_repeated_frame_width(
        build,
        holder_boundaries,
    )
    resolved = _corroborate_build_adjacent_boundary_roles(resolved)
    resolved = _corroborate_build_roles_from_physical_scale(
        resolved,
        _frame_width_physical_scale_constraint(
            photo_height_evidence,
            dimensions,
        ),
    )
    common_width = _common_frame_width(
        resolved.slots,
        holder_boundaries,
        photo_height_evidence,
        dimensions,
    )
    resolved = _corroborate_build_boundary_roles(resolved, common_width)
    common_width = _common_frame_width(
        resolved.slots,
        holder_boundaries,
        photo_height_evidence,
        dimensions,
    )
    resolved = _resolve_build_dimension_boundaries(
        resolved,
        common_width,
        holder_boundaries,
    )
    return resolved, common_width


def _separator_assignments_from_bindings(
    bindings: tuple[_SeparatorBandBinding, ...],
    slots: tuple[FrameSlot, ...],
    common_width: CommonFrameWidthResolution,
) -> tuple[SeparatorBandAssignment, ...]:
    if common_width.state != EvidenceState.SUPPORTED:
        return ()
    assert common_width.width_px is not None
    assignments: list[SeparatorBandAssignment] = []
    for binding in bindings:
        if binding.observation.width_px.maximum >= common_width.width_px.minimum:
            continue
        trailing = slots[binding.boundary_index - 1].trailing
        leading = slots[binding.boundary_index].leading
        if (
            trailing.position != binding.observation.leading_edge
            or leading.position != binding.observation.trailing_edge
        ):
            continue
        assignments.append(
            SeparatorBandAssignment(
                boundary_index=binding.boundary_index,
                observation=binding.observation,
                cross_axis_measurement=binding.cross_axis_measurement,
                frame_width_px=common_width.width_px,
                preceding_trailing_edge=trailing,
                following_leading_edge=leading,
            )
        )
    return tuple(
        sorted(assignments, key=lambda assignment: assignment.boundary_index)
    )


def _final_inter_frame_spacings(
    slots: tuple[FrameSlot, ...],
    assignments: tuple[SeparatorBandAssignment, ...],
    common_width: CommonFrameWidthResolution,
) -> tuple[InterFrameSpacing, ...]:
    assigned_boundaries = {item.boundary_index for item in assignments}
    return tuple(
        _corroborate_overlap_from_independent_sequence_constraints(
            _spacing_from_frame_edges(
                boundary_index,
                left.trailing,
                right.leading,
                separator_observation_supported=(
                    boundary_index in assigned_boundaries
                ),
            ),
            left,
            right,
            common_width,
        )
        for boundary_index, (left, right) in enumerate(
            zip(slots, slots[1:]),
            start=1,
        )
    )


def _target_independent_common_width(
    common_width: CommonFrameWidthResolution,
    left_frame_index: int,
    right_frame_index: int,
) -> tuple[PixelInterval, tuple[FrameWidthMeasurementConstraint, ...]] | None:
    if common_width.state != EvidenceState.SUPPORTED:
        return None
    eligible = tuple(
        constraint
        for constraint in common_width.constraints
        if constraint.frame_index not in {left_frame_index, right_frame_index}
        and all(
            boundary_role_is_independent_physical_measurement(boundary)
            for boundary in (constraint.leading, constraint.trailing)
        )
    )
    contributor_indexes = _largest_measurement_compatible_interval_indexes(
        tuple(constraint.width_px for constraint in eligible),
        MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS,
    )
    if not contributor_indexes:
        return None
    contributors = tuple(eligible[index] for index in contributor_indexes)
    return (
        _interval_envelope(
            tuple(constraint.width_px for constraint in contributors)
        ),
        contributors,
    )


def _inferred_overlap_geometry(
    left: FrameSlot,
    right: FrameSlot,
    frame_width: PixelInterval,
) -> tuple[
    ResolvedFrameBoundary,
    ResolvedFrameBoundary,
    PixelInterval,
] | None:
    if (
        left.trailing.source == FrameBoundarySource.DIMENSION_CONSTRAINED
        and boundary_role_is_independent_physical_measurement(left.leading)
        and boundary_role_is_independent_physical_measurement(right.leading)
    ):
        expected = left.leading.position.plus(frame_width)
        if (
            expected.minimum <= left.trailing.position.minimum
            and left.trailing.position.maximum <= expected.maximum
        ):
            return (
                left.leading,
                right.leading,
                right.leading.position.minus(expected),
            )
    if (
        right.leading.source == FrameBoundarySource.DIMENSION_CONSTRAINED
        and boundary_role_is_independent_physical_measurement(right.trailing)
        and boundary_role_is_independent_physical_measurement(left.trailing)
    ):
        expected = right.trailing.position.minus(frame_width)
        if (
            expected.minimum <= right.leading.position.minimum
            and right.leading.position.maximum <= expected.maximum
        ):
            return (
                right.trailing,
                left.trailing,
                expected.minus(left.trailing.position),
            )
    return None


def _corroborate_overlap_from_independent_sequence_constraints(
    spacing: InterFrameSpacing,
    left: FrameSlot,
    right: FrameSlot,
    common_width: CommonFrameWidthResolution,
) -> InterFrameSpacing:
    if (
        spacing.basis != InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS
        or spacing.kind != InterFrameSpacingKind.OVERLAP
    ):
        return spacing
    independent_width = _target_independent_common_width(
        common_width,
        left.index,
        right.index,
    )
    if independent_width is None:
        return spacing
    width_px, contributors = independent_width
    geometry = _inferred_overlap_geometry(left, right, width_px)
    if geometry is None:
        return spacing
    positional_anchor, measured_overlap_edge, forced_spacing = geometry
    if forced_spacing.maximum >= 0.0:
        return spacing
    inputs = tuple(
        boundary
        for constraint in contributors
        for boundary in (constraint.leading, constraint.trailing)
    )
    dependencies = tuple(
        sorted(
            {
                provenance.root_measurement
                for boundary in (
                    positional_anchor,
                    measured_overlap_edge,
                    *inputs,
                )
                for provenance in (
                    boundary.measurement_provenance,
                    boundary.role_provenance,
                )
                if provenance is not None
                and provenance.root_measurement
                not in {
                    MeasurementIdentity.FRAME_GEOMETRY,
                    MeasurementIdentity.FRAME_WIDTH_PATTERN,
                }
            },
            key=lambda item: item.value,
        )
    )
    boundary_anchors = tuple(
        dict.fromkeys(
            boundary.measurement_provenance.observation_id
            for boundary in (
                positional_anchor,
                measured_overlap_edge,
                *inputs,
            )
        )
    )
    return InterFrameSpacing(
        boundary=spacing.boundary,
        signed_width_px=spacing.signed_width_px,
        provenance=MeasurementProvenance(
            root_measurement=MeasurementIdentity.FRAME_DIMENSIONS,
            observation_id=ObservationId(
                "sequence_corroborated_overlap:"
                f"{spacing.boundary.boundary_index}:"
                + ":".join(str(item.frame_index) for item in contributors)
            ),
            dependencies=dependencies,
            description=(
                "target-independent frame-width measurements require overlap"
            ),
            boundary_anchors=boundary_anchors,
        ),
        basis=InterFrameSpacingBasis.CORROBORATED_OVERLAP,
    )


def _occlusion_provenance(
    side: BoundarySide,
    holder_boundary: HolderBoundaryObservation,
    common_width: CommonFrameWidthResolution,
) -> MeasurementProvenance:
    return MeasurementProvenance(
        root_measurement=MeasurementIdentity.FRAME_GEOMETRY,
        observation_id=ObservationId(f"holder_occlusion_inference:{side.value}"),
        dependencies=(
            MeasurementIdentity.BOUNDARY_PATHS,
            MeasurementIdentity.FRAME_DIMENSIONS,
        ),
        description="frame endpoint inferred from holder contact and common frame width",
        boundary_anchors=tuple(
            dict.fromkeys(
                (
                    holder_boundary.provenance.observation_id,
                    *common_width.provenance.boundary_anchors,
                )
            )
        ),
    )


def _apply_edge_occlusion_inference(
    slots: tuple[FrameSlot, ...],
    assignments: tuple[FrameEdgeAssignment, ...],
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
    common_width: CommonFrameWidthResolution,
    strip_mode: str,
) -> tuple[tuple[FrameSlot, ...], tuple[FrameEdgeAssignment, ...]]:
    if strip_mode != FULL or common_width.state != EvidenceState.SUPPORTED:
        return slots, assignments
    assert common_width.width_px is not None
    updated = list(slots)
    removed: set[tuple[int, BoundarySide]] = set()
    for index, side in ((0, BoundarySide.LEADING), (len(slots) - 1, BoundarySide.TRAILING)):
        slot = updated[index]
        if slot.sequence_inferred:
            continue
        visible_boundary = slot.leading if side == BoundarySide.LEADING else slot.trailing
        opposite_boundary = (
            slot.trailing if side == BoundarySide.LEADING else slot.leading
        )
        holder_boundary = holder_boundaries.get(side)
        if not _boundary_matches_holder(visible_boundary, holder_boundary):
            continue
        if not opposite_boundary.independently_observed:
            continue
        if slot.width_px.maximum >= common_width.width_px.minimum:
            continue
        assert holder_boundary is not None
        inferred = (
            slot.trailing.position.minus(common_width.width_px)
            if side == BoundarySide.LEADING
            else slot.leading.position.plus(common_width.width_px)
        )
        if side == BoundarySide.LEADING:
            if inferred.maximum >= visible_boundary.position.minimum:
                continue
            hidden_width = visible_boundary.position.minus(inferred)
        else:
            if inferred.minimum <= visible_boundary.position.maximum:
                continue
            hidden_width = inferred.minus(visible_boundary.position)
        provenance = _occlusion_provenance(side, holder_boundary, common_width)
        inferred_boundary = ResolvedFrameBoundary(
            position=inferred,
            source=FrameBoundarySource.HOLDER_OCCLUSION_INFERENCE,
            geometry_state=BoundaryGeometryState.RESOLVED,
            boundary_anchor=None,
            inference_provenance=provenance,
        )
        updated[index] = replace(
            slot,
            leading=(inferred_boundary if side == BoundarySide.LEADING else slot.leading),
            trailing=(inferred_boundary if side == BoundarySide.TRAILING else slot.trailing),
            edge_occlusion=FrameEdgeOcclusionInference(
                side=side,
                hidden_width_px=hidden_width,
                holder_boundary_provenance=holder_boundary.provenance,
            ),
        )
        removed.add((slot.index, side))
    return (
        tuple(updated),
        tuple(
            assignment
            for assignment in assignments
            if (assignment.frame_index, assignment.side) not in removed
        ),
    )


def _slot_has_observed_content(
    slot: FrameSlot,
    visible_content: ContentRegionObservation,
) -> bool:
    return visible_content.reliable_content_intersects(slot.visible_long_axis)


def _annotate_frame_content_occupancy(
    slots: tuple[FrameSlot, ...],
    visible_content: ContentRegionObservation,
) -> tuple[FrameSlot, ...]:
    return tuple(
        replace(
            slot,
            content_occupancy=(
                FrameContentOccupancy.CONTENT_OBSERVED
                if _slot_has_observed_content(slot, visible_content)
                else FrameContentOccupancy.UNAVAILABLE
            ),
        )
        for slot in slots
    )


def _shifted_frame_index(frame_index: int, insertion_index: int) -> int:
    return frame_index + 1 if frame_index >= insertion_index else frame_index


def _shifted_separator_boundary_index(
    boundary_index: int,
    insertion_index: int,
) -> int | None:
    broken_boundary = insertion_index - 1
    if 1 < insertion_index and boundary_index == broken_boundary:
        return None
    return boundary_index + 1 if boundary_index >= insertion_index else boundary_index


def _build_with_inserted_slot(
    build: _SequenceBuild,
    inserted_slot: FrameSlot,
    holder: Box,
) -> _SequenceBuild:
    insertion_index = inserted_slot.index
    inserted_slot_count = 1
    slots = tuple(
        (
            inserted_slot
            if frame_index == insertion_index
            else replace(
                build.slots[
                    frame_index
                    - 1
                    - (
                        inserted_slot_count
                        if frame_index > insertion_index
                        else 0
                    )
                ],
                index=frame_index,
            )
        )
        for frame_index in range(
            1,
            len(build.slots) + inserted_slot_count + 1,
        )
    )
    long_axis_assignments = tuple(
        replace(
            assignment,
            frame_index=_shifted_frame_index(
                assignment.frame_index,
                insertion_index,
            ),
        )
        for assignment in build.long_axis_assignments
    )
    separator_bindings = tuple(
        replace(assignment, boundary_index=shifted)
        for assignment in build.separator_bindings
        if (
            shifted := _shifted_separator_boundary_index(
                assignment.boundary_index,
                insertion_index,
            )
        )
        is not None
    )
    spacings = tuple(
        _spacing_from_frame_edges(
            boundary_index,
            left.trailing,
            right.leading,
        )
        for boundary_index, (left, right) in enumerate(
            zip(slots, slots[1:]),
            start=1,
        )
    )
    added_uncertainty = (
        inserted_slot.leading.position.maximum
        - inserted_slot.leading.position.minimum
        + inserted_slot.trailing.position.maximum
        - inserted_slot.trailing.position.minimum
    ) / max(
        MINIMUM_POSITIVE_PIXEL_EXTENT,
        float(holder.width + holder.height),
    )
    residuals = replace(
        build.residuals,
        boundary_uncertainty=(
            build.residuals.boundary_uncertainty + added_uncertainty
        ),
    )
    return _SequenceBuild(
        slots=slots,
        long_axis_assignments=long_axis_assignments,
        separator_bindings=separator_bindings,
        spacings=spacings,
        frame_width_px=build.frame_width_px,
        short_axis=build.short_axis,
        residuals=residuals,
        objectives=replace(
            build.objectives,
            uncorroborated_overlap_extent_px=_uncorroborated_overlap_extent(
                spacings
            ),
            unexplained_spacing_extent_px=_unexplained_spacing_extent(spacings),
            supported_separator_count=len(separator_bindings),
            boundary_uncertainty_ratio=(
                build.objectives.boundary_uncertainty_ratio + added_uncertainty
            ),
        ),
    )


def _sequence_completed_builds(
    real_frame_builds: tuple[_SequenceBuild, ...],
    search_scope: FrameSequenceSearchScope,
    photo_height_evidence: PhotoHeightEvidence,
    dimensions: FrameDimensionPrior,
) -> tuple[_SequenceBuild, ...]:
    inferred: list[_SequenceBuild] = []
    holder_boundaries = _holder_boundaries(search_scope)
    for build in real_frame_builds:
        build, common_width = _resolve_build_physical_boundaries(
            build,
            holder_boundaries,
            photo_height_evidence,
            dimensions,
        )
        if common_width.state != EvidenceState.SUPPORTED:
            continue
        if not measured_sequence_supports_slot_inference(
            build.slots,
            build.spacings,
            common_width,
        ):
            continue
        sequence_inferred_slot_count = 1
        for insertion_index in range(
            1,
            len(build.slots) + sequence_inferred_slot_count + 1,
        ):
            inferred_slot = infer_sequence_frame_slot(
                build.slots,
                insertion_index=insertion_index,
                common_width=common_width,
                holder_safety=search_scope.holder_safety,
            )
            if inferred_slot is not None:
                inferred.append(
                    _build_with_inserted_slot(
                        build,
                        inferred_slot,
                        search_scope.holder_safety.box,
                    )
                )
    return tuple(inferred)


def _slots_do_not_contradict_supported_common_width(
    slots: tuple[FrameSlot, ...],
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
    common_width: CommonFrameWidthResolution,
) -> bool:
    if common_width.state != EvidenceState.SUPPORTED:
        return False
    assert common_width.width_px is not None
    last_index = len(slots) - 1
    for slot_index, slot in enumerate(slots):
        if slot.width_px.intersects(common_width.width_px):
            continue
        clipped_side = (
            BoundarySide.LEADING
            if slot_index == 0
            else BoundarySide.TRAILING
            if slot_index == last_index
            else None
        )
        if (
            clipped_side is None
            or slot.width_px.maximum >= common_width.width_px.minimum
        ):
            return False
        visible_boundary = (
            slot.leading
            if clipped_side == BoundarySide.LEADING
            else slot.trailing
        )
        if not _boundary_matches_holder(
            visible_boundary,
            holder_boundaries.get(clipped_side),
        ):
            return False
        opposite_boundary = (
            slot.trailing
            if clipped_side == BoundarySide.LEADING
            else slot.leading
        )
        if not opposite_boundary.independently_observed:
            return False
    return True


def _build_supports_resolved_nominal_slots(
    build: _SequenceBuild,
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
    photo_height_evidence: PhotoHeightEvidence,
    dimensions: FrameDimensionPrior,
) -> bool:
    resolved_build, common_width = _resolve_build_physical_boundaries(
        build,
        holder_boundaries,
        photo_height_evidence,
        dimensions,
    )
    resolved_slots = resolved_build.slots
    return bool(
        _frame_slots_are_strictly_monotonic(resolved_slots)
        and resolved_build.objectives.uncorroborated_overlap_extent_px == 0.0
        and all(
            slot.leading.geometry_state == BoundaryGeometryState.RESOLVED
            and slot.trailing.geometry_state == BoundaryGeometryState.RESOLVED
            for slot in resolved_slots
        )
        and _slots_do_not_contradict_supported_common_width(
            resolved_slots,
            holder_boundaries,
            common_width,
        )
        and _full_sequence_endpoint_slack_is_sub_frame(
            resolved_slots,
            holder_boundaries,
            common_width,
        )
    )


def _full_sequence_endpoint_slack_is_sub_frame(
    slots: tuple[FrameSlot, ...],
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
    common_width: CommonFrameWidthResolution,
) -> bool:
    if common_width.state != EvidenceState.SUPPORTED or common_width.width_px is None:
        return False
    return _endpoint_slack_is_sub_frame(
        slots,
        holder_boundaries,
        common_width.width_px,
    )


def _endpoint_slack_is_sub_frame(
    slots: tuple[FrameSlot, ...],
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
    frame_width: PixelInterval,
) -> bool:
    leading_holder = holder_boundaries.get(BoundarySide.LEADING)
    if leading_holder is not None:
        leading_slack = slots[0].leading.position.minus(leading_holder.position)
        if leading_slack.minimum >= frame_width.minimum:
            return False
    trailing_holder = holder_boundaries.get(BoundarySide.TRAILING)
    if trailing_holder is not None:
        trailing_slack = trailing_holder.position.minus(slots[-1].trailing.position)
        if trailing_slack.minimum >= frame_width.minimum:
            return False
    return True


def _build_satisfies_full_endpoint_extent(
    build: _SequenceBuild,
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
    photo_height_evidence: PhotoHeightEvidence,
    dimensions: FrameDimensionPrior,
) -> bool:
    resolved_build, common_width = _resolve_build_physical_boundaries(
        build,
        holder_boundaries,
        photo_height_evidence,
        dimensions,
    )
    frame_width = (
        common_width.width_px
        if common_width.state == EvidenceState.SUPPORTED
        and common_width.width_px is not None
        else PixelInterval.exact(
            max(slot.width_px.maximum for slot in build.slots)
        )
    )
    return _endpoint_slack_is_sub_frame(
        resolved_build.slots,
        holder_boundaries,
        frame_width,
    )


def _build_does_not_contradict_common_width(
    build: _SequenceBuild,
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
    photo_height_evidence: PhotoHeightEvidence,
    dimensions: FrameDimensionPrior,
) -> bool:
    resolved_build, common_width = _resolve_build_physical_boundaries(
        build,
        holder_boundaries,
        photo_height_evidence,
        dimensions,
    )
    resolved_slots = resolved_build.slots
    return bool(
        _frame_slots_are_strictly_monotonic(resolved_slots)
        and (
            common_width.state != EvidenceState.SUPPORTED
            or _slots_do_not_contradict_supported_common_width(
                resolved_slots,
                holder_boundaries,
                common_width,
            )
        )
    )


def _slot_has_non_holder_boundary_observation(
    slot: FrameSlot,
    slot_index: int,
    last_index: int,
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
) -> bool:
    observed_boundary_count = 0
    for side, boundary in (
        (BoundarySide.LEADING, slot.leading),
        (BoundarySide.TRAILING, slot.trailing),
    ):
        if boundary.boundary_anchor is None:
            continue
        external_holder_boundary = (
            slot_index == 0 and side == BoundarySide.LEADING
        ) or (
            slot_index == last_index and side == BoundarySide.TRAILING
        )
        if external_holder_boundary and _boundary_matches_holder(
            boundary,
            holder_boundaries.get(side),
        ):
            continue
        if boundary.independently_observed:
            return True
        observed_boundary_count += 1
    return observed_boundary_count == INTERVAL_ENDPOINT_COUNT


def _unexcluded_sequence_inference_indexes(
    build: _SequenceBuild,
    visible_content: ContentRegionObservation,
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
) -> tuple[int, ...]:
    last_index = len(build.slots) - 1
    unresolved: list[int] = []
    for slot_index, slot in enumerate(build.slots):
        if (
            not slot.sequence_inferred
            and not _slot_has_non_holder_boundary_observation(
                slot,
                slot_index,
                last_index,
                holder_boundaries,
            )
            and not visible_content.reliable_content_intersects(
                slot.visible_long_axis
            )
        ):
            unresolved.append(slot_index)
    return tuple(unresolved)


def _infer_unique_slot_in_direct_nominal_build(
    build: _SequenceBuild,
    visible_content: ContentRegionObservation,
    search_scope: FrameSequenceSearchScope,
    photo_height_evidence: PhotoHeightEvidence,
    dimensions: FrameDimensionPrior,
) -> _SequenceBuild:
    holder_boundaries = _holder_boundaries(search_scope)
    resolved_build, common_width = _resolve_build_physical_boundaries(
        build,
        holder_boundaries,
        photo_height_evidence,
        dimensions,
    )
    inference_indexes = _unexcluded_sequence_inference_indexes(
        resolved_build,
        visible_content,
        holder_boundaries,
    )
    if len(inference_indexes) != 1:
        return build
    slot_index = inference_indexes[0]
    existing_slot = resolved_build.slots[slot_index]
    real_slots = tuple(
        slot
        for index, slot in enumerate(resolved_build.slots)
        if index != slot_index
    )
    inferred_slot = infer_sequence_frame_slot(
        real_slots,
        insertion_index=existing_slot.index,
        common_width=common_width,
        holder_safety=search_scope.holder_safety,
    )
    if (
        inferred_slot is None
        or not inferred_slot.nominal_long_axis.intersects(
            existing_slot.nominal_long_axis
        )
    ):
        return build
    slots = tuple(
        inferred_slot if index == slot_index else slot
        for index, slot in enumerate(resolved_build.slots)
    )
    return _rebuild_sequence_build(resolved_build, slots)


def _direct_nominal_geometry_is_complete(
    builds: tuple[_SequenceBuild, ...],
    visible_content: ContentRegionObservation,
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
    photo_height_evidence: PhotoHeightEvidence,
    dimensions: FrameDimensionPrior,
) -> bool:
    if not builds:
        return False
    preserving = tuple(
        build
        for build in builds
        if _build_preserves_visible_content(build, visible_content)
    )
    return any(
        _build_supports_resolved_nominal_slots(
            build,
            holder_boundaries,
            photo_height_evidence,
            dimensions,
        )
        and not _unexcluded_sequence_inference_indexes(
            build,
            visible_content,
            holder_boundaries,
        )
        for build in preserving or builds
    )


def _preferred_direct_common_width_is_supported(
    builds: tuple[_SequenceBuild, ...],
    visible_content: ContentRegionObservation,
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
    photo_height_evidence: PhotoHeightEvidence,
    dimensions: FrameDimensionPrior,
) -> bool:
    if not builds:
        return False
    preserving = tuple(
        build
        for build in builds
        if _build_preserves_visible_content(build, visible_content)
    )
    preferred = _physically_preferred_builds(preserving or builds)
    return any(
        _common_width_has_independent_measurement_basis(
            _resolve_build_physical_boundaries(
                build,
                holder_boundaries,
                photo_height_evidence,
                dimensions,
            )[1]
        )
        for build in preferred
    )


def _common_width_has_independent_measurement_basis(
    common_width: CommonFrameWidthResolution,
) -> bool:
    if common_width.state != EvidenceState.SUPPORTED:
        return False
    independent_constraints = tuple(
        constraint
        for constraint in common_width.constraints
        if all(
            boundary_role_is_independent_physical_measurement(boundary)
            for boundary in (constraint.leading, constraint.trailing)
        )
    )
    return bool(
        len(independent_constraints)
        >= MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS
        or (
            common_width.physical_scale_constraint is not None
            and independent_constraints
        )
    )


def _build_has_geometry_only_slot(build: _SequenceBuild) -> bool:
    return any(
        not any(
            boundary.independently_observed
            for boundary in (slot.leading, slot.trailing)
        )
        for slot in build.slots
    )


def _sequence_builds_for_count(
    search_index: FrameSequenceSearchIndex,
    search_scope: FrameSequenceSearchScope,
    shared_short_axis: SharedShortAxisSafetySpan,
    photo_height_evidence: PhotoHeightEvidence,
    count: int,
    dimensions: FrameDimensionPrior,
    visible_content: ContentRegionObservation,
    maximum_assignment_evaluations: int,
    *,
    allow_nominal_slot_sized_gap: bool,
) -> tuple[tuple[_SequenceBuild, ...], int, bool]:
    supports = search_index.separator_supports.canonical_supports
    frame_width_hint = frame_width_search_hint(
        shared_short_axis,
        dimensions,
    ).width_px
    holder_width_hint = _holder_span_scale_hint(
        search_scope,
        count,
    ).width_px
    physical_scale_constraint = _frame_width_physical_scale_constraint(
        photo_height_evidence,
        dimensions,
    )
    separator_width_search_hints = _raw_separator_frame_width_search_hints(
        supports,
        search_scope,
        count,
    )
    search_widths = tuple(
        dict.fromkeys(
            (
                *(
                    ()
                    if physical_scale_constraint is None
                    else (physical_scale_constraint.width_px,)
                ),
                *separator_width_search_hints,
                frame_width_hint,
                holder_width_hint,
            )
        )
    )
    band_hypotheses: list[_BandSequenceHypothesis] = []
    band_evaluations = 0
    band_budget_exhausted = False
    for short_axis in (shared_short_axis,) if supports and count > 1 else ():
        remaining_band_budget = maximum_assignment_evaluations - band_evaluations
        if remaining_band_budget <= 0:
            band_budget_exhausted = True
            break
        hypotheses, evaluations, exhausted = _band_sequence_hypotheses(
            supports,
            search_scope,
            count,
            short_axis,
            frame_width_hint,
            remaining_band_budget,
        )
        band_hypotheses.extend(hypotheses)
        band_evaluations += evaluations
        if exhausted:
            band_budget_exhausted = True
            break
    remaining = maximum_assignment_evaluations - band_evaluations
    separator_builds: tuple[_SequenceBuild, ...] = ()
    separator_build_evaluations = 0
    separator_build_budget_exhausted = False
    if band_hypotheses and remaining > 0:
        (
            separator_builds,
            separator_build_evaluations,
            separator_build_budget_exhausted,
        ) = _builds_for_hypotheses(
            tuple(band_hypotheses),
            search_scope,
            _axis_paths(search_scope, BoundaryAxis.LONG),
            supports,
            count,
            remaining,
            physical_scale_constraint,
        )
    if _complete_separator_sequence_builds_dominate_dimension_inference(
        separator_builds,
        visible_content,
    ):
        return (
            separator_builds,
            band_evaluations + separator_build_evaluations,
            bool(
                band_budget_exhausted
                or separator_build_budget_exhausted
            ),
        )
    measured_budget = (
        maximum_assignment_evaluations
        - band_evaluations
        - separator_build_evaluations
    )
    measured_builds: tuple[_SequenceBuild, ...] = ()
    measured_evaluations = 0
    measured_budget_exhausted = False
    if measured_budget > 0:
        (
            measured_builds,
            measured_evaluations,
            measured_budget_exhausted,
        ) = _measured_path_builds(
            search_scope,
            search_index,
            (shared_short_axis,),
            search_widths,
            frame_width_hint,
            count,
            visible_content,
            measured_budget,
            tuple(
                dict.fromkeys(
                    (
                        *separator_width_search_hints,
                        frame_width_hint,
                        *(
                            ()
                            if physical_scale_constraint is None
                            else (physical_scale_constraint.width_px,)
                        ),
                    )
                )
            ),
            physical_scale_constraint=physical_scale_constraint,
            allow_nominal_slot_sized_gap=allow_nominal_slot_sized_gap,
        )
    return (
        (*separator_builds, *measured_builds),
        band_evaluations + separator_build_evaluations + measured_evaluations,
        bool(
            band_budget_exhausted
            or separator_build_budget_exhausted
            or measured_budget_exhausted
        ),
    )


def solve_frame_sequence(
    search_index: FrameSequenceSearchIndex,
    search_scope: FrameSequenceSearchScope,
    short_axis_plan: SharedShortAxisPlan,
    count: int,
    dimensions: FrameDimensionPrior,
    visible_content: ContentRegionObservation,
    maximum_assignment_evaluations: int,
    *,
    strip_mode: str,
    nominal_count: int,
) -> FrameSequenceSolveResult | FrameSequenceSolveFailure:
    if count <= 0:
        raise ValueError("frame sequence count must be positive")
    if strip_mode not in {FULL, PARTIAL} or nominal_count <= 0:
        raise ValueError("frame sequence solver requires mode and nominal count")
    if maximum_assignment_evaluations <= 0:
        raise ValueError("frame sequence solver budget must be positive")
    supports = search_index.separator_supports.canonical_supports
    shared_short_axis = short_axis_plan.span
    if not shared_short_axis.supports_safe_crop:
        return FrameSequenceSolveFailure(short_axis_plan.search_outcome, 0)
    if supports and any(
        support.measurement.short_axis_span
        != shared_short_axis.measurement_span
        for support in supports
    ):
        raise ValueError(
            "frame sequence solver requires measurements on its shared short axis"
        )
    sequence_completion_search_enabled = bool(
        strip_mode == FULL
        and count == nominal_count
        and count > MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS
    )
    direct_builds, direct_evaluations, direct_exhausted = (
        _sequence_builds_for_count(
            search_index,
            search_scope,
            shared_short_axis,
            short_axis_plan.photo_height_evidence,
            count,
            dimensions,
            visible_content,
            maximum_assignment_evaluations,
            allow_nominal_slot_sized_gap=False,
        )
    )
    holder_boundaries = _holder_boundaries(search_scope)
    direct_geometry_complete_before_inference = (
        _direct_nominal_geometry_is_complete(
            direct_builds,
            visible_content,
            holder_boundaries,
            short_axis_plan.photo_height_evidence,
            dimensions,
        )
    )
    if (
        sequence_completion_search_enabled
        and not direct_exhausted
        and not direct_geometry_complete_before_inference
    ):
        direct_builds = tuple(
            _infer_unique_slot_in_direct_nominal_build(
                build,
                visible_content,
                search_scope,
                short_axis_plan.photo_height_evidence,
                dimensions,
            )
            for build in direct_builds
        )
    direct_separator_sequence_complete = any(
        len(build.separator_bindings) == count - 1
        for build in direct_builds
    )
    direct_nominal_geometry_resolved = (
        _direct_nominal_geometry_is_complete(
            direct_builds,
            visible_content,
            holder_boundaries,
            short_axis_plan.photo_height_evidence,
            dimensions,
        )
    )
    direct_common_width_supported = (
        _preferred_direct_common_width_is_supported(
            direct_builds,
            visible_content,
            holder_boundaries,
            short_axis_plan.photo_height_evidence,
            dimensions,
        )
    )
    completion_builds: tuple[_SequenceBuild, ...] = ()
    completion_evaluations = 0
    completion_exhausted = False
    if (
        sequence_completion_search_enabled
        and direct_common_width_supported
        and not direct_separator_sequence_complete
        and not direct_nominal_geometry_resolved
    ):
        remaining_evaluations = maximum_assignment_evaluations - direct_evaluations
        if direct_exhausted or remaining_evaluations <= 0:
            completion_exhausted = True
        else:
            (
                real_frame_builds,
                completion_evaluations,
                completion_exhausted,
            ) = (
                _sequence_builds_for_count(
                    search_index,
                    search_scope,
                    shared_short_axis,
                    short_axis_plan.photo_height_evidence,
                    count - 1,
                    dimensions,
                    visible_content,
                    remaining_evaluations,
                    allow_nominal_slot_sized_gap=True,
                )
            )
            completion_builds = _sequence_completed_builds(
                real_frame_builds,
                search_scope,
                short_axis_plan.photo_height_evidence,
                dimensions,
            )
    direct_selection_builds = direct_builds
    if completion_builds:
        strongest_completion_separator_count = max(
            build.objectives.supported_separator_count
            for build in completion_builds
        )
        direct_selection_builds = tuple(
            build
            for build in direct_builds
            if (
                not _build_has_geometry_only_slot(build)
                and (
                    build.objectives.supported_separator_count
                    > strongest_completion_separator_count
                    or _build_supports_resolved_nominal_slots(
                        build,
                        holder_boundaries,
                        short_axis_plan.photo_height_evidence,
                        dimensions,
                    )
                )
            )
        )
    builds = tuple(
        build
        for build in (*direct_selection_builds, *completion_builds)
        if _build_does_not_contradict_common_width(
            build,
            holder_boundaries,
            short_axis_plan.photo_height_evidence,
            dimensions,
        )
        and (
            strip_mode != FULL
            or any(slot.sequence_inferred for slot in build.slots)
            or _build_satisfies_full_endpoint_extent(
                build,
                holder_boundaries,
                short_axis_plan.photo_height_evidence,
                dimensions,
            )
        )
    )
    total_evaluations = direct_evaluations + completion_evaluations
    budget_exhausted = bool(
        short_axis_plan.search_outcome.budget_exhausted
        or direct_exhausted
        or completion_exhausted
    )
    if not builds:
        return FrameSequenceSolveFailure(
            PhysicalSearchOutcome(
                (
                    PhysicalSearchFact.EXECUTION_BUDGET_EXHAUSTED
                    if budget_exhausted
                    else PhysicalSearchFact.CONSTRAINTS_CONTRADICTED,
                ),
            ),
            total_evaluations,
        )

    interior_supports = _interior_separator_supports(supports, search_scope)
    holder_path_ids = {
        path.provenance.observation_id
        for boundary in holder_boundaries.values()
        for path in boundary.supporting_paths
    }
    interior_paths = tuple(
        path
        for path in _axis_paths(search_scope, BoundaryAxis.LONG)
        if path.provenance.observation_id not in holder_path_ids
    )
    resolved_builds = []
    for build in builds:
        resolved, common_width = _resolve_build_physical_boundaries(
            build,
            holder_boundaries,
            short_axis_plan.photo_height_evidence,
            dimensions,
        )
        assigned = _assign_unique_separator_observations(
            resolved,
            common_width,
            interior_supports,
        )
        assigned = _assign_unique_boundary_path_observations(
            assigned,
            common_width,
            interior_paths,
        )
        if assigned != resolved:
            resolved, common_width = _resolve_build_physical_boundaries(
                assigned,
                holder_boundaries,
                short_axis_plan.photo_height_evidence,
                dimensions,
            )
        resolved_builds.append((resolved, common_width))
    resolved_builds = tuple(resolved_builds)
    resolved_builds = tuple(
        item
        for item in resolved_builds
        if _frame_slots_are_strictly_monotonic(item[0].slots)
    )
    if not resolved_builds:
        return FrameSequenceSolveFailure(
            PhysicalSearchOutcome(
                (
                    PhysicalSearchFact.EXECUTION_BUDGET_EXHAUSTED
                    if budget_exhausted
                    else PhysicalSearchFact.CONSTRAINTS_CONTRADICTED,
                ),
            ),
            total_evaluations,
        )
    builds = tuple(build for build, _common_width in resolved_builds)
    content_preserving_builds = tuple(
        build
        for build in builds
        if _build_preserves_visible_content(build, visible_content)
    )
    if content_preserving_builds:
        builds = content_preserving_builds

    best = _physically_preferred_builds(builds)
    assignment_consensus = (
        BoundaryAssignmentConsensus(
            AssignmentConsensusOutcome.COMPONENT_UNRESOLVED,
            len(best),
            (),
        )
        if budget_exhausted
        else _sequence_assignment_consensus(best)
    )
    representative = _representative_build(best)
    holder_boundaries = _holder_boundaries(search_scope)
    representative, common_width = _resolve_build_physical_boundaries(
        representative,
        holder_boundaries,
        short_axis_plan.photo_height_evidence,
        dimensions,
    )
    if not _frame_slots_are_strictly_monotonic(representative.slots):
        return FrameSequenceSolveFailure(
            PhysicalSearchOutcome((PhysicalSearchFact.CONSTRAINTS_CONTRADICTED,)),
            total_evaluations,
        )
    slots, long_axis_assignments = _apply_edge_occlusion_inference(
        representative.slots,
        representative.long_axis_assignments,
        holder_boundaries,
        common_width,
        strip_mode,
    )
    internal_geometry = (
        _apply_internal_geometry_uncertainty(
            slots,
            long_axis_assignments,
            best,
        )
        if assignment_consensus.state == EvidenceState.SUPPORTED
        else (slots, long_axis_assignments)
    )
    if internal_geometry is None:
        return FrameSequenceSolveFailure(
            PhysicalSearchOutcome((PhysicalSearchFact.CONSTRAINTS_CONTRADICTED,)),
            total_evaluations,
        )
    slots, long_axis_assignments = internal_geometry
    external_safety_geometry = _apply_external_safety_envelope(
        slots,
        long_axis_assignments,
        best,
        assignment_consensus,
        search_scope.holder_safety.safe_axis_interval(BoundaryAxis.LONG),
    )
    if external_safety_geometry is None:
        return FrameSequenceSolveFailure(
            PhysicalSearchOutcome((PhysicalSearchFact.CONSTRAINTS_CONTRADICTED,)),
            total_evaluations,
        )
    slots, long_axis_assignments = external_safety_geometry
    if not _frame_slots_are_strictly_monotonic(slots):
        return FrameSequenceSolveFailure(
            PhysicalSearchOutcome((PhysicalSearchFact.CONSTRAINTS_CONTRADICTED,)),
            total_evaluations,
        )
    slots = _annotate_frame_content_occupancy(
        slots,
        visible_content,
    )
    separator_assignments = _separator_assignments_from_bindings(
        representative.separator_bindings,
        slots,
        common_width,
    )
    inter_frame_spacings = _final_inter_frame_spacings(
        slots,
        separator_assignments,
        common_width,
    )
    indexed_anchor_constraints = _indexed_anchor_distance_constraints(
        separator_assignments,
        inter_frame_spacings,
        representative.frame_width_px,
    )
    return FrameSequenceSolveResult(
        shared_short_axis=representative.short_axis,
        photo_height_evidence=short_axis_plan.photo_height_evidence,
        frame_width_search_hint=frame_width_search_hint(
            representative.short_axis,
            dimensions,
        ),
        holder_span_scale_hint=_holder_span_scale_hint(search_scope, count),
        content_extent_constraint=_content_extent_constraint(visible_content),
        indexed_anchor_distance_constraints=indexed_anchor_constraints,
        frame_slots=slots,
        long_axis_assignments=long_axis_assignments,
        separator_assignments=separator_assignments,
        inter_frame_spacings=inter_frame_spacings,
        common_frame_width=common_width,
        residuals=representative.residuals,
        assignment_consensus=assignment_consensus,
        search_outcome=PhysicalSearchOutcome(
            (
                PhysicalSearchFact.SOLUTION_FOUND,
                *(
                    (PhysicalSearchFact.EXECUTION_BUDGET_EXHAUSTED,)
                    if budget_exhausted
                    else ()
                ),
            ),
        ),
        assignment_evaluations=total_evaluations,
    )
