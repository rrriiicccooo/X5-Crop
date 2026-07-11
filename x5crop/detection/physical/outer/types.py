from __future__ import annotations

from dataclasses import dataclass

from ....domain import Box, MeasurementProvenance


@dataclass(frozen=True)
class OuterProposal:
    name: str
    box: Box
    strategy: str
    provenance: MeasurementProvenance
