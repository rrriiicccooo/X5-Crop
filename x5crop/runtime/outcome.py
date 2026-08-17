from __future__ import annotations

from dataclasses import dataclass, fields
from enum import Enum
import math
from pathlib import Path
import traceback
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
    REPORT_BUILD = "report_build"
    WORKER = "worker"


@dataclass(frozen=True)
class RuntimeMetrics:
    processing_seconds: float | None
    detection_seconds: float | None
    domain_pixels: int | None
    measurement_query_count: int | None
    pixel_query_count: int | None
    basic_profile_coordinate_count: int | None
    basic_profile_run_count: int | None
    registered_sequence_observation_count: int | None
    phase_hypothesis_count: int | None
    separator_lattice_hypothesis_count: int | None
    phase_fit_pass_count: int | None
    phase_role_lookup_count: int | None
    phase_role_binding_count: int | None
    local_relation_evaluation_count: int | None
    cross_registered_run_count: int | None
    cross_fit_evaluation_count: int | None
    placement_evaluation_count: int | None
    boundary_evaluation_count: int | None
    content_evaluation_count: int | None
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
        return cls(*(None for _ in fields(cls)))

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
    error_errno: int | None = None

    @classmethod
    def from_exception(
        cls,
        source: Path,
        exc: Exception,
        *,
        stage: FailureStage = FailureStage.WORKER,
    ) -> "FailedInput":
        return cls(
            source=source,
            failure_stage=stage,
            error_code=type(exc).__name__,
            error_message=str(exc),
            artifacts=RuntimeArtifacts.empty(),
            traceback_text=traceback.format_exc(),
            metrics=RuntimeMetrics.unavailable(),
            error_errno=(exc.errno if isinstance(exc, OSError) else None),
        )


InputProcessingOutcome = CompletedInput | FailedInput
