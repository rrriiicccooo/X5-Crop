"""Development-only dependency and host identity for verification receipts."""

from __future__ import annotations

from pathlib import Path
import platform
from typing import Any

from tools.install.dependency_manager import (
    inspect_dependency_states,
    load_dependency_contract,
)
from x5crop.runtime.threading import thread_identity


CONTRACT_PATH = Path(__file__).parents[1] / "install" / "dependencies.toml"


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
            "build_information_sha256": state.build_information_sha256,
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
