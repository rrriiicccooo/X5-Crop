"""Audit confirmed annotations and build the tracked development-gold cohort."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable, Sequence

from tools.manual_annotation.model import (
    BASELINE_SCHEMA,
    canonical_record_sha256,
    confirmed_baseline_rows,
    geometry_snapshot,
)
from tools.manual_annotation.workspace import ReviewWorkspace

from .accuracy import (
    CONFIRMED_GEOMETRY_KEYS,
    DEVELOPMENT_GOLD_COHORT_PATH,
    DEVELOPMENT_GOLD_COHORT_SCHEMA,
    DEVELOPMENT_GOLD_COMPLETION_SCOPE,
    validate_gold_evaluation_role,
    validate_gold_source_identities,
)
from .diagnostic_cohort import DIAGNOSTIC_COHORT_PATH
from .file_identity import sha256_file
from .gold_geometry import GOLD_ACCEPTANCE_CONTRACT


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _jsonl(path: Path) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: row must be an object")
        rows.append(value)
    return tuple(rows)


def _safe_repository_file(
    workspace: ReviewWorkspace,
    relative_path: object,
) -> Path:
    if not isinstance(relative_path, str) or not relative_path:
        raise ValueError("confirmed evidence path is invalid")
    path = workspace.resolve_repository_path(relative_path)
    if not path.is_file():
        raise ValueError(f"confirmed evidence is missing: {relative_path}")
    return path


def audit_current_confirmed_rows(
    repository_root: Path = PROJECT_ROOT,
) -> tuple[dict[str, Any], ...]:
    """Rebuild and independently verify every current confirmed task row."""

    workspace = ReviewWorkspace(repository_root)
    records: list[dict[str, Any]] = []
    verified_source_paths: set[str] = set()
    verified_artifacts: set[str] = set()
    for source_sha, members in sorted(
        workspace.groups.items(),
        key=lambda item: int(item[1][0]["sort_index"]),
    ):
        record = workspace.load_record(source_sha)
        if record["state"] != "user_confirmed":
            identities = "/".join(str(row["sample_id"]) for row in members)
            raise ValueError(f"gold calibration is incomplete: {identities}")
        confirmation = record["confirmation"]
        if (
            canonical_record_sha256(geometry_snapshot(record))
            != confirmation["proposal_snapshot_sha256"]
        ):
            raise ValueError(
                f"confirmed geometry snapshot changed: {members[0]['sample_id']}"
            )
        for member in members:
            source_relative = str(member["source_relative_path"])
            if source_relative in verified_source_paths:
                continue
            source = _safe_repository_file(workspace, source_relative)
            if sha256_file(source) != source_sha:
                raise ValueError(
                    f"confirmed source SHA-256 changed: {member['sample_id']}"
                )
            verified_source_paths.add(source_relative)
        artifact_relative = str(confirmation["review_artifact_relative_path"])
        if artifact_relative not in verified_artifacts:
            artifact = _safe_repository_file(workspace, artifact_relative)
            if sha256_file(artifact) != confirmation["review_artifact_sha256"]:
                raise ValueError(
                    f"confirmed review artifact changed: {members[0]['sample_id']}"
                )
            verified_artifacts.add(artifact_relative)
        records.append(record)

    derived = tuple(
        sorted(
            (
                row
                for record in records
                for row in confirmed_baseline_rows(record)
            ),
            key=lambda row: str(row["sample_id"]),
        )
    )
    stored = _jsonl(workspace.confirmed_rows_path)
    if stored != derived:
        raise ValueError("confirmed geometry summary is not the current derivation")
    if len(derived) != len(workspace.manifest_rows):
        raise ValueError("confirmed geometry does not cover every current task exactly once")
    return derived


def build_gold_cohort_records(
    confirmed_rows: Iterable[dict[str, Any]],
    diagnostic_rows: Iterable[dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Bind confirmed geometry to the tracked task identities without inference."""

    confirmed_by_id: dict[str, dict[str, Any]] = {}
    for geometry in confirmed_rows:
        sample_id = str(geometry.get("sample_id", ""))
        if (
            not sample_id
            or sample_id in confirmed_by_id
            or set(geometry) != CONFIRMED_GEOMETRY_KEYS
            or geometry.get("baseline_schema") != BASELINE_SCHEMA
            or geometry.get("status") != "user_confirmed"
        ):
            raise ValueError(f"confirmed geometry row is invalid: {sample_id}")
        confirmed_by_id[sample_id] = geometry

    ordered_diagnostic = tuple(
        sorted(diagnostic_rows, key=lambda row: int(row["sort_index"]))
    )
    diagnostic_ids = [str(row.get("sample_id", "")) for row in ordered_diagnostic]
    if (
        len(set(diagnostic_ids)) != len(diagnostic_ids)
        or set(diagnostic_ids) != set(confirmed_by_id)
    ):
        raise ValueError("confirmed geometry and tracked task identities disagree")

    records: list[dict[str, Any]] = []
    for diagnostic in ordered_diagnostic:
        sample_id = str(diagnostic["sample_id"])
        geometry = confirmed_by_id[sample_id]
        for key in (
            "source_relative_path",
            "source_sha256",
            "format_id",
            "count",
        ):
            if geometry.get(key) != diagnostic.get(key):
                raise ValueError(f"confirmed task authority changed: {sample_id}:{key}")
        evaluation = geometry.get("evaluation_role")
        if not isinstance(evaluation, dict):
            raise ValueError(f"confirmed evaluation role is invalid: {sample_id}")
        record = {
            "cohort_schema": DEVELOPMENT_GOLD_COHORT_SCHEMA,
            "completion_scope": DEVELOPMENT_GOLD_COMPLETION_SCOPE,
            "sample_id": sample_id,
            "source_relative_path": geometry["source_relative_path"],
            "source_sha256": geometry["source_sha256"],
            "format_id": geometry["format_id"],
            "count": geometry["count"],
            "validation_role": "development_gold",
            "cohort_role": evaluation["cohort_role"],
            "acceptance_contract": GOLD_ACCEPTANCE_CONTRACT,
            "acceptance_baseline_schema": BASELINE_SCHEMA,
            "geometry_digest": canonical_record_sha256(geometry),
            "confirmed_geometry": geometry,
        }
        validate_gold_evaluation_role(record)
        records.append(record)
    return tuple(records)


