from __future__ import annotations

from ..constants import GAP_CONTENT, GAP_EQUAL
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
            dependencies=("film_span", "count", "placement"),
        ),
    )




def content_model_gap(
    index: int,
    center: float,
    score: float,
    start: float | None = None,
    end: float | None = None,
) -> SeparatorBandObservation:
    return SeparatorBandObservation(
        index=index,
        center=float(center),
        score=float(score),
        method=GAP_CONTENT,
        provenance=MeasurementProvenance(
            root_measurement="content_guidance",
            source="content_model",
            dependencies=("content_evidence", "count", "placement"),
        ),
        start=None if start is None else float(start),
        end=None if end is None else float(end),
    )
