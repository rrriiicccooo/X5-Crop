from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..run_config import RunConfig


@dataclass(frozen=True)
class OutputSurface:
    root: Path


def output_directory_for(input_file: Path, config: RunConfig) -> Path:
    if config.output_dir is not None:
        return config.output_dir
    return input_file.parent / "x5_crop_output"


def output_surface_for_input(input_file: Path, config: RunConfig) -> OutputSurface:
    return OutputSurface(root=output_directory_for(input_file, config))


def display_generated_path(path: Path | str, config: RunConfig) -> str:
    generated_path = Path(path)
    if config.output_dir is None:
        return generated_path.name
    return str(generated_path)
