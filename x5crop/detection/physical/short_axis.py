from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from ...configuration.photo_edges import PhotoEdgeDetectionParameters
from ...domain import (
    BoundarySide,
    EvidenceState,
    FrameDimensionPrior,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PhysicalSearchFact,
    PhysicalSearchOutcome,
    PixelInterval,
    ShortAxisMeasurementSpan,
)
from ..evidence.photo_edges import (
    PhotoEdgePairEvidence,
    photo_edge_inner_line,
)


@dataclass(frozen=True)
class FrameWidthSearchHint:
    width_px: PixelInterval
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if self.width_px.minimum <= 0.0:
            raise ValueError("frame-width search hint must be positive")


class SharedShortAxisOutcome(str, Enum):
    SUPPORTED = "supported"
    PHOTO_EDGE_PAIR_UNAVAILABLE = "photo_edge_pair_unavailable"
    EXTRAPOLATION_UNCERTAINTY_TOO_LARGE = (
        "extrapolation_uncertainty_too_large"
    )
    MAPPED_GEOMETRY_CONTRADICTED = "mapped_geometry_contradicted"


@dataclass(frozen=True)
class SharedShortAxisPlan:
    photo_edge_pair_id: ObservationId
    span: ShortAxisMeasurementSpan | None
    outcome: SharedShortAxisOutcome
    position_uncertainty_px: float | None
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if not isinstance(self.photo_edge_pair_id, ObservationId):
            raise TypeError("shared short axis requires a photo-edge evidence identity")
        if not isinstance(self.outcome, SharedShortAxisOutcome):
            raise TypeError("shared short axis requires a typed consumer outcome")
        supported = self.outcome == SharedShortAxisOutcome.SUPPORTED
        if supported != (self.span is not None):
            raise ValueError("shared short-axis outcome must match span availability")
        if supported != (self.position_uncertainty_px is not None):
            raise ValueError(
                "shared short-axis uncertainty must match span availability"
            )
        if self.position_uncertainty_px is not None and (
            not math.isfinite(self.position_uncertainty_px)
            or self.position_uncertainty_px < 0.0
        ):
            raise ValueError("shared short-axis uncertainty must be finite")
        if self.span is not None and self.span.provenance != self.provenance:
            raise ValueError("shared short-axis span must preserve plan provenance")
        if self.provenance.root_measurement != MeasurementIdentity.PHOTO_EDGES:
            raise ValueError("shared short axis must derive from photo-edge evidence")

    @property
    def state(self) -> EvidenceState:
        if self.outcome == SharedShortAxisOutcome.SUPPORTED:
            return EvidenceState.SUPPORTED
        if self.outcome in {
            SharedShortAxisOutcome.PHOTO_EDGE_PAIR_UNAVAILABLE,
            SharedShortAxisOutcome.EXTRAPOLATION_UNCERTAINTY_TOO_LARGE,
        }:
            return EvidenceState.UNAVAILABLE
        return EvidenceState.CONTRADICTED

    @property
    def physical_search(self) -> PhysicalSearchOutcome:
        return PhysicalSearchOutcome(
            (
                PhysicalSearchFact.SOLUTION_FOUND
                if self.state == EvidenceState.SUPPORTED
                else (
                    PhysicalSearchFact.MEASUREMENTS_UNAVAILABLE
                    if self.state == EvidenceState.UNAVAILABLE
                    else PhysicalSearchFact.CONSTRAINTS_CONTRADICTED
                ),
            )
        )

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
        if self.position_uncertainty_px is None:
            raise ValueError("unresolved shared short axis has no uncertainty")
        return self.position_uncertainty_px

    @property
    def measurement_span(self) -> ShortAxisMeasurementSpan:
        if self.span is None:
            raise ValueError("unresolved shared short axis has no measurement span")
        return self.span


def _plan_provenance(
    evidence: PhotoEdgePairEvidence,
) -> MeasurementProvenance:
    selected = evidence.selected_candidates
    anchors = (
        ()
        if selected is None
        else tuple(
            candidate.path.provenance.observation_id
            for candidate in selected
        )
    )
    return MeasurementProvenance(
        root_measurement=MeasurementIdentity.PHOTO_EDGES,
        observation_id=ObservationId(
            f"shared_short_axis:{evidence.observation_id}"
        ),
        dependencies=tuple(
            dependency
            for dependency in evidence.provenance.dependencies
            if dependency != MeasurementIdentity.PHOTO_EDGES
        ),
        description="shared short axis derived from mapped photo-edge pair",
        boundary_anchors=anchors,
    )


def shared_short_axis_from_photo_edge_pair(
    evidence: PhotoEdgePairEvidence,
    workspace_long_axis_extent: int,
    parameters: PhotoEdgeDetectionParameters,
) -> SharedShortAxisPlan:
    if workspace_long_axis_extent <= 0:
        raise ValueError("shared short-axis projection requires a positive domain")
    provenance = _plan_provenance(evidence)
    if evidence.selected_candidates is None:
        return SharedShortAxisPlan(
            photo_edge_pair_id=evidence.observation_id,
            span=None,
            outcome=SharedShortAxisOutcome.PHOTO_EDGE_PAIR_UNAVAILABLE,
            position_uncertainty_px=None,
            provenance=provenance,
        )
    top_candidate, bottom_candidate = evidence.selected_candidates
    top_line = photo_edge_inner_line(top_candidate, side=BoundarySide.TOP)
    bottom_line = photo_edge_inner_line(
        bottom_candidate,
        side=BoundarySide.BOTTOM,
    )
    coordinates = (0.0, float(workspace_long_axis_extent))
    top_positions = tuple(
        top_line.position_interval_at(coordinate)
        for coordinate in coordinates
    )
    bottom_positions = tuple(
        bottom_line.position_interval_at(coordinate)
        for coordinate in coordinates
    )
    top = PixelInterval(
        min(item.minimum for item in top_positions),
        max(item.maximum for item in top_positions),
    )
    bottom = PixelInterval(
        min(item.minimum for item in bottom_positions),
        max(item.maximum for item in bottom_positions),
    )
    if bottom.minimum <= top.maximum:
        return SharedShortAxisPlan(
            photo_edge_pair_id=evidence.observation_id,
            span=None,
            outcome=SharedShortAxisOutcome.MAPPED_GEOMETRY_CONTRADICTED,
            position_uncertainty_px=None,
            provenance=provenance,
        )
    height = bottom.minus(top)
    uncertainty = (
        top.maximum
        - top.minimum
        + bottom.maximum
        - bottom.minimum
    )
    uncertainty_limit = max(
        parameters.shared_axis_uncertainty_floor_px,
        height.midpoint * parameters.maximum_shared_axis_uncertainty_ratio,
    )
    if uncertainty > uncertainty_limit:
        return SharedShortAxisPlan(
            photo_edge_pair_id=evidence.observation_id,
            span=None,
            outcome=(
                SharedShortAxisOutcome.EXTRAPOLATION_UNCERTAINTY_TOO_LARGE
            ),
            position_uncertainty_px=None,
            provenance=provenance,
        )
    span = ShortAxisMeasurementSpan(
        top=top,
        bottom=bottom,
        provenance=provenance,
    )
    return SharedShortAxisPlan(
        photo_edge_pair_id=evidence.observation_id,
        span=span,
        outcome=SharedShortAxisOutcome.SUPPORTED,
        position_uncertainty_px=uncertainty,
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
