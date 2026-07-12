from __future__ import annotations

from dataclasses import dataclass

from ...output.model import OutputGeometry
from ..decision.model import DecisionResult


@dataclass(frozen=True)
class FinalDetection:
    decision: DecisionResult
    output_geometry: OutputGeometry

    def __post_init__(self) -> None:
        decision_geometry = self.decision.decision_geometry
        decision_envelope = decision_geometry.crop_envelope.box
        output_envelope = self.output_geometry.crop_envelope.box
        if not (
            output_envelope.left <= decision_envelope.left
            and output_envelope.top <= decision_envelope.top
            and output_envelope.right >= decision_envelope.right
            and output_envelope.bottom >= decision_envelope.bottom
        ):
            raise ValueError("final output must contain the decision crop envelope")
        if len(self.output_geometry.frames) != len(decision_geometry.frames):
            raise ValueError("final output must preserve decision frame identity")
        if any(
            output.left > decision.left
            or output.top > decision.top
            or output.right < decision.right
            or output.bottom < decision.bottom
            for decision, output in zip(
                decision_geometry.frames,
                self.output_geometry.frames,
                strict=True,
            )
        ):
            raise ValueError("final output frames may expand but cannot shrink or move")
