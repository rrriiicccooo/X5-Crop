from __future__ import annotations

from ..constants import GAP_EQUAL
from ..domain import MeasurementProvenance, SeparatorBandObservation


def equal_model_gap(index: int, expected: float, score: float) -> SeparatorBandObservation:
    return SeparatorBandObservation(
        index=index,
        center=float(expected),
        score=float(score),
        method=GAP_EQUAL,
        provenance=MeasurementProvenance(
            root_measurement="geometry_model",
            source="equal_model",
            dependencies=("visible_sequence_span", "count", "placement"),
        ),
    )
