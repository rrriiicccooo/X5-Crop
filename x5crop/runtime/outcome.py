from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from pathlib import Path
from typing import Any

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
class RuntimeMetrics:
    processing_seconds: float | None
    detection_seconds: float | None
    assessed_candidates: int | None
    assignment_evaluations: int | None
    measurement_cache_hits: int | None
    measurement_cache_misses: int | None

    def __post_init__(self) -> None:
        values = (
            self.processing_seconds,
            self.detection_seconds,
            self.assessed_candidates,
            self.assignment_evaluations,
            self.measurement_cache_hits,
            self.measurement_cache_misses,
        )
        if all(value is None for value in values):
            return
        if any(value is None for value in values):
            raise ValueError("runtime metrics must be complete or unavailable")
        durations = (self.processing_seconds, self.detection_seconds)
        if any(not math.isfinite(value) or value < 0.0 for value in durations):
            raise ValueError("runtime durations must be finite and nonnegative")
        if self.detection_seconds > self.processing_seconds:
            raise ValueError("detection duration cannot exceed input processing duration")
        counts = (
            self.assessed_candidates,
            self.assignment_evaluations,
            self.measurement_cache_hits,
            self.measurement_cache_misses,
        )
        if any(value < 0 for value in counts):
            raise ValueError("runtime counters cannot be negative")

    @classmethod
    def unavailable(cls) -> RuntimeMetrics:
        return cls(None, None, None, None, None, None)

    @property
    def available(self) -> bool:
        return self.processing_seconds is not None

    def as_record(self) -> dict[str, Any]:
        return {
            "processing_seconds": self.processing_seconds,
            "detection_seconds": self.detection_seconds,
            "assessed_candidates": self.assessed_candidates,
            "assignment_evaluations": self.assignment_evaluations,
            "measurement_cache_hits": self.measurement_cache_hits,
            "measurement_cache_misses": self.measurement_cache_misses,
        }


@dataclass(frozen=True)
class CompletedInput:
    result: ReportResult
    debug_analysis: str | None
    metrics: RuntimeMetrics


@dataclass(frozen=True)
class FailedInput:
    source: Path
    failure_stage: FailureStage
    error_code: str
    error_message: str
    debug_analysis: str | None
    output_files: tuple[str, ...]
    traceback_text: str | None
    metrics: RuntimeMetrics


InputProcessingOutcome = CompletedInput | FailedInput
