from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from ....formats import FormatPhysicalSpec
from ....strip_modes import FULL, PARTIAL


class CountHypothesisSource(str, Enum):
    AUTOMATIC = "automatic_count"
    FORMAT_DEFAULT = "format_default"
    HARD_SAFETY = "hard_safety"
    MODE_CONTRACT = "mode_contract"
    REQUESTED = "requested_count"


@dataclass(frozen=True)
class CountHypothesis:
    count: int
    strip_mode: str
    source: CountHypothesisSource

    def __post_init__(self) -> None:
        if self.count <= 0:
            raise ValueError("count hypothesis must be positive")
        if self.strip_mode not in {FULL, PARTIAL}:
            raise ValueError(f"unsupported count hypothesis mode: {self.strip_mode}")
        if not isinstance(self.source, CountHypothesisSource):
            raise ValueError("count hypothesis requires a typed source")


@dataclass(frozen=True)
class CountHypothesisPlan:
    hypotheses: tuple[CountHypothesis, ...]
    automatic: bool
    requested_count: int | None

    def __post_init__(self) -> None:
        if not self.hypotheses:
            raise ValueError("count hypothesis plan requires hypotheses")
        counts = tuple(hypothesis.count for hypothesis in self.hypotheses)
        if len(set(counts)) != len(counts):
            raise ValueError("count hypothesis plan counts must be unique")
        modes = {hypothesis.strip_mode for hypothesis in self.hypotheses}
        if len(modes) != 1:
            raise ValueError("count hypothesis plan requires one strip mode")
        if self.automatic:
            if self.requested_count is not None or any(
                hypothesis.source != CountHypothesisSource.AUTOMATIC
                for hypothesis in self.hypotheses
            ):
                raise ValueError("automatic count plan has inconsistent ownership")
            if counts != tuple(sorted(counts, reverse=True)):
                raise ValueError("automatic count plan must search larger counts first")
        else:
            if len(self.hypotheses) != 1:
                raise ValueError("fixed count plan requires exactly one hypothesis")
            hypothesis = self.hypotheses[0]
            expected_source = (
                CountHypothesisSource.REQUESTED
                if self.requested_count is not None
                else CountHypothesisSource.FORMAT_DEFAULT
            )
            if hypothesis.source != expected_source or (
                self.requested_count is not None
                and hypothesis.count != self.requested_count
            ):
                raise ValueError("fixed count plan has inconsistent ownership")

    @property
    def hard_safety_count(self) -> int:
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
