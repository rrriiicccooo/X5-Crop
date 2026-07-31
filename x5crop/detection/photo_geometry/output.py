from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import itertools
import math

from ...domain import Box, FiniteInterval
from ..source_core import SourceLaneEvidence
from .corridors import source_lane_box
from .model import (
    BoundaryAxis,
    FramePhotoGeometry,
    GridInferredBlankOutputGeometry,
    GridSlotTranslationAssessment,
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    SafeCropEnvelope,
    SourceCoordinateLine,
)
from .protection import OutputProtectionSpec


def _stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}:{sha256(payload).hexdigest()[:24]}"


def _line_with_offset(
    line: SourceCoordinateLine,
    offset_px: float,
) -> SourceCoordinateLine:
    return replace(line, offset_px=offset_px)


def _uncertain_polygon_points(
    geometry: FramePhotoGeometry,
) -> tuple[tuple[float, float], ...]:
    points: list[tuple[float, float]] = []
    for top_offset, bottom_offset, start_offset, end_offset in itertools.product(
        (
            geometry.top.offset_interval_px.minimum,
            geometry.top.offset_interval_px.maximum,
        ),
        (
            geometry.bottom.offset_interval_px.minimum,
            geometry.bottom.offset_interval_px.maximum,
        ),
        (
            geometry.start.offset_interval_px.minimum,
            geometry.start.offset_interval_px.maximum,
        ),
        (
            geometry.end.offset_interval_px.minimum,
            geometry.end.offset_interval_px.maximum,
        ),
    ):
        top = _line_with_offset(geometry.top.line, top_offset)
        bottom = _line_with_offset(geometry.bottom.line, bottom_offset)
        start = _line_with_offset(geometry.start.line, start_offset)
        end = _line_with_offset(geometry.end.line, end_offset)
        points.extend(
            (
                top.intersection(start),
                top.intersection(end),
                bottom.intersection(end),
                bottom.intersection(start),
            )
        )
    return tuple(points)


def _outward_box(
    points: tuple[tuple[float, float], ...],
    allowance_px: float,
) -> Box:
    if not points or allowance_px < 0.0:
        raise ValueError("outward source box requires points and allowance")
    return Box(
        left=math.floor(
            math.nextafter(
                min(point[0] for point in points) - allowance_px,
                -math.inf,
            )
        ),
        top=math.floor(
            math.nextafter(
                min(point[1] for point in points) - allowance_px,
                -math.inf,
            )
        ),
        right=math.ceil(
            math.nextafter(
                max(point[0] for point in points) + allowance_px,
                math.inf,
            )
        ),
        bottom=math.ceil(
            math.nextafter(
                max(point[1] for point in points) + allowance_px,
                math.inf,
            )
        ),
    )


def _protect_and_clip(
    safe: Box,
    *,
    lane_box: Box,
    layout: str,
    long_protection_px: int,
    short_protection_px: int,
) -> tuple[Box, tuple[str, ...]]:
    if layout == "horizontal":
        x_protection = long_protection_px
        y_protection = short_protection_px
    elif layout == "vertical":
        x_protection = short_protection_px
        y_protection = long_protection_px
    else:
        raise ValueError(f"unsupported output layout: {layout}")
    requested = Box(
        safe.left - x_protection,
        safe.top - y_protection,
        safe.right + x_protection,
        safe.bottom + y_protection,
    )
    saturated: list[str] = []
    if requested.left < lane_box.left:
        saturated.append("left")
    if requested.top < lane_box.top:
        saturated.append("top")
    if requested.right > lane_box.right:
        saturated.append("right")
    if requested.bottom > lane_box.bottom:
        saturated.append("bottom")
    protected = Box(
        max(lane_box.left, requested.left),
        max(lane_box.top, requested.top),
        min(lane_box.right, requested.right),
        min(lane_box.bottom, requested.bottom),
    )
    if not protected.valid():
        raise ValueError("protected source geometry is outside lane authority")
    return protected, tuple(saturated)


