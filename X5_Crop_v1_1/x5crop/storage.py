from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

APP_NAME = "X5 Crop"
APP_DIR_NAME = "X5 Crop"


@dataclass(frozen=True)
class AppPaths:
    config_dir: Path
    cache_dir: Path
    log_dir: Path
    temp_dir: Path


def _home() -> Path:
    return Path.home()


def app_paths() -> AppPaths:
    """Return traditional OS application-data paths.

    This intentionally follows normal desktop app behavior instead of portable
    storage. Cleanup scripts under tools/ remove these folders after uninstall.
    """
    if sys.platform == "darwin":
        base_config = _home() / "Library" / "Application Support" / APP_DIR_NAME
        base_cache = _home() / "Library" / "Caches" / APP_DIR_NAME
        base_log = _home() / "Library" / "Logs" / APP_DIR_NAME
    elif os.name == "nt":
        roaming = Path(os.environ.get("APPDATA", _home() / "AppData" / "Roaming"))
        local = Path(os.environ.get("LOCALAPPDATA", _home() / "AppData" / "Local"))
        base_config = roaming / APP_DIR_NAME
        base_cache = local / APP_DIR_NAME / "Cache"
        base_log = local / APP_DIR_NAME / "Logs"
    else:
        xdg_config = Path(os.environ.get("XDG_CONFIG_HOME", _home() / ".config"))
        xdg_cache = Path(os.environ.get("XDG_CACHE_HOME", _home() / ".cache"))
        xdg_state = Path(os.environ.get("XDG_STATE_HOME", _home() / ".local" / "state"))
        base_config = xdg_config / "x5-crop"
        base_cache = xdg_cache / "x5-crop"
        base_log = xdg_state / "x5-crop" / "logs"
    return AppPaths(
        config_dir=base_config,
        cache_dir=base_cache,
        log_dir=base_log,
        temp_dir=base_cache / "tmp",
    )


def ensure_app_dirs() -> AppPaths:
    paths = app_paths()
    for p in asdict(paths).values():
        Path(p).mkdir(parents=True, exist_ok=True)
    return paths


def settings_path() -> Path:
    return app_paths().config_dir / "settings.json"


def load_settings() -> dict[str, Any]:
    path = settings_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_settings(settings: dict[str, Any]) -> None:
    ensure_app_dirs()
    path = settings_path()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def recent_project_cache_dir(project_path: Path) -> Path:
    # Project cache is intentionally explicit and removable. It is not required
    # for app operation; it may be disabled in a future settings page.
    return project_path / ".x5crop"
