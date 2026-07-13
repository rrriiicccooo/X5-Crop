from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ...domain import (
    BoundaryAxis,
    BoundarySide,
    EvidenceState,
    FrameDimensionPrior,
    GrayBoundaryPathObservation,
    InterPhotoBoundaryReference,
    InterPhotoSpacing,
    InterPhotoSpacingBasis,
    MeasurementIdentity,
    MeasurementProvenance,
    PhotoAperture,
    PhotoApertureBoundaryResolution,
    PhotoApertureCrossAxisHypothesis,
    PhotoApertureEdgeAssignment,
    PhotoApertureEdgeSource,
    PhotoSequenceSearchScope,
    PixelInterval,
    SeparatorBandAssignment,
    SeparatorBandObservation,
    SeparatorCrossAxisMeasurement,
)
from .model import (
    AssignmentConsensusOutcome,
    BoundaryAssignmentConsensus,
    SequenceResiduals,
)


MINIMUM_POSITIVE_PIXEL_EXTENT = 1.0
MINIMUM_COUNT_WITH_INTERIOR_PHOTO = 3
BIDIRECTIONAL_REFINEMENT_PASSES = 2


@dataclass(frozen=True)
class PhotoSequenceSolveResult:
    photo_apertures: tuple[PhotoAperture, ...]
    aperture_edge_assignments: tuple[PhotoApertureEdgeAssignment, ...]
    separator_assignments: tuple[SeparatorBandAssignment, ...]
    inter_photo_spacings: tuple[InterPhotoSpacing, ...]
    photo_width_constraint_px: PixelInterval
    photo_height_constraint_px: PixelInterval
    residuals: SequenceResiduals
    assignment_consensus: BoundaryAssignmentConsensus
    assignment_evaluations: int
    search_budget_exhausted: bool

    def __post_init__(self) -> None:
        if self.assignment_evaluations < 0:
            raise ValueError("assignment evaluation count cannot be negative")
        if self.photo_width_constraint_px.minimum <= 0.0:
            raise ValueError("photo width constraint must be positive")
        if self.photo_height_constraint_px.minimum <= 0.0:
            raise ValueError("photo height constraint must be positive")


class PhotoSequenceSolveUnavailableReason(str, Enum):
    GEOMETRY_CONSTRAINTS = "photo_aperture_geometry_unresolved"


@dataclass(frozen=True)
class PhotoSequenceSolveUnavailable:
    reason: PhotoSequenceSolveUnavailableReason
    assignment_evaluations: int

    def __post_init__(self) -> None:
        if self.assignment_evaluations < 0:
            raise ValueError("assignment evaluation count cannot be negative")


@dataclass(frozen=True)
class PhotoApertureCrossAxisPlan:
    hypotheses: tuple[PhotoApertureCrossAxisHypothesis, ...]
    assignment_evaluations: int
    search_budget_exhausted: bool

    def __post_init__(self) -> None:
        if self.assignment_evaluations < 0:
            raise ValueError("cross-axis plan evaluation count cannot be negative")


@dataclass(frozen=True)
class _EdgeConstraint:
    position: PixelInterval
    source: PhotoApertureEdgeSource
    state: EvidenceState
    provenance: MeasurementProvenance
    path: GrayBoundaryPathObservation | None = None
    separator: SeparatorBandObservation | None = None
    separator_cross_axis: SeparatorCrossAxisMeasurement | None = None

    def __post_init__(self) -> None:
        if self.source == PhotoApertureEdgeSource.MEASURED_BOUNDARY_PATH:
            if (
                self.path is None
                or self.separator is not None
                or self.separator_cross_axis is not None
            ):
                raise ValueError("measured aperture constraint requires one raw path")
            if self.path.axis != BoundaryAxis.LONG:
                raise ValueError("long-axis aperture constraint requires a long path")
            if self.state != EvidenceState.SUPPORTED:
                raise ValueError("measured aperture path must remain supported")
            if not self.path.position.intersects(self.position):
                raise ValueError("measured aperture constraint must preserve its path")
        elif self.source == PhotoApertureEdgeSource.SEPARATOR_BAND_EDGE:
            if (
                self.separator is None
                or self.separator_cross_axis is None
                or self.path is not None
            ):
                raise ValueError("separator aperture constraint requires one band")
            if self.state != EvidenceState.SUPPORTED:
                raise ValueError("independent separator aperture edge must be supported")
        elif self.source == PhotoApertureEdgeSource.DIMENSION_HYPOTHESIS:
            if (
                self.separator is None
                or self.separator_cross_axis is None
                or self.path is not None
            ):
                raise ValueError("dimension-constrained aperture edge requires one band")
            if self.state != EvidenceState.UNAVAILABLE:
                raise ValueError("dimension-constrained aperture edge must be unavailable")
        else:
            raise ValueError("unsupported photo aperture constraint source")

    @property
    def measurement_quality(self) -> float:
        if self.path is not None:
            return min(
                self.path.lower_appearance.spatial_continuity,
                self.path.upper_appearance.spatial_continuity,
            )
        assert self.separator is not None
        assert self.separator_cross_axis is not None
        return float(self.separator_cross_axis.longest_supported_ratio or 0.0)


@dataclass(frozen=True)
class _BandSequenceHypothesis:
    bands: tuple[SeparatorBandObservation, ...]
    band_edges: tuple[tuple[_EdgeConstraint, _EdgeConstraint], ...]
    cross_axis: PhotoApertureCrossAxisHypothesis
    photo_width_px: PixelInterval | None
    supported_band_count: int
    measurement_quality: float
    width_residual: float
    uncertainty_px: float


@dataclass(frozen=True)
class _SequenceBuild:
    apertures: tuple[PhotoAperture, ...]
    edge_assignments: tuple[PhotoApertureEdgeAssignment, ...]
    separator_assignments: tuple[SeparatorBandAssignment, ...]
    spacings: tuple[InterPhotoSpacing, ...]
    photo_width_px: PixelInterval
    cross_axis: PhotoApertureCrossAxisHypothesis
    residuals: SequenceResiduals
    rank: tuple[float, int, float, float, float, float, float]


@dataclass(frozen=True)
class _MeasuredApertureConstraint:
    leading: _EdgeConstraint
    trailing: _EdgeConstraint
    width_px: PixelInterval
    full_dimension_supported: bool
    leading_holder_clip_supported: bool
    trailing_holder_clip_supported: bool
    dimension_residual: float

    def allowed_at(self, photo_index: int, count: int) -> bool:
        return bool(
            self.full_dimension_supported
            or (photo_index == 1 and self.leading_holder_clip_supported)
            or (photo_index == count and self.trailing_holder_clip_supported)
        )


