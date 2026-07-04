from __future__ import annotations

from pathlib import Path

from ..runtime.config import RuntimeConfig


def output_directory_for(input_file: Path, config: RuntimeConfig) -> Path:
    if config.output_dir is not None:
        return config.output_dir
    return input_file.parent / "x5_crop_output"


def display_generated_path(path: Path | str, config: RuntimeConfig) -> str:
    generated_path = Path(path)
    if config.output_dir is None:
        return generated_path.name
    return str(generated_path)


__all__ = [
    "display_generated_path",
    "output_directory_for",
]
