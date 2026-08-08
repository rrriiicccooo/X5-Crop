from __future__ import annotations

import hashlib
from importlib import import_module, metadata
from pathlib import Path


DEPENDENCY_MODULES = (
    ("numpy", "numpy", "numpy"),
    ("scipy", "scipy", "scipy"),
    ("opencv", "cv2", "opencv-python-headless"),
    ("tifffile", "tifffile", "tifffile"),
    ("imagecodecs", "imagecodecs", "imagecodecs"),
    ("pillow", "PIL", "Pillow"),
)


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
) -> tuple[str, str] | None:
    top_level = module_name.split(".", 1)[0]
    candidates = set(metadata.packages_distributions().get(top_level, ()))
    candidates.add(preferred_distribution)
    preferred = preferred_distribution.casefold()
    matches: list[tuple[str, str]] = []
    for distribution_name in sorted(
        candidates,
        key=lambda value: value.casefold() != preferred,
    ):
        try:
            distribution = metadata.distribution(distribution_name)
        except metadata.PackageNotFoundError:
            continue
        root = Path(distribution.locate_file("")).resolve()
        try:
            origin.relative_to(root)
        except ValueError:
            continue
        matches.append((distribution_name, distribution.version))
    unique = tuple(dict.fromkeys(matches))
    if len(unique) > 1:
        owners = ", ".join(name for name, _version in unique)
        raise RuntimeError(
            f"Dependency module has ambiguous package ownership: "
            f"{module_name} ({owners})"
        )
    return None if not unique else unique[0]


def runtime_dependency_identity() -> dict[str, dict[str, str | None]]:
    dependencies: dict[str, dict[str, str | None]] = {}
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
        distribution = _distribution_package(
            module_name,
            preferred_distribution,
            origin,
        )
        if homebrew is not None:
            provider = "homebrew"
            package, package_version = homebrew
        elif distribution is not None:
            provider = "pip"
            package, package_version = distribution
        else:
            provider = "external"
            package = module_name
            package_version = str(getattr(module, "__version__", "unavailable"))
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
