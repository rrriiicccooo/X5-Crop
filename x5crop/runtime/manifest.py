from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from ..app_info import RUN_MANIFEST_JSONL_NAME
from ..output.surface import output_directory_for
from ..run_config import RunConfig
from ..run_status import RunTerminalOutcome
from .outcome import FailureStage


@dataclass(frozen=True)
class RunManifestRecord:
    source: str
    terminal_outcome: RunTerminalOutcome
    failure_stage: FailureStage | None
    error_code: str | None
    error_message: str | None
    report_written: bool
    debug_analysis: str | None
    output_files: tuple[str, ...]

    def __post_init__(self) -> None:
        failure_values = (
            self.failure_stage,
            self.error_code,
            self.error_message,
        )
        if self.terminal_outcome == RunTerminalOutcome.COMPLETED:
            if any(value is not None for value in failure_values):
                raise ValueError("Completed manifest record cannot contain failure detail")
            return
        if any(value is None for value in failure_values):
            raise ValueError("Runtime-error manifest record requires complete failure detail")

    def as_record(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "terminal_outcome": self.terminal_outcome.value,
            "failure_stage": (
                None if self.failure_stage is None else self.failure_stage.value
            ),
            "error_code": self.error_code,
            "error_message": self.error_message,
            "report_written": self.report_written,
            "debug_analysis": self.debug_analysis,
            "output_files": list(self.output_files),
        }


def append_run_manifest(
    input_file: Path,
    config: RunConfig,
    record: RunManifestRecord,
) -> Path:
    path = output_directory_for(input_file, config) / RUN_MANIFEST_JSONL_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record.as_record(), ensure_ascii=False) + "\n")
    return path
