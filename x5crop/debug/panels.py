from __future__ import annotations

from typing import Any, Optional

import numpy as np

from ..domain import Box, FinalDetection
from ..cache.separator import cached_separator_evidence_crop
from ..image.evidence import (
    SeparatorEvidenceImageParameters,
    make_separator_evidence_gray,
)
from ..policies.runtime.policy import DetectionPolicy
from ..policies.runtime.diagnostics import RuntimeDiagnosticsPolicy
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
    detection: FinalDetection,
    cache: Optional[AnalysisCache],
) -> np.ndarray:
    rgb, scale = cached_preview_gray(cache, "original_gray", gray)
    for index, box in enumerate(detection.frames):
        color = FRAME_FILL_COLORS[index % len(FRAME_FILL_COLORS)]
        fill_preview_rect(rgb, box, scale, color, 0.26)
        draw_preview_rect(rgb, box, scale, color, 1)
    draw_preview_rect(rgb, detection.outer, scale, (0, 255, 0), 3)
    return rgb


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
    detection: FinalDetection,
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
    detection: FinalDetection,
    params: SeparatorEvidenceImageParameters,
    cache: Optional[AnalysisCache],
) -> np.ndarray:
    if cache is not None and cache.layout == detection.layout:
        full_work = Box(0, 0, cache.gray_work.shape[1], cache.gray_work.shape[0])
        evidence = cached_separator_evidence_crop(cache, cache.gray_work, full_work, params)
        if evidence.size:
            return work_evidence_to_original_shape(evidence, gray, detection.layout)
    return make_separator_evidence_gray(
        gray,
        params,
    )


def make_separator_evidence_debug_rgb(
    gray: np.ndarray,
    detection: FinalDetection,
    debug_gap: Any,
    params: SeparatorEvidenceImageParameters,
    cache: Optional[AnalysisCache],
) -> np.ndarray:
    evidence = make_separator_evidence_debug_gray(gray, detection, params, cache)
    rgb, scale = cached_preview_gray(cache, "separator_evidence_full", evidence)
    draw_evidence_context_overlay(rgb, detection, scale)
    draw_gap_overlay(rgb, detection, scale, debug_gap)
    return rgb


def make_debug_analysis_panel(
    gray: np.ndarray,
    detection: FinalDetection,
    threshold: float,
    policy: DetectionPolicy,
    cache: Optional[AnalysisCache],
) -> np.ndarray:
    diagnostics: RuntimeDiagnosticsPolicy = policy.diagnostics
    debug_gap = diagnostics.debug_gap_overlay
    panel_builders = {
        "original_gray": lambda title: cached_labeled_preview_gray(cache, "original_gray", title, gray)[0],
        "debug_boxes": lambda title: add_panel_label(make_debug_preview_rgb(gray, detection, cache), title),
        "separator_evidence": lambda title: add_panel_label(
            make_separator_evidence_debug_rgb(
                gray,
                detection,
                debug_gap,
                policy.preprocess.separator_evidence_image,
                cache,
            ),
            title,
        ),
    }
    panels = [
        panel_builders[name](diagnostics.debug_panel_title(name))
        for name in diagnostics.debug_panels
    ]
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
