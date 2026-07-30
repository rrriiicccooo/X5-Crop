"""Run the fixed production TIFF throughput cohort."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import statistics
import subprocess
import sys
import tempfile
import time
from typing import Any, Sequence

from x5crop.app_info import RUN_MANIFEST_JSONL_NAME, TIFF_SUFFIXES
from x5crop.configuration.registry import get_detection_configuration
from x5crop.detection.evidence.scan_canvas import (
    ScanCanvasOutcome,
    observe_scan_canvas,
)
from x5crop.formats import FORMAT_CHOICES, format_spec
from x5crop.geometry.layout import infer_layout
from x5crop.io.tiff import read_tiff_page_shape, read_tiff_profile
from x5crop.runtime.manifest import RUN_MANIFEST_SCHEMA
from x5crop.strip_modes import STRIP_MODES


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COHORT = Path(__file__).with_name("cohorts") / "production_performance.jsonl"
PERFORMANCE_RESULT_SCHEMA = "x5crop_production_performance_v4"
COHORT_FIELDS = (
    "sample_id",
    "source_sha256",
    "format_id",
    "strip_mode",
    "compression",
)
MEASURED_RUN_COUNT = 3
PRODUCTION_JOBS = 2
SECONDS_PER_INPUT_LIMIT = 5.0
FIXED_INPUT_COUNT = 24
CURRENT_OUTPUT_TIFF_RECEIPT = 168
CURRENT_PARTIAL_EXTRA_SLOT_RECEIPT = 25
COUNT_ANNOTATION = re.compile(r"_X5_(\d+)_")
FORMAT_DIRECTORY_TO_ID = {
    "66": "120-66",
    "67": "120-67",
}


@dataclass(frozen=True)
class PerformanceCohortEntry:
    sample_id: str
    source_sha256: str
    format_id: str
    strip_mode: str
    compression: str

    def __post_init__(self) -> None:
        if not self.sample_id:
            raise ValueError("performance sample_id must not be empty")
        digest = self.source_sha256.lower()
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError(
                f"performance source_sha256 is invalid for {self.sample_id}"
            )
        if self.format_id not in FORMAT_CHOICES:
            raise ValueError(
                f"performance format_id is invalid for {self.sample_id}: "
                f"{self.format_id}"
            )
        if self.strip_mode not in STRIP_MODES:
            raise ValueError(
                f"performance strip_mode is invalid for {self.sample_id}: "
                f"{self.strip_mode}"
            )
        if not self.compression or self.compression != self.compression.upper():
            raise ValueError(
                f"performance compression must be an uppercase TIFF name for "
                f"{self.sample_id}"
            )


@dataclass(frozen=True)
class LocalSampleIdentity:
    sample_id: str
    source_sha256: str
    format_id: str
    strip_mode: str
    source_relative_path: str


@dataclass(frozen=True)
class ResolvedPerformanceSource:
    cohort: PerformanceCohortEntry
    path: Path
    layout: str
    selected_scan_canvas_profile_id: str
    lane_output_slot_counts: tuple[int, ...]
    slot_identities: tuple[dict[str, int | str], ...]
    validation_annotation: int

    @property
    def output_slot_count(self) -> int:
        return sum(self.lane_output_slot_counts)

    @property
    def partial_extra_slot_count(self) -> int:
        if self.cohort.strip_mode != "partial":
            return 0
        return self.output_slot_count - self.validation_annotation


@dataclass(frozen=True, order=True)
class PerformanceRunGroup:
    format_id: str
    strip_mode: str
    layout: str

    @property
    def count_mode(self) -> str:
        return "fixed_full" if self.strip_mode == "full" else "auto"

    @property
    def directory_name(self) -> str:
        return f"{self.format_id}_{self.strip_mode}_{self.layout}"


@dataclass(frozen=True)
class PerformanceTiming:
    label: str
    wall_seconds: float
    input_count: int
    completed_inputs: int
    approved_inputs_with_outputs: int
    frame_output_count: int
    expected_frame_output_count: int

    @property
    def seconds_per_input(self) -> float:
        return self.wall_seconds / self.input_count

    def as_record(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "wall_seconds": self.wall_seconds,
            "input_count": self.input_count,
            "completed_inputs": self.completed_inputs,
            "approved_inputs_with_outputs": self.approved_inputs_with_outputs,
            "frame_output_count": self.frame_output_count,
            "expected_frame_output_count": self.expected_frame_output_count,
            "seconds_per_input": self.seconds_per_input,
        }


@dataclass(frozen=True)
class ProductionPerformanceResult:
    cold: PerformanceTiming
    measured: tuple[PerformanceTiming, ...]
    output_root: Path
    groups: tuple[PerformanceRunGroup, ...]
    expected_frame_output_count: int
    partial_extra_slot_count: int

    def __post_init__(self) -> None:
        if len(self.measured) != MEASURED_RUN_COUNT:
            raise ValueError(
                f"production performance requires {MEASURED_RUN_COUNT} measured runs"
            )
        input_counts = {self.cold.input_count}
        input_counts.update(timing.input_count for timing in self.measured)
        if len(input_counts) != 1:
            raise ValueError("performance runs must use one fixed input count")
        if input_counts != {FIXED_INPUT_COUNT}:
            raise ValueError(
                f"production performance requires exactly {FIXED_INPUT_COUNT} inputs"
            )
        if not self.groups:
            raise ValueError("production performance requires resolved run groups")
        if self.expected_frame_output_count != CURRENT_OUTPUT_TIFF_RECEIPT:
            raise ValueError(
                "current performance cohort/catalog receipt changed: "
                f"expected {CURRENT_OUTPUT_TIFF_RECEIPT} outputs, resolved "
                f"{self.expected_frame_output_count}"
            )
        if self.partial_extra_slot_count != CURRENT_PARTIAL_EXTRA_SLOT_RECEIPT:
            raise ValueError(
                "current partial annotation receipt changed: "
                f"expected +{CURRENT_PARTIAL_EXTRA_SLOT_RECEIPT}, resolved "
                f"+{self.partial_extra_slot_count}"
            )

    @property
    def median_seconds_per_input(self) -> float:
        return statistics.median(
            timing.seconds_per_input for timing in self.measured
        )

    @property
    def passed(self) -> bool:
        return (
            self.median_seconds_per_input <= SECONDS_PER_INPUT_LIMIT
            and all(
                timing.completed_inputs == FIXED_INPUT_COUNT
                and timing.approved_inputs_with_outputs == FIXED_INPUT_COUNT
                and timing.frame_output_count
                == timing.expected_frame_output_count
                == self.expected_frame_output_count
                for timing in (self.cold, *self.measured)
            )
        )

    @property
    def certification_status(self) -> str:
        return "certified" if self.passed else "failed"

    def as_record(self) -> dict[str, Any]:
        return {
            "schema": PERFORMANCE_RESULT_SCHEMA,
            "jobs": PRODUCTION_JOBS,
            "compression": "same",
            "mode": "real_tiff_write_and_readback",
            "input_count": FIXED_INPUT_COUNT,
            "run_topology": [
                "cold",
                "measured-1",
                "measured-2",
                "measured-3",
            ],
            "count_modes": {
                "full": "fixed_full",
                "partial": "auto",
            },
            "expected_frame_output_count": self.expected_frame_output_count,
            "partial_extra_slot_count": self.partial_extra_slot_count,
            "current_receipt": {
                "frame_output_count": CURRENT_OUTPUT_TIFF_RECEIPT,
                "partial_extra_slot_count": (
                    CURRENT_PARTIAL_EXTRA_SLOT_RECEIPT
                ),
            },
            "groups": [
                {
                    "format_id": group.format_id,
                    "strip_mode": group.strip_mode,
                    "layout": group.layout,
                    "count_mode": group.count_mode,
                }
                for group in self.groups
            ],
            "seconds_per_input_limit": SECONDS_PER_INPUT_LIMIT,
            "cold": self.cold.as_record(),
            "measured": [timing.as_record() for timing in self.measured],
            "median_seconds_per_input": self.median_seconds_per_input,
            "certification_status": self.certification_status,
            "passed": self.passed,
        }


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            value = json.loads(stripped)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number} must be a JSON object")
            rows.append(value)
    return rows


def load_performance_cohort(path: Path) -> tuple[PerformanceCohortEntry, ...]:
    entries: list[PerformanceCohortEntry] = []
    for line_number, row in enumerate(_load_jsonl(path), start=1):
        if tuple(row) != COHORT_FIELDS:
            raise ValueError(
                f"{path}:{line_number} must contain exactly "
                f"{', '.join(COHORT_FIELDS)} in canonical order"
            )
        entries.append(
            PerformanceCohortEntry(
                sample_id=str(row["sample_id"]),
                source_sha256=str(row["source_sha256"]).lower(),
                format_id=str(row["format_id"]),
                strip_mode=str(row["strip_mode"]),
                compression=str(row["compression"]),
            )
        )
    if not entries:
        raise ValueError("performance cohort must not be empty")
    sample_ids = tuple(entry.sample_id for entry in entries)
    digests = tuple(entry.source_sha256 for entry in entries)
    if len(sample_ids) != len(set(sample_ids)):
        raise ValueError("performance cohort sample_id values must be unique")
    if len(digests) != len(set(digests)):
        raise ValueError("performance cohort source_sha256 values must be unique")
    return tuple(entries)


def load_local_sample_catalog(path: Path) -> dict[str, LocalSampleIdentity]:
    catalog: dict[str, LocalSampleIdentity] = {}
    for line_number, row in enumerate(_load_jsonl(path), start=1):
        required = {
            "sample_id",
            "source_sha256",
            "format_directory",
            "strip_mode",
            "source_relative_path",
        }
        if not required.issubset(row):
            missing = ", ".join(sorted(required - set(row)))
            raise ValueError(f"{path}:{line_number} is missing {missing}")
        format_directory = str(row["format_directory"])
        identity = LocalSampleIdentity(
            sample_id=str(row["sample_id"]),
            source_sha256=str(row["source_sha256"]).lower(),
            format_id=FORMAT_DIRECTORY_TO_ID.get(format_directory, format_directory),
            strip_mode=str(row["strip_mode"]),
            source_relative_path=str(row["source_relative_path"]),
        )
        if identity.sample_id in catalog:
            raise ValueError(
                f"local sample catalog repeats sample_id {identity.sample_id}"
            )
        catalog[identity.sample_id] = identity
    return catalog


def validate_cohort_identities(
    cohort: Sequence[PerformanceCohortEntry],
    catalog: dict[str, LocalSampleIdentity],
) -> None:
    for entry in cohort:
        identity = catalog.get(entry.sample_id)
        if identity is None:
            raise ValueError(
                f"local sample catalog has no identity for {entry.sample_id}"
            )
        expected = (
            entry.source_sha256,
            entry.format_id,
            entry.strip_mode,
        )
        actual = (
            identity.source_sha256,
            identity.format_id,
            identity.strip_mode,
        )
        if actual != expected:
            raise ValueError(
                f"local sample identity disagrees with tracked cohort for "
                f"{entry.sample_id}"
            )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validation_annotation(
    entry: PerformanceCohortEntry,
    identity: LocalSampleIdentity,
) -> int:
    if entry.strip_mode == "full":
        return format_spec(entry.format_id).strip.default_count
    match = COUNT_ANNOTATION.search(Path(identity.source_relative_path).name)
    if match is None:
        raise ValueError(
            f"{entry.sample_id} has no validation-only partial count annotation"
        )
    annotation = int(match.group(1))
    if annotation not in format_spec(entry.format_id).strip.partial_count_range:
        raise ValueError(
            f"{entry.sample_id} has an invalid validation-only count annotation"
        )
    return annotation


def _expected_output_identity(
    entry: PerformanceCohortEntry,
    identity: LocalSampleIdentity,
    width: int,
    height: int,
    layout: str,
) -> tuple[str, tuple[int, ...], tuple[dict[str, int | str], ...], int]:
    configuration = get_detection_configuration(
        entry.format_id,
        entry.strip_mode,
        None,
    )
    long_axis_px = max(width, height)
    short_axis_px = min(width, height)
    canvas = observe_scan_canvas(
        long_axis_px,
        short_axis_px,
        layout,
        configuration.scan_canvas,
    )
    if (
        canvas.outcome != ScanCanvasOutcome.SUPPORTED
        or canvas.selected_profile is None
    ):
        raise ValueError(
            f"{entry.sample_id} scan-canvas profile is not uniquely resolved"
        )
    if entry.strip_mode == "full":
        total = configuration.count_request.authoritative_count
        if total is None:
            raise ValueError(
                f"{entry.sample_id} fixed-full request has no authority"
            )
    else:
        fits = tuple(
            fit
            for fit in canvas.selected_profile.format_fits
            if fit.format_id == entry.format_id
        )
        if len(fits) != 1:
            raise ValueError(
                f"{entry.sample_id} selected profile has no unique format fit"
            )
        total = fits[0].maximum_frame_count
    lane_total = format_spec(entry.format_id).layout.lane_count
    if total <= 0 or total % lane_total:
        raise ValueError(
            f"{entry.sample_id} output capacity does not divide canonical lanes"
        )
    lane_counts = tuple(total // lane_total for _index in range(lane_total))
    slot_identities = tuple(
        {
            "global_output_ordinal": global_ordinal,
            "lane_id": f"lane:{lane_index}",
            "lane_ordinal": lane_ordinal,
        }
        for global_ordinal, (lane_index, lane_ordinal) in enumerate(
            (
                (lane_index, lane_ordinal)
                for lane_index, lane_count in enumerate(lane_counts)
                for lane_ordinal in range(1, lane_count + 1)
            ),
            start=1,
        )
    )
    annotation = _validation_annotation(entry, identity)
    if total < annotation:
        raise ValueError(
            f"{entry.sample_id} resolved capacity is below its validation annotation"
        )
    return (
        canvas.selected_profile.profile_id,
        lane_counts,
        slot_identities,
        annotation,
    )


def resolve_performance_sources(
    cohort: Sequence[PerformanceCohortEntry],
    catalog: dict[str, LocalSampleIdentity],
    source_root: Path,
) -> tuple[ResolvedPerformanceSource, ...]:
    resolved: list[ResolvedPerformanceSource] = []
    for entry in cohort:
        identity = catalog[entry.sample_id]
        relative = Path(identity.source_relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(
                f"{entry.sample_id} catalog source path is not canonical"
            )
        path = (
            source_root.joinpath(*relative.parts[1:])
            if relative.parts and relative.parts[0] == source_root.name
            else source_root / relative
        )
        if (
            not path.is_file()
            or path.suffix.lower() not in TIFF_SUFFIXES
            or _sha256(path) != entry.source_sha256
        ):
            raise ValueError(
                f"{entry.sample_id} canonical catalog source is missing or "
                "does not match its SHA"
            )
        path = path.resolve()
        profile, _warnings = read_tiff_profile(path, 0)
        if profile.compression.upper() != entry.compression:
            raise ValueError(
                f"{entry.sample_id} compression is {profile.compression}, "
                f"not {entry.compression}"
            )
        height, width = read_tiff_page_shape(path, 0)
        layout = infer_layout(width, height)
        (
            selected_profile_id,
            lane_counts,
            slot_identities,
            validation_annotation,
        ) = _expected_output_identity(
            entry,
            identity,
            width,
            height,
            layout,
        )
        resolved.append(
            ResolvedPerformanceSource(
                cohort=entry,
                path=path,
                layout=layout,
                selected_scan_canvas_profile_id=selected_profile_id,
                lane_output_slot_counts=lane_counts,
                slot_identities=slot_identities,
                validation_annotation=validation_annotation,
            )
        )
    return tuple(resolved)


def group_performance_sources(
    sources: Sequence[ResolvedPerformanceSource],
) -> tuple[tuple[PerformanceRunGroup, tuple[ResolvedPerformanceSource, ...]], ...]:
    grouped: dict[PerformanceRunGroup, list[ResolvedPerformanceSource]] = {}
    for source in sources:
        key = PerformanceRunGroup(
            source.cohort.format_id,
            source.cohort.strip_mode,
            source.layout,
        )
        grouped.setdefault(key, []).append(source)
    return tuple(
        (
            key,
            tuple(sorted(grouped[key], key=lambda item: item.cohort.sample_id)),
        )
        for key in sorted(grouped)
    )


def _stage_inputs(
    sources: Sequence[ResolvedPerformanceSource],
    staging_root: Path,
) -> tuple[tuple[PerformanceRunGroup, Path, tuple[ResolvedPerformanceSource, ...]], ...]:
    staged: list[
        tuple[PerformanceRunGroup, Path, tuple[ResolvedPerformanceSource, ...]]
    ] = []
    for group, members in group_performance_sources(sources):
        input_directory = staging_root / group.directory_name
        input_directory.mkdir(parents=True)
        for source in members:
            suffix = source.path.suffix.lower()
            (input_directory / f"{source.cohort.sample_id}{suffix}").symlink_to(
                source.path
            )
        staged.append((group, input_directory, members))
    return tuple(staged)


def build_group_command(
    group: PerformanceRunGroup,
    input_directory: Path,
    output_directory: Path,
) -> tuple[str, ...]:
    return (
        sys.executable,
        str(PROJECT_ROOT / "X5_Crop.py"),
        str(input_directory),
        "--output",
        str(output_directory),
        "--format",
        group.format_id,
        "--strip",
        group.strip_mode,
        "--layout",
        group.layout,
        "--compression",
        "same",
        "--jobs",
        str(PRODUCTION_JOBS),
        "--no-copy-review-files",
    )


def _read_run_manifest(path: Path) -> tuple[dict[str, Any], ...]:
    rows = tuple(_load_jsonl(path))
    if not rows:
        raise RuntimeError(f"performance run manifest is empty: {path}")
    return rows


def _validate_group_outputs(
    output_directory: Path,
    members: Sequence[ResolvedPerformanceSource],
) -> tuple[int, int, int]:
    manifest_path = output_directory / RUN_MANIFEST_JSONL_NAME
    rows = _read_run_manifest(manifest_path)
    if len(rows) != len(members):
        raise RuntimeError(
            f"{manifest_path} contains {len(rows)} records for {len(members)} inputs"
        )
    expected_by_name = {
        f"{source.cohort.sample_id}{source.path.suffix.lower()}": source
        for source in members
    }
    completed = 0
    approved_with_outputs = 0
    frame_output_count = 0
    seen: set[str] = set()
    for row in rows:
        source_name = Path(str(row.get("source", ""))).name
        source = expected_by_name.get(source_name)
        if source is None or source_name in seen:
            raise RuntimeError(
                f"{manifest_path} contains an unexpected source: {source_name}"
            )
        seen.add(source_name)
        if row.get("terminal_outcome") != "completed":
            raise RuntimeError(
                f"{source.cohort.sample_id} did not complete during performance run"
            )
        completed += 1
        if row.get("schema") != RUN_MANIFEST_SCHEMA:
            raise RuntimeError(
                f"{source.cohort.sample_id} has a non-current run manifest"
            )
        output_identity = row.get("output_identity")
        expected_identity = {
            "selected_scan_canvas_profile_id": (
                source.selected_scan_canvas_profile_id
            ),
            "resolved_output_slots": {
                "lane_output_slot_counts": list(
                    source.lane_output_slot_counts
                ),
            },
            "output_slot_count": source.output_slot_count,
            "slot_identities": list(source.slot_identities),
        }
        if output_identity != expected_identity:
            raise RuntimeError(
                f"{source.cohort.sample_id} output identity disagrees with "
                "the scan-canvas catalog receipt"
            )
        artifacts = row.get("artifacts")
        if not isinstance(artifacts, dict):
            raise RuntimeError(
                f"{source.cohort.sample_id} has no runtime artifacts record"
            )
        frame_outputs = artifacts.get("frame_outputs")
        if (
            not isinstance(frame_outputs, list)
            or len(frame_outputs) != source.output_slot_count
        ):
            raise RuntimeError(
                f"{source.cohort.sample_id} did not produce its exact capacity TIFFs"
            )
        approved_with_outputs += 1
        for value in frame_outputs:
            output_path = Path(str(value))
            if not output_path.is_file():
                raise RuntimeError(f"written TIFF is missing: {output_path}")
            profile, _warnings = read_tiff_profile(output_path, 0)
            if profile.compression.upper() != source.cohort.compression:
                raise RuntimeError(
                    f"{source.cohort.sample_id} output compression changed from "
                    f"{source.cohort.compression} to {profile.compression}"
                )
            frame_output_count += 1
    if seen != set(expected_by_name):
        raise RuntimeError(f"{manifest_path} omitted one or more cohort inputs")
    return completed, approved_with_outputs, frame_output_count


def _run_once(
    label: str,
    staged_groups: Sequence[
        tuple[PerformanceRunGroup, Path, tuple[ResolvedPerformanceSource, ...]]
    ],
    output_root: Path,
) -> PerformanceTiming:
    run_output = output_root / label
    run_output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    for group, input_directory, members in staged_groups:
        group_output = run_output / group.directory_name
        command = build_group_command(group, input_directory, group_output)
        completed = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
        if completed.returncode != 0:
            raise RuntimeError(
                f"performance group failed with exit code {completed.returncode}: "
                f"{group.directory_name}"
            )
    wall_seconds = time.perf_counter() - started

    completed_inputs = 0
    approved_inputs_with_outputs = 0
    frame_output_count = 0
    for group, _input_directory, members in staged_groups:
        (
            group_completed,
            group_approved,
            group_outputs,
        ) = _validate_group_outputs(
            run_output / group.directory_name,
            members,
        )
        completed_inputs += group_completed
        approved_inputs_with_outputs += group_approved
        frame_output_count += group_outputs
    input_count = sum(len(members) for _group, _directory, members in staged_groups)
    expected_frame_output_count = sum(
        source.output_slot_count
        for _group, _directory, members in staged_groups
        for source in members
    )
    return PerformanceTiming(
        label=label,
        wall_seconds=wall_seconds,
        input_count=input_count,
        completed_inputs=completed_inputs,
        approved_inputs_with_outputs=approved_inputs_with_outputs,
        frame_output_count=frame_output_count,
        expected_frame_output_count=expected_frame_output_count,
    )


def run_production_performance(
    sources: Sequence[ResolvedPerformanceSource],
    output_root: Path,
) -> ProductionPerformanceResult:
    if len(sources) != FIXED_INPUT_COUNT:
        raise ValueError(
            f"performance cohort must resolve exactly {FIXED_INPUT_COUNT} sources"
        )
    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError(f"performance output root must be empty: {output_root}")
    expected_frame_output_count = sum(
        source.output_slot_count for source in sources
    )
    partial_extra_slot_count = sum(
        source.partial_extra_slot_count for source in sources
    )
    if expected_frame_output_count != CURRENT_OUTPUT_TIFF_RECEIPT:
        raise ValueError(
            "current performance cohort/catalog receipt changed: "
            f"expected {CURRENT_OUTPUT_TIFF_RECEIPT} outputs, resolved "
            f"{expected_frame_output_count}"
        )
    if partial_extra_slot_count != CURRENT_PARTIAL_EXTRA_SLOT_RECEIPT:
        raise ValueError(
            "current partial annotation receipt changed: "
            f"expected +{CURRENT_PARTIAL_EXTRA_SLOT_RECEIPT}, resolved "
            f"+{partial_extra_slot_count}"
        )
    output_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="x5crop-performance-inputs-",
        dir="/private/tmp",
    ) as staging_directory:
        staged_groups = _stage_inputs(sources, Path(staging_directory))
        cold = _run_once("cold", staged_groups, output_root)
        measured = tuple(
            _run_once(f"measured-{index}", staged_groups, output_root)
            for index in range(1, MEASURED_RUN_COUNT + 1)
        )
        groups = tuple(group for group, _path, _members in staged_groups)
    result = ProductionPerformanceResult(
        cold,
        measured,
        output_root,
        groups,
        expected_frame_output_count,
        partial_extra_slot_count,
    )
    (output_root / "performance_result.json").write_text(
        json.dumps(result.as_record(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def _print_result(result: ProductionPerformanceResult) -> None:
    print(
        f"cold: {result.cold.wall_seconds:.3f}s "
        f"({result.cold.seconds_per_input:.3f}s/input)"
    )
    for timing in result.measured:
        print(
            f"{timing.label}: {timing.wall_seconds:.3f}s "
            f"({timing.seconds_per_input:.3f}s/input)"
        )
    outcome = "PASS" if result.passed else "FAIL"
    print(
        f"median: {result.median_seconds_per_input:.3f}s/input "
        f"(limit {SECONDS_PER_INPUT_LIMIT:.1f}s/input) {outcome}"
    )
    print(f"certification: {result.certification_status}")
    print(f"artifacts: {result.output_root}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the fixed X5 Crop production performance cohort."
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        required=True,
        help="Local root containing original TIFF samples.",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=None,
        help="Local sample identity catalog; default SOURCE_ROOT/manual_review/manifest.jsonl.",
    )
    parser.add_argument(
        "--cohort",
        type=Path,
        default=DEFAULT_COHORT,
        help="Tracked performance cohort definition.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Fresh benchmark output root; default a new directory under /private/tmp.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source_root = args.source_root.expanduser().resolve()
    catalog_path = (
        args.catalog.expanduser().resolve()
        if args.catalog is not None
        else source_root / "manual_review" / "manifest.jsonl"
    )
    cohort = load_performance_cohort(args.cohort.expanduser().resolve())
    catalog = load_local_sample_catalog(catalog_path)
    validate_cohort_identities(cohort, catalog)
    sources = resolve_performance_sources(
        cohort,
        catalog,
        source_root,
    )
    output_root = (
        args.output_root.expanduser().resolve()
        if args.output_root is not None
        else Path(
            tempfile.mkdtemp(
                prefix="x5crop-production-performance-",
                dir="/private/tmp",
            )
        )
    )
    result = run_production_performance(sources, output_root)
    _print_result(result)
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
