from __future__ import annotations

from dataclasses import dataclass

from ..domain import Box, EvidenceState
from ..geometry.affine import AffineCoordinateTransform
from .grid.model import ProtectedCropEnvelope


@dataclass(frozen=True)
class OutputTransformAssessment:
    transform: AffineCoordinateTransform
    outcome: str
    state: EvidenceState
    named_gap: str | None

    def __post_init__(self) -> None:
        if self.outcome != "typed_identity":
            raise ValueError("current bounded flow only admits typed identity")
        if (
            not self.transform.is_identity
            or self.state != EvidenceState.SUPPORTED
            or self.named_gap is not None
        ):
            raise ValueError("typed identity transform assessment is inconsistent")


def typed_identity_transform_assessment(
    width: int,
    height: int,
) -> OutputTransformAssessment:
    return OutputTransformAssessment(
        transform=AffineCoordinateTransform.identity(width, height),
        outcome="typed_identity",
        state=EvidenceState.SUPPORTED,
        named_gap=None,
    )


def source_boxes_from_work_envelopes(
    envelopes: tuple[ProtectedCropEnvelope, ...],
    *,
    layout: str,
) -> tuple[Box, ...]:
    if layout == "horizontal":
        return tuple(item.protected_work_box for item in envelopes)
    if layout == "vertical":
        return tuple(
            Box(
                item.protected_work_box.top,
                item.protected_work_box.left,
                item.protected_work_box.bottom,
                item.protected_work_box.right,
            )
            for item in envelopes
        )
    raise ValueError(f"unsupported work layout: {layout}")
