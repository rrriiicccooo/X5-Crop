"""Validate explicit count authority without consulting source filenames."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


COHORT_DIRECTORY = Path(__file__).with_name("cohorts")
COHORT_PATHS = tuple(sorted(COHORT_DIRECTORY.glob("*.jsonl")))
EXPLICIT_AUTHORITY = "explicit_user_confirmation"


def _rows(paths: Iterable[Path]) -> tuple[dict[str, Any], ...]:
    return tuple(
        json.loads(line)
        for path in paths
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def confirmed_slot_count(row: dict[str, Any]) -> int | None:
    value = row.get("confirmed_slot_count", row.get("confirmed_photo_count"))
    return None if value is None else int(value)


def validate_count_authority(
    paths: Iterable[Path] = COHORT_PATHS,
) -> None:
    authorities_by_sha: dict[str, tuple[int, str]] = {}
    for row in _rows(paths):
        sample_id = str(row.get("sample_id", "<unknown>"))
        strip_mode = row.get("strip_mode")
        count = confirmed_slot_count(row)
        authority = row.get("confirmed_count_authority")
        if strip_mode == "partial" and (
            count is None or count <= 0 or authority != EXPLICIT_AUTHORITY
        ):
            raise ValueError(
                f"partial cohort count authority is incomplete: {sample_id}"
            )
        if count is None:
            continue
        if count <= 0 or not isinstance(authority, str) or not authority:
            raise ValueError(f"cohort count authority is invalid: {sample_id}")
        digest = str(row.get("source_sha256", "")).lower()
        if len(digest) != 64:
            continue
        identity = (count, authority)
        previous = authorities_by_sha.setdefault(digest, identity)
        if previous != identity:
            raise ValueError(
                f"source SHA has conflicting count authority: {sample_id}"
            )


if __name__ == "__main__":
    validate_count_authority()
    print("cohort count authority: valid")
