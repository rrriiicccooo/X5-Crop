from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path
import platform
import subprocess
import uuid


class OutputSupportLevel(str, Enum):
    VERIFIED_LOCAL = "verified_local"
    BEST_EFFORT_UNVERIFIED = "best_effort_unverified"


@dataclass(frozen=True)
class FilesystemIdentity:
    platform: str
    filesystem_kind: str
    support_level: OutputSupportLevel
    reason: str

    def as_record(self) -> dict[str, str]:
        return {
            "platform": self.platform,
            "filesystem_kind": self.filesystem_kind,
            "support_level": self.support_level.value,
            "reason": self.reason,
        }


_CLOUD_PATH_MARKERS = (
    "/library/cloudstorage/",
    "/onedrive/",
    "/dropbox/",
    "/google drive/",
)
_NETWORK_FILESYSTEMS = frozenset(
    {"smbfs", "smb", "nfs", "afpfs", "cifs", "webdav", "fuse"}
)


def _filesystem_kind_posix(path: Path) -> str:
    commands = (
        ("/usr/bin/stat", "-f", "%T", str(path)),
        ("stat", "-f", "-c", "%T", str(path)),
    )
    for command in commands:
        try:
            completed = subprocess.run(
                command,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError):
            continue
        value = completed.stdout.strip().lower()
        if value:
            return value
    return "unknown"


def _filesystem_kind_windows(path: Path) -> str:
    try:
        import ctypes
        from ctypes import wintypes

        root = Path(path.anchor or path.drive + "\\")
        buffer = ctypes.create_unicode_buffer(64)
        ok = ctypes.windll.kernel32.GetVolumeInformationW(
            wintypes.LPCWSTR(str(root)),
            None,
            0,
            None,
            None,
            None,
            buffer,
            len(buffer),
        )
        return buffer.value.lower() if ok else "unknown"
    except Exception:
        return "unknown"


def identify_filesystem(parent: Path) -> FilesystemIdentity:
    resolved = parent.resolve()
    system = platform.system().lower()
    kind = (
        _filesystem_kind_windows(resolved)
        if os.name == "nt"
        else _filesystem_kind_posix(resolved)
    )
    normalized_path = "/" + resolved.as_posix().casefold().strip("/") + "/"
    if any(marker in normalized_path for marker in _CLOUD_PATH_MARKERS):
        return FilesystemIdentity(
            system,
            kind,
            OutputSupportLevel.BEST_EFFORT_UNVERIFIED,
            "known cloud-synchronization path",
        )
    if any(marker in kind for marker in _NETWORK_FILESYSTEMS):
        return FilesystemIdentity(
            system,
            kind,
            OutputSupportLevel.BEST_EFFORT_UNVERIFIED,
            "network or userspace filesystem",
        )
    verified = (
        (system == "darwin" and kind in {"apfs", "hfs", "hfs+"})
        or (system == "windows" and kind == "ntfs")
    )
    return FilesystemIdentity(
        system,
        kind,
        (
            OutputSupportLevel.VERIFIED_LOCAL
            if verified
            else OutputSupportLevel.BEST_EFFORT_UNVERIFIED
        ),
        "verified local filesystem" if verified else "filesystem lacks a release receipt",
    )


def probe_same_parent_rename(parent: Path, token: str) -> None:
    left = parent / f".{token}.probe-{uuid.uuid4().hex}.a"
    right = left.with_suffix(".b")
    try:
        left.mkdir()
        os.rename(left, right)
        if not right.is_dir() or left.exists():
            raise OSError("same-parent rename did not publish exactly one directory")
    finally:
        if left.exists():
            left.rmdir()
        if right.exists():
            right.rmdir()