def _axis_paths(
    search_scope: PhotoSequenceSearchScope,
    axis: BoundaryAxis,
) -> tuple[GrayBoundaryPathObservation, ...]:
    return tuple(
        sorted(
            dict.fromkeys(
                path
                for path in search_scope.raw_boundary_paths
                if path.axis == axis
            ),
            key=lambda path: (
                path.position.midpoint,
                path.position.maximum - path.position.minimum,
                path.kind.value,
                path.provenance.source,
            ),
        )
    )


def _positive_interval(interval: PixelInterval) -> PixelInterval | None:
    if interval.minimum < MINIMUM_POSITIVE_PIXEL_EXTENT:
        return None
    return interval


def _all_photo_aperture_cross_axis_hypotheses(
    search_scope: PhotoSequenceSearchScope,
) -> tuple[PhotoApertureCrossAxisHypothesis, ...]:
    paths = _axis_paths(search_scope, BoundaryAxis.SHORT)
    holder = search_scope.holder_span.box
    hypotheses: list[PhotoApertureCrossAxisHypothesis] = []
    for top_index, top in enumerate(paths):
        if top.position.minimum < float(holder.top):
            continue
        for bottom in paths[top_index + 1 :]:
            if bottom.position.maximum > float(holder.bottom):
                continue
            if bottom.position.minimum <= top.position.maximum:
                continue
            hypotheses.append(
                PhotoApertureCrossAxisHypothesis(
                    top_path=top,
                    bottom_path=bottom,
                )
            )
    return tuple(
        sorted(
            hypotheses,
            key=lambda item: (
                item.measurement_quality,
                -item.uncertainty_px,
                item.height_px.midpoint,
            ),
            reverse=True,
        )
    )


def _interior_separator_observations(
    observations: tuple[SeparatorBandObservation, ...],
    search_scope: PhotoSequenceSearchScope,
) -> tuple[SeparatorBandObservation, ...]:
    holder = search_scope.holder_span.box
    return tuple(
        sorted(
            dict.fromkeys(
                observation
                for observation in observations
                if observation.start > float(holder.left)
                and observation.end < float(holder.right)
            ),
            key=lambda observation: (
                observation.start,
                observation.end,
                observation.provenance.source,
            ),
        )
    )


def photo_aperture_cross_axis_plan(
    search_scope: PhotoSequenceSearchScope,
    dimensions: FrameDimensionPrior,
    count: int,
    maximum_hypotheses: int,
) -> PhotoApertureCrossAxisPlan:
    if min(count, maximum_hypotheses) <= 0:
        raise ValueError("cross-axis planning requires positive count and budget")
    all_hypotheses = _all_photo_aperture_cross_axis_hypotheses(search_scope)
    holder_long_extent = float(search_scope.holder_span.box.width)

    def rank(
        hypothesis: PhotoApertureCrossAxisHypothesis,
    ) -> tuple[float, float, float, float, float]:
        photo_width = _cross_axis_width_constraint(hypothesis, dimensions)
        nonoverlap_overrun = max(
            0.0,
            float(count) * photo_width.minimum - holder_long_extent,
        ) / max(MINIMUM_POSITIVE_PIXEL_EXTENT, holder_long_extent)
        return (
            -nonoverlap_overrun,
            hypothesis.height_px.minimum,
            hypothesis.measurement_quality,
            -hypothesis.uncertainty_px,
            hypothesis.height_px.maximum,
        )

    ranked = tuple(
        sorted(
            all_hypotheses,
            key=rank,
            reverse=True,
        )[:maximum_hypotheses]
    )
    return PhotoApertureCrossAxisPlan(ranked, 0, False)


def _dimension_band_constraint(
    observation: SeparatorBandObservation,
    cross_axis: PhotoApertureCrossAxisHypothesis,
) -> _EdgeConstraint:
    measurement = observation.cross_axis_measurement_for(cross_axis)
    return _EdgeConstraint(
        position=observation.interval,
        source=PhotoApertureEdgeSource.DIMENSION_HYPOTHESIS,
        state=EvidenceState.UNAVAILABLE,
        provenance=observation.provenance,
        separator=observation,
        separator_cross_axis=measurement,
    )


def _separator_band_edge_constraint(
    observation: SeparatorBandObservation,
    cross_axis: PhotoApertureCrossAxisHypothesis,
    position: float,
) -> _EdgeConstraint:
    return _EdgeConstraint(
        position=PixelInterval.exact(position),
        source=PhotoApertureEdgeSource.SEPARATOR_BAND_EDGE,
        state=EvidenceState.SUPPORTED,
        provenance=observation.provenance,
        separator=observation,
        separator_cross_axis=observation.cross_axis_measurement_for(cross_axis),
    )


def _observed_band_edges(
    observation: SeparatorBandObservation,
    cross_axis: PhotoApertureCrossAxisHypothesis,
) -> tuple[_EdgeConstraint, _EdgeConstraint]:
    return (
        _separator_band_edge_constraint(
            observation,
            cross_axis,
            observation.start,
        ),
        _separator_band_edge_constraint(
            observation,
            cross_axis,
            observation.end,
        ),
    )


def _separator_band_edges(
    edges: tuple[_EdgeConstraint, _EdgeConstraint],
) -> bool:
    return all(
        edge.source == PhotoApertureEdgeSource.SEPARATOR_BAND_EDGE
        for edge in edges
    )


def _measured_path_pairs_within_band(
    observation: SeparatorBandObservation,
    paths: tuple[GrayBoundaryPathObservation, ...],
) -> tuple[tuple[_EdgeConstraint, _EdgeConstraint], ...]:
    contained = tuple(
        _external_constraint(path)
        for path in paths
        if path.position.minimum >= observation.start
        and path.position.maximum <= observation.end
    )
    pairs = tuple(
        (trailing, leading)
        for trailing_index, trailing in enumerate(contained)
        for leading in contained[trailing_index + 1 :]
        if leading.position.minimum > trailing.position.maximum
        and leading.provenance != trailing.provenance
    )
    return tuple(
        sorted(
            pairs,
            key=lambda pair: (
                sum(edge.measurement_quality for edge in pair),
                -sum(
                    edge.position.maximum - edge.position.minimum
                    for edge in pair
                ),
                -pair[0].position.midpoint,
                -pair[1].position.midpoint,
            ),
            reverse=True,
        )
    )


def _band_edge_options(
    observation: SeparatorBandObservation,
    cross_axis: PhotoApertureCrossAxisHypothesis,
    paths: tuple[GrayBoundaryPathObservation, ...],
) -> tuple[tuple[_EdgeConstraint, _EdgeConstraint], ...]:
    fallback = _dimension_band_constraint(observation, cross_axis)
    measurement = observation.cross_axis_measurement_for(cross_axis)
    measured_paths = _measured_path_pairs_within_band(observation, paths)
    if measurement.state != EvidenceState.SUPPORTED:
        return (*measured_paths, (fallback, fallback))
    return (
        _observed_band_edges(observation, cross_axis),
        *measured_paths,
        (fallback, fallback),
    )


