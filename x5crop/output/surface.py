from __future__ import annotations

from pathlib import Path

from ..run_config import RunConfig


def output_directory_for(config: RunConfig) -> Path:
    if config.output_dir is not None:
        return config.output_dir
    base = config.input_path if config.input_path.is_dir() else config.input_path.parent
    return base / "x5_crop_output"
