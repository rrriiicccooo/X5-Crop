from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from ..app_info import SCRIPT_NAME, VERSION
from ..domain import Box, WorkspaceExtent
from ..geometry.affine import AffineCoordinateTransform
from ..io.model import ImageProfile
from ..report.identity import bind_core_facts
from ..report.model import ReportResult
from ..report.read_models import typed_read_model
from ..report.validation import validate_current_report_record
from ..run_config import RunConfig
from .identity import (
    runtime_configuration_identity,
    runtime_environment_identity,
)
from .invocation import PlannedSource


class AnalysisReportReuseError(ValueError):
    pass


@dataclass(frozen=True)
class ReusableAnalysisReport:
    path: Path
    record: dict[str, Any]

    @property
    def decision_status(self) -> str:
        return str(self.record["decision"]["status"])

    @property
    def final_review_reasons(self) -> tuple[str, ...]:
        return tuple(self.record["decision"]["final_review_reasons"])

    @property
    def final_boxes(self) -> tuple[Box, ...]:
        return _boxes_from_record(
            self.record["output"]["finalization"]["final_boxes"]
        )

    @property
    def sampling_authority_boxes(self) -> tuple[Box, ...]:
        return _boxes_from_record(
            self.record["output"]["finalization"][
                "sampling_authority_boxes"
            ]
        )

    @property
    def transform(self) -> AffineCoordinateTransform:
        value = self.record["output"]["finalization"][
            "transform_assessment"
        ]["transform"]
        if not isinstance(value, dict):
            raise AnalysisReportReuseError(
                "approved report lacks an affine transform"
            )
        return _transform_from_record(value)


def _read_report_records(path: Path) -> tuple[dict[str, Any], ...]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise AnalysisReportReuseError("analysis report is unreadable") from exc
    records: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AnalysisReportReuseError(
                "analysis report contains invalid JSONL"
            ) from exc
        if not isinstance(record, dict):
            raise AnalysisReportReuseError(
                "analysis report record must be an object"
            )
        records.append(record)
    if not records:
        raise AnalysisReportReuseError("analysis report is empty")
    return tuple(records)


def _same_detection_runtime_configuration(
    recorded: object,
    config: RunConfig,
) -> bool:
    if not isinstance(recorded, dict):
        return False
    expected = runtime_configuration_identity(config)
    return {
        key: value
        for key, value in recorded.items()
        if key != "debug_analysis"
    } == {
        key: value
        for key, value in expected.items()
        if key != "debug_analysis"
    }


def _record_matches_source(
    record: dict[str, Any],
    source: PlannedSource,
) -> bool:
    runtime_identity = record.get("runtime_identity")
    if not isinstance(runtime_identity, dict):
        return False
    identity = runtime_identity.get("source")
    return (
        isinstance(identity, dict)
        and identity.get("input_ordinal") == source.input_ordinal
        and identity.get("name") == source.path.name
        and identity.get("portable_stem") == source.portable_stem
    )


def _validate_reusable_record(
    record: dict[str, Any],
    *,
    source_identity: dict[str, Any],
    configuration_detail: dict[str, Any],
    profile: ImageProfile,
    config: RunConfig,
) -> None:
    validate_current_report_record(record)
    if record["script_version"] != VERSION:
        raise AnalysisReportReuseError("analysis report version is stale")
    if record["runtime_identity"]["source"] != source_identity:
        raise AnalysisReportReuseError(
            "analysis report source identity does not match"
        )
    if record["input"]["profile"] != typed_read_model(profile):
        raise AnalysisReportReuseError(
            "analysis report TIFF profile does not match"
        )
    if record["configuration"] != configuration_detail:
        raise AnalysisReportReuseError(
            "analysis report detection configuration does not match"
        )
    if not _same_detection_runtime_configuration(
        record["runtime_identity"].get("runtime_configuration"),
        config,
    ):
        raise AnalysisReportReuseError(
            "analysis report runtime configuration does not match"
        )
    reusable = ReusableAnalysisReport(Path(), record)
    if reusable.decision_status == "approved_auto":
        if (
            not reusable.final_boxes
            or len(reusable.final_boxes)
            != len(reusable.sampling_authority_boxes)
        ):
            raise AnalysisReportReuseError(
                "approved analysis report geometry is incomplete"
            )
        reusable.transform


def find_reusable_analysis_report(
    report_path: Path,
    *,
    source: PlannedSource,
    source_identity: dict[str, Any],
    configuration_detail: dict[str, Any],
    profile: ImageProfile,
    config: RunConfig,
) -> tuple[ReusableAnalysisReport | None, str | None]:
    try:
        records = _read_report_records(report_path)
    except AnalysisReportReuseError as exc:
        return None, str(exc)
    failures: list[str] = []
    for record in records:
        if not _record_matches_source(record, source):
            continue
        try:
            _validate_reusable_record(
                record,
                source_identity=source_identity,
                configuration_detail=configuration_detail,
                profile=profile,
                config=config,
            )
        except (KeyError, TypeError, ValueError) as exc:
            failures.append(str(exc))
            continue
        return ReusableAnalysisReport(report_path, record), None
    return (
        None,
        failures[-1] if failures else "analysis report has no matching source record",
    )


def result_from_reusable_analysis_report(
    reusable: ReusableAnalysisReport,
    *,
    input_file: Path,
    profile: ImageProfile,
    source_runtime_identity: dict[str, Any],
    config: RunConfig,
    output_files: list[str],
    review_copy: str | None,
    warnings: list[str],
) -> ReportResult:
    record = deepcopy(reusable.record)
    record["script_version"] = VERSION
    record["source"] = str(input_file)
    record["input"]["profile"] = typed_read_model(profile)
    finalization = record["output"]["finalization"]
    approved = record["decision"]["status"] == "approved_auto"
    finalization["frame_export_requested"] = True
    finalization["frame_export_performed"] = bool(output_files)
    finalization["official_tiff_expected"] = approved
    finalization["official_tiff_count"] = len(output_files)
    fidelity = record["output"]["tiff_fidelity"]
    fidelity["write_readback_validated"] = bool(output_files)
    fidelity["success_receipt"] = (
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
    bind_core_facts(record)
    validate_current_report_record(record)
    return ReportResult(record=record)


def _boxes_from_record(values: object) -> tuple[Box, ...]:
    if not isinstance(values, list):
        raise AnalysisReportReuseError("analysis report boxes are not a list")
    boxes: list[Box] = []
    for value in values:
        if not isinstance(value, dict) or set(value) != {
            "left",
            "top",
            "right",
            "bottom",
        }:
            raise AnalysisReportReuseError("analysis report box is invalid")
        boxes.append(
            Box(
                left=int(value["left"]),
                top=int(value["top"]),
                right=int(value["right"]),
                bottom=int(value["bottom"]),
            )
        )
    if any(not box.valid() for box in boxes):
        raise AnalysisReportReuseError("analysis report box is empty")
    return tuple(boxes)


def _transform_from_record(value: dict[str, Any]) -> AffineCoordinateTransform:
    if set(value) != {"matrix", "source_extent", "output_extent"}:
        raise AnalysisReportReuseError(
            "analysis report affine transform is invalid"
        )
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
        raise AnalysisReportReuseError(
            "analysis report affine transform is incomplete"
        )
    return AffineCoordinateTransform(
        matrix=tuple(tuple(float(item) for item in row) for row in matrix),
        source_extent=WorkspaceExtent(
            width=int(source_extent["width"]),
            height=int(source_extent["height"]),
        ),
        output_extent=WorkspaceExtent(
            width=int(output_extent["width"]),
            height=int(output_extent["height"]),
        ),
    )
