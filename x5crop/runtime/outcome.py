from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import traceback
from typing import Any


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
    result: dict[str, Any]
    artifacts: RuntimeArtifacts


@dataclass(frozen=True)
class FailedInput:
    source: Path
    failure_stage: FailureStage
    error_code: str
    error_message: str
    artifacts: RuntimeArtifacts
    traceback_text: str | None
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
            error_errno=(exc.errno if isinstance(exc, OSError) else None),
        )


InputProcessingOutcome = CompletedInput | FailedInput
