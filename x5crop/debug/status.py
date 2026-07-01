from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from ..app_info import SCRIPT_NAME, VERSION
from ..detection_detail import decision_summary
from ..domain import Detection


def debug_status_parts(detection: Detection, threshold: float) -> tuple[str, str, tuple[int, int, int]]:
    decision = decision_summary(detection)
    status_value = str(decision.get("status", "") or "")
    if status_value:
        passed = status_value == "approved_auto"
        source = "decision"
    else:
        passed = detection.confidence >= threshold and not detection.review_reasons
        status_value = "approved_auto" if passed else "needs_review"
        source = "fallback"
    status = "PASS" if passed else "REVIEW"
    detail = (
        f"{source} status {status_value}; "
        f"confidence {detection.confidence:.3f}; threshold {threshold:.3f}"
    )
    if detection.review_reasons:
        detail += " | " + ",".join(detection.review_reasons[:3])
    color = (40, 180, 90) if passed else (230, 80, 70)
    return status, detail, color


def draw_large_status(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    color: tuple[int, int, int],
) -> tuple[int, int]:
    x, y = xy
    offsets = ((0, 0), (1, 0), (0, 1), (1, 1), (2, 0), (0, 2))
    for dx, dy in offsets:
        draw.text((x + dx, y + dy), text, fill=color)
    try:
        bbox = draw.textbbox((x, y), text)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
    except Exception:
        width = len(text) * 8
        height = 12
    return width + 3, height + 3


def add_status_bar(rgb: np.ndarray, detection: Detection, threshold: float) -> np.ndarray:
    status, detail, color = debug_status_parts(detection, threshold)
    detail = f"{SCRIPT_NAME} {VERSION} | {detail}"
    bar_h = 48
    h, w = rgb.shape[:2]
    panel = np.full((h + bar_h, w, 3), 18, dtype=np.uint8)
    panel[bar_h:, :, :] = rgb
    image = Image.fromarray(panel, mode="RGB")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, w - 1, bar_h - 1), outline=color, width=2)
    status_w, _ = draw_large_status(draw, (12, 10), status, color)
    draw.text((12 + status_w + 14, 17), detail, fill=(245, 245, 245))
    return np.asarray(image)

