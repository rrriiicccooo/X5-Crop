from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from ..run_config import RunConfig
from ..domain import Box
from ..geometry.affine import AffineCoordinateTransform
from ..image.transforms import photometric_background_value, sample_affine_roi
from ..io.model import ImageProfile
from ..image.crop_pixels import validate_source_crop_pixels
from ..io.tiff import write_validated_tiff


def write_crops(
    input_file: Path,
    source_arr: np.ndarray,
    profile: ImageProfile,
    frames: tuple[Box, ...],
    config: RunConfig,
    transform: AffineCoordinateTransform,
    output_dir: Path,
) -> list[str]:
    output_files: list[str] = []
    background_value = photometric_background_value(
        source_arr,
        profile.photometric,
    )
    for i, box in enumerate(frames, 1):
        if not box.valid():
            raise RuntimeError(f"Invalid crop box for frame {i}: {box}")
        out_path = output_dir / f"{input_file.stem}_{i:02d}.tif"
        if out_path.exists() and not config.overwrite:
            raise RuntimeError(f"Output exists: {out_path}; use --overwrite")
        cropped = np.ascontiguousarray(
            sample_affine_roi(
                source_arr,
                profile.axes,
                transform,
                box,
                background_value=background_value,
            )
        )
        if transform.is_identity:
            validate_source_crop_pixels(source_arr, profile.axes, box, cropped)
        tmp = out_path.with_name(f".{out_path.stem}.tmp{out_path.suffix}")
        if tmp.exists():
            tmp.unlink()
        try:
            write_validated_tiff(tmp, cropped, profile, config.compression)
            os.replace(tmp, out_path)
        except Exception:
            if tmp.exists():
                tmp.unlink()
            raise
        output_files.append(str(out_path))
    return output_files