def _width_between_bands(
    left: SeparatorBandObservation,
    right: SeparatorBandObservation,
    left_edges: tuple[_EdgeConstraint, _EdgeConstraint],
    right_edges: tuple[_EdgeConstraint, _EdgeConstraint],
) -> PixelInterval | None:
    if right.start < left.end:
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


def _supported_band_demotion_is_justified(
    band_index: int,
    bands: tuple[SeparatorBandObservation, ...],
    selected_edges: tuple[tuple[_EdgeConstraint, _EdgeConstraint], ...],
    cross_axis: PhotoApertureCrossAxisHypothesis,
    physical_width: PixelInterval,
) -> bool:
    band = bands[band_index]
    chosen = selected_edges[band_index]
    measurement = band.cross_axis_measurement_for(cross_axis)
    if (
        measurement.state != EvidenceState.SUPPORTED
        or _separator_band_edges(chosen)
    ):
        return True
    observed = _observed_band_edges(band, cross_axis)
    neighbor_widths: list[PixelInterval | None] = []
    if band_index > 0:
        neighbor_widths.append(
            _width_between_bands(
                bands[band_index - 1],
                band,
                selected_edges[band_index - 1],
                observed,
            )
        )
    if band_index + 1 < len(bands):
        neighbor_widths.append(
            _width_between_bands(
                band,
                bands[band_index + 1],
                observed,
                selected_edges[band_index + 1],
            )
        )
    return any(
        width is None or not width.intersects(physical_width)
        for width in neighbor_widths
    )


def _band_search_order(
    observations: tuple[SeparatorBandObservation, ...],
    edge_options: tuple[tuple[tuple[_EdgeConstraint, _EdgeConstraint], ...], ...],
    start_index: int,
    remaining_count: int,
) -> tuple[int, ...]:
    maximum_index = len(observations) - remaining_count
    return tuple(
        sorted(
            range(start_index, maximum_index + 1),
            key=lambda index: (
                max(
                    all(edge.state == EvidenceState.SUPPORTED for edge in pair)
                    for pair in edge_options[index]
                ),
                max(
                    sum(edge.measurement_quality for edge in pair)
                    for pair in edge_options[index]
                ),
                -min(
                    sum(
                        edge.position.maximum - edge.position.minimum
                        for edge in pair
                    )
                    for pair in edge_options[index]
                ),
                -observations[index].start,
            ),
            reverse=True,
        )
    )


def _band_sequence_hypothesis(
    bands: tuple[SeparatorBandObservation, ...],
    band_edges: tuple[tuple[_EdgeConstraint, _EdgeConstraint], ...],
    cross_axis: PhotoApertureCrossAxisHypothesis,
    photo_width_px: PixelInterval,
    physical_width_px: PixelInterval,
) -> _BandSequenceHypothesis:
    return _BandSequenceHypothesis(
        bands=bands,
        band_edges=band_edges,
        cross_axis=cross_axis,
        photo_width_px=photo_width_px,
        supported_band_count=sum(
            _separator_band_edges(pair)
            for pair in band_edges
        ),
        measurement_quality=sum(
            edge.measurement_quality
            for pair in band_edges
            for edge in pair
            if edge.state == EvidenceState.SUPPORTED
        ),
        width_residual=float(
            _interval_distance(photo_width_px, physical_width_px)
            / max(MINIMUM_POSITIVE_PIXEL_EXTENT, physical_width_px.midpoint)
        ),
        uncertainty_px=sum(
            edge.position.maximum - edge.position.minimum
            for pair in band_edges
            for edge in pair
        ),
    )


def _band_sequence_hypotheses(
    observations: tuple[SeparatorBandObservation, ...],
    search_scope: PhotoSequenceSearchScope,
    count: int,
    dimensions: FrameDimensionPrior,
    cross_axis: PhotoApertureCrossAxisHypothesis,
    evaluation_budget: int,
    maximum_hypotheses: int,
) -> tuple[tuple[_BandSequenceHypothesis, ...], int, bool]:
    required = max(0, count - 1)
    interior = _interior_separator_observations(observations, search_scope)
    if required == 0:
        return (
            (
                _BandSequenceHypothesis(
                    (),
                    (),
                    cross_axis,
                    None,
                    0,
                    0.0,
                    0.0,
                    0.0,
                ),
            ),
            0,
            False,
        )
    if len(interior) < required:
        return (), 0, False
    if maximum_hypotheses <= 0:
        raise ValueError("separator hypothesis budget must be positive")

    hypotheses: list[_BandSequenceHypothesis] = []
    evaluations = 0
    search_truncated = False
    physical_width = _cross_axis_width_constraint(cross_axis, dimensions)
    long_paths = _axis_paths(search_scope, BoundaryAxis.LONG)
    edge_options = tuple(
        _band_edge_options(item, cross_axis, long_paths) for item in interior
    )

    def search(
        start_index: int,
        selected_bands: tuple[SeparatorBandObservation, ...],
        selected_edges: tuple[tuple[_EdgeConstraint, _EdgeConstraint], ...],
    ) -> None:
        nonlocal evaluations, search_truncated
        if search_truncated:
            return
        if len(selected_bands) == required:
            if not all(
                _supported_band_demotion_is_justified(
                    band_index,
                    selected_bands,
                    selected_edges,
                    cross_axis,
                    physical_width,
                )
                for band_index in range(len(selected_bands))
            ):
                return
            hypothesis = _band_sequence_hypothesis(
                selected_bands,
                selected_edges,
                cross_axis,
                physical_width,
                physical_width,
            )
            if len(hypotheses) < maximum_hypotheses:
                hypotheses.append(hypothesis)
            else:
                search_truncated = True
            return

        remaining_count = required - len(selected_bands)
        for observation_index in _band_search_order(
            interior,
            edge_options,
            start_index,
            remaining_count,
        ):
            observation = interior[observation_index]
            for edges in edge_options[observation_index]:
                if evaluations >= evaluation_budget:
                    search_truncated = True
                    return
                evaluations += 1
                if selected_bands:
                    measured_width = _width_between_bands(
                        selected_bands[-1],
                        observation,
                        selected_edges[-1],
                        edges,
                    )
                    if (
                        measured_width is None
                        or not measured_width.intersects(physical_width)
                    ):
                        continue
                next_bands = (*selected_bands, observation)
                next_edges = (*selected_edges, edges)
                resolved_neighbor_index = len(selected_bands) - 1
                if (
                    selected_bands
                    and not _supported_band_demotion_is_justified(
                        resolved_neighbor_index,
                        next_bands,
                        next_edges,
                        cross_axis,
                        physical_width,
                    )
                ):
                    continue
                search(
                    observation_index + 1,
                    next_bands,
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
        source=PhotoApertureEdgeSource.MEASURED_BOUNDARY_PATH,
        state=EvidenceState.SUPPORTED,
        provenance=path.provenance,
        path=path,
    )