def gold_cohort_jsonl(records: Iterable[dict[str, Any]]) -> str:
    return "".join(
        json.dumps(
            record,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
        for record in records
    )


def current_gold_cohort_records(
    repository_root: Path = PROJECT_ROOT,
) -> tuple[dict[str, Any], ...]:
    confirmed = audit_current_confirmed_rows(repository_root)
    diagnostic = _jsonl(repository_root / DIAGNOSTIC_COHORT_PATH.relative_to(PROJECT_ROOT))
    return build_gold_cohort_records(confirmed, diagnostic)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument(
        "--write",
        action="store_true",
        help="replace the tracked cohort with the complete audited derivation",
    )
    args = parser.parse_args(argv)
    try:
        records = current_gold_cohort_records()
        payload = gold_cohort_jsonl(records)
        if args.write:
            DEVELOPMENT_GOLD_COHORT_PATH.write_text(payload, encoding="utf-8")
            validate_gold_source_identities()
            state = "written"
        else:
            current = DEVELOPMENT_GOLD_COHORT_PATH.read_text(encoding="utf-8")
            if current != payload:
                raise ValueError("tracked gold cohort is not the current audited derivation")
            state = "current"
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"gold cohort: FAIL: {error}")
        return 1
    roles: dict[str, int] = {"nominal": 0, "challenge": 0}
    for record in records:
        roles[str(record["cohort_role"])] += 1
    print(
        f"gold cohort: {state}; tasks={len(records)}; "
        f"nominal={roles['nominal']}; challenge={roles['challenge']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
