from __future__ import annotations

from dataclasses import dataclass

from ...domain import (
    BOUNDARY_SIDES,
    BoundaryObservation,
    Box,
    CropEnvelope,
    EvidenceState,
    FrameBoundary,
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
        if observation.side in {"leading", "trailing"}
    }
    maximum_hidden = frame_width_px.maximum

    def side_interval(side: str) -> PixelInterval:
        observation = by_side.get(side)
        if observation is None or observation.kind != "white_holder_transition":
            return PixelInterval.zero()
        return PixelInterval(0.0, maximum_hidden)

    return HolderOcclusionConstraint(
        side_interval("leading"),
        side_interval("trailing"),
    )


@dataclass(frozen=True)
class HolderOcclusionSideEvidence:
    side: str
    state: EvidenceState
    hidden_width_px: PixelInterval
    reason: str
    boundary: BoundaryObservation | None

    def __post_init__(self) -> None:
        if self.side not in {"leading", "trailing"}:
            raise ValueError("holder occlusion side must be leading or trailing")
        if self.hidden_width_px.minimum < 0.0:
            raise ValueError("holder occlusion width cannot be negative")
        if not self.reason:
            raise ValueError("holder occlusion evidence requires a reason")
        if self.boundary is not None and self.boundary.side != self.side:
            raise ValueError("holder occlusion boundary must match its side")
        if self.state == EvidenceState.NOT_APPLICABLE:
            if self.hidden_width_px != PixelInterval.zero():
                raise ValueError("not-applicable holder occlusion has zero width")
        elif self.state == EvidenceState.SUPPORTED:
            if (
                self.hidden_width_px.minimum <= 0.0
                or self.boundary is None
                or self.boundary.kind != "white_holder_transition"
            ):
                raise ValueError(
                    "supported holder occlusion requires positive white-holder evidence"
                )
        elif self.state != EvidenceState.UNAVAILABLE:
            raise ValueError("unsupported holder occlusion evidence state")


@dataclass(frozen=True)
class HolderOcclusionEvidence:
    leading: HolderOcclusionSideEvidence
    trailing: HolderOcclusionSideEvidence
    combined_hidden_width_px: PixelInterval

    def __post_init__(self) -> None:
        if self.leading.side != "leading" or self.trailing.side != "trailing":
            raise ValueError("holder occlusion evidence requires ordered edge sides")
        if self.combined_hidden_width_px.minimum < 0.0:
            raise ValueError("combined holder occlusion width cannot be negative")
        side_total = self.leading.hidden_width_px.plus(
            self.trailing.hidden_width_px
        )
        allocation_unresolved = self.combined_hidden_width_px != side_total
        if allocation_unresolved:
            if (
                self.leading.state != EvidenceState.UNAVAILABLE
                or self.trailing.state != EvidenceState.UNAVAILABLE
                or self.leading.hidden_width_px.minimum != 0.0
                or self.trailing.hidden_width_px.minimum != 0.0
                or self.leading.hidden_width_px.maximum
                != self.combined_hidden_width_px.maximum
                or self.trailing.hidden_width_px.maximum
                != self.combined_hidden_width_px.maximum
            ):
                raise ValueError("unresolved edge allocation must preserve one total width")
        elif self.combined_hidden_width_px != side_total:
            raise ValueError("combined holder occlusion must derive from edge widths")

    @classmethod
    def unavailable(cls) -> "HolderOcclusionEvidence":
        return cls(
            _unavailable_side("leading"),
            _unavailable_side("trailing"),
            PixelInterval.zero(),
        )


def visible_sequence_length_interval(
    visible_sequence_span: VisibleSequenceSpan,
    boundary_observations: tuple[BoundaryObservation, ...],
) -> PixelInterval:
    by_side = {
        observation.side: observation
        for observation in boundary_observations
        if observation.side in {"leading", "trailing"}
    }
    if set(by_side) == {"leading", "trailing"}:
        measured = by_side["trailing"].position.minus(
            by_side["leading"].position
        )
        if measured.maximum > 0.0:
            return PixelInterval(
                max(0.0, measured.minimum),
                measured.maximum,
            )
    return PixelInterval.exact(float(visible_sequence_span.box.width))


def _unavailable_side(side: str) -> HolderOcclusionSideEvidence:
    return HolderOcclusionSideEvidence(
        side=side,
        state=EvidenceState.UNAVAILABLE,
        hidden_width_px=PixelInterval.zero(),
        reason="holder_occlusion_measurement_unavailable",
        boundary=None,
    )


