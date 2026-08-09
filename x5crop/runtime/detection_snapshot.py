from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import gzip
from hashlib import sha256
import io
import json
from functools import lru_cache
from pathlib import Path
import sys
from typing import Any

from ..app_info import SCRIPT_NAME, VERSION
from ..domain import Box, WorkspaceExtent
from ..geometry.affine import AffineCoordinateTransform
from ..io.model import ImageProfile
from ..output.naming import portable_component
from ..report.identity import (
    REPORT_SCHEMA_ID,
    REPORT_SCHEMA_REVISION,
    bind_core_facts,
)
from ..report.model import ReportResult
from ..report.read_models import typed_read_model
from ..report.validation import validate_current_report_record
from ..run_config import RunConfig
from .identity import (
    runtime_configuration_identity,
    runtime_environment_identity,
)
from .invocation import PlannedSource


DETECTION_SNAPSHOT_SCHEMA = "x5crop_detection_snapshot_v1"
DETECTION_SNAPSHOT_OWNER = "x5_crop_v5"
DETECTION_SNAPSHOT_DIRECTORY = "_detection_snapshot"
_SNAPSHOT_SECTIONS = (
    "schema",
    "owner",
    "script_version",
    "report_schema_id",
    "report_schema_revision",
    "implementation_sha256",
    "source",
    "detection_configuration",
    "report",
    "snapshot_sha256",
)


class DetectionSnapshotError(ValueError):
    pass


