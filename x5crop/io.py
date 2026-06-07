"""TIFF I/O and output helpers.

These names are re-exported from ``x5crop.core`` in V4 so callers can depend on
a clean I/O module while the implementation is migrated without behavior drift.
"""

from .core import (
    ImageProfile,
    compression_for_write,
    copy_for_review,
    read_tiff,
    read_tiff_profile,
    tiff_write_kwargs,
    validate_written_tiff,
    write_crops,
)

__all__ = [
    "ImageProfile",
    "compression_for_write",
    "copy_for_review",
    "read_tiff",
    "read_tiff_profile",
    "tiff_write_kwargs",
    "validate_written_tiff",
    "write_crops",
]
