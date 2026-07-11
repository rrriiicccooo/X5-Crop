from __future__ import annotations

import numpy as np

from ..domain import AxisBleedParameters, Box
from .model import OutputGeometry
from ..geometry.boxes import map_work_box, original_box_to_work
from ..geometry.layout import work_gray
from ..policies.parameters.exposure_overlap import EdgeBleedProtectionParameters
from ..policies.parameters.finalization import ApprovedGeometryAdjustmentParameters
from ..units import ScanCalibration
from ..utils import clamp_int


def edge_bleed_protected_geometry(
    geometry: OutputGeometry,
    *,
    layout: str,
    strip_mode: str,
    count: int,
    output_bleed: AxisBleedParameters,
    image_width: int,
    image_height: int,
    calibration: ScanCalibration,
    parameters: EdgeBleedProtectionParameters,
) -> OutputGeometry:
    if (
        strip_mode != "full"
        or count <= 1
        or len(geometry.frames) != count
    ):
        return geometry
    outer = original_box_to_work(
        geometry.outer,
        layout,
        image_width,
        image_height,
    )
    frames = [
        original_box_to_work(frame, layout, image_width, image_height)
        for frame in geometry.frames
    ]
    if not outer.valid() or any(not frame.valid() for frame in frames):
        return geometry
    work_width = image_width if layout == "horizontal" else image_height
    nominal = float(outer.width) / float(max(1, count))
    guard = parameters.guard.resolve_px(
        calibration,
        axis="x" if layout == "horizontal" else "y",
        reference_px=nominal,
    )
    first_target = max(0, outer.left - int(output_bleed.long_axis))
    if frames[0].left > first_target + guard:
        frames[0] = Box(
            first_target,
            frames[0].top,
            frames[0].right,
            frames[0].bottom,
        )
    last_target = min(work_width, outer.right + int(output_bleed.long_axis))
    if frames[-1].right < last_target - guard:
        frames[-1] = Box(
            frames[-1].left,
            frames[-1].top,
            last_target,
            frames[-1].bottom,
        )
    if any(not frame.valid() for frame in frames):
        return geometry
    return OutputGeometry(
        outer=geometry.outer,
        frames=tuple(
            map_work_box(frame, layout, image_width, image_height)
            for frame in frames
        ),
    )


def approved_geometry_adjustment(
    geometry: OutputGeometry,
    gray: np.ndarray,
    *,
    layout: str,
    strip_mode: str,
    count: int,
    approved: bool,
    parameters: ApprovedGeometryAdjustmentParameters,
) -> OutputGeometry:
    if (
        not approved
        or strip_mode != "full"
        or len(geometry.frames) != count
    ):
        return geometry
    gray_work = work_gray(gray, layout)
    width = gray_work.shape[1]
    outer = original_box_to_work(
        geometry.outer,
        layout,
        gray.shape[1],
        gray.shape[0],
    )
    frames = [
        original_box_to_work(
            frame,
            layout,
            gray.shape[1],
            gray.shape[0],
        )
        for frame in geometry.frames
    ]
    if not outer.valid() or any(not frame.valid() for frame in frames):
        return geometry
    long_limit = clamp_int(
        (outer.width / float(max(1, count))) * parameters.long_limit_ratio,
        parameters.long_limit_min,
        parameters.long_limit_max,
    )
    band_top = outer.top + int(
        round(outer.height * parameters.side_band_trim_ratio)
    )
    band_bottom = outer.bottom - int(
        round(outer.height * parameters.side_band_trim_ratio)
    )
    if band_bottom <= band_top:
        band_top, band_bottom = outer.top, outer.bottom

    def side_extension(side: str) -> int:
        if side == "left":
            low, high = max(0, outer.left - long_limit), outer.left
        else:
            low, high = outer.right, min(width, outer.right + long_limit)
        if high <= low:
            return 0
        strip = gray_work[band_top:band_bottom, low:high]
        if not strip.size:
            return 0
        active_fraction = (
            strip < parameters.content_threshold_u8
        ).mean(axis=0)
        active = np.where(
            active_fraction > parameters.min_active_column_fraction
        )[0]
        if not active.size:
            return 0
        if side == "left":
            return int(high - (low + int(active[0])))
        return int(active[-1]) + 1

    pitch = float(outer.width) / float(max(1, count))
    minimum_extension = clamp_int(
        pitch * parameters.min_ext_ratio,
        parameters.min_ext_min,
        parameters.min_ext_max,
    )
    left_extension = side_extension("left")
    right_extension = side_extension("right")
    left_extension = left_extension if left_extension >= minimum_extension else 0
    right_extension = right_extension if right_extension >= minimum_extension else 0
    if 0 < left_extension <= long_limit:
        outer = Box(
            max(0, outer.left - left_extension),
            outer.top,
            outer.right,
            outer.bottom,
        )
        frames[0] = Box(
            outer.left,
            frames[0].top,
            frames[0].right,
            frames[0].bottom,
        )
    if 0 < right_extension <= long_limit:
        outer = Box(
            outer.left,
            outer.top,
            min(width, outer.right + right_extension),
            outer.bottom,
        )
        frames[-1] = Box(
            frames[-1].left,
            frames[-1].top,
            outer.right,
            frames[-1].bottom,
        )
    if not outer.valid() or any(not frame.valid() for frame in frames):
        return geometry
    return OutputGeometry(
        outer=map_work_box(
            outer,
            layout,
            gray.shape[1],
            gray.shape[0],
        ),
        frames=tuple(
            map_work_box(
                frame,
                layout,
                gray.shape[1],
                gray.shape[0],
            )
            for frame in frames
        ),
    )
