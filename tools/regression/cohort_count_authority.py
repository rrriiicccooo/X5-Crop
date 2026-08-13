"""Validate explicit count authority without consulting source filenames."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


COHORT_DIRECTORY = Path(__file__).with_name("cohorts")
COHORT_PATHS = tuple(sorted(COHORT_DIRECTORY.glob("*.jsonl")))
MATCHED_HOLDER_AUTHORITY = "matched_holder_full_count"
USER_PARTIAL_AUTHORITY = "user_explicit_partial_count"


def _rows(paths: Iterable[Path]) -> tuple[dict[str, Any], ...]:
    return tuple(
        json.loads(line)
        for path in paths
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def confirmed_slot_count(row: dict[str, Any]) -> int | None:
    if "requested_count" in row:
        raise ValueError("cohort uses removed requested_count field")
    value = row.get("confirmed_slot_count")
    return None if value is None else int(value)


def validate_count_authority(
    paths: Iterable[Path] = COHORT_PATHS,
) -> None:
    authorities_by_sha: dict[str, tuple[str, int | None, str]] = {}
    for row in _rows(paths):
        sample_id = str(row.get("sample_id", "<unknown>"))
        strip_mode = row.get("strip_mode")
        count = confirmed_slot_count(row)
        authority = row.get("count_authority")
        if strip_mode == "partial" and not (
            count is not None
            and count > 0
            and authority == USER_PARTIAL_AUTHORITY
        ):
            raise ValueError(
                f"partial cohort count authority is incomplete: {sample_id}"
            )
        if strip_mode == "full" and not (
            count is None and authority == MATCHED_HOLDER_AUTHORITY
        ):
            raise ValueError(
                f"full cohort must use matched-holder count authority: {sample_id}"
            )
        if strip_mode not in {"full", "partial"}:
            raise ValueError(f"cohort strip mode is invalid: {sample_id}")
        digest = str(row.get("source_sha256", "")).lower()
        if len(digest) != 64:
            continue
        identity = (strip_mode, count, str(authority))
        previous = authorities_by_sha.setdefault(digest, identity)
        if previous != identity:
            raise ValueError(
                f"source SHA has conflicting mode/count authority: {sample_id}"
            )


if __name__ == "__main__":
    validate_count_authority()
    print("cohort count authority: valid")
