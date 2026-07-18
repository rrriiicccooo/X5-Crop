from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite

from ...domain import (
    BoundaryAxis,
    BoundaryPathFit,
    BoundarySide,
    Box,
    EvidenceState,
    FrameDimensionPrior,
    FrameSequenceSearchScope,
    GrayBoundaryPathObservation,
    HolderBoundaryObservation,
    InterFrameSpacing,
    InterFrameSpacingBasis,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
    SeparatorBandCrossAxisSupport,
    SeparatorBandObservation,
)
from ...image.content import ContentRegionObservation
from . import frame_sequence_candidate_resolution as candidate_resolution
from . import frame_sequence_candidates as sequence_candidates
from . import frame_sequence_common_width as width_resolution
from . import frame_sequence_measurements as measurement_facts
from . import frame_sequence_search as sequence_search
from . import frame_sequence_separator_assignment as separator_assignment
from .model import (
    BoundaryGeometryState,
    FrameBoundarySource,
    FrameContentOccupancy,
    FrameEdgeAssignment,
    FrameSlot,
    FrameWidthPhysicalScaleConstraint,
    HolderSpanScaleHint,
    PhotoHeightEvidence,
    SequenceResiduals,
    SharedShortAxisSafetySpan,
)
from .frame_dimensions import MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS
from .separator.observations import SeparatorSupportSet
from .short_axis import frame_width_search_hint


MINIMUM_COUNT_WITH_INTERIOR_FRAME = 3
BIDIRECTIONAL_REFINEMENT_PASSES = 2

