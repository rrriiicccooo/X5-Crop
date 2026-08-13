"""Development-only filesystem identity for platform receipts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path
import platform
import re
import subprocess


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


def _command_kind(args: tuple[str, ...], pattern: str | None = None) -> str:
    try:
        completed = subprocess.run(
            args,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    if pattern is None:
        return completed.stdout.strip().lower() or "unknown"
    match = re.search(pattern, completed.stdout)
    return "unknown" if match is None else match.group(1).strip().lower()


def _filesystem_kind(path: Path) -> str:
    system = platform.system().lower()
    if os.name == "nt":
        try:
            import ctypes

            buffer = ctypes.create_unicode_buffer(64)
            root = Path(path.anchor or path.drive + "\\")
            ok = ctypes.windll.kernel32.GetVolumeInformationW(
                str(root), None, 0, None, None, None, buffer, len(buffer)
            )
            return buffer.value.lower() if ok else "unknown"
        except Exception:
            return "unknown"
    if system != "darwin":
        return _command_kind(("stat", "-f", "-c", "%T", str(path)))
    try:
        completed = subprocess.run(
            ("/sbin/mount",),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    resolved = path.resolve()
    matches: list[tuple[int, str]] = []
    for line in completed.stdout.splitlines():
        match = re.search(r" on (.+) \(([^,()]+)(?:,|\))", line)
        if match is None:
            continue
        mount = Path(match.group(1).replace("\\040", " "))
        try:
            resolved.relative_to(mount)
        except ValueError:
            continue
        matches.append((len(mount.parts), match.group(2).strip().lower()))
    return max(matches, default=(0, "unknown"))[1]


def identify_filesystem(path: Path) -> FilesystemIdentity:
    resolved = path.resolve()
    system = platform.system().lower()
    kind = _filesystem_kind(resolved)
    normalized = "/" + resolved.as_posix().casefold().strip("/") + "/"
    cloud = any(
        marker in normalized
        for marker in (
            "/library/cloudstorage/",
            "/onedrive/",
            "/dropbox/",
            "/google drive/",
        )
    )
    network = any(
        marker in kind
        for marker in ("smbfs", "smb", "nfs", "afpfs", "cifs", "webdav", "fuse")
    )
    verified = (
        not cloud
        and not network
        and (
            (system == "darwin" and kind in {"apfs", "hfs", "hfs+"})
            or (system == "windows" and kind == "ntfs")
        )
    )
    return FilesystemIdentity(
        system,
        kind,
        OutputSupportLevel.VERIFIED_LOCAL
        if verified
        else OutputSupportLevel.BEST_EFFORT_UNVERIFIED,
        "verified local filesystem" if verified else "unverified platform filesystem",
    )