def _visible_width(
    leading: _EdgeConstraint,
    trailing: _EdgeConstraint,
) -> PixelInterval | None:
    return _positive_interval(trailing.position.minus(leading.position))


def _endpoint_residual(
    visible_width: PixelInterval,
    photo_width: PixelInterval,
) -> float | None:
    if visible_width.minimum > photo_width.maximum:
        return None
    if visible_width.intersects(photo_width):
        return 0.0
    return max(0.0, photo_width.minimum - visible_width.maximum) / max(
        MINIMUM_POSITIVE_PIXEL_EXTENT,
        photo_width.midpoint,
    )


def _best_external_constraints(
    paths: tuple[GrayBoundaryPathObservation, ...],
    inner: _EdgeConstraint,
    photo_width: PixelInterval,
    *,
    leading: bool,
) -> tuple[_EdgeConstraint, ...]:
    ranked: list[tuple[tuple[float, float, float, float], _EdgeConstraint]] = []
    for path in paths:
        constraint = _external_constraint(path)
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
        residual = _endpoint_residual(visible, photo_width)
        if residual is None:
            continue
        rank = (
            -float(residual),
            min(visible.midpoint, photo_width.midpoint),
            constraint.measurement_quality,
            -(constraint.position.maximum - constraint.position.minimum),
        )
        ranked.append((rank, constraint))
    if not ranked:
        return ()
    best_rank = max(item[0] for item in ranked)
    return tuple(item[1] for item in ranked if item[0] == best_rank)


def _cross_axis_width_constraint(
    cross_axis: PhotoApertureCrossAxisHypothesis,
    dimensions: FrameDimensionPrior,
) -> PixelInterval:
    if dimensions.calibrated:
        calibrated = dimensions.calibrated_width_px
        assert calibrated is not None
        return calibrated
    return cross_axis.height_px.scaled(dimensions.aspect)


def _width_for_cross_axis(
    band_width: PixelInterval | None,
    cross_axis: PhotoApertureCrossAxisHypothesis,
    dimensions: FrameDimensionPrior,
) -> tuple[PixelInterval | None, float]:
    cross_width = _cross_axis_width_constraint(cross_axis, dimensions)
    if band_width is None:
        return cross_width, 0.0
    intersection = band_width.intersection(cross_width)
    return (
        None if intersection is None else _positive_interval(intersection),
        _interval_distance(band_width, cross_width)
        / max(MINIMUM_POSITIVE_PIXEL_EXTENT, cross_width.midpoint),
    )


def _refine_dimension_constraint(
    constraint: _EdgeConstraint,
    position: PixelInterval,
) -> _EdgeConstraint | None:
    refined = constraint.position.intersection(position)
    if refined is None:
        return None
    if constraint.source != PhotoApertureEdgeSource.DIMENSION_HYPOTHESIS:
        return constraint
    return _EdgeConstraint(
        position=refined,
        source=constraint.source,
        state=constraint.state,
        provenance=constraint.provenance,
        separator=constraint.separator,
        separator_cross_axis=constraint.separator_cross_axis,
    )


def _refine_aperture_edges(
    leading: _EdgeConstraint,
    trailing: _EdgeConstraint,
    photo_width: PixelInterval,
    *,
    allow_underwidth: bool,
) -> tuple[_EdgeConstraint, _EdgeConstraint] | None:
    current_leading = leading
    current_trailing = trailing
    for _ in range(BIDIRECTIONAL_REFINEMENT_PASSES):
        refined_trailing = _refine_dimension_constraint(
            current_trailing,
            current_leading.position.plus(photo_width),
        )
        if refined_trailing is None:
            if not allow_underwidth:
                return None
        else:
            current_trailing = refined_trailing
        refined_leading = _refine_dimension_constraint(
            current_leading,
            current_trailing.position.minus(photo_width),
        )
        if refined_leading is None:
            if not allow_underwidth:
                return None
        else:
            current_leading = refined_leading
    width = _visible_width(current_leading, current_trailing)
    if width is None or width.minimum > photo_width.maximum:
        return None
    if not allow_underwidth and not width.intersects(photo_width):
        return None
    return current_leading, current_trailing


def _resolution(
    photo_index: int,
    side: BoundarySide,
    constraint: _EdgeConstraint,
) -> tuple[PhotoApertureBoundaryResolution, PhotoApertureEdgeAssignment | None]:
    resolution = PhotoApertureBoundaryResolution(
        photo_index=photo_index,
        side=side,
        position=constraint.position,
        state=constraint.state,
        source=constraint.source,
        provenance=constraint.provenance,
    )
    if constraint.path is None:
        return resolution, None
    return (
        resolution,
        PhotoApertureEdgeAssignment(
            photo_index=photo_index,
            side=side,
            observation=constraint.path,
            resolution=resolution,
        ),
    )


def _short_axis_resolution(
    photo_index: int,
    side: BoundarySide,
    path: GrayBoundaryPathObservation,
) -> tuple[PhotoApertureBoundaryResolution, PhotoApertureEdgeAssignment]:
    resolution = PhotoApertureBoundaryResolution(
        photo_index=photo_index,
        side=side,
        position=path.position,
        state=EvidenceState.SUPPORTED,
        source=PhotoApertureEdgeSource.MEASURED_BOUNDARY_PATH,
        provenance=path.provenance,
    )
    return (
        resolution,
        PhotoApertureEdgeAssignment(
            photo_index=photo_index,
            side=side,
            observation=path,
            resolution=resolution,
        ),
    )


