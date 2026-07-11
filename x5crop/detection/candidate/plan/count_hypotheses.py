from __future__ import annotations

from dataclasses import dataclass
from ....formats import FormatPhysicalSpec
from ....strip_modes import FULL, PARTIAL


@dataclass(frozen=True)
class CountHypothesis:
    count: int
    strip_mode: str
    source: str
    allowed_by_physical_spec: bool


@dataclass(frozen=True)
class CountHypothesisPlan:
    hypotheses: tuple[CountHypothesis, ...]
    automatic: bool
    requested_count: int | None

    @property
    def hard_safety_count(self) -> int:
        if not self.hypotheses:
            raise ValueError("count hypothesis plan is empty")
        return int(self.hypotheses[0].count)

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
                    "format_default" if requested_count is None else "requested_count",
                    True,
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
                    "requested_count",
                    True,
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
                "automatic_count",
                True,
            )
            for count in counts
        ),
        automatic=True,
        requested_count=None,
    )
