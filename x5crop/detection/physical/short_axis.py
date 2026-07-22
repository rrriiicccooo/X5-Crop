from __future__ import annotations

from dataclasses import dataclass
import math

from ...domain import (
    BoundaryAxis,
    BoundaryKind,
    BoundaryPathFit,
    BoundarySide,
    EvidenceState,
    FrameDimensionPrior,
    FrameSequenceSearchScope,
    GrayBoundaryPathObservation,
    HolderBoundaryObservation,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PhysicalSearchFact,
    PhysicalSearchOutcome,
    PixelInterval,
    ShortAxisMeasurementSpan,
)


@dataclass(frozen=True)
class FrameWidthSearchHint:
    width_px: PixelInterval
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if self.width_px.minimum <= 0.0:
            raise ValueError("frame-width search hint must be positive")


@dataclass(frozen=True)
class SharedShortAxisPlan:
    top_photo_edge: GrayBoundaryPathObservation | None
    bottom_photo_edge: GrayBoundaryPathObservation | None
    span: ShortAxisMeasurementSpan | None
    search_outcome: PhysicalSearchOutcome
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        edges_observed = (
            self.top_photo_edge is not None
            and self.bottom_photo_edge is not None
        )
        if (self.top_photo_edge is None) != (self.bottom_photo_edge is None):
            raise ValueError("shared short axis requires both photo edges together")
        if self.span is not None and not edges_observed:
            raise ValueError("shared short-axis span requires both photo edges")
        if edges_observed:
            assert self.top_photo_edge is not None
            assert self.bottom_photo_edge is not None
            top = self.top_photo_edge
            bottom = self.bottom_photo_edge
            if (
                top.kind == BoundaryKind.EDGE_ADJACENT_TRANSITION
                or bottom.kind == BoundaryKind.EDGE_ADJACENT_TRANSITION
                or not _path_contacts_active_image(top, BoundarySide.TOP)
                or not _path_contacts_active_image(bottom, BoundarySide.BOTTOM)
            ):
                raise ValueError(
                    "shared short axis requires two qualified real-photo edges"
                )
            if bottom.position.minimum <= top.position.maximum:
                raise ValueError("shared short-axis photo edges must be ordered")
            expected_provenance = _span_provenance(top, bottom)
            if self.provenance != expected_provenance:
                raise ValueError(
                    "shared short-axis provenance must come from its photo edges"
                )
            if self.span is not None:
                expected_span = _inner_line_span(
                    top,
                    bottom,
                    expected_provenance,
                )
                if self.span != expected_span:
                    raise ValueError(
                        "shared short-axis span must be the two photo-side inner lines"
                    )
        resolved = self.span is not None
        solution_found = PhysicalSearchFact.SOLUTION_FOUND in self.search_outcome.facts
        if solution_found != resolved:
            raise ValueError("short-axis search facts must match resolved photo edges")
        if self.span is not None and self.span.provenance != self.provenance:
            raise ValueError("shared short-axis span must preserve plan provenance")

    @property
    def state(self) -> EvidenceState:
        return self.search_outcome.state

    @property
    def supports_safe_crop(self) -> bool:
        return self.span is not None

    @property
    def top(self) -> PixelInterval:
        if self.span is None:
            raise ValueError("unresolved shared short axis has no top edge")
        return self.span.top

    @property
    def bottom(self) -> PixelInterval:
        if self.span is None:
            raise ValueError("unresolved shared short axis has no bottom edge")
        return self.span.bottom

    @property
    def height_px(self) -> PixelInterval:
        if self.span is None:
            raise ValueError("unresolved shared short axis has no photo height")
        return self.span.height_px

    @property
    def uncertainty_px(self) -> float:
        return float(
            self.top.maximum
            - self.top.minimum
            + self.bottom.maximum
            - self.bottom.minimum
        )

    @property
    def measurement_span(self) -> ShortAxisMeasurementSpan:
        if self.span is None:
            raise ValueError("unresolved shared short axis has no measurement span")
        return self.span


def _path_contacts_active_image(
    path: GrayBoundaryPathObservation,
    side: BoundarySide,
) -> bool:
    if side not in {BoundarySide.TOP, BoundarySide.BOTTOM}:
        raise ValueError("photo-edge contact requires a short-axis boundary")
    if path.axis != BoundaryAxis.SHORT:
        return False
    if side == BoundarySide.TOP:
        outer = path.lower_appearance
        inner = path.upper_appearance
    else:
        outer = path.upper_appearance
        inner = path.lower_appearance
    return bool(
        inner.intensity_tail != outer.intensity_tail
        and inner.texture_median > outer.texture_median
        and inner.gradient_median > outer.gradient_median
        and inner.spatial_continuity > 0.0
    )


