from __future__ import annotations

from dataclasses import dataclass

from ...geometry.layout import require_work_layout
from ...output.model import FrameBleedPlan, OutputGeometry
from ..decision.model import DecisionGateAssessment


@dataclass(frozen=True)
class FinalizationPlan:
    layout: str
    image_width: int
    image_height: int
    base_geometry: OutputGeometry

    def __post_init__(self) -> None:
        require_work_layout(self.layout)
        if self.image_width <= 0 or self.image_height <= 0:
            raise ValueError("finalization image dimensions must be positive")


@dataclass(frozen=True)
class FinalDetection:
    decision: DecisionGateAssessment
    frame_bleed_plan: FrameBleedPlan
    finalization_plan: FinalizationPlan | None
    output_geometry: OutputGeometry | None

    def __post_init__(self) -> None:
        plan = self.finalization_plan
        if plan is None and self.decision.status == "approved_auto":
            raise ValueError("approved detection requires resolved final geometry")
        if (plan is None) != (self.output_geometry is None):
            raise ValueError("finalization plan and output geometry must resolve together")
        if plan is None and self.frame_bleed_plan.frame_sides:
            raise ValueError("unresolved geometry cannot carry frame output bleed")
        if plan is not None and len(plan.base_geometry.frame_crop_envelopes) != len(
            self.frame_bleed_plan.frame_sides
        ):
            raise ValueError("final detection must preserve frame identity")
        if plan is not None and (
            self.output_geometry.frame_crop_envelopes
            != plan.base_geometry.frame_crop_envelopes
        ):
            raise ValueError("final output must preserve photo aperture identity")

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
