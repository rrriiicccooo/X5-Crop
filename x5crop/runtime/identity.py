"""Lightweight identity needed by one local production run."""

from __future__ import annotations

from typing import Any

from ..app_info import SCRIPT_NAME, VERSION
from ..detection.photo_geometry.output_model import (
    OutputSlotIdentity,
    ResolvedOutputSlots,
)
from ..io.model import ImageProfile
from ..report.read_models import typed_read_model
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
        "strip_mode": config.strip_mode,
        "output_slot_policy": {
            "intent": request.strip_mode,
            "user_count": request.user_count,
            "holder_layout_authority": request.holder_layout_authority.value,
        },
        "debug_analysis": config.debug_analysis,
    }


def make_runtime_identity(
    source_identity: dict[str, Any],
    config: RunConfig,
    selected_profile_id: str | None,
    resolved_output_slots: ResolvedOutputSlots | None,
    output_slot_identities: tuple[OutputSlotIdentity, ...],
) -> dict[str, Any]:
    return {
        "script": SCRIPT_NAME,
        "script_version": VERSION,
        "source": dict(source_identity),
        "runtime_configuration": runtime_configuration_identity(config),
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
