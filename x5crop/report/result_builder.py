from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

from ..app_info import VERSION
from ..detection.detail import policy_id_from_detail
from ..domain import FinalDetection, ImageProfile, ProcessResult
from ..policies.runtime.policy import DetectionPolicy
from ..utils import json_safe
from .record import report_record_for_final_detection


def policy_id_for_detection(detection: FinalDetection) -> str:
    return policy_id_from_detail(detection)


def result_from_detection(
    input_file: Path,
    detection: FinalDetection,
    profile: ImageProfile,
    output_files: list[str],
    review_copy: Optional[str],
    warnings: list[str],
    policy: DetectionPolicy,
    detail_extra: dict[str, Any] | None = None,
) -> ProcessResult:
    detail = dict(detection.detail)
    if detail_extra:
        detail.update(detail_extra)
    result = ProcessResult(
        source=str(input_file),
        status=detection.status,
        confidence=float(detection.confidence),
        film_format=detection.film_format,
        layout=detection.layout,
        strip_mode=detection.strip_mode,
        count=int(detection.count),
        final_review_reasons=list(detection.final_review_reasons),
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
    result.report_record = report_record_for_final_detection(detection, result, policy=policy)
    return result


def result_from_cached_record(
    input_file: Path,
    cached_record: dict[str, Any],
    profile: ImageProfile,
    warnings: list[str],
) -> ProcessResult:
    format_detail = dict(cached_record.get("format", {})) if isinstance(cached_record.get("format"), dict) else {}
    output_detail = dict(cached_record.get("output", {})) if isinstance(cached_record.get("output"), dict) else {}
    result = ProcessResult(
        source=str(input_file),
        status=str(cached_record["status"]),
        confidence=float(cached_record["confidence"]),
        film_format=str(cached_record["format_id"]),
        layout=str(cached_record.get("layout") or format_detail.get("layout")),
        strip_mode=str(cached_record["strip_mode"]),
        count=int(cached_record.get("count") or format_detail.get("count")),
        final_review_reasons=list(cached_record["final_review_reasons"]),
        output_files=list(output_detail.get("output_files", [])),
        review_copy=output_detail.get("review_copy"),
        outer_box=dict(cached_record.get("outer_box", {})),
        frame_boxes=list(cached_record.get("frame_boxes", [])),
        gaps=list(cached_record.get("gaps", [])),
        detail={**dict(cached_record.get("detail", {})), "reused_analysis": True},
        profile=json_safe(asdict(profile)),
        warnings=warnings,
        version=VERSION,
        policy_id=str(cached_record.get("policy_id", "")),
    )
    report_record = dict(cached_record)
    report_record["detail"] = dict(result.detail)
    output_detail = dict(report_record.get("output", {})) if isinstance(report_record.get("output"), dict) else {}
    output_detail["warnings"] = list(warnings)
    report_record["output"] = output_detail
    result.report_record = report_record
    return result


__all__ = [
    "policy_id_for_detection",
    "result_from_cached_record",
    "result_from_detection",
]
