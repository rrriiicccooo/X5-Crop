from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..configuration.bundle import DetectionConfigurationBundle
from ..run_config import RunConfig


@dataclass(frozen=True)
class PlannedSource:
    input_ordinal: int
    path: Path
    portable_stem: str

    def __post_init__(self) -> None:
        if self.input_ordinal <= 0 or not self.path.is_absolute() or not self.portable_stem:
            raise ValueError("planned source is incomplete")


@dataclass(frozen=True)
class RuntimeInvocation:
    config: RunConfig
    sources: tuple[PlannedSource, ...]
    configuration_bundle: DetectionConfigurationBundle
