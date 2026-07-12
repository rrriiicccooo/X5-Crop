from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import tifffile

from ..run_config import RunConfig
from ..domain import Box
from ..io.model import ImageProfile
from ..image.crop_pixels import crop_array, validate_source_crop_pixels
from ..io.tiff import tiff_write_kwargs, validate_written_tiff


def write_crops(
    input_file: Path,
    arr: np.ndarray,
    source_arr: np.ndarray,
    profile: ImageProfile,
    frames: list[Box],
    config: RunConfig,
    deskew_applied: bool,
    output_dir: Path,
) -> list[str]:
    output_files: list[str] = []
    for i, box in enumerate(frames, 1):
        if not box.valid():
            raise RuntimeError(f"Invalid crop box for frame {i}: {box}")
        out_path = output_dir / f"{input_file.stem}_{i:02d}.tif"
        if out_path.exists() and not config.overwrite:
            raise RuntimeError(f"Output exists: {out_path}; use --overwrite")
        cropped = np.ascontiguousarray(crop_array(arr, profile.axes, box))
        if not deskew_applied:
            validate_source_crop_pixels(source_arr, profile.axes, box, cropped)
        tmp = out_path.with_name(f".{out_path.stem}.tmp{out_path.suffix}")
        if tmp.exists():
            tmp.unlink()
        try:
            tifffile.imwrite(tmp, cropped, **tiff_write_kwargs(profile, config.compression))
            validate_written_tiff(tmp, cropped, profile, config.compression)
            os.replace(tmp, out_path)
        except Exception:
            if tmp.exists():
                tmp.unlink()
            raise
        output_files.append(str(out_path))
    return output_files
