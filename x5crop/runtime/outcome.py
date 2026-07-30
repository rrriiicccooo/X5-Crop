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
    exact_measurement_count: int | None
    exact_cache_hit_count: int | None
    separator_line_observations: int | None
    placement_seeds: int | None
    candidate_builds: int | None
    dp_states: int | None
    dp_transitions: int | None
    retained_proposals: int | None
    peak_temporary_bytes: int | None

    def __post_init__(self) -> None:
        values = (
            self.processing_seconds,
            self.detection_seconds,
            self.domain_pixels,
            self.content_runs,
            self.content_components,
            self.censored_content_components,
            self.exact_measurement_count,
            self.exact_cache_hit_count,
            self.separator_line_observations,
            self.placement_seeds,
            self.candidate_builds,
            self.dp_states,
            self.dp_transitions,
            self.retained_proposals,
            self.peak_temporary_bytes,
        )
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
        counts = (
            self.domain_pixels,
            self.content_runs,
            self.content_components,
            self.censored_content_components,
            self.exact_measurement_count,
            self.exact_cache_hit_count,
            self.separator_line_observations,
            self.placement_seeds,
            self.candidate_builds,
            self.dp_states,
            self.dp_transitions,
            self.retained_proposals,
            self.peak_temporary_bytes,
        )
        if any(value is None or value < 0 for value in counts):
            raise ValueError("runtime counters cannot be negative")

    @classmethod
    def unavailable(cls) -> "RuntimeMetrics":
        return cls(
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        )

    @property
    def available(self) -> bool:
        return self.processing_seconds is not None

    def as_record(self) -> dict[str, Any]:
        return {
            "processing_seconds": self.processing_seconds,
            "detection_seconds": self.detection_seconds,
            "domain_pixels": self.domain_pixels,
            "content_runs": self.content_runs,
            "content_components": self.content_components,
            "censored_content_components": self.censored_content_components,
            "exact_measurement_count": self.exact_measurement_count,
            "exact_cache_hit_count": self.exact_cache_hit_count,
            "separator_line_observations": self.separator_line_observations,
            "placement_seeds": self.placement_seeds,
            "candidate_builds": self.candidate_builds,
            "dp_states": self.dp_states,
            "dp_transitions": self.dp_transitions,
            "retained_proposals": self.retained_proposals,
            "peak_temporary_bytes": self.peak_temporary_bytes,
        }


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