def _photo_edge_contrast(
    path: GrayBoundaryPathObservation,
    side: BoundarySide,
) -> float:
    if side == BoundarySide.TOP:
        outer = path.lower_appearance
        inner = path.upper_appearance
    else:
        outer = path.upper_appearance
        inner = path.lower_appearance
    return float(
        inner.texture_median
        - outer.texture_median
        + inner.gradient_median
        - outer.gradient_median
    )


def photo_edge_is_independent(
    path: GrayBoundaryPathObservation,
    side: BoundarySide,
    holder_boundary: HolderBoundaryObservation | None,
    *,
    minimum_intensity_contrast: float,
    minimum_holder_gap: float,
) -> bool:
    """Return whether one path is distinct evidence for a real photo edge."""
    thresholds = (minimum_intensity_contrast, minimum_holder_gap)
    if any(not math.isfinite(value) or value < 0.0 for value in thresholds):
        raise ValueError("photo-edge thresholds must be finite and non-negative")
    if not _path_contacts_active_image(path, side):
        return False
    if side == BoundarySide.TOP:
        outer = path.lower_appearance
        inner = path.upper_appearance
    elif side == BoundarySide.BOTTOM:
        outer = path.upper_appearance
        inner = path.lower_appearance
    else:
        raise ValueError("photo-edge independence requires a short-axis side")
    if (
        abs(inner.intensity_median - outer.intensity_median)
        < minimum_intensity_contrast
    ):
        return False
    if holder_boundary is None:
        return True
    if holder_boundary.side != side:
        raise ValueError("photo edge and holder boundary must use the same side")
    local_gaps = []
    for photo_sample in path.samples:
        for holder_path in holder_boundary.supporting_paths:
            for holder_sample in holder_path.samples:
                if photo_sample.orthogonal_interval.intersection(
                    holder_sample.orthogonal_interval
                ) is None:
                    continue
                local_gaps.append(
                    (
                        photo_sample.position.minimum
                        - holder_sample.position.maximum
                    )
                    if side == BoundarySide.TOP
                    else (
                        holder_sample.position.minimum
                        - photo_sample.position.maximum
                    )
                )
    return not local_gaps or min(local_gaps) >= minimum_holder_gap


def _photo_edge_pair_score(
    top: GrayBoundaryPathObservation,
    bottom: GrayBoundaryPathObservation,
) -> tuple[float, int, float, float]:
    top_fit = BoundaryPathFit(top)
    bottom_fit = BoundaryPathFit(bottom)
    common = top_fit.orthogonal_extent.intersection(bottom_fit.orthogonal_extent)
    common_support = 0.0 if common is None else common.maximum - common.minimum
    maximum_residual = max(
        top_fit.minimum_line.residual,
        top_fit.maximum_line.residual,
        bottom_fit.minimum_line.residual,
        bottom_fit.maximum_line.residual,
    )
    return (
        common_support,
        min(len(top.samples), len(bottom.samples)),
        _photo_edge_contrast(top, BoundarySide.TOP)
        + _photo_edge_contrast(bottom, BoundarySide.BOTTOM),
        -maximum_residual,
    )


def _same_photo_edge_pair(
    left: SharedShortAxisPlan,
    right: SharedShortAxisPlan,
) -> bool:
    if (
        left.top_photo_edge is None
        or left.bottom_photo_edge is None
        or right.top_photo_edge is None
        or right.bottom_photo_edge is None
    ):
        return False
    return bool(
        left.top_photo_edge.position.intersection(
            right.top_photo_edge.position
        )
        is not None
        and left.bottom_photo_edge.position.intersection(
            right.bottom_photo_edge.position
        )
        is not None
    )


def _span_provenance(
    top: GrayBoundaryPathObservation,
    bottom: GrayBoundaryPathObservation,
) -> MeasurementProvenance:
    paths = (top, bottom)
    anchors = tuple(path.provenance.observation_id for path in paths)
    dependencies = tuple(
        sorted(
            {
                dependency
                for path in paths
                for dependency in (
                    path.provenance.root_measurement,
                    *path.provenance.dependencies,
                )
                if dependency != MeasurementIdentity.PHOTO_EDGES
            },
            key=lambda item: item.value,
        )
    )
    return MeasurementProvenance(
        root_measurement=MeasurementIdentity.PHOTO_EDGES,
        observation_id=ObservationId(
            "shared_short_axis:photo_edges:" + ":".join(map(str, anchors))
        ),
        dependencies=dependencies,
        description="shared short axis from two real photo edges",
        boundary_anchors=anchors,
    )


