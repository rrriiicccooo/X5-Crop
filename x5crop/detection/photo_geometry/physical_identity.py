"""Readable source-run identities for physical-chain facts."""

from __future__ import annotations

from ...domain import ObservationId
from ...run_local_identity import run_local_id


def physical_fact_id(prefix: str, *parts: object) -> str:
    return run_local_id(prefix, *parts)


def physical_observation_id(prefix: str, *parts: object) -> ObservationId:
    return ObservationId(run_local_id(prefix, *parts))
