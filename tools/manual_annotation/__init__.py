"""Local, source-bound human annotation tools for X5 Crop calibration."""

from .model import (
    ANNOTATION_SCHEMA,
    BASELINE_SCHEMA,
    canonical_record_sha256,
    confirmed_baseline_rows,
    frame_polygons_display,
    validate_annotation_record,
)

__all__ = (
    "ANNOTATION_SCHEMA",
    "BASELINE_SCHEMA",
    "canonical_record_sha256",
    "confirmed_baseline_rows",
    "frame_polygons_display",
    "validate_annotation_record",
)
