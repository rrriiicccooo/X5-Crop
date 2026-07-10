from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

from ..detection.detail import policy_id_from_detail
from ..domain import FinalDetection, ImageProfile, ProcessResult
from ..utils import json_safe
from .record import report_record_for_final_detection


def result_from_detection(
    input_file: Path,
    detection: FinalDetection,
    profile: ImageProfile,
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
        status=detection.status,
        confidence=float(detection.confidence),
        format_id=detection.format_id,
        layout=detection.layout,
        strip_mode=detection.strip_mode,
        count=int(detection.count),
        final_review_reasons=list(detection.final_review_reasons),
        output_files=output_files,
        review_copy=review_copy,
        detail=json_safe(detail),
        profile=json_safe(asdict(profile)),
        warnings=warnings,
        policy_id=policy_id_from_detail(detection),
    )
    result.report_record = report_record_for_final_detection(detection, result)
    return result


def result_from_cached_record(
    input_file: Path,
    cached_record: dict[str, Any],
    profile: ImageProfile,
    warnings: list[str],
    *,
    output_files: list[str],
    detail_extra: dict[str, Any],
) -> ProcessResult:
    output_detail = dict(cached_record["output"])
    result = ProcessResult(
        source=str(input_file),
        status=str(cached_record["status"]),
        confidence=float(cached_record["confidence"]),
        format_id=str(cached_record["format_id"]),
        layout=str(cached_record["layout"]),
        strip_mode=str(cached_record["strip_mode"]),
        count=int(cached_record["count"]),
        final_review_reasons=list(cached_record["final_review_reasons"]),
        output_files=list(output_files),
        review_copy=output_detail["review_copy"],
        detail={**dict(cached_record["detail"]), **detail_extra},
        profile=json_safe(asdict(profile)),
        warnings=warnings,
        policy_id=str(cached_record["policy_id"]),
    )
    report_record = dict(cached_record)
    report_record["detail"] = dict(result.detail)
    output_detail = dict(report_record["output"])
    output_detail["output_files"] = list(output_files)
    output_detail["warnings"] = list(warnings)
    report_record["output"] = output_detail
    result.report_record = report_record
    return result
