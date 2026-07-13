from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from ..app_info import SCRIPT_NAME, VERSION
from ..configuration.diagnostics import DebugStyleParameters
from ..detection.final.model import FinalDetection
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
    passed = detection.decision.status == "approved_auto"
    status = "PASS" if passed else "REVIEW"
    detail = f"status: {detection.decision.status}"
    color = style.pass_color if passed else style.review_color
    reasons = detection.decision.final_review_reasons
    if reasons:
        detail += " | " + ",".join(reasons[: style.reason_display_limit])
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
) -> tuple[int, int]:
    x, y = xy
    draw.text(
        (x, y),
        text,
        fill=color,
        stroke_width=stroke_width,
        stroke_fill=color,
    )
    try:
        bbox = draw.textbbox((x, y), text, stroke_width=stroke_width)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
    except Exception:
        width = len(text) * fallback_size[0]
        height = fallback_size[1]
    return width, height


def add_status_bar(
    rgb: np.ndarray,
    detection: FinalDetection,
    style: DebugStyleParameters,
    terminal_outcome: RunTerminalOutcome,
) -> np.ndarray:
    status, detail, color = debug_status_parts(
        detection,
        style,
        terminal_outcome,
    )
    detail = f"{SCRIPT_NAME} {VERSION} | {detail}"
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
    )
    draw.text(
        (
            style.status_origin[0] + status_w + style.detail_gap,
            style.detail_baseline,
        ),
        detail,
        fill=style.text_color,
    )
    return np.asarray(image)
