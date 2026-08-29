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
    render_review_artifact,
    sha256_file,
)
from .machine_salience import (
    build_machine_salience_review,
    set_line_review_status,
    source_review_summary,
    validate_machine_salience_review,
)
from .model import (
    AnnotationError,
    canonical_record_sha256,
    confirmed_rows_jsonl,
    evaluation_role_summary,
    frame_state_summary,
    geometry_snapshot,
    line_basis_summary,
    record_for_client,
    referenced_boundary_ids,
    utc_now,
    validate_annotation_record,
    apply_client_geometry,
)
from .proposal import (
    apply_review_context_metadata,
    apply_review_context_slot_semantics,
    import_red_markup_draft,
    propose_record,
)
from .refinement import REFINEMENT_REVISION, refine_record


MANIFEST_SCHEMA = "x5crop_manual_review_manifest_v5"
COHORT_RELATIVE_PATH = Path("tools/regression/cohorts/diagnostic_unreviewed.jsonl")
MANIFEST_RELATIVE_PATH = Path("Test/manual_review/manifest.jsonl")
DEFAULT_STATE_RELATIVE_PATH = Path("Test/manual_review/source_annotations")
REVIEW_CONTEXT_RELATIVE_PATH = Path("Test/manual_review/review_context.json")
REVIEW_CONTEXT_SCHEMA = "x5crop_manual_review_context_v2"


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
        self.machine_salience_path = self.state_root / "machine_salience_review.json"
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
        expected_manifest_keys = {
            "manifest_schema",
            "sample_id",
            "format_id",
            "count",
            "source_relative_path",
            "source_sha256",
            "sort_index",
            "calibration_canonical_sample_id",
            "calibration_copy_relative_path",
            "source_alias_sample_ids",
        }
        for row in manifest:
            if (
                set(row) != expected_manifest_keys
                or row.get("manifest_schema") != MANIFEST_SCHEMA
            ):
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
                "shared_edge_review_basis": "unclassified",
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
            "shared_edge_review_basis",
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
        if value["shared_edge_review_basis"] not in {
            "unclassified",
            "directly_visible",
        }:
            raise WorkspaceError("manual-review shared-edge basis is invalid")
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
            "shared_edge_review_basis": self.review_context[
                "shared_edge_review_basis"
            ],
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
        sha = str(record["source"]["sha256"])
        expected_preview = self.preview_path(sha).relative_to(
            self.repository_root
        ).as_posix()
        if record["diagnostics"].get("preview_relative_path") != expected_preview:
            raise WorkspaceError("annotation preview path is not current")
        red_import = record["diagnostics"].get("red_markup_import")
        if isinstance(red_import, dict):
            canonical = self._canonical_row(self.groups[sha])
            if (
                "marked_path" in red_import
                or red_import.get("marked_relative_path")
                != canonical["calibration_copy_relative_path"]
            ):
                raise WorkspaceError("red-markup source path is not current")
        return self._record_for_client(record) if client else record

    def _load_machine_salience_review(self) -> dict[str, Any] | None:
        if not self.machine_salience_path.is_file():
            return None
        try:
            review = json.loads(self.machine_salience_path.read_text(encoding="utf-8"))
            if not isinstance(review, dict):
                raise ValueError("machine salience review must be an object")
            validate_machine_salience_review(review)
        except (OSError, json.JSONDecodeError, ValueError) as error:
            raise WorkspaceError(f"machine salience review is invalid: {error}") from error
        return review

    @staticmethod
    def _current_salience_source(
        record: dict[str, Any],
        review: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if review is None:
            return None
        source = review["sources"].get(record["source"]["sha256"])
        if (
            not isinstance(source, dict)
            or source.get("source_geometry_sha256")
            != canonical_record_sha256(geometry_snapshot(record))
        ):
            return None
        return source

    def _record_for_client(
        self,
        record: dict[str, Any],
        *,
        review: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = record_for_client(record)
        active_review = (
            review
            if review is not None
            else self._load_machine_salience_review()
        )
        source = self._current_salience_source(record, active_review)
        facts = source.get("lines", {}) if source is not None else {}
        for line in result["boundary_pool"]:
            line["machine_salience"] = deepcopy(facts.get(line["line_id"]))
        result["machine_salience_review"] = {
            "analysis_revision": (
                active_review.get("analysis_revision")
                if active_review is not None
                else None
            ),
            "review_revision": (
                active_review.get("review_revision")
                if active_review is not None
                else None
            ),
            "source_summary": source_review_summary(source),
        }
        return result

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
        counts = {
            "prepared": 0,
            "existing": 0,
            "red_drafts": 0,
        }
        for offset, sha in enumerate(
            sorted(requested, key=lambda value: int(self.groups[value][0]["sort_index"])),
            start=1,
        ):
            members = self.groups[sha]
            existing_path = self.record_path(sha)
            if existing_path.is_file():
                existing = self.load_record(sha)
                if existing["state"] != "machine_proposal" or not force_machine:
                    preview_path = self.preview_path(sha)
                    if not preview_path.is_file():
                        raise WorkspaceError(
                            f"{members[0]['sample_id']}: prepared record has no preview"
                        )
                    preview_sha = sha256_file(preview_path)
                    stored_preview_sha = existing["diagnostics"].get(
                        "preview_jpeg_sha256"
                    )
                    if stored_preview_sha != preview_sha:
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
                record["diagnostics"]["declared_markup_state"] = declared_markup_state
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
                            marked_relative_path=str(
                                canonical["calibration_copy_relative_path"]
                            ),
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
        basis_states: dict[str, int] = defaultdict(int)
        frame_states: dict[str, int] = defaultdict(int)
        evaluation_roles: dict[str, int] = defaultdict(int)
        salience_counts: dict[str, int] = defaultdict(int)
        salience_current_sources = 0
        salience_review = self._load_machine_salience_review()
        for sha, members in sorted(
            self.groups.items(), key=lambda item: int(item[1][0]["sort_index"])
        ):
            path = self.record_path(sha)
            if path.is_file():
                record = self.load_record(sha)
                state = str(record["state"])
                reviewed = list(record["reviewed_task_ids"])
                basis_summary = line_basis_summary(record)
                basis_states[str(basis_summary["status"])] += 1
                frame_summary = frame_state_summary(record)
                frame_states[str(frame_summary["status"])] += 1
                role_summary = evaluation_role_summary(record)
                evaluation_roles[str(role_summary["source_role"])] += 1
                refinement = record["diagnostics"].get("refinement")
                refinement_summary = (
                    {
                        "refinement_revision": refinement.get(
                            "refinement_revision"
                        ),
                        "moved_line_count": refinement.get("moved_line_count", 0),
                        "retained_line_count": refinement.get(
                            "retained_line_count", 0
                        ),
                        "moved_line_ids": refinement.get("moved_line_ids", []),
                    }
                    if isinstance(refinement, dict)
                    else None
                )
                salience_source = self._current_salience_source(
                    record,
                    salience_review,
                )
                salience_summary = source_review_summary(salience_source)
            else:
                state = "not_prepared"
                reviewed = []
                basis_summary = None
                frame_summary = None
                role_summary = None
                refinement_summary = None
                salience_summary = source_review_summary(None)
            if salience_summary["analysis_state"] == "current":
                salience_current_sources += 1
                for key, value in salience_summary.items():
                    if key != "analysis_state":
                        salience_counts[key] += int(value)
                salience_counts["high_confidence_proposal_source_count"] += int(
                    salience_summary["high_confidence_proposal_line_count"] > 0
                )
                salience_counts["pending_proposal_source_count"] += int(
                    salience_summary["pending_proposal_line_count"] > 0
                )
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
                    "line_basis_summary": basis_summary,
                    "frame_state_summary": frame_summary,
                    "evaluation_role_summary": role_summary,
                    "refinement_summary": refinement_summary,
                    "machine_salience_summary": salience_summary,
                    "tasks": [
                        {"sample_id": row["sample_id"], "count": row["count"]}
                        for row in members
                    ],
                }
            )
        return {
            "index_schema": "x5crop_source_annotation_index_v7",
            "tile_max_render_dimension": MAX_TILE_RENDER_DIMENSION,
            "tile_max_source_dimension": MAX_TILE_SOURCE_DIMENSION,
            "tile_max_source_pixels": MAX_TILE_SOURCE_PIXELS,
            "total_unique_sources": len(items),
            "states": dict(sorted(states.items())),
            "basis_states": dict(sorted(basis_states.items())),
            "frame_states": dict(sorted(frame_states.items())),
            "evaluation_roles": dict(sorted(evaluation_roles.items())),
            "machine_salience": (
                {
                    "analysis_revision": salience_review["analysis_revision"],
                    "review_revision": salience_review["review_revision"],
                    "source_count": salience_current_sources,
                    "stale_or_missing_source_count": (
                        len(items) - salience_current_sources
                    ),
                    **dict(sorted(salience_counts.items())),
                }
                if salience_review is not None
                else {
                    "analysis_revision": None,
                    "review_revision": None,
                    "source_count": 0,
                    "stale_or_missing_source_count": len(items),
                }
            ),
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
            return self._record_for_client(updated)

    def analyze_machine_salience(
        self,
        *,
        progress: Any | None = None,
    ) -> dict[str, Any]:
        """Regenerate local review facts without changing golden annotations."""

        from x5crop.image.gray import BaseGrayParameters, make_base_gray_u8
        from x5crop.io.tiff import read_tiff

        from .machine_salience import analyze_source_lines

        source_facts: list[dict[str, Any]] = []
        ordered = sorted(
            self.groups.items(),
            key=lambda item: int(item[1][0]["sort_index"]),
        )
        for offset, (sha, members) in enumerate(ordered, start=1):
            record = self.load_record(sha)
            source_path = self._verify_source(self._canonical_row(members))
            raster, _profile, warnings = read_tiff(source_path)
            if warnings:
                raise WorkspaceError(
                    f"{members[0]['sample_id']}: source TIFF produced warnings"
                )
            gray = make_base_gray_u8(raster, BaseGrayParameters())
            source_fact = analyze_source_lines(record, gray)
            source_facts.append(source_fact)
            if progress is not None:
                progress(
                    offset,
                    len(ordered),
                    members,
                    source_review_summary(source_fact),
                )
            del gray, raster
        existing = self._load_machine_salience_review()
        try:
            review = build_machine_salience_review(
                source_facts,
                existing=existing,
            )
        except ValueError as error:
            raise WorkspaceError(str(error)) from error
        _atomic_json(self.machine_salience_path, review)
        return deepcopy(review["summary"])

    def set_machine_salience_review(
        self,
        identity: str,
        *,
        expected_review_revision: int,
        line_id: str,
        review_status: str,
    ) -> dict[str, Any]:
        """Save an orthogonal human verdict on one current machine proposal."""

        with self._lock:
            record = self.load_record(identity)
            if line_id not in {
                str(line["line_id"]) for line in record["boundary_pool"]
            }:
                raise WorkspaceError("machine salience line is not in the source record")
            review = self._load_machine_salience_review()
            if review is None:
                raise WorkspaceError("machine salience analysis is not prepared")
            try:
                updated = set_line_review_status(
                    review,
                    source_sha256=str(record["source"]["sha256"]),
                    source_geometry_sha256=canonical_record_sha256(
                        geometry_snapshot(record)
                    ),
                    line_id=line_id,
                    review_status=review_status,
                    expected_review_revision=expected_review_revision,
                )
            except ValueError as error:
                raise WorkspaceError(str(error)) from error
            _atomic_json(self.machine_salience_path, updated)
            return {
                "record": self._record_for_client(record, review=updated),
                "index": self.index(),
            }

    def reconcile_review_context(
        self,
        *,
        identities: Iterable[str] | None,
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
        with self._lock:
            for sha in sorted(
                requested,
                key=lambda value: int(self.groups[value][0]["sort_index"]),
            ):
                current = self.load_record(sha)
                if current["state"] == "user_confirmed":
                    raise WorkspaceError("confirmed annotation is immutable")
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
                updated["reviewed_task_ids"] = []
                updated["confirmation"] = None
                self._save_record(updated)
                changed_sources += 1
                changed_lines += len(corrected)
                changed_slots += len(corrected_slots)
        return {
            "changed_sources": changed_sources,
            "changed_lines": changed_lines,
            "changed_slots": changed_slots,
        }

    def refine(
        self,
        *,
        identities: Iterable[str] | None,
        dry_run: bool = False,
        progress: Any | None = None,
    ) -> dict[str, Any]:
        """Apply reviewable refinements without granting gold authority."""

        requested = (
            {self.resolve_identity(identity) for identity in identities}
            if identities is not None
            else set(self.groups)
        )
        counts: dict[str, Any] = {
            "sources": len(requested),
            "refined_sources": 0,
            "unchanged_existing": 0,
            "skipped_modified_after_refinement": 0,
            "skipped_confirmed": 0,
            "moved_lines": 0,
            "retained_lines": 0,
            "dry_run": dry_run,
            "refinement_revision": REFINEMENT_REVISION,
            "source_results": [],
        }
        with self._lock:
            for offset, sha in enumerate(
                sorted(
                    requested,
                    key=lambda value: int(self.groups[value][0]["sort_index"]),
                ),
                start=1,
            ):
                members = self.groups[sha]
                current = self.load_record(sha)
                sample_ids = [str(row["sample_id"]) for row in members]
                if current["state"] == "user_confirmed":
                    counts["skipped_confirmed"] += 1
                    result = {
                        "sample_ids": sample_ids,
                        "status": "skipped_confirmed",
                        "moved_line_count": 0,
                        "retained_line_count": 0,
                    }
                    counts["source_results"].append(result)
                    if progress is not None:
                        progress(offset, len(requested), members, result)
                    continue
                if not line_basis_summary(current)["classification_complete"]:
                    raise WorkspaceError(
                        f"{sample_ids[0]}: all active line bases must be "
                        "classified before refinement"
                    )
                current_geometry_sha = canonical_record_sha256(
                    geometry_snapshot(current)
                )
                existing = current["diagnostics"].get("refinement")
                if (
                    isinstance(existing, dict)
                    and existing.get("refinement_revision") == REFINEMENT_REVISION
                ):
                    line_evidence = existing.get("lines")
                    if (
                        existing.get("human_review_state")
                        not in {"pending", "reviewed", "confirmed"}
                        or existing.get("current_geometry_sha256")
                        != current_geometry_sha
                        or not isinstance(line_evidence, dict)
                        or any(
                            not isinstance(evidence, dict)
                            or evidence.get("human_review_status")
                            not in {
                                "pending",
                                "reviewed",
                                "confirmed",
                                "adjusted_after_refinement",
                            }
                            for evidence in line_evidence.values()
                        )
                    ):
                        raise WorkspaceError("refinement receipt is not current")
                    if existing.get("output_geometry_sha256") == current_geometry_sha:
                        counts["unchanged_existing"] += 1
                        status = "unchanged_existing"
                    else:
                        counts["skipped_modified_after_refinement"] += 1
                        status = "skipped_modified_after_refinement"
                    result = {
                        "sample_ids": sample_ids,
                        "status": status,
                        "moved_line_count": int(existing.get("moved_line_count", 0)),
                        "retained_line_count": int(
                            existing.get("retained_line_count", 0)
                        ),
                    }
                    counts["source_results"].append(result)
                    if progress is not None:
                        progress(offset, len(requested), members, result)
                    continue
                source = self._verify_source(self._canonical_row(members))
                with SourceRaster(source) as raster:
                    try:
                        updated, refinement = refine_record(current, raster)
                    except AnnotationError as error:
                        raise WorkspaceError(
                            f"{sample_ids[0]}: refinement failed: {error}"
                        ) from error
                moved = int(refinement["moved_line_count"])
                retained = int(refinement["retained_line_count"])
                result = {
                    "sample_ids": sample_ids,
                    "status": "dry_run" if dry_run else "refined",
                    "moved_line_count": moved,
                    "retained_line_count": retained,
                    "moved_line_ids": list(refinement["moved_line_ids"]),
                }
                counts["source_results"].append(result)
                counts["refined_sources"] += 1
                counts["moved_lines"] += moved
                counts["retained_lines"] += retained
                if not dry_run:
                    self._save_record(updated)
                if progress is not None:
                    progress(offset, len(requested), members, result)
        return counts

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
            refinement = current["diagnostics"].get("refinement")
            if isinstance(refinement, dict):
                refinement["human_review_state"] = (
                    "reviewed" if reviewed else "pending"
                )
                line_evidence = refinement.get("lines")
                if isinstance(line_evidence, dict):
                    current_points = {
                        line["line_id"]: line["points_raw"]
                        for line in [
                            *current["shared_edges"],
                            *current["boundary_pool"],
                        ]
                    }
                    for line_id, evidence in line_evidence.items():
                        if not isinstance(evidence, dict):
                            continue
                        if reviewed:
                            evidence["human_review_status"] = "reviewed"
                        else:
                            evidence["human_review_status"] = (
                                "adjusted_after_refinement"
                                if current_points.get(line_id)
                                != evidence.get("output_points_raw")
                                else "pending"
                            )
            current["revision"] += 1
            self._save_record(current)
            return self._record_for_client(current)

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
            basis_summary = line_basis_summary(current)
            if not basis_summary["classification_complete"]:
                line_ids = ", ".join(
                    line["line_id"]
                    for line in basis_summary["attention_lines"]
                    if line["review_basis"] in {"unclassified", "unresolved_red_stroke"}
                )
                raise WorkspaceError(
                    f"unclassified line basis must be completed before confirmation: {line_ids}"
                )
            used_boundary_ids = referenced_boundary_ids(current)
            current["boundary_pool"] = [
                line
                for line in current["boundary_pool"]
                if line["line_id"] in used_boundary_ids
            ]
            current["diagnostics"]["unresolved"] = []
            proposal_sha = canonical_record_sha256(geometry_snapshot(current))
            artifact = render_review_artifact(preview_path.read_bytes(), current)
            artifact_sha = hashlib.sha256(artifact).hexdigest()
            artifact_name = (
                f"{current['source']['canonical_sample_id']}_"
                f"{proposal_sha[:12]}_confirmed.jpg"
            )
            artifact_path = self.artifacts_root / artifact_name
            _atomic_write(artifact_path, artifact)
            refinement = current["diagnostics"].get("refinement")
            if isinstance(refinement, dict):
                refinement["human_review_state"] = "confirmed"
                line_evidence = refinement.get("lines")
                if isinstance(line_evidence, dict):
                    for evidence in line_evidence.values():
                        if isinstance(evidence, dict):
                            evidence["human_review_status"] = "confirmed"
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
            return self._record_for_client(current)
