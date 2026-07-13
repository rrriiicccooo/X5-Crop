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

    def __post_init__(self) -> None:
        require_work_layout(self.layout)
        if self.image_width <= 0 or self.image_height <= 0:
            raise ValueError("finalization image dimensions must be positive")


@dataclass(frozen=True)
class FinalDetection:
    decision: DecisionGateAssessment
    frame_bleed_plan: FrameBleedPlan
    finalization_plan: FinalizationPlan | None

    def __post_init__(self) -> None:
        plan = self.finalization_plan
        if plan is None and self.decision.status == "approved_auto":
            raise ValueError("approved detection requires resolved final geometry")
        if plan is not None and len(plan.decision_geometry.frames) != len(
            self.frame_bleed_plan.frame_sides
        ):
            raise ValueError("final detection must preserve frame identity")

    @property
    def output_geometry(self) -> OutputGeometry | None:
        plan = self.finalization_plan
        if plan is None:
            return None
        return apply_frame_bleed(
            plan.decision_geometry,
            self.frame_bleed_plan,
            layout=plan.layout,
            image_width=plan.image_width,
            image_height=plan.image_height,
        )

    @property
    def frame_export_eligible(self) -> bool:
        return self.finalization_plan is not None

    @property
    def frame_export_reason(self) -> str:
        return (
            "geometry_resolved"
            if self.frame_export_eligible
            else "geometry_resolution_unavailable"
        )