def _measured_aperture_constraints(
    search_scope: PhotoSequenceSearchScope,
    cross_axis: PhotoApertureCrossAxisHypothesis,
    dimensions: FrameDimensionPrior,
    evaluation_budget: int,
    maximum_options: int,
) -> tuple[tuple[_MeasuredApertureConstraint, ...], int, bool]:
    photo_width = _cross_axis_width_constraint(cross_axis, dimensions)
    paths = _axis_paths(search_scope, BoundaryAxis.LONG)
    holder_provenance = {
        item.side: item.provenance for item in search_scope.holder_boundaries
    }
    constraints: list[_MeasuredApertureConstraint] = []
    evaluations = 0
    if maximum_options <= 0:
        raise ValueError("measured aperture option budget must be positive")
    for leading_index, leading_path in enumerate(paths):
        leading = _external_constraint(leading_path)
        for trailing_path in paths[leading_index + 1 :]:
            if evaluations >= evaluation_budget:
                return tuple(constraints), evaluations, True
            evaluations += 1
            trailing = _external_constraint(trailing_path)
            width = _visible_width(leading, trailing)
            if width is None:
                continue
            if width.minimum > photo_width.maximum:
                break
            full_dimension_supported = width.intersects(photo_width)
            leading_clip_supported = bool(
                holder_provenance.get(BoundarySide.LEADING) == leading.provenance
                and width.maximum < photo_width.minimum
            )
            trailing_clip_supported = bool(
                holder_provenance.get(BoundarySide.TRAILING) == trailing.provenance
                and width.maximum < photo_width.minimum
            )
            if not (
                full_dimension_supported
                or leading_clip_supported
                or trailing_clip_supported
            ):
                continue
            constraints.append(
                _MeasuredApertureConstraint(
                    leading=leading,
                    trailing=trailing,
                    width_px=width,
                    full_dimension_supported=full_dimension_supported,
                    leading_holder_clip_supported=leading_clip_supported,
                    trailing_holder_clip_supported=trailing_clip_supported,
                    dimension_residual=(
                        0.0
                        if full_dimension_supported
                        else _interval_distance(width, photo_width)
                        / max(MINIMUM_POSITIVE_PIXEL_EXTENT, photo_width.midpoint)
                    ),
                )
            )
            if len(constraints) >= maximum_options:
                return tuple(constraints), evaluations, True
    return tuple(constraints), evaluations, False


def _spacing_from_aperture_edges(
    boundary_index: int,
    trailing: PhotoApertureBoundaryResolution,
    leading: PhotoApertureBoundaryResolution,
) -> InterPhotoSpacing:
    signed_width = leading.position.minus(trailing.position)
    trailing_provenance = trailing.provenance
    leading_provenance = leading.provenance
    observed = bool(
        signed_width.minimum >= 0.0
        and trailing.source == PhotoApertureEdgeSource.MEASURED_BOUNDARY_PATH
        and leading.source == PhotoApertureEdgeSource.MEASURED_BOUNDARY_PATH
    )
    provenance = MeasurementProvenance(
        root_measurement=(
            MeasurementIdentity.PHOTO_EDGES
            if observed
            else MeasurementIdentity.FRAME_GEOMETRY
        ),
        source=(
            "measured_inter_photo_spacing"
            if observed
            else "overlap_spacing_hypothesis"
        ),
        dependencies=tuple(
            dict.fromkeys(
                (
                    trailing_provenance.root_measurement,
                    leading_provenance.root_measurement,
                )
            )
        ),
        boundary_anchors=(
            trailing_provenance.source,
            leading_provenance.source,
        ),
    )
    return InterPhotoSpacing(
        boundary=InterPhotoBoundaryReference(None, boundary_index),
        signed_width_px=signed_width,
        provenance=provenance,
        basis=(
            InterPhotoSpacingBasis.OBSERVED
            if observed
            else InterPhotoSpacingBasis.GEOMETRY_HYPOTHESIS
        ),
    )


def _measured_spacing(
    boundary_index: int,
    left: PhotoAperture,
    right: PhotoAperture,
) -> InterPhotoSpacing:
    return _spacing_from_aperture_edges(
        boundary_index,
        left.trailing,
        right.leading,
    )


def _uncorroborated_overlap_extent(
    spacings: tuple[InterPhotoSpacing, ...],
) -> float:
    return sum(
        max(0.0, -spacing.signed_width_px.maximum)
        for spacing in spacings
        if spacing.basis == InterPhotoSpacingBasis.GEOMETRY_HYPOTHESIS
    )


def _strictly_dominates_measured_only_search(build: _SequenceBuild) -> bool:
    return bool(
        build.separator_assignments
        and _uncorroborated_overlap_extent(build.spacings) == 0.0
    )


def _measured_sequence_build(
    constraints: tuple[_MeasuredApertureConstraint, ...],
    cross_axis: PhotoApertureCrossAxisHypothesis,
    photo_width: PixelInterval,
    holder_extent: int,
) -> _SequenceBuild:
    apertures: list[PhotoAperture] = []
    assignments: list[PhotoApertureEdgeAssignment] = []
    for photo_index, constraint in enumerate(constraints, start=1):
        leading, leading_assignment = _resolution(
            photo_index,
            BoundarySide.LEADING,
            constraint.leading,
        )
        trailing, trailing_assignment = _resolution(
            photo_index,
            BoundarySide.TRAILING,
            constraint.trailing,
        )
        top, top_assignment = _short_axis_resolution(
            photo_index,
            BoundarySide.TOP,
            cross_axis.top_path,
        )
        bottom, bottom_assignment = _short_axis_resolution(
            photo_index,
            BoundarySide.BOTTOM,
            cross_axis.bottom_path,
        )
        assignments.extend(
            (
                leading_assignment,
                trailing_assignment,
                top_assignment,
                bottom_assignment,
            )
        )
        apertures.append(PhotoAperture(photo_index, leading, trailing, top, bottom))
    spacings = tuple(
        _measured_spacing(index, left, right)
        for index, (left, right) in enumerate(
            zip(apertures, apertures[1:]),
            start=1,
        )
    )
    uncertainty_px = sum(
        edge.position.maximum - edge.position.minimum
        for aperture in apertures
        for edge in (
            aperture.leading,
            aperture.trailing,
            aperture.top,
            aperture.bottom,
        )
    )
    dimension_residual = max(
        (item.dimension_residual for item in constraints),
        default=0.0,
    )
    residuals = SequenceResiduals(
        dimension=dimension_residual,
        conservation=None,
        boundary_uncertainty=uncertainty_px
        / max(MINIMUM_POSITIVE_PIXEL_EXTENT, float(holder_extent)),
    )
    measurement_quality = sum(
        item.leading.measurement_quality + item.trailing.measurement_quality
        for item in constraints
    )
    visible_coverage = sum(item.width_px.midpoint for item in constraints)
    return _SequenceBuild(
        apertures=tuple(apertures),
        edge_assignments=tuple(assignments),
        separator_assignments=(),
        spacings=spacings,
        photo_width_px=photo_width,
        cross_axis=cross_axis,
        residuals=residuals,
        rank=(
            -_uncorroborated_overlap_extent(spacings),
            0,
            measurement_quality,
            -dimension_residual,
            measurement_quality + cross_axis.measurement_quality,
            -residuals.boundary_uncertainty,
            visible_coverage,
        ),
    )


