from __future__ import annotations

from pathlib import Path

import tifffile

from ..app_info import TIFF_SUFFIXES
from ..utils import spatial_shape_from_shape


def iter_input_files(path: Path) -> list[Path]:
    if path.is_file():
        if path.suffix.lower() not in TIFF_SUFFIXES:
            raise ValueError(f"Input is not a TIFF: {path}")
        return [path]
    if path.is_dir():
        return [p for p in sorted(path.iterdir()) if p.is_file() and p.suffix.lower() in TIFF_SUFFIXES]
    raise ValueError(f"Path does not exist: {path}")


def first_tiff_shape(path: Path, page_index: int) -> tuple[int, int]:
    if page_index < 0:
        raise ValueError("--page must be 0 or greater")
    with tifffile.TiffFile(path) as tif:
        if not tif.pages:
            raise ValueError(f"TIFF has no pages: {path}")
        if page_index >= len(tif.pages):
            raise ValueError(f"--page {page_index} is out of range; TIFF has {len(tif.pages)} pages")
        shape = tuple(int(x) for x in tif.pages[page_index].shape)
    return spatial_shape_from_shape(shape)