@dataclass(frozen=True)
class SourceContentIdentity:
    input_ordinal: int
    name: str
    portable_stem: str
    size: int
    mtime_ns: int
    sha256: str

    def as_record(self) -> dict[str, Any]:
        return {
            "input_ordinal": self.input_ordinal,
            "name": self.name,
            "portable_stem": self.portable_stem,
            "size": self.size,
            "mtime_ns": self.mtime_ns,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class ReusableDetectionSnapshot:
    path: Path
    record: dict[str, Any]

    @property
    def report(self) -> dict[str, Any]:
        return self.record["report"]

    @property
    def decision_status(self) -> str:
        return str(self.report["decision"]["status"])

    @property
    def final_review_reasons(self) -> tuple[str, ...]:
        return tuple(self.report["decision"]["final_review_reasons"])

    @property
    def final_boxes(self) -> tuple[Box, ...]:
        return _boxes_from_record(
            self.report["output"]["finalization"]["final_boxes"]
        )

    @property
    def sampling_authority_boxes(self) -> tuple[Box, ...]:
        return _boxes_from_record(
            self.report["output"]["finalization"][
                "sampling_authority_boxes"
            ]
        )

    @property
    def transform(self) -> AffineCoordinateTransform:
        value = self.report["output"]["finalization"][
            "transform_assessment"
        ]["transform"]
        if not isinstance(value, dict):
            raise DetectionSnapshotError(
                "approved snapshot lacks an affine transform"
            )
        return _transform_from_record(value)


def detection_snapshot_path(
    output_root: Path,
    source: PlannedSource,
) -> Path:
    name = portable_component(
        source.portable_stem,
        input_ordinal=source.input_ordinal,
        suffix="_detection_snapshot.json.gz",
    ).value
    return output_root / DETECTION_SNAPSHOT_DIRECTORY / name


def source_content_identity(source: PlannedSource) -> SourceContentIdentity:
    before = source.path.stat()
    digest = sha256()
    with source.path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    after = source.path.stat()
    before_identity = (int(before.st_size), int(before.st_mtime_ns))
    after_identity = (int(after.st_size), int(after.st_mtime_ns))
    if before_identity != after_identity:
        raise DetectionSnapshotError(
            "source changed while its SHA-256 was being calculated"
        )
    return SourceContentIdentity(
        input_ordinal=source.input_ordinal,
        name=source.path.name,
        portable_stem=source.portable_stem,
        size=after_identity[0],
        mtime_ns=after_identity[1],
        sha256=digest.hexdigest(),
    )


def detection_configuration_binding(
    configuration_detail: dict[str, Any],
    layout: str,
) -> dict[str, Any]:
    return {
        "layout": layout,
        "configuration": deepcopy(configuration_detail),
    }


def _module_name_for_path(package_root: Path, path: Path) -> str:
    parts = [package_root.name, *path.relative_to(package_root).with_suffix("").parts]
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


@lru_cache(maxsize=1)
def implementation_sha256() -> str:
    embedded = getattr(sys.modules.get("__main__"), "_X5_EMBEDDED_SOURCES", None)
    if isinstance(embedded, dict) and embedded:
        sources = {
            str(name): str(source)
            for name, source in embedded.items()
            if str(name) == "x5crop" or str(name).startswith("x5crop.")
        }
    else:
        package_root = Path(__file__).resolve().parents[1]
        sources = {
            _module_name_for_path(package_root, path): path.read_text(
                encoding="utf-8"
            )
            for path in sorted(package_root.rglob("*.py"))
        }
    if not sources:
        raise DetectionSnapshotError(
            "current implementation sources are unavailable"
        )
    digest = sha256()
    for name in sorted(sources):
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sources[name].encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _canonical_sha256(record: dict[str, Any]) -> str:
    payload = {
        key: value
        for key, value in record.items()
        if key != "snapshot_sha256"
    }
    digest = sha256()

    class DigestWriter:
        def write(self, value: str) -> int:
            digest.update(value.encode("utf-8"))
            return len(value)

    json.dump(
        payload,
        DigestWriter(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return digest.hexdigest()


def _write_record(path: Path, record: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8") as text:
                json.dump(record, text, ensure_ascii=False, separators=(",", ":"))
    return path


def write_detection_snapshot(
    path: Path,
    *,
    source_identity: SourceContentIdentity,
    configuration_binding: dict[str, Any],
    report: dict[str, Any],
) -> Path:
    validate_current_report_record(report)
    if report["output"]["finalization"]["frame_export_requested"]:
        raise DetectionSnapshotError(
            "detection snapshots may only be created by preview runs"
        )
    record: dict[str, Any] = {
        "schema": DETECTION_SNAPSHOT_SCHEMA,
        "owner": DETECTION_SNAPSHOT_OWNER,
        "script_version": VERSION,
        "report_schema_id": REPORT_SCHEMA_ID,
        "report_schema_revision": REPORT_SCHEMA_REVISION,
        "implementation_sha256": implementation_sha256(),
        "source": source_identity.as_record(),
        "detection_configuration": configuration_binding,
        "report": report,
    }
    record["snapshot_sha256"] = _canonical_sha256(record)
    return _write_record(path, record)


def carry_detection_snapshot(
    snapshot: ReusableDetectionSnapshot,
    output_root: Path,
    source: PlannedSource,
) -> Path:
    return _write_record(
        detection_snapshot_path(output_root, source),
        snapshot.record,
    )


def _read_record(path: Path) -> dict[str, Any]:
    try:
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DetectionSnapshotError("snapshot is unreadable") from exc
    if not isinstance(value, dict):
        raise DetectionSnapshotError("snapshot root must be an object")
    return value


def load_detection_snapshot(
    path: Path,
    *,
    source_identity: SourceContentIdentity,
    configuration_binding: dict[str, Any],
    profile: ImageProfile,
) -> ReusableDetectionSnapshot:
    record = _read_record(path)
    if tuple(record) != _SNAPSHOT_SECTIONS:
        raise DetectionSnapshotError("snapshot sections are not current")
    if (
        record["schema"] != DETECTION_SNAPSHOT_SCHEMA
        or record["owner"] != DETECTION_SNAPSHOT_OWNER
        or record["script_version"] != VERSION
        or record["report_schema_id"] != REPORT_SCHEMA_ID
        or record["report_schema_revision"] != REPORT_SCHEMA_REVISION
        or record["implementation_sha256"] != implementation_sha256()
    ):
        raise DetectionSnapshotError("snapshot program identity is stale")
    if record["snapshot_sha256"] != _canonical_sha256(record):
        raise DetectionSnapshotError("snapshot integrity hash does not match")
    source_record = record.get("source")
    if (
        not isinstance(source_record, dict)
        or source_record.get("sha256") != source_identity.sha256
    ):
        raise DetectionSnapshotError("snapshot source SHA-256 does not match")
    if record["detection_configuration"] != configuration_binding:
        raise DetectionSnapshotError("snapshot detection configuration does not match")
    report = record.get("report")
    if not isinstance(report, dict):
        raise DetectionSnapshotError("snapshot report payload is missing")
    try:
        validate_current_report_record(report)
    except (KeyError, TypeError, ValueError) as exc:
        raise DetectionSnapshotError("snapshot report payload is invalid") from exc
    if (
        report["output"]["finalization"]["frame_export_requested"]
        or report["configuration"] != configuration_binding["configuration"]
        or report["runtime_identity"]["runtime_configuration"].get(
            "preview"
        )
        is not True
        or report["runtime_identity"]["runtime_configuration"]["layout"]
        != configuration_binding["layout"]
        or report["runtime_identity"]["runtime_environment"]
        != runtime_environment_identity()
        or report["input"]["profile"] != typed_read_model(profile)
    ):
        raise DetectionSnapshotError("snapshot evidence binding does not match")
    snapshot = ReusableDetectionSnapshot(path=path, record=record)
    if snapshot.decision_status == "approved_auto":
        if (
            not snapshot.final_boxes
            or len(snapshot.final_boxes) != len(snapshot.sampling_authority_boxes)
        ):
            raise DetectionSnapshotError("snapshot approved geometry is incomplete")
        snapshot.transform
    return snapshot


def result_from_detection_snapshot(
    snapshot: ReusableDetectionSnapshot,
    *,
    input_file: Path,
    profile: ImageProfile,
    source_runtime_identity: dict[str, Any],
    config: RunConfig,
    output_files: list[str],
    review_copy: str | None,
    warnings: list[str],
) -> ReportResult:
    record = deepcopy(snapshot.report)
    record["script_version"] = VERSION
    record["source"] = str(input_file)
    record["input"]["profile"] = typed_read_model(profile)
    finalization = record["output"]["finalization"]
    approved = record["decision"]["status"] == "approved_auto"
    finalization["frame_export_requested"] = True
    finalization["frame_export_performed"] = bool(output_files)
    finalization["official_tiff_expected"] = approved
    finalization["official_tiff_count"] = len(output_files)
    record["output"]["tiff_fidelity"]["write_readback_validated"] = bool(
        output_files
    )
    record["output"]["tiff_fidelity"]["success_receipt"] = (
        "validated" if output_files else "not_created"
    )
    record["output"]["output_files"] = list(output_files)
    record["output"]["review_copy"] = review_copy
    record["output"]["warnings"] = list(warnings)
    runtime_identity = record["runtime_identity"]
    runtime_identity["script"] = SCRIPT_NAME
    runtime_identity["script_version"] = VERSION
    runtime_identity["source"] = dict(source_runtime_identity)
    runtime_identity["runtime_configuration"] = runtime_configuration_identity(
        config
    )
    runtime_identity["runtime_environment"] = runtime_environment_identity()
    return ReportResult(record=bind_core_facts(record))


def _boxes_from_record(values: object) -> tuple[Box, ...]:
    if not isinstance(values, list):
        raise DetectionSnapshotError("snapshot boxes are not a list")
    boxes: list[Box] = []
    for value in values:
        if not isinstance(value, dict) or set(value) != {
            "left",
            "top",
            "right",
            "bottom",
        }:
            raise DetectionSnapshotError("snapshot box is invalid")
        boxes.append(
            Box(
                left=int(value["left"]),
                top=int(value["top"]),
                right=int(value["right"]),
                bottom=int(value["bottom"]),
            )
        )
    if any(not box.valid() for box in boxes):
        raise DetectionSnapshotError("snapshot box is empty")
    return tuple(boxes)


def _transform_from_record(value: dict[str, Any]) -> AffineCoordinateTransform:
    if set(value) != {"matrix", "source_extent", "output_extent"}:
        raise DetectionSnapshotError("snapshot affine transform is invalid")
    matrix = value["matrix"]
    source_extent = value["source_extent"]
    output_extent = value["output_extent"]
    if (
        not isinstance(matrix, list)
        or len(matrix) != 3
        or any(not isinstance(row, list) or len(row) != 3 for row in matrix)
        or not isinstance(source_extent, dict)
        or not isinstance(output_extent, dict)
    ):
        raise DetectionSnapshotError("snapshot affine transform is incomplete")
    return AffineCoordinateTransform(
        matrix=tuple(
            tuple(float(item) for item in row)
            for row in matrix
        ),
        source_extent=WorkspaceExtent(
            width=int(source_extent["width"]),
            height=int(source_extent["height"]),
        ),
        output_extent=WorkspaceExtent(
            width=int(output_extent["width"]),
            height=int(output_extent["height"]),
        ),
    )
