from __future__ import annotations

from dataclasses import dataclass

from ...domain import (
    BoundaryAxis,
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
)
from .model import (
    FrameWidthSearchHint,
    PhotoHeightEvidence,
    SharedShortAxisBasis,
    SharedShortAxisSafetySpan,
)


@dataclass(frozen=True)
class SharedShortAxisPlan:
    span: SharedShortAxisSafetySpan
    photo_height_evidence: PhotoHeightEvidence
    search_outcome: PhysicalSearchOutcome

    def __post_init__(self) -> None:
        solution_found = (
            PhysicalSearchFact.SOLUTION_FOUND in self.search_outcome.facts
        )
        if solution_found != self.span.supports_safe_crop:
            raise ValueError("short-axis search facts must match its span")


def _span_provenance(
    basis: SharedShortAxisBasis,
    paths: tuple[GrayBoundaryPathObservation, ...],
    *,
    canvas_sides: tuple[BoundarySide, ...] = (),
) -> MeasurementProvenance:
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
                if dependency != MeasurementIdentity.BOUNDARY_PATHS
            }
            | ({MeasurementIdentity.CANVAS} if canvas_sides else set()),
            key=lambda item: item.value,
        )
    )
    canvas_identity = ":".join(side.value for side in canvas_sides)
    return MeasurementProvenance(
        root_measurement=MeasurementIdentity.BOUNDARY_PATHS,
        observation_id=ObservationId(
            f"shared_short_axis:{basis.value}:"
            + ":".join(map(str, anchors))
            + (f":canvas:{canvas_identity}" if canvas_sides else "")
        ),
        dependencies=dependencies,
        description="shared strip short-axis crop span",
        boundary_anchors=anchors,
    )


def resolve_shared_short_axis(
    search_scope: FrameSequenceSearchScope,
) -> SharedShortAxisSafetySpan:
    by_side = {
        boundary.side: boundary
        for boundary in search_scope.holder_safety.boundaries
    }
    top_holder = by_side.get(BoundarySide.TOP)
    bottom_holder = by_side.get(BoundarySide.BOTTOM)
    canvas = search_scope.holder_safety.containment_fallback.box
    interval = search_scope.holder_safety.safe_axis_interval(BoundaryAxis.SHORT)
    contributors = tuple(
        boundary
        for boundary, coordinate in (
            (top_holder, interval.minimum),
            (bottom_holder, interval.maximum),
        )
        if boundary is not None
        and coordinate
        in {boundary.position.minimum, boundary.position.maximum}
    )
    if contributors:
        top = (
            top_holder.position
            if top_holder in contributors
            else PixelInterval.exact(float(canvas.top))
        )
        bottom = (
            bottom_holder.position
            if bottom_holder in contributors
            else PixelInterval.exact(float(canvas.bottom))
        )
        paths = tuple(
            path
            for boundary in contributors
            for path in boundary.supporting_paths
        )
        canvas_sides = tuple(
            side
            for side, boundary in (
                (BoundarySide.TOP, top_holder),
                (BoundarySide.BOTTOM, bottom_holder),
            )
            if boundary not in contributors
        )
        basis = (
            SharedShortAxisBasis.PHOTO_EDGE_BOUNDED
            if _holder_boundaries_contact_active_image(search_scope)
            else SharedShortAxisBasis.HOLDER_EDGE_BOUNDED
        )
        return SharedShortAxisSafetySpan(
            top=top,
            bottom=bottom,
            basis=basis,
            state=EvidenceState.SUPPORTED,
            provenance=_span_provenance(
                basis,
                paths,
                canvas_sides=canvas_sides,
            ),
        )

    return SharedShortAxisSafetySpan(
        top=PixelInterval.exact(float(canvas.top)),
        bottom=PixelInterval.exact(float(canvas.bottom)),
        basis=SharedShortAxisBasis.CONTAINMENT_FALLBACK,
        state=EvidenceState.UNAVAILABLE,
        provenance=search_scope.holder_safety.containment_fallback.provenance,
    )


