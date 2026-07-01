from __future__ import annotations

from .canvas import (
    FRAME_FILL_COLORS,
    add_panel_label,
    cached_labeled_preview_gray,
    cached_preview_gray,
    draw_preview_hline,
    draw_preview_line,
    draw_preview_mark,
    draw_preview_rect,
    fill_preview_rect,
    preview_gray,
    write_rgb_jpeg,
)
from .gaps import draw_gap_diagnostic_overlay, draw_gap_overlay, gap_mark_box, gap_tick_boxes
from .panels import (
    add_review_lines,
    box_from_debug_value,
    draw_evidence_context_overlay,
    make_debug_analysis_panel,
    make_debug_preview_rgb,
    make_frame_geometry_rgb,
    make_outer_candidates_rgb,
    make_risk_review_rgb,
    make_separator_evidence_debug_gray,
    make_separator_evidence_debug_rgb,
    stack_debug_panels,
    work_evidence_to_original_shape,
)
from .status import add_status_bar, debug_status_parts, draw_large_status
from .writer import write_debug_analysis, write_debug_preview


__all__ = [
    "FRAME_FILL_COLORS",
    "add_panel_label",
    "add_review_lines",
    "add_status_bar",
    "box_from_debug_value",
    "cached_labeled_preview_gray",
    "cached_preview_gray",
    "debug_status_parts",
    "draw_evidence_context_overlay",
    "draw_gap_diagnostic_overlay",
    "draw_gap_overlay",
    "draw_large_status",
    "draw_preview_hline",
    "draw_preview_line",
    "draw_preview_mark",
    "draw_preview_rect",
    "fill_preview_rect",
    "gap_mark_box",
    "gap_tick_boxes",
    "make_debug_analysis_panel",
    "make_debug_preview_rgb",
    "make_frame_geometry_rgb",
    "make_outer_candidates_rgb",
    "make_risk_review_rgb",
    "make_separator_evidence_debug_gray",
    "make_separator_evidence_debug_rgb",
    "preview_gray",
    "stack_debug_panels",
    "work_evidence_to_original_shape",
    "write_debug_analysis",
    "write_debug_preview",
    "write_rgb_jpeg",
]