def _inner_line_span(
    top: GrayBoundaryPathObservation,
    bottom: GrayBoundaryPathObservation,
    provenance: MeasurementProvenance,
) -> ShortAxisMeasurementSpan | None:
    top_fit = BoundaryPathFit(top)
    bottom_fit = BoundaryPathFit(bottom)
    common_extent = top_fit.orthogonal_extent.intersection(
        bottom_fit.orthogonal_extent
    )
    if common_extent is None:
        return None
    top_bounds = top_fit.maximum_line.bounds_within(common_extent)
    bottom_bounds = bottom_fit.minimum_line.bounds_within(common_extent)
    top_interval = PixelInterval(*top_bounds)
    bottom_interval = PixelInterval(*bottom_bounds)
    if bottom_interval.minimum <= top_interval.maximum:
        return None
    return ShortAxisMeasurementSpan(
        top=top_interval,
        bottom=bottom_interval,
        provenance=provenance,
    )


def shared_short_axis_plan(
    search_scope: FrameSequenceSearchScope,
) -> SharedShortAxisPlan:
    unavailable = SharedShortAxisPlan(
        top_photo_edge=None,
        bottom_photo_edge=None,
        span=None,
        search_outcome=PhysicalSearchOutcome(
            (PhysicalSearchFact.MEASUREMENTS_UNAVAILABLE,)
        ),
        provenance=search_scope.provenance,
    )
    paths = tuple(
        path
        for path in search_scope.raw_boundary_paths
        if path.axis == BoundaryAxis.SHORT
        and path.kind != BoundaryKind.EDGE_ADJACENT_TRANSITION
    )
    top_candidates = tuple(
        path
        for path in paths
        if _path_contacts_active_image(path, BoundarySide.TOP)
    )
    bottom_candidates = tuple(
        path
        for path in paths
        if _path_contacts_active_image(path, BoundarySide.BOTTOM)
    )
    scored = tuple(
        (
            _photo_edge_pair_score(top, bottom),
            shared_short_axis_from_photo_edges(top, bottom),
        )
        for top in top_candidates
        for bottom in bottom_candidates
        if bottom.position.minimum > top.position.maximum
    )
    if not scored:
        return unavailable
    plans = tuple(plan for _, plan in scored)
    if any(
        not _same_photo_edge_pair(left, right)
        for index, left in enumerate(plans)
        for right in plans[index + 1 :]
    ):
        return unavailable
    return max(
        scored,
        key=lambda item: (
            item[0],
            str(item[1].top_photo_edge.provenance.observation_id),
            str(item[1].bottom_photo_edge.provenance.observation_id),
        ),
    )[1]


def shared_short_axis_from_photo_edges(
    top: GrayBoundaryPathObservation,
    bottom: GrayBoundaryPathObservation,
) -> SharedShortAxisPlan:
    if (
        top.kind == BoundaryKind.EDGE_ADJACENT_TRANSITION
        or bottom.kind == BoundaryKind.EDGE_ADJACENT_TRANSITION
        or not _path_contacts_active_image(top, BoundarySide.TOP)
        or not _path_contacts_active_image(bottom, BoundarySide.BOTTOM)
    ):
        raise ValueError(
            "shared short axis requires two qualified real-photo edges"
        )
    provenance = _span_provenance(top, bottom)
    span = _inner_line_span(top, bottom, provenance)
    if span is None:
        return SharedShortAxisPlan(
            top_photo_edge=top,
            bottom_photo_edge=bottom,
            span=None,
            search_outcome=PhysicalSearchOutcome(
                (PhysicalSearchFact.MEASUREMENTS_UNAVAILABLE,)
            ),
            provenance=provenance,
        )
    return SharedShortAxisPlan(
        top_photo_edge=top,
        bottom_photo_edge=bottom,
        span=span,
        search_outcome=PhysicalSearchOutcome((PhysicalSearchFact.SOLUTION_FOUND,)),
        provenance=provenance,
    )


def frame_width_search_hint(
    shared_short_axis: SharedShortAxisPlan,
    dimensions: FrameDimensionPrior,
) -> FrameWidthSearchHint:
    if not shared_short_axis.supports_safe_crop:
        raise ValueError("frame-width hint requires a resolved shared short axis")
    provenance = MeasurementProvenance(
        root_measurement=MeasurementIdentity.FRAME_GEOMETRY,
        observation_id=ObservationId(
            "frame_width_search_hint:"
            f"{shared_short_axis.provenance.observation_id}:"
            f"{dimensions.provenance.observation_id}"
        ),
        dependencies=tuple(
            dict.fromkeys(
                dependency
                for dependency in (
                    shared_short_axis.provenance.root_measurement,
                    *shared_short_axis.provenance.dependencies,
                    dimensions.provenance.root_measurement,
                    *dimensions.provenance.dependencies,
                )
                if dependency != MeasurementIdentity.FRAME_GEOMETRY
            )
        ),
        description="shared photo short axis frame-width search hint",
        boundary_anchors=shared_short_axis.provenance.boundary_anchors,
    )
    return FrameWidthSearchHint(
        shared_short_axis.height_px.scaled(dimensions.aspect),
        provenance,
    )
