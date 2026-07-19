"""Canonical local source identity for real-sample regression artifacts."""

from __future__ import annotations

from pathlib import Path


def canonical_sample_source(source: str | Path, workspace_root: Path) -> Path:
    path = Path(source)
    if not path.is_absolute():
        path = workspace_root / path
    return path.resolve(strict=False)
