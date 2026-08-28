"""Authority reconciliation and atomic local state for the annotator."""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
from typing import Any, Iterable

from .imaging import (
    MAX_TILE_RENDER_DIMENSION,
    MAX_TILE_SOURCE_DIMENSION,
    MAX_TILE_SOURCE_PIXELS,
    SourceRaster,
    orientation_record,
    render_review_artifact,
    sha256_file,
)
from .model import (
    ANNOTATION_SCHEMA,
    CONFIRMED_IMPORT_ORIGIN,
    COORDINATE_SYSTEM,
    AnnotationError,
    canonical_record_sha256,
    confirmed_rows_jsonl,
    display_to_raw_point,
    geometry_snapshot,
    record_for_client,
    referenced_boundary_ids,
    utc_now,
    validate_annotation_record,
    apply_client_geometry,
)
from .proposal import (
    apply_review_context_metadata,
    apply_review_context_slot_semantics,
    canonicalize_source_reference_mappings,
    import_red_markup_draft,
    propose_record,
)


MANIFEST_SCHEMA = "x5crop_manual_review_manifest_v3"
COHORT_RELATIVE_PATH = Path("tools/regression/cohorts/diagnostic_unreviewed.jsonl")
MANIFEST_RELATIVE_PATH = Path("Test/manual_review/manifest.jsonl")
LEGACY_BASELINE_RELATIVE_PATH = Path(
    "Test/manual_review/user_confirmed_golden_baseline.jsonl"
)
DEFAULT_STATE_RELATIVE_PATH = Path("Test/manual_review/source_annotations")
REVIEW_CONTEXT_RELATIVE_PATH = Path("Test/manual_review/review_context.json")
REVIEW_CONTEXT_SCHEMA = "x5crop_manual_review_context_v1"


class WorkspaceError(RuntimeError):
    """Raised when local review data violates its tracked authority."""


