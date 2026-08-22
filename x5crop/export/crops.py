from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile

import numpy as np

from ..detection.photo_geometry.output_model import OutputFootprint
from ..domain import Box
from ..geometry.affine import AffineCoordinateTransform
from ..image.transforms import sample_affine_roi
from ..io.model import ImageProfile
from ..io.tiff import write_validated_tiff
from ..output.naming import portable_component


def write_crops(
    portable_stem: str,
    input_ordinal: int,
    source_arr: np.ndarray,
    profile: ImageProfile,
    frames: tuple[Box, ...],
    footprints: tuple[OutputFootprint, ...],
    transform: AffineCoordinateTransform,
    output_dir: Path,
) -> list[str]:
    if len(frames) != len(footprints):
        raise ValueError("each crop requires one aligned sampling authority")
    output_files: list[str] = []
    promoted: list[Path] = []
    source_workspace = Path(
        tempfile.mkdtemp(
            prefix=f".x5crop-source-{input_ordinal:04d}-",
            dir=output_dir,
        )
    )
    try:
        for i, (box, footprint) in enumerate(
            zip(frames, footprints, strict=True),
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
            temporary_path = source_workspace / name
            write_validated_tiff(
                temporary_path,
                sample_affine_roi(
                    source_arr,
                    transform,
                    box,
                    sampling_authority_box=footprint.sampling_authority_box,
                ),
                profile,
            )
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
            shutil.rmtree(source_workspace)
        raise
