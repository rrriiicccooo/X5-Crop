from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import platform
import sys
from typing import Any

from ..app_info import SCRIPT_NAME, VERSION
from ..configuration.model import FrameCountMode
from ..detection.photo_geometry.model import OutputSlotIdentity, ResolvedOutputSlots
from ..image.workspace import WorkspaceIdentity
from ..io.model import ImageProfile
from ..report.read_models import typed_read_model
from ..run_config import RunConfig
from .invocation import PlannedSource
from .dependency_identity import runtime_dependency_identity
from .threading import thread_identity


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
        "axes": profile.axes,
        "photometric": profile.photometric,
        "orientation": profile.orientation.as_record(),
    }


def runtime_configuration_identity(config: RunConfig) -> dict[str, Any]:
    request = config.count_request
    count_policy = (
        {"policy": "scan_canvas_capacity"}
        if request.mode == FrameCountMode.AUTO
        else {
            "policy": (
                "format_default"
                if request.mode == FrameCountMode.FIXED_FULL
                else "user_explicit"
            ),
            "authoritative_count": request.authoritative_count,
        }
    )
    return {
        "format_id": config.format_id,
        "layout": config.layout,
        "strip_mode": config.strip_mode,
        "output_slot_policy": count_policy,
        "debug_analysis": config.debug_analysis,
        "preview": config.preview,
    }


@lru_cache(maxsize=1)
def runtime_environment_identity() -> dict[str, Any]:
    return {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform_system": platform.system(),
        "platform": platform.platform(),
        "dependencies": runtime_dependency_identity(),
        "threads": thread_identity(),
    }


def make_runtime_identity(
    source_identity: dict[str, Any],
    config: RunConfig,
    workspace_identity: WorkspaceIdentity,
    selected_profile_id: str | None,
    resolved_output_slots: ResolvedOutputSlots | None,
    output_slot_identities: tuple[OutputSlotIdentity, ...],
) -> dict[str, Any]:
    return {
        "script": SCRIPT_NAME,
        "script_version": VERSION,
        "source": dict(source_identity),
        "runtime_configuration": runtime_configuration_identity(config),
        "runtime_environment": runtime_environment_identity(),
        "workspace_identity": typed_read_model(workspace_identity),
        "output_identity": {
            "selected_scan_canvas_profile_id": selected_profile_id,
            "resolved_output_slots": typed_read_model(resolved_output_slots),
            "output_slot_count": (
                None
                if resolved_output_slots is None
                else resolved_output_slots.output_slot_count
            ),
            "slot_identities": typed_read_model(output_slot_identities),
        },
    }
