from __future__ import annotations

from ...domain import FrameCropEnvelope, WorkspaceExtent
from ...geometry.boxes import map_work_box
from ...output.model import FrameBleedPlan, OutputGeometry
from ...output.frame_bleed import apply_frame_bleed
from ..candidate.selection.model import SelectionResult
from ..decision.model import DecisionGateAssessment
from .model import FinalDetection, FinalizationPlan


def finalization_plan_for_selection(
    selection: SelectionResult,
    *,
    workspace_extent: WorkspaceExtent,
) -> FinalizationPlan | None:
    if not selection.geometry_resolution.supported:
        return None
    geometry = selection.selected.geometry
    image_width = workspace_extent.width
    image_height = workspace_extent.height
    mapped_envelopes = tuple(
        FrameCropEnvelope(
            envelope.photo_index,
            map_work_box(
                envelope.box,
                geometry.layout,
                image_width,
                image_height,
            ),
        )
        for envelope in geometry.frame_crop_envelopes
    )
    base_geometry = OutputGeometry(
        frame_crop_envelopes=mapped_envelopes,
        final_boxes=tuple(item.box for item in mapped_envelopes),
    )
    return FinalizationPlan(
        layout=geometry.layout,
        image_width=image_width,
        image_height=image_height,
        base_geometry=base_geometry,
    )


def finalize_detection(
    decision: DecisionGateAssessment,
    frame_bleed_plan: FrameBleedPlan,
    finalization_plan: FinalizationPlan | None,
) -> FinalDetection:
    output_geometry = (
        None
        if finalization_plan is None
        else apply_frame_bleed(
            finalization_plan.base_geometry,
            frame_bleed_plan,
            layout=finalization_plan.layout,
            image_width=finalization_plan.image_width,
            image_height=finalization_plan.image_height,
        )
    )
    return final_detection_from_facts(
        decision=decision,
        frame_bleed_plan=frame_bleed_plan,
        finalization_plan=finalization_plan,
        output_geometry=output_geometry,
    )


def final_detection_from_facts(
    decision: DecisionGateAssessment,
    frame_bleed_plan: FrameBleedPlan,
    finalization_plan: FinalizationPlan | None,
    output_geometry: OutputGeometry | None,
) -> FinalDetection:
    return FinalDetection(
        decision=decision,
        frame_bleed_plan=frame_bleed_plan,
        finalization_plan=finalization_plan,
        output_geometry=output_geometry,
    )
