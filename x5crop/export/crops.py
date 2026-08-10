from __future__ import annotations

import os
from pathlib import Path
import uuid

import numpy as np

from ..domain import Box
from ..geometry.affine import AffineCoordinateTransform
from ..image.transforms import photometric_background_value, sample_affine_roi
from ..io.model import ImageProfile
from ..io.tiff import write_validated_tiff
from ..output.naming import portable_component
from ..output.safe_tree import safe_remove_tree


def write_crops(
    portable_stem: str,
    input_ordinal: int,
    source_arr: np.ndarray,
    profile: ImageProfile,
    frames: tuple[Box, ...],
    sampling_authority_boxes: tuple[Box, ...],
    transforms: tuple[AffineCoordinateTransform, ...],
    output_dir: Path,
) -> list[str]:
    if not (
        len(frames) == len(sampling_authority_boxes) == len(transforms)
    ):
        raise ValueError("each crop requires one aligned sampling authority")
    output_files: list[str] = []
    promoted: list[Path] = []
    source_workspace = output_dir / (
        f".x5crop-source-{input_ordinal:04d}-{uuid.uuid4().hex}"
    )
    source_workspace.mkdir()
    try:
        background_value = photometric_background_value(
            source_arr,
            profile.photometric,
        )
        for i, (box, sampling_authority_box, transform) in enumerate(
            zip(frames, sampling_authority_boxes, transforms, strict=True),
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
            temporary_path = source_workspace / name
            write_validated_tiff(temporary_path, cropped, profile)
            output_files.append(str(out_path))
        for output_path_string in output_files:
            output_path = Path(output_path_string)
            temporary_path = source_workspace / output_path.name
            if output_path.exists():
                raise RuntimeError(f"Output name was not fresh: {output_path}")
            os.rename(temporary_path, output_path)
            promoted.append(output_path)
        source_workspace.rmdir()
        return output_files
    except Exception:
        for output_path in promoted:
            if output_path.is_file() and not output_path.is_symlink():
                output_path.unlink()
        if source_workspace.exists():
            safe_remove_tree(source_workspace)
        raise
