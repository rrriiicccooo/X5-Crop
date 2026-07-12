from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ...domain import (
    BOUNDARY_SIDES,
    BoundaryKind,
    BoundaryObservation,
    BoundarySide,
    Box,
    CropEnvelope,
    EvidenceState,
    FrameBoundary,
    MeasurementIdentity,
    MeasurementProvenance,
    PixelInterval,
    VisibleSequenceSpan,
)


@dataclass(frozen=True)
class HolderOcclusionConstraint:
    leading_hidden_width_px: PixelInterval
    trailing_hidden_width_px: PixelInterval

    def __post_init__(self) -> None:
        if (
            self.leading_hidden_width_px.minimum < 0.0
            or self.trailing_hidden_width_px.minimum < 0.0
        ):
            raise ValueError("holder occlusion constraint cannot be negative")

    @property
    def combined_hidden_width_px(self) -> PixelInterval:
        return self.leading_hidden_width_px.plus(
            self.trailing_hidden_width_px
        )


def holder_occlusion_constraint(
    boundary_observations: tuple[BoundaryObservation, ...],
    frame_width_px: PixelInterval,
) -> HolderOcclusionConstraint:
    by_side = {
        observation.side: observation
        for observation in boundary_observations
        if observation.side in {BoundarySide.LEADING, BoundarySide.TRAILING}
    }
    maximum_hidden = frame_width_px.maximum

    def side_interval(side: BoundarySide) -> PixelInterval:
        observation = by_side.get(side)
        if (
            observation is None
            or observation.kind != BoundaryKind.WHITE_HOLDER_TRANSITION
        ):
            return PixelInterval.zero()
        return PixelInterval(0.0, maximum_hidden)

    return HolderOcclusionConstraint(
        side_interval(BoundarySide.LEADING),
        side_interval(BoundarySide.TRAILING),
    )


class HolderOcclusionSideOutcome(str, Enum):
    MEASUREMENT_UNAVAILABLE = "measurement_unavailable"
    NOT_WHITE_HOLDER = "not_white_holder"
    NO_FRAME_SHORTENING = "no_frame_shortening"
    SHORTENING_UNCERTAIN = "shortening_uncertain"
    OCCLUSION_SUPPORTED = "occlusion_supported"
    ALLOCATION_UNRESOLVED = "allocation_unresolved"


@dataclass(frozen=True)
class HolderOcclusionSideEvidence:
    side: BoundarySide
    outcome: HolderOcclusionSideOutcome
    hidden_width_px: PixelInterval
    boundary: BoundaryObservation | None
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)

    def __post_init__(self) -> None:
        if self.side not in {BoundarySide.LEADING, BoundarySide.TRAILING}:
            raise ValueError("holder occlusion side must be leading or trailing")
        if not isinstance(self.outcome, HolderOcclusionSideOutcome):
            raise TypeError("holder occlusion side requires a typed outcome")
        if self.hidden_width_px.minimum < 0.0:
            raise ValueError("holder occlusion width cannot be negative")
        if self.boundary is not None and self.boundary.side != self.side:
            raise ValueError("holder occlusion boundary must match its side")
        white_holder = bool(
            self.boundary is not None
            and self.boundary.kind == BoundaryKind.WHITE_HOLDER_TRANSITION
        )
        if self.outcome == HolderOcclusionSideOutcome.MEASUREMENT_UNAVAILABLE:
            if (
                self.hidden_width_px != PixelInterval.zero()
                or (self.boundary is not None and not white_holder)
            ):
                raise ValueError("unavailable occlusion has zero hidden width")
        elif self.outcome == HolderOcclusionSideOutcome.NOT_WHITE_HOLDER:
            if (
                self.hidden_width_px != PixelInterval.zero()
                or self.boundary is None
                or white_holder
            ):
                raise ValueError(
                    "non-white-holder outcome requires a measured non-white edge"
                )
        elif self.outcome == HolderOcclusionSideOutcome.NO_FRAME_SHORTENING:
            if self.hidden_width_px != PixelInterval.zero() or not white_holder:
                raise ValueError("unshortened frame requires a white-holder boundary")
        elif self.outcome == HolderOcclusionSideOutcome.SHORTENING_UNCERTAIN:
            if (
                not white_holder
                or self.hidden_width_px.minimum > 0.0
                or self.hidden_width_px.maximum <= 0.0
            ):
                raise ValueError(
                    "uncertain shortening requires a possible positive width"
                )
        elif self.outcome == HolderOcclusionSideOutcome.OCCLUSION_SUPPORTED:
            if not white_holder or self.hidden_width_px.minimum <= 0.0:
                raise ValueError(
                    "supported occlusion requires positive white-holder evidence"
                )
        elif (
            not white_holder
            or self.hidden_width_px.minimum != 0.0
            or self.hidden_width_px.maximum <= 0.0
        ):
            raise ValueError(
                "unresolved allocation requires a possible white-holder width"
            )
        state, reason = {
            HolderOcclusionSideOutcome.MEASUREMENT_UNAVAILABLE: (
                EvidenceState.UNAVAILABLE,
                "holder_occlusion_measurement_unavailable",
            ),
            HolderOcclusionSideOutcome.NOT_WHITE_HOLDER: (
                EvidenceState.NOT_APPLICABLE,
                "measured_edge_is_not_white_holder_occlusion",
            ),
            HolderOcclusionSideOutcome.NO_FRAME_SHORTENING: (
                EvidenceState.NOT_APPLICABLE,
                "white_holder_boundary_without_frame_shortening",
            ),
            HolderOcclusionSideOutcome.SHORTENING_UNCERTAIN: (
                EvidenceState.UNAVAILABLE,
                "edge_frame_shortening_uncertain",
            ),
            HolderOcclusionSideOutcome.OCCLUSION_SUPPORTED: (
                EvidenceState.SUPPORTED,
                "white_holder_occludes_edge_frame",
            ),
            HolderOcclusionSideOutcome.ALLOCATION_UNRESOLVED: (
                EvidenceState.UNAVAILABLE,
                "single_frame_occlusion_allocation_unresolved",
            ),
        }[self.outcome]
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "reason", reason)


