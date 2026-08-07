from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from ..domain import Box
from ..geometry.affine import AffineCoordinateTransform
from ..image.transforms import photometric_background_value, sample_affine_roi
from ..io.model import ImageProfile
from ..io.tiff import write_validated_tiff
from ..output.naming import portable_component


def write_crops(
    portable_stem: str,
    input_ordinal: int,
    source_arr: np.ndarray,
    profile: ImageProfile,
    frames: tuple[Box, ...],
    sampling_authority_boxes: tuple[Box, ...],
    transform: AffineCoordinateTransform,
    output_dir: Path,
) -> list[str]:
    if len(frames) != len(sampling_authority_boxes):
        raise ValueError("each crop requires one aligned sampling authority")
    output_files: list[str] = []
    background_value = photometric_background_value(
        source_arr,
        profile.photometric,
    )
    for i, (box, sampling_authority_box) in enumerate(
        zip(frames, sampling_authority_boxes, strict=True),
        1,
    ):
        if not box.valid():
            raise RuntimeError(f"Invalid crop box for frame {i}: {box}")
        name = portable_component(
            portable_stem,
            input_ordinal=input_ordinal,
            suffix=f"_{i:02d}.tif",
        ).value
        out_path = output_dir / name
        if out_path.exists():
            raise RuntimeError(f"Output name was not fresh: {out_path}")
        cropped = np.ascontiguousarray(
            sample_affine_roi(
                source_arr,
                profile.axes,
                transform,
                box,
                background_value=background_value,
                sampling_authority_box=sampling_authority_box,
            )
        )
        tmp = out_path.with_name(f".{out_path.stem}.tmp{out_path.suffix}")
        if tmp.exists():
            tmp.unlink()
        try:
            write_validated_tiff(tmp, cropped, profile)
            os.replace(tmp, out_path)
        except Exception:
            if tmp.exists():
                tmp.unlink()
            raise
        output_files.append(str(out_path))
    return output_files
