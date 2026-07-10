from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

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
    *,
    deskew_detail: dict[str, Any],
    analysis_cache_metadata: dict[str, Any],
) -> ProcessResult:
    record = report_record_for_final_detection(
        detection,
        source=str(input_file),
        profile=json_safe(asdict(profile)),
        output_files=output_files,
        review_copy=review_copy,
        warnings=warnings,
        deskew_detail=deskew_detail,
        analysis_cache_metadata=analysis_cache_metadata,
    )
    return ProcessResult(record=record)


def result_from_cached_record(
    input_file: Path,
    cached_record: dict[str, Any],
    profile: ImageProfile,
    warnings: list[str],
    *,
    output_files: list[str],
) -> ProcessResult:
    report_record = dict(cached_record)
    report_record["source"] = str(input_file)
    report_record["profile"] = json_safe(asdict(profile))
    report_record["analysis_reuse"] = {"used": True}
    output_detail = dict(cached_record["output"])
    output_detail["output_files"] = list(output_files)
    output_detail["warnings"] = list(warnings)
    report_record["output"] = output_detail
    return ProcessResult(record=json_safe(report_record))
