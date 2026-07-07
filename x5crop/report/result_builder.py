from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

from ..app_info import VERSION
from ..detection.detail import policy_id_from_detail
from ..domain import Detection, ImageProfile, ProcessResult
from ..utils import json_safe
from .schema import report_schema_for_detection


def policy_id_for_detection(detection: Detection) -> str:
    return policy_id_from_detail(detection)


def result_from_detection(
    input_file: Path,
    detection: Detection,
    profile: ImageProfile,
    status: str,
    output_files: list[str],
    review_copy: Optional[str],
    warnings: list[str],
    detail_extra: dict[str, Any] | None = None,
) -> ProcessResult:
    detail = dict(detection.detail)
    if detail_extra:
        detail.update(detail_extra)
    result = ProcessResult(
        source=str(input_file),
        status=status,
        confidence=float(detection.confidence),
        film_format=detection.film_format,
        layout=detection.layout,
        strip_mode=detection.strip_mode,
        count=int(detection.count),
        review_reasons=list(detection.review_reasons),
        output_files=output_files,
        review_copy=review_copy,
        outer_box=asdict(detection.outer),
        frame_boxes=[asdict(box) for box in detection.frames],
        gaps=[asdict(gap) for gap in detection.gaps],
        detail=json_safe(detail),
        profile=json_safe(asdict(profile)),
        warnings=warnings,
        version=VERSION,
        policy_id=policy_id_for_detection(detection),
    )
    result.report_schema = report_schema_for_detection(detection, result)
    return result


def result_from_cached_record(
    input_file: Path,
    cached_record: dict[str, Any],
    profile: ImageProfile,
    warnings: list[str],
) -> ProcessResult:
    result = ProcessResult(
        source=str(input_file),
        status=str(cached_record["status"]),
        confidence=float(cached_record["confidence"]),
        film_format=str(cached_record["film_format"]),
        layout=str(cached_record["layout"]),
        strip_mode=str(cached_record["strip_mode"]),
        count=int(cached_record["count"]),
        review_reasons=list(cached_record.get("review_reasons", [])),
        output_files=[],
        review_copy=cached_record.get("review_copy"),
        outer_box=dict(cached_record.get("outer_box", {})),
        frame_boxes=list(cached_record.get("frame_boxes", [])),
        gaps=list(cached_record.get("gaps", [])),
        detail={**dict(cached_record.get("detail", {})), "reused_analysis": True},
        profile=json_safe(asdict(profile)),
        warnings=warnings,
        version=VERSION,
        policy_id=str(cached_record.get("policy_id", "")),
    )
    result.report_schema = dict(cached_record.get("report_schema", {}))
    return result


__all__ = [
    "policy_id_for_detection",
    "result_from_cached_record",
    "result_from_detection",
]
