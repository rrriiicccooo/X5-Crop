"""Validate explicit cohort slot counts without consulting filenames."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


COHORT_DIRECTORY = Path(__file__).with_name("cohorts")
COHORT_PATHS = tuple(sorted(COHORT_DIRECTORY.glob("*.jsonl")))


def _rows(paths: Iterable[Path]) -> tuple[dict[str, Any], ...]:
    return tuple(
        json.loads(line)
        for path in paths
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def cohort_slot_count(row: dict[str, Any]) -> int:
    value = row.get("count")
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError("cohort requires one explicit positive count")
    return value


def validate_cohort_counts(
    paths: Iterable[Path] = COHORT_PATHS,
) -> None:
    counts_by_sha: dict[str, tuple[str, int]] = {}
    for row in _rows(paths):
        sample_id = str(row.get("sample_id", "<unknown>"))
        count = cohort_slot_count(row)
        format_id = str(row.get("format_id", ""))
        if not format_id:
            raise ValueError(f"cohort format is missing: {sample_id}")
        digest = str(row.get("source_sha256", "")).lower()
        if len(digest) != 64:
            continue
        identity = (format_id, count)
        previous = counts_by_sha.setdefault(digest, identity)
        if previous != identity:
            raise ValueError(
                f"source SHA has conflicting format/count authority: {sample_id}"
            )


if __name__ == "__main__":
    validate_cohort_counts()
    print("cohort count authority: valid")
