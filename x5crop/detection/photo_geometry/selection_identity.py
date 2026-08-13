"""Readable source-run identities for chain-selection facts."""

from __future__ import annotations

from ...run_local_identity import run_local_id


def selection_fact_id(prefix: str, fields: tuple[str, ...]) -> str:
    return run_local_id(prefix, *fields)
