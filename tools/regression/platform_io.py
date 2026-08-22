"""External real-TIFF and production Orientation validation for platform receipts."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Any

import numpy as np
import tifffile

from x5crop.io.orientation import canonicalize_orientation
from x5crop.io.tiff import read_tiff, read_tiff_profile, tiff_write_kwargs
from .report_validation import validate_current_report_record

from .cohort_count import validate_cohort_counts
from .file_identity import sha256_file


PROJECT_ROOT = Path(__file__).resolve().parents[2]
COHORT_PATH = Path(__file__).with_name("cohorts") / "platform_validation.jsonl"
COHORT_SCHEMA = "x5crop_platform_validation_cohort_v3"
PLATFORM_IO_RESULT_SCHEMA = "x5crop_platform_io_result_v1"
EXPECTED_SAMPLE_IDS = ("S027", "S046", "S062", "S094", "S098", "S101")


def cohort_sha256() -> str:
    return sha256_file(COHORT_PATH)


@dataclass(frozen=True)
class PlatformSource:
    sample_id: str
    role: str
    source_path: Path
    source_sha256: str
    format_id: str
    count: int
    expected_orientation: int
    expected_compression: str
    expected_icc_bytes: int


def load_platform_sources(*, verify_files: bool) -> tuple[PlatformSource, ...]:
    validate_cohort_counts()
    records = tuple(
        json.loads(line)
        for line in COHORT_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    expected_keys = {
        "cohort_schema",
        "sample_id",
        "role",
        "source_relative_path",
        "source_sha256",
        "format_id",
        "count",
        "expected_orientation",
        "expected_compression",
        "expected_icc_bytes",
    }
    if (
        tuple(record.get("sample_id") for record in records) != EXPECTED_SAMPLE_IDS
        or any(set(record) != expected_keys for record in records)
    ):
        raise ValueError("platform cohort is incomplete or out of order")
    sources: list[PlatformSource] = []
    for record in records:
        relative = Path(str(record["source_relative_path"]))
        source = (PROJECT_ROOT / relative).resolve()
        expected_sha = str(record["source_sha256"])
        if (
            record["cohort_schema"] != COHORT_SCHEMA
            or record["role"] not in {"user_path", "io_only"}
            or relative.is_absolute()
            or not source.is_relative_to(PROJECT_ROOT)
            or len(expected_sha) != 64
            or (
                verify_files
                and (
                    not source.is_file()
                    or sha256_file(source) != expected_sha
                )
            )
        ):
            raise ValueError(f"platform source identity is invalid: {record['sample_id']}")
        sources.append(
            PlatformSource(
                sample_id=str(record["sample_id"]),
                role=str(record["role"]),
                source_path=source,
                source_sha256=expected_sha,
                format_id=str(record["format_id"]),
                count=int(record["count"]),
                expected_orientation=int(record["expected_orientation"]),
                expected_compression=str(record["expected_compression"]),
                expected_icc_bytes=int(record["expected_icc_bytes"]),
            )
        )
    return tuple(sources)


def _production_command(source: PlatformSource, path: Path, output: Path) -> list[str]:
    command = [
        sys.executable,
        str(PROJECT_ROOT / "X5_Crop.py"),
        str(path),
        "--output",
        str(output),
        "--format",
        source.format_id,
        "--count",
        str(source.count),
        "--jobs",
        "1",
    ]
    return command


def _run_cli(source: PlatformSource, path: Path, output: Path) -> dict[str, Any]:
    completed = subprocess.run(
        _production_command(source, path, output),
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError(
            f"{source.sample_id} production CLI failed:\n{completed.stdout[-4000:]}"
        )
    rows = tuple(
        json.loads(line)
        for line in (output / "x5_crop_report.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    )
    if len(rows) != 1:
        raise ValueError(f"{source.sample_id} lacks one production report")
    validate_current_report_record(rows[0])
    return rows[0]


def _validate_source_metadata(source: PlatformSource) -> dict[str, object]:
    profile, _warnings = read_tiff_profile(source.source_path)
    actual_icc = 0 if profile.icc_profile is None else len(profile.icc_profile)
    if (
        profile.orientation.original_tag != source.expected_orientation
        or profile.compression.upper() != source.expected_compression
        or actual_icc != source.expected_icc_bytes
        or profile.resolution is None
        or profile.resolution_unit is None
    ):
        raise ValueError(f"{source.sample_id} TIFF metadata responsibility changed")
    return {
        "sample_id": source.sample_id,
        "role": source.role,
        "source_sha256": source.source_sha256,
        "orientation": profile.orientation.original_tag,
        "compression": profile.compression.upper(),
        "icc_bytes": actual_icc,
        "resolution": list(profile.resolution),
        "resolution_unit": profile.resolution_unit,
    }


def raw_raster_for_orientation(canonical: np.ndarray, tag: int) -> np.ndarray:
    if tag == 3:
        raw = np.flip(canonical, axis=(0, 1))
    elif tag == 8:
        raw = np.rot90(canonical, k=3, axes=(0, 1))
    else:
        raise ValueError("derived production Orientation is limited to tags 3 and 8")
    restored, _mapping = canonicalize_orientation(raw, "YXS", tag)
    if not np.array_equal(restored, canonical):
        raise ValueError("derived raw raster does not invert the Orientation mapping")
    return np.ascontiguousarray(raw)


def _write_orientation_fixture(
    source: PlatformSource,
    canonical: np.ndarray,
    profile,
    tag: int,
    path: Path,
) -> None:
    raw = raw_raster_for_orientation(canonical, tag)
    kwargs = tiff_write_kwargs(profile)
    kwargs["extratags"] = (
        (274, "H", 1, tag, False),
        *tuple(item for item in kwargs.get("extratags", ()) if item[0] != 274),
    )
    tifffile.imwrite(path, raw, **kwargs)
    reread, reread_profile, _warnings = read_tiff(path)
    if (
        reread_profile.orientation.original_tag != tag
        or not np.array_equal(reread, canonical)
    ):
        raise ValueError(f"derived Orientation {tag} fixture failed canonical readback")


def _official_outputs(output: Path, report: dict[str, Any]) -> tuple[Path, ...]:
    return tuple(output / value for value in report["output"]["output_files"])


def _validate_orientation_integrations(
    source: PlatformSource,
    root: Path,
) -> tuple[dict[str, object], ...]:
    canonical, profile, _warnings = read_tiff(source.source_path)
    original_output = root / "original-output"
    original_report = _run_cli(source, source.source_path, original_output)
    if original_report["decision"]["status"] != "approved_auto":
        raise ValueError(
            f"{source.sample_id} must be approved for Orientation integration"
        )
    original_files = _official_outputs(original_output, original_report)
    results: list[dict[str, object]] = []
    for tag in (3, 8):
        fixture = root / f"{source.sample_id}-derived-orientation-{tag}.tif"
        _write_orientation_fixture(source, canonical, profile, tag, fixture)
        output = root / f"orientation-{tag}-output"
        report = _run_cli(source, fixture, output)
        files = _official_outputs(output, report)
        if (
            report["decision"]["status"] != "approved_auto"
            or len(files) != len(original_files)
            or report["photo_geometry"]["slot_identities"]
            != original_report["photo_geometry"]["slot_identities"]
        ):
            raise ValueError(f"Orientation {tag} changed production ordinals or status")
        for original, candidate in zip(original_files, files, strict=True):
            original_pixels = tifffile.imread(original)
            candidate_pixels = tifffile.imread(candidate)
            candidate_profile, _warnings = read_tiff_profile(candidate)
            if (
                not np.array_equal(original_pixels, candidate_pixels)
                or candidate_profile.orientation.original_tag != 1
                or candidate_profile.icc_profile != profile.icc_profile
                or candidate_profile.resolution != profile.resolution
                or candidate_profile.resolution_unit != profile.resolution_unit
                or candidate_profile.compression != profile.compression
            ):
                raise ValueError(f"Orientation {tag} changed formal TIFF output")
        results.append(
            {
                "derived_from": source.sample_id,
                "orientation": tag,
                "status": report["decision"]["status"],
                "output_tiff_count": len(files),
                "output_orientation": 1,
                "canonical_pixels_match": True,
            }
        )
    return tuple(results)


def run_platform_io_validation() -> dict[str, Any]:
    sources = load_platform_sources(verify_files=True)
    source_results: list[dict[str, object]] = []
    orientation_source: PlatformSource | None = None
    with TemporaryDirectory(prefix="x5crop-platform-io-") as temporary:
        root = Path(temporary)
        for source in sources:
            metadata = _validate_source_metadata(source)
            output = root / f"{source.sample_id}-output"
            report = _run_cli(source, source.source_path, output)
            metadata["terminal_status"] = report["decision"]["status"]
            metadata["official_tiff_count"] = len(
                report["output"]["output_files"]
            )
            source_results.append(metadata)
            if (
                orientation_source is None
                and source.role == "user_path"
                and metadata["terminal_status"] == "approved_auto"
            ):
                orientation_source = source
            print(f"platform I/O {source.sample_id}: {metadata['terminal_status']}")
        if orientation_source is None:
            raise ValueError(
                "Orientation integration requires an approved user-path source"
            )
        orientation_results = _validate_orientation_integrations(
            orientation_source,
            root,
        )
    return {
        "schema": PLATFORM_IO_RESULT_SCHEMA,
        "cohort_sha256": cohort_sha256(),
        "sources": source_results,
        "orientation_integrations": list(orientation_results),
        "accuracy_verdict": "not_assessed",
    }
