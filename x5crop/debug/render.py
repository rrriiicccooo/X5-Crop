from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Optional

import numpy as np
from PIL import Image, ImageDraw

from ..app_info import SCRIPT_NAME, VERSION
from ..constants import HARD_GAP_METHODS
from ..domain import Box, Detection, Gap
from ..image.evidence import make_separator_evidence_gray
from ..runtime import AnalysisCache
from ..utils import clamp_float
from ..geometry import cached_separator_evidence_crop
from ..detection.diagnostics import gap_diagnostic_record
from ..policies.registry import get_detection_policy

def preview_gray(gray: np.ndarray, max_side: int = 1800) -> tuple[np.ndarray, float]:
    h, w = gray.shape
    scale = min(1.0, float(max_side) / float(max(h, w)))
    if scale < 1.0:
        step = max(1, int(math.ceil(1.0 / scale)))
        small = gray[::step, ::step]
        actual_scale = float(small.shape[1]) / float(w)
    else:
        small = gray
        actual_scale = 1.0
    rgb = np.repeat(small[..., None], 3, axis=2).astype(np.uint8, copy=False)
    return rgb, actual_scale


def cached_preview_gray(cache: Optional[AnalysisCache], key: str, gray: np.ndarray, max_side: int = 1800) -> tuple[np.ndarray, float]:
    if cache is None:
        return preview_gray(gray, max_side)
    cache_key = (str(key), int(max_side))
    cached = cache.preview_rgb_cache.get(cache_key)
    if cached is None:
        rgb, scale = preview_gray(gray, max_side)
        cache.preview_rgb_cache[cache_key] = (rgb.copy(), float(scale))
        return rgb, scale
    rgb, scale = cached
    return rgb.copy(), float(scale)


def cached_labeled_preview_gray(cache: Optional[AnalysisCache], key: str, label: str, gray: np.ndarray, max_side: int = 1800) -> tuple[np.ndarray, float]:
    if cache is None:
        rgb, scale = preview_gray(gray, max_side)
        return add_panel_label(rgb, label), scale
    cache_key = (str(key), str(label), int(max_side))
    cached = cache.panel_label_cache.get(cache_key)
    if cached is None:
        rgb, scale = cached_preview_gray(cache, key, gray, max_side)
        labeled = add_panel_label(rgb, label)
        cache.panel_label_cache[cache_key] = labeled.copy()
        return labeled, scale
    preview = cache.preview_rgb_cache.get((str(key), int(max_side)))
    scale = float(preview[1]) if preview is not None else 1.0
    return cached.copy(), float(scale)


def draw_preview_rect(rgb: np.ndarray, box: Box, scale: float, color: tuple[int, int, int], thickness: int = 2) -> None:
    h, w = rgb.shape[:2]
    left = max(0, min(w - 1, int(round(box.left * scale))))
    right = max(0, min(w, int(round(box.right * scale))))
    top = max(0, min(h - 1, int(round(box.top * scale))))
    bottom = max(0, min(h, int(round(box.bottom * scale))))
    if right <= left or bottom <= top:
        return
    t = max(1, int(thickness))
    rgb[top:min(bottom, top + t), left:right] = color
    rgb[max(top, bottom - t):bottom, left:right] = color
    rgb[top:bottom, left:min(right, left + t)] = color
    rgb[top:bottom, max(left, right - t):right] = color


FRAME_FILL_COLORS = (
    (30, 144, 255),
    (255, 120, 40),
    (80, 200, 120),
    (210, 90, 255),
    (255, 210, 40),
    (40, 210, 220),
    (255, 90, 120),
    (150, 170, 255),
)


def fill_preview_rect(rgb: np.ndarray, box: Box, scale: float, color: tuple[int, int, int], alpha: float = 0.24) -> None:
    h, w = rgb.shape[:2]
    left = max(0, min(w - 1, int(round(box.left * scale))))
    right = max(0, min(w, int(round(box.right * scale))))
    top = max(0, min(h - 1, int(round(box.top * scale))))
    bottom = max(0, min(h, int(round(box.bottom * scale))))
    if right <= left or bottom <= top:
        return
    overlay = np.array(color, dtype=np.float32)
    region = rgb[top:bottom, left:right].astype(np.float32, copy=False)
    rgb[top:bottom, left:right] = np.clip(region * (1.0 - alpha) + overlay * alpha, 0, 255).astype(np.uint8)


