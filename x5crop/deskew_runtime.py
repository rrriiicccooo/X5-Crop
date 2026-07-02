from __future__ import annotations

import math
from typing import Any

from .runtime_config import RuntimeConfig
from .domain import ImageProfile
from .formats import FormatSpec
from .geometry.layout import work_gray
from .image.deskew import choose_deskew_angle
from .image.evidence import make_gray_u8
from .image.transforms import rotate_array_expand
from .policies.parameter_registry import format_parameters
from .utils import clamp_float


def apply_deskew(
    arr: Any,
    gray: Any,
    profile: ImageProfile,
    config: RuntimeConfig,
    fmt: FormatSpec,
    warnings: list[str],
) -> tuple[Any, Any, dict[str, Any]]:
    deskew = format_parameters(fmt.name).deskew
    deskew_detail: dict[str, Any] = {"applied": False}
    if config.deskew == "off":
        return arr, gray, deskew_detail

    angle, angle_detail = choose_deskew_angle(gray, config.layout, config.analysis, deskew)
    deskew_detail.update(angle_detail)
    deskew_detail["angle"] = angle
    deskew_work_width = float(work_gray(gray, config.layout).shape[1])
    deskew_span = abs(math.tan(math.radians(angle)) * deskew_work_width)
    deskew_span_threshold = clamp_float(
        deskew_work_width * deskew.span_skip_ratio,
        deskew.span_skip_min,
        deskew.span_skip_max,
    )
    deskew_detail["span_px"] = deskew_span
    deskew_detail["span_threshold_px"] = deskew_span_threshold
    if deskew_span < deskew_span_threshold:
        deskew_detail["skipped"] = "span_below_threshold"
    elif config.deskew_min_angle <= abs(angle) <= config.deskew_max_angle:
        arr = rotate_array_expand(arr, -angle, profile.axes)
        gray = make_gray_u8(arr, profile.axes, profile.photometric)
        deskew_detail["applied"] = True
        warnings.append(f"deskew applied: {-angle:.4f} degrees")
    else:
        deskew_detail["skipped"] = "angle_out_of_range"
    return arr, gray, deskew_detail


__all__ = [
    "apply_deskew",
]
