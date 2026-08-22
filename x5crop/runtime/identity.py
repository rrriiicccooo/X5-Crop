"""Lightweight identity needed by one local production run."""

from __future__ import annotations

from typing import Any

from ..app_info import SCRIPT_NAME, VERSION
from ..io.model import ImageProfile
from ..run_config import RunConfig
from .invocation import PlannedSource


def source_runtime_identity(
    source: PlannedSource,
    profile: ImageProfile,
) -> dict[str, Any]:
    info = source.path.stat()
    return {
        "input_ordinal": source.input_ordinal,
        "name": source.path.name,
        "portable_stem": source.portable_stem,
        "size": int(info.st_size),
        "mtime_ns": int(info.st_mtime_ns),
        "shape": list(profile.shape),
        "dtype": profile.dtype,
        "orientation": profile.orientation.as_record(),
    }


def runtime_configuration_identity(config: RunConfig) -> dict[str, Any]:
    request = config.count_request
    return {
        "format_id": config.format_id,
        "layout": config.layout,
        "output_slot_policy": {
            "user_count": request.user_count,
            "authority": request.authority.value,
        },
        "debug_analysis": config.debug_analysis,
    }


def make_runtime_identity(
    source_identity: dict[str, Any],
    config: RunConfig,
) -> dict[str, Any]:
    return {
        "script": SCRIPT_NAME,
        "script_version": VERSION,
        "source": dict(source_identity),
        "runtime_configuration": runtime_configuration_identity(config),
    }
