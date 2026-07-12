from __future__ import annotations

from dataclasses import dataclass

from ...geometry.layout import require_work_layout
from ...output.frame_bleed import apply_frame_bleed
from ...output.model import FrameBleedPlan, OutputGeometry
from ..decision.model import DecisionGateAssessment


@dataclass(frozen=True)
class FinalizationPlan:
    layout: str
    image_width: int
    image_height: int
    decision_geometry: OutputGeometry
    frame_bleed_plan: FrameBleedPlan

    def __post_init__(self) -> None:
        require_work_layout(self.layout)
        if self.image_width <= 0 or self.image_height <= 0:
            raise ValueError("finalization image dimensions must be positive")
        if len(self.decision_geometry.frames) != len(
            self.frame_bleed_plan.frame_sides
        ):
            raise ValueError("finalization plan must preserve frame identity")


@dataclass(frozen=True)
class FinalDetection:
    decision: DecisionGateAssessment
    finalization_plan: FinalizationPlan

    @property
    def output_geometry(self) -> OutputGeometry:
        plan = self.finalization_plan
        return apply_frame_bleed(
            plan.decision_geometry,
            plan.frame_bleed_plan,
            layout=plan.layout,
            image_width=plan.image_width,
            image_height=plan.image_height,
        )