def _occlusion_side_evidence(
    side: str,
    boundary: BoundaryObservation | None,
    visible_width: PixelInterval | None,
    frame_width: PixelInterval,
) -> HolderOcclusionSideEvidence:
    if boundary is None:
        return HolderOcclusionSideEvidence(
            side,
            EvidenceState.UNAVAILABLE,
            PixelInterval.zero(),
            "edge_boundary_or_visible_width_unavailable",
            boundary,
        )
    if boundary.side != side:
        raise ValueError(f"{side} occlusion requires a {side} boundary")
    if boundary.kind != "white_holder_transition":
        return HolderOcclusionSideEvidence(
            side,
            EvidenceState.NOT_APPLICABLE,
            PixelInterval.zero(),
            "measured_edge_is_not_white_holder_occlusion",
            boundary,
        )
    if visible_width is None:
        return HolderOcclusionSideEvidence(
            side,
            EvidenceState.UNAVAILABLE,
            PixelInterval.zero(),
            "edge_boundary_or_visible_width_unavailable",
            boundary,
        )
    hidden = PixelInterval(
        max(0.0, frame_width.minimum - visible_width.maximum),
        max(0.0, frame_width.maximum - visible_width.minimum),
    )
    if hidden.maximum <= 0.0:
        return HolderOcclusionSideEvidence(
            side,
            EvidenceState.NOT_APPLICABLE,
            PixelInterval.zero(),
            "white_holder_boundary_without_frame_shortening",
            boundary,
        )
    if hidden.minimum <= 0.0:
        return HolderOcclusionSideEvidence(
            side,
            EvidenceState.UNAVAILABLE,
            hidden,
            "edge_frame_shortening_uncertain",
            boundary,
        )
    return HolderOcclusionSideEvidence(
        side,
        EvidenceState.SUPPORTED,
        hidden,
        "white_holder_occludes_edge_frame",
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
        "leading",
        leading_boundary,
        leading_visible_frame_width,
        frame_width_px,
    )
    trailing = _occlusion_side_evidence(
        "trailing",
        trailing_boundary,
        trailing_visible_frame_width,
        frame_width_px,
    )
    return HolderOcclusionEvidence(
        leading=leading,
        trailing=trailing,
        combined_hidden_width_px=leading.hidden_width_px.plus(
            trailing.hidden_width_px
        ),
    )


def _single_frame_two_sided_occlusion(
    leading_boundary: BoundaryObservation,
    trailing_boundary: BoundaryObservation,
    visible_width: PixelInterval,
    frame_width: PixelInterval,
) -> HolderOcclusionEvidence | None:
    if (
        leading_boundary.kind != "white_holder_transition"
        or trailing_boundary.kind != "white_holder_transition"
    ):
        return None
    total_hidden = PixelInterval(
        max(0.0, frame_width.minimum - visible_width.maximum),
        max(0.0, frame_width.maximum - visible_width.minimum),
    )
    if total_hidden.maximum <= 0.0:
        return None
    side_interval = PixelInterval(0.0, total_hidden.maximum)
    reason = "single_frame_occlusion_allocation_unresolved"
    return HolderOcclusionEvidence(
        HolderOcclusionSideEvidence(
            "leading",
            EvidenceState.UNAVAILABLE,
            side_interval,
            reason,
            leading_boundary,
        ),
        HolderOcclusionSideEvidence(
            "trailing",
            EvidenceState.UNAVAILABLE,
            side_interval,
            reason,
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
        if observation.side in {"leading", "trailing"}
    }
    if not frame_boundaries:
        visible_width = PixelInterval.exact(
            float(visible_sequence_span.box.width)
        )
        leading_boundary = sequence_edges.get("leading")
        trailing_boundary = sequence_edges.get("trailing")
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
        leading_boundary=sequence_edges.get("leading"),
        trailing_boundary=sequence_edges.get("trailing"),
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
        int(round(by_side["leading"].position.midpoint)),
        int(round(by_side["top"].position.midpoint)),
        int(round(by_side["trailing"].position.midpoint)),
        int(round(by_side["bottom"].position.midpoint)),
    ).clamp(canvas_width, canvas_height)
    envelope = Box(
        int(round(by_side["leading"].position.minimum)),
        int(round(by_side["top"].position.minimum)),
        int(round(by_side["trailing"].position.maximum)),
        int(round(by_side["bottom"].position.maximum)),
    ).clamp(canvas_width, canvas_height)
    if not visible.valid() or not envelope.valid():
        raise ValueError("boundary observations produce invalid geometry")
    return VisibleSequenceSpan(visible), CropEnvelope(envelope)


def canvas_boundary_observations(
    width: int,
    height: int,
) -> tuple[BoundaryObservation, ...]:
    provenance = MeasurementProvenance(
        root_measurement="holder_canvas",
        source="canvas_clip",
        dependencies=("canvas",),
    )
    return (
        BoundaryObservation(
            "leading", PixelInterval.exact(0.0), "canvas_clip", provenance
        ),
        BoundaryObservation(
            "trailing", PixelInterval.exact(float(width)), "canvas_clip", provenance
        ),
        BoundaryObservation(
            "top", PixelInterval.exact(0.0), "canvas_clip", provenance
        ),
        BoundaryObservation(
            "bottom", PixelInterval.exact(float(height)), "canvas_clip", provenance
        ),
    )
