from __future__ import annotations

import hashlib
from importlib import import_module, metadata
from pathlib import Path
import re
from typing import Mapping


DEPENDENCY_MODULES = (
    ("numpy", "numpy", "numpy"),
    ("scipy", "scipy", "scipy"),
    ("opencv", "cv2", "opencv-python-headless"),
    ("tifffile", "tifffile", "tifffile"),
    ("imagecodecs", "imagecodecs", "imagecodecs"),
    ("pillow", "PIL", "Pillow"),
)


def _canonical_distribution_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _homebrew_package(origin: Path) -> tuple[str, str] | None:
    parts = origin.parts
    try:
        index = parts.index("Cellar")
        package = parts[index + 1]
        version = parts[index + 2]
    except (ValueError, IndexError):
        return None
    if not package or not version:
        return None
    return package, version


def _distribution_package(
    module_name: str,
    preferred_distribution: str,
    origin: Path,
    owners: Mapping[str, list[str]],
    cache: dict[str, tuple[Path, str] | None],
) -> tuple[str, str] | None:
    top_level = module_name.split(".", 1)[0]
    candidates: dict[str, str] = {}
    for distribution_name in (
        *owners.get(top_level, ()),
        preferred_distribution,
    ):
        candidates.setdefault(
            _canonical_distribution_name(distribution_name),
            distribution_name,
        )
    preferred = _canonical_distribution_name(preferred_distribution)
    matches: dict[str, tuple[str, str]] = {}
    for identity, distribution_name in sorted(
        candidates.items(),
        key=lambda item: item[0] != preferred,
    ):
        cache_key = identity
        if cache_key not in cache:
            try:
                distribution = metadata.distribution(distribution_name)
            except metadata.PackageNotFoundError:
                cache[cache_key] = None
            else:
                cache[cache_key] = (
                    Path(distribution.locate_file("")).resolve(),
                    distribution.version,
                )
        cached = cache[cache_key]
        if cached is None:
            continue
        root, version = cached
        try:
            origin.relative_to(root)
        except ValueError:
            continue
        display_name = (
            preferred_distribution if identity == preferred else distribution_name
        )
        matches[identity] = (display_name, version)
    unique = tuple(matches.values())
    if len(unique) > 1:
        owners = ", ".join(name for name, _version in unique)
        raise RuntimeError(
            f"Dependency module has ambiguous package ownership: "
            f"{module_name} ({owners})"
        )
    return None if not unique else unique[0]


def runtime_dependency_identity() -> dict[str, dict[str, str | None]]:
    dependencies: dict[str, dict[str, str | None]] = {}
    distribution_owners: Mapping[str, list[str]] | None = None
    distribution_cache: dict[str, tuple[Path, str] | None] = {}
    for name, module_name, preferred_distribution in DEPENDENCY_MODULES:
        try:
            module = import_module(module_name)
        except ImportError as exc:
            raise RuntimeError(
                f"Required dependency module is unavailable: {module_name}"
            ) from exc
        origin_value = getattr(module, "__file__", None)
        if origin_value is None:
            raise RuntimeError(f"Dependency module has no origin: {module_name}")
        origin = Path(origin_value).resolve()
        homebrew = _homebrew_package(origin)
        if homebrew is not None:
            provider = "homebrew"
            package, package_version = homebrew
        else:
            if distribution_owners is None:
                distribution_owners = metadata.packages_distributions()
            distribution = _distribution_package(
                module_name,
                preferred_distribution,
                origin,
                distribution_owners,
                distribution_cache,
            )
            if distribution is not None:
                provider = "pip"
                package, package_version = distribution
            else:
                provider = "external"
                package = module_name
                package_version = str(
                    getattr(module, "__version__", "unavailable")
                )
        build_information_sha256 = None
        if module_name == "cv2":
            build_information_sha256 = hashlib.sha256(
                module.getBuildInformation().encode("utf-8")
            ).hexdigest()
        dependencies[name] = {
            "module": module_name,
            "module_version": str(getattr(module, "__version__", "unavailable")),
            "module_origin": str(origin),
            "provider": provider,
            "package": package,
            "package_version": package_version,
            "build_information_sha256": build_information_sha256,
        }
    return dependencies
