from __future__ import annotations

from hashlib import file_digest, sha256
import json
from pathlib import Path
from typing import Any

from ..app_info import SCRIPT_NAME, VERSION
from ..configuration.bundle import DetectionConfigurationBundle
from ..image.workspace import WorkspaceIdentity
from ..io.model import ImageProfile
from ..report.read_models import typed_read_model
from ..run_config import RunConfig
from .implementation import active_implementation_fingerprint


def source_analysis_identity(
    input_file: Path,
    profile: ImageProfile,
    page_index: int,
) -> dict[str, Any]:
    stat = input_file.stat()
    with input_file.open("rb") as stream:
        content_sha256 = file_digest(stream, "sha256").hexdigest()
    return {
        "name": input_file.name,
        "size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
        "content_sha256": content_sha256,
        "page": int(page_index),
        "shape": list(profile.shape),
        "dtype": profile.dtype,
        "axes": profile.axes,
        "photometric": profile.photometric,
    }


def runtime_configuration_identity(config: RunConfig) -> dict[str, Any]:
    return {
        "format_id": config.format_id,
        "layout": config.layout,
        "strip_mode": config.strip_mode,
        "requested_count": (
            None if config.requested_count is None else int(config.requested_count)
        ),
        "page": int(config.page),
        "bleed_x": int(config.bleed_x),
        "bleed_y": int(config.bleed_y),
    }


def detection_configuration_fingerprint(
    configuration_bundle: DetectionConfigurationBundle,
) -> str:
    analysis_configurations = []
    for configuration in configuration_bundle.resolved_configurations:
        analysis_configuration = typed_read_model(configuration)
        del analysis_configuration["diagnostics"]
        analysis_configurations.append(analysis_configuration)
    payload = json.dumps(
        analysis_configurations,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def make_analysis_identity(
    input_file: Path,
    profile: ImageProfile,
    config: RunConfig,
    configuration_bundle: DetectionConfigurationBundle,
    workspace_identity: WorkspaceIdentity,
) -> dict[str, Any]:
    return {
        "script": SCRIPT_NAME,
        "script_version": VERSION,
        "implementation_fingerprint": active_implementation_fingerprint(),
        "source": source_analysis_identity(input_file, profile, config.page),
        "runtime_configuration": runtime_configuration_identity(config),
        "detection_configuration_fingerprint": (
            detection_configuration_fingerprint(configuration_bundle)
        ),
        "workspace_identity": typed_read_model(workspace_identity),
    }
