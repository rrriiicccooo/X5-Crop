from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor, isfinite

from ...domain import (
    BoundaryAxis,
    BoundaryPathFit,
    BoundarySide,
    EvidenceState,
    FrameDimensionPrior,
    GrayBoundaryPathObservation,
    InterPhotoBoundaryReference,
    InterPhotoSpacing,
    InterPhotoSpacingBasis,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PhotoAperture,
    PhotoApertureBoundaryResolution,
    PhotoApertureCrossAxisHypothesis,
    PhotoApertureEdgeAssignment,
    PhotoApertureEdgeSource,
    PhotoSequenceSearchScope,
    PhysicalSearchFact,
    PhysicalSearchOutcome,
    PixelInterval,
    SeparatorBandAssignment,
    SeparatorBandCrossAxisSupport,
    SeparatorBandObservation,
    SeparatorWidthConstraint,
    SeparatorCrossAxisMeasurement,
)
from ...image.content import ContentRegionObservation
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
    search_outcome: PhysicalSearchOutcome
    assignment_evaluations: int

    def __post_init__(self) -> None:
        if self.assignment_evaluations < 0:
            raise ValueError("assignment evaluation count cannot be negative")
        if PhysicalSearchFact.SOLUTION_FOUND not in self.search_outcome.facts:
            raise ValueError("photo sequence result requires a found solution")
        if self.photo_width_constraint_px.minimum <= 0.0:
            raise ValueError("photo width constraint must be positive")
        if self.photo_height_constraint_px.minimum <= 0.0:
            raise ValueError("photo height constraint must be positive")


@dataclass(frozen=True)
class PhotoSequenceSolveFailure:
    search_outcome: PhysicalSearchOutcome
    assignment_evaluations: int

    def __post_init__(self) -> None:
        if self.assignment_evaluations < 0:
            raise ValueError("assignment evaluation count cannot be negative")
        if PhysicalSearchFact.SOLUTION_FOUND in self.search_outcome.facts:
            raise ValueError("photo sequence failure cannot contain a solution")


@dataclass(frozen=True)
class PhotoApertureCrossAxisPlan:
    hypotheses: tuple[PhotoApertureCrossAxisHypothesis, ...]
    search_outcome: PhysicalSearchOutcome

    def __post_init__(self) -> None:
        solution_found = PhysicalSearchFact.SOLUTION_FOUND in self.search_outcome.facts
        if solution_found != bool(self.hypotheses):
            raise ValueError("cross-axis search facts must match its hypotheses")


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
    supports: tuple[SeparatorBandCrossAxisSupport, ...]
    band_edges: tuple[tuple[_EdgeConstraint, _EdgeConstraint], ...]
    cross_axis: PhotoApertureCrossAxisHypothesis
    photo_width_px: PixelInterval | None
    supported_band_count: int
    measurement_quality: float
    width_residual: float
    uncertainty_px: float


@dataclass(frozen=True)
class _SequenceBuildObjectives:
    uncorroborated_overlap_extent_px: float
    supported_separator_count: int
    internal_boundary_measurement_quality: float
    dimension_residual: float
    external_boundary_measurement_quality: float
    boundary_uncertainty_ratio: float

    def __post_init__(self) -> None:
        measurements = (
            self.uncorroborated_overlap_extent_px,
            self.internal_boundary_measurement_quality,
            self.dimension_residual,
            self.external_boundary_measurement_quality,
            self.boundary_uncertainty_ratio,
        )
        if any(not isfinite(value) or value < 0.0 for value in measurements):
            raise ValueError("sequence build objectives must be finite and non-negative")
        if self.supported_separator_count < 0:
            raise ValueError("supported separator count cannot be negative")

    def ranking_key(self) -> tuple[float, int, float, float, float, float]:
        return (
            -self.uncorroborated_overlap_extent_px,
            self.supported_separator_count,
            self.internal_boundary_measurement_quality,
            -self.dimension_residual,
            self.external_boundary_measurement_quality,
            -self.boundary_uncertainty_ratio,
        )


@dataclass(frozen=True)
class _SequenceBuild:
    apertures: tuple[PhotoAperture, ...]
    edge_assignments: tuple[PhotoApertureEdgeAssignment, ...]
    separator_assignments: tuple[SeparatorBandAssignment, ...]
    spacings: tuple[InterPhotoSpacing, ...]
    photo_width_px: PixelInterval
    cross_axis: PhotoApertureCrossAxisHypothesis
    residuals: SequenceResiduals
    objectives: _SequenceBuildObjectives


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


