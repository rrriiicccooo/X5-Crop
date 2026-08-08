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


def debug_status_parts(
    detection: FinalDetection,
    style: DebugStyleParameters,
    terminal_outcome: RunTerminalOutcome,
) -> tuple[str, str, tuple[int, int, int]]:
    if terminal_outcome == RunTerminalOutcome.RUNTIME_ERROR:
        return (
            "RUNTIME ERROR",
            (
                "terminal_outcome: runtime_error"
                f" | decision_status: {detection.decision.status}"
            ),
            style.review_color,
        )
    status = (
        "APPROVED"
        if detection.decision.status == "approved_auto"
        else "REVIEW"
    )
    detail = f"status: {detection.decision.status}"
    color = (
        style.approved_color
        if detection.decision.status == "approved_auto"
        else style.review_color
    )
    reasons = detection.decision.final_review_reasons
    if reasons:
        detail += " | " + ", ".join(reasons[: style.reason_display_limit])
    if not detection.frame_export_eligible:
        detail += " | NOT EXPORTABLE"
    return status, detail, color


def draw_large_status(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    color: tuple[int, int, int],
    fallback_size: tuple[int, int],
    stroke_width: int,
    font_size: int,
) -> tuple[int, int]:
    x, y = xy
    draw.text(
        (x, y),
        text,
        fill=color,
        font=ImageFont.load_default(size=font_size),
        stroke_width=stroke_width,
        stroke_fill=color,
    )
    try:
        bbox = draw.textbbox(
            (x, y),
            text,
            font=ImageFont.load_default(size=font_size),
            stroke_width=stroke_width,
        )
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
    except Exception:
        width = len(text) * fallback_size[0]
        height = fallback_size[1]
    return width, height


def add_status_bar(
    rgb: np.ndarray,
    detection: FinalDetection,
    configuration: DetectionConfiguration,
    profile: ImageProfile,
    style: DebugStyleParameters,
    terminal_outcome: RunTerminalOutcome,
) -> np.ndarray:
    status, detail, color = debug_status_parts(
        detection,
        style,
        terminal_outcome,
    )
    bar_h = style.status_bar_height
    h, w = rgb.shape[:2]
    panel = np.full(
        (h + bar_h, w, RGB_CHANNEL_COUNT),
        style.dark_background,
        dtype=np.uint8,
    )
    panel[bar_h:, :, :] = rgb
    image = Image.fromarray(panel, mode="RGB")
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        (0, 0, w - 1, bar_h - 1),
        outline=color,
        width=style.status_outline_width,
    )
    status_w, _ = draw_large_status(
        draw,
        style.status_origin,
        status,
        color,
        style.text_fallback_size,
        style.status_text_stroke_width,
        style.status_label_font_size,
    )
    count_request = configuration.count_request
    count_authority = (
        count_request.mode.value
        if count_request.authoritative_count is None
        else (
            f"{count_request.mode.value}:"
            f"{count_request.authoritative_count}"
        )
    )
    context = (
        f"{SCRIPT_NAME} {VERSION} · "
        f"{configuration.physical_spec.format_id}/"
        f"{configuration.strip_mode} · count={count_authority} · "
        f"slots={detection.output_slot_count or 0} · "
        f"ORIENTATION {profile.orientation.original_tag}>CANONICAL>1"
    )
    draw.text(
        (
            style.status_origin[0] + status_w + style.detail_gap,
            style.detail_baseline,
        ),
        context,
        fill=style.text_color,
        font=ImageFont.load_default(size=style.status_detail_font_size),
    )
    decision_y = style.detail_baseline + 27
    draw.text(
        (
            style.status_origin[0] + status_w + style.detail_gap,
            decision_y,
        ),
        detail,
        fill=style.text_color,
        font=ImageFont.load_default(size=style.status_detail_font_size),
    )
    transform = detection.transform_assessment
    interval = transform.observed_angle_interval_degrees
    if interval is None:
        transform_text = "DIRECTION UNAVAILABLE"
    elif transform.outcome == "identity":
        transform_text = (
            "TRANSFORM IDENTITY +0.000° · "
            f"DIRECTION [{interval.minimum:+.3f}°, "
            f"{interval.maximum:+.3f}°]"
        )
    else:
        transform_text = (
            f"DESKEW APPLIED {transform.applied_source_rotation_degrees:+.3f}° · "
            f"DIRECTION [{interval.minimum:+.3f}°, "
            f"{interval.maximum:+.3f}°]"
        )
    try:
        transform_box = draw.textbbox(
            (0, 0),
            transform_text,
            font=ImageFont.load_default(size=style.status_detail_font_size),
        )
        transform_width = transform_box[2] - transform_box[0]
    except Exception:
        transform_width = len(transform_text) * style.text_fallback_size[0]
    transform_x = max(8, w - transform_width - 12)
    draw.rectangle(
        (
            transform_x - 4,
            style.detail_baseline - 2,
            w - 8,
            style.detail_baseline + style.status_detail_font_size + 4,
        ),
        fill=style.dark_background,
    )
    draw.text(
        (transform_x, style.detail_baseline),
        transform_text,
        fill=style.inferred_direction_color,
        font=ImageFont.load_default(size=style.status_detail_font_size),
        stroke_width=1,
        stroke_fill=style.dark_background,
    )
    atomic_text = (
        f"SOURCE ATOMIC · {detection.output_slot_count} TIFF ELIGIBLE"
        if detection.frame_export_eligible
        else "SOURCE ATOMIC · 0 OFFICIAL TIFF"
    )
    try:
        atomic_box = draw.textbbox(
            (0, 0),
            atomic_text,
            font=ImageFont.load_default(size=style.status_detail_font_size),
        )
        atomic_width = atomic_box[2] - atomic_box[0]
    except Exception:
        atomic_width = len(atomic_text) * style.text_fallback_size[0]
    atomic_x = max(8, w - atomic_width - 12)
    draw.rectangle(
        (
            atomic_x - 4,
            decision_y - 2,
            w - 8,
            decision_y + style.status_detail_font_size + 4,
        ),
        fill=style.dark_background,
    )
    draw.text(
        (atomic_x, decision_y),
        atomic_text,
        fill=color,
        font=ImageFont.load_default(size=style.status_detail_font_size),
        stroke_width=1,
        stroke_fill=style.dark_background,
    )
    return np.asarray(image)
