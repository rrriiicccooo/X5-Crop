from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from pathlib import Path
from typing import Any

from ..report.model import ReportResult


class FailureStage(str, Enum):
    INPUT_PROFILE = "input_profile"
    IMAGE_READ = "image_read"
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
    domain_pixels: int | None
    content_runs: int | None
    content_components: int | None
    censored_content_components: int | None
    measurement_query_count: int | None
    raw_transition_count: int | None
    line_family_count: int | None
    physical_geometry_count: int | None
    pre_join_state_count: int | None
    post_join_state_count: int | None
    deduplicated_state_count: int | None
    sequence_phase_class_count: int | None
    dp_states: int | None
    dp_transitions: int | None
    pixel_query_count: int | None
    shared_measurement_reuse_count: int | None
    peak_temporary_bytes: int | None

    def __post_init__(self) -> None:
        values = tuple(self.__dict__.values())
        if all(value is None for value in values):
            return
        if any(value is None for value in values):
            raise ValueError("runtime metrics must be complete or unavailable")
        assert self.processing_seconds is not None
        assert self.detection_seconds is not None
        if any(
            not math.isfinite(value) or value < 0.0
            for value in (self.processing_seconds, self.detection_seconds)
        ):
            raise ValueError("runtime durations must be finite")
        if self.detection_seconds > self.processing_seconds:
            raise ValueError("detection cannot exceed total processing time")
        counts = values[2:]
        if any(value is None or value < 0 for value in counts):
            raise ValueError("runtime counters cannot be negative")

    @classmethod
    def unavailable(cls) -> "RuntimeMetrics":
        return cls(*(None for _ in range(19)))

    @property
    def available(self) -> bool:
        return self.processing_seconds is not None

    def as_record(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class RuntimeArtifacts:
    frame_outputs: tuple[str, ...]
    review_copy: str | None
    debug_analysis: str | None

    @classmethod
    def empty(cls) -> "RuntimeArtifacts":
        return cls((), None, None)

    def as_record(self) -> dict[str, Any]:
        return {
            "frame_outputs": list(self.frame_outputs),
            "review_copy": self.review_copy,
            "debug_analysis": self.debug_analysis,
        }


@dataclass(frozen=True)
class CompletedInput:
    result: ReportResult
    artifacts: RuntimeArtifacts
    metrics: RuntimeMetrics


@dataclass(frozen=True)
class FailedInput:
    source: Path
    failure_stage: FailureStage
    error_code: str
    error_message: str
    artifacts: RuntimeArtifacts
    traceback_text: str | None
    metrics: RuntimeMetrics


InputProcessingOutcome = CompletedInput | FailedInput
