"""Readable identities scoped to one source-processing run."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from collections.abc import Hashable, Iterator


@dataclass
class _IdentityScope:
    identities: dict[tuple[str, tuple[Hashable, ...]], str] = field(
        default_factory=dict
    )
    next_ordinal: dict[str, int] = field(default_factory=dict)

    def identity(self, prefix: str, parts: tuple[object, ...]) -> str:
        if not all(isinstance(part, Hashable) for part in parts):
            raise TypeError("run-local identity fields must be hashable")
        key = (prefix, parts)
        existing = self.identities.get(key)
        if existing is not None:
            return existing
        ordinal = self.next_ordinal.get(prefix, 0) + 1
        self.next_ordinal[prefix] = ordinal
        value = f"{prefix}:{ordinal}"
        self.identities[key] = value
        return value


_CURRENT_SCOPE: ContextVar[_IdentityScope | None] = ContextVar(
    "x5crop_run_local_identity_scope",
    default=None,
)


def run_local_id(prefix: str, *parts: object) -> str:
    if not prefix:
        raise ValueError("run-local identity prefix is empty")
    scope = _CURRENT_SCOPE.get()
    if scope is None:
        scope = _IdentityScope()
        _CURRENT_SCOPE.set(scope)
    return scope.identity(prefix, parts)


@contextmanager
def source_identity_scope() -> Iterator[None]:
    token = _CURRENT_SCOPE.set(_IdentityScope())
    try:
        yield
    finally:
        _CURRENT_SCOPE.reset(token)
