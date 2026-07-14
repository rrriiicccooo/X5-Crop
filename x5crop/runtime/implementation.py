from __future__ import annotations

from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from typing import Mapping
import sys


def implementation_fingerprint_for_sources(sources: Mapping[str, str]) -> str:
    digest = sha256()
    for module_name, source in sorted(sources.items()):
        digest.update(module_name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(source.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _active_sources() -> dict[str, str]:
    main_module = sys.modules.get("__main__")
    embedded = getattr(main_module, "_X5_EMBEDDED_SOURCES", None)
    if isinstance(embedded, dict) and all(
        isinstance(name, str) and isinstance(source, str)
        for name, source in embedded.items()
    ):
        return dict(embedded)

    package_root = Path(__file__).resolve().parents[1]
    return {
        "x5crop." + path.relative_to(package_root).with_suffix("").as_posix().replace("/", "."):
        path.read_text(encoding="utf-8")
        for path in package_root.rglob("*.py")
    }


@lru_cache(maxsize=1)
def active_implementation_fingerprint() -> str:
    return implementation_fingerprint_for_sources(_active_sources())
