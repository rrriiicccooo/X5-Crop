from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..policies.runtime.bundle import DetectionPolicyBundle
from ..run_config import RunConfig


@dataclass(frozen=True)
class RuntimeInvocation:
    config: RunConfig
    files: tuple[Path, ...]
    policy_bundle: DetectionPolicyBundle
