from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..output.filesystem import FilesystemIdentity
from ..output.ownership import write_owned_output_manifest
from ..run_status import RunTerminalOutcome
from .identity import runtime_environment_identity
from .outcome import FailureStage, RuntimeArtifacts


@dataclass(frozen=True)
class SourceTerminalRecord:
    input_ordinal: int
    source_name: str
    portable_stem: str
    size: int | None
    mtime_ns: int | None
    terminal_status: RunTerminalOutcome
    failure_stage: FailureStage | None
    error_code: str | None
    error_message: str | None
    artifacts: RuntimeArtifacts

    def __post_init__(self) -> None:
        if self.input_ordinal <= 0 or not self.source_name or not self.portable_stem:
            raise ValueError("source terminal identity is incomplete")
        failures = (self.failure_stage, self.error_code, self.error_message)
        if self.terminal_status == RunTerminalOutcome.RUNTIME_ERROR:
            if any(value is None for value in failures):
                raise ValueError("runtime_error requires complete failure detail")
        elif any(value is not None for value in failures):
            raise ValueError("valid source terminal cannot contain failure detail")

    def as_record(self, output_root: Path) -> dict[str, Any]:
        def relative(value: str | None) -> str | None:
            if value is None:
                return None
            return Path(value).relative_to(output_root).as_posix()

        return {
            "input_ordinal": self.input_ordinal,
            "source_name": self.source_name,
            "portable_stem": self.portable_stem,
            "size": self.size,
            "mtime_ns": self.mtime_ns,
            "terminal_status": self.terminal_status.value,
            "failure_stage": (
                None if self.failure_stage is None else self.failure_stage.value
            ),
            "error_code": self.error_code,
            "error_message": self.error_message,
            "artifacts": {
                "frame_outputs": [relative(path) for path in self.artifacts.frame_outputs],
                "review_copy": relative(self.artifacts.review_copy),
                "debug_analysis": relative(self.artifacts.debug_analysis),
            },
        }


def write_run_manifest(
    output_root: Path,
    *,
    run_id: str,
    started_at_utc: str,
    finished_at_utc: str,
    jobs: int,
    filesystem: FilesystemIdentity,
    best_effort_consent: str,
    disk_reservation: dict[str, int],
    terminals: tuple[SourceTerminalRecord, ...],
) -> Path:
    if not any(
        item.terminal_status != RunTerminalOutcome.RUNTIME_ERROR
        for item in terminals
    ):
        raise ValueError("at least one valid source terminal is required to publish")
    return write_owned_output_manifest(
        output_root,
        run_id=run_id,
        run_record={
            "started_at_utc": started_at_utc,
            "finished_at_utc": finished_at_utc,
            "jobs": jobs,
            "filesystem": filesystem.as_record(),
            "best_effort_consent": best_effort_consent,
            "disk_reservation": dict(disk_reservation),
            "runtime_environment": runtime_environment_identity(),
        },
        terminal_records=tuple(
            item.as_record(output_root)
            for item in sorted(terminals, key=lambda value: value.input_ordinal)
        ),
    )
