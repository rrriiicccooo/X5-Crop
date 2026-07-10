from __future__ import annotations

from typing import Any

from ....domain import Box
from ....policies.parameters.outer import GridOuterRefineParameters
from ....utils import clamp_int


def grid_refined_outer_box(
    outer: Box,
    grid_detail: dict[str, Any],
    count: int,
    pitch: float,
    work_width: int,
    policy: GridOuterRefineParameters,
) -> Box | None:
    if not bool(grid_detail.get("grid_used", False)):
        return None
    model_origin = float(grid_detail.get("grid_origin", 0.0))
    model_pitch = float(grid_detail.get("grid_pitch", pitch))
    proposed_left = int(round(outer.left + model_origin))
    proposed_right = int(round(outer.left + model_origin + model_pitch * count))
    max_shift = clamp_int(pitch * policy.shift_ratio, policy.shift_min, policy.shift_max)
    width_change = abs((proposed_right - proposed_left) - outer.width) / max(1.0, float(outer.width))
    if (
        proposed_right > proposed_left
        and abs(proposed_left - outer.left) <= max_shift
        and abs(proposed_right - outer.right) <= max_shift
        and width_change <= policy.max_width_change
        and 0 <= proposed_left < proposed_right <= work_width
    ):
        return Box(proposed_left, outer.top, proposed_right, outer.bottom)
    return None
