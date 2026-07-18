from __future__ import annotations

from dataclasses import dataclass

from ...geometry.layout import require_work_layout
from ...output.model import FrameBleedPlan, OutputGeometry
from ..decision.model import DecisionGateAssessment
from ..decision.vocabulary import (
    FINAL_REASON_GEOMETRY_RESOLUTION_UNAVAILABLE,
    FINAL_REASON_OUTPUT_PROTECTION_UNRESOLVED,
)


FRAME_EXPORT_REASON_READY = "geometry_resolved_output_protected"


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


def frame_export_eligibility(
    finalization_plan: FinalizationPlan | None,
    frame_bleed_plan: FrameBleedPlan,
) -> tuple[bool, str]:
    if finalization_plan is None:
        return False, FINAL_REASON_GEOMETRY_RESOLUTION_UNAVAILABLE
    if not frame_bleed_plan.feasible:
        return False, FINAL_REASON_OUTPUT_PROTECTION_UNRESOLVED
    return True, FRAME_EXPORT_REASON_READY


@dataclass(frozen=True)
class FinalDetection:
    decision: DecisionGateAssessment
    frame_bleed_plan: FrameBleedPlan
    finalization_plan: FinalizationPlan | None
    output_geometry: OutputGeometry | None

    def __post_init__(self) -> None:
        plan = self.finalization_plan
        if (
            self.decision.status == "approved_auto"
            and not frame_export_eligibility(plan, self.frame_bleed_plan)[0]
        ):
            raise ValueError("approved detection requires export-eligible output")
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
            raise ValueError("final output must preserve frame-slot identity")

    @property
    def frame_export_eligible(self) -> bool:
        return frame_export_eligibility(
            self.finalization_plan,
            self.frame_bleed_plan,
        )[0]

    @property
    def frame_export_reason(self) -> str:
        return frame_export_eligibility(
            self.finalization_plan,
            self.frame_bleed_plan,
        )[1]
