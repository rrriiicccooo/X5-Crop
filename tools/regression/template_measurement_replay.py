"""Developer-only replay of the exact registered template-solver inputs."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable

from x5crop.domain import FiniteInterval, ObservationId, PositiveInterval
from x5crop.detection.photo_geometry.measurement_model import (
    PhotoBoundaryCoverageReceipt,
)
from x5crop.detection.photo_geometry.model import (
    BoundaryAxis,
    BoundaryEvidenceState,
    BoundaryRole,
    PHOTO_BOUNDARY_MEASUREMENT_REVISION,
)
from x5crop.detection.photo_geometry.observation_types import (
    BoundaryEdgeObservation,
    SeparatorBandObservation,
    SeparatorMaterialRegionObservation,
)
from x5crop.detection.photo_geometry.template_cross import fit_template_cross
from x5crop.detection.photo_geometry.template_cross_model import (
    CrossEvidence,
    CrossRoleBinding,
    TemplateCrossInput,
)
from x5crop.detection.photo_geometry.template_model import (
    PhaseLatticeAuthority,
    TemplateRole,
    TemplateSpec,
)
from x5crop.detection.photo_geometry.template_phase import (
    fit_template_phase_with_local_advance,
)
from x5crop.detection.photo_geometry.template_phase_model import (
    TemplatePhaseInput,
)
from x5crop.detection.photo_geometry.template_runtime_model import (
    PreparedTemplateLane,
)


REPLAY_SCHEMA = "x5crop_template_measurement_replay_v1"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_FORBIDDEN_TRUTH_KEYS = {
    "accuracy",
    "expected_frames",
    "gold",
    "gold_frames",
    "gold_geometry",
    "golden",
    "ground_truth",
    "reference_geometry",
    "truth",
}


@dataclass(frozen=True)
class ReplayConfiguration:
    format_id: str
    count: int
    holder_profile_id: str
    lane_id: str
    layout: str

    def __post_init__(self) -> None:
        if (
            not self.format_id
            or not isinstance(self.count, int)
            or isinstance(self.count, bool)
            or self.count <= 0
            or not self.holder_profile_id
            or not self.lane_id
            or self.layout not in {"horizontal", "vertical"}
        ):
            raise ValueError("replay configuration is invalid")


@dataclass(frozen=True)
class TemplateMeasurementReplay:
    source_sha256: str
    configuration: ReplayConfiguration
    measurement_revision: str
    physical_identity: str
    plan_identity: str
    template_id: str
    phase_input: TemplatePhaseInput
    cross_input: TemplateCrossInput
    coverage_receipts: tuple[PhotoBoundaryCoverageReceipt, ...]

    def __post_init__(self) -> None:
        if not _SHA256.fullmatch(self.source_sha256):
            raise ValueError("replay source identity must be a lowercase SHA-256")
        if self.measurement_revision != PHOTO_BOUNDARY_MEASUREMENT_REVISION:
            raise ValueError("replay measurement revision is not current")
        if not self.physical_identity or not self.plan_identity:
            raise ValueError("replay requires compiled template identities")
        if (
            self.phase_input.template != self.cross_input.template
            or self.phase_input.template.template_id != self.template_id
        ):
            raise ValueError("replay solver inputs disagree on template identity")
        query_ids = tuple(item.query_id for item in self.coverage_receipts)
        if len(set(query_ids)) != len(query_ids):
            raise ValueError("replay coverage receipts must be unique")

    @classmethod
    def capture(
        cls,
        lane: PreparedTemplateLane,
        *,
        source_sha256: str,
    ) -> "TemplateMeasurementReplay":
        if not isinstance(lane, PreparedTemplateLane):
            raise TypeError("replay capture requires a prepared template lane")
        plan = lane.measurement_plan
        return cls(
            source_sha256=source_sha256,
            configuration=ReplayConfiguration(
                format_id=plan.format_spec.format_id,
                count=plan.count,
                holder_profile_id=plan.lane_authority.authority_profile_id,
                lane_id=plan.lane_id,
                layout=plan.layout,
            ),
            measurement_revision=PHOTO_BOUNDARY_MEASUREMENT_REVISION,
            physical_identity=plan.physical_identity,
            plan_identity=plan.plan_identity,
            template_id=lane.template_spec.template_id,
            phase_input=lane.phase_input,
            cross_input=lane.cross_input,
            coverage_receipts=lane.measurement_work.coverage_receipts,
        )

    def rerun(self) -> tuple[object, object]:
        """Run the same solvers without TIFF pixels or another input path."""

        return (
            fit_template_phase_with_local_advance(self.phase_input),
            fit_template_cross(self.cross_input),
        )


_DATACLASSES = {
    item.__name__: item
    for item in (
        FiniteInterval,
        PositiveInterval,
        PhaseLatticeAuthority,
        TemplateRole,
        TemplateSpec,
        BoundaryEdgeObservation,
        SeparatorMaterialRegionObservation,
        SeparatorBandObservation,
        CrossRoleBinding,
        TemplatePhaseInput,
        TemplateCrossInput,
        PhotoBoundaryCoverageReceipt,
        ReplayConfiguration,
    )
}
_ENUMS = {
    item.__name__: item
    for item in (
        BoundaryAxis,
        BoundaryEvidenceState,
        BoundaryRole,
        CrossEvidence,
    )
}


def _encode(value: object) -> object:
    if isinstance(value, ObservationId):
        return {"$observation_id": str(value)}
    if isinstance(value, Enum):
        return {"$enum": type(value).__name__, "value": value.value}
    if is_dataclass(value) and not isinstance(value, type):
        name = type(value).__name__
        if name not in _DATACLASSES:
            raise TypeError(f"replay does not allow dataclass {name}")
        return {
            "$type": name,
            "fields": {item.name: _encode(getattr(value, item.name)) for item in fields(value)},
        }
    if isinstance(value, tuple):
        return {"$tuple": [_encode(item) for item in value]}
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise TypeError(f"replay value is not canonical JSON data: {type(value).__name__}")


def _decode(value: object) -> object:
    if not isinstance(value, dict):
        if value is None or isinstance(value, (bool, int, str)):
            return value
        if isinstance(value, float) and math.isfinite(value):
            return value
        raise ValueError("replay contains non-canonical JSON data")
    if set(value) == {"$observation_id"}:
        return ObservationId(str(value["$observation_id"]))
    if set(value) == {"$tuple"} and isinstance(value["$tuple"], list):
        return tuple(_decode(item) for item in value["$tuple"])
    if set(value) == {"$enum", "value"}:
        enum_type = _ENUMS.get(str(value["$enum"]))
        if enum_type is None:
            raise ValueError("replay contains an unknown enum type")
        return enum_type(value["value"])
    if set(value) == {"$type", "fields"} and isinstance(value["fields"], dict):
        record_type = _DATACLASSES.get(str(value["$type"]))
        if record_type is None:
            raise ValueError("replay contains an unknown record type")
        expected = {item.name for item in fields(record_type)}
        if set(value["fields"]) != expected:
            raise ValueError("replay record fields do not match the current type")
        return record_type(
            **{key: _decode(item) for key, item in value["fields"].items()}
        )
    raise ValueError("replay contains an invalid tagged value")


def _reject_truth_fields(value: object) -> None:
    if isinstance(value, dict):
        keys = {str(key).lower() for key in value}
        if keys & _FORBIDDEN_TRUTH_KEYS:
            raise ValueError("measurement replay cannot contain truth or accuracy data")
        for item in value.values():
            _reject_truth_fields(item)
    elif isinstance(value, list):
        for item in value:
            _reject_truth_fields(item)


def replay_record(replay: TemplateMeasurementReplay) -> dict[str, object]:
    return {
        "schema": REPLAY_SCHEMA,
        "source_sha256": replay.source_sha256,
        "configuration": _encode(replay.configuration),
        "measurement_revision": replay.measurement_revision,
        "physical_identity": replay.physical_identity,
        "plan_identity": replay.plan_identity,
        "template_id": replay.template_id,
        "phase_input": _encode(replay.phase_input),
        "cross_input": _encode(replay.cross_input),
        "coverage_receipts": _encode(replay.coverage_receipts),
    }


def _load_record(record: object) -> TemplateMeasurementReplay:
    if not isinstance(record, dict):
        raise ValueError("replay line must be a JSON object")
    _reject_truth_fields(record)
    expected = {
        "schema",
        "source_sha256",
        "configuration",
        "measurement_revision",
        "physical_identity",
        "plan_identity",
        "template_id",
        "phase_input",
        "cross_input",
        "coverage_receipts",
    }
    if set(record) != expected or record["schema"] != REPLAY_SCHEMA:
        raise ValueError("replay does not use the current schema")
    configuration = _decode(record["configuration"])
    phase_input = _decode(record["phase_input"])
    cross_input = _decode(record["cross_input"])
    receipts = _decode(record["coverage_receipts"])
    if (
        not isinstance(configuration, ReplayConfiguration)
        or not isinstance(phase_input, TemplatePhaseInput)
        or not isinstance(cross_input, TemplateCrossInput)
        or not isinstance(receipts, tuple)
        or any(not isinstance(item, PhotoBoundaryCoverageReceipt) for item in receipts)
    ):
        raise TypeError("replay decoded to the wrong canonical types")
    return TemplateMeasurementReplay(
        source_sha256=str(record["source_sha256"]),
        configuration=configuration,
        measurement_revision=str(record["measurement_revision"]),
        physical_identity=str(record["physical_identity"]),
        plan_identity=str(record["plan_identity"]),
        template_id=str(record["template_id"]),
        phase_input=phase_input,
        cross_input=cross_input,
        coverage_receipts=receipts,
    )


def dump_jsonl(replays: Iterable[TemplateMeasurementReplay]) -> str:
    return "".join(
        json.dumps(replay_record(item), sort_keys=True, separators=(",", ":")) + "\n"
        for item in replays
    )


def load_jsonl(
    text: str,
    *,
    expected_source_sha256: str | None = None,
    expected_plan_identity: str | None = None,
) -> tuple[TemplateMeasurementReplay, ...]:
    rows = tuple(
        _load_record(json.loads(line))
        for line in text.splitlines()
        if line.strip()
    )
    if not rows:
        raise ValueError("measurement replay is empty")
    if expected_source_sha256 is not None and any(
        item.source_sha256 != expected_source_sha256 for item in rows
    ):
        raise ValueError("measurement replay source identity mismatch")
    if expected_plan_identity is not None and any(
        item.plan_identity != expected_plan_identity for item in rows
    ):
        raise ValueError("measurement replay plan identity mismatch")
    return rows


def dump_file(path: Path, replays: Iterable[TemplateMeasurementReplay]) -> None:
    path.write_text(dump_jsonl(replays), encoding="utf-8")


def load_file(
    path: Path,
    *,
    expected_source_sha256: str | None = None,
    expected_plan_identity: str | None = None,
) -> tuple[TemplateMeasurementReplay, ...]:
    return load_jsonl(
        path.read_text(encoding="utf-8"),
        expected_source_sha256=expected_source_sha256,
        expected_plan_identity=expected_plan_identity,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "inspect"))
    parser.add_argument("path", type=Path)
    parser.add_argument("--source-sha256")
    parser.add_argument("--plan-identity")
    args = parser.parse_args(argv)
    replays = load_file(
        args.path,
        expected_source_sha256=args.source_sha256,
        expected_plan_identity=args.plan_identity,
    )
    if args.command == "inspect":
        for item in replays:
            phase, cross = item.rerun()
            print(
                json.dumps(
                    {
                        "source_sha256": item.source_sha256,
                        "lane_id": item.configuration.lane_id,
                        "plan_identity": item.plan_identity,
                        "phase_status": phase.status.value,
                        "cross_status": cross.status.value,
                    },
                    sort_keys=True,
                )
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
