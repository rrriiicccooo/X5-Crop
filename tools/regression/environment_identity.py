"""Development-only dependency and host identity for verification receipts."""

from __future__ import annotations

import os
from pathlib import Path
import platform
from typing import Any

from tools.install.dependency_manager import (
    inspect_dependency_states,
    load_dependency_contract,
)
from x5crop.runtime.threading import THREAD_ENVIRONMENT_KEYS


CONTRACT_PATH = Path(__file__).parents[1] / "install" / "dependencies.toml"


def thread_identity() -> dict[str, object]:
    try:
        import cv2

        opencv_threads: int | None = int(cv2.getNumThreads())
    except ImportError:
        opencv_threads = None
    return {
        "x5crop_source_workers": "--jobs",
        "opencv_threads": opencv_threads,
        "environment": {key: os.environ.get(key) for key in THREAD_ENVIRONMENT_KEYS},
    }


def verification_environment_identity() -> dict[str, Any]:
    contract = load_dependency_contract(CONTRACT_PATH)
    states = inspect_dependency_states(contract)
    dependencies = {
        state.name: {
            "module": state.module,
            "module_version": state.module_version,
            "module_origin": state.module_origin,
            "provider": state.provider,
            "package": state.package,
            "package_version": state.package_version,
        }
        for state in states
    }
    return {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform_system": platform.system(),
        "platform": platform.platform(),
        "dependencies": dependencies,
        "threads": thread_identity(),
    }
