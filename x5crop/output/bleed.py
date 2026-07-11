from __future__ import annotations

from ..domain import AxisBleedParameters
from ..geometry.boxes import map_work_box, original_box_to_work
from .model import OutputGeometry


def output_bleed_geometry(
    geometry: OutputGeometry,
    output_bleed: AxisBleedParameters,
    *,
    layout: str,
    image_width: int,
    image_height: int,
) -> OutputGeometry:
    if output_bleed.long_axis == 0 and output_bleed.short_axis == 0:
        return geometry
    work_width = image_width if layout == "horizontal" else image_height
    work_height = image_height if layout == "horizontal" else image_width
    frames = tuple(
        original_box_to_work(frame, layout, image_width, image_height).expand(
            int(output_bleed.long_axis),
            int(output_bleed.short_axis),
            work_width,
            work_height,
        )
        for frame in geometry.frames
    )
    return OutputGeometry(
        outer=geometry.outer,
        frames=tuple(
            map_work_box(frame, layout, image_width, image_height)
            for frame in frames
        ),
    )
