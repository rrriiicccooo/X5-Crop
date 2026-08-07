"""Install and conservatively remove X5 Crop's pinned user dependencies."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import re
import site
import struct
import subprocess
import sys
from typing import Mapping, Sequence


RECEIPT_SCHEMA = "x5crop_user_dependencies_v1"
SUPPORTED_PYTHON_MIN = (3, 12)
SUPPORTED_PYTHON_MAX_EXCLUSIVE = (3, 15)
REQUIREMENT_PATTERN = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;]+)$"
)
REQUIREMENT_NAME_PATTERN = re.compile(
    r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)"
)
IMPORT_CHECK = (
    "import cv2, imagecodecs, numpy, scipy, tifffile; "
    "from PIL import Image; print('Dependencies OK')"
)
CONFLICTING_OPENCV_DISTRIBUTIONS = (
    "opencv-contrib-python",
    "opencv-contrib-python-headless",
    "opencv-python",
    "opencv-python-rolling",
)


@dataclass(frozen=True)
class PackagePin:
    distribution: str
    canonical_name: str
    version: str


@dataclass(frozen=True)
class UninstallPlan:
    removable: tuple[str, ...]
    preserved: Mapping[str, str]


def canonical_distribution_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def load_pins(path: Path) -> tuple[PackagePin, ...]:
    pins: list[PackagePin] = []
    seen: set[str] = set()
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = REQUIREMENT_PATTERN.fullmatch(line)
        if match is None:
            raise ValueError(
                f"{path}:{line_number}: every dependency must use an exact == pin"
            )
        distribution, version = match.groups()
        canonical_name = canonical_distribution_name(distribution)
        if canonical_name in seen:
            raise ValueError(f"{path}:{line_number}: duplicate dependency {distribution}")
        seen.add(canonical_name)
        pins.append(PackagePin(distribution, canonical_name, version))
    if not pins:
        raise ValueError(f"{path}: no dependencies found")
    return tuple(pins)


def installed_versions(
    selected: Mapping[str, str],
) -> dict[str, str]:
    versions: dict[str, str] = {}
    for canonical_name, distribution in selected.items():
        try:
            versions[canonical_name] = metadata.version(distribution)
        except metadata.PackageNotFoundError:
            pass
    return versions


def fresh_installed_versions(selected: Mapping[str, str]) -> dict[str, str]:
    script = (
        "from importlib import metadata\n"
        "import json\n"
        "import sys\n"
        "selected = json.loads(sys.argv[1])\n"
        "found = {}\n"
        "for key, name in selected.items():\n"
        "    try:\n"
        "        found[key] = metadata.version(name)\n"
        "    except metadata.PackageNotFoundError:\n"
        "        pass\n"
        "print(json.dumps(found))\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script, json.dumps(selected)],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    return {str(name): str(version) for name, version in payload.items()}


def installed_dependency_users() -> dict[str, set[str]]:
    users: dict[str, set[str]] = {}
    for distribution in metadata.distributions():
        raw_name = distribution.metadata.get("Name")
        if not raw_name:
            continue
        owner = canonical_distribution_name(raw_name)
        for requirement in distribution.requires or ():
            match = REQUIREMENT_NAME_PATTERN.match(requirement)
            if match is None:
                continue
            dependency = canonical_distribution_name(match.group(1))
            if dependency != owner:
                users.setdefault(dependency, set()).add(owner)
    return users


def installed_opencv_conflicts() -> dict[str, str]:
    conflicts: dict[str, str] = {}
    for distribution in CONFLICTING_OPENCV_DISTRIBUTIONS:
        try:
            conflicts[distribution] = metadata.version(distribution)
        except metadata.PackageNotFoundError:
            pass
    return conflicts


def build_uninstall_plan(
    receipt_packages: Sequence[Mapping[str, object]],
    current_versions: Mapping[str, str],
    dependency_users: Mapping[str, set[str]],
) -> UninstallPlan:
    introduced: dict[str, Mapping[str, object]] = {}
    preserved: dict[str, str] = {}
    for package in receipt_packages:
        canonical_name = str(package["canonical_name"])
        distribution = str(package["distribution"])
        preexisting = package.get("preexisting_version")
        installed = str(package["installed_version"])
        current = current_versions.get(canonical_name)
        if preexisting is not None:
            preserved[distribution] = "already existed before X5 Crop setup"
        elif current is None:
            preserved[distribution] = "already absent"
        elif current != installed:
            preserved[distribution] = "version changed after X5 Crop setup"
        else:
            introduced[canonical_name] = package

    removable = set(introduced)
    while True:
        newly_shared = {
            name
            for name in removable
            if set(dependency_users.get(name, set())) - removable
        }
        if not newly_shared:
            break
        removable -= newly_shared
        for name in newly_shared:
            package = introduced[name]
            external = sorted(set(dependency_users.get(name, set())) - removable)
            preserved[str(package["distribution"])] = (
                "required by other installed package(s): " + ", ".join(external)
            )

    distributions = tuple(
        sorted(str(introduced[name]["distribution"]) for name in removable)
    )
    return UninstallPlan(distributions, preserved)


def _receipt_path(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    return Path(__file__).resolve().with_name(".x5_crop_dependency_receipt.json")


def _requirements_path(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    return Path(__file__).resolve().with_name("requirements.txt")


def _requirements_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json_atomic(path: Path, payload: Mapping[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _load_receipt(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != RECEIPT_SCHEMA:
        raise ValueError(f"Unsupported dependency receipt: {path}")
    return payload


def _same_executable(left: str, right: str) -> bool:
    return os.path.realpath(left) == os.path.realpath(right)


def _require_supported_python() -> None:
    current = sys.version_info[:2]
    if not (SUPPORTED_PYTHON_MIN <= current < SUPPORTED_PYTHON_MAX_EXCLUSIVE):
        raise RuntimeError(
            "X5 Crop requires Python 3.12, 3.13, or 3.14; "
            f"this interpreter is Python {current[0]}.{current[1]}."
        )
    if struct.calcsize("P") != 8:
        raise RuntimeError("X5 Crop requires a 64-bit Python interpreter.")


def _original_preexisting_versions(
    pins: Sequence[PackagePin],
    current: Mapping[str, str],
    previous: Mapping[str, object] | None,
) -> dict[str, str | None]:
    previous_packages = {
        str(item["canonical_name"]): item
        for item in (previous or {}).get("packages", [])
        if isinstance(item, dict) and "canonical_name" in item
    }
    return {
        pin.canonical_name: (
            previous_packages[pin.canonical_name].get("preexisting_version")
            if pin.canonical_name in previous_packages
            else current.get(pin.canonical_name)
        )
        for pin in pins
    }


def install_dependencies(
    requirements_path: Path,
    receipt_path: Path,
    *,
    break_system_packages: bool,
) -> int:
    _require_supported_python()
    pins = load_pins(requirements_path)
    selected = {pin.canonical_name: pin.distribution for pin in pins}
    previous = _load_receipt(receipt_path)
    if previous is not None and not _same_executable(
        str(previous.get("python_executable", "")), sys.executable
    ):
        raise RuntimeError(
            "This Release folder already has a dependency receipt for another "
            "Python interpreter. Run its uninstaller before reinstalling."
        )

    conflicts = installed_opencv_conflicts()
    if conflicts:
        details = ", ".join(
            f"{name} {version}" for name, version in sorted(conflicts.items())
        )
        raise RuntimeError(
            "A conflicting OpenCV distribution is already installed "
            f"({details}). No package was changed. Remove that conflict or use "
            "a separate supported Python interpreter before running setup again."
        )

    before = installed_versions(selected)
    version_conflicts = [
        (pin.distribution, before[pin.canonical_name], pin.version)
        for pin in pins
        if pin.canonical_name in before
        and before[pin.canonical_name] != pin.version
    ]
    if version_conflicts:
        details = ", ".join(
            f"{distribution} {installed} (X5 Crop requires {required})"
            for distribution, installed, required in version_conflicts
        )
        raise RuntimeError(
            "Pinned X5 Crop dependencies already exist at different versions "
            f"({details}). No package was changed. Use another supported Python "
            "interpreter or resolve those versions explicitly before running setup."
        )
    preexisting = _original_preexisting_versions(pins, before, previous)
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--user",
        "--disable-pip-version-check",
        "--no-cache-dir",
        "--only-binary=:all:",
        "--no-deps",
        "--requirement",
        str(requirements_path),
    ]
    if break_system_packages:
        command.insert(-2, "--break-system-packages")
    completed = subprocess.run(command, check=False)
    after = fresh_installed_versions(selected)
    package_records = [
        {
            "distribution": pin.distribution,
            "canonical_name": pin.canonical_name,
            "required_version": pin.version,
            "preexisting_version": preexisting[pin.canonical_name],
            "installed_version": after.get(pin.canonical_name),
        }
        for pin in pins
    ]
    receipt: dict[str, object] = {
        "schema": RECEIPT_SCHEMA,
        "status": "pip_failed" if completed.returncode else "installed_unverified",
        "python_executable": sys.executable,
        "python_version": ".".join(map(str, sys.version_info[:3])),
        "platform_system": platform.system(),
        "platform_release": platform.release(),
        "platform_machine": platform.machine(),
        "user_site": site.getusersitepackages(),
        "requirements_sha256": _requirements_sha256(requirements_path),
        "packages": package_records,
    }
    _write_json_atomic(receipt_path, receipt)
    if completed.returncode:
        return completed.returncode

    mismatches = [
        f"{pin.distribution}: expected {pin.version}, found "
        f"{after.get(pin.canonical_name, 'not installed')}"
        for pin in pins
        if after.get(pin.canonical_name) != pin.version
    ]
    if mismatches:
        print("Dependency version verification failed:", file=sys.stderr)
        for mismatch in mismatches:
            print(f"  - {mismatch}", file=sys.stderr)
        return 1

    verified = subprocess.run(
        [sys.executable, "-c", IMPORT_CHECK], check=False
    )
    if verified.returncode:
        print("Dependency import verification failed.", file=sys.stderr)
        return verified.returncode
    receipt["status"] = "verified"
    _write_json_atomic(receipt_path, receipt)
    print(f"Dependency receipt: {receipt_path}")
    return 0


def uninstall_dependencies(receipt_path: Path, *, no_relaunch: bool) -> int:
    receipt = _load_receipt(receipt_path)
    if receipt is None:
        print("No X5 Crop dependency receipt was found. Nothing was removed.")
        return 0

    recorded_python = str(receipt.get("python_executable", ""))
    if not _same_executable(recorded_python, sys.executable):
        if not no_relaunch and Path(recorded_python).is_file():
            return subprocess.run(
                [
                    recorded_python,
                    str(Path(__file__).resolve()),
                    "uninstall",
                    "--receipt",
                    str(receipt_path),
                    "--no-relaunch",
                ],
                check=False,
            ).returncode
        raise RuntimeError(
            "The Python interpreter recorded by setup is unavailable. No package "
            "was removed."
        )

    packages = receipt.get("packages", [])
    if not isinstance(packages, list):
        raise ValueError("Dependency receipt has an invalid packages field")
    selected = {
        str(package["canonical_name"]): str(package["distribution"])
        for package in packages
        if isinstance(package, dict)
        and "canonical_name" in package
        and "distribution" in package
    }
    plan = build_uninstall_plan(
        packages, installed_versions(selected), installed_dependency_users()
    )
    for distribution, reason in sorted(plan.preserved.items()):
        print(f"Preserved {distribution}: {reason}.")
    if plan.removable:
        print("Removing packages installed only for X5 Crop:")
        for distribution in plan.removable:
            print(f"  - {distribution}")
        completed = subprocess.run(
            [sys.executable, "-m", "pip", "uninstall", "-y", *plan.removable],
            check=False,
        )
        if completed.returncode:
            print(
                f"Uninstall was incomplete; receipt kept at {receipt_path}.",
                file=sys.stderr,
            )
            return completed.returncode
    else:
        print("No X5 Crop-owned package is safe to remove.")

    receipt_path.unlink(missing_ok=True)
    print("Dependency receipt removed. Delete the X5 Crop folder to remove the program.")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    install_parser = subparsers.add_parser("install")
    install_parser.add_argument("--requirements")
    install_parser.add_argument("--receipt")
    install_parser.add_argument("--break-system-packages", action="store_true")
    uninstall_parser = subparsers.add_parser("uninstall")
    uninstall_parser.add_argument("--receipt")
    uninstall_parser.add_argument("--no-relaunch", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "install":
            return install_dependencies(
                _requirements_path(args.requirements),
                _receipt_path(args.receipt),
                break_system_packages=args.break_system_packages,
            )
        return uninstall_dependencies(
            _receipt_path(args.receipt), no_relaunch=args.no_relaunch
        )
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"Dependency operation stopped safely: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
