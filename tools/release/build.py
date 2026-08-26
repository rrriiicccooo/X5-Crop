#!/usr/bin/env python3
"""Build the exact user-facing X5 Crop release zip."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from tools.release.manifest import RELEASE_FILES
from tools.release.standalone import (
    build_standalone_bytes,
    package_names,
    read_sources,
)


ROOT = Path(__file__).resolve().parents[2]
VERSION_PATTERN = re.compile(r"v[0-9A-Za-z][0-9A-Za-z._-]*")
SPARSE_RELEASE_SOURCE = "LICENSE"


def normalize_version(value: str) -> str:
    version = value.strip()
    if not version.startswith("v"):
        version = f"v{version}"
    if not VERSION_PATTERN.fullmatch(version):
        raise ValueError(f"invalid release version: {value!r}")
    return version


def _read_sparse_tracked_source(source_path: str) -> bytes:
    if source_path != SPARSE_RELEASE_SOURCE:
        raise FileNotFoundError(f"release source is unavailable: {source_path}")
    listing = subprocess.run(
        ("git", "ls-files", "-v", "--", source_path),
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if listing.returncode != 0 or not listing.stdout.startswith(b"S "):
        raise FileNotFoundError(f"release source is unavailable: {source_path}")
    blob = subprocess.run(
        ("git", "cat-file", "blob", f"HEAD:{source_path}"),
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if blob.returncode != 0:
        raise FileNotFoundError(
            f"release source is unavailable from HEAD: {source_path}"
        )
    return blob.stdout


def _write_staging_file(staging: Path, archive_path: str, source_path: str | None) -> None:
    destination = staging / archive_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source_path is None:
        destination.write_bytes(
            build_standalone_bytes(read_sources(), package_names()),
        )
    else:
        source = ROOT / source_path
        if source.is_file():
            shutil.copy2(source, destination)
        else:
            destination.write_bytes(_read_sparse_tracked_source(source_path))
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
    parser.add_argument("--version", required=True, help="Release version, for example vX.Y.Z")
    parser.add_argument("--output", type=Path, help="Optional output zip path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(build_release(args.version, args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
