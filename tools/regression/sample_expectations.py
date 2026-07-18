"""Validate local sample labels, roles, and manual frame-slot references."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
from typing import Any, Iterable, TypeVar

from tools.regression.frame_slot_reference import (
    FrameSlotReference,
    load_frame_slot_references,
)
from x5crop.formats import FORMATS
from x5crop.strip_modes import FULL, PARTIAL


EXPECTATION_SCHEMA_ID = "sample_expectation"
EXPECTATION_SCHEMA_REVISION = "frame_slot_sequence_resolution"


class DecisionExpectation(str, Enum):
    PASS_REQUIRED = "pass_required"
    REVIEW_REQUIRED = "review_required"
    PASS_PREFERRED = "pass_preferred"


class SampleScenario(str, Enum):
    STANDARD = "standard"
    UNDEREXPOSED_HUMAN_AMBIGUOUS = "underexposed_human_ambiguous"
    UNDEREXPOSED_HUMAN_DISTINGUISHABLE = (
        "underexposed_human_distinguishable"
    )
    UNUSUAL_COUNT_OR_PLACEMENT = "unusual_count_or_placement"
    BLANK_FRAME_SLOT = "blank_frame_slot"
    HOLDER_CLIPPING = "holder_clipping"
    HOLDER_UNDERFILLED = "holder_underfilled"
    CONTACT = "contact"
    OVERLAP = "overlap"
    MIXED_BOUNDARY = "mixed_boundary"


class DatasetRole(str, Enum):
    CALIBRATION = "calibration"
    VALIDATION = "validation"


_EXPECTATION_BY_PREFIX = {
    "pass": DecisionExpectation.PASS_REQUIRED,
    "review": DecisionExpectation.REVIEW_REQUIRED,
    "unknown": DecisionExpectation.PASS_PREFERRED,
}

_EnumType = TypeVar("_EnumType", bound=Enum)


@dataclass(frozen=True)
class SampleExpectation:
    source: str
    format_id: str
    strip_mode: str
    requested_count: int | str | None
    decision_expectation: DecisionExpectation
    scenario: SampleScenario
    dataset_role: DatasetRole
    expected_count: int | None
    geometry_reference: str | None
    review_basis: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.source:
            raise ValueError("sample expectation requires a source")
        prefix = Path(self.source).name.partition("_")[0]
        expected_decision = _EXPECTATION_BY_PREFIX.get(prefix)
        if expected_decision is None:
            raise ValueError("sample filename requires pass, review, or unknown prefix")
        if self.decision_expectation != expected_decision:
            raise ValueError("sample filename prefix and decision expectation differ")
        if self.format_id not in FORMATS:
            raise ValueError("sample expectation format is unknown")
        if self.strip_mode not in {FULL, PARTIAL}:
            raise ValueError("sample expectation strip mode is unknown")
        if isinstance(self.requested_count, bool) or not (
            self.requested_count is None
            or self.requested_count == "auto"
            or isinstance(self.requested_count, int)
            and self.requested_count > 0
        ):
            raise ValueError("requested count must be null, auto, or positive")
        if isinstance(self.expected_count, bool) or (
            self.expected_count is not None
            and (not isinstance(self.expected_count, int) or self.expected_count <= 0)
        ):
            raise ValueError("expected count must be null or positive")
        if any(not item for item in self.review_basis):
            raise ValueError("review basis entries must not be empty")
        if self.decision_expectation == DecisionExpectation.REVIEW_REQUIRED:
            if not self.review_basis:
                raise ValueError("review-required sample needs a physical review basis")
            if self.dataset_role != DatasetRole.VALIDATION:
                raise ValueError("review-required sample must be validation-only")
        elif self.geometry_reference != self.source:
            raise ValueError("pass and unknown samples require their own geometry reference")
        if (
            self.decision_expectation == DecisionExpectation.PASS_PREFERRED
            and self.dataset_role != DatasetRole.VALIDATION
        ):
            raise ValueError("pass-preferred sample must be validation-only")


def _typed_enum(
    enum_type: type[_EnumType],
    value: Any,
    field: str,
) -> _EnumType:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    try:
        return enum_type(value)
    except ValueError as error:
        raise ValueError(f"{field} is unknown") from error


def sample_expectation_from_record(record: dict[str, Any]) -> SampleExpectation:
    required = {
        "schema_id",
        "schema_revision",
        "source",
        "format_id",
        "strip_mode",
        "requested_count",
        "decision_expectation",
        "scenario",
        "dataset_role",
        "expected_count",
        "geometry_reference",
        "review_basis",
    }
    if record.get("schema_id") != EXPECTATION_SCHEMA_ID:
        raise ValueError("sample expectation schema id mismatch")
    if record.get("schema_revision") != EXPECTATION_SCHEMA_REVISION:
        raise ValueError("sample expectation schema revision mismatch")
    if set(record) != required:
        raise ValueError("sample expectation fields are incomplete")
    if any(
        not isinstance(record[field], str) or not record[field]
        for field in ("source", "format_id", "strip_mode")
    ):
        raise ValueError("sample expectation identities must be strings")
    geometry_reference = record["geometry_reference"]
    if geometry_reference is not None and (
        not isinstance(geometry_reference, str) or not geometry_reference
    ):
        raise ValueError("geometry reference must be null or a source identity")
    review_basis = record["review_basis"]
    if not isinstance(review_basis, list) or any(
        not isinstance(item, str) for item in review_basis
    ):
        raise ValueError("review basis must be a list of strings")
    return SampleExpectation(
        source=record["source"],
        format_id=record["format_id"],
        strip_mode=record["strip_mode"],
        requested_count=record["requested_count"],
        decision_expectation=_typed_enum(
            DecisionExpectation,
            record["decision_expectation"],
            "decision expectation",
        ),
        scenario=_typed_enum(SampleScenario, record["scenario"], "scenario"),
        dataset_role=_typed_enum(
            DatasetRole,
            record["dataset_role"],
            "dataset role",
        ),
        expected_count=record["expected_count"],
        geometry_reference=geometry_reference,
        review_basis=tuple(review_basis),
    )


def load_sample_expectations(path: Path) -> tuple[SampleExpectation, ...]:
    expectations: list[SampleExpectation] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if stripped := line.strip():
                expectations.append(
                    sample_expectation_from_record(json.loads(stripped))
                )
    sources = tuple(expectation.source for expectation in expectations)
    if len(sources) != len(set(sources)):
        raise ValueError("sample expectation sources must be unique")
    return tuple(expectations)


def validate_sample_dataset(
    expectations: tuple[SampleExpectation, ...],
    references: tuple[FrameSlotReference, ...],
    sample_paths: Iterable[Path],
) -> None:
    expectation_by_source = {
        expectation.source: expectation for expectation in expectations
    }
    if len(expectation_by_source) != len(expectations):
        raise ValueError("sample expectation sources must be unique")
    sample_sources = tuple(path.as_posix() for path in sample_paths)
    if len(sample_sources) != len(set(sample_sources)):
        raise ValueError("sample file sources must be unique")
    if set(sample_sources) != set(expectation_by_source):
        raise ValueError("sample files and expectations must match exactly")

    reference_by_source = {reference.source: reference for reference in references}
    if len(reference_by_source) != len(references):
        raise ValueError("frame-slot reference sources must be unique")
    required_references = {
        expectation.geometry_reference
        for expectation in expectations
        if expectation.geometry_reference is not None
    }
    if set(reference_by_source) != required_references:
        raise ValueError("manual references must match required sample geometry exactly")
    for source, reference in reference_by_source.items():
        expectation = expectation_by_source[source]
        if (reference.format_id, reference.strip_mode) != (
            expectation.format_id,
            expectation.strip_mode,
        ):
            raise ValueError("sample expectation and geometry reference identity differ")
        if (
            expectation.expected_count is not None
            and len(reference.frame_slots) != expectation.expected_count
        ):
            raise ValueError("expected count and geometry reference count differ")


def _sample_paths(root: Path) -> tuple[Path, ...]:
    return tuple(
        sorted(
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in {".tif", ".tiff"}
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate sample expectations and manual frame-slot references."
    )
    parser.add_argument("expectations", type=Path)
    parser.add_argument("references", type=Path)
    parser.add_argument("sample_root", type=Path)
    args = parser.parse_args(argv)

    expectations = load_sample_expectations(args.expectations)
    references = load_frame_slot_references(args.references)
    validate_sample_dataset(expectations, references, _sample_paths(args.sample_root))
    print(
        f"samples={len(expectations)} references={len(references)} "
        "expectations=valid"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
