from __future__ import annotations

from ..runtime.output import OutputPolicy


def output_policy() -> OutputPolicy:
    return OutputPolicy()


__all__ = [
    "output_policy",
]
