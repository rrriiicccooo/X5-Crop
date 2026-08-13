"""Publish one completed run into a fresh output directory."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile


class FreshOutputError(RuntimeError):
    """The requested output directory cannot be published safely."""


class FreshOutputDirectory:
    """Own one same-parent staging directory and publish it exactly once."""

    def __init__(self, target: Path) -> None:
        self.target = target
        self.staging: Path | None = None
        self._published = False

    def __enter__(self) -> "FreshOutputDirectory":
        self.target.parent.mkdir(parents=True, exist_ok=True)
        if os.path.lexists(self.target):
            raise FreshOutputError(
                f"Output directory already exists; choose a new path: {self.target}"
            )
        self.staging = Path(
            tempfile.mkdtemp(
                prefix=f".{self.target.name}.x5crop-",
                dir=self.target.parent,
            )
        )
        return self

    def publish(self) -> None:
        if self.staging is None or not self.staging.is_dir():
            raise FreshOutputError("Fresh output staging is unavailable")
        if os.path.lexists(self.target):
            raise FreshOutputError(
                f"Output directory appeared during processing: {self.target}"
            )
        os.rename(self.staging, self.target)
        self._published = True

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        if (
            not self._published
            and self.staging is not None
            and self.staging.exists()
        ):
            shutil.rmtree(self.staging)
