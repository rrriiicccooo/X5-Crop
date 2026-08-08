from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ..app_info import SCRIPT_NAME, VERSION
from ..configuration.diagnostics import DebugStyleParameters
from ..configuration.model import DetectionConfiguration
from ..detection.final.model import FinalDetection
from ..io.model import ImageProfile
from ..run_status import RunTerminalOutcome
from ..utils import RGB_CHANNEL_COUNT


def _font(size: int) -> ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def _text_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def debug_status_parts(
    detection: FinalDetection,
    style: DebugStyleParameters,
    terminal_outcome: RunTerminalOutcome,
) -> tuple[str, str, tuple[int, int, int]]:
    if terminal_outcome == RunTerminalOutcome.RUNTIME_ERROR:
        return "RUNTIME ERROR", "runtime_error · NOT EXPORTABLE", style.review_color
    if detection.decision.status == "approved_auto":
        return "APPROVED", "approved_auto · EXPORT ELIGIBLE", style.approved_color
    reasons = detection.decision.final_review_reasons
    reason = (
        " · ".join(reasons[: style.reason_display_limit])
        if reasons
        else detection.decision.status
    )
    return "REVIEW", f"{reason} · NOT EXPORTABLE", style.review_color


def _count_authority(configuration: DetectionConfiguration) -> str:
    request = configuration.count_request
    if request.authoritative_count is None:
        return request.mode.value
    return f"{request.mode.value}:{request.authoritative_count}"


def _transform_lines(
    detection: FinalDetection,
    profile: ImageProfile,
) -> tuple[str, str]:
    transform = detection.transform_assessment
    interval = transform.observed_angle_interval_degrees
    if interval is None:
        first = "V5 · DIRECTION UNAVAILABLE"
        second = (
            f"ORIENTATION {profile.orientation.original_tag}>CANONICAL>1"
        )
    else:
        action = (
            "TRANSFORM IDENTITY"
            if transform.outcome == "identity"
            else "DESKEW APPLIED"
        )
        first = (
            f"V5 · {action} "
            f"{transform.applied_source_rotation_degrees:+.3f}°"
        )
        second = (
            f"observed {interval.minimum:+.3f}°…{interval.maximum:+.3f}° · "
            f"ORIENTATION {profile.orientation.original_tag}>CANONICAL>1"
        )
    return first, second


def add_status_bar(
    rgb: np.ndarray,
    detection: FinalDetection,
    configuration: DetectionConfiguration,
    profile: ImageProfile,
    style: DebugStyleParameters,
    terminal_outcome: RunTerminalOutcome,
) -> np.ndarray:
    if rgb.shape[1] != style.canvas_width:
        raise ValueError("Debug Analysis status width is not canonical")
    height, width = rgb.shape[:2]
    panel = np.full(
        (height + style.status_bar_height, width, RGB_CHANNEL_COUNT),
        style.canvas_background,
        dtype=np.uint8,
    )
    panel[style.status_bar_height :] = rgb
    image = Image.fromarray(panel, mode="RGB")
    draw = ImageDraw.Draw(image)
    status, detail, status_color = debug_status_parts(
        detection,
        style,
        terminal_outcome,
    )
    chip = (16, 12, 154, 52)
    draw.rounded_rectangle(
        chip,
        radius=6,
        fill=status_color,
        outline=tuple(min(255, channel + 34) for channel in status_color),
        width=1,
    )
    status_font = _font(style.header_status_font_size)
    status_width = _text_width(draw, status, status_font)
    draw.text(
        ((chip[0] + chip[2] - status_width) // 2, 22),
        status,
        fill=(255, 255, 255),
        font=status_font,
    )
    detail_font = _font(style.header_detail_font_size)
    draw.text((178, 18), detail, fill=style.text_color, font=detail_font)
    context = (
        f"{configuration.physical_spec.format_id}/{configuration.strip_mode} · "
        f"count={_count_authority(configuration)} · "
        f"slots={detection.output_slot_count or 0}"
    )
    draw.text(
        (178, 39),
        context,
        fill=style.secondary_text_color,
        font=detail_font,
    )
    runtime_chip = (1490, 16, width - 16, 50)
    draw.rounded_rectangle(
        runtime_chip,
        radius=4,
        outline=style.panel_border_color,
        width=1,
    )
    runtime_text = f"{SCRIPT_NAME} {VERSION}"
    runtime_font = _font(style.annotation_font_size)
    runtime_width = _text_width(draw, runtime_text, runtime_font)
    draw.text(
        (
            (runtime_chip[0] + runtime_chip[2] - runtime_width) // 2,
            26,
        ),
        runtime_text,
        fill=style.secondary_text_color,
        font=runtime_font,
    )
    first, second = _transform_lines(detection, profile)
    transform_right = runtime_chip[0] - 16
    for text, y, color in (
        (first, 16, style.text_color),
        (second, 38, style.secondary_text_color),
    ):
        text_width = _text_width(draw, text, detail_font)
        draw.text(
            (transform_right - text_width, y),
            text,
            fill=color,
            font=detail_font,
        )
    return np.asarray(image)
