"""Validate source-bound development gold and release task results."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from tools.manual_annotation.model import (
    BASELINE_SCHEMA,
    EVALUATION_ROLE_CONTRACT,
    AnnotationError,
    canonical_record_sha256,
    evaluation_task_role,
)

from .cohort_count import validate_cohort_counts
from .file_identity import sha256_file
from .gold_geometry import (
    GOLD_ACCEPTANCE_CONTRACT,
    validate_approved_geometry,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEVELOPMENT_GOLD_COHORT_PATH = (
    Path(__file__).with_name("cohorts") / "development_gold.jsonl"
)
DEVELOPMENT_GOLD_COHORT_SCHEMA = "x5crop_development_gold_cohort_v1"
DEVELOPMENT_GOLD_COMPLETION_SCOPE = (
    "all_current_development_user_confirmed_tasks_exactly_once"
)
CONFIRMED_GEOMETRY_KEYS = frozenset(
    {
        "baseline_schema",
        "sample_id",
        "status",
        "authority",
        "confirmation_scope",
        "accuracy_scope",
        "confirmed_at_utc",
        "proposal_snapshot_sha256",
        "source_relative_path",
        "source_sha256",
        "format_id",
        "count",
        "coordinate_system",
        "strip_orientation",
        "shared_edges",
        "boundary_pool",
        "slots",
        "adjacencies",
        "evaluation_role",
        "frames",
        "confirmed_review_artifact",
        "confirmed_review_artifact_sha256",
    }
)


def validate_gold_evaluation_role(record: dict[str, object]) -> None:
    """Reject a cohort role that disagrees with its frozen human evidence."""
    sample_id = str(record.get("sample_id", ""))
    geometry = record.get("confirmed_geometry")
    if not isinstance(geometry, dict):
        raise ValueError(f"gold evaluation role is invalid: {sample_id}")
    task = {
        "task_id": sample_id,
        "sample_id": sample_id,
        "count": geometry.get("count"),
        "slots": geometry.get("slots"),
        "adjacencies": geometry.get("adjacencies"),
    }
    coordinate_system = geometry.get("coordinate_system")
    if not isinstance(coordinate_system, dict):
        raise ValueError(f"gold evaluation role is invalid: {sample_id}")
    try:
        derived = evaluation_task_role(
            format_id=str(geometry["format_id"]),
            strip_axis_display=str(geometry["strip_orientation"]),
            source_canonical_extent=coordinate_system["canonical_extent"],
            orientation_mapping=coordinate_system["orientation_mapping"],
            shared_edges=geometry["shared_edges"],
            boundary_pool=geometry["boundary_pool"],
            task=task,
        )
    except (AnnotationError, KeyError, TypeError, ValueError) as error:
        raise ValueError(f"gold evaluation role is invalid: {sample_id}") from error
    expected = {
        "contract": EVALUATION_ROLE_CONTRACT,
        "cohort_role": derived["cohort_role"],
        "reasons": derived["reasons"],
    }
    if (
        geometry.get("evaluation_role") != expected
        or record.get("cohort_role") != derived["cohort_role"]
    ):
        raise ValueError(f"gold evaluation role is invalid: {sample_id}")


def _physical_frames_by_boundary_pair(
    record: dict[str, object],
) -> dict[tuple[str, str], tuple[str, object]]:
    """Index one task's real Frames by the source-level boundary identities."""

    geometry = record["confirmed_geometry"]
    slots = geometry["slots"]
    frames = geometry["frames"]
    slots_by_ordinal = {int(slot["ordinal"]): slot for slot in slots}
    indexed: dict[tuple[str, str], tuple[str, object]] = {}
    for frame in frames:
        ordinal = int(frame["frame_index"])
        slot = slots_by_ordinal[ordinal]
        reference = slot["reference_geometry"]
        if reference.get("kind") != "boundary_pair":
            raise ValueError(
                f"count-variant Frame identity is invalid: {record['sample_id']}"
            )
        identity = (
            str(reference["start_boundary_id"]),
            str(reference["end_boundary_id"]),
        )
        value = (
            str(slot["slot_kind"]),
            frame["polygon_source_pixel_center_coordinates"],
        )
        if identity in indexed:
            raise ValueError(
                f"count-variant Frame identity is invalid: {record['sample_id']}"
            )
        indexed[identity] = value
    return indexed


