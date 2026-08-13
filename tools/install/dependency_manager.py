"""Install and conservatively remove X5 Crop's user dependencies."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from importlib import metadata
import json
import os
from pathlib import Path
import re
import shutil
import site
import struct
import subprocess
import sys
import tomllib
from typing import Mapping, Sequence


CONTRACT_SCHEMA = "x5crop_dependencies_v2"
RECEIPT_SCHEMA = "x5crop_user_dependencies_v3"
SUPPORTED_PYTHON_MIN = (3, 12)
SUPPORTED_PYTHON_MAX_EXCLUSIVE = (3, 15)
REQUIREMENT_NAME_PATTERN = re.compile(
    r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)"
)


@dataclass(frozen=True)
class DependencyPin:
    name: str
    module: str
    module_version: str
    pip_distribution: str
    pip_version: str
    homebrew_formula: str | None


@dataclass(frozen=True)
class DependencyContract:
    dependencies: tuple[DependencyPin, ...]

    def by_name(self) -> dict[str, DependencyPin]:
        return {pin.name: pin for pin in self.dependencies}


@dataclass(frozen=True)
class DependencyState:
    name: str
    module: str
    available: bool
    module_version: str | None
    module_origin: str | None
    provider: str
    package: str | None
    package_version: str | None
    import_error: str | None = None

    def satisfies(self, pin: DependencyPin) -> bool:
        return self.available and self.module_version == pin.module_version


@dataclass(frozen=True)
class PipInstall:
    name: str
    distribution: str
    version: str


@dataclass(frozen=True)
class UninstallPlan:
    removable: tuple[str, ...]
    preserved: Mapping[str, str]


def canonical_distribution_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _contract_string(
    record: Mapping[str, object], key: str, context: str
) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError(f"{context}: {key} must be one non-empty string")
    return value


def load_dependency_contract(path: Path) -> DependencyContract:
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Invalid dependency contract: {path}: {exc}") from exc
    if set(payload) != {"schema", "dependencies"}:
        raise ValueError(f"{path}: dependency contract fields are not current")
    if payload.get("schema") != CONTRACT_SCHEMA:
        raise ValueError(f"Unsupported dependency contract: {path}")
    raw_dependencies = payload.get("dependencies")
    if not isinstance(raw_dependencies, list) or not raw_dependencies:
        raise ValueError(f"{path}: no dependencies found")

    required_fields = {
        "name",
        "module",
        "module_version",
        "pip_distribution",
        "pip_version",
    }
    allowed_fields = required_fields | {"homebrew_formula"}
    dependencies: list[DependencyPin] = []
    names: set[str] = set()
    modules: set[str] = set()
    for index, raw_record in enumerate(raw_dependencies, start=1):
        context = f"{path}: dependencies[{index}]"
        if (
            not isinstance(raw_record, dict)
            or not required_fields.issubset(raw_record)
            or not set(raw_record).issubset(allowed_fields)
        ):
            raise ValueError(f"{context}: dependency fields are not current")
        formula = raw_record.get("homebrew_formula")
        if formula is not None and (
            not isinstance(formula, str)
            or not formula
            or formula.strip() != formula
        ):
            raise ValueError(f"{context}: homebrew_formula is invalid")
        pin = DependencyPin(
            name=_contract_string(raw_record, "name", context),
            module=_contract_string(raw_record, "module", context),
            module_version=_contract_string(raw_record, "module_version", context),
            pip_distribution=_contract_string(
                raw_record, "pip_distribution", context
            ),
            pip_version=_contract_string(raw_record, "pip_version", context),
            homebrew_formula=formula,
        )
        if pin.name in names or pin.module in modules:
            raise ValueError(f"{context}: duplicate dependency identity")
        names.add(pin.name)
        modules.add(pin.module)
        dependencies.append(pin)
    return DependencyContract(tuple(dependencies))


def installed_versions(selected: Mapping[str, str]) -> dict[str, str]:
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


def _fresh_module_records(
    contract: DependencyContract,
) -> dict[str, dict[str, object]]:
    specifications = [
        {
            "name": pin.name,
            "module": pin.module,
            "pip_distribution": pin.pip_distribution,
        }
        for pin in contract.dependencies
    ]
    script = (
        "from importlib import import_module, metadata\n"
        "import json\n"
        "from pathlib import Path\n"
        "import re\n"
        "import sys\n"
        "def canonical_distribution_name(name):\n"
        "    return re.sub(r'[-_.]+', '-', name).lower()\n"
        "specifications = json.loads(sys.argv[1])\n"
        "owners = metadata.packages_distributions()\n"
        "records = {}\n"
        "for spec in specifications:\n"
        "    name = spec['name']\n"
        "    module_name = spec['module']\n"
        "    top_level = module_name.split('.', 1)[0]\n"
        "    candidates = {}\n"
        "    for candidate in (*owners.get(top_level, ()), spec['pip_distribution']):\n"
        "        candidates.setdefault(canonical_distribution_name(candidate), candidate)\n"
        "    distributions = {}\n"
        "    for candidate in candidates.values():\n"
        "        try:\n"
        "            package = metadata.distribution(candidate)\n"
        "        except metadata.PackageNotFoundError:\n"
        "            continue\n"
        "        distribution = str(package.metadata.get('Name') or candidate)\n"
        "        distributions[canonical_distribution_name(distribution)] = {\n"
        "            'distribution': distribution,\n"
        "            'version': package.version,\n"
        "            'root': str(Path(package.locate_file('')).resolve()),\n"
        "        }\n"
        "    try:\n"
        "        module = import_module(module_name)\n"
        "    except Exception as error:\n"
        "        records[name] = {\n"
        "            'available': False,\n"
        "            'module_version': None,\n"
        "            'module_origin': None,\n"
        "            'import_error': f'{type(error).__name__}: {error}',\n"
        "            'distributions': distributions,\n"
        "        }\n"
        "        continue\n"
        "    origin = getattr(module, '__file__', None)\n"
        "    records[name] = {\n"
        "        'available': True,\n"
        "        'module_version': str(getattr(module, '__version__', 'unavailable')),\n"
        "        'module_origin': None if origin is None else str(Path(origin).resolve()),\n"
        "        'import_error': None,\n"
        "        'distributions': distributions,\n"
        "    }\n"
        "print(json.dumps(records))\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script, json.dumps(specifications)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        detail = completed.stderr.strip() or "dependency inspection failed"
        raise RuntimeError(f"Dependency inspection failed: {detail}")
    payload = json.loads(completed.stdout)
    if not isinstance(payload, dict):
        raise RuntimeError("Dependency inspection returned an invalid record")
    return {
        str(name): dict(record)
        for name, record in payload.items()
        if isinstance(record, dict)
    }


def _homebrew_executable() -> str | None:
    candidates = (
        shutil.which("brew"),
        "/opt/homebrew/bin/brew",
        "/usr/local/bin/brew",
    )
    for candidate in dict.fromkeys(candidates):
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def _run_capture(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
    )


def _homebrew_package_for_origin(
    pin: DependencyPin,
    module_origin: str | None,
) -> tuple[str, str] | None:
    if pin.homebrew_formula is None or module_origin is None:
        return None
    brew = _homebrew_executable()
    if brew is None:
        return None
    cellar_result = _run_capture((brew, "--cellar", pin.homebrew_formula))
    versions_result = _run_capture(
        (brew, "list", "--versions", "--formula", pin.homebrew_formula)
    )
    if cellar_result.returncode or versions_result.returncode:
        return None
    cellar = Path(cellar_result.stdout.strip()).resolve()
    origin = Path(module_origin).resolve()
    try:
        origin.relative_to(cellar)
    except ValueError:
        return None
    fields = versions_result.stdout.split()
    if fields[:1] != [pin.homebrew_formula] or len(fields) != 2:
        return None
    return pin.homebrew_formula, fields[1]


def pip_package_for_record(
    pin: DependencyPin,
    record: Mapping[str, object],
) -> tuple[str, str] | None:
    raw_distributions = record.get("distributions")
    if not isinstance(raw_distributions, dict) or not raw_distributions:
        return None
    origin_value = record.get("module_origin")
    origin = None if origin_value is None else Path(str(origin_value)).resolve()
    preferred = canonical_distribution_name(pin.pip_distribution)
    ordered = sorted(
        raw_distributions,
        key=lambda name: canonical_distribution_name(str(name)) != preferred,
    )
    matches: dict[str, tuple[str, str]] = {}
    for raw_name in ordered:
        detail = raw_distributions.get(raw_name)
        if not isinstance(detail, dict) or "version" not in detail:
            continue
        if origin is not None and detail.get("root") is not None:
            root = Path(str(detail["root"])).resolve()
            try:
                origin.relative_to(root)
            except ValueError:
                continue
        distribution = str(detail.get("distribution", raw_name))
        identity = canonical_distribution_name(distribution)
        version = str(detail["version"])
        display_name = pin.pip_distribution if identity == preferred else distribution
        existing = matches.get(identity)
        if existing is not None and existing[1] != version:
            raise RuntimeError(
                f"{pin.module} has conflicting pip metadata for {identity}; "
                "no dependency was changed"
            )
        matches[identity] = (display_name, version)
    unique = tuple(matches.values())
    if len(unique) > 1:
        owners = ", ".join(name for name, _version in unique)
        raise RuntimeError(
            f"{pin.module} has ambiguous pip ownership ({owners}); "
            "no dependency was changed"
        )
    return None if not unique else unique[0]


def inspect_dependency_states(
    contract: DependencyContract,
) -> tuple[DependencyState, ...]:
    records = _fresh_module_records(contract)
    states: list[DependencyState] = []
    for pin in contract.dependencies:
        record = records.get(pin.name)
        if record is None:
            raise RuntimeError(f"Dependency inspection omitted {pin.name}")
        available = bool(record.get("available"))
        origin = (
            None
            if record.get("module_origin") is None
            else str(record["module_origin"])
        )
        homebrew = _homebrew_package_for_origin(pin, origin)
        pip_package = pip_package_for_record(pin, record)
        if homebrew is not None:
            provider = "homebrew"
            package, package_version = homebrew
        elif pip_package is not None:
            provider = "pip"
            package, package_version = pip_package
        elif available:
            provider = "external"
            package = pin.module
            package_version = (
                None
                if record.get("module_version") is None
                else str(record["module_version"])
            )
        else:
            provider = "missing"
            package = None
            package_version = None
        states.append(
            DependencyState(
                name=pin.name,
                module=pin.module,
                available=available,
                module_version=(
                    None
                    if record.get("module_version") is None
                    else str(record["module_version"])
                ),
                module_origin=origin,
                provider=provider,
                package=package,
                package_version=package_version,
                import_error=(
                    None
                    if record.get("import_error") is None
                    else str(record["import_error"])
                ),
            )
        )
    return tuple(states)


def _homebrew_can_supply(pin: DependencyPin) -> bool:
    if pin.homebrew_formula is None:
        return False
    brew = _homebrew_executable()
    if brew is None:
        return False
    completed = _run_capture((brew, "info", "--json=v2", pin.homebrew_formula))
    if completed.returncode:
        return False
    try:
        payload = json.loads(completed.stdout)
        stable = str(payload["formulae"][0]["versions"]["stable"])
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return False
    return stable.split("_", 1)[0] == pin.module_version


def _update_homebrew_formula(formula: str) -> None:
    brew = _homebrew_executable()
    if brew is None:
        raise RuntimeError("Homebrew provider disappeared before update")
    completed = subprocess.run([brew, "upgrade", formula], check=False)
    if completed.returncode:
        raise RuntimeError(f"Homebrew failed to update {formula}")


def _pip_command(
    actions: Sequence[PipInstall],
    *,
    break_system_packages: bool,
    dry_run: bool,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--user",
        "--upgrade",
        "--disable-pip-version-check",
        "--no-cache-dir",
        "--only-binary=:all:",
        "--no-deps",
    ]
    if dry_run:
        command.append("--dry-run")
    if break_system_packages:
        command.append("--break-system-packages")
    command.extend(
        f"{action.distribution}=={action.version}" for action in actions
    )
    return command


def _preflight_pip(
    actions: Sequence[PipInstall],
    *,
    break_system_packages: bool,
) -> int:
    return subprocess.run(
        _pip_command(
            actions,
            break_system_packages=break_system_packages,
            dry_run=True,
        ),
        check=False,
    ).returncode


def _ensure_pip_available() -> int:
    available = subprocess.run(
        [sys.executable, "-m", "pip", "--version"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if available.returncode == 0:
        return 0
    bootstrapped = subprocess.run(
        [sys.executable, "-m", "ensurepip", "--user"],
        check=False,
    )
    if bootstrapped.returncode:
        return bootstrapped.returncode
    return subprocess.run(
        [sys.executable, "-m", "pip", "--version"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode


def _install_with_pip(
    actions: Sequence[PipInstall],
    *,
    break_system_packages: bool,
) -> int:
    return subprocess.run(
        _pip_command(
            actions,
            break_system_packages=break_system_packages,
            dry_run=False,
        ),
        check=False,
    ).returncode


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


def _contract_path(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    return Path(__file__).resolve().with_name("dependencies.toml")


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


def _state_record(
    pin: DependencyPin,
    state: DependencyState,
    action: str,
) -> dict[str, object]:
    return {
        "name": pin.name,
        "module": pin.module,
        "required_module_version": pin.module_version,
        "action": action,
        "available": state.available,
        "module_version": state.module_version,
        "module_origin": state.module_origin,
        "provider": state.provider,
        "package": state.package,
        "package_version": state.package_version,
        "import_error": state.import_error,
    }


def check_dependencies(
    contract_path: Path,
    *,
    quiet: bool,
) -> int:
    _require_supported_python()
    contract = load_dependency_contract(contract_path)
    states = inspect_dependency_states(contract)
    by_name = {state.name: state for state in states}
    mismatches = tuple(
        (pin, by_name[pin.name])
        for pin in contract.dependencies
        if not by_name[pin.name].satisfies(pin)
    )
    if not quiet:
        for pin in contract.dependencies:
            state = by_name[pin.name]
            status = "ready" if state.satisfies(pin) else "needs action"
            found = state.module_version or "not importable"
            print(
                f"{pin.name}: {status}; required {pin.module_version}; "
                f"found {found}; provider {state.provider}"
            )
    return 1 if mismatches else 0


def install_dependencies(
    contract_path: Path,
    receipt_path: Path,
    *,
    break_system_packages: bool,
) -> int:
    _require_supported_python()
    contract = load_dependency_contract(contract_path)
    previous = _load_receipt(receipt_path)
    if previous is not None and not _same_executable(
        str(previous.get("python_executable", "")), sys.executable
    ):
        raise RuntimeError(
            "This Release folder already has a dependency receipt for another "
            "Python interpreter. Run its uninstaller before reinstalling."
        )
    before_states = inspect_dependency_states(contract)
    before_by_name = {state.name: state for state in before_states}
    actions = {pin.name: "reused" for pin in contract.dependencies}
    homebrew_actions: list[tuple[DependencyPin, str]] = []
    pip_actions: list[PipInstall] = []
    for pin in contract.dependencies:
        state = before_by_name[pin.name]
        if state.satisfies(pin):
            continue
        if state.provider == "homebrew":
            if not _homebrew_can_supply(pin):
                raise RuntimeError(
                    f"Homebrew cannot supply required {pin.name} "
                    f"{pin.module_version}; no dependency was changed"
                )
            if state.package is None:
                raise RuntimeError(f"Homebrew ownership is incomplete for {pin.name}")
            actions[pin.name] = "homebrew_updated"
            homebrew_actions.append((pin, state.package))
        elif state.provider == "pip":
            distribution = state.package or pin.pip_distribution
            actions[pin.name] = "pip_updated"
            pip_actions.append(
                PipInstall(pin.name, distribution, pin.pip_version)
            )
        elif state.provider == "missing":
            actions[pin.name] = "pip_installed"
            pip_actions.append(
                PipInstall(pin.name, pin.pip_distribution, pin.pip_version)
            )
        else:
            raise RuntimeError(
                f"{pin.name} {state.module_version} comes from an unknown provider "
                f"at {state.module_origin}; no dependency was changed"
            )

    previous_packages = {
        str(item["canonical_name"]): item
        for item in (previous or {}).get("packages", [])
        if isinstance(item, dict) and "canonical_name" in item
    }
    tracked_distributions = {
        canonical_distribution_name(action.distribution): action.distribution
        for action in pip_actions
    }
    tracked_distributions.update(
        {
            name: str(item["distribution"])
            for name, item in previous_packages.items()
            if "distribution" in item
        }
    )
    preexisting_versions = (
        installed_versions(tracked_distributions) if tracked_distributions else {}
    )

    if pip_actions:
        pip_bootstrap_result = _ensure_pip_available()
        if pip_bootstrap_result:
            return pip_bootstrap_result
        preflight_result = _preflight_pip(
            pip_actions,
            break_system_packages=break_system_packages,
        )
        if preflight_result:
            return preflight_result
    for _pin, formula in homebrew_actions:
        _update_homebrew_formula(formula)
    pip_result = 0
    if pip_actions:
        pip_result = _install_with_pip(
            pip_actions,
            break_system_packages=break_system_packages,
        )

    final_states = inspect_dependency_states(contract)
    final_by_name = {state.name: state for state in final_states}
    final_versions = (
        fresh_installed_versions(tracked_distributions)
        if tracked_distributions
        else {}
    )
    package_records: list[dict[str, object]] = []
    for canonical_name, distribution in tracked_distributions.items():
        previous_package = previous_packages.get(canonical_name)
        preexisting_version = (
            previous_package.get("preexisting_version")
            if previous_package is not None
            else preexisting_versions.get(canonical_name)
        )
        package_records.append(
            {
                "distribution": distribution,
                "canonical_name": canonical_name,
                "preexisting_version": preexisting_version,
                "installed_version": final_versions.get(canonical_name),
            }
        )

    mismatches = [
        f"{pin.name}: expected {pin.module_version}, found "
        f"{final_by_name[pin.name].module_version or 'not importable'}"
        for pin in contract.dependencies
        if not final_by_name[pin.name].satisfies(pin)
    ]
    status = "verified"
    if pip_result:
        status = "pip_failed"
    elif mismatches:
        status = "verification_failed"
    receipt: dict[str, object] = {
        "schema": RECEIPT_SCHEMA,
        "status": status,
        "python_executable": sys.executable,
        "python_version": ".".join(map(str, sys.version_info[:3])),
        "user_site": site.getusersitepackages(),
        "dependencies": [
            _state_record(pin, final_by_name[pin.name], actions[pin.name])
            for pin in contract.dependencies
        ],
        "packages": package_records,
    }
    _write_json_atomic(receipt_path, receipt)
    if pip_result:
        return pip_result
    if mismatches:
        print("Dependency verification failed:", file=sys.stderr)
        for mismatch in mismatches:
            print(f"  - {mismatch}", file=sys.stderr)
        return 1
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
        print("Removing user packages installed only for X5 Crop:")
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
        print("No X5 Crop-owned user package is safe to remove.")

    receipt_path.unlink(missing_ok=True)
    print("Dependency receipt removed. Delete the X5 Crop folder to remove the program.")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("--contract")
    check_parser.add_argument("--quiet", action="store_true")
    install_parser = subparsers.add_parser("install")
    install_parser.add_argument("--contract")
    install_parser.add_argument("--receipt")
    install_parser.add_argument("--break-system-packages", action="store_true")
    uninstall_parser = subparsers.add_parser("uninstall")
    uninstall_parser.add_argument("--receipt")
    uninstall_parser.add_argument("--no-relaunch", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "check":
            return check_dependencies(
                _contract_path(args.contract),
                quiet=args.quiet,
            )
        if args.command == "install":
            return install_dependencies(
                _contract_path(args.contract),
                _receipt_path(args.receipt),
                break_system_packages=args.break_system_packages,
            )
        return uninstall_dependencies(
            _receipt_path(args.receipt), no_relaunch=args.no_relaunch
        )
    except (
        OSError,
        ValueError,
        RuntimeError,
        json.JSONDecodeError,
        subprocess.SubprocessError,
    ) as error:
        print(f"Dependency operation stopped safely: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
