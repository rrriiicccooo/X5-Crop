"""Validate resolved photo apertures against manual boundary intervals."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
from typing import Any, Iterable

from x5crop.domain import PixelInterval
from x5crop.report.validation import validate_current_report_record


REFERENCE_SCHEMA_ID = "photo_aperture_reference"
REFERENCE_SCHEMA_REVISION = "acceptable_boundary_intervals"
BOUNDARY_SIDES = ("leading", "trailing", "top", "bottom")


@dataclass(frozen=True)
class PhotoApertureIntervalReference:
    index: int
    leading: PixelInterval
    trailing: PixelInterval
    top: PixelInterval
    bottom: PixelInterval

    def __post_init__(self) -> None:
        if self.index <= 0:
            raise ValueError("photo aperture reference index must be positive")

    def interval_for(self, side: str) -> PixelInterval:
        if side not in BOUNDARY_SIDES:
            raise ValueError(f"unsupported photo aperture side: {side}")
        return getattr(self, side)


@dataclass(frozen=True)
class PhotoApertureReference:
    source: str
    format_id: str
    strip_mode: str
    layout: str
    apertures: tuple[PhotoApertureIntervalReference, ...]
    notes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.source:
            raise ValueError("photo aperture reference requires a source")
        indexes = tuple(item.index for item in self.apertures)
        if not indexes or indexes != tuple(range(1, len(indexes) + 1)):
            raise ValueError("photo aperture references must use consecutive indexes")


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
        raise ValueError("reference boundary requires minimum and maximum")
    return PixelInterval(float(value["minimum"]), float(value["maximum"]))


def photo_aperture_reference_from_record(record: dict[str, Any]) -> PhotoApertureReference:
    if record.get("schema_id") != REFERENCE_SCHEMA_ID:
        raise ValueError("photo aperture reference schema id mismatch")
    if record.get("schema_revision") != REFERENCE_SCHEMA_REVISION:
        raise ValueError("photo aperture reference schema revision mismatch")
    required = {
        "schema_id",
        "schema_revision",
        "source",
        "format_id",
        "strip_mode",
        "layout",
        "apertures",
        "notes",
    }
    if set(record) != required:
        raise ValueError("photo aperture reference fields are incomplete")
    apertures = record["apertures"]
    notes = record["notes"]
    if not isinstance(apertures, list) or not isinstance(notes, list):
        raise ValueError("photo aperture reference collections must be lists")
    return PhotoApertureReference(
        source=str(record["source"]),
        format_id=str(record["format_id"]),
        strip_mode=str(record["strip_mode"]),
        layout=str(record["layout"]),
        apertures=tuple(
            PhotoApertureIntervalReference(
                index=int(aperture["index"]),
                **{
                    side: _interval_from_record(aperture[side])
                    for side in BOUNDARY_SIDES
                },
            )
            for aperture in apertures
        ),
        notes=tuple(str(note) for note in notes),
    )


def load_photo_aperture_references(path: Path) -> tuple[PhotoApertureReference, ...]:
    references: list[PhotoApertureReference] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                references.append(
                    photo_aperture_reference_from_record(json.loads(line))
                )
    sources = tuple(reference.source for reference in references)
    if len(sources) != len(set(sources)):
        raise ValueError("photo aperture reference sources must be unique")
    return tuple(references)


def _selected_geometry(report: dict[str, Any]) -> dict[str, Any]:
    selection = report["selection"]
    selected_index = int(selection["selected_rank"]) - 1
    candidates = selection["candidates"]
    if selected_index < 0 or selected_index >= len(candidates):
        raise ValueError("selected candidate rank is outside the candidate table")
    candidate = candidates[selected_index]
    if candidate["geometry_kind"] != "sequence":
        raise ValueError("photo aperture reference requires sequence geometry")
    return candidate["provisional_geometry"]


def _interval_inside(actual: PixelInterval, accepted: PixelInterval) -> bool:
    return bool(
        actual.minimum >= accepted.minimum
        and actual.maximum <= accepted.maximum
    )


def compare_report_to_reference(
    report: dict[str, Any],
    reference: PhotoApertureReference,
) -> ReferenceValidationResult:
    validate_current_report_record(report)
    if report["source"] != reference.source:
        raise ValueError("report and photo aperture reference sources differ")
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
    if identity != (
        reference.format_id,
        reference.strip_mode,
        reference.layout,
    ):
        raise ValueError("report and photo aperture reference identities differ")
    actual_apertures = geometry["photo_apertures"]
    violations: list[str] = []
    if len(actual_apertures) != len(reference.apertures):
        violations.append("photo_count_outside_reference")
    for actual, accepted in zip(
        actual_apertures,
        reference.apertures,
        strict=False,
    ):
        if int(actual["index"]) != accepted.index:
            violations.append(f"photo:{accepted.index}:index_mismatch")
            continue
        for side in BOUNDARY_SIDES:
            actual_interval = _interval_from_record(actual[side]["position"])
            if not _interval_inside(actual_interval, accepted.interval_for(side)):
                violations.append(
                    f"photo:{accepted.index}:{side}:outside_reference"
                )
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
                line = line.strip()
                if not line:
                    continue
                report = json.loads(line)
                validate_current_report_record(report)
                source = str(report["source"])
                if source in reports:
                    raise ValueError(f"duplicate report source: {source}")
                reports[source] = report
    return reports


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate resolved photo apertures against manual intervals."
    )
    parser.add_argument("reference", type=Path)
    parser.add_argument("reports", nargs="+", type=Path)
    args = parser.parse_args(argv)
    references = load_photo_aperture_references(args.reference)
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