def _measured_aperture_precedes(
    left: _MeasuredApertureConstraint,
    right: _MeasuredApertureConstraint,
) -> bool:
    return bool(
        right.leading.position.minimum > left.leading.position.maximum
        and right.trailing.position.minimum > left.trailing.position.maximum
    )


def _measured_aperture_option_rank(
    option: _MeasuredApertureConstraint,
) -> tuple[bool, float, float, float, float]:
    return (
        option.full_dimension_supported,
        -option.dimension_residual,
        option.leading.measurement_quality + option.trailing.measurement_quality,
        -(
            option.leading.position.maximum
            - option.leading.position.minimum
            + option.trailing.position.maximum
            - option.trailing.position.minimum
        ),
        -option.leading.position.midpoint,
    )


def _measured_aperture_sequences(
    options: tuple[_MeasuredApertureConstraint, ...],
    count: int,
    evaluation_budget: int,
    maximum_sequences: int,
) -> tuple[tuple[tuple[_MeasuredApertureConstraint, ...], ...], int, bool]:
    ordered_indexes = tuple(
        sorted(
            range(len(options)),
            key=lambda index: _measured_aperture_option_rank(options[index]),
            reverse=True,
        )
    )
    evaluations = 0
    layers: list[dict[int, tuple[int, ...]]] = []
    first_layer: dict[int, tuple[int, ...]] = {}
    for option_index in ordered_indexes:
        if evaluations >= evaluation_budget:
            return (), evaluations, True
        evaluations += 1
        if options[option_index].allowed_at(1, count):
            first_layer[option_index] = ()
    if not first_layer:
        return (), evaluations, False
    layers.append(first_layer)

    for layer_index in range(1, count):
        photo_index = layer_index + 1
        previous_layer = layers[-1]
        current_layer: dict[int, tuple[int, ...]] = {}
        for option_index in ordered_indexes:
            if evaluations >= evaluation_budget:
                return (), evaluations, True
            evaluations += 1
            option = options[option_index]
            if not option.allowed_at(photo_index, count):
                continue
            predecessors: list[int] = []
            for previous_index in previous_layer:
                if evaluations >= evaluation_budget:
                    return (), evaluations, True
                evaluations += 1
                if _measured_aperture_precedes(
                    options[previous_index],
                    option,
                ):
                    predecessors.append(previous_index)
            if predecessors:
                current_layer[option_index] = tuple(predecessors)
        if not current_layer:
            return (), evaluations, False
        layers.append(current_layer)

    sequences: list[tuple[_MeasuredApertureConstraint, ...]] = []
    truncated = False

    def collect(
        layer_index: int,
        option_index: int,
        reversed_indexes: tuple[int, ...],
    ) -> None:
        nonlocal evaluations, truncated
        if truncated:
            return
        if evaluations >= evaluation_budget:
            truncated = True
            return
        evaluations += 1
        next_reversed = (*reversed_indexes, option_index)
        if layer_index == 0:
            sequence = tuple(options[index] for index in reversed(next_reversed))
            if len(sequences) < maximum_sequences:
                sequences.append(sequence)
            else:
                truncated = True
            return
        for previous_index in layers[layer_index][option_index]:
            collect(layer_index - 1, previous_index, next_reversed)
            if truncated:
                return

    for final_index in layers[-1]:
        collect(len(layers) - 1, final_index, ())
        if truncated:
            break
    return tuple(sequences), evaluations, truncated


def _measured_path_builds(
    search_scope: PhotoSequenceSearchScope,
    cross_axis_hypotheses: tuple[PhotoApertureCrossAxisHypothesis, ...],
    dimensions: FrameDimensionPrior,
    count: int,
    evaluation_budget: int,
    maximum_solution_alternatives: int,
) -> tuple[tuple[_SequenceBuild, ...], int, bool]:
    holder = search_scope.holder_span.box
    builds: list[_SequenceBuild] = []
    evaluations = 0
    search_truncated = False
    for cross_axis in cross_axis_hypotheses:
        remaining = evaluation_budget - evaluations
        if remaining <= 0:
            return tuple(builds), evaluations, True
        options, option_evaluations, exhausted = _measured_aperture_constraints(
            search_scope,
            cross_axis,
            dimensions,
            remaining,
            count * (maximum_solution_alternatives + 1),
        )
        evaluations += option_evaluations
        search_truncated = search_truncated or exhausted
        ordered_options = tuple(
            sorted(
                options,
                key=_measured_aperture_option_rank,
                reverse=True,
            )
        )
        states, state_evaluations, states_truncated = _measured_aperture_sequences(
            ordered_options,
            count,
            evaluation_budget - evaluations,
            maximum_solution_alternatives,
        )
        evaluations += state_evaluations
        search_truncated = search_truncated or states_truncated
        photo_width = _cross_axis_width_constraint(cross_axis, dimensions)
        builds.extend(
            _measured_sequence_build(
                state,
                cross_axis,
                photo_width,
                holder.width + holder.height,
            )
            for state in states
        )
        if evaluations >= evaluation_budget:
            break
    return tuple(builds), evaluations, search_truncated