def safe_crop_envelope_from_photo_geometry(
    geometry: FramePhotoGeometry,
    lane: SourceLaneEvidence,
    *,
    layout: str,
    protection: OutputProtectionSpec,
) -> SafeCropEnvelope:
    lane_box = source_lane_box(lane, layout)
    safe_requested = _outward_box(
        _uncertain_polygon_points(geometry),
        PHOTO_BOUNDARY_MEASUREMENT_SPEC.interpolation_allowance_source_px,
    )
    safe = Box(
        max(lane_box.left, safe_requested.left),
        max(lane_box.top, safe_requested.top),
        min(lane_box.right, safe_requested.right),
        min(lane_box.bottom, safe_requested.bottom),
    )
    if not safe.valid():
        raise ValueError("photo safe geometry cannot be clipped to its lane")
    scales = lane.axis_scale_intervals
    long_px = int(
        math.ceil(
            protection.long_axis_mm_per_side
            * scales.long_axis_px_per_mm.maximum
        )
    )
    short_px = int(
        math.ceil(
            protection.short_axis_mm_per_side
            * scales.short_axis_px_per_mm.maximum
        )
    )
    protected, saturated = _protect_and_clip(
        safe,
        lane_box=lane_box,
        layout=layout,
        long_protection_px=long_px,
        short_protection_px=short_px,
    )
    return SafeCropEnvelope(
        geometry_id=geometry.geometry_id,
        lane_id=geometry.lane_id,
        lane_ordinal=geometry.lane_ordinal,
        source_safe_box=safe,
        source_protected_box=protected,
        interpolation_allowance_source_px=(
            PHOTO_BOUNDARY_MEASUREMENT_SPEC
            .interpolation_allowance_source_px
        ),
        long_axis_protection_mm=protection.long_axis_mm_per_side,
        short_axis_protection_mm=protection.short_axis_mm_per_side,
        saturated_sides=saturated,
    )


def grid_inferred_blank_output_geometry(
    *,
    lane: SourceLaneEvidence,
    layout: str,
    lane_ordinal: int,
    long_axis_interval_px: FiniteInterval,
    short_axis_interval_px: FiniteInterval,
    grid_translation: GridSlotTranslationAssessment,
    protection: OutputProtectionSpec,
) -> GridInferredBlankOutputGeometry:
    lane_box = source_lane_box(lane, layout)
    allowance = (
        PHOTO_BOUNDARY_MEASUREMENT_SPEC
        .interpolation_allowance_source_px
    )
    if layout == "horizontal":
        points = (
            (long_axis_interval_px.minimum, short_axis_interval_px.minimum),
            (long_axis_interval_px.maximum, short_axis_interval_px.maximum),
        )
    elif layout == "vertical":
        points = (
            (short_axis_interval_px.minimum, long_axis_interval_px.minimum),
            (short_axis_interval_px.maximum, long_axis_interval_px.maximum),
        )
    else:
        raise ValueError(f"unsupported blank layout: {layout}")
    safe_requested = _outward_box(points, allowance)
    safe = Box(
        max(lane_box.left, safe_requested.left),
        max(lane_box.top, safe_requested.top),
        min(lane_box.right, safe_requested.right),
        min(lane_box.bottom, safe_requested.bottom),
    )
    if not safe.valid():
        raise ValueError("blank slot geometry exceeds lane authority")
    scales = lane.axis_scale_intervals
    long_px = int(
        math.ceil(
            protection.long_axis_mm_per_side
            * scales.long_axis_px_per_mm.maximum
        )
    )
    short_px = int(
        math.ceil(
            protection.short_axis_mm_per_side
            * scales.short_axis_px_per_mm.maximum
        )
    )
    protected, saturated = _protect_and_clip(
        safe,
        lane_box=lane_box,
        layout=layout,
        long_protection_px=long_px,
        short_protection_px=short_px,
    )
    return GridInferredBlankOutputGeometry(
        geometry_id=_stable_id(
            "grid-inferred-blank",
            lane.domain.lane_id,
            lane_ordinal,
            safe,
            protected,
        ),
        lane_id=lane.domain.lane_id,
        lane_ordinal=lane_ordinal,
        source_safe_box=safe,
        source_protected_box=protected,
        grid_translation=grid_translation,
        saturated_sides=saturated,
    )
