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


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> str:
    if max_width <= 0:
        return ""
    if _text_width(draw, text, font) <= max_width:
        return text
    suffix = "..."
    if _text_width(draw, suffix, font) > max_width:
        return ""
    low = 0
    high = len(text)
    while low < high:
        middle = (low + high + 1) // 2
        candidate = text[:middle] + suffix
        if _text_width(draw, candidate, font) <= max_width:
            low = middle
        else:
            high = middle - 1
    return text[:low] + suffix


def _source_header(source_name: str) -> str:
    printable = "".join(
        character if character.isprintable() else " "
        for character in source_name
    ).strip()
    if not printable:
        raise ValueError("Debug Analysis requires a source filename")
    return f"SOURCE · {printable}"


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


def _count_authority(detection: FinalDetection) -> str:
    resolved = detection.source_core.resolved_slot_count
    if resolved is None:
        return "unresolved"
    return (
        f"{resolved.authority.value}:"
        f"{resolved.output_count}/{resolved.full_count}"
    )


def _transform_lines(
    detection: FinalDetection,
    profile: ImageProfile,
) -> tuple[str, str]:
    transform = detection.source_transform_assessment
    interval = transform.observed_angle_interval_degrees
    applied = transform.applied_source_rotation_degrees
    if transform.outcome == "unavailable" or applied is None:
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
            f"{applied:+.3f}°"
        )
        observed = (
            "observed interval unavailable"
            if interval is None
            else (
                f"observed {interval.minimum:+.3f}°"
                f"…{interval.maximum:+.3f}°"
            )
        )
        second = (
            f"{observed} · ORIENTATION "
            f"{profile.orientation.original_tag}>CANONICAL>1"
        )
    return first, second


def add_status_bar(
    rgb: np.ndarray,
    detection: FinalDetection,
    configuration: DetectionConfiguration,
    profile: ImageProfile,
    source_name: str,
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
    holder_id = (
        "unresolved"
        if detection.source_core.matched_holder is None
        else detection.source_core.matched_holder.profile.profile_id
    )
    context = (
        f"{configuration.physical_spec.format_id}/{configuration.strip_mode} · "
        f"holder={holder_id} · "
        f"count={_count_authority(detection)} · "
        f"slots={detection.output_slot_count or 0}"
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
    transform_lines = (
        (first, 16, style.text_color),
        (second, 38, style.secondary_text_color),
    )
    transform_lefts = []
    for text, y, color in transform_lines:
        text_width = _text_width(draw, text, detail_font)
        transform_lefts.append(transform_right - text_width)
        draw.text(
            (transform_right - text_width, y),
            text,
            fill=color,
            font=detail_font,
        )
    left_text_x = 178
    clearance = 24
    source_text = _fit_text(
        draw,
        _source_header(source_name),
        detail_font,
        transform_lefts[0] - left_text_x - clearance,
    )
    draw.text(
        (left_text_x, 18),
        source_text,
        fill=style.text_color,
        font=detail_font,
    )
    detail_text = _fit_text(
        draw,
        f"{detail} · {context}",
        detail_font,
        transform_lefts[1] - left_text_x - clearance,
    )
    draw.text(
        (left_text_x, 39),
        detail_text,
        fill=style.secondary_text_color,
        font=detail_font,
    )
    return np.asarray(image)
