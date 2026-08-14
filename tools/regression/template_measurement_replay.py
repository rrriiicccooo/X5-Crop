"""Developer-only, identity-bound JSONL replay of template measurements.

The record carries measurements and bounded work receipts only.  It is not a
reference, truth, accuracy, crop, or production fallback artifact.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
import json
import math
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Mapping


REPLAY_RECORD_SCHEMA = "x5crop_template_measurement_replay_v2"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_FORBIDDEN_KEY_PARTS = (
    "accuracy",
    "gold",
    "groundtruth",
    "reference",
    "truth",
)


def _check_key(key: object) -> str:
    if not isinstance(key, str) or not key:
        raise TypeError("replay mapping keys must be non-empty strings")
    lowered = key.casefold().replace("-", "_")
    if any(part in lowered for part in _FORBIDDEN_KEY_PARTS):
        raise ValueError("replay records cannot carry truth/reference semantics")
    return key


def _freeze(value: object) -> object:
    if isinstance(value, Enum):
        return _freeze(value.value)
    if is_dataclass(value) and not isinstance(value, type):
        return _freeze({field.name: getattr(value, field.name) for field in fields(value)})
    if isinstance(value, Mapping):
        result = {
            _check_key(key): _freeze(item)
            for key, item in value.items()
        }
        return MappingProxyType(result)
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (str, bool, int)) or value is None:
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("replay numbers must be finite")
        return value
    raise TypeError(f"unsupported replay value: {type(value).__name__}")


def _json_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    return value


def _mapping(value: object, name: str) -> Mapping[str, object]:
    frozen = _freeze(value)
    if not isinstance(frozen, Mapping):
        raise TypeError(f"{name} must be a mapping or dataclass record")
    return frozen


def _rows(value: object, name: str, identity_key: str) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, (tuple, list)):
        raise TypeError(f"{name} must be a sequence of records")
    rows = tuple(_mapping(item, name) for item in value)
    identities = tuple(row.get(identity_key) for row in rows)
    if any(not isinstance(identity, str) or not identity for identity in identities):
        raise ValueError(f"{name} records require non-empty {identity_key}")
    if len(set(identities)) != len(identities):
        raise ValueError(f"{name} identities must be unique")
    return rows


def _identity(value: object, name: str) -> Mapping[str, object]:
    result = _mapping(value, name)
    if not result:
        raise ValueError(f"{name} must not be empty")
    return result


@dataclass(frozen=True, slots=True, init=False)
class TemplateMeasurementReplay:
    """Frozen current-only replay facts for one source and template plan."""

    source_sha256: str
    config_identity: Mapping[str, object]
    measurement_revision: str
    template_plan_identity: Mapping[str, object]
    fitted_template_spec: Mapping[str, object]
    registered_query_receipts: tuple[Mapping[str, object], ...]
    sequence_edges: tuple[Mapping[str, object], ...]
    separator_bands: tuple[Mapping[str, object], ...]
    cross_bindings: tuple[Mapping[str, object], ...]
    content_occupancy_summary: tuple[Mapping[str, object], ...]

    def __init__(
        self,
        *,
        source_sha256: str,
        config_identity: Mapping[str, object],
        measurement_revision: str,
        template_plan_identity: Mapping[str, object],
        fitted_template_spec: Mapping[str, object],
        registered_query_receipts: tuple[Mapping[str, object], ...] | list[Mapping[str, object]],
        sequence_edges: tuple[Mapping[str, object], ...] | list[Mapping[str, object]],
        separator_bands: tuple[Mapping[str, object], ...] | list[Mapping[str, object]],
        cross_bindings: tuple[Mapping[str, object], ...] | list[Mapping[str, object]],
        content_occupancy_summary: tuple[Mapping[str, object], ...] | list[Mapping[str, object]],
    ) -> None:
        if not isinstance(source_sha256, str) or _SHA256.fullmatch(source_sha256) is None:
            raise ValueError("source_sha256 must be a lowercase SHA-256 digest")
        if not isinstance(measurement_revision, str) or not measurement_revision.strip():
            raise ValueError("measurement_revision must be non-empty")
        object.__setattr__(self, "source_sha256", source_sha256)
        object.__setattr__(self, "config_identity", _identity(config_identity, "config_identity"))
        object.__setattr__(self, "measurement_revision", measurement_revision)
        object.__setattr__(self, "template_plan_identity", _identity(template_plan_identity, "template_plan_identity"))
        object.__setattr__(self, "fitted_template_spec", _identity(fitted_template_spec, "fitted_template_spec"))
        object.__setattr__(self, "registered_query_receipts", _rows(registered_query_receipts, "registered_query_receipts", "query_id"))
        object.__setattr__(self, "sequence_edges", _rows(sequence_edges, "sequence_edges", "observation_id"))
        object.__setattr__(self, "separator_bands", _rows(separator_bands, "separator_bands", "observation_id"))
        object.__setattr__(self, "cross_bindings", _rows(cross_bindings, "cross_bindings", "observation_id"))
        object.__setattr__(self, "content_occupancy_summary", _rows(content_occupancy_summary, "content_occupancy_summary", "lane_id"))

    def as_record(self) -> dict[str, object]:
        return {
            "record_schema": REPLAY_RECORD_SCHEMA,
            "source_sha256": self.source_sha256,
            "config_identity": _json_value(self.config_identity),
            "measurement_revision": self.measurement_revision,
            "template_plan_identity": _json_value(self.template_plan_identity),
            "fitted_template_spec": _json_value(self.fitted_template_spec),
            "registered_query_receipts": _json_value(self.registered_query_receipts),
            "sequence_edges": _json_value(self.sequence_edges),
            "separator_bands": _json_value(self.separator_bands),
            "cross_bindings": _json_value(self.cross_bindings),
            "content_occupancy_summary": _json_value(self.content_occupancy_summary),
        }


@dataclass(frozen=True)
class TemplateReplayFitResult:
    phase: object
    cross: object


def capture_template_measurement_replay(
    prepared: object,
    *,
    source_sha256: str,
    config_identity: Mapping[str, object],
    measurement_revision: str,
    content_occupancy_summary: tuple[Mapping[str, object], ...] = (),
) -> TemplateMeasurementReplay:
    """Capture only registered facts from one prepared template lane."""

    from x5crop.detection.photo_geometry.template_runtime_model import (
        PreparedTemplateLane,
    )

    if not isinstance(prepared, PreparedTemplateLane):
        raise TypeError("template replay capture requires a prepared lane")
    plan = prepared.measurement_plan
    return TemplateMeasurementReplay(
        source_sha256=source_sha256,
        config_identity=config_identity,
        measurement_revision=measurement_revision,
        template_plan_identity={
            "physical_identity": plan.physical_identity,
            "plan_identity": plan.plan_identity,
            "template_id": prepared.template_spec.template_id,
        },
        fitted_template_spec=_mapping(
            prepared.template_spec,
            "fitted_template_spec",
        ),
        registered_query_receipts=prepared.measurement_work.coverage_receipts,
        sequence_edges=prepared.sequence_edges,
        separator_bands=prepared.separator_bands,
        cross_bindings=(
            *prepared.top_cross_bindings,
            *prepared.bottom_cross_bindings,
        ),
        content_occupancy_summary=content_occupancy_summary,
    )


def _finite(value: object, name: str):
    from x5crop.domain import FiniteInterval

    if not isinstance(value, Mapping) or set(value) != {"minimum", "maximum"}:
        raise ValueError(f"replay {name} interval is not canonical")
    return FiniteInterval(float(value["minimum"]), float(value["maximum"]))


def _observation_ids(value: object, name: str):
    from x5crop.domain import ObservationId

    if not isinstance(value, tuple) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"replay {name} identities are invalid")
    return tuple(ObservationId(item) for item in value)


def _template_spec(value: Mapping[str, object]):
    from x5crop.detection.photo_geometry.template_model import (
        PhaseAuthority,
        PhaseLatticeAuthority,
        TemplateSpec,
    )

    lattice = value.get("phase_lattice_authority")
    if not isinstance(lattice, Mapping):
        raise ValueError("replay template lattice is missing")
    authority = PhaseAuthority(str(value["phase_authority"]))
    return TemplateSpec(
        template_id=str(value["template_id"]),
        frame_width_px=_finite(value["frame_width_px"], "frame width"),
        pitch_px=_finite(value["pitch_px"], "pitch"),
        count=int(value["count"]),
        phase_authority=authority,
        phase_lattice_authority=PhaseLatticeAuthority(
            period_px=_finite(lattice["period_px"], "lattice period"),
            cycle_origin_px=float(lattice["cycle_origin_px"]),
            minimum_slot_offset=int(lattice["minimum_slot_offset"]),
            maximum_slot_offset=int(lattice["maximum_slot_offset"]),
            phase_authority=PhaseAuthority(str(lattice["phase_authority"])),
        ),
        frame_height_px=(
            None
            if value.get("frame_height_px") is None
            else _finite(value["frame_height_px"], "frame height")
        ),
        direction=int(value["direction"]),
        cross=(None if value.get("cross") is None else str(value["cross"])),
        nominal_gap_px=(
            None
            if value.get("nominal_gap_px") is None
            else _finite(value["nominal_gap_px"], "nominal gap")
        ),
    )


def _sequence_edge(value: Mapping[str, object]):
    from x5crop.detection.photo_geometry.model import (
        BoundaryEvidenceState,
        BoundaryRole,
    )
    from x5crop.detection.photo_geometry.observation_types import (
        BoundaryEdgeObservation,
    )
    from x5crop.domain import ObservationId

    return BoundaryEdgeObservation(
        observation_id=ObservationId(str(value["observation_id"])),
        run_id=str(value["run_id"]),
        coordinate_interval_px=_finite(
            value["coordinate_interval_px"],
            "sequence coordinate",
        ),
        transition_ids=_observation_ids(value["transition_ids"], "transition"),
        trace_coordinates_px=tuple(int(item) for item in value["trace_coordinates_px"]),
        polarity=int(value["polarity"]),
        support_fraction=float(value["support_fraction"]),
        continuous_support_fraction=float(value["continuous_support_fraction"]),
        fit_residual_px=float(value["fit_residual_px"]),
        canonical_direction_degrees=(
            None
            if value.get("canonical_direction_degrees") is None
            else float(value["canonical_direction_degrees"])
        ),
        fit_direction_interval_degrees=(
            None
            if value.get("fit_direction_interval_degrees") is None
            else _finite(value["fit_direction_interval_degrees"], "fit direction")
        ),
        full_direction_interval_degrees=(
            None
            if value.get("full_direction_interval_degrees") is None
            else _finite(value["full_direction_interval_degrees"], "full direction")
        ),
        qualified_anchor_roles=tuple(
            BoundaryRole(str(item)) for item in value["qualified_anchor_roles"]
        ),
        evidence_state=BoundaryEvidenceState(str(value["evidence_state"])),
    )


def _separator_band(value: Mapping[str, object]):
    from x5crop.detection.photo_geometry.model import BoundaryEvidenceState
    from x5crop.detection.photo_geometry.observation_types import (
        SeparatorBandObservation,
        SeparatorMaterialRegionObservation,
    )
    from x5crop.domain import ObservationId

    regions = tuple(
        SeparatorMaterialRegionObservation(
            region_index=int(item["region_index"]),
            sample_count=int(item["sample_count"]),
            darkness_contrast_interval=_finite(
                item["darkness_contrast_interval"],
                "material darkness",
            ),
            texture_contrast_interval=_finite(
                item["texture_contrast_interval"],
                "material texture",
            ),
        )
        for item in value["material_regions"]
    )
    return SeparatorBandObservation(
        observation_id=ObservationId(str(value["observation_id"])),
        left_edge_observation_id=ObservationId(
            str(value["left_edge_observation_id"])
        ),
        right_edge_observation_id=ObservationId(
            str(value["right_edge_observation_id"])
        ),
        left_run_id=str(value["left_run_id"]),
        right_run_id=str(value["right_run_id"]),
        gap_interval_px=_finite(value["gap_interval_px"], "separator gap"),
        transition_ids=_observation_ids(value["transition_ids"], "separator transition"),
        independent_support_region_count=int(
            value["independent_support_region_count"]
        ),
        continuous_support_fraction=float(value["continuous_support_fraction"]),
        darkness_contrast=float(value["darkness_contrast"]),
        darkness_contrast_interval=_finite(
            value["darkness_contrast_interval"],
            "separator darkness",
        ),
        texture_contrast=float(value["texture_contrast"]),
        texture_contrast_interval=_finite(
            value["texture_contrast_interval"],
            "separator texture",
        ),
        material_regions=regions,
        evidence_state=BoundaryEvidenceState(str(value["evidence_state"])),
    )


def _cross_binding(value: Mapping[str, object]):
    from x5crop.detection.photo_geometry.model import BoundaryRole
    from x5crop.detection.photo_geometry.template_cross_model import (
        CrossEvidence,
        CrossRoleBinding,
    )
    from x5crop.domain import ObservationId

    return CrossRoleBinding(
        role=BoundaryRole(str(value["role"])),
        run_id=str(value["run_id"]),
        observation_id=ObservationId(str(value["observation_id"])),
        coordinate_interval_px=_finite(
            value["coordinate_interval_px"],
            "cross coordinate",
        ),
        trace_coordinates_px=tuple(int(item) for item in value["trace_coordinates_px"]),
        support_fraction=float(value["support_fraction"]),
        continuous_support_fraction=float(value["continuous_support_fraction"]),
        fit_residual_px=float(value["fit_residual_px"]),
        fit_interval_px=_finite(value["fit_interval_px"], "cross fit"),
        full_interval_px=_finite(value["full_interval_px"], "cross full"),
        canonical_direction_degrees=(
            None
            if value.get("canonical_direction_degrees") is None
            else float(value["canonical_direction_degrees"])
        ),
        fit_direction_interval_degrees=(
            None
            if value.get("fit_direction_interval_degrees") is None
            else _finite(
                value["fit_direction_interval_degrees"],
                "cross fit direction",
            )
        ),
        full_direction_interval_degrees=(
            None
            if value.get("full_direction_interval_degrees") is None
            else _finite(value["full_direction_interval_degrees"], "cross direction")
        ),
        evidence=CrossEvidence(str(value["evidence"])),
        source_observation_ids=_observation_ids(
            value["source_observation_ids"],
            "cross source",
        ),
        independent_support_region_count=int(
            value["independent_support_region_count"]
        ),
        source_spanning_continuous=bool(value["source_spanning_continuous"]),
        role_authorized=bool(value["role_authorized"]),
    )


def rerun_template_fits(
    replay: TemplateMeasurementReplay,
    plan: object,
) -> TemplateReplayFitResult:
    """Re-run phase and cross fit without touching source pixels."""

    from x5crop.detection.photo_geometry.model import BoundaryAxis, BoundaryRole
    from x5crop.detection.photo_geometry.template_cross import fit_template_cross
    from x5crop.detection.photo_geometry.template_cross_model import (
        TemplateCrossInput,
    )
    from x5crop.detection.photo_geometry.template_measurement_plan_model import (
        TemplateMeasurementPlan,
    )
    from x5crop.detection.photo_geometry.template_phase import (
        fit_template_phase_with_local_advance,
    )
    from x5crop.detection.photo_geometry.template_registration import (
        short_axis_center_authority,
    )

    if not isinstance(plan, TemplateMeasurementPlan):
        raise TypeError("template replay requires a current compiled plan")
    expected = {
        "physical_identity": plan.physical_identity,
        "plan_identity": plan.plan_identity,
        "template_id": str(replay.fitted_template_spec.get("template_id")),
    }
    _expected_identity(
        replay,
        source_sha256=None,
        config_identity=None,
        measurement_revision=None,
        template_plan_identity=expected,
    )
    spec = _template_spec(replay.fitted_template_spec)
    edges = tuple(_sequence_edge(item) for item in replay.sequence_edges)
    bands = tuple(_separator_band(item) for item in replay.separator_bands)
    bindings = tuple(_cross_binding(item) for item in replay.cross_bindings)
    long_authority = plan.projected_queries.sequence_ownership_interval_px
    box = plan.lane_authority.work_box
    short_authority = (
        _finite({"minimum": float(box.top), "maximum": float(box.bottom)}, "short")
        if plan.layout == "horizontal"
        else _finite({"minimum": float(box.left), "maximum": float(box.right)}, "short")
    )
    phase = fit_template_phase_with_local_advance(
        edges,
        bands,
        spec,
        scale_px_per_mm=plan.scale_authority.width_axis_px_per_mm,
        holder_span_px=long_authority,
    )
    top = tuple(item for item in bindings if item.role == BoundaryRole.TOP)
    bottom = tuple(item for item in bindings if item.role == BoundaryRole.BOTTOM)
    cross = fit_template_cross(
        TemplateCrossInput(
            template=spec,
            fixed_height_px=spec.frame_height_px,
            holder_short_axis_center_px=short_axis_center_authority(
                short_authority,
                plan.scale_authority.height_axis_px_per_mm,
            ),
            lane_reference_trace_px=long_authority.center,
            top_bindings=top,
            bottom_bindings=bottom,
            registered_trace_coordinates_px=(
                plan.projected_queries.cross_trace_positions_px
            ),
            boundary_axis=(
                BoundaryAxis.Y
                if plan.layout == "horizontal"
                else BoundaryAxis.X
            ),
            maximum_registered_runs=plan.cross_bounds.max_registered_runs,
            maximum_fitted_observations=plan.cross_bounds.max_fitted_observations,
            maximum_compatible_pairs=plan.cross_bounds.max_compatible_pairs,
            maximum_evaluated_fits=plan.cross_bounds.max_evaluated_fits,
        )
    )
    return TemplateReplayFitResult(phase=phase, cross=cross)


def validate_replay(replay: TemplateMeasurementReplay) -> TemplateMeasurementReplay:
    if not isinstance(replay, TemplateMeasurementReplay):
        raise TypeError("expected TemplateMeasurementReplay")
    return replay


def dump_jsonl(replay: TemplateMeasurementReplay) -> str:
    """Return one stable, newline-terminated canonical JSON record."""
    record = validate_replay(replay).as_record()
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _expected_identity(
    replay: TemplateMeasurementReplay,
    *,
    source_sha256: str | None,
    config_identity: Mapping[str, object] | None,
    measurement_revision: str | None,
    template_plan_identity: Mapping[str, object] | None,
) -> None:
    if source_sha256 is not None and replay.source_sha256 != source_sha256:
        raise ValueError("replay source SHA does not match expected identity")
    if config_identity is not None and replay.config_identity != _identity(config_identity, "config_identity"):
        raise ValueError("replay configuration identity does not match")
    if measurement_revision is not None and replay.measurement_revision != measurement_revision:
        raise ValueError("replay measurement revision does not match")
    if template_plan_identity is not None and replay.template_plan_identity != _identity(template_plan_identity, "template_plan_identity"):
        raise ValueError("replay template plan identity does not match")


def load_jsonl(
    payload: str,
    *,
    source_sha256: str | None = None,
    config_identity: Mapping[str, object] | None = None,
    measurement_revision: str | None = None,
    template_plan_identity: Mapping[str, object] | None = None,
) -> TemplateMeasurementReplay:
    if not isinstance(payload, str):
        raise TypeError("replay JSONL payload must be text")
    lines = tuple(line for line in payload.splitlines() if line.strip())
    if len(lines) != 1:
        raise ValueError("replay JSONL must contain exactly one record")
    try:
        record = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        raise ValueError("replay JSONL is not valid JSON") from exc
    if not isinstance(record, dict) or record.get("record_schema") != REPLAY_RECORD_SCHEMA:
        raise ValueError("replay record schema is not current")
    required = {
        "record_schema", "source_sha256", "config_identity", "measurement_revision",
        "template_plan_identity", "fitted_template_spec",
        "registered_query_receipts", "sequence_edges", "separator_bands",
        "cross_bindings", "content_occupancy_summary",
    }
    if set(record) != required:
        raise ValueError("replay record fields are not canonical")
    replay = TemplateMeasurementReplay(
        source_sha256=record["source_sha256"],
        config_identity=record["config_identity"],
        measurement_revision=record["measurement_revision"],
        template_plan_identity=record["template_plan_identity"],
        fitted_template_spec=record["fitted_template_spec"],
        registered_query_receipts=record["registered_query_receipts"],
        sequence_edges=record["sequence_edges"],
        separator_bands=record["separator_bands"],
        cross_bindings=record["cross_bindings"],
        content_occupancy_summary=record["content_occupancy_summary"],
    )
    _expected_identity(
        replay,
        source_sha256=source_sha256,
        config_identity=config_identity,
        measurement_revision=measurement_revision,
        template_plan_identity=template_plan_identity,
    )
    canonical = dump_jsonl(replay)
    if (payload.endswith("\n") and canonical != payload) or (
        not payload.endswith("\n") and canonical.rstrip("\n") != payload
    ):
        raise ValueError("replay JSONL is not canonical serialization")
    return replay


def dump_file(replay: TemplateMeasurementReplay, path: Path) -> None:
    Path(path).write_text(dump_jsonl(replay), encoding="utf-8", newline="\n")


def load_file(path: Path, **expected: object) -> TemplateMeasurementReplay:
    return load_jsonl(Path(path).read_text(encoding="utf-8"), **expected)


def _inspect(replay: TemplateMeasurementReplay) -> dict[str, object]:
    return {
        "record_schema": REPLAY_RECORD_SCHEMA,
        "source_sha256": replay.source_sha256,
        "measurement_revision": replay.measurement_revision,
        "template_plan_identity": _json_value(replay.template_plan_identity),
        "counts": {
            "registered_query_receipts": len(replay.registered_query_receipts),
            "sequence_edges": len(replay.sequence_edges),
            "separator_bands": len(replay.separator_bands),
            "cross_bindings": len(replay.cross_bindings),
            "content_occupancy_summary": len(replay.content_occupancy_summary),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="validate or inspect template measurement replay JSONL")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("validate", "inspect"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("path", type=Path)
    args = parser.parse_args(argv)
    replay = load_file(args.path)
    if args.command == "inspect":
        print(json.dumps(_inspect(replay), ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    else:
        print("valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
