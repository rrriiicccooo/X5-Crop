from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import file_digest, sha256
import json
from pathlib import Path
from typing import Any

import numpy as np

from ..app_info import REPORT_JSONL_NAME, SCRIPT_NAME, VERSION
from ..image.workspace import WorkspaceIdentity
from ..io.model import ImageProfile
from ..report.model import ReportResult
from ..export.actions import copy_for_review_if_needed, write_crops_if_allowed
from ..output.surface import OutputSurface
from ..configuration.bundle import DetectionConfigurationBundle
from ..report.restoration import (
    final_detection_from_record as _final_detection_from_record,
)
from ..report.read_models import typed_read_model
from ..report.validation import current_report_record_errors
from ..report.result_builder import result_from_cached_record
from ..run_config import RunConfig
from .implementation import active_implementation_fingerprint
from .outcome import RuntimeArtifacts
from .prepared_workspace import PreparedWorkspace


_REPORT_RECORD_CACHE: dict[Path, tuple[int, int, list[dict[str, Any]]]] = {}


@dataclass(frozen=True)
class ReusedAnalysis:
    result: ReportResult
    artifacts: RuntimeArtifacts


def source_cache_signature(input_file: Path, profile: ImageProfile, page_index: int) -> dict[str, Any]:
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


def config_cache_signature(config: RunConfig) -> dict[str, Any]:
    return {
        "format_id": config.format_id,
        "layout": config.layout,
        "strip_mode": config.strip_mode,
        "requested_count": (
            None if config.requested_count is None else int(config.requested_count)
        ),
        "page": int(config.page),
        "deskew": config.deskew,
        "deskew_fallback": config.deskew_fallback,
        "deskew_min_angle": float(config.deskew_min_angle),
        "deskew_max_angle": float(config.deskew_max_angle),
        "bleed_x": int(config.bleed_x),
        "bleed_y": int(config.bleed_y),
    }


def analysis_configuration_fingerprint(
    configuration_bundle: DetectionConfigurationBundle,
) -> str:
    analysis_configurations = []
    for configuration in configuration_bundle.resolved_configurations:
        analysis_configuration = asdict(configuration)
        del analysis_configuration["diagnostics"]
        analysis_configurations.append(analysis_configuration)
    payload = json.dumps(
        analysis_configurations,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def make_analysis_reuse_signature(
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
        "source": source_cache_signature(input_file, profile, config.page),
        "config": config_cache_signature(config),
        "configuration_fingerprint": analysis_configuration_fingerprint(
            configuration_bundle
        ),
        "workspace_identity": typed_read_model(workspace_identity),
    }


def cached_record_matches(
    record: dict[str, Any],
    expected_signature: dict[str, Any],
) -> bool:
    if current_report_record_errors(record):
        return False
    if record["script_version"] != VERSION:
        return False
    cache = record["analysis_reuse_signature"]
    if not isinstance(cache, dict):
        return False
    if cache != expected_signature:
        return False
    return str(record["decision"]["status"]) in {
        "approved_auto",
        "needs_review",
    }


def load_report_records(report_path: Path) -> list[dict[str, Any]]:
    try:
        stat = report_path.stat()
    except FileNotFoundError:
        return []
    cached = _REPORT_RECORD_CACHE.get(report_path)
    signature = (int(stat.st_size), int(stat.st_mtime_ns))
    if cached is not None and cached[0] == signature[0] and cached[1] == signature[1]:
        return cached[2]
    try:
        lines = report_path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return []
    records: list[dict[str, Any]] = []
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    _REPORT_RECORD_CACHE[report_path] = (signature[0], signature[1], records)
    return records


def find_reusable_analysis(
    input_file: Path,
    output_dir: Path,
    expected_signature: dict[str, Any],
) -> dict[str, Any] | None:
    report_path = output_dir / REPORT_JSONL_NAME
    for record in load_report_records(report_path):
        if not cached_record_matches(record, expected_signature):
            continue
        if Path(str(record["source"])).name == input_file.name:
            return record
    return None


def result_from_reusable_analysis(
    input_file: Path,
    config: RunConfig,
    output_surface: OutputSurface,
    profile: ImageProfile,
    warnings: list[str],
    analysis_reuse_signature: dict[str, Any],
    workspace: PreparedWorkspace,
    source_pixels: np.ndarray,
) -> ReusedAnalysis | None:
    if not (
        config.reuse_analysis
        and not config.dry_run
        and not config.debug
        and not config.debug_analysis
    ):
        return None
    cached_record = find_reusable_analysis(
        input_file,
        output_surface.root,
        analysis_reuse_signature,
    )
    if cached_record is None:
        return None

    try:
        detection = _final_detection_from_record(cached_record)
    except (KeyError, TypeError, ValueError):
        return None
    warnings.append(f"reused analysis report: {REPORT_JSONL_NAME}")
    review_copy = copy_for_review_if_needed(
        input_file,
        output_surface.root,
        config,
        detection,
        warnings,
    )
    if detection.decision.status == "needs_review" and not config.export_review:
        warnings.append("cached status is needs_review; crop export not requested")
        return ReusedAnalysis(
            result=result_from_cached_record(
                input_file,
                cached_record,
                profile,
                warnings,
                output_files=[],
                review_copy=review_copy,
            ),
            artifacts=RuntimeArtifacts((), review_copy, None),
        )

    output_files = write_crops_if_allowed(
        input_file,
        workspace.pixels,
        source_pixels,
        profile,
        detection,
        config,
        workspace.transform_geometry.applied,
        output_surface,
    )
    return ReusedAnalysis(
        result=result_from_cached_record(
            input_file,
            cached_record,
            profile,
            warnings,
            output_files=output_files,
            review_copy=review_copy,
        ),
        artifacts=RuntimeArtifacts(tuple(output_files), review_copy, None),
    )