def _jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise WorkspaceError(f"cannot read {path}: {error}") from error
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise WorkspaceError(f"{path}:{line_number}: invalid JSON") from error
        if not isinstance(value, dict):
            raise WorkspaceError(f"{path}:{line_number}: row must be an object")
        rows.append(value)
    return rows


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    payload = (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    _atomic_write(path, payload)


def _line_from_legacy(
    seed: dict[str, Any],
    *,
    horizontal: bool,
    family: str,
    width: int,
    height: int,
) -> list[list[float]]:
    slope = float(seed["slope"])
    intercept = float(seed["intercept"])
    if horizontal:
        if family == "shared":
            return [[0.0, intercept], [float(width - 1), slope * (width - 1) + intercept]]
        return [[intercept, 0.0], [slope * (height - 1) + intercept, float(height - 1)]]
    if family == "shared":
        return [[intercept, 0.0], [slope * (height - 1) + intercept, float(height - 1)]]
    return [[0.0, intercept], [float(width - 1), slope * (width - 1) + intercept]]


class ReviewWorkspace:
    def __init__(
        self,
        repository_root: Path,
        *,
        state_root: Path | None = None,
    ):
        self.repository_root = repository_root.resolve()
        self.state_root = (
            state_root.resolve()
            if state_root is not None
            else (self.repository_root / DEFAULT_STATE_RELATIVE_PATH).resolve()
        )
        expected_state_parent = (self.repository_root / "Test/manual_review").resolve()
        if self.state_root != expected_state_parent and expected_state_parent not in self.state_root.parents:
            raise WorkspaceError("annotation state must remain inside Test/manual_review")
        self.records_root = self.state_root / "records"
        self.previews_root = self.state_root / "previews"
        self.artifacts_root = self.state_root / "review_artifacts"
        self.confirmed_rows_path = self.state_root / "confirmed_source_geometry.jsonl"
        self._lock = threading.RLock()
        self.manifest_rows = self._load_and_reconcile_authority()
        self.groups = self._group_rows(self.manifest_rows)
        self.sample_to_sha = {
            row["sample_id"]: row["source_sha256"] for row in self.manifest_rows
        }
        self.review_context = self._load_review_context()

    def resolve_repository_path(self, relative: str) -> Path:
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise WorkspaceError("repository path must be a safe relative path")
        current = self.repository_root
        for part in candidate.parts:
            current = current / part
            if current.is_symlink():
                raise WorkspaceError(f"symlink paths are not accepted: {relative}")
        resolved = current.resolve()
        if resolved != self.repository_root and self.repository_root not in resolved.parents:
            raise WorkspaceError(f"path leaves repository: {relative}")
        return resolved

    def _load_and_reconcile_authority(self) -> list[dict[str, Any]]:
        manifest_path = self.resolve_repository_path(MANIFEST_RELATIVE_PATH.as_posix())
        cohort_path = self.resolve_repository_path(COHORT_RELATIVE_PATH.as_posix())
        manifest = _jsonl(manifest_path)
        cohort = _jsonl(cohort_path)
        required = (
            "sample_id",
            "format_id",
            "count",
            "source_relative_path",
            "source_sha256",
        )
        manifest_by_id: dict[str, dict[str, Any]] = {}
        for row in manifest:
            if row.get("manifest_schema") != MANIFEST_SCHEMA:
                raise WorkspaceError("manual-review manifest schema is not current")
            sample_id = row.get("sample_id")
            if not isinstance(sample_id, str) or sample_id in manifest_by_id:
                raise WorkspaceError("manual-review manifest sample identities are invalid")
            manifest_by_id[sample_id] = row
        cohort_by_id = {row.get("sample_id"): row for row in cohort}
        if set(manifest_by_id) != set(cohort_by_id):
            raise WorkspaceError("manual-review manifest does not cover the tracked cohort")
        for sample_id, row in manifest_by_id.items():
            tracked = cohort_by_id[sample_id]
            if any(row.get(key) != tracked.get(key) for key in required):
                raise WorkspaceError(f"{sample_id}: local manifest disagrees with tracked authority")
            if (
                not isinstance(row.get("count"), int)
                or isinstance(row.get("count"), bool)
                or int(row["count"]) <= 0
            ):
                raise WorkspaceError(f"{sample_id}: explicit count is invalid")
            self.resolve_repository_path(str(row["source_relative_path"]))
            self.resolve_repository_path(str(row["calibration_copy_relative_path"]))
        return sorted(manifest, key=lambda row: int(row["sort_index"]))

    @staticmethod
    def _group_rows(rows: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[str(row["source_sha256"])].append(row)
        result: dict[str, list[dict[str, Any]]] = {}
        for sha, members in grouped.items():
            if len({row["format_id"] for row in members}) != 1:
                raise WorkspaceError(f"{sha}: one source SHA has multiple formats")
            if len({row["calibration_canonical_sample_id"] for row in members}) != 1:
                raise WorkspaceError(f"{sha}: canonical annotation identity is ambiguous")
            if len({row["calibration_copy_relative_path"] for row in members}) != 1:
                raise WorkspaceError(f"{sha}: one source SHA has multiple work copies")
            result[sha] = sorted(members, key=lambda row: int(row["sort_index"]))
        return result

    def _load_review_context(self) -> dict[str, Any]:
        path = self.resolve_repository_path(REVIEW_CONTEXT_RELATIVE_PATH.as_posix())
        if not path.is_file():
            return {
                "review_context_schema": REVIEW_CONTEXT_SCHEMA,
                "default_pending_markup_state": "unknown",
                "default_film_polarity": "unknown",
                "positive_sample_ids": [],
                "unmarked_sample_ids": [],
                "samples": {},
            }
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise WorkspaceError(f"cannot read {path}") from error
        expected_keys = {
            "review_context_schema",
            "default_pending_markup_state",
            "default_film_polarity",
            "positive_sample_ids",
            "unmarked_sample_ids",
            "samples",
        }
        if not isinstance(value, dict) or set(value) != expected_keys:
            raise WorkspaceError("manual-review context is malformed")
        if value["review_context_schema"] != REVIEW_CONTEXT_SCHEMA:
            raise WorkspaceError("manual-review context schema is not current")
        if value["default_pending_markup_state"] not in {
            "unknown",
            "user_declared_marked",
        }:
            raise WorkspaceError("manual-review default markup state is invalid")
        if value["default_film_polarity"] not in {"positive", "negative", "unknown"}:
            raise WorkspaceError("manual-review default film polarity is invalid")
        known = set(self.sample_to_sha)
        for key in ("positive_sample_ids", "unmarked_sample_ids"):
            identities = value[key]
            if (
                not isinstance(identities, list)
                or len(set(identities)) != len(identities)
                or not set(identities).issubset(known)
            ):
                raise WorkspaceError(f"manual-review {key} is invalid")
        samples = value["samples"]
        if not isinstance(samples, dict) or not set(samples).issubset(known):
            raise WorkspaceError("manual-review sample context identities are invalid")
        if any(not isinstance(context, dict) for context in samples.values()):
            raise WorkspaceError("manual-review sample context must be an object")
        unmarked = set(value["unmarked_sample_ids"])
        for members in self.groups.values():
            states = {row["sample_id"] in unmarked for row in members}
            if len(states) > 1:
                raise WorkspaceError("one source SHA cannot mix marked and unmarked tasks")
        return value

    def _source_review_context(self, members: list[dict[str, Any]]) -> dict[str, Any]:
        positives = set(self.review_context["positive_sample_ids"])
        default_polarity = str(self.review_context["default_film_polarity"])
        polarities = {
            "positive" if row["sample_id"] in positives else default_polarity
            for row in members
        }
        if len(polarities) != 1:
            raise WorkspaceError("one source SHA cannot have multiple film polarities")
        samples = self.review_context["samples"]
        return {
            "authority": "user_supplied_calibration_metadata_only",
            "film_polarity": polarities.pop(),
            "tasks": {
                row["sample_id"]: deepcopy(samples.get(row["sample_id"], {}))
                for row in members
            },
        }

    def _declared_markup_state(self, members: list[dict[str, Any]]) -> str:
        unmarked = set(self.review_context["unmarked_sample_ids"])
        if all(row["sample_id"] in unmarked for row in members):
            return "user_declared_unmarked"
        return str(self.review_context["default_pending_markup_state"])

    def record_path(self, sha: str) -> Path:
        if len(sha) != 64 or any(character not in "0123456789abcdef" for character in sha):
            raise WorkspaceError("source SHA identity is invalid")
        return self.records_root / f"{sha}.json"

    def preview_path(self, sha: str) -> Path:
        return self.previews_root / f"{sha}.jpg"

    def resolve_identity(self, identity: str) -> str:
        if identity in self.groups:
            return identity
        if identity in self.sample_to_sha:
            return self.sample_to_sha[identity]
        raise WorkspaceError(f"unknown sample/source identity: {identity}")

    def _canonical_row(self, members: list[dict[str, Any]]) -> dict[str, Any]:
        canonical = str(members[0]["calibration_canonical_sample_id"])
        return next((row for row in members if row["sample_id"] == canonical), members[0])

    def _read_record(self, identity: str) -> dict[str, Any]:
        sha = self.resolve_identity(identity)
        path = self.record_path(sha)
        if not path.is_file():
            raise WorkspaceError(f"annotation proposal is not prepared: {identity}")
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise WorkspaceError(f"cannot read annotation record {path}") from error
        if not isinstance(record, dict):
            raise WorkspaceError("annotation record must be an object")
        source = record.get("source")
        if not isinstance(source, dict) or source.get("sha256") != sha:
            raise WorkspaceError("annotation filename and source SHA disagree")
        return record

    def load_record(self, identity: str, *, client: bool = False) -> dict[str, Any]:
        record = self._read_record(identity)
        try:
            validate_annotation_record(record)
        except AnnotationError as error:
            raise WorkspaceError(f"annotation record is invalid: {error}") from error
        return record_for_client(record) if client else record

    def _save_record(self, record: dict[str, Any]) -> None:
        validate_annotation_record(record)
        _atomic_json(self.record_path(record["source"]["sha256"]), record)

    def _verify_source(self, row: dict[str, Any]) -> Path:
        source = self.resolve_repository_path(str(row["source_relative_path"]))
        if not source.is_file():
            raise WorkspaceError(f"source TIFF is missing: {row['source_relative_path']}")
        actual = sha256_file(source)
        if actual != row["source_sha256"]:
            raise WorkspaceError(f"{row['sample_id']}: source TIFF SHA-256 mismatch")
        return source

    def _legacy_baselines(self) -> dict[str, dict[str, Any]]:
        path = self.resolve_repository_path(LEGACY_BASELINE_RELATIVE_PATH.as_posix())
        if not path.is_file():
            return {}
        return {str(row["source_sha256"]): row for row in _jsonl(path)}

    def _import_legacy_record(
        self,
        *,
        members: list[dict[str, Any]],
        baseline: dict[str, Any],
        raster: SourceRaster,
    ) -> dict[str, Any]:
        canonical = self._canonical_row(members)
        raw_width, raw_height = raster.raw_extent
        display_width, display_height = raster.canonical_extent
        horizontal = baseline["strip_orientation"] == "horizontal"
        record: dict[str, Any] = {
            "annotation_schema": ANNOTATION_SCHEMA,
            "revision": 1,
            "state": "user_confirmed",
            "source": {
                "canonical_sample_id": canonical["calibration_canonical_sample_id"],
                "relative_path": canonical["source_relative_path"],
                "sha256": canonical["source_sha256"],
                "raw_extent": {"width": raw_width, "height": raw_height},
                "canonical_extent": {"width": display_width, "height": display_height},
                "orientation_mapping": orientation_record(raster.mapping),
            },
            "format_id": canonical["format_id"],
            "strip_axis_display": baseline["strip_orientation"],
            "coordinate_system": COORDINATE_SYSTEM,
            "origin": CONFIRMED_IMPORT_ORIGIN,
            "shared_edges": [],
            "boundary_pool": [],
            "tasks": [],
            "diagnostics": {
                "legacy_baseline_schema": baseline["baseline_schema"],
                "legacy_baseline_sha256": canonical_record_sha256(baseline),
                "legacy_algorithm_revision": baseline["algorithm_revision"],
                "authority": "preserved_existing_user_confirmation",
                "review_context": self._source_review_context(members),
            },
            "reviewed_task_ids": [row["sample_id"] for row in members],
            "confirmation": {
                "confirmed_at_utc": baseline["confirmed_at_utc"],
                "proposal_snapshot_sha256": baseline["proposal_snapshot_sha256"],
                "review_artifact_relative_path": baseline["confirmed_review_jpg"],
                "review_artifact_sha256": baseline["confirmed_review_jpg_sha256"],
                "checklist": {
                    "shared_edges": True,
                    "task_boundaries": True,
                    "native_pixel_checks": True,
                    "safe_without_bleed": True,
                },
            },
        }
        for index, seed in enumerate(baseline["shared_edges"], start=1):
            points = _line_from_legacy(
                seed,
                horizontal=horizontal,
                family="shared",
                width=display_width,
                height=display_height,
            )
            record["shared_edges"].append(
                {
                    "line_id": f"E{index}",
                    "role": "short_low" if index == 1 else "short_high",
                    "points_raw": [display_to_raw_point(record, point) for point in points],
                    "origin": CONFIRMED_IMPORT_ORIGIN,
                    "review_basis": "explicit_prior_user_confirmation",
                }
            )
        boundary_ids: list[str] = []
        for index, seed in enumerate(baseline["frame_boundaries"], start=1):
            line_id = f"B{index:03d}"
            points = _line_from_legacy(
                seed,
                horizontal=horizontal,
                family="boundary",
                width=display_width,
                height=display_height,
            )
            record["boundary_pool"].append(
                {
                    "line_id": line_id,
                    "role": "long_boundary",
                    "points_raw": [display_to_raw_point(record, point) for point in points],
                    "origin": CONFIRMED_IMPORT_ORIGIN,
                    "review_basis": "explicit_prior_user_confirmation",
                }
            )
            boundary_ids.append(line_id)
        if len(members) != 1:
            raise WorkspaceError("legacy confirmed source unexpectedly has aliases")
        member = members[0]
        record["tasks"].append(
            {
                "task_id": member["sample_id"],
                "sample_id": member["sample_id"],
                "source_relative_path": member["source_relative_path"],
                "count": member["count"],
                "slots": [
                    {
                        "ordinal": index + 1,
                        "slot_kind": "image",
                        "reference_geometry": {
                            "kind": "boundary_pair",
                            "start_boundary_id": boundary_ids[index * 2],
                            "end_boundary_id": boundary_ids[index * 2 + 1],
                        },
                    }
                    for index in range(int(member["count"]))
                ],
                "adjacencies": [
                    {
                        "left_ordinal": index,
                        "right_ordinal": index + 1,
                        "kind": "separator",
                    }
                    for index in range(1, int(member["count"]))
                ],
            }
        )
        validate_annotation_record(record)
        return record

    def prepare(
        self,
        *,
        identities: Iterable[str] | None = None,
        force_machine: bool = False,
        progress: Any | None = None,
    ) -> dict[str, int]:
        requested = (
            {self.resolve_identity(identity) for identity in identities}
            if identities is not None
            else set(self.groups)
        )
        legacy = self._legacy_baselines()
        counts = {
            "prepared": 0,
            "existing": 0,
            "confirmed_imported": 0,
            "red_drafts": 0,
            "source_references_normalized": 0,
        }
        for offset, sha in enumerate(
            sorted(requested, key=lambda value: int(self.groups[value][0]["sort_index"])),
            start=1,
        ):
            members = self.groups[sha]
            existing_path = self.record_path(sha)
            if existing_path.is_file():
                existing = self._read_record(sha)
                if existing["state"] != "machine_proposal" or not force_machine:
                    if existing["state"] != "user_confirmed":
                        try:
                            normalized = canonicalize_source_reference_mappings(existing)
                        except (KeyError, TypeError, ValueError) as error:
                            raise WorkspaceError(
                                f"{members[0]['sample_id']}: cannot normalize source reference"
                            ) from error
                        if normalized != existing:
                            normalized["revision"] = int(existing["revision"]) + 1
                            normalized["reviewed_task_ids"] = []
                            validate_annotation_record(normalized)
                            self._save_record(normalized)
                            existing = normalized
                            counts["source_references_normalized"] += 1
                    try:
                        validate_annotation_record(existing)
                    except AnnotationError as error:
                        raise WorkspaceError(
                            f"annotation record is invalid: {error}"
                        ) from error
                    preview_path = self.preview_path(sha)
                    if not preview_path.is_file():
                        raise WorkspaceError(
                            f"{members[0]['sample_id']}: prepared record has no preview"
                        )
                    preview_sha = sha256_file(preview_path)
                    stored_preview_sha = existing["diagnostics"].get(
                        "preview_jpeg_sha256"
                    )
                    if stored_preview_sha is None:
                        existing["diagnostics"]["preview_jpeg_sha256"] = preview_sha
                        existing["diagnostics"]["preview_relative_path"] = (
                            preview_path.relative_to(self.repository_root).as_posix()
                        )
                        self._save_record(existing)
                    elif stored_preview_sha != preview_sha:
                        raise WorkspaceError(
                            f"{members[0]['sample_id']}: prepared preview SHA-256 mismatch"
                        )
                    counts["existing"] += 1
                    if progress is not None:
                        progress(offset, len(requested), members, "existing")
                    continue
            canonical = self._canonical_row(members)
            source = self._verify_source(canonical)
            with SourceRaster(source) as raster:
                if sha in legacy:
                    record = self._import_legacy_record(
                        members=members,
                        baseline=legacy[sha],
                        raster=raster,
                    )
                    counts["confirmed_imported"] += 1
                else:
                    record, _ = propose_record(
                        raster=raster,
                        source_relative_path=canonical["source_relative_path"],
                        source_sha256=sha,
                        canonical_sample_id=canonical["calibration_canonical_sample_id"],
                        format_id=canonical["format_id"],
                        tasks=members,
                        review_context=self._source_review_context(members),
                    )
                    copy_path = self.resolve_repository_path(
                        str(canonical["calibration_copy_relative_path"])
                    )
                    if not copy_path.is_file():
                        raise WorkspaceError(
                            f"calibration work copy is missing: {canonical['calibration_copy_relative_path']}"
                        )
                    copy_changed = sha256_file(copy_path) != sha
                    declared_markup_state = self._declared_markup_state(members)
                    record["diagnostics"]["declared_markup_state"] = (
                        declared_markup_state
                    )
                    if declared_markup_state == "user_declared_marked" and not copy_changed:
                        raise WorkspaceError(
                            f"{canonical['sample_id']}: user-declared marked copy has no raster/file change"
                        )
                    if copy_changed and declared_markup_state != "user_declared_unmarked":
                        try:
                            record = import_red_markup_draft(
                                record,
                                source_raster=raster,
                                marked_path=copy_path,
                            )
                        except (ValueError, AnnotationError) as error:
                            raise WorkspaceError(
                                f"{canonical['sample_id']}: modified work copy cannot be safely imported: {error}"
                            ) from error
                        counts["red_drafts"] += 1
                    else:
                        record = apply_review_context_slot_semantics(record)
                preview = raster.preview_jpeg(
                    levels=record["diagnostics"].get("render_levels")
                )
            record["diagnostics"]["preview_jpeg_sha256"] = hashlib.sha256(
                preview
            ).hexdigest()
            record["diagnostics"]["preview_relative_path"] = self.preview_path(
                sha
            ).relative_to(self.repository_root).as_posix()
            _atomic_write(self.preview_path(sha), preview)
            self._save_record(record)
            counts["prepared"] += 1
            if progress is not None:
                progress(offset, len(requested), members, record["state"])
        self._refresh_confirmed_rows()
        return counts

    def _refresh_confirmed_rows(self) -> None:
        confirmed: list[dict[str, Any]] = []
        if self.records_root.is_dir():
            for path in sorted(self.records_root.glob("*.json")):
                record = self.load_record(path.stem)
                if record["state"] == "user_confirmed":
                    confirmed.append(record)
        payload = confirmed_rows_jsonl(confirmed).encode("utf-8") if confirmed else b""
        _atomic_write(self.confirmed_rows_path, payload)

    def index(self) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        states: dict[str, int] = defaultdict(int)
        for sha, members in sorted(
            self.groups.items(), key=lambda item: int(item[1][0]["sort_index"])
        ):
            path = self.record_path(sha)
            if path.is_file():
                record = self.load_record(sha)
                state = str(record["state"])
                reviewed = list(record["reviewed_task_ids"])
            else:
                state = "not_prepared"
                reviewed = []
            states[state] += 1
            canonical = self._canonical_row(members)
            items.append(
                {
                    "source_sha256": sha,
                    "canonical_sample_id": canonical["calibration_canonical_sample_id"],
                    "format_id": canonical["format_id"],
                    "state": state,
                    "prepared": path.is_file(),
                    "reviewed_task_ids": reviewed,
                    "tasks": [
                        {"sample_id": row["sample_id"], "count": row["count"]}
                        for row in members
                    ],
                }
            )
        return {
            "index_schema": "x5crop_source_annotation_index_v3",
            "tile_max_render_dimension": MAX_TILE_RENDER_DIMENSION,
            "tile_max_source_dimension": MAX_TILE_SOURCE_DIMENSION,
            "tile_max_source_pixels": MAX_TILE_SOURCE_PIXELS,
            "total_unique_sources": len(items),
            "states": dict(sorted(states.items())),
            "items": items,
        }

    def update_geometry(self, identity: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            current = self.load_record(identity)
            try:
                updated = apply_client_geometry(current, payload)
            except AnnotationError as error:
                raise WorkspaceError(str(error)) from error
            self._save_record(updated)
            return record_for_client(updated)

    def reconcile_review_context(
        self,
        *,
        identities: Iterable[str] | None,
        include_confirmed: bool = False,
    ) -> dict[str, int]:
        """Apply explicit nonstructural review metadata without changing geometry."""
        if identities is None:
            raise WorkspaceError("review-context reconciliation requires sample identities")
        requested = {self.resolve_identity(identity) for identity in identities}
        if not requested:
            raise WorkspaceError("review-context reconciliation requires sample identities")
        changed_sources = 0
        changed_lines = 0
        changed_slots = 0
        changed_confirmed = False
        with self._lock:
            for sha in sorted(
                requested,
                key=lambda value: int(self.groups[value][0]["sort_index"]),
            ):
                current = self.load_record(sha)
                if current["state"] == "user_confirmed" and not include_confirmed:
                    raise WorkspaceError(
                        "confirmed review-context correction requires explicit permission"
                    )
                updated = deepcopy(current)
                updated["diagnostics"]["review_context"] = self._source_review_context(
                    self.groups[sha]
                )
                try:
                    updated = apply_review_context_metadata(updated)
                except (AnnotationError, KeyError, TypeError, ValueError) as error:
                    raise WorkspaceError(
                        f"{updated['source']['canonical_sample_id']}: cannot reconcile review context"
                    ) from error
                before = {
                    line["line_id"]: line["review_basis"]
                    for line in [*current["shared_edges"], *current["boundary_pool"]]
                }
                after = {
                    line["line_id"]: line["review_basis"]
                    for line in [*updated["shared_edges"], *updated["boundary_pool"]]
                }
                corrected = sorted(
                    line_id
                    for line_id, basis in after.items()
                    if before.get(line_id) != basis
                )
                before_slots = {
                    (task["task_id"], slot["ordinal"]): slot["slot_kind"]
                    for task in current["tasks"]
                    for slot in task["slots"]
                }
                after_slots = {
                    (task["task_id"], slot["ordinal"]): slot["slot_kind"]
                    for task in updated["tasks"]
                    for slot in task["slots"]
                }
                corrected_slots = sorted(
                    f"{task_id}#{ordinal}"
                    for (task_id, ordinal), kind in after_slots.items()
                    if before_slots.get((task_id, ordinal)) != kind
                )
                if updated == current:
                    continue
                updated["revision"] = int(current["revision"]) + 1
                updated["diagnostics"]["review_context_reconciliation"] = {
                    "authority": "explicit_user_review_context",
                    "corrected_line_ids": corrected,
                    "corrected_slots": corrected_slots,
                }
                if updated["state"] == "user_confirmed":
                    updated["confirmation"]["proposal_snapshot_sha256"] = (
                        canonical_record_sha256(geometry_snapshot(updated))
                    )
                    changed_confirmed = True
                else:
                    updated["reviewed_task_ids"] = []
                    updated["confirmation"] = None
                self._save_record(updated)
                changed_sources += 1
                changed_lines += len(corrected)
                changed_slots += len(corrected_slots)
            if changed_confirmed:
                self._refresh_confirmed_rows()
        return {
            "changed_sources": changed_sources,
            "changed_lines": changed_lines,
            "changed_slots": changed_slots,
        }

    def set_source_reviewed(
        self,
        identity: str,
        *,
        expected_revision: int,
        reviewed: bool,
    ) -> dict[str, Any]:
        with self._lock:
            current = self.load_record(identity)
            if current["state"] == "user_confirmed":
                raise WorkspaceError("confirmed annotation is immutable")
            if (
                not isinstance(expected_revision, int)
                or isinstance(expected_revision, bool)
                or expected_revision != current["revision"]
            ):
                raise WorkspaceError("annotation revision conflict")
            if not isinstance(reviewed, bool):
                raise WorkspaceError("source reference review state must be boolean")
            task_ids = {task["task_id"] for task in current["tasks"]}
            current["reviewed_task_ids"] = sorted(task_ids) if reviewed else []
            current["revision"] += 1
            self._save_record(current)
            return record_for_client(current)

    def confirm(
        self,
        identity: str,
        *,
        expected_revision: int,
    ) -> dict[str, Any]:
        required_checks = {
            "shared_edges",
            "task_boundaries",
            "native_pixel_checks",
            "safe_without_bleed",
        }
        with self._lock:
            current = self.load_record(identity)
            if current["state"] == "user_confirmed":
                raise WorkspaceError("confirmed annotation is immutable")
            if (
                not isinstance(expected_revision, int)
                or isinstance(expected_revision, bool)
                or expected_revision != current["revision"]
            ):
                raise WorkspaceError("annotation revision conflict")
            task_ids = {task["task_id"] for task in current["tasks"]}
            if set(current["reviewed_task_ids"]) != task_ids:
                raise WorkspaceError("source reference must be reviewed before confirmation")
            preview_path = self.preview_path(current["source"]["sha256"])
            if not preview_path.is_file():
                raise WorkspaceError("bounded source preview is missing")
            expected_preview_sha = current["diagnostics"].get(
                "preview_jpeg_sha256"
            )
            if (
                not isinstance(expected_preview_sha, str)
                or sha256_file(preview_path) != expected_preview_sha
            ):
                raise WorkspaceError("bounded source preview changed after preparation")
            source_sha = current["source"]["sha256"]
            self._verify_source(self._canonical_row(self.groups[source_sha]))
            used_boundary_ids = referenced_boundary_ids(current)
            current["boundary_pool"] = [
                line
                for line in current["boundary_pool"]
                if line["line_id"] in used_boundary_ids
            ]
            for line in [*current["shared_edges"], *current["boundary_pool"]]:
                if line["review_basis"] == "machine_proposal_pending_review":
                    line["review_basis"] = "user_accepted_machine_inference"
            proposal_sha = canonical_record_sha256(geometry_snapshot(current))
            artifact = render_review_artifact(preview_path.read_bytes(), current)
            artifact_sha = hashlib.sha256(artifact).hexdigest()
            artifact_name = (
                f"{current['source']['canonical_sample_id']}_"
                f"{proposal_sha[:12]}_confirmed.jpg"
            )
            artifact_path = self.artifacts_root / artifact_name
            _atomic_write(artifact_path, artifact)
            current["revision"] += 1
            current["state"] = "user_confirmed"
            current["confirmation"] = {
                "confirmed_at_utc": utc_now(),
                "proposal_snapshot_sha256": proposal_sha,
                "review_artifact_relative_path": artifact_path.relative_to(
                    self.repository_root
                ).as_posix(),
                "review_artifact_sha256": artifact_sha,
                "checklist": {key: True for key in sorted(required_checks)},
            }
            self._save_record(current)
            self._refresh_confirmed_rows()
            return record_for_client(current)