@dataclass(frozen=True)
class HolderOcclusionEvidence:
    leading: HolderOcclusionSideEvidence
    trailing: HolderOcclusionSideEvidence
    unallocated_hidden_width_px: PixelInterval | None = None
    combined_hidden_width_px: PixelInterval = field(init=False)

    def __post_init__(self) -> None:
        if self.leading.side != "leading" or self.trailing.side != "trailing":
            raise ValueError("holder occlusion evidence requires ordered edge sides")
        side_total = self.leading.hidden_width_px.plus(
            self.trailing.hidden_width_px
        )
        if self.unallocated_hidden_width_px is not None:
            combined = self.unallocated_hidden_width_px
            if combined.minimum < 0.0:
                raise ValueError("unallocated holder occlusion cannot be negative")
            if (
                self.leading.outcome
                != HolderOcclusionSideOutcome.ALLOCATION_UNRESOLVED
                or self.trailing.outcome
                != HolderOcclusionSideOutcome.ALLOCATION_UNRESOLVED
                or self.leading.hidden_width_px.minimum != 0.0
                or self.trailing.hidden_width_px.minimum != 0.0
                or self.leading.hidden_width_px.maximum
                != combined.maximum
                or self.trailing.hidden_width_px.maximum
                != combined.maximum
            ):
                raise ValueError(
                    "unresolved edge allocation must preserve one total width"
                )
        else:
            combined = side_total
            if any(
                side.outcome == HolderOcclusionSideOutcome.ALLOCATION_UNRESOLVED
                for side in (self.leading, self.trailing)
            ):
                raise ValueError("unresolved edge allocation requires one total width")
        object.__setattr__(self, "combined_hidden_width_px", combined)

    @classmethod
    def unavailable(cls) -> "HolderOcclusionEvidence":
        return cls(
            _unavailable_side(BoundarySide.LEADING),
            _unavailable_side(BoundarySide.TRAILING),
        )


def visible_sequence_length_interval(
    visible_sequence_span: VisibleSequenceSpan,
    boundary_observations: tuple[BoundaryObservation, ...],
) -> PixelInterval:
    by_side = {
        observation.side: observation
        for observation in boundary_observations
        if observation.side in {BoundarySide.LEADING, BoundarySide.TRAILING}
    }
    if set(by_side) == {BoundarySide.LEADING, BoundarySide.TRAILING}:
        measured = by_side[BoundarySide.TRAILING].position.minus(
            by_side[BoundarySide.LEADING].position
        )
        if measured.maximum > 0.0:
            return PixelInterval(
                max(0.0, measured.minimum),
                measured.maximum,
            )
    return PixelInterval.exact(float(visible_sequence_span.box.width))


