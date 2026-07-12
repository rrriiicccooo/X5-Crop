from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..configuration.bundle import DetectionConfigurationBundle
from ..run_config import RunConfig


@dataclass(frozen=True)
class RuntimeInvocation:
    config: RunConfig
    files: tuple[Path, ...]
    configuration_bundle: DetectionConfigurationBundle