def validate_count_variant_references(
    records: Iterable[dict[str, object]],
) -> None:
    """Require same-source count tasks to share one physical reference."""

    by_source: dict[str, list[dict[str, object]]] = {}
    for record in records:
        by_source.setdefault(str(record["source_sha256"]), []).append(record)
    for members in by_source.values():
        if len(members) < 2:
            continue
        reference_geometry = members[0]["confirmed_geometry"]
        reference_shared = reference_geometry["shared_edges"]
        reference_pool = reference_geometry["boundary_pool"]
        frames_by_task = {
            str(record["sample_id"]): _physical_frames_by_boundary_pair(record)
            for record in members
        }
        for record in members[1:]:
            geometry = record["confirmed_geometry"]
            if (
                geometry["shared_edges"] != reference_shared
                or geometry["boundary_pool"] != reference_pool
            ):
                raise ValueError(
                    "count-variant source reference differs: "
                    f"{members[0]['sample_id']}/{record['sample_id']}"
                )
        for left_index, left in enumerate(members):
            left_frames = frames_by_task[str(left["sample_id"])]
            for right in members[left_index + 1 :]:
                right_frames = frames_by_task[str(right["sample_id"])]
                shared = set(left_frames) & set(right_frames)
                if not shared or any(
                    left_frames[identity] != right_frames[identity]
                    for identity in shared
                ):
                    raise ValueError(
                        "count-variant shared Frame reference differs: "
                        f"{left['sample_id']}/{right['sample_id']}"
                    )


def validate_gold_source_identities() -> tuple[dict[str, object], ...]:
    validate_cohort_counts()
    records = tuple(
        json.loads(line)
        for line in DEVELOPMENT_GOLD_COHORT_PATH.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    )
    if not records:
        raise ValueError(
            "gold accuracy calibration is incomplete: no current user-confirmed sources"
        )
    project_root = PROJECT_ROOT.resolve()
    sample_ids: set[str] = set()
    for record in records:
        expected_keys = {
            "cohort_schema",
            "completion_scope",
            "sample_id",
            "source_relative_path",
            "source_sha256",
            "format_id",
            "count",
            "validation_role",
            "cohort_role",
            "acceptance_contract",
            "acceptance_baseline_schema",
            "geometry_digest",
            "confirmed_geometry",
        }
        sample_id = str(record.get("sample_id", ""))
        relative = Path(str(record.get("source_relative_path", "")))
        source = (PROJECT_ROOT / relative).resolve()
        expected_sha = str(record.get("source_sha256", "")).lower()
        count = record.get("count")
        if (
            set(record) != expected_keys
            or record.get("cohort_schema") != DEVELOPMENT_GOLD_COHORT_SCHEMA
            or record.get("completion_scope")
            != DEVELOPMENT_GOLD_COMPLETION_SCOPE
            or not sample_id
            or sample_id in sample_ids
            or record.get("validation_role") != "development_gold"
            or record.get("cohort_role") not in {"nominal", "challenge"}
            or record.get("acceptance_contract")
            != GOLD_ACCEPTANCE_CONTRACT
            or not isinstance(count, int)
            or isinstance(count, bool)
            or count <= 0
            or relative.is_absolute()
            or not source.is_relative_to(project_root)
            or not source.is_file()
            or len(expected_sha) != 64
            or sha256_file(source) != expected_sha
        ):
            raise ValueError(f"gold source identity is invalid: {sample_id or relative}")
        geometry = record.get("confirmed_geometry")
        coordinate_system = (
            geometry.get("coordinate_system")
            if isinstance(geometry, dict)
            else None
        )
        if (
            not isinstance(geometry, dict)
            or set(geometry) != CONFIRMED_GEOMETRY_KEYS
            or geometry.get("baseline_schema") != BASELINE_SCHEMA
            or geometry.get("status") != "user_confirmed"
            or geometry.get("sample_id") != sample_id
            or geometry.get("source_relative_path") != relative.as_posix()
            or geometry.get("source_sha256") != expected_sha
            or geometry.get("format_id") != record.get("format_id")
            or geometry.get("count") != count
            or geometry.get("accuracy_scope")
            != "slots_with_boundary_pair_reference_geometry"
            or record.get("acceptance_baseline_schema")
            != BASELINE_SCHEMA
            or canonical_record_sha256(geometry)
            != record.get("geometry_digest")
            or not isinstance(geometry.get("slots"), list)
            or len(geometry["slots"]) != count
            or not isinstance(geometry.get("frames"), list)
            or not isinstance(coordinate_system, dict)
            or set(coordinate_system) != {
                "origin",
                "x_direction",
                "y_direction",
                "continuous_coordinates",
                "canonical_extent",
                "orientation_mapping",
            }
        ):
            raise ValueError(f"gold geometry is invalid: {sample_id}")
        validate_gold_evaluation_role(record)
        sample_ids.add(sample_id)
    validate_count_variant_references(records)
    return records


def validate_release_gold_task_result(
    record: dict[str, object],
    report: dict[str, object],
) -> str:
    """Enforce the release-only gold decision and approved geometry gate."""

    status = str(report["decision"]["status"])
    role = str(record["cohort_role"])
    if role == "nominal" and status != "approved_auto":
        raise ValueError(f"{record['sample_id']} nominal task is {status}")
    if role == "challenge" and status not in {
        "approved_auto",
        "needs_review",
    }:
        raise ValueError(f"{record['sample_id']} challenge task is {status}")
    if status == "approved_auto":
        validate_approved_geometry(record, report)
    return status
