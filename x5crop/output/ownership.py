from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from ..app_info import RUN_MANIFEST_JSONL_NAME
from .safe_tree import InventoryEntry, assert_safe_root, inventory_tree


V5_RUN_MANIFEST_SCHEMA = "x5crop_run_manifest_v5"
V5_OUTPUT_OWNER = "x5_crop_v5"


class OutputOwnershipError(RuntimeError):
    pass


def output_role(relative: Path) -> str:
    value = relative.as_posix()
    if value == "x5_crop_report.jsonl":
        return "report"
    if value == "x5_crop_summary.csv":
        return "summary"
    if value.startswith("needs_review/"):
        return "needs_review"
    if value.startswith("_debug_analysis/"):
        return "debug_analysis"
    if value.startswith("_detection_snapshot/") and value.endswith(
        "_detection_snapshot.json.gz"
    ):
        return "detection_snapshot"
    if value.lower().endswith((".tif", ".tiff")):
        return "official_tiff"
    raise OutputOwnershipError(f"Unknown V5 output role: {value}")


def inventory_for_output(root: Path) -> tuple[InventoryEntry, ...]:
    return inventory_tree(
        root,
        manifest_name=RUN_MANIFEST_JSONL_NAME,
        role_for_file=output_role,
    )


@dataclass(frozen=True)
class OwnedOutput:
    run_id: str
    terminal_records: tuple[dict[str, Any], ...]
    inventory: tuple[InventoryEntry, ...]


def write_owned_output_manifest(
    root: Path,
    *,
    run_id: str,
    run_record: dict[str, Any],
    terminal_records: tuple[dict[str, Any], ...],
) -> Path:
    if not run_id or not terminal_records:
        raise ValueError("V5 manifest requires a run and source terminals")
    inventory = inventory_for_output(root)
    header = {
        "schema": V5_RUN_MANIFEST_SCHEMA,
        "owner": V5_OUTPUT_OWNER,
        "record_type": "run",
        "run_id": run_id,
        **run_record,
    }
    terminals = tuple(
        {
            "schema": V5_RUN_MANIFEST_SCHEMA,
            "owner": V5_OUTPUT_OWNER,
            "record_type": "source_terminal",
            "run_id": run_id,
            **record,
        }
        for record in terminal_records
    )
    footer = {
        "schema": V5_RUN_MANIFEST_SCHEMA,
        "owner": V5_OUTPUT_OWNER,
        "record_type": "inventory",
        "run_id": run_id,
        "inventory": [item.as_record() for item in inventory],
    }
    path = root / RUN_MANIFEST_JSONL_NAME
    with path.open("x", encoding="utf-8") as stream:
        for record in (header, *terminals, footer):
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    read_owned_output(root)
    return path


def read_owned_output(root: Path) -> OwnedOutput:
    assert_safe_root(root)
    manifest = root / RUN_MANIFEST_JSONL_NAME
    try:
        lines = manifest.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise OutputOwnershipError(
            f"Output ownership manifest is unavailable: {manifest}"
        ) from exc
    try:
        records = tuple(json.loads(line) for line in lines if line.strip())
    except (TypeError, json.JSONDecodeError) as exc:
        raise OutputOwnershipError("Output ownership manifest is invalid JSONL") from exc
    if len(records) < 3:
        raise OutputOwnershipError("Output ownership manifest is incomplete")
    header, *middle, footer = records
    run_id = header.get("run_id")
    if (
        header.get("schema") != V5_RUN_MANIFEST_SCHEMA
        or header.get("owner") != V5_OUTPUT_OWNER
        or header.get("record_type") != "run"
        or not isinstance(run_id, str)
        or not run_id
        or footer.get("schema") != V5_RUN_MANIFEST_SCHEMA
        or footer.get("owner") != V5_OUTPUT_OWNER
        or footer.get("record_type") != "inventory"
        or footer.get("run_id") != run_id
        or any(
            item.get("schema") != V5_RUN_MANIFEST_SCHEMA
            or item.get("owner") != V5_OUTPUT_OWNER
            or item.get("record_type") != "source_terminal"
            or item.get("run_id") != run_id
            for item in middle
        )
    ):
        raise OutputOwnershipError("Output ownership manifest is not current V5")
    try:
        expected = tuple(
            InventoryEntry(
                relative_path=str(item["relative_path"]),
                kind=str(item["kind"]),
                role=(None if item.get("role") is None else str(item["role"])),
                size=(None if item.get("size") is None else int(item["size"])),
                mtime_ns=(
                    None if item.get("mtime_ns") is None else int(item["mtime_ns"])
                ),
            )
            for item in footer.get("inventory", ())
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise OutputOwnershipError("Output inventory record is invalid") from exc
    actual = inventory_for_output(root)
    if actual != expected:
        raise OutputOwnershipError("Output directory differs from its V5 inventory")
    return OwnedOutput(run_id, tuple(middle), actual)
