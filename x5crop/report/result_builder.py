from __future__ import annotations

from pathlib import Path
from typing import Any

from ..detection.final.model import FinalDetection
from ..detection.workspace import DetectionWorkspace
from ..io.model import ImageProfile
from .model import ReportResult
from .read_models import typed_read_model
from .record import report_record_for_final_detection


def result_from_detection(
    input_file: Path,
    detection: FinalDetection,
    profile: ImageProfile,
    workspace: DetectionWorkspace,
    output_files: list[str],
    review_copy: str | None,
    warnings: list[str],
    *,
    configuration_detail: dict[str, Any],
    runtime_identity: dict[str, Any],
) -> ReportResult:
    return ReportResult(
        record=report_record_for_final_detection(
            detection,
            source=str(input_file),
            profile=typed_read_model(profile),
            workspace=workspace,
            output_files=output_files,
            review_copy=review_copy,
            warnings=warnings,
            configuration=configuration_detail,
            runtime_identity=runtime_identity,
        )
    )
