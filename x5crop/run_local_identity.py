"""Readable identities scoped to one source-processing run."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from collections.abc import Hashable, Iterable, Iterator


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
def source_identity_scope(*, reserved_ids: Iterable[str] = (),
                          registered_keys: Iterable[tuple[str, tuple[Hashable, ...], str]] = ()) -> Iterator[None]:
    """Start one source, optionally restoring registered identities for replay.

    Reservations only prevent name collisions. Registered keys restore the
    same physical observation's existing name; neither operation grants any
    measurement or output authority.
    """
    scope = _IdentityScope()
    registered_names = {}
    for identity in reserved_ids:
        prefix, separator, ordinal = identity.rpartition(":")
        if separator and prefix and ordinal.isdecimal():
            scope.next_ordinal[prefix] = max(scope.next_ordinal.get(prefix, 0), int(ordinal))
    for prefix, parts, identity in registered_keys:
        name, separator, ordinal = identity.rpartition(":")
        if not separator or name != prefix or not ordinal.isdecimal() or int(ordinal) < 1:
            raise ValueError("registered run-local identity is invalid")
        key = (prefix, parts)
        if key in scope.identities and scope.identities[key] != identity:
            raise ValueError("registered physical key has conflicting identities")
        if identity in registered_names and registered_names[identity] != key:
            raise ValueError("registered identity aliases different physical keys")
        registered_names[identity] = key
        scope.identities[key] = identity
        scope.next_ordinal[prefix] = max(scope.next_ordinal.get(prefix, 0), int(ordinal))
    token = _CURRENT_SCOPE.set(scope)
    try:
        yield
    finally:
        _CURRENT_SCOPE.reset(token)
