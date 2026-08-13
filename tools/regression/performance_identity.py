"""Own the external 24-source V5 performance workload identity."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from .cohort_count_authority import validate_count_authority
from .file_identity import sha256_file


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PERFORMANCE_COHORT_PATH = (
    Path(__file__).with_name("cohorts") / "production_performance.jsonl"
)
COHORT_SCHEMA = "x5crop_performance_cohort_v1"
FIXED_SOURCE_COUNT = 24


@dataclass(frozen=True)
class PerformanceSourceIdentity:
    sample_id: str
    source_relative_path: str
    source_sha256: str
    format_id: str
    strip_mode: str
    confirmed_slot_count: int | None
    count_authority: str
    compression: str

    @property
    def source_path(self) -> Path:
        return PROJECT_ROOT / self.source_relative_path


def cohort_sha256() -> str:
    return hashlib.sha256(PERFORMANCE_COHORT_PATH.read_bytes()).hexdigest()


def load_performance_sources(
    *,
    verify_source_files: bool = True,
) -> tuple[PerformanceSourceIdentity, ...]:
    validate_count_authority()
    rows: tuple[dict[str, Any], ...] = tuple(
        json.loads(line)
        for line in PERFORMANCE_COHORT_PATH.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    )
    if len(rows) != FIXED_SOURCE_COUNT:
        raise ValueError("performance cohort must contain exactly 24 sources")
    project_root = PROJECT_ROOT.resolve()
    sources: list[PerformanceSourceIdentity] = []
    for row in rows:
        source = PerformanceSourceIdentity(
            sample_id=str(row.get("sample_id", "")),
            source_relative_path=str(row.get("source_relative_path", "")),
            source_sha256=str(row.get("source_sha256", "")).lower(),
            format_id=str(row.get("format_id", "")),
            strip_mode=str(row.get("strip_mode", "")),
            confirmed_slot_count=(
                None
                if row.get("confirmed_slot_count") is None
                else int(row["confirmed_slot_count"])
            ),
            count_authority=str(row.get("count_authority", "")),
            compression=str(row.get("compression", "")),
        )
        path = source.source_path.resolve()
        if (
            row.get("cohort_schema") != COHORT_SCHEMA
            or not source.sample_id
            or len(source.source_sha256) != 64
            or Path(source.source_relative_path).is_absolute()
            or not path.is_relative_to(project_root)
            or (
                verify_source_files
                and (
                    not path.is_file()
                    or sha256_file(path) != source.source_sha256
                )
            )
        ):
            raise ValueError(
                f"performance source identity is invalid: {source.sample_id}"
            )
        sources.append(source)
    if len({item.sample_id for item in sources}) != len(sources):
        raise ValueError("performance sample identities must be unique")
    return tuple(sources)


def main() -> int:
    sources = load_performance_sources(verify_source_files=True)
    print(
        f"performance identity: {len(sources)}/{FIXED_SOURCE_COUNT} sources "
        f"sha256={cohort_sha256()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
