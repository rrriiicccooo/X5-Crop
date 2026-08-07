from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import stat


@dataclass(frozen=True)
class InventoryEntry:
    relative_path: str
    kind: str
    role: str | None = None
    size: int | None = None
    mtime_ns: int | None = None

    def __post_init__(self) -> None:
        if not self.relative_path or self.relative_path.startswith(("/", "../")):
            raise ValueError("inventory path must be relative and contained")
        if self.kind == "file":
            if self.role is None or self.size is None or self.mtime_ns is None:
                raise ValueError("file inventory requires role, size, and mtime")
        elif self.kind == "directory":
            if any(value is not None for value in (self.role, self.size, self.mtime_ns)):
                raise ValueError("directory inventory contains unstable identity")
        else:
            raise ValueError("inventory kind must be file or directory")

    def as_record(self) -> dict[str, object]:
        record: dict[str, object] = {
            "relative_path": self.relative_path,
            "kind": self.kind,
        }
        if self.kind == "file":
            record.update(
                role=self.role,
                size=self.size,
                mtime_ns=self.mtime_ns,
            )
        return record


class UnsafeOutputTreeError(RuntimeError):
    pass


def _is_reparse_point(info: os.stat_result) -> bool:
    attributes = int(getattr(info, "st_file_attributes", 0))
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    return bool(os.name == "nt" and attributes & reparse_flag)


def _is_junction(path: Path) -> bool:
    predicate = getattr(path, "is_junction", None)
    return bool(os.name == "nt" and predicate is not None and predicate())


def _assert_safe_entry(path: Path, *, is_symlink: bool, info: os.stat_result) -> None:
    if is_symlink or _is_junction(path) or _is_reparse_point(info):
        raise UnsafeOutputTreeError(
            f"Refusing linked or reparse output path: {path}"
        )
    if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
        raise UnsafeOutputTreeError(f"Refusing non-file output path: {path}")


def assert_safe_root(path: Path) -> os.stat_result:
    try:
        info = path.lstat()
    except FileNotFoundError:
        raise UnsafeOutputTreeError(f"Output path does not exist: {path}") from None
    _assert_safe_entry(path, is_symlink=path.is_symlink(), info=info)
    if not stat.S_ISDIR(info.st_mode):
        raise UnsafeOutputTreeError(f"Output root is not a directory: {path}")
    return info


def inventory_tree(
    root: Path,
    *,
    manifest_name: str,
    role_for_file,
) -> tuple[InventoryEntry, ...]:
    assert_safe_root(root)
    records: list[InventoryEntry] = []

    def visit(directory: Path) -> None:
        with os.scandir(directory) as entries:
            for entry in sorted(entries, key=lambda item: item.name.casefold()):
                path = Path(entry.path)
                info = entry.stat(follow_symlinks=False)
                _assert_safe_entry(path, is_symlink=entry.is_symlink(), info=info)
                relative = path.relative_to(root).as_posix()
                if relative == manifest_name:
                    continue
                if stat.S_ISDIR(info.st_mode):
                    records.append(InventoryEntry(relative, "directory"))
                    visit(path)
                else:
                    records.append(
                        InventoryEntry(
                            relative,
                            "file",
                            role=str(role_for_file(Path(relative))),
                            size=int(info.st_size),
                            mtime_ns=int(info.st_mtime_ns),
                        )
                    )

    visit(root)
    return tuple(sorted(records, key=lambda item: item.relative_path.casefold()))


def safe_remove_tree(root: Path) -> None:
    """Remove an already-owned tree without ever following links."""

    assert_safe_root(root)

    def remove(directory: Path) -> None:
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                info = entry.stat(follow_symlinks=False)
                _assert_safe_entry(path, is_symlink=entry.is_symlink(), info=info)
                if stat.S_ISDIR(info.st_mode):
                    remove(path)
                    path.rmdir()
                else:
                    path.unlink()

    remove(root)
    root.rmdir()