def _spacing_for_band(
    boundary_index: int,
    band: SeparatorBandObservation,
    cross_axis: PhotoApertureCrossAxisHypothesis,
    trailing: PhotoApertureBoundaryResolution,
    leading: PhotoApertureBoundaryResolution,
) -> tuple[InterPhotoSpacing, SeparatorBandAssignment | None]:
    measurement = band.cross_axis_measurement_for(cross_axis)
    supported = bool(
        measurement.state == EvidenceState.SUPPORTED
        and trailing.state == EvidenceState.SUPPORTED
        and leading.state == EvidenceState.SUPPORTED
        and trailing.source == PhotoApertureEdgeSource.SEPARATOR_BAND_EDGE
        and leading.source == PhotoApertureEdgeSource.SEPARATOR_BAND_EDGE
    )
    assignment = (
        SeparatorBandAssignment(
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
        basis = InterPhotoSpacingBasis.OBSERVED
    elif (
        trailing.source == PhotoApertureEdgeSource.MEASURED_BOUNDARY_PATH
        and leading.source == PhotoApertureEdgeSource.MEASURED_BOUNDARY_PATH
    ):
        return (
            _spacing_from_aperture_edges(
                boundary_index,
                trailing,
                leading,
            ),
            None,
        )
    else:
        provenance = MeasurementProvenance(
            MeasurementIdentity.FRAME_GEOMETRY,
            "dimension_constrained_inter_photo_spacing",
            tuple(
                dict.fromkeys(
                    (
                        MeasurementIdentity.FRAME_DIMENSIONS,
                        band.provenance.root_measurement,
                    )
                )
            ),
            (
                f"photo:{boundary_index}:trailing",
                f"photo:{boundary_index + 1}:leading",
            ),
        )
        basis = InterPhotoSpacingBasis.GEOMETRY_HYPOTHESIS
    return (
        InterPhotoSpacing(
            boundary=InterPhotoBoundaryReference(None, boundary_index),
            signed_width_px=leading.position.minus(trailing.position),
            provenance=provenance,
            basis=basis,
        ),
        assignment,
    )


def _build_sequence(
    band_hypothesis: _BandSequenceHypothesis,
    cross_axis: PhotoApertureCrossAxisHypothesis,
    leading_endpoint: _EdgeConstraint,
    trailing_endpoint: _EdgeConstraint,
    photo_width: PixelInterval,
    count: int,
    holder_extent: int,
    cross_axis_residual: float,
    holder_boundary_provenance: dict[BoundarySide, MeasurementProvenance],
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
        raise ValueError("photo sequence constraints must match requested count")

    apertures: list[PhotoAperture] = []
    assignments: list[PhotoApertureEdgeAssignment] = []
    for photo_index, (leading_constraint, trailing_constraint) in enumerate(
        zip(leading_constraints, trailing_constraints, strict=True),
        start=1,
    ):
        leading_clip_supported = bool(
            photo_index == 1
            and leading_constraint.path is not None
            and holder_boundary_provenance.get(BoundarySide.LEADING)
            == leading_constraint.provenance
        )
        trailing_clip_supported = bool(
            photo_index == count
            and trailing_constraint.path is not None
            and holder_boundary_provenance.get(BoundarySide.TRAILING)
            == trailing_constraint.provenance
        )
        refined = _refine_aperture_edges(
            leading_constraint,
            trailing_constraint,
            photo_width,
            allow_underwidth=leading_clip_supported or trailing_clip_supported,
        )
        if refined is None:
            return None
        refined_leading, refined_trailing = refined
        leading, leading_assignment = _resolution(
            photo_index,
            BoundarySide.LEADING,
            refined_leading,
        )
        trailing, trailing_assignment = _resolution(
            photo_index,
            BoundarySide.TRAILING,
            refined_trailing,
        )
        top, top_assignment = _short_axis_resolution(
            photo_index,
            BoundarySide.TOP,
            cross_axis.top_path,
        )
        bottom, bottom_assignment = _short_axis_resolution(
            photo_index,
            BoundarySide.BOTTOM,
            cross_axis.bottom_path,
        )
        assignments.extend(
            item
            for item in (
                leading_assignment,
                trailing_assignment,
                top_assignment,
                bottom_assignment,
            )
            if item is not None
        )
        apertures.append(PhotoAperture(photo_index, leading, trailing, top, bottom))

    spacings: list[InterPhotoSpacing] = []
    separator_assignments: list[SeparatorBandAssignment] = []
    for boundary_index, band in enumerate(band_hypothesis.bands, start=1):
        signed_width = apertures[boundary_index].leading.position.minus(
            apertures[boundary_index - 1].trailing.position
        )
        if signed_width.maximum < 0.0:
            return None
        spacing, assignment = _spacing_for_band(
            boundary_index,
            band,
            cross_axis,
            apertures[boundary_index - 1].trailing,
            apertures[boundary_index].leading,
        )
        spacings.append(spacing)
        if assignment is not None:
            separator_assignments.append(assignment)

    photo_widths = tuple(
        aperture.trailing.position.minus(aperture.leading.position)
        for aperture in apertures
    )
    interior_widths = (
        photo_widths[1:-1]
        if count >= MINIMUM_COUNT_WITH_INTERIOR_PHOTO
        else photo_widths
    )
    dimension_residual = max(
        (
            _interval_distance(width, photo_width)
            / max(MINIMUM_POSITIVE_PIXEL_EXTENT, photo_width.midpoint)
            for width in interior_widths
        ),
        default=0.0,
    )
    uncertainty_px = sum(
        edge.position.maximum - edge.position.minimum
        for aperture in apertures
        for edge in (
            aperture.leading,
            aperture.trailing,
            aperture.top,
            aperture.bottom,
        )
    )
    residuals = SequenceResiduals(
        dimension=float(max(dimension_residual, cross_axis_residual)),
        conservation=None,
        boundary_uncertainty=float(uncertainty_px)
        / max(MINIMUM_POSITIVE_PIXEL_EXTENT, float(holder_extent)),
    )
    endpoint_quality = (
        leading_endpoint.measurement_quality + trailing_endpoint.measurement_quality
    )
    visible_coverage = sum(width.midpoint for width in photo_widths)
    return _SequenceBuild(
        apertures=tuple(apertures),
        edge_assignments=tuple(assignments),
        separator_assignments=tuple(separator_assignments),
        spacings=tuple(spacings),
        photo_width_px=photo_width,
        cross_axis=cross_axis,
        residuals=residuals,
        rank=(
            -_uncorroborated_overlap_extent(tuple(spacings)),
            band_hypothesis.supported_band_count,
            band_hypothesis.measurement_quality,
            -float(max(band_hypothesis.width_residual, cross_axis_residual)),
            endpoint_quality + cross_axis.measurement_quality,
            -float(residuals.boundary_uncertainty),
            float(visible_coverage),
        ),
    )


def _builds_for_hypotheses(
    band_hypotheses: tuple[_BandSequenceHypothesis, ...],
    search_scope: PhotoSequenceSearchScope,
    dimensions: FrameDimensionPrior,
    count: int,
    evaluation_budget: int,
) -> tuple[tuple[_SequenceBuild, ...], int, bool]:
    long_paths = _axis_paths(search_scope, BoundaryAxis.LONG)
    holder = search_scope.holder_span.box
    holder_boundary_provenance = {
        item.side: item.provenance for item in search_scope.holder_boundaries
    }
    builds: list[_SequenceBuild] = []
    evaluations = 0
    exhausted = False
    for band_hypothesis in band_hypotheses:
        cross_axis = band_hypothesis.cross_axis
        if evaluations >= evaluation_budget:
            exhausted = True
            break
        evaluations += 1
        photo_width, cross_axis_residual = _width_for_cross_axis(
            band_hypothesis.photo_width_px,
            cross_axis,
            dimensions,
        )
        if photo_width is None:
            continue
        if band_hypothesis.bands:
            first_edges = band_hypothesis.band_edges[0]
            last_edges = band_hypothesis.band_edges[-1]
            leading_options = _best_external_constraints(
                long_paths,
                first_edges[0],
                photo_width,
                leading=True,
            )
            trailing_options = _best_external_constraints(
                long_paths,
                last_edges[1],
                photo_width,
                leading=False,
            )
        else:
            leading_options = tuple(
                _external_constraint(path) for path in long_paths
            )
            trailing_options = leading_options
        for leading_endpoint in leading_options:
            for trailing_endpoint in trailing_options:
                if evaluations >= evaluation_budget:
                    exhausted = True
                    break
                evaluations += 1
                if trailing_endpoint.position.minimum <= leading_endpoint.position.maximum:
                    continue
                if not band_hypothesis.bands:
                    visible = _visible_width(leading_endpoint, trailing_endpoint)
                    if visible is None or not visible.intersects(photo_width):
                        continue
                build = _build_sequence(
                    band_hypothesis,
                    cross_axis,
                    leading_endpoint,
                    trailing_endpoint,
                    photo_width,
                    count,
                    holder.width + holder.height,
                    cross_axis_residual,
                    holder_boundary_provenance,
                )
                if build is not None:
                    builds.append(build)
            if exhausted:
                break
        if exhausted:
            break
    return tuple(builds), evaluations, exhausted


def _conflicting_photo_indexes(
    builds: tuple[_SequenceBuild, ...],
) -> tuple[int, ...]:
    reference = builds[0]
    return tuple(
        photo_index
        for photo_index in range(1, len(reference.apertures) + 1)
        if any(
            any(
                not left.position.intersects(right.position)
                for left, right in zip(
                    (
                        reference.apertures[photo_index - 1].leading,
                        reference.apertures[photo_index - 1].trailing,
                        reference.apertures[photo_index - 1].top,
                        reference.apertures[photo_index - 1].bottom,
                    ),
                    (
                        other.apertures[photo_index - 1].leading,
                        other.apertures[photo_index - 1].trailing,
                        other.apertures[photo_index - 1].top,
                        other.apertures[photo_index - 1].bottom,
                    ),
                    strict=True,
                )
            )
            for other in builds[1:]
        )
    )


def _assignment_consensus(
    builds: tuple[_SequenceBuild, ...],
    *,
    budget_exhausted: bool,
) -> BoundaryAssignmentConsensus:
    conflicting = _conflicting_photo_indexes(builds)
    if budget_exhausted:
        outcome = AssignmentConsensusOutcome.BUDGET_EXHAUSTED
    elif conflicting:
        outcome = AssignmentConsensusOutcome.DISAGREED
    elif len(builds) == 1:
        outcome = AssignmentConsensusOutcome.UNCONTESTED
    else:
        outcome = AssignmentConsensusOutcome.AGREED
    return BoundaryAssignmentConsensus(outcome, len(builds), conflicting)


def solve_photo_sequence(
    observations: tuple[SeparatorBandObservation, ...],
    search_scope: PhotoSequenceSearchScope,
    cross_axis_plan: PhotoApertureCrossAxisPlan,
    count: int,
    dimensions: FrameDimensionPrior,
    maximum_assignment_evaluations: int,
    maximum_solution_alternatives: int,
) -> PhotoSequenceSolveResult | PhotoSequenceSolveUnavailable:
    if count <= 0:
        raise ValueError("photo sequence count must be positive")
    if min(
        maximum_assignment_evaluations,
        maximum_solution_alternatives,
    ) <= 0:
        raise ValueError("photo sequence solver budgets must be positive")
    cross_axis_hypotheses = cross_axis_plan.hypotheses
    if not cross_axis_hypotheses:
        return PhotoSequenceSolveUnavailable(
            PhotoSequenceSolveUnavailableReason.GEOMETRY_CONSTRAINTS,
            cross_axis_plan.assignment_evaluations,
        )
    expected_measurements = tuple(
        measurement.aperture_cross_axis
        for observation in observations
        for measurement in observation.cross_axis_measurements
    )
    if observations and (
        any(not observation.cross_axis_measurements for observation in observations)
        or set(expected_measurements) != set(cross_axis_hypotheses)
    ):
        raise ValueError(
            "photo sequence solver requires measurements for its cross-axis plan"
        )
    band_hypotheses: list[_BandSequenceHypothesis] = []
    band_evaluations = cross_axis_plan.assignment_evaluations
    band_budget_exhausted = cross_axis_plan.search_budget_exhausted
    for cross_axis in cross_axis_hypotheses if observations and count > 1 else ():
        remaining_band_budget = maximum_assignment_evaluations - band_evaluations
        if remaining_band_budget <= 0:
            band_budget_exhausted = True
            break
        hypotheses, evaluations, exhausted = _band_sequence_hypotheses(
            observations,
            search_scope,
            count,
            dimensions,
            cross_axis,
            remaining_band_budget,
            maximum_solution_alternatives,
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
            dimensions,
            count,
            remaining,
        )
    measured_budget = (
        maximum_assignment_evaluations
        - band_evaluations
        - separator_build_evaluations
    )
    measured_builds: tuple[_SequenceBuild, ...] = ()
    measured_evaluations = 0
    measured_budget_exhausted = False
    measured_search_dominated = any(
        _strictly_dominates_measured_only_search(build)
        for build in separator_builds
    )
    if measured_budget > 0 and not measured_search_dominated:
        (
            measured_builds,
            measured_evaluations,
            measured_budget_exhausted,
        ) = _measured_path_builds(
            search_scope,
            cross_axis_hypotheses,
            dimensions,
            count,
            measured_budget,
            maximum_solution_alternatives,
        )
    builds = (*separator_builds, *measured_builds)
    total_evaluations = (
        band_evaluations
        + separator_build_evaluations
        + measured_evaluations
    )
    budget_exhausted = bool(
        band_budget_exhausted
        or separator_build_budget_exhausted
        or measured_budget_exhausted
    )
    if not builds:
        return PhotoSequenceSolveUnavailable(
            PhotoSequenceSolveUnavailableReason.GEOMETRY_CONSTRAINTS,
            total_evaluations,
        )

    best_rank = max(build.rank for build in builds)
    best = tuple(build for build in builds if build.rank == best_rank)
    if len(best) > maximum_solution_alternatives:
        best = best[:maximum_solution_alternatives]
        budget_exhausted = True
    representative = min(
        best,
        key=lambda build: tuple(
            edge.position.midpoint
            for aperture in build.apertures
            for edge in (
                aperture.leading,
                aperture.trailing,
                aperture.top,
                aperture.bottom,
            )
        ),
    )
    return PhotoSequenceSolveResult(
        photo_apertures=representative.apertures,
        aperture_edge_assignments=representative.edge_assignments,
        separator_assignments=representative.separator_assignments,
        inter_photo_spacings=representative.spacings,
        photo_width_constraint_px=representative.photo_width_px,
        photo_height_constraint_px=representative.cross_axis.height_px,
        residuals=representative.residuals,
        assignment_consensus=_assignment_consensus(
            best,
            budget_exhausted=budget_exhausted,
        ),
        assignment_evaluations=total_evaluations,
        search_budget_exhausted=budget_exhausted,
    )
