#!/usr/bin/env python3
"""Build the exact user-facing X5 Crop release zip."""

from __future__ import annotations

import argparse
import re
import shutil
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from tools.build_standalone import build_standalone_text, package_names, read_sources
from tools.release_manifest import RELEASE_FILES


ROOT = Path(__file__).resolve().parents[1]
VERSION_PATTERN = re.compile(r"v[0-9A-Za-z][0-9A-Za-z._-]*")


def normalize_version(value: str) -> str:
    version = value.strip()
    if not version.startswith("v"):
        version = f"v{version}"
    if not VERSION_PATTERN.fullmatch(version):
        raise ValueError(f"invalid release version: {value!r}")
    return version


def _write_staging_file(staging: Path, archive_path: str, source_path: str | None) -> None:
    destination = staging / archive_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source_path is None:
        destination.write_text(
            build_standalone_text(read_sources(), package_names()),
            encoding="utf-8",
        )
    else:
        source = ROOT / source_path
        if not source.is_file():
            raise FileNotFoundError(f"release source is unavailable: {source_path}")
        shutil.copy2(source, destination)
    if destination.suffix == ".command" or archive_path == "X5_Crop.py":
        destination.chmod(destination.stat().st_mode | 0o111)


def build_release(version: str, output: Path | None = None) -> Path:
    normalized = normalize_version(version)
    archive = (output or ROOT / "dist" / f"X5-Crop-{normalized}.zip").resolve()
    archive.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="x5-crop-release-") as temporary:
        staging = Path(temporary)
        for archive_path, source_path in RELEASE_FILES:
            _write_staging_file(staging, archive_path, source_path)
        with ZipFile(archive, "w", compression=ZIP_DEFLATED, compresslevel=9) as package:
            for archive_path, _ in RELEASE_FILES:
                package.write(staging / archive_path, arcname=archive_path)
    return archive


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="Release version, for example v4.2.9")
    parser.add_argument("--output", type=Path, help="Optional output zip path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(build_release(args.version, args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
