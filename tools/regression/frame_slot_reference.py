"""Validate resolved frame slots against manual boundary intervals."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
from typing import Any, Iterable

from x5crop.domain import PixelInterval
from x5crop.report.validation import validate_current_report_record


REFERENCE_SCHEMA_ID = "frame_slot_reference"
REFERENCE_SCHEMA_REVISION = "acceptable_sequence_intervals"


@dataclass(frozen=True)
class FrameSlotIntervalReference:
    index: int
    leading: PixelInterval
    trailing: PixelInterval

    def __post_init__(self) -> None:
        if self.index <= 0:
            raise ValueError("frame-slot reference index must be positive")
        if self.trailing.minimum <= self.leading.maximum:
            raise ValueError("frame-slot reference must admit positive width")


@dataclass(frozen=True)
class SharedShortAxisReference:
    top: PixelInterval
    bottom: PixelInterval

    def __post_init__(self) -> None:
        if self.bottom.minimum <= self.top.maximum:
            raise ValueError("shared short-axis reference must admit positive height")


@dataclass(frozen=True)
class FrameSlotReference:
    source: str
    format_id: str
    strip_mode: str
    layout: str
    shared_short_axis: SharedShortAxisReference
    frame_slots: tuple[FrameSlotIntervalReference, ...]
    notes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.source:
            raise ValueError("frame-slot reference requires a source")
        indexes = tuple(item.index for item in self.frame_slots)
        if not indexes or indexes != tuple(range(1, len(indexes) + 1)):
            raise ValueError("frame-slot references require consecutive indexes")


class ReferenceValidationOutcome(str, Enum):
    MATCHED = "matched"
    UNRESOLVED = "unresolved"
    VIOLATED = "violated"


@dataclass(frozen=True)
class ReferenceValidationResult:
    source: str
    outcome: ReferenceValidationOutcome
    violations: tuple[str, ...]


def _interval_from_record(value: Any) -> PixelInterval:
    if not isinstance(value, dict) or set(value) != {"minimum", "maximum"}:
        raise ValueError("reference interval requires minimum and maximum")
    bounds = (value["minimum"], value["maximum"])
    if any(
        isinstance(item, bool) or not isinstance(item, (int, float))
        for item in bounds
    ):
        raise ValueError("reference interval values must be numbers")
    return PixelInterval(float(bounds[0]), float(bounds[1]))


def frame_slot_reference_from_record(record: dict[str, Any]) -> FrameSlotReference:
    required = {
        "schema_id",
        "schema_revision",
        "source",
        "format_id",
        "strip_mode",
        "layout",
        "shared_short_axis",
        "frame_slots",
        "notes",
    }
    if record.get("schema_id") != REFERENCE_SCHEMA_ID:
        raise ValueError("frame-slot reference schema id mismatch")
    if record.get("schema_revision") != REFERENCE_SCHEMA_REVISION:
        raise ValueError("frame-slot reference schema revision mismatch")
    if set(record) != required:
        raise ValueError("frame-slot reference fields are incomplete")
    identity_values = tuple(
        record[field] for field in ("source", "format_id", "strip_mode", "layout")
    )
    if any(not isinstance(value, str) or not value for value in identity_values):
        raise ValueError("frame-slot reference identities must be strings")
    short_axis = record["shared_short_axis"]
    frame_slots = record["frame_slots"]
    notes = record["notes"]
    if not isinstance(short_axis, dict) or set(short_axis) != {"top", "bottom"}:
        raise ValueError("shared short-axis reference fields are invalid")
    if not isinstance(frame_slots, list) or not isinstance(notes, list):
        raise ValueError("frame-slot reference collections must be lists")
    if any(not isinstance(note, str) for note in notes):
        raise ValueError("frame-slot reference notes must be strings")
    slot_fields = {"index", "leading", "trailing"}
    for slot in frame_slots:
        if not isinstance(slot, dict) or set(slot) != slot_fields:
            raise ValueError("frame-slot reference slot fields are invalid")
        if isinstance(slot["index"], bool) or not isinstance(slot["index"], int):
            raise ValueError("frame-slot reference index must be an integer")
    return FrameSlotReference(
        source=record["source"],
        format_id=record["format_id"],
        strip_mode=record["strip_mode"],
        layout=record["layout"],
        shared_short_axis=SharedShortAxisReference(
            top=_interval_from_record(short_axis["top"]),
            bottom=_interval_from_record(short_axis["bottom"]),
        ),
        frame_slots=tuple(
            FrameSlotIntervalReference(
                index=slot["index"],
                leading=_interval_from_record(slot["leading"]),
                trailing=_interval_from_record(slot["trailing"]),
            )
            for slot in frame_slots
        ),
        notes=tuple(notes),
    )


def load_frame_slot_references(path: Path) -> tuple[FrameSlotReference, ...]:
    references: list[FrameSlotReference] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if stripped := line.strip():
                references.append(frame_slot_reference_from_record(json.loads(stripped)))
    sources = tuple(reference.source for reference in references)
    if len(sources) != len(set(sources)):
        raise ValueError("frame-slot reference sources must be unique")
    return tuple(references)


def _selected_geometry(report: dict[str, Any]) -> dict[str, Any]:
    selection = report["selection"]
    selected_index = int(selection["selected_rank"]) - 1
    candidates = selection["candidates"]
    if selected_index < 0 or selected_index >= len(candidates):
        raise ValueError("selected candidate rank is outside the candidate table")
    candidate = candidates[selected_index]
    if candidate["geometry_kind"] != "sequence":
        raise ValueError("frame-slot reference requires sequence geometry")
    return candidate["provisional_geometry"]


def _interval_inside(actual: PixelInterval, accepted: PixelInterval) -> bool:
    return bool(
        actual.minimum >= accepted.minimum
        and actual.maximum <= accepted.maximum
    )


def compare_report_to_reference(
    report: dict[str, Any],
    reference: FrameSlotReference,
) -> ReferenceValidationResult:
    validate_current_report_record(report)
    if report["source"] != reference.source:
        raise ValueError("report and frame-slot reference sources differ")
    if report["selection"]["geometry_resolution"]["state"] != "supported":
        return ReferenceValidationResult(
            reference.source,
            ReferenceValidationOutcome.UNRESOLVED,
            (),
        )
    geometry = _selected_geometry(report)
    identity = (
        geometry["format_id"],
        geometry["strip_mode"],
        geometry["layout"],
    )
    if identity != (reference.format_id, reference.strip_mode, reference.layout):
        raise ValueError("report and frame-slot reference identities differ")
    violations: list[str] = []
    actual_short_axis = geometry["shared_short_axis"]
    for side in ("top", "bottom"):
        actual = _interval_from_record(actual_short_axis[side])
        accepted = getattr(reference.shared_short_axis, side)
        if not _interval_inside(actual, accepted):
            violations.append(f"shared_short_axis:{side}:outside_reference")
    actual_slots = geometry["frame_slots"]
    if len(actual_slots) != len(reference.frame_slots):
        violations.append("frame_count_outside_reference")
    for actual, accepted in zip(actual_slots, reference.frame_slots, strict=False):
        if int(actual["index"]) != accepted.index:
            violations.append(f"frame:{accepted.index}:index_mismatch")
            continue
        for side in ("leading", "trailing"):
            actual_interval = _interval_from_record(actual[side]["position"])
            if not _interval_inside(actual_interval, getattr(accepted, side)):
                violations.append(f"frame:{accepted.index}:{side}:outside_reference")
    return ReferenceValidationResult(
        reference.source,
        (
            ReferenceValidationOutcome.VIOLATED
            if violations
            else ReferenceValidationOutcome.MATCHED
        ),
        tuple(violations),
    )


def _load_report_rows(paths: Iterable[Path]) -> dict[str, dict[str, Any]]:
    reports: dict[str, dict[str, Any]] = {}
    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not (stripped := line.strip()):
                    continue
                report = json.loads(stripped)
                validate_current_report_record(report)
                source = str(report["source"])
                if source in reports:
                    raise ValueError(f"duplicate report source: {source}")
                reports[source] = report
    return reports


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate resolved frame slots against manual intervals."
    )
    parser.add_argument("reference", type=Path)
    parser.add_argument("reports", nargs="+", type=Path)
    args = parser.parse_args(argv)
    references = load_frame_slot_references(args.reference)
    reports = _load_report_rows(args.reports)
    results: list[ReferenceValidationResult] = []
    for reference in references:
        report = reports.get(reference.source)
        if report is None:
            raise ValueError(f"missing report for reference: {reference.source}")
        results.append(compare_report_to_reference(report, reference))
    for result in results:
        print(f"{result.outcome.value}: {result.source}")
        for violation in result.violations:
            print(f"  {violation}")
    matched = sum(result.outcome == ReferenceValidationOutcome.MATCHED for result in results)
    unresolved = sum(
        result.outcome == ReferenceValidationOutcome.UNRESOLVED for result in results
    )
    violated = sum(
        result.outcome == ReferenceValidationOutcome.VIOLATED for result in results
    )
    print(f"matched={matched} unresolved={unresolved} violated={violated}")
    return 1 if violated else 0


if __name__ == "__main__":
    raise SystemExit(main())
