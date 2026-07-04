from __future__ import annotations

from pathlib import Path

import tifffile

from ..app_info import TIFF_SUFFIXES
from ..entry.options import CliOptions
from ..formats import FORMATS
from ..geometry.layout import infer_layout
from ..utils import spatial_shape_from_shape
from .config import RuntimeConfig


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


def runtime_config_from_options(options: CliOptions) -> tuple[RuntimeConfig, list[Path]]:
    files = iter_input_files(options.input_path)
    first_file = next(iter(files), None)
    if first_file is None:
        raise ValueError(f"No TIFF files found: {options.input_path}")

    height, width = first_tiff_shape(first_file, options.page)
    fmt = FORMATS[options.film_format]
    count = int(fmt.default_count if options.count_override is None else options.count_override)
    if count not in fmt.allowed_counts:
        allowed = ", ".join(str(x) for x in fmt.allowed_counts)
        raise ValueError(f"--format {fmt.name} allows --count values: {allowed}")

    layout_auto = options.layout == "auto"
    layout = infer_layout(width, height) if layout_auto else options.layout
    bleed_x_default = 20 if options.bleed is None else int(options.bleed)
    bleed_y_default = 10 if options.bleed is None else int(options.bleed)
    bleed_x = int(bleed_x_default if options.bleed_x is None else options.bleed_x)
    bleed_y = int(bleed_y_default if options.bleed_y is None else options.bleed_y)
    if bleed_x < 0 or bleed_y < 0:
        raise ValueError("Bleed cannot be negative")

    jobs_cap = 4 if options.diagnostics else 2
    jobs = max(1, min(jobs_cap, int(options.jobs)))
    return RuntimeConfig(
        input_path=options.input_path,
        output_dir=options.output_dir,
        film_format=options.film_format,
        layout_auto=layout_auto,
        layout=layout,
        strip_mode=options.strip_mode,
        count=count,
        count_override=options.count_override,
        page=options.page,
        bleed_x=bleed_x,
        bleed_y=bleed_y,
        deskew=options.deskew,
        analysis=options.analysis,
        deskew_min_angle=options.deskew_min_angle,
        deskew_max_angle=options.deskew_max_angle,
        confidence_threshold=options.confidence_threshold,
        review_dir=options.review_dir,
        copy_review_files=options.copy_review_files,
        export_review=options.export_review,
        compression=options.compression,
        debug=options.debug,
        debug_analysis=options.debug_analysis,
        dry_run=options.dry_run,
        diagnostics=options.diagnostics,
        overwrite=options.overwrite,
        report=options.report,
        debug_errors=options.debug_errors,
        reuse_analysis=options.reuse_analysis,
        jobs=jobs,
    ), files


__all__ = [
    "first_tiff_shape",
    "iter_input_files",
    "runtime_config_from_options",
]
