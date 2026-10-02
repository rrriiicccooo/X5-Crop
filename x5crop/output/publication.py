"""Publish one completed run into a fresh output directory."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
import tempfile


class FreshOutputError(RuntimeError):
    """The requested output directory cannot be published safely."""


def _rename_without_replacing(source: Path, target: Path) -> None:
    """Publish atomically, including when another process creates target."""
    if sys.platform == "win32":
        # Windows os.rename refuses an existing destination atomically.
        os.rename(source, target)
        return

    # These extensions are needed because POSIX rename replaces empty dirs.
    # Load only at publication; never fall back to a check followed by rename.
    import ctypes

    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        function = getattr(libc, "renamex_np", None)
        # Darwin RENAME_EXCL (sys/stdio.h).
        arguments = (os.fsencode(source), os.fsencode(target), 0x00000004)
        signature = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint)
    elif sys.platform.startswith("linux"):
        function = getattr(libc, "renameat2", None)
        # AT_FDCWD, RENAME_NOREPLACE; also used by Linux development/CI.
        arguments = (-100, os.fsencode(source), -100, os.fsencode(target), 1)
        signature = (
            ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
            ctypes.c_char_p, ctypes.c_uint,
        )
    else:
        function = None
    if function is None:
        raise FreshOutputError("Atomic output publication is unavailable on this platform")
    function.argtypes = signature
    function.restype = ctypes.c_int
    if function(*arguments) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(target))


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
        try:
            _rename_without_replacing(self.staging, self.target)
        except OSError as exc:
            raise FreshOutputError(
                f"Output directory could not be published safely: {self.target}: {exc}"
            ) from exc
        self._published = True

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        if (
            not self._published
            and self.staging is not None
            and self.staging.exists()
        ):
            shutil.rmtree(self.staging)