def _axis_paths(
    search_scope: PhotoSequenceSearchScope,
    axis: BoundaryAxis,
) -> tuple[GrayBoundaryPathObservation, ...]:
    paths = tuple(
        dict.fromkeys(
            path
            for path in search_scope.raw_boundary_paths
            if path.axis == axis
        )
    )
    holder_paths = {item.path for item in search_scope.holder_boundaries}
    ranked = sorted(
        paths,
        key=lambda path: (
            -(path in holder_paths),
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


def _interior_separator_supports(
    supports: tuple[SeparatorBandCrossAxisSupport, ...],
    search_scope: PhotoSequenceSearchScope,
) -> tuple[SeparatorBandCrossAxisSupport, ...]:
    holder = search_scope.holder_span.box
    return tuple(
        sorted(
            dict.fromkeys(
                support
                for support in supports
                if support.observation.start > float(holder.left)
                and support.observation.end < float(holder.right)
            ),
            key=lambda support: (
                support.observation.start,
                support.observation.end,
                support.observation.provenance.observation_id,
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
    ) -> tuple[float, float, float, float, float, float]:
        photo_width = _cross_axis_width_constraint(hypothesis, dimensions)
        nonoverlap_overrun = max(
            0.0,
            float(count) * photo_width.minimum - holder_long_extent,
        ) / max(MINIMUM_POSITIVE_PIXEL_EXTENT, holder_long_extent)
        calibrated_height = dimensions.calibrated_height_px
        calibrated_height_residual = (
            0.0
            if calibrated_height is None
            else _interval_distance(
                hypothesis.height_px,
                calibrated_height,
            )
            / max(MINIMUM_POSITIVE_PIXEL_EXTENT, calibrated_height.midpoint)
        )
        return (
            -nonoverlap_overrun,
            -calibrated_height_residual,
            hypothesis.measurement_quality,
            -hypothesis.uncertainty_px,
            -hypothesis.top_path.position.midpoint,
            -hypothesis.bottom_path.position.midpoint,
        )

    ranked = tuple(
        sorted(
            all_hypotheses,
            key=rank,
            reverse=True,
        )[:maximum_hypotheses]
    )
    budget_exhausted = bool(
        search_scope.measurement_budget_exhausted
        or len(all_hypotheses) > maximum_hypotheses
    )
    facts: list[PhysicalSearchFact] = []
    if ranked:
        facts.append(PhysicalSearchFact.SOLUTION_FOUND)
    if budget_exhausted:
        facts.append(PhysicalSearchFact.EXECUTION_BUDGET_EXHAUSTED)
    elif not ranked:
        facts.append(PhysicalSearchFact.MEASUREMENTS_UNAVAILABLE)
    return PhotoApertureCrossAxisPlan(
        ranked,
        PhysicalSearchOutcome(tuple(facts)),
    )


def _dimension_band_constraint(
    support: SeparatorBandCrossAxisSupport,
    cross_axis: PhotoApertureCrossAxisHypothesis,
) -> _EdgeConstraint:
    observation = support.observation
    measurement = support.measurement_for(cross_axis)
    return _EdgeConstraint(
        position=observation.interval,
        source=PhotoApertureEdgeSource.DIMENSION_HYPOTHESIS,
        state=EvidenceState.UNAVAILABLE,
        provenance=observation.provenance,
        separator=observation,
        separator_cross_axis=measurement,
    )


def _separator_band_edge_constraint(
    support: SeparatorBandCrossAxisSupport,
    cross_axis: PhotoApertureCrossAxisHypothesis,
    position: float,
) -> _EdgeConstraint:
    observation = support.observation
    return _EdgeConstraint(
        position=PixelInterval.exact(position),
        source=PhotoApertureEdgeSource.SEPARATOR_BAND_EDGE,
        state=EvidenceState.SUPPORTED,
        provenance=observation.provenance,
        separator=observation,
        separator_cross_axis=support.measurement_for(cross_axis),
    )


def _observed_band_edges(
    support: SeparatorBandCrossAxisSupport,
    cross_axis: PhotoApertureCrossAxisHypothesis,
) -> tuple[_EdgeConstraint, _EdgeConstraint]:
    observation = support.observation
    return (
        _separator_band_edge_constraint(
            support,
            cross_axis,
            observation.start,
        ),
        _separator_band_edge_constraint(
            support,
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


def _measured_path_edges(
    edges: tuple[_EdgeConstraint, _EdgeConstraint],
) -> bool:
    return all(
        edge.source == PhotoApertureEdgeSource.MEASURED_BOUNDARY_PATH
        for edge in edges
    )


def _path_associated_with_band(
    path: GrayBoundaryPathObservation,
    observation: SeparatorBandObservation,
) -> bool:
    return bool(
        path.position.intersects(observation.interval)
        and observation.start <= path.position.midpoint <= observation.end
    )


def _measured_path_pairs_within_band(
    observation: SeparatorBandObservation,
    paths: tuple[GrayBoundaryPathObservation, ...],
) -> tuple[tuple[_EdgeConstraint, _EdgeConstraint], ...]:
    contained = tuple(
        _external_constraint(path)
        for path in paths
        if _path_associated_with_band(path, observation)
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
    support: SeparatorBandCrossAxisSupport,
    cross_axis: PhotoApertureCrossAxisHypothesis,
    paths: tuple[GrayBoundaryPathObservation, ...],
    width_constraint: SeparatorWidthConstraint,
) -> tuple[tuple[_EdgeConstraint, _EdgeConstraint], ...]:
    observation = support.observation
    fallback = _dimension_band_constraint(support, cross_axis)
    measurement = support.measurement_for(cross_axis)
    measured_paths = _measured_path_pairs_within_band(observation, paths)
    if (
        measurement.state != EvidenceState.SUPPORTED
        or not width_constraint.permits(observation)
    ):
        return (*measured_paths, (fallback, fallback))
    return (
        _observed_band_edges(support, cross_axis),
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


def _band_edge_interpretation_is_admissible(
    band_index: int,
    supports: tuple[SeparatorBandCrossAxisSupport, ...],
    selected_edges: tuple[tuple[_EdgeConstraint, _EdgeConstraint], ...],
    cross_axis: PhotoApertureCrossAxisHypothesis,
    physical_width: PixelInterval,
) -> bool:
    support = supports[band_index]
    band = support.observation
    chosen = selected_edges[band_index]
    measurement = support.measurement_for(cross_axis)
    width_constraint = SeparatorWidthConstraint(physical_width)
    if (
        measurement.state != EvidenceState.SUPPORTED
        or _separator_band_edges(chosen)
        or _measured_path_edges(chosen)
        or not width_constraint.permits(band)
    ):
        return True
    observed = _observed_band_edges(support, cross_axis)
    neighbor_widths: list[PixelInterval | None] = []
    if band_index > 0:
        neighbor_widths.append(
            _width_between_bands(
                supports[band_index - 1].observation,
                band,
                selected_edges[band_index - 1],
                observed,
            )
        )
    if band_index + 1 < len(supports):
        neighbor_widths.append(
            _width_between_bands(
                band,
                supports[band_index + 1].observation,
                observed,
                selected_edges[band_index + 1],
            )
        )
    return any(
        width is None or not width.intersects(physical_width)
        for width in neighbor_widths
    )


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
                -supports[index].observation.start,
            ),
            reverse=True,
        )
    )


def _band_sequence_hypothesis(
    supports: tuple[SeparatorBandCrossAxisSupport, ...],
    band_edges: tuple[tuple[_EdgeConstraint, _EdgeConstraint], ...],
    cross_axis: PhotoApertureCrossAxisHypothesis,
    photo_width_px: PixelInterval,
    physical_width_px: PixelInterval,
) -> _BandSequenceHypothesis:
    return _BandSequenceHypothesis(
        supports=supports,
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
    supports: tuple[SeparatorBandCrossAxisSupport, ...],
    search_scope: PhotoSequenceSearchScope,
    long_paths: tuple[GrayBoundaryPathObservation, ...],
    count: int,
    dimensions: FrameDimensionPrior,
    cross_axis: PhotoApertureCrossAxisHypothesis,
    evaluation_budget: int,
    maximum_hypotheses: int,
) -> tuple[tuple[_BandSequenceHypothesis, ...], int, bool]:
    required = max(0, count - 1)
    interior = _interior_separator_supports(supports, search_scope)
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
    width_constraint = SeparatorWidthConstraint(physical_width)
    edge_options = tuple(
        _band_edge_options(item, cross_axis, long_paths, width_constraint)
        for item in interior
    )

    def search(
        start_index: int,
        selected_supports: tuple[SeparatorBandCrossAxisSupport, ...],
        selected_edges: tuple[tuple[_EdgeConstraint, _EdgeConstraint], ...],
    ) -> None:
        nonlocal evaluations, search_truncated
        if search_truncated:
            return
        if len(selected_supports) == required:
            if not all(
                _band_edge_interpretation_is_admissible(
                    band_index,
                    selected_supports,
                    selected_edges,
                    cross_axis,
                    physical_width,
                )
                for band_index in range(len(selected_supports))
            ):
                return
            hypothesis = _band_sequence_hypothesis(
                selected_supports,
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
                    if (
                        measured_width is None
                        or not measured_width.intersects(physical_width)
                    ):
                        continue
                next_supports = (*selected_supports, support)
                next_edges = (*selected_edges, edges)
                resolved_neighbor_index = len(selected_supports) - 1
                if (
                    selected_supports
                    and not _band_edge_interpretation_is_admissible(
                        resolved_neighbor_index,
                        next_supports,
                        next_edges,
                        cross_axis,
                        physical_width,
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


def _admissible_aperture_endpoints(
    paths: tuple[GrayBoundaryPathObservation, ...],
    inner: _EdgeConstraint,
    photo_width: PixelInterval,
    holder_boundary_provenance: MeasurementProvenance | None,
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
        if residual > 0.0 and constraint.provenance != holder_boundary_provenance:
            continue
        rank = (
            -float(residual),
            min(visible.midpoint, photo_width.midpoint),
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
    path_fit: BoundaryPathFit,
    long_axis_interval: PixelInterval,
) -> tuple[
    PhotoApertureBoundaryResolution,
    PhotoApertureEdgeAssignment,
] | None:
    path = path_fit.observation
    position = path_fit.position_within(long_axis_interval)
    if position is None:
        return None
    resolution = PhotoApertureBoundaryResolution(
        photo_index=photo_index,
        side=side,
        position=position,
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
    long_paths: tuple[GrayBoundaryPathObservation, ...],
    cross_axis: PhotoApertureCrossAxisHypothesis,
    dimensions: FrameDimensionPrior,
    excluded_separator_bands: tuple[SeparatorBandObservation, ...],
    evaluation_budget: int,
    maximum_options: int,
) -> tuple[tuple[_MeasuredApertureConstraint, ...], int, bool]:
    photo_width = _cross_axis_width_constraint(cross_axis, dimensions)
    paths = tuple(
        path
        for path in long_paths
        if not any(
            _path_associated_with_band(path, observation)
            for observation in excluded_separator_bands
        )
    )
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
            if len(constraints) > maximum_options:
                return tuple(constraints[:maximum_options]), evaluations, True
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
        observation_id=ObservationId(
            f"inter_photo_spacing:{boundary_index}:"
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
            "measured inter-photo spacing"
            if observed
            else "inter-photo spacing hypothesis"
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


def _measured_sequence_build(
    constraints: tuple[_MeasuredApertureConstraint, ...],
    cross_axis: PhotoApertureCrossAxisHypothesis,
    path_fits: dict[ObservationId, BoundaryPathFit],
    photo_width: PixelInterval,
    holder_extent: int,
) -> _SequenceBuild | None:
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
        long_axis_interval = PixelInterval(
            leading.position.minimum,
            trailing.position.maximum,
        )
        top_result = _short_axis_resolution(
            photo_index,
            BoundarySide.TOP,
            path_fits[cross_axis.top_path.provenance.observation_id],
            long_axis_interval,
        )
        bottom_result = _short_axis_resolution(
            photo_index,
            BoundarySide.BOTTOM,
            path_fits[cross_axis.bottom_path.provenance.observation_id],
            long_axis_interval,
        )
        if top_result is None or bottom_result is None:
            return None
        top, top_assignment = top_result
        bottom, bottom_assignment = bottom_result
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
        boundary_uncertainty=uncertainty_px
        / max(MINIMUM_POSITIVE_PIXEL_EXTENT, float(holder_extent)),
    )
    internal_boundary_quality = sum(
        left.trailing.measurement_quality + right.leading.measurement_quality
        for left, right in zip(constraints, constraints[1:])
    )
    external_boundary_quality = (
        constraints[0].leading.measurement_quality
        + constraints[-1].trailing.measurement_quality
        + cross_axis.measurement_quality
    )
    return _SequenceBuild(
        apertures=tuple(apertures),
        edge_assignments=tuple(assignments),
        separator_assignments=(),
        spacings=spacings,
        photo_width_px=photo_width,
        cross_axis=cross_axis,
        residuals=residuals,
        objectives=_SequenceBuildObjectives(
            uncorroborated_overlap_extent_px=_uncorroborated_overlap_extent(spacings),
            supported_separator_count=0,
            internal_boundary_measurement_quality=internal_boundary_quality,
            dimension_residual=dimension_residual,
            external_boundary_measurement_quality=external_boundary_quality,
            boundary_uncertainty_ratio=residuals.boundary_uncertainty,
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
    long_paths: tuple[GrayBoundaryPathObservation, ...],
    path_fits: dict[ObservationId, BoundaryPathFit],
    separator_supports: tuple[SeparatorBandCrossAxisSupport, ...],
    cross_axis_hypotheses: tuple[PhotoApertureCrossAxisHypothesis, ...],
    dimensions: FrameDimensionPrior,
    count: int,
    evaluation_budget: int,
    maximum_solution_alternatives: int,
) -> tuple[tuple[_SequenceBuild, ...], int, bool]:
    holder = search_scope.holder_span.box
    excluded_separator_bands = tuple(
        support.observation
        for support in _interior_separator_supports(
            separator_supports,
            search_scope,
        )
    )
    builds: list[_SequenceBuild] = []
    evaluations = 0
    search_truncated = False
    for cross_axis_index, cross_axis in enumerate(cross_axis_hypotheses):
        remaining = evaluation_budget - evaluations
        if remaining <= 0:
            return tuple(builds), evaluations, True
        options, option_evaluations, exhausted = _measured_aperture_constraints(
            search_scope,
            long_paths,
            cross_axis,
            dimensions,
            excluded_separator_bands,
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
        measured_builds = tuple(
            build
            for state in states
            if (
                build := _measured_sequence_build(
                    state,
                    cross_axis,
                    path_fits,
                    photo_width,
                    holder.width + holder.height,
                )
            )
            is not None
        )
        builds.extend(measured_builds)
        if evaluations >= evaluation_budget:
            search_truncated = bool(
                search_truncated
                or cross_axis_index + 1 < len(cross_axis_hypotheses)
            )
            break
    return tuple(builds), evaluations, search_truncated


def _spacing_for_band(
    boundary_index: int,
    support: SeparatorBandCrossAxisSupport,
    cross_axis: PhotoApertureCrossAxisHypothesis,
    trailing: PhotoApertureBoundaryResolution,
    leading: PhotoApertureBoundaryResolution,
    width_constraint: SeparatorWidthConstraint,
) -> tuple[InterPhotoSpacing, SeparatorBandAssignment | None]:
    band = support.observation
    measurement = support.measurement_for(cross_axis)
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
            width_constraint,
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
            root_measurement=MeasurementIdentity.FRAME_GEOMETRY,
            observation_id=ObservationId(
                f"dimension_spacing:{boundary_index}:"
                f"{trailing.provenance.observation_id}:"
                f"{leading.provenance.observation_id}"
            ),
            dependencies=tuple(
                dict.fromkeys(
                    (
                        MeasurementIdentity.FRAME_DIMENSIONS,
                        band.provenance.root_measurement,
                    )
                )
            ),
            description="dimension-constrained inter-photo spacing",
            boundary_anchors=tuple(
                dict.fromkeys(
                    (
                        trailing.provenance.observation_id,
                        leading.provenance.observation_id,
                    )
                )
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
    path_fits: dict[ObservationId, BoundaryPathFit],
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
        long_axis_interval = PixelInterval(
            leading.position.minimum,
            trailing.position.maximum,
        )
        top_result = _short_axis_resolution(
            photo_index,
            BoundarySide.TOP,
            path_fits[cross_axis.top_path.provenance.observation_id],
            long_axis_interval,
        )
        bottom_result = _short_axis_resolution(
            photo_index,
            BoundarySide.BOTTOM,
            path_fits[cross_axis.bottom_path.provenance.observation_id],
            long_axis_interval,
        )
        if top_result is None or bottom_result is None:
            return None
        top, top_assignment = top_result
        bottom, bottom_assignment = bottom_result
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
    width_constraint = SeparatorWidthConstraint(photo_width)
    for boundary_index, support in enumerate(band_hypothesis.supports, start=1):
        signed_width = apertures[boundary_index].leading.position.minus(
            apertures[boundary_index - 1].trailing.position
        )
        if signed_width.maximum < 0.0:
            return None
        spacing, assignment = _spacing_for_band(
            boundary_index,
            support,
            cross_axis,
            apertures[boundary_index - 1].trailing,
            apertures[boundary_index].leading,
            width_constraint,
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
        boundary_uncertainty=float(uncertainty_px)
        / max(MINIMUM_POSITIVE_PIXEL_EXTENT, float(holder_extent)),
    )
    endpoint_quality = (
        leading_endpoint.measurement_quality + trailing_endpoint.measurement_quality
    )
    return _SequenceBuild(
        apertures=tuple(apertures),
        edge_assignments=tuple(assignments),
        separator_assignments=tuple(separator_assignments),
        spacings=tuple(spacings),
        photo_width_px=photo_width,
        cross_axis=cross_axis,
        residuals=residuals,
        objectives=_SequenceBuildObjectives(
            uncorroborated_overlap_extent_px=_uncorroborated_overlap_extent(
                tuple(spacings)
            ),
            supported_separator_count=band_hypothesis.supported_band_count,
            internal_boundary_measurement_quality=(
                band_hypothesis.measurement_quality
            ),
            dimension_residual=float(
                max(band_hypothesis.width_residual, cross_axis_residual)
            ),
            external_boundary_measurement_quality=(
                endpoint_quality + cross_axis.measurement_quality
            ),
            boundary_uncertainty_ratio=float(residuals.boundary_uncertainty),
        ),
    )


def _builds_for_hypotheses(
    band_hypotheses: tuple[_BandSequenceHypothesis, ...],
    search_scope: PhotoSequenceSearchScope,
    long_paths: tuple[GrayBoundaryPathObservation, ...],
    path_fits: dict[ObservationId, BoundaryPathFit],
    dimensions: FrameDimensionPrior,
    count: int,
    evaluation_budget: int,
) -> tuple[tuple[_SequenceBuild, ...], int, bool]:
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
        if band_hypothesis.supports:
            first_edges = band_hypothesis.band_edges[0]
            last_edges = band_hypothesis.band_edges[-1]
            leading_options = _admissible_aperture_endpoints(
                long_paths,
                first_edges[0],
                photo_width,
                holder_boundary_provenance.get(BoundarySide.LEADING),
                leading=True,
            )
            trailing_options = _admissible_aperture_endpoints(
                long_paths,
                last_edges[1],
                photo_width,
                holder_boundary_provenance.get(BoundarySide.TRAILING),
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
                if not band_hypothesis.supports:
                    visible = _visible_width(leading_endpoint, trailing_endpoint)
                    if visible is None or not visible.intersects(photo_width):
                        continue
                build = _build_sequence(
                    band_hypothesis,
                    cross_axis,
                    path_fits,
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
    conflicts: list[int] = []
    for photo_index in range(1, len(reference.apertures) + 1):
        apertures = tuple(build.apertures[photo_index - 1] for build in builds)
        edges = tuple(
            (
                aperture.leading.position,
                aperture.trailing.position,
                aperture.top.position,
                aperture.bottom.position,
            )
            for aperture in apertures
        )
        if any(
            PixelInterval.common_intersection(tuple(intervals)) is None
            for intervals in zip(*edges, strict=True)
        ):
            conflicts.append(photo_index)
    return tuple(conflicts)


def _build_apertures_refine(
    left: _SequenceBuild,
    right: _SequenceBuild,
) -> bool:
    if len(left.apertures) != len(right.apertures):
        return False
    for left_aperture, right_aperture in zip(
        left.apertures,
        right.apertures,
        strict=True,
    ):
        for side in (
            BoundarySide.LEADING,
            BoundarySide.TRAILING,
            BoundarySide.TOP,
            BoundarySide.BOTTOM,
        ):
            left_position = getattr(left_aperture, side.value).position
            right_position = getattr(right_aperture, side.value).position
            if not (
                left_position.minimum >= right_position.minimum
                and left_position.maximum <= right_position.maximum
            ):
                return False
    return True


def _build_dominates(left: _SequenceBuild, right: _SequenceBuild) -> bool:
    comparisons = tuple(
        left_value - right_value
        for left_value, right_value in zip(
            left.objectives.ranking_key(),
            right.objectives.ranking_key(),
            strict=True,
        )
    )
    if not (
        all(value >= 0.0 for value in comparisons)
        and any(value > 0.0 for value in comparisons)
    ):
        return False
    return _build_apertures_refine(left, right)


def _non_dominated_builds(
    builds: tuple[_SequenceBuild, ...],
) -> tuple[_SequenceBuild, ...]:
    frontier: list[_SequenceBuild] = []
    for build in builds:
        if any(_build_dominates(other, build) for other in frontier):
            continue
        frontier = [
            other
            for other in frontier
            if not _build_dominates(build, other)
        ]
        frontier.append(build)
    return tuple(frontier)


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


def _build_preserves_visible_content(
    build: _SequenceBuild,
    visible_content: ContentRegionObservation,
) -> bool:
    intervals = tuple(
        (
            max(
                visible_content.region.left,
                int(floor(aperture.leading.position.minimum)),
            ),
            min(
                visible_content.region.right,
                int(ceil(aperture.trailing.position.maximum)),
            ),
        )
        for aperture in build.apertures
    )
    if any(end <= start for start, end in intervals):
        return False
    return not visible_content.uncovered_by(intervals)


def solve_photo_sequence(
    supports: tuple[SeparatorBandCrossAxisSupport, ...],
    search_scope: PhotoSequenceSearchScope,
    cross_axis_plan: PhotoApertureCrossAxisPlan,
    count: int,
    dimensions: FrameDimensionPrior,
    visible_content: ContentRegionObservation,
    maximum_assignment_evaluations: int,
    maximum_solution_alternatives: int,
) -> PhotoSequenceSolveResult | PhotoSequenceSolveFailure:
    if count <= 0:
        raise ValueError("photo sequence count must be positive")
    if min(
        maximum_assignment_evaluations,
        maximum_solution_alternatives,
    ) <= 0:
        raise ValueError("photo sequence solver budgets must be positive")
    cross_axis_hypotheses = cross_axis_plan.hypotheses
    if not cross_axis_hypotheses:
        return PhotoSequenceSolveFailure(cross_axis_plan.search_outcome, 0)
    expected_measurements = tuple(
        measurement.aperture_cross_axis
        for support in supports
        for measurement in support.measurements
    )
    if supports and (
        any(not support.measurements for support in supports)
        or set(expected_measurements) != set(cross_axis_hypotheses)
    ):
        raise ValueError(
            "photo sequence solver requires measurements for its cross-axis plan"
        )
    path_fits = _boundary_path_fits(
        tuple(
            path
            for cross_axis in cross_axis_hypotheses
            for path in (cross_axis.top_path, cross_axis.bottom_path)
        )
    )
    long_paths = _axis_paths(search_scope, BoundaryAxis.LONG)
    band_hypotheses: list[_BandSequenceHypothesis] = []
    band_evaluations = 0
    band_budget_exhausted = cross_axis_plan.search_outcome.budget_exhausted
    for cross_axis in cross_axis_hypotheses if supports and count > 1 else ():
        remaining_band_budget = maximum_assignment_evaluations - band_evaluations
        if remaining_band_budget <= 0:
            band_budget_exhausted = True
            break
        hypotheses, evaluations, exhausted = _band_sequence_hypotheses(
            supports,
            search_scope,
            long_paths,
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
            long_paths,
            path_fits,
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
    if measured_budget > 0:
        (
            measured_builds,
            measured_evaluations,
            measured_budget_exhausted,
        ) = _measured_path_builds(
            search_scope,
            long_paths,
            path_fits,
            supports,
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
        return PhotoSequenceSolveFailure(
            PhysicalSearchOutcome(
                (
                    PhysicalSearchFact.EXECUTION_BUDGET_EXHAUSTED
                    if budget_exhausted
                    else PhysicalSearchFact.CONSTRAINTS_CONTRADICTED,
                ),
            ),
            total_evaluations,
        )

    content_preserving_builds = tuple(
        build
        for build in builds
        if _build_preserves_visible_content(build, visible_content)
    )
    if content_preserving_builds:
        builds = content_preserving_builds

    non_dominated = _non_dominated_builds(builds)
    best_objectives = max(
        build.objectives.ranking_key() for build in non_dominated
    )
    best = tuple(
        build
        for build in non_dominated
        if build.objectives.ranking_key() == best_objectives
    )
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
            non_dominated,
            budget_exhausted=budget_exhausted,
        ),
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
