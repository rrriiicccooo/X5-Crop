from __future__ import annotations

from typing import Any

from ..detection.final.finalize import final_detection_from_facts
from ..detection.final.model import FinalDetection
from .validation import (
    current_report_record_errors,
    decision_gate_from_read_model,
    frame_bleed_plan_from_read_model,
    finalization_plan_from_read_model,
    output_geometry_from_read_model,
)


def final_detection_from_record(record: dict[str, Any]) -> FinalDetection:
    errors = current_report_record_errors(record)
    if errors:
        raise ValueError("invalid current report record: " + ",".join(errors))
    decision = record["decision"]
    output = record["output"]
    finalization_plan = finalization_plan_from_read_model(
        output["finalization_plan"]
    ) if output["finalization_plan"] is not None else None
    frame_bleed_plan = frame_bleed_plan_from_read_model(
        output["frame_bleed_plan"]
    )
    restored_geometry = (
        None
        if output["final_geometry"] is None
        else output_geometry_from_read_model(output["final_geometry"])
    )
    return final_detection_from_facts(
        decision=decision_gate_from_read_model(decision["gate"]),
        frame_bleed_plan=frame_bleed_plan,
        finalization_plan=finalization_plan,
        output_geometry=restored_geometry,
    )
