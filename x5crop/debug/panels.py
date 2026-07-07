from __future__ import annotations

from typing import Any, Optional

import numpy as np
from PIL import Image, ImageDraw

from ..detection.detail import RISK_SUMMARY, decision_summary, detail_dict, policy_id_from_detail
from ..domain import Box, Detection
from ..cache.separator import cached_separator_evidence_crop
from ..image.evidence import make_separator_evidence_gray
from ..policies.registry import get_detection_policy
from ..cache import AnalysisCache
from .canvas import (
    FRAME_FILL_COLORS,
    add_panel_label,
    cached_labeled_preview_gray,
    cached_preview_gray,
    draw_preview_rect,
    fill_preview_rect,
)
from .gaps import draw_gap_overlay
from .status import add_status_bar


def make_debug_preview_rgb(
    gray: np.ndarray,
    detection: Detection,
    cache: Optional[AnalysisCache] = None,
) -> np.ndarray:
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


def make_outer_candidates_rgb(
    gray: np.ndarray,
    detection: Detection,
    cache: Optional[AnalysisCache] = None,
) -> np.ndarray:
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


def make_frame_geometry_rgb(
    gray: np.ndarray,
    detection: Detection,
    cache: Optional[AnalysisCache] = None,
) -> np.ndarray:
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


def make_risk_review_rgb(
    gray: np.ndarray,
    detection: Detection,
    cache: Optional[AnalysisCache] = None,
) -> np.ndarray:
    rgb = make_frame_geometry_rgb(gray, detection, cache)
    decision = decision_summary(detection)
    risk = detail_dict(detection, RISK_SUMMARY)
    lines = [
        f"policy: {policy_id_from_detail(detection)}",
        "reasons: " + (",".join(detection.review_reasons[:4]) if detection.review_reasons else "none"),
    ]
    if decision:
        lines.append(f"decision pass: {bool(decision.get('pass', False))}")
    if risk:
        active = [key for key, value in risk.items() if isinstance(value, bool) and value]
        lines.append("risks: " + (",".join(active[:4]) if active else "none"))
    return add_review_lines(rgb, lines)


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


def draw_evidence_context_overlay(
    rgb: np.ndarray,
    detection: Detection,
    scale: float,
    include_frames: bool = False,
) -> None:
    draw_preview_rect(rgb, detection.outer, scale, (0, 255, 0), 2)
    if include_frames:
        for index, box in enumerate(detection.frames):
            color = FRAME_FILL_COLORS[index % len(FRAME_FILL_COLORS)]
            draw_preview_rect(rgb, box, scale, color, 1)


def make_separator_evidence_debug_gray(
    gray: np.ndarray,
    detection: Detection,
    cache: Optional[AnalysisCache] = None,
) -> np.ndarray:
    if cache is not None and cache.layout == detection.layout:
        full_work = Box(0, 0, cache.gray_work.shape[1], cache.gray_work.shape[0])
        evidence = cached_separator_evidence_crop(cache, cache.gray_work, full_work)
        if evidence.size:
            return work_evidence_to_original_shape(evidence, gray, detection.layout)
    return make_separator_evidence_gray(gray)


def make_separator_evidence_debug_rgb(
    gray: np.ndarray,
    detection: Detection,
    cache: Optional[AnalysisCache] = None,
) -> np.ndarray:
    evidence = make_separator_evidence_debug_gray(gray, detection, cache)
    rgb, scale = cached_preview_gray(cache, "separator_evidence_full", evidence)
    draw_evidence_context_overlay(rgb, detection, scale)
    draw_gap_overlay(rgb, detection, scale)
    return rgb


def make_debug_analysis_panel(
    gray: np.ndarray,
    detection: Detection,
    threshold: float,
    cache: Optional[AnalysisCache] = None,
) -> np.ndarray:
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
    canvas = stack_debug_panels(panels, horizontal=gray.shape[1] < gray.shape[0])
    return add_status_bar(canvas, detection, threshold)


def stack_debug_panels(panels: list[np.ndarray], horizontal: bool) -> np.ndarray:
    gap = 12
    if horizontal:
        max_h = max(panel.shape[0] for panel in panels)
        total_w = sum(panel.shape[1] for panel in panels) + gap * (len(panels) - 1)
        canvas = np.full((max_h, total_w, 3), 32, dtype=np.uint8)
        x = 0
        for panel in panels:
            h, w = panel.shape[:2]
            canvas[:h, x:x + w] = panel
            x += w + gap
        return canvas

    max_w = max(panel.shape[1] for panel in panels)
    total_h = sum(panel.shape[0] for panel in panels) + gap * (len(panels) - 1)
    canvas = np.full((total_h, max_w, 3), 32, dtype=np.uint8)
    y = 0
    for panel in panels:
        h, w = panel.shape[:2]
        canvas[y:y + h, :w] = panel
        y += h + gap
    return canvas