def _unavailable_side(side: BoundarySide) -> HolderOcclusionSideEvidence:
    return HolderOcclusionSideEvidence(
        side=side,
        outcome=HolderOcclusionSideOutcome.MEASUREMENT_UNAVAILABLE,
        hidden_width_px=PixelInterval.zero(),
        boundary=None,
    )


def _occlusion_side_evidence(
    side: BoundarySide,
    boundary: BoundaryObservation | None,
    visible_width: PixelInterval | None,
    frame_width: PixelInterval,
) -> HolderOcclusionSideEvidence:
    if boundary is None:
        return HolderOcclusionSideEvidence(
            side,
            HolderOcclusionSideOutcome.MEASUREMENT_UNAVAILABLE,
            PixelInterval.zero(),
            boundary,
        )
    if boundary.side != side:
        raise ValueError(f"{side} occlusion requires a {side} boundary")
    if boundary.kind != BoundaryKind.WHITE_HOLDER_TRANSITION:
        return HolderOcclusionSideEvidence(
            side,
            HolderOcclusionSideOutcome.NOT_WHITE_HOLDER,
            PixelInterval.zero(),
            boundary,
        )
    if visible_width is None:
        return HolderOcclusionSideEvidence(
            side,
            HolderOcclusionSideOutcome.MEASUREMENT_UNAVAILABLE,
            PixelInterval.zero(),
            boundary,
        )
    hidden = PixelInterval(
        max(0.0, frame_width.minimum - visible_width.maximum),
        max(0.0, frame_width.maximum - visible_width.minimum),
    )
    if hidden.maximum <= 0.0:
        return HolderOcclusionSideEvidence(
            side,
            HolderOcclusionSideOutcome.NO_FRAME_SHORTENING,
            PixelInterval.zero(),
            boundary,
        )
    if hidden.minimum <= 0.0:
        return HolderOcclusionSideEvidence(
            side,
            HolderOcclusionSideOutcome.SHORTENING_UNCERTAIN,
            hidden,
            boundary,
        )
    return HolderOcclusionSideEvidence(
        side,
        HolderOcclusionSideOutcome.OCCLUSION_SUPPORTED,
        hidden,
        boundary,
    )


def holder_occlusion_evidence(
    *,
    leading_boundary: BoundaryObservation | None,
    trailing_boundary: BoundaryObservation | None,
    leading_visible_frame_width: PixelInterval | None,
    trailing_visible_frame_width: PixelInterval | None,
    frame_width_px: PixelInterval,
) -> HolderOcclusionEvidence:
    leading = _occlusion_side_evidence(
        BoundarySide.LEADING,
        leading_boundary,
        leading_visible_frame_width,
        frame_width_px,
    )
    trailing = _occlusion_side_evidence(
        BoundarySide.TRAILING,
        trailing_boundary,
        trailing_visible_frame_width,
        frame_width_px,
    )
    return HolderOcclusionEvidence(
        leading=leading,
        trailing=trailing,
    )


def _single_frame_two_sided_occlusion(
    leading_boundary: BoundaryObservation,
    trailing_boundary: BoundaryObservation,
    visible_width: PixelInterval,
    frame_width: PixelInterval,
) -> HolderOcclusionEvidence | None:
    if (
        leading_boundary.kind != BoundaryKind.WHITE_HOLDER_TRANSITION
        or trailing_boundary.kind != BoundaryKind.WHITE_HOLDER_TRANSITION
    ):
        return None
    total_hidden = PixelInterval(
        max(0.0, frame_width.minimum - visible_width.maximum),
        max(0.0, frame_width.maximum - visible_width.minimum),
    )
    if total_hidden.maximum <= 0.0:
        return None
    side_interval = PixelInterval(0.0, total_hidden.maximum)
    return HolderOcclusionEvidence(
        HolderOcclusionSideEvidence(
            BoundarySide.LEADING,
            HolderOcclusionSideOutcome.ALLOCATION_UNRESOLVED,
            side_interval,
            leading_boundary,
        ),
        HolderOcclusionSideEvidence(
            BoundarySide.TRAILING,
            HolderOcclusionSideOutcome.ALLOCATION_UNRESOLVED,
            side_interval,
            trailing_boundary,
        ),
        total_hidden,
    )