def holder_span_scale_hint(
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

@dataclass(frozen=True)
class _BandSequenceHypothesis:
    supports: tuple[SeparatorBandCrossAxisSupport, ...]
    band_edges: tuple[
        tuple[measurement_facts.EdgeConstraint, measurement_facts.EdgeConstraint], ...
    ]
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
        if self.frame_width_px.minimum < measurement_facts.MINIMUM_POSITIVE_PIXEL_EXTENT:
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
class _MeasuredFrameSearchSpace:
    leading_candidates: tuple[tuple[measurement_facts.EdgeConstraint, bool], ...]
    trailing_candidates: tuple[tuple[measurement_facts.EdgeConstraint, bool], ...]
    observed_constraints: tuple[measurement_facts.MeasuredFrameConstraint, ...]
    width_hypotheses: tuple[width_resolution.CommonWidthHypothesis, ...]
    recurring_width_hypotheses: tuple[
        width_resolution.RecurringBoundaryWidthHypothesis, ...
    ]

@dataclass(frozen=True)
class FrameSequenceSearchIndex:
    separator_supports: SeparatorSupportSet
    leading_candidates: tuple[tuple[measurement_facts.EdgeConstraint, bool], ...]
    trailing_candidates: tuple[tuple[measurement_facts.EdgeConstraint, bool], ...]
    observed_constraints: tuple[measurement_facts.MeasuredFrameConstraint, ...]
    width_hypotheses: tuple[width_resolution.CommonWidthHypothesis, ...]
    recurring_width_hypotheses: tuple[
        width_resolution.RecurringBoundaryWidthHypothesis, ...
    ]
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


def axis_paths(
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
        for boundary in candidate_resolution.holder_boundaries(search_scope).values()
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

def interior_separator_supports(
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
    interior = interior_separator_supports(supports, search_scope)
    if len(interior) < count - 1:
        return ()
    candidate_widths = tuple(
        width
        for left, right in zip(interior, interior[1:])
        if (
            width := measurement_facts.positive_interval(
                right.observation.leading_edge.minus(
                    left.observation.trailing_edge
                )
            )
        )
        is not None
    )
    contributor_indexes = measurement_facts.largest_strict_intersection_indexes(
        candidate_widths,
        MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS,
    )
    if not contributor_indexes:
        return ()
    return (
        measurement_facts.interval_envelope(
            tuple(candidate_widths[index] for index in contributor_indexes)
        ),
    )


def _separator_band_edges(
    edges: tuple[measurement_facts.EdgeConstraint, measurement_facts.EdgeConstraint],
) -> bool:
    return all(
        edge.basis == FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION
        for edge in edges
    )

def _band_edge_options(
    support: SeparatorBandCrossAxisSupport,
) -> tuple[tuple[measurement_facts.EdgeConstraint, measurement_facts.EdgeConstraint], ...]:
    return (separator_assignment.observed_band_edges(support),)

def _width_between_bands(
    left: SeparatorBandObservation,
    right: SeparatorBandObservation,
    left_edges: tuple[measurement_facts.EdgeConstraint, measurement_facts.EdgeConstraint],
    right_edges: tuple[measurement_facts.EdgeConstraint, measurement_facts.EdgeConstraint],
) -> PixelInterval | None:
    if right.leading_edge.minimum <= left.trailing_edge.maximum:
        return None
    return measurement_facts.positive_interval(
        right_edges[0].position.minus(left_edges[1].position)
    )

def _band_edge_interpretation_is_admissible(
    band_index: int,
    supports: tuple[SeparatorBandCrossAxisSupport, ...],
    selected_edges: tuple[tuple[measurement_facts.EdgeConstraint, measurement_facts.EdgeConstraint], ...],
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
    selected_edges: tuple[tuple[measurement_facts.EdgeConstraint, measurement_facts.EdgeConstraint], ...],
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
    edge_options: tuple[tuple[tuple[measurement_facts.EdgeConstraint, measurement_facts.EdgeConstraint], ...], ...],
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
    band_edges: tuple[tuple[measurement_facts.EdgeConstraint, measurement_facts.EdgeConstraint], ...],
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
            measurement_facts.interval_distance(frame_width_px, frame_width_hint)
            / max(measurement_facts.MINIMUM_POSITIVE_PIXEL_EXTENT, frame_width_hint.midpoint)
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
    interior = interior_separator_supports(supports, search_scope)
    if len(interior) < required:
        return (), 0, False
    hypotheses: list[_BandSequenceHypothesis] = []
    evaluations = 0
    search_truncated = False
    search_width = PixelInterval(
        measurement_facts.MINIMUM_POSITIVE_PIXEL_EXTENT,
        float(search_scope.holder_safety.box.width),
    )
    edge_options = tuple(_band_edge_options(item) for item in interior)

    def search(
        start_index: int,
        selected_supports: tuple[SeparatorBandCrossAxisSupport, ...],
        selected_edges: tuple[tuple[measurement_facts.EdgeConstraint, measurement_facts.EdgeConstraint], ...],
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
                width_resolution.strict_majority_width_consensus(indexed_widths)
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
                        else width_resolution.strict_majority_width_consensus(existing_widths)
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
) -> measurement_facts.EdgeConstraint:
    return measurement_facts.EdgeConstraint(
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
) -> tuple[measurement_facts.EdgeConstraint | None, bool]:
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

def _endpoint_residual(
    visible_width: PixelInterval,
    frame_width: PixelInterval,
) -> float:
    if visible_width.intersects(frame_width):
        return 0.0
    return measurement_facts.interval_distance(visible_width, frame_width) / max(
        measurement_facts.MINIMUM_POSITIVE_PIXEL_EXTENT,
        frame_width.midpoint,
    )

def _admissible_frame_endpoints(
    paths: tuple[GrayBoundaryPathObservation, ...],
    inner: measurement_facts.EdgeConstraint,
    frame_width: PixelInterval,
    holder_boundary: HolderBoundaryObservation | None,
    holder: Box,
    *,
    leading: bool,
    additional_constraints: tuple[measurement_facts.EdgeConstraint, ...] = (),
) -> tuple[measurement_facts.EdgeConstraint, ...]:
    ranked: list[tuple[tuple[float, float, float, float], measurement_facts.EdgeConstraint]] = []
    candidates: list[tuple[measurement_facts.EdgeConstraint, bool]] = []
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
            visible = measurement_facts.visible_width(constraint, inner)
        else:
            if constraint.position.maximum <= inner.position.minimum:
                continue
            visible = measurement_facts.visible_width(inner, constraint)
        if visible is None:
            continue
        residual = _endpoint_residual(visible, frame_width)
        if (
            residual > 0.0
            and not holder_clip_supported
            and not measurement_facts.measurement_intervals_are_compatible(
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
    endpoint: measurement_facts.EdgeConstraint,
    boundary: HolderBoundaryObservation | None,
) -> bool:
    return bool(
        endpoint.path is not None
        and _holder_boundary_supports_path(endpoint.path, boundary)
    )

def _frame_width_for_endpoints(
    hypothesis: _BandSequenceHypothesis,
    leading_endpoint: measurement_facts.EdgeConstraint,
    trailing_endpoint: measurement_facts.EdgeConstraint,
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
) -> PixelInterval | None:
    first_edges = hypothesis.band_edges[0]
    last_edges = hypothesis.band_edges[-1]
    leading_width = measurement_facts.visible_width(leading_endpoint, first_edges[0])
    trailing_width = measurement_facts.visible_width(last_edges[1], trailing_endpoint)
    if leading_width is None or trailing_width is None:
        return None

    if hypothesis.indexed_anchor_count == 0:
        shared = leading_width.intersection(trailing_width)
        if shared is not None:
            return measurement_facts.positive_interval(shared)
        if measurement_facts.measurement_intervals_are_compatible(
            leading_width,
            trailing_width,
        ):
            return measurement_facts.positive_interval(
                measurement_facts.interval_envelope((leading_width, trailing_width))
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
        if measurement_facts.measurement_intervals_are_compatible(shared, visible_width):
            continue
        if not clipped or visible_width.minimum > shared.maximum:
            return None
    return measurement_facts.positive_interval(shared)

def _refine_dimension_constraint(
    constraint: measurement_facts.EdgeConstraint,
    position: PixelInterval,
) -> measurement_facts.EdgeConstraint | None:
    if constraint.basis != FrameBoundarySource.DIMENSION_CONSTRAINED:
        return (
            constraint
            if measurement_facts.measurement_intervals_are_compatible(
                constraint.position,
                position,
            )
            else None
        )
    refined = constraint.position.intersection(position)
    if refined is None:
        return None
    return measurement_facts.EdgeConstraint(
        position=refined,
        basis=constraint.basis,
        state=constraint.state,
        geometry_state=constraint.geometry_state,
        provenance=constraint.provenance,
    )

def _refine_frame_edges(
    leading: measurement_facts.EdgeConstraint,
    trailing: measurement_facts.EdgeConstraint,
    frame_width: PixelInterval,
    *,
    allow_underwidth: bool,
) -> tuple[measurement_facts.EdgeConstraint, measurement_facts.EdgeConstraint] | None:
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
    width = measurement_facts.visible_width(current_leading, current_trailing)
    if width is None:
        return None
    if (
        not allow_underwidth
        and not measurement_facts.measurement_intervals_are_compatible(width, frame_width)
    ):
        return None
    return current_leading, current_trailing

def _sequence_constraints_fit_physical_scale(
    constraints: tuple[measurement_facts.MeasuredFrameConstraint, ...],
    physical_scale: FrameWidthPhysicalScaleConstraint,
) -> bool:
    return all(
        constraint.leading_holder_clip_supported
        or constraint.trailing_holder_clip_supported
        or constraint.width_px.intersects(physical_scale.width_px)
        for constraint in constraints
    )


def _dimension_constraint(
    anchor: measurement_facts.EdgeConstraint,
    hypothesis: width_resolution.DimensionPlacementHypothesis,
    position: PixelInterval,
    side: BoundarySide,
) -> measurement_facts.EdgeConstraint:
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
    return measurement_facts.EdgeConstraint(
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
    inferred: measurement_facts.EdgeConstraint,
    candidates: tuple[tuple[measurement_facts.EdgeConstraint, bool], ...],
) -> tuple[measurement_facts.EdgeConstraint, ...]:
    observed = tuple(
        candidate
        for candidate, _ in candidates
        if candidate.position.intersects(inferred.position)
    )
    return tuple(dict.fromkeys((*observed, inferred)))

def _dimension_seed_candidates(
    candidates: tuple[tuple[measurement_facts.EdgeConstraint, bool], ...],
) -> tuple[tuple[measurement_facts.EdgeConstraint, bool], ...]:
    return tuple(
        item
        for item in candidates
        if (
            item[0].external_side is not None
            or measurement_facts.separator_edge_path_is_supported(item[0])
        )
    )

def _has_supported_internal_separator_edge_seed(
    candidates: tuple[tuple[measurement_facts.EdgeConstraint, bool], ...],
) -> bool:
    return any(
        edge.external_side is None
        and measurement_facts.separator_edge_path_is_supported(edge)
        for edge, _ in candidates
    )

def _dimension_frame_constraints(
    leading_seeds: tuple[tuple[measurement_facts.EdgeConstraint, bool], ...],
    trailing_seeds: tuple[tuple[measurement_facts.EdgeConstraint, bool], ...],
    leading_candidates: tuple[tuple[measurement_facts.EdgeConstraint, bool], ...],
    trailing_candidates: tuple[tuple[measurement_facts.EdgeConstraint, bool], ...],
    width_hypotheses: tuple[width_resolution.DimensionPlacementHypothesis, ...],
    holder_axis: PixelInterval,
    search_widths: tuple[PixelInterval, ...],
    frame_width_hint: PixelInterval,
) -> tuple[measurement_facts.MeasuredFrameConstraint, ...]:
    constraints: list[measurement_facts.MeasuredFrameConstraint] = []
    for hypothesis in width_hypotheses:
        search_order_residual = measurement_facts.minimum_width_residual(
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
                        width = measurement_facts.visible_width(focused_leading, focused_trailing)
                        if width is None:
                            continue
                        shared = width.intersection(hypothesis.width_px)
                        if shared is None:
                            continue
                        constraints.append(
                            measurement_facts.MeasuredFrameConstraint(
                                leading=focused_leading,
                                trailing=focused_trailing,
                                width_px=shared,
                                full_width_hypothesis_admissible=True,
                                leading_holder_clip_supported=False,
                                trailing_holder_clip_supported=False,
                                search_order_residual=search_order_residual,
                                frame_width_hint_residual=measurement_facts.minimum_width_residual(
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
                        width = measurement_facts.visible_width(focused_leading, focused_trailing)
                        if width is None:
                            continue
                        shared = width.intersection(hypothesis.width_px)
                        if shared is None:
                            continue
                        constraints.append(
                            measurement_facts.MeasuredFrameConstraint(
                                leading=focused_leading,
                                trailing=focused_trailing,
                                width_px=shared,
                                full_width_hypothesis_admissible=True,
                                leading_holder_clip_supported=False,
                                trailing_holder_clip_supported=False,
                                search_order_residual=search_order_residual,
                                frame_width_hint_residual=measurement_facts.minimum_width_residual(
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
    tuple[tuple[measurement_facts.EdgeConstraint, bool], ...],
    tuple[tuple[measurement_facts.EdgeConstraint, bool], ...],
]:
    holder_boundaries = candidate_resolution.holder_boundaries(search_scope)
    interior_observations = set(
        _interior_separator_observations(separator_supports, search_scope)
    )
    leading_holder = holder_boundaries.get(BoundarySide.LEADING)
    trailing_holder = holder_boundaries.get(BoundarySide.TRAILING)
    leading_candidates: list[tuple[measurement_facts.EdgeConstraint, bool]] = []
    trailing_candidates: list[tuple[measurement_facts.EdgeConstraint, bool]] = []
    for support in separator_supports:
        preceding_trailing, following_leading = separator_assignment.observed_band_edges(support)
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
        if support in interior_observations and measurement_facts.separator_edge_path_is_supported(
            preceding_trailing
        ):
            trailing_candidates.append((preceding_trailing, False))
        if support in interior_observations and measurement_facts.separator_edge_path_is_supported(
            following_leading
        ):
            leading_candidates.append((following_leading, False))
        if measurement_facts.separator_edge_path_is_supported(following_leading):
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
        if measurement_facts.separator_edge_path_is_supported(preceding_trailing):
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
    tuple[tuple[measurement_facts.EdgeConstraint, bool], ...],
    tuple[tuple[measurement_facts.EdgeConstraint, bool], ...],
]:
    holder = search_scope.holder_safety.box
    leading_candidates: list[tuple[measurement_facts.EdgeConstraint, bool]] = []
    trailing_candidates: list[tuple[measurement_facts.EdgeConstraint, bool]] = []
    for support in separator_supports:
        observation = support.observation
        if (
            observation.leading_edge.minimum <= float(holder.left)
            or observation.trailing_edge.maximum >= float(holder.right)
        ):
            continue
        preceding_trailing, following_leading = separator_assignment.observed_band_edges(support)
        trailing_candidates.append((preceding_trailing, False))
        leading_candidates.append((following_leading, False))
    return tuple(dict.fromkeys(leading_candidates)), tuple(
        dict.fromkeys(trailing_candidates)
    )

def prepare_frame_sequence_search_index(
    search_scope: FrameSequenceSearchScope,
    separator_supports: SeparatorSupportSet,
) -> FrameSequenceSearchIndex:
    paths = axis_paths(search_scope, BoundaryAxis.LONG)
    holder_boundaries = candidate_resolution.holder_boundaries(search_scope)
    leading_candidates: list[tuple[measurement_facts.EdgeConstraint, bool]] = []
    trailing_candidates: list[tuple[measurement_facts.EdgeConstraint, bool]] = []
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
    observed_constraints: list[measurement_facts.MeasuredFrameConstraint] = []
    evaluations = 0
    for leading, leading_holder_supported in leading_candidates:
        for trailing, trailing_holder_supported in trailing_candidates:
            if trailing.position.minimum <= leading.position.maximum:
                continue
            width = measurement_facts.visible_width(leading, trailing)
            if width is None:
                continue
            leading_clip_supported = leading_holder_supported
            trailing_clip_supported = trailing_holder_supported
            evaluations += 1
            observed_constraints.append(
                measurement_facts.MeasuredFrameConstraint(
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
    width_hypotheses = width_resolution.non_dominated_width_hypotheses(
        width_resolution.measured_width_hypotheses(canonical_observed)
    )
    recurring_width_hypotheses = width_resolution.recurring_boundary_width_hypotheses(
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
            search_order_residual=measurement_facts.minimum_width_residual(
                constraint.width_px,
                search_widths,
            ),
            frame_width_hint_residual=measurement_facts.minimum_width_residual(
                constraint.width_px,
                (frame_width_hint,),
            ),
        )
        for constraint in search_index.observed_constraints
        if (
            constraint.leading_holder_clip_supported
            or constraint.trailing_holder_clip_supported
            or width_resolution.width_satisfies_physical_scale(
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
                if width_resolution.width_satisfies_physical_scale(
                    hypothesis.width_px,
                    physical_scale_constraint,
                )
            ),
            key=lambda hypothesis: (
                measurement_facts.width_search_order_key(hypothesis.width_px, search_widths),
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
                if width_resolution.width_satisfies_physical_scale(
                    hypothesis.width_px,
                    physical_scale_constraint,
                )
            ),
            key=lambda hypothesis: (
                measurement_facts.width_search_order_key(
                    hypothesis.width_px,
                    search_widths,
                ),
                measurement_facts.interval_distance(
                    hypothesis.width_px,
                    frame_width_hint,
                )
                / max(
                    measurement_facts.MINIMUM_POSITIVE_PIXEL_EXTENT,
                    frame_width_hint.midpoint,
                ),
                -hypothesis.contributor_count,
                measurement_facts.interval_midpoint_residual(
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


def _measured_spacing(
    boundary_index: int,
    left: FrameSlot,
    right: FrameSlot,
) -> InterFrameSpacing:
    return sequence_candidates.spacing_from_frame_edges(
        boundary_index,
        left.trailing,
        right.leading,
    )


def _measured_sequence_build(
    constraints: tuple[measurement_facts.MeasuredFrameConstraint, ...],
    short_axis: SharedShortAxisSafetySpan,
    holder: Box,
    *,
    allow_nominal_slot_sized_gap: bool,
) -> sequence_candidates.SequenceBuild | None:
    frame_width = (
        constraints[0].width_px
        if len(constraints) == 1
        else width_resolution.measured_constraint_common_width(
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
    constraints = separator_assignment.candidate_specific_separator_edge_roles(constraints)
    slots: list[FrameSlot] = []
    assignments: list[FrameEdgeAssignment] = []
    for frame_index, constraint in enumerate(constraints, start=1):
        leading, leading_assignment = sequence_candidates.resolve_edge_constraint(
            frame_index,
            BoundarySide.LEADING,
            constraint.leading,
        )
        trailing, trailing_assignment = sequence_candidates.resolve_edge_constraint(
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
    separator_bindings: list[sequence_candidates.SeparatorBandBinding] = []
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
            spacing, assignment = separator_assignment.spacing_for_band(
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
            measurement_facts.normalized_interval_contradiction(
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
            measurement_facts.MINIMUM_POSITIVE_PIXEL_EXTENT,
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
    return sequence_candidates.SequenceBuild(
        slots=slots,
        long_axis_assignments=assignments,
        separator_bindings=tuple(separator_bindings),
        spacings=tuple(spacings),
        frame_width_px=frame_width,
        short_axis=short_axis,
        residuals=residuals,
        objectives=sequence_candidates.SequenceBuildObjectives(
            uncorroborated_overlap_extent_px=sequence_candidates.uncorroborated_overlap_extent(
                tuple(spacings)
            ),
            unexplained_spacing_extent_px=sequence_candidates.unexplained_spacing_extent(
                tuple(spacings)
            ),
            supported_separator_count=len(separator_bindings),
            internal_boundary_measurement_quality=internal_boundary_quality,
            dimension_residual=dimension_residual,
            external_boundary_measurement_quality=external_boundary_quality,
            boundary_uncertainty_ratio=residuals.boundary_uncertainty,
            frame_width_hint_residual=frame_width_hint_residual,
            uncorroborated_contact_count=sequence_candidates.uncorroborated_contact_count(
                tuple(spacings)
            ),
            inferred_boundary_count=sequence_candidates.inferred_boundary_count(slots),
        ),
    )

def _canonical_measured_frame_constraints(
    options: tuple[measurement_facts.MeasuredFrameConstraint, ...],
) -> tuple[measurement_facts.MeasuredFrameConstraint, ...]:
    by_geometry: dict[
        tuple[
            tuple[PixelInterval, BoundarySide | None],
            tuple[PixelInterval, BoundarySide | None],
        ],
        measurement_facts.MeasuredFrameConstraint,
    ] = {}
    for option in options:
        key = (
            (option.leading.position, option.leading.external_side),
            (option.trailing.position, option.trailing.external_side),
        )
        existing = by_geometry.get(key)
        if (
            existing is None
            or sequence_search.measured_frame_option_rank(option)
            > sequence_search.measured_frame_option_rank(existing)
        ):
            by_geometry[key] = option
    return tuple(by_geometry.values())

def _content_preserving_complete_separator_builds(
    builds: tuple[sequence_candidates.SequenceBuild, ...],
    visible_content: ContentRegionObservation,
) -> tuple[sequence_candidates.SequenceBuild, ...]:
    return tuple(
        build
        for build in builds
        if sequence_candidates.build_preserves_visible_content(build, visible_content)
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
    builds: tuple[sequence_candidates.SequenceBuild, ...],
    visible_content: ContentRegionObservation,
) -> bool:
    return bool(
        _content_preserving_complete_separator_builds(builds, visible_content)
    )

def _measured_builds_for_options(
    options: tuple[measurement_facts.MeasuredFrameConstraint, ...],
    short_axis: SharedShortAxisSafetySpan,
    holder: Box,
    count: int,
    visible_content: ContentRegionObservation,
    evaluation_budget: int,
    width_hypotheses: tuple[PixelInterval, ...],
    *,
    allow_nominal_slot_sized_gap: bool,
    minimum_supported_separator_count: int = 0,
) -> tuple[tuple[sequence_candidates.SequenceBuild, ...], int, bool]:
    search_result = sequence_search.measured_frame_sequences(
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
            for state in search_result.sequences
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
        search_result.assignment_evaluations,
        search_result.budget_exhausted,
    )

def _supported_separator_incumbent(
    builds: tuple[sequence_candidates.SequenceBuild, ...],
    visible_content: ContentRegionObservation,
) -> int:
    return max(
        (
            build.objectives.supported_separator_count
            for build in builds
            if build.objectives.uncorroborated_overlap_extent_px == 0.0
            and sequence_candidates.build_preserves_visible_content(build, visible_content)
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
) -> tuple[tuple[sequence_candidates.SequenceBuild, ...], int, bool]:
    holder = search_scope.holder_safety.box
    builds: list[sequence_candidates.SequenceBuild] = []
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

        observed_builds: list[sequence_candidates.SequenceBuild] = []
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

        dimension_hypotheses: tuple[width_resolution.DimensionPlacementHypothesis, ...] = ()
        if count > 1 and not complete_separator_sequence_build:
            dimension_hypotheses = width_resolution.dimension_placement_hypotheses(
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
            if not sequence_search.width_hypothesis_can_cover_reliable_content(
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
            hypothesis_builds: list[sequence_candidates.SequenceBuild] = []
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


def _build_sequence(
    band_hypothesis: _BandSequenceHypothesis,
    short_axis: SharedShortAxisSafetySpan,
    leading_endpoint: measurement_facts.EdgeConstraint,
    trailing_endpoint: measurement_facts.EdgeConstraint,
    frame_width: PixelInterval,
    count: int,
    holder: Box,
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
    physical_scale_constraint: FrameWidthPhysicalScaleConstraint | None,
) -> sequence_candidates.SequenceBuild | None:
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

    refined_constraints: list[measurement_facts.MeasuredFrameConstraint] = []
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
        visible_width = measurement_facts.visible_width(refined_leading, refined_trailing)
        if visible_width is None:
            return None
        refined_constraints.append(
            measurement_facts.MeasuredFrameConstraint(
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
            separator_assignment.candidate_specific_separator_edge_roles(tuple(refined_constraints))
        )
        refined_constraints = list(
            separator_assignment.candidate_specific_holder_band_roles(
                tuple(refined_constraints),
                frame_width,
                holder_boundaries,
            )
        )
    slots: list[FrameSlot] = []
    assignments: list[FrameEdgeAssignment] = []
    for frame_index, constraint in enumerate(refined_constraints, start=1):
        leading, leading_assignment = sequence_candidates.resolve_edge_constraint(
            frame_index,
            BoundarySide.LEADING,
            constraint.leading,
        )
        trailing, trailing_assignment = sequence_candidates.resolve_edge_constraint(
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
    separator_bindings: list[sequence_candidates.SeparatorBandBinding] = []
    for boundary_index, support in enumerate(band_hypothesis.supports, start=1):
        signed_width = slots[boundary_index].leading.position.minus(
            slots[boundary_index - 1].trailing.position
        )
        if signed_width.maximum < 0.0:
            return None
        spacing, assignment = separator_assignment.spacing_for_band(
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
            measurement_facts.normalized_interval_contradiction(width, frame_width)
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
            measurement_facts.MINIMUM_POSITIVE_PIXEL_EXTENT,
            float(holder.width + holder.height),
        ),
    )
    endpoint_quality = (
        leading_endpoint.measurement_quality + trailing_endpoint.measurement_quality
    )
    return sequence_candidates.SequenceBuild(
        slots=tuple(slots),
        long_axis_assignments=tuple(assignments),
        separator_bindings=tuple(separator_bindings),
        spacings=tuple(spacings),
        frame_width_px=frame_width,
        short_axis=short_axis,
        residuals=residuals,
        objectives=sequence_candidates.SequenceBuildObjectives(
            uncorroborated_overlap_extent_px=sequence_candidates.uncorroborated_overlap_extent(
                tuple(spacings)
            ),
            unexplained_spacing_extent_px=sequence_candidates.unexplained_spacing_extent(
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
            uncorroborated_contact_count=sequence_candidates.uncorroborated_contact_count(
                tuple(spacings)
            ),
            inferred_boundary_count=sequence_candidates.inferred_boundary_count(tuple(slots)),
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
) -> tuple[tuple[sequence_candidates.SequenceBuild, ...], int, bool]:
    holder = search_scope.holder_safety.box
    holder_boundaries = candidate_resolution.holder_boundaries(search_scope)
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
    builds: list[sequence_candidates.SequenceBuild] = []
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
                measurement_facts.MINIMUM_POSITIVE_PIXEL_EXTENT,
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


def sequence_builds_for_count(
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
) -> tuple[tuple[sequence_candidates.SequenceBuild, ...], int, bool]:
    supports = search_index.separator_supports.canonical_supports
    frame_width_hint = frame_width_search_hint(
        shared_short_axis,
        dimensions,
    ).width_px
    holder_width_hint = holder_span_scale_hint(
        search_scope,
        count,
    ).width_px
    physical_scale_constraint = width_resolution.frame_width_physical_scale_constraint(
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
    separator_builds: tuple[sequence_candidates.SequenceBuild, ...] = ()
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
            axis_paths(search_scope, BoundaryAxis.LONG),
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
    measured_builds: tuple[sequence_candidates.SequenceBuild, ...] = ()
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
