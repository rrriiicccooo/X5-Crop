"""Local, source-bound human annotation tools for X5 Crop calibration."""

from .model import (
    ANNOTATION_SCHEMA,
    BASELINE_SCHEMA,
    canonical_record_sha256,
    confirmed_baseline_rows,
    evaluation_role_summary,
    frame_polygons_display,
    frame_state_summary,
    line_basis_summary,
    validate_annotation_record,
)
__all__ = (
    "ANNOTATION_SCHEMA",
    "BASELINE_SCHEMA",
    "canonical_record_sha256",
    "confirmed_baseline_rows",
    "evaluation_role_summary",
    "frame_polygons_display",
    "frame_state_summary",
    "line_basis_summary",
    "validate_annotation_record",
)