def holder_occlusion_for_sequence(
    boundary_observations: tuple[BoundaryObservation, ...],
    visible_sequence_span: VisibleSequenceSpan,
    frame_boundaries: tuple[FrameBoundary, ...],
    frame_width_px: PixelInterval,
) -> HolderOcclusionEvidence:
    sequence_edges = {
        observation.side: observation
        for observation in boundary_observations
        if observation.side in {BoundarySide.LEADING, BoundarySide.TRAILING}
    }
    if not frame_boundaries:
        visible_width = PixelInterval.exact(
            float(visible_sequence_span.box.width)
        )
        leading_boundary = sequence_edges.get(BoundarySide.LEADING)
        trailing_boundary = sequence_edges.get(BoundarySide.TRAILING)
        if leading_boundary is not None and trailing_boundary is not None:
            unresolved = _single_frame_two_sided_occlusion(
                leading_boundary,
                trailing_boundary,
                visible_width,
                frame_width_px,
            )
            if unresolved is not None:
                return unresolved
        leading_width = visible_width
        trailing_width = visible_width
    else:
        first = min(frame_boundaries, key=lambda item: item.boundary_index)
        last = max(frame_boundaries, key=lambda item: item.boundary_index)
        leading_width = (
            PixelInterval.exact(
                float(first.assignment.observation.start)
                - float(visible_sequence_span.box.left)
            )
            if first.assignment is not None and first.assignment.independent
            else None
        )
        trailing_width = (
            PixelInterval.exact(
                float(visible_sequence_span.box.right)
                - float(last.assignment.observation.end)
            )
            if last.assignment is not None and last.assignment.independent
            else None
        )
    return holder_occlusion_evidence(
        leading_boundary=sequence_edges.get(BoundarySide.LEADING),
        trailing_boundary=sequence_edges.get(BoundarySide.TRAILING),
        leading_visible_frame_width=leading_width,
        trailing_visible_frame_width=trailing_width,
        frame_width_px=frame_width_px,
    )


def visible_sequence_and_crop_envelope(
    observations: tuple[BoundaryObservation, ...],
    *,
    canvas_width: int,
    canvas_height: int,
) -> tuple[VisibleSequenceSpan, CropEnvelope]:
    by_side = {observation.side: observation for observation in observations}
    if set(by_side) != BOUNDARY_SIDES:
        raise ValueError("four boundary observations are required")
    visible = Box(
        int(round(by_side[BoundarySide.LEADING].position.midpoint)),
        int(round(by_side[BoundarySide.TOP].position.midpoint)),
        int(round(by_side[BoundarySide.TRAILING].position.midpoint)),
        int(round(by_side[BoundarySide.BOTTOM].position.midpoint)),
    ).clamp(canvas_width, canvas_height)
    envelope = Box(
        int(round(by_side[BoundarySide.LEADING].position.minimum)),
        int(round(by_side[BoundarySide.TOP].position.minimum)),
        int(round(by_side[BoundarySide.TRAILING].position.maximum)),
        int(round(by_side[BoundarySide.BOTTOM].position.maximum)),
    ).clamp(canvas_width, canvas_height)
    if not visible.valid() or not envelope.valid():
        raise ValueError("boundary observations produce invalid geometry")
    return VisibleSequenceSpan(visible), CropEnvelope(envelope)


def canvas_boundary_observations(
    width: int,
    height: int,
) -> tuple[BoundaryObservation, ...]:
    provenance = MeasurementProvenance(
        root_measurement=MeasurementIdentity.HOLDER_CANVAS,
        source="canvas_clip",
        dependencies=(MeasurementIdentity.CANVAS,),
    )
    return (
        BoundaryObservation(
            BoundarySide.LEADING,
            PixelInterval.exact(0.0),
            BoundaryKind.CANVAS_CLIP,
            provenance,
        ),
        BoundaryObservation(
            BoundarySide.TRAILING,
            PixelInterval.exact(float(width)),
            BoundaryKind.CANVAS_CLIP,
            provenance,
        ),
        BoundaryObservation(
            BoundarySide.TOP,
            PixelInterval.exact(0.0),
            BoundaryKind.CANVAS_CLIP,
            provenance,
        ),
        BoundaryObservation(
            BoundarySide.BOTTOM,
            PixelInterval.exact(float(height)),
            BoundaryKind.CANVAS_CLIP,
            provenance,
        ),
    )
