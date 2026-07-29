from __future__ import annotations


FINAL_REASON_FRAME_GRID_AUTHORITY_UNAVAILABLE = (
    "frame_grid_authority_unavailable"
)
FINAL_REASON_SCAN_CANVAS_AUTHORITY_UNAVAILABLE = (
    "scan_canvas_authority_unavailable"
)
FINAL_REASON_SOURCE_CONTENT_MEASUREMENT_UNAVAILABLE = (
    "source_content_measurement_unavailable"
)


FINAL_REVIEW_REASONS = frozenset(
    {
        FINAL_REASON_FRAME_GRID_AUTHORITY_UNAVAILABLE,
        FINAL_REASON_SCAN_CANVAS_AUTHORITY_UNAVAILABLE,
        FINAL_REASON_SOURCE_CONTENT_MEASUREMENT_UNAVAILABLE,
    }
)