def resolve_photo_height_evidence(
    search_scope: FrameSequenceSearchScope,
) -> PhotoHeightEvidence:
    by_side = {
        boundary.side: boundary
        for boundary in search_scope.holder_safety.boundaries
    }
    top = by_side.get(BoundarySide.TOP)
    bottom = by_side.get(BoundarySide.BOTTOM)
    if (
        top is not None
        and bottom is not None
        and _holder_boundary_contacts_active_image(top)
        and _holder_boundary_contacts_active_image(bottom)
    ):
        height = bottom.position.minus(top.position)
        if height.minimum > 0.0:
            paths = (*top.supporting_paths, *bottom.supporting_paths)
            anchors = tuple(
                path.provenance.observation_id for path in paths
            )
            return PhotoHeightEvidence(
                height_px=height,
                state=EvidenceState.SUPPORTED,
                provenance=MeasurementProvenance(
                    root_measurement=MeasurementIdentity.PHOTO_EDGES,
                    observation_id=ObservationId(
                        "photo_height:holder_contact:"
                        + ":".join(map(str, anchors))
                    ),
                    dependencies=(MeasurementIdentity.BOUNDARY_PATHS,),
                    description=(
                        "photo height from two holder-to-active-image contacts"
                    ),
                    boundary_anchors=anchors,
                ),
            )
    return PhotoHeightEvidence(
        height_px=None,
        state=EvidenceState.UNAVAILABLE,
        provenance=search_scope.holder_safety.provenance,
    )


def _holder_boundary_contacts_active_image(
    boundary: HolderBoundaryObservation,
) -> bool:
    if boundary.side not in {BoundarySide.TOP, BoundarySide.BOTTOM}:
        raise ValueError("photo-height contact requires a short-axis boundary")
    for path in boundary.supporting_paths:
        if boundary.side == BoundarySide.TOP:
            outer = path.lower_appearance
            inner = path.upper_appearance
        else:
            outer = path.upper_appearance
            inner = path.lower_appearance
        if not (
            inner.intensity_tail != outer.intensity_tail
            and inner.texture_median > outer.texture_median
            and inner.gradient_median > outer.gradient_median
        ):
            return False
    return bool(boundary.supporting_paths)


def _holder_boundaries_contact_active_image(
    search_scope: FrameSequenceSearchScope,
) -> bool:
    top = search_scope.holder_safety.boundary(BoundarySide.TOP)
    bottom = search_scope.holder_safety.boundary(BoundarySide.BOTTOM)
    return bool(
        top is not None
        and bottom is not None
        and _holder_boundary_contacts_active_image(top)
        and _holder_boundary_contacts_active_image(bottom)
    )


def frame_width_search_hint(
    safety_span: SharedShortAxisSafetySpan,
    dimensions: FrameDimensionPrior,
) -> FrameWidthSearchHint:
    provenance = MeasurementProvenance(
        root_measurement=MeasurementIdentity.FRAME_GEOMETRY,
        observation_id=ObservationId(
            "frame_width_search_hint:"
            f"{safety_span.provenance.observation_id}:"
            f"{dimensions.provenance.observation_id}"
        ),
        dependencies=tuple(
            dict.fromkeys(
                dependency
                for dependency in (
                    safety_span.provenance.root_measurement,
                    *safety_span.provenance.dependencies,
                    dimensions.provenance.root_measurement,
                    *dimensions.provenance.dependencies,
                )
                if dependency != MeasurementIdentity.FRAME_GEOMETRY
            )
        ),
        description="short-axis safety span frame-width search hint",
        boundary_anchors=safety_span.provenance.boundary_anchors,
    )
    return FrameWidthSearchHint(
        safety_span.height_px.scaled(dimensions.aspect),
        provenance,
    )


def shared_short_axis_plan(
    search_scope: FrameSequenceSearchScope,
) -> SharedShortAxisPlan:
    photo_height = resolve_photo_height_evidence(search_scope)
    span = resolve_shared_short_axis(search_scope)
    search_fact = (
        PhysicalSearchFact.SOLUTION_FOUND
        if span.supports_safe_crop
        else PhysicalSearchFact.MEASUREMENTS_UNAVAILABLE
    )
    return SharedShortAxisPlan(
        span=span,
        photo_height_evidence=photo_height,
        search_outcome=PhysicalSearchOutcome((search_fact,)),
    )
