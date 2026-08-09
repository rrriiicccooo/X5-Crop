from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..run_config import RunConfig
from .naming import portable_component


@dataclass(frozen=True)
class OutputSurface:
    root: Path


def output_directory_for(config: RunConfig) -> Path:
    production = production_output_directory_for(config)
    return preview_output_directory_for(config) if config.preview else production


def production_output_directory_for(config: RunConfig) -> Path:
    if config.output_dir is not None:
        return config.output_dir
    base = config.input_path if config.input_path.is_dir() else config.input_path.parent
    return base / "x5_crop_output"


def preview_output_directory_for(config: RunConfig) -> Path:
    production = production_output_directory_for(config)
    if config.output_dir is None:
        return production.with_name("x5_crop_preview")
    preview_name = portable_component(
        production.name,
        input_ordinal=1,
        suffix="_preview",
        fallback="x5_crop",
    ).value
    return production.with_name(preview_name)


def output_surface_for_run(config: RunConfig) -> OutputSurface:
    return OutputSurface(root=output_directory_for(config))


def display_generated_path(path: Path | str, config: RunConfig) -> str:
    generated_path = Path(path)
    if config.output_dir is None:
        return generated_path.name
    return str(generated_path)
