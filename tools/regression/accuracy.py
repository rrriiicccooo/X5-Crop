"""External source-identity foundation for the V5 accuracy verifier."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GOLD_COHORT_PATH = Path(__file__).with_name("cohorts") / "gold_accuracy.jsonl"
EXPECTED_SOURCE_COUNT = 9


def _source_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_gold_source_identities() -> tuple[dict[str, object], ...]:
    records = tuple(
        json.loads(line)
        for line in GOLD_COHORT_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    if len(records) != EXPECTED_SOURCE_COUNT:
        raise ValueError("gold accuracy cohort must contain exactly nine sources")
    project_root = PROJECT_ROOT.resolve()
    sample_ids: set[str] = set()
    for record in records:
        sample_id = str(record.get("sample_id", ""))
        relative = Path(str(record.get("source_relative_path", "")))
        source = (PROJECT_ROOT / relative).resolve()
        expected_sha = str(record.get("source_sha256", "")).lower()
        if (
            not sample_id
            or sample_id in sample_ids
            or record.get("validation_role") != "gold_accuracy_blocking"
            or relative.is_absolute()
            or not source.is_relative_to(project_root)
            or not source.is_file()
            or len(expected_sha) != 64
            or _source_sha256(source) != expected_sha
        ):
            raise ValueError(f"gold source identity is invalid: {sample_id or relative}")
        sample_ids.add(sample_id)
    return records


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--identity-only",
        action="store_true",
        help="Validate the source-bound cohort without running the active detector.",
    )
    args = parser.parse_args(argv)
    records = validate_gold_source_identities()
    if not args.identity_only:
        raise RuntimeError(
            "V5 accuracy execution becomes active with the V5 runtime/schema cutover"
        )
    print(f"gold source identities: {len(records)}/{EXPECTED_SOURCE_COUNT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