def draw_preview_line(rgb: np.ndarray, box: Box, scale: float, color: tuple[int, int, int], thickness: int = 2) -> None:
    h, w = rgb.shape[:2]
    x = max(0, min(w - 1, int(round(box.left * scale))))
    top = max(0, min(h - 1, int(round(box.top * scale))))
    bottom = max(0, min(h, int(round(box.bottom * scale))))
    if bottom <= top:
        return
    t = max(1, int(thickness))
    rgb[top:bottom, max(0, x - t // 2):min(w, x + (t + 1) // 2)] = color


def draw_preview_hline(rgb: np.ndarray, box: Box, scale: float, color: tuple[int, int, int], thickness: int = 2) -> None:
    h, w = rgb.shape[:2]
    y = max(0, min(h - 1, int(round(box.top * scale))))
    left = max(0, min(w - 1, int(round(box.left * scale))))
    right = max(0, min(w, int(round(box.right * scale))))
    if right <= left:
        return
    t = max(1, int(thickness))
    rgb[max(0, y - t // 2):min(h, y + (t + 1) // 2), left:right] = color


def draw_preview_mark(rgb: np.ndarray, box: Box, scale: float, color: tuple[int, int, int], thickness: int = 2) -> None:
    if box.width > 1 or box.height > 1:
        draw_preview_rect(rgb, box, scale, color, thickness)
    else:
        draw_preview_line(rgb, box, scale, color, thickness)


def gap_mark_box(detection: Detection, gap: Gap) -> Optional[Box]:
    work_outer_raw = gap.lane_box if isinstance(gap.lane_box, dict) else detection.detail.get("work_outer")
    if not isinstance(work_outer_raw, dict):
        return None
    try:
        work_outer = Box(
            int(work_outer_raw["left"]),
            int(work_outer_raw["top"]),
            int(work_outer_raw["right"]),
            int(work_outer_raw["bottom"]),
        )
    except Exception:
        return None
    if gap.method in HARD_GAP_METHODS and gap.start is not None and gap.end is not None:
        start = int(round(work_outer.left + min(gap.start, gap.end)))
        end = int(round(work_outer.left + max(gap.start, gap.end)))
        if end <= start:
            end = start + 1
        if detection.layout == "horizontal":
            return Box(start, work_outer.top, end, work_outer.bottom)
        return Box(work_outer.top, start, work_outer.bottom, end)

    x = int(round(work_outer.left + gap.center))
    if detection.layout == "horizontal":
        return Box(x, work_outer.top, x + 1, work_outer.bottom)
    return Box(work_outer.top, x, work_outer.bottom, x + 1)


def gap_tick_boxes(detection: Detection, gap: Gap, debug_gap: Any) -> list[Box]:
    work_outer_raw = gap.lane_box if isinstance(gap.lane_box, dict) else detection.detail.get("work_outer")
    if not isinstance(work_outer_raw, dict):
        return []
    try:
        work_outer = Box(
            int(work_outer_raw["left"]),
            int(work_outer_raw["top"]),
            int(work_outer_raw["right"]),
            int(work_outer_raw["bottom"]),
        )
    except Exception:
        return []
    tick_axis = work_outer.height if detection.layout == "horizontal" else work_outer.width
    tick = max(
        int(debug_gap.tick_length_min),
        int(round(tick_axis * float(debug_gap.tick_length_ratio))),
    )
    if detection.layout == "horizontal":
        x = int(round(work_outer.left + gap.center))
        return [
            Box(x, work_outer.top, x + 1, min(work_outer.bottom, work_outer.top + tick)),
            Box(x, max(work_outer.top, work_outer.bottom - tick), x + 1, work_outer.bottom),
        ]
    y = int(round(work_outer.left + gap.center))
    return [
        Box(work_outer.top, y, min(work_outer.bottom, work_outer.top + tick), y + 1),
        Box(max(work_outer.top, work_outer.bottom - tick), y, work_outer.bottom, y + 1),
    ]


def debug_status_parts(detection: Detection, threshold: float) -> tuple[str, str, tuple[int, int, int]]:
    passed = detection.confidence >= threshold
    status = "PASS" if passed else "REVIEW"
    op = ">=" if passed else "<"
    detail = f"confidence {detection.confidence:.3f} {op} threshold {threshold:.3f}"
    if detection.review_reasons:
        detail += " | " + ",".join(detection.review_reasons[:3])
    color = (40, 180, 90) if passed else (230, 80, 70)
    return status, detail, color


def draw_large_status(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, color: tuple[int, int, int]) -> tuple[int, int]:
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


def write_debug_preview(gray: np.ndarray, detection: Detection, output_path: Path, threshold: float, cache: Optional[AnalysisCache] = None) -> None:
    rgb = add_status_bar(make_debug_preview_rgb(gray, detection, cache), detection, threshold)
    write_rgb_jpeg(rgb, output_path)


def make_debug_preview_rgb(gray: np.ndarray, detection: Detection, cache: Optional[AnalysisCache] = None) -> np.ndarray:
    rgb, scale = cached_preview_gray(cache, "original_gray", gray)
    for index, box in enumerate(detection.frames):
        color = FRAME_FILL_COLORS[index % len(FRAME_FILL_COLORS)]
        fill_preview_rect(rgb, box, scale, color, 0.26)
        draw_preview_rect(rgb, box, scale, color, 1)
    draw_preview_rect(rgb, detection.outer, scale, (0, 255, 0), 3)
    return rgb


def box_from_debug_value(value: Any) -> Optional[Box]:
    if not isinstance(value, dict):
        return None
    box_value = value.get("box") if isinstance(value.get("box"), dict) else value
    try:
        return Box(
            int(box_value["left"]),
            int(box_value["top"]),
            int(box_value["right"]),
            int(box_value["bottom"]),
        )
    except Exception:
        return None


def make_outer_candidates_rgb(gray: np.ndarray, detection: Detection, cache: Optional[AnalysisCache] = None) -> np.ndarray:
    rgb, scale = cached_preview_gray(cache, "outer_candidates", gray)
    candidates = detection.detail.get("outer_candidates", [])
    if isinstance(candidates, list):
        for index, candidate in enumerate(candidates[:16]):
            box = box_from_debug_value(candidate)
            if box is None:
                continue
            color = FRAME_FILL_COLORS[index % len(FRAME_FILL_COLORS)]
            draw_preview_rect(rgb, box, scale, color, 1)
    draw_preview_rect(rgb, detection.outer, scale, (0, 255, 0), 3)
    return rgb


def make_frame_geometry_rgb(gray: np.ndarray, detection: Detection, cache: Optional[AnalysisCache] = None) -> np.ndarray:
    rgb, scale = cached_preview_gray(cache, "frame_geometry", gray)
    draw_preview_rect(rgb, detection.outer, scale, (0, 255, 0), 2)
    for index, box in enumerate(detection.frames):
        color = FRAME_FILL_COLORS[index % len(FRAME_FILL_COLORS)]
        fill_preview_rect(rgb, box, scale, color, 0.18)
        draw_preview_rect(rgb, box, scale, color, 2)
    draw_gap_overlay(rgb, detection, scale)
    return rgb


def add_review_lines(rgb: np.ndarray, lines: list[str]) -> np.ndarray:
    if not lines:
        return rgb
    h, w = rgb.shape[:2]
    line_h = 18
    pad = 10
    panel_h = min(h, pad * 2 + line_h * min(len(lines), 6))
    image = Image.fromarray(rgb, mode="RGB")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, h - panel_h, w - 1, h - 1), fill=(18, 18, 18))
    for index, line in enumerate(lines[:6]):
        draw.text((pad, h - panel_h + pad + index * line_h), line, fill=(245, 245, 245))
    return np.asarray(image)


def make_risk_review_rgb(gray: np.ndarray, detection: Detection, cache: Optional[AnalysisCache] = None) -> np.ndarray:
    rgb = make_frame_geometry_rgb(gray, detection, cache)
    decision = detection.detail.get("v4_9_decision", {})
    risk = detection.detail.get("risk_summary", {})
    lines = [
        f"policy: {detection.detail.get('policy_id', '')}",
        "reasons: " + (",".join(detection.review_reasons[:4]) if detection.review_reasons else "none"),
    ]
    if isinstance(decision, dict):
        lines.append(f"v4.9 pass: {bool(decision.get('pass', False))}")
    if isinstance(risk, dict):
        active = [key for key, value in risk.items() if isinstance(value, bool) and value]
        lines.append("risks: " + (",".join(active[:4]) if active else "none"))
    return add_review_lines(rgb, lines)


def draw_gap_overlay(rgb: np.ndarray, detection: Detection, scale: float) -> None:
    debug_gap = get_detection_policy(detection.film_format, detection.strip_mode).diagnostics.debug_gap_overlay
    gap_colors = {
        "detected": (255, 0, 0),
        "edge-pair": (255, 0, 0),
        "wide-separator": (255, 70, 70),
        "enhanced-detected": (255, 140, 0),
        "grid": (255, 220, 30),
        "equal": (190, 80, 255),
    }
    pitch = float(detection.detail.get("pitch", 0.0) or 0.0)
    detected_centers = [gap.center for gap in detection.gaps if gap.method in HARD_GAP_METHODS]
    overlap_tolerance = clamp_float(
        pitch * debug_gap.overlap_tolerance_ratio,
        debug_gap.overlap_tolerance_min,
        debug_gap.overlap_tolerance_max,
    )
    for gap in detection.gaps:
        if gap.method not in HARD_GAP_METHODS:
            continue
        mark = gap_mark_box(detection, gap)
        if mark is not None:
            draw_preview_mark(rgb, mark, scale, gap_colors.get(gap.method, (255, 255, 255)), debug_gap.hard_line_width)
    for gap in detection.gaps:
        if gap.method in HARD_GAP_METHODS:
            continue
        if any(abs(gap.center - center) <= overlap_tolerance for center in detected_centers):
            continue
        color = gap_colors.get(gap.method, (255, 255, 255))
        for tick in gap_tick_boxes(detection, gap, debug_gap):
            if detection.layout == "horizontal":
                draw_preview_line(rgb, tick, scale, color, debug_gap.model_line_width)
            else:
                draw_preview_hline(rgb, tick, scale, color, debug_gap.model_line_width)
    draw_gap_diagnostic_overlay(rgb, detection, scale)


def draw_gap_diagnostic_overlay(rgb: np.ndarray, detection: Detection, scale: float) -> None:
    debug_gap = get_detection_policy(detection.film_format, detection.strip_mode).diagnostics.debug_gap_overlay
    diagnostics = detection.detail.get("diagnostics")
    records: Any = None
    if isinstance(diagnostics, dict):
        records = diagnostics.get("gap_diagnostics", [])
    if not isinstance(records, list):
        overlap_bleed = detection.detail.get("overlap_bleed_risk")
        if isinstance(overlap_bleed, dict):
            records = overlap_bleed.get("gap_diagnostics", [])
    if not isinstance(records, list):
        return
    gaps_by_index = {gap.index: gap for gap in detection.gaps}
    for record in records:
        if not isinstance(record, dict):
            continue
        gap = gaps_by_index.get(int(record.get("index", -1)))
        if gap is None:
            continue
        color: Optional[tuple[int, int, int]] = None
        if record.get("hard_trust") in {
            "suspect_internal_edge",
            "suspect_frame_border",
            "nearby_separator_conflict",
            "geometry_conflict",
        }:
            color = (255, 0, 220)
        elif str(record.get("overlap_risk", "none")) in {"medium", "strong"}:
            color = (0, 220, 255)
        if color is None:
            continue
        for tick in gap_tick_boxes(detection, gap, debug_gap):
            if detection.layout == "horizontal":
                draw_preview_line(rgb, tick, scale, color, debug_gap.diagnostic_line_width)
            else:
                draw_preview_hline(rgb, tick, scale, color, debug_gap.diagnostic_line_width)


def work_evidence_to_original_shape(evidence_work: np.ndarray, gray: np.ndarray, layout: str) -> np.ndarray:
    patch = evidence_work if layout == "horizontal" else evidence_work.T
    if patch.shape == gray.shape:
        return patch.astype(np.uint8, copy=False)
    out = np.full(gray.shape, 235, dtype=np.uint8)
    ph = min(out.shape[0], patch.shape[0])
    pw = min(out.shape[1], patch.shape[1])
    if ph > 0 and pw > 0:
        out[:ph, :pw] = patch[:ph, :pw]
    return out


def draw_evidence_context_overlay(rgb: np.ndarray, detection: Detection, scale: float, include_frames: bool = False) -> None:
    draw_preview_rect(rgb, detection.outer, scale, (0, 255, 0), 2)
    if include_frames:
        for index, box in enumerate(detection.frames):
            color = FRAME_FILL_COLORS[index % len(FRAME_FILL_COLORS)]
            draw_preview_rect(rgb, box, scale, color, 1)


def make_separator_evidence_debug_gray(gray: np.ndarray, detection: Detection, cache: Optional[AnalysisCache] = None) -> np.ndarray:
    if cache is not None and cache.layout == detection.layout:
        full_work = Box(0, 0, cache.gray_work.shape[1], cache.gray_work.shape[0])
        evidence = cached_separator_evidence_crop(cache, cache.gray_work, full_work)
        if evidence.size:
            return work_evidence_to_original_shape(evidence, gray, detection.layout)
    return make_separator_evidence_gray(gray)


def make_separator_evidence_debug_rgb(gray: np.ndarray, detection: Detection, cache: Optional[AnalysisCache] = None) -> np.ndarray:
    evidence = make_separator_evidence_debug_gray(gray, detection, cache)
    rgb, scale = cached_preview_gray(cache, "separator_evidence_full", evidence)
    draw_evidence_context_overlay(rgb, detection, scale)
    draw_gap_overlay(rgb, detection, scale)
    return rgb


def write_rgb_jpeg(rgb: np.ndarray, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.fromarray(np.ascontiguousarray(rgb), mode="RGB")
    image.save(output_path, format="JPEG", quality=92, optimize=True)


def add_panel_label(rgb: np.ndarray, label: str) -> np.ndarray:
    label_h = 34
    h, w = rgb.shape[:2]
    panel = np.full((h + label_h, w, 3), 18, dtype=np.uint8)
    panel[label_h:, :, :] = rgb
    image = Image.fromarray(panel, mode="RGB")
    draw = ImageDraw.Draw(image)
    draw.text((12, 9), label, fill=(245, 245, 245))
    return np.asarray(image)


def make_debug_analysis_panel(gray: np.ndarray, detection: Detection, threshold: float, cache: Optional[AnalysisCache] = None) -> np.ndarray:
    policy = get_detection_policy(detection.film_format, detection.strip_mode)
    diagnostics = policy.diagnostics
    panel_builders = {
        "original_gray": lambda title: cached_labeled_preview_gray(cache, "original_gray", title, gray)[0],
        "gray_context": lambda title: cached_labeled_preview_gray(cache, "original_gray", title, gray)[0],
        "debug_boxes": lambda title: add_panel_label(make_debug_preview_rgb(gray, detection, cache), title),
        "outer_candidates": lambda title: add_panel_label(make_outer_candidates_rgb(gray, detection, cache), title),
        "separator_evidence": lambda title: add_panel_label(
            make_separator_evidence_debug_rgb(gray, detection, cache),
            title,
        ),
        "frame_geometry": lambda title: add_panel_label(make_frame_geometry_rgb(gray, detection, cache), title),
        "selected_candidate": lambda title: add_panel_label(make_debug_preview_rgb(gray, detection, cache), title),
        "risk_review": lambda title: add_panel_label(make_risk_review_rgb(gray, detection, cache), title),
    }
    panels = [
        panel_builders[name](diagnostics.debug_panel_title(name))
        for name in diagnostics.debug_panels
        if name in panel_builders
    ]
    if not panels:
        panels = [panel_builders["original_gray"](diagnostics.debug_panel_title("original_gray"))]
    gap = 12
    if gray.shape[1] >= gray.shape[0]:
        max_w = max(panel.shape[1] for panel in panels)
        total_h = sum(panel.shape[0] for panel in panels) + gap * (len(panels) - 1)
        canvas = np.full((total_h, max_w, 3), 32, dtype=np.uint8)
        y = 0
        for panel in panels:
            h, w = panel.shape[:2]
            canvas[y:y + h, :w] = panel
            y += h + gap
    else:
        max_h = max(panel.shape[0] for panel in panels)
        total_w = sum(panel.shape[1] for panel in panels) + gap * (len(panels) - 1)
        canvas = np.full((max_h, total_w, 3), 32, dtype=np.uint8)
        x = 0
        for panel in panels:
            h, w = panel.shape[:2]
            canvas[:h, x:x + w] = panel
            x += w + gap
    return add_status_bar(canvas, detection, threshold)


def write_debug_analysis(
    gray: np.ndarray,
    detection: Detection,
    output_dir: Path,
    stem: str,
    threshold: float,
    cache: Optional[AnalysisCache] = None,
) -> list[str]:
    analysis_dir = output_dir / "_debug_analysis"
    panel_path = analysis_dir / f"{stem}_debug_analysis.jpg"
    write_rgb_jpeg(make_debug_analysis_panel(gray, detection, threshold, cache), panel_path)
    return [str(panel_path)]
