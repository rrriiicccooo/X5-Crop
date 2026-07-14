from __future__ import annotations

from ....formats import FormatPhysicalSpec
from ....strip_modes import FULL, PARTIAL
from .model import CountHypothesis, CountHypothesisPlan, CountHypothesisSource


def count_hypothesis_plan(
    *,
    strip_mode: str,
    requested_count: int | None,
    fmt: FormatPhysicalSpec,
) -> CountHypothesisPlan:
    if requested_count is not None and requested_count not in fmt.allowed_counts:
        raise ValueError(f"count {requested_count} is not allowed for {fmt.format_id}")

    if strip_mode == FULL:
        count = fmt.default_count if requested_count is None else requested_count
        return CountHypothesisPlan(
            hypotheses=(
                CountHypothesis(
                    count,
                    FULL,
                    (
                        CountHypothesisSource.FORMAT_DEFAULT
                        if requested_count is None
                        else CountHypothesisSource.REQUESTED
                    ),
                ),
            ),
            automatic=False,
            requested_count=requested_count,
        )
    if strip_mode != PARTIAL:
        raise ValueError(f"unsupported strip mode: {strip_mode}")
    if requested_count is not None:
        return CountHypothesisPlan(
            hypotheses=(
                CountHypothesis(
                    requested_count,
                    PARTIAL,
                    CountHypothesisSource.REQUESTED,
                ),
            ),
            automatic=False,
            requested_count=requested_count,
        )

    counts = tuple(
        count
        for count in reversed(fmt.allowed_counts)
        if count < fmt.default_count or fmt.complete_strip_can_be_underfilled
    )
    if not counts:
        raise ValueError(f"no automatic count hypotheses configured for {fmt.format_id}")
    return CountHypothesisPlan(
        hypotheses=tuple(
            CountHypothesis(
                count,
                PARTIAL,
                CountHypothesisSource.AUTOMATIC,
            )
            for count in counts
        ),
        automatic=True,
        requested_count=None,
    )
