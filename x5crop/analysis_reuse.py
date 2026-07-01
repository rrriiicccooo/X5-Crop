from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import numpy as np

from .app_info import SCRIPT_NAME, VERSION
from .config import Config
from .domain import Box, Detection, Gap, ImageProfile
from .image.deskew import rotate_array_expand
from .image.evidence import make_gray_u8
from .runtime import REPORT_RECORD_CACHE


def source_cache_signature(input_file: Path, profile: ImageProfile, page_index: int) -> dict[str, Any]:
    stat = input_file.stat()
    return {
        "name": input_file.name,
        "size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
        "page": int(page_index),
        "shape": list(profile.shape),
        "dtype": profile.dtype,
        "axes": profile.axes,
        "photometric": profile.photometric,
    }


def config_cache_signature(config: Config) -> dict[str, Any]:
    return {
        "film_format": config.film_format,
        "layout": config.layout,
        "strip_mode": config.strip_mode,
        "count": int(config.count),
        "page": int(config.page),
        "deskew": config.deskew,
        "analysis": config.analysis,
        "deskew_min_angle": float(config.deskew_min_angle),
        "deskew_max_angle": float(config.deskew_max_angle),
        "confidence_threshold": float(config.confidence_threshold),
    }


def make_analysis_cache_metadata(input_file: Path, profile: ImageProfile, config: Config) -> dict[str, Any]:
    return {
        "script": SCRIPT_NAME,
        "version": VERSION,
        "source": source_cache_signature(input_file, profile, config.page),
        "config": config_cache_signature(config),
    }


def box_from_dict(value: dict[str, Any]) -> Box:
    return Box(int(value["left"]), int(value["top"]), int(value["right"]), int(value["bottom"]))


def gap_from_dict(value: dict[str, Any]) -> Gap:
    return Gap(
        index=int(value.get("index", 0)),
        center=float(value.get("center", 0.0)),
        score=float(value.get("score", 0.0)),
        method=str(value.get("method", "cached")),
        start=(None if value.get("start") is None else float(value.get("start"))),
        end=(None if value.get("end") is None else float(value.get("end"))),
        lane_box=(dict(value["lane_box"]) if isinstance(value.get("lane_box"), dict) else None),
    )


def detection_from_record(record: dict[str, Any]) -> Detection:
    return Detection(
        film_format=str(record["film_format"]),
        layout=str(record["layout"]),
        strip_mode=str(record["strip_mode"]),
        count=int(record["count"]),
        outer=box_from_dict(record["outer_box"]),
        frames=[box_from_dict(box) for box in record.get("frame_boxes", [])],
        gaps=[gap_from_dict(gap) for gap in record.get("gaps", [])],
        confidence=float(record["confidence"]),
        review_reasons=list(record.get("review_reasons", [])),
        detail=dict(record.get("detail", {})),
    )


def cached_record_matches(record: dict[str, Any], input_file: Path, profile: ImageProfile, config: Config) -> bool:
    detail = record.get("detail")
    if not isinstance(detail, dict):
        return False
    cache = detail.get("analysis_cache")
    if not isinstance(cache, dict):
        return False
    if cache.get("script") != SCRIPT_NAME or cache.get("version") != VERSION:
        return False
    expected_source = source_cache_signature(input_file, profile, config.page)
    expected_config = config_cache_signature(config)
    if cache.get("source") != expected_source:
        return False
    cached_config = cache.get("config")
    if not isinstance(cached_config, dict):
        return False
    comparable_cached_config = dict(cached_config)
    comparable_cached_config.pop("bleed_x", None)
    comparable_cached_config.pop("bleed_y", None)
    if comparable_cached_config != expected_config:
        return False
    return str(record.get("status", "")) in {"approved_auto", "needs_review"}


def load_report_records(report_path: Path) -> list[dict[str, Any]]:
    try:
        stat = report_path.stat()
    except FileNotFoundError:
        return []
    cached = REPORT_RECORD_CACHE.get(report_path)
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
    REPORT_RECORD_CACHE[report_path] = (signature[0], signature[1], records)
    return records


def find_reusable_analysis(
    input_file: Path,
    output_dir: Path,
    profile: ImageProfile,
    config: Config,
) -> Optional[dict[str, Any]]:
    report_path = output_dir / "split_report.jsonl"
    for record in load_report_records(report_path):
        if Path(str(record.get("source", ""))).name != input_file.name:
            continue
        if cached_record_matches(record, input_file, profile, config):
            return record
    return None


def apply_cached_deskew(
    arr: np.ndarray,
    gray: np.ndarray,
    axes: str,
    photometric: str,
    detail: dict[str, Any],
    warnings: list[str],
) -> tuple[np.ndarray, np.ndarray, bool]:
    deskew_detail = detail.get("deskew")
    if not isinstance(deskew_detail, dict) or not bool(deskew_detail.get("applied", False)):
        return arr, gray, False
    angle = float(deskew_detail.get("angle", 0.0))
    arr = rotate_array_expand(arr, -angle, axes)
    gray = make_gray_u8(arr, axes, photometric)
    warnings.append(f"reused deskew: {-angle:.4f} degrees")
    return arr, gray, True


__all__ = [
    "apply_cached_deskew",
    "box_from_dict",
    "cached_record_matches",
    "config_cache_signature",
    "detection_from_record",
    "find_reusable_analysis",
    "gap_from_dict",
    "load_report_records",
    "make_analysis_cache_metadata",
    "source_cache_signature",
]
