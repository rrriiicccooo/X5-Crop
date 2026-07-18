from __future__ import annotations

from ....formats import FormatSpec
from ....strip_modes import FULL, PARTIAL
from .model import CountHypothesis, CountHypothesisPlan, CountHypothesisSource


def count_hypothesis_plan(
    *,
    strip_mode: str,
    requested_count: int | None,
    fmt: FormatSpec,
) -> CountHypothesisPlan:
    if strip_mode == FULL:
        if requested_count is not None and requested_count != fmt.strip.default_count:
            raise ValueError(
                f"full mode for {fmt.format_id} requires the nominal count "
                f"{fmt.strip.default_count}"
            )
        count = fmt.strip.default_count
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
        if requested_count not in fmt.strip.allowed_partial_counts:
            raise ValueError(
                f"partial count {requested_count} is not allowed for {fmt.format_id}"
            )
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
        for count in reversed(fmt.strip.allowed_partial_counts)
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
