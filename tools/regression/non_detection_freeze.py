"""Freeze all golden detection semantics while non-detection work proceeds."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from typing import Any, Iterable, Sequence

from .accuracy import (
    GOLD_COHORT_PATH,
    PROJECT_ROOT,
    _production_command,
    _validate_approved_geometry,
    validate_gold_source_identities,
)


BASELINE_PATH = Path(__file__).with_name("contracts") / "non_detection_freeze_v1.json"
PROTECTED_PATHS_PATH = (
    Path(__file__).with_name("contracts") / "non_detection_protected_paths_v1.txt"
)
BASELINE_SCHEMA = "x5crop_non_detection_freeze_v1"
NORMALIZER_SCHEMA = "x5crop_non_detection_task_v1"
BASELINE_COMMIT = "90e5e8c4"
PROTECTED_SINCE_COMMIT = "21da1131"
TASK_FIELDS = (
    "task_id",
    "status",
    "final_reasons",
    "candidate_gate",
    "decision_gate",
    "retained_placements",
    "canonical",
    "crop_envelopes",
    "direct_use_budgets",
    "transform_assessment",
    "comparator_verdict",
)
PIXEL_TOLERANCE = 1.0e-6
PHYSICAL_TOLERANCE = 1.0e-9
COMPARATOR_DEPENDENCIES = (
    "tools/regression/accuracy.py",
    "x5crop/report/identity.py",
    "x5crop/report/validation.py",
)


def _git(*args: str, check: bool = True) -> str:
    completed = subprocess.run(
        ("git", *args),
        cwd=PROJECT_ROOT,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout.strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_exact_keys(value: object, keys: Iterable[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or tuple(value) != tuple(keys):
        raise ValueError(f"{name} has missing, extra, or reordered fields")
    return value


def _task_ids(records: Iterable[dict[str, object]]) -> tuple[str, ...]:
    return tuple(
        f"{record['sample_id']}/{mode}"
        for record in records
        for mode in record["count_modes"]
    )


def _comparator_verdict(
    record: dict[str, object],
    report: dict[str, Any],
) -> dict[str, object]:
    status = str(report["decision"]["status"])
    try:
        if record["cohort_role"] == "nominal" and status != "approved_auto":
            raise ValueError("nominal task is not approved_auto")
        if record["cohort_role"] == "challenge" and status not in {
            "approved_auto",
            "needs_review",
        }:
            raise ValueError("challenge task has an invalid status")
        if status == "approved_auto":
            _validate_approved_geometry(record, report)
    except ValueError as exc:
        return {"accepted": False, "detail": str(exc)}
    return {"accepted": True, "detail": "accepted"}


def _semantic_digest(value: object) -> dict[str, object]:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "item_count": len(value) if isinstance(value, list) else 1,
        "sha256": hashlib.sha256(encoded).hexdigest(),
    }


def _sequence_placement_facts(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "placement_id": item["placement_id"],
        "template_seed_id": item["template_seed_id"],
        "phase_group_ids": item["phase_group_ids"],
        "source_geometry_id": item["source_geometry_id"],
        "roles": item["roles"],
        "phase_fit_interval_px": item["phase_fit_interval_px"],
        "phase_full_interval_px": item["phase_full_interval_px"],
        "nominal_pitch": item["nominal_pitch"],
        "local_advance_relations": item["local_advance_relations"],
        "canonical_positions_px": item["canonical_positions_px"],
        "fit_positions_px": item["fit_positions_px"],
        "full_positions_px": item["full_positions_px"],
        "sequence_edge_direction_intervals_degrees": item[
            "sequence_edge_direction_intervals_degrees"
        ],
        "safety_support_transition_ids": _semantic_digest(
            item["safety_support_transition_ids"]
        ),
        "observations": _semantic_digest(item["observations"]),
        "exclusion_authorized": item["exclusion_authorized"],
    }


def _cross_placement_facts(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "placement_id": item["placement_id"],
        "provisional_template_id": item["provisional_template_id"],
        "source_geometry_id": item["source_geometry_id"],
        "lane_reference_trace_px": item["lane_reference_trace_px"],
        "frame_reference_traces_px": item["frame_reference_traces_px"],
        "top_canonical_positions_px": item["top_canonical_positions_px"],
        "bottom_canonical_positions_px": item["bottom_canonical_positions_px"],
        "top_fit_positions_px": item["top_fit_positions_px"],
        "bottom_fit_positions_px": item["bottom_fit_positions_px"],
        "top_full_positions_px": item["top_full_positions_px"],
        "bottom_full_positions_px": item["bottom_full_positions_px"],
        "evidence": _semantic_digest(item["evidence"]),
    }


def _canonical_cross_facts(item: dict[str, Any]) -> dict[str, Any]:
    facts = dict(item)
    facts["evidence"] = _semantic_digest(item["evidence"])
    return facts


def normalize_task(
    record: dict[str, object],
    count_mode: str,
    report: dict[str, Any],
) -> dict[str, Any]:
    lanes = report["photo_geometry"]["lanes"]
    retained: list[dict[str, object]] = []
    canonical: list[dict[str, object]] = []
    envelopes: list[dict[str, object]] = []
    budgets: list[dict[str, object]] = []
    for lane in lanes:
        placement = lane["placement"]
        retained.append(
            {
                "lane_id": lane["lane_id"],
                "placements": [
                    {
                        "placement_id": item["placement_id"],
                        "component": item["component"],
                        "output_slot_count": item["output_slot_count"],
                        "direction": item["direction"],
                        "source_frame_geometry": item["source_frame_geometry"],
                        "sequence_placements": [
                            _sequence_placement_facts(value)
                            for value in item["sequence_placements"]
                        ],
                        "cross_placements": [
                            _cross_placement_facts(value)
                            for value in item["cross_placements"]
                        ],
                    }
                    for item in placement["retained_placements"]
                ],
            }
        )
        canonical.append(
            {
                "lane_id": lane["lane_id"],
                "canonical_placement_id": placement["canonical_placement_id"],
                "representatives": [
                    {
                        "placement_id": item["placement_id"],
                        "canonical_cross_placement": _canonical_cross_facts(
                            item["canonical_cross_placement"]
                        ),
                        "canonical": item["canonical"],
                    }
                    for item in placement["retained_placements"]
                ],
            }
        )
        envelopes.append(
            {
                "lane_id": lane["lane_id"],
                "values": placement["safe_crop_envelopes"],
            }
        )
        budgets.append(
            {
                "lane_id": lane["lane_id"],
                "values": placement["direct_use_budget_assessments"],
            }
        )
    normalized = {
        "task_id": f"{record['sample_id']}/{count_mode}",
        "status": report["decision"]["status"],
        "final_reasons": report["decision"]["final_review_reasons"],
        "candidate_gate": report["candidate_gate"],
        "decision_gate": report["decision"]["gate"],
        "retained_placements": retained,
        "canonical": canonical,
        "crop_envelopes": envelopes,
        "direct_use_budgets": budgets,
        "transform_assessment": report["output"]["finalization"][
            "transform_assessment"
        ],
        "comparator_verdict": _comparator_verdict(record, report),
    }
    return _require_exact_keys(normalized, TASK_FIELDS, "normalized task")


def _run_task(record: dict[str, object], count_mode: str) -> dict[str, Any]:
    source = (PROJECT_ROOT / str(record["source_relative_path"])).resolve()
    with TemporaryDirectory(prefix="x5crop-non-detection-") as temporary:
        output = Path(temporary) / "x5_crop_output"
        completed = subprocess.run(
            _production_command(source, output, record, count_mode),
            cwd=PROJECT_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if completed.returncode != 0:
            raise ValueError(
                f"{record['sample_id']}/{count_mode} production CLI failed:\n"
                + completed.stdout[-4000:]
            )
        report_path = output / "x5_crop_report.jsonl"
        rows = tuple(
            json.loads(line)
            for line in report_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        if len(rows) != 1:
            raise ValueError("freeze task must produce exactly one report record")
        return normalize_task(record, count_mode, rows[0])


def capture_current_tasks(
    records: Iterable[dict[str, object]],
) -> tuple[dict[str, Any], ...]:
    tasks: list[dict[str, Any]] = []
    for record in records:
        for count_mode in record["count_modes"]:
            task = _run_task(record, str(count_mode))
            tasks.append(task)
            print(
                f"{task['task_id']}: {task['status']} "
                f"comparator={task['comparator_verdict']['accepted']}"
            )
    return tuple(tasks)


def _cohort_schema(records: Sequence[dict[str, object]]) -> str:
    schemas = {str(record.get("cohort_schema", "")) for record in records}
    if len(schemas) != 1:
        raise ValueError("gold cohort schema is not unique")
    return schemas.pop()


def build_baseline() -> dict[str, Any]:
    if not _git("rev-parse", "HEAD").startswith(BASELINE_COMMIT):
        raise ValueError("baseline capture is allowed only at the frozen baseline commit")
    records = validate_gold_source_identities()
    task_ids = _task_ids(records)
    tasks = capture_current_tasks(records)
    if tuple(task["task_id"] for task in tasks) != task_ids:
        raise ValueError("captured tasks are incomplete or out of order")
    return {
        "schema": BASELINE_SCHEMA,
        "baseline_commit": _git("rev-parse", BASELINE_COMMIT),
        "protected_since_commit": _git("rev-parse", PROTECTED_SINCE_COMMIT),
        "cohort": {
            "path": GOLD_COHORT_PATH.relative_to(PROJECT_ROOT).as_posix(),
            "schema": _cohort_schema(records),
            "sha256": _sha256(GOLD_COHORT_PATH),
        },
        "normalizer": {
            "schema": NORMALIZER_SCHEMA,
            "fields": list(TASK_FIELDS),
            "pixel_coordinate_tolerance": PIXEL_TOLERANCE,
            "angle_and_physical_tolerance": PHYSICAL_TOLERANCE,
        },
        "comparator_dependencies": {
            path: _sha256(PROJECT_ROOT / path)
            for path in COMPARATOR_DEPENDENCIES
        },
        "task_ids": list(task_ids),
        "tasks": list(tasks),
    }


def validate_baseline(record: object) -> dict[str, Any]:
    baseline = _require_exact_keys(
        record,
        (
            "schema",
            "baseline_commit",
            "protected_since_commit",
            "cohort",
            "normalizer",
            "comparator_dependencies",
            "task_ids",
            "tasks",
        ),
        "freeze baseline",
    )
    cohort = _require_exact_keys(
        baseline["cohort"], ("path", "schema", "sha256"), "cohort identity"
    )
    normalizer = _require_exact_keys(
        baseline["normalizer"],
        (
            "schema",
            "fields",
            "pixel_coordinate_tolerance",
            "angle_and_physical_tolerance",
        ),
        "normalizer identity",
    )
    if (
        baseline["schema"] != BASELINE_SCHEMA
        or baseline["baseline_commit"] != _git("rev-parse", BASELINE_COMMIT)
        or baseline["protected_since_commit"]
        != _git("rev-parse", PROTECTED_SINCE_COMMIT)
        or cohort["path"] != GOLD_COHORT_PATH.relative_to(PROJECT_ROOT).as_posix()
        or cohort["sha256"] != _sha256(GOLD_COHORT_PATH)
        or normalizer
        != {
            "schema": NORMALIZER_SCHEMA,
            "fields": list(TASK_FIELDS),
            "pixel_coordinate_tolerance": PIXEL_TOLERANCE,
            "angle_and_physical_tolerance": PHYSICAL_TOLERANCE,
        }
        or baseline["comparator_dependencies"]
        != {
            path: _sha256(PROJECT_ROOT / path)
            for path in COMPARATOR_DEPENDENCIES
        }
        or not isinstance(baseline["tasks"], list)
        or baseline["task_ids"]
        != [task.get("task_id") for task in baseline["tasks"]]
        or len(baseline["task_ids"]) != 14
    ):
        raise ValueError("freeze baseline identity is invalid")
    for task in baseline["tasks"]:
        _require_exact_keys(task, TASK_FIELDS, f"baseline task {task.get('task_id')}")
    return baseline


def load_baseline() -> dict[str, Any]:
    return validate_baseline(json.loads(BASELINE_PATH.read_text(encoding="utf-8")))


def _number_tolerance(path: tuple[str, ...]) -> float:
    joined = ".".join(path).casefold()
    if any(token in joined for token in ("angle", "degrees", "_mm", "scale")):
        return PHYSICAL_TOLERANCE
    return PIXEL_TOLERANCE


def assert_semantically_equal(
    expected: object,
    actual: object,
    path: tuple[str, ...] = (),
) -> None:
    if isinstance(expected, bool) or isinstance(actual, bool):
        if expected is not actual:
            raise ValueError(f"semantic drift at {'.'.join(path)}")
        return
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        if not math.isclose(
            float(expected),
            float(actual),
            rel_tol=0.0,
            abs_tol=_number_tolerance(path),
        ):
            raise ValueError(f"numeric semantic drift at {'.'.join(path)}")
        return
    if type(expected) is not type(actual):
        raise ValueError(f"semantic type drift at {'.'.join(path)}")
    if isinstance(expected, dict):
        if tuple(expected) != tuple(actual):
            raise ValueError(f"semantic field drift at {'.'.join(path)}")
        for key in expected:
            assert_semantically_equal(expected[key], actual[key], (*path, key))
        return
    if isinstance(expected, list):
        if len(expected) != len(actual):
            raise ValueError(f"semantic sequence drift at {'.'.join(path)}")
        for index, (left, right) in enumerate(zip(expected, actual, strict=True)):
            assert_semantically_equal(left, right, (*path, str(index)))
        return
    if expected != actual:
        raise ValueError(f"semantic drift at {'.'.join(path)}")


def load_protected_paths() -> tuple[tuple[str, str], ...]:
    rows: list[tuple[str, str]] = []
    for line in PROTECTED_PATHS_PATH.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) != 2 or fields[0] not in {"historical", "anchor"}:
            raise ValueError("protected path manifest has an invalid row")
        scope, path = fields
        candidate = PROJECT_ROOT / path
        if Path(path).is_absolute() or ".." in Path(path).parts or not candidate.is_file():
            raise ValueError(f"protected path is invalid: {path}")
        rows.append((scope, path))
    if rows != sorted(set(rows)):
        raise ValueError("protected path manifest must be unique and sorted")
    return tuple(rows)


def _anchor_commit(paths: Sequence[str]) -> str:
    latest_changes = {
        _git("log", "-1", "--format=%H", "--", path)
        for path in paths
        if _git("log", "-1", "--format=%H", "--", path)
    }
    if len(latest_changes) != 1:
        raise ValueError("freeze anchor files do not share one finalization commit")
    return latest_changes.pop()


def verify_protected_paths() -> str:
    rows = load_protected_paths()
    historical = [path for scope, path in rows if scope == "historical"]
    anchor = [path for scope, path in rows if scope == "anchor"]
    anchor_commit = _anchor_commit(anchor)
    for since, paths in ((PROTECTED_SINCE_COMMIT, historical), (anchor_commit, anchor)):
        completed = subprocess.run(
            ("git", "diff", "--quiet", since, "HEAD", "--", *paths),
            cwd=PROJECT_ROOT,
            check=False,
        )
        if completed.returncode != 0:
            raise ValueError(f"protected paths changed after {since}")
    return anchor_commit


def run_freeze(*, audit_only: bool = False) -> None:
    baseline = load_baseline()
    anchor_commit = verify_protected_paths()
    if audit_only:
        print(f"non-detection audit: protected anchor {anchor_commit}")
        return
    records = validate_gold_source_identities()
    current = capture_current_tasks(records)
    expected = baseline["tasks"]
    if [task["task_id"] for task in current] != baseline["task_ids"]:
        raise ValueError("current task set differs from the frozen fourteen tasks")
    assert_semantically_equal(expected, list(current), ("tasks",))
    print(
        f"non-detection freeze: {len(current)}/14 tasks unchanged; "
        f"anchor={anchor_commit}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-baseline", action="store_true")
    parser.add_argument("--audit-only", action="store_true")
    args = parser.parse_args(argv)
    if args.capture_baseline and args.audit_only:
        parser.error("capture and audit modes are mutually exclusive")
    if args.capture_baseline:
        record = build_baseline()
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"non-detection baseline: {BASELINE_PATH}")
        return 0
    run_freeze(audit_only=args.audit_only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
