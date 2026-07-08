from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..export.paths import output_directory_for
from ..runtime.config import RuntimeConfig


@dataclass(frozen=True)
class OutputSurface:
    root: Path

    def ensure_root(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        return self.root


def output_surface_for_input(input_file: Path, config: RuntimeConfig) -> OutputSurface:
    return OutputSurface(root=output_directory_for(input_file, config))


__all__ = ["OutputSurface", "output_surface_for_input"]
