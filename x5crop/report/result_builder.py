from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

from ..detection.decision.model import FinalDetection
from ..detection.candidate.selection.model import SelectionResult
from ..detection.evidence.transform_geometry import TransformGeometryEvidence
from ..io.model import ImageProfile
from ..utils import json_safe
from .model import ReportResult
from .record import report_record_for_final_detection


def result_from_detection(
    input_file: Path,
    detection: FinalDetection,
    selection: SelectionResult,
    profile: ImageProfile,
    output_files: list[str],
    review_copy: Optional[str],
    warnings: list[str],
    *,
    configuration_detail: dict[str, Any],
    transform_geometry: TransformGeometryEvidence,
    analysis_reuse_signature: dict[str, Any],
) -> ReportResult:
    record = report_record_for_final_detection(
        detection,
        selection,
        source=str(input_file),
        profile=json_safe(asdict(profile)),
        output_files=output_files,
        review_copy=review_copy,
        warnings=warnings,
        configuration=configuration_detail,
        transform_geometry=transform_geometry,
        analysis_reuse_signature=analysis_reuse_signature,
    )
    return ReportResult(record=record)


def result_from_cached_record(
    input_file: Path,
    cached_record: dict[str, Any],
    profile: ImageProfile,
    warnings: list[str],
    *,
    output_files: list[str],
    review_copy: str | None,
) -> ReportResult:
    report_record = dict(cached_record)
    report_record["source"] = str(input_file)
    input_detail = dict(cached_record["input"])
    input_detail["profile"] = json_safe(asdict(profile))
    report_record["input"] = input_detail
    report_record["analysis_reuse"] = {"used": True}
    output_detail = dict(cached_record["output"])
    output_detail["output_files"] = list(output_files)
    output_detail["review_copy"] = review_copy
    output_detail["warnings"] = list(warnings)
    report_record["output"] = output_detail
    return ReportResult(record=json_safe(report_record))
