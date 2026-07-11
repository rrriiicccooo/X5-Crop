from __future__ import annotations

from dataclasses import dataclass

from ...domain import MeasurementProvenance
from ..evidence.state import EvidenceState
from .intervals import PixelInterval


BOUNDARY_SIDES = frozenset({"leading", "trailing", "top", "bottom"})
BOUNDARY_KINDS = frozenset(
    {
        "white_holder_transition",
        "tonal_transition",
        "texture_transition",
        "canvas_clip",
    }
)


@dataclass(frozen=True)
class BoundaryObservation:
    side: str
    position: PixelInterval
    kind: str
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if self.side not in BOUNDARY_SIDES:
            raise ValueError(f"unsupported boundary side: {self.side}")
        if self.kind not in BOUNDARY_KINDS:
            raise ValueError(f"unsupported boundary kind: {self.kind}")


@dataclass(frozen=True)
class HolderOcclusionSideEvidence:
    side: str
    state: EvidenceState
    hidden_width_px: PixelInterval
    reason: str
    boundary: BoundaryObservation | None


@dataclass(frozen=True)
class HolderOcclusionEvidence:
    leading: HolderOcclusionSideEvidence
    trailing: HolderOcclusionSideEvidence

    @classmethod
    def not_applicable(cls) -> "HolderOcclusionEvidence":
        return cls(
            _not_applicable_side("leading"),
            _not_applicable_side("trailing"),
        )

    @classmethod
    def unavailable(cls) -> "HolderOcclusionEvidence":
        return cls(
            _unavailable_side("leading"),
            _unavailable_side("trailing"),
        )


def _not_applicable_side(side: str) -> HolderOcclusionSideEvidence:
    return HolderOcclusionSideEvidence(
        side=side,
        state=EvidenceState.NOT_APPLICABLE,
        hidden_width_px=PixelInterval.zero(),
        reason="edge_frame_not_occluded",
        boundary=None,
    )


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
    if boundary is None or visible_width is None:
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
            EvidenceState.UNAVAILABLE,
            PixelInterval.zero(),
            "edge_boundary_is_not_white_holder",
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
    return HolderOcclusionEvidence(
        leading=_occlusion_side_evidence(
            "leading",
            leading_boundary,
            leading_visible_frame_width,
            frame_width_px,
        ),
        trailing=_occlusion_side_evidence(
            "trailing",
            trailing_boundary,
            trailing_visible_frame_width,
            frame_width_px,
        ),
    )
