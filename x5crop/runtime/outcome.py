from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ..report.model import ReportResult


class FailureStage(str, Enum):
    INPUT_PROFILE = "input_profile"
    ANALYSIS_REUSE = "analysis_reuse"
    IMAGE_READ = "image_read"
    PREPROCESS = "preprocess"
    DETECTION = "detection"
    DECISION = "decision"
    FINALIZATION = "finalization"
    OUTPUT = "output"
    DEBUG = "debug"
    REPORT_VALIDATION = "report_validation"
    REPORT_WRITE = "report_write"
    WORKER = "worker"


@dataclass(frozen=True)
class CompletedInput:
    result: ReportResult
    debug_analysis: str | None


@dataclass(frozen=True)
class FailedInput:
    source: Path
    failure_stage: FailureStage
    error_code: str
    error_message: str
    debug_analysis: str | None
    output_files: tuple[str, ...]
    traceback_text: str | None


InputProcessingOutcome = CompletedInput | FailedInput
