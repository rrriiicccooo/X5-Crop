from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ....formats import FormatPhysicalSpec
from ....strip_modes import FULL, PARTIAL
from ...evidence.count_planning import CountPlanningEvidence


@dataclass(frozen=True)
class CountHypothesis:
    count: int
    strip_mode: str
    offsets: tuple[float, ...]
    source: str
    physically_supported: bool

    def report_detail(self) -> dict[str, Any]:
        return {
            "count": int(self.count),
            "strip_mode": self.strip_mode,
            "offsets": [float(offset) for offset in self.offsets],
            "source": self.source,
            "physically_supported": bool(self.physically_supported),
        }


@dataclass(frozen=True)
class CountHypothesisPlan:
    hypotheses: tuple[CountHypothesis, ...]
    automatic: bool
    requested_count: int | None
    planning_evidence: CountPlanningEvidence

    @property
    def safety_count(self) -> int:
        if not self.hypotheses:
            raise ValueError("count hypothesis plan is empty")
        return int(self.hypotheses[0].count)

    def report_detail(self) -> dict[str, Any]:
        return {
            "automatic": bool(self.automatic),
            "requested_count": (
                None if self.requested_count is None else int(self.requested_count)
            ),
            "search_order": [int(hypothesis.count) for hypothesis in self.hypotheses],
            "hypotheses": [hypothesis.report_detail() for hypothesis in self.hypotheses],
            "planning_evidence": self.planning_evidence.report_detail(),
        }


def count_hypothesis_plan(
    *,
    strip_mode: str,
    requested_count: int | None,
    fmt: FormatPhysicalSpec,
    partial_offsets: tuple[float, ...],
    planning_evidence: CountPlanningEvidence,
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
                    (0.0,),
                    "format_default" if requested_count is None else "requested_count",
                    False,
                ),
            ),
            automatic=False,
            requested_count=requested_count,
            planning_evidence=planning_evidence,
        )
    if strip_mode != PARTIAL:
        raise ValueError(f"unsupported strip mode: {strip_mode}")
    if requested_count is not None:
        return CountHypothesisPlan(
            hypotheses=(
                CountHypothesis(
                    requested_count,
                    PARTIAL,
                    partial_offsets,
                    "requested_count",
                    False,
                ),
            ),
            automatic=False,
            requested_count=requested_count,
            planning_evidence=planning_evidence,
        )

    counts = tuple(
        count
        for count in reversed(fmt.allowed_counts)
        if count < fmt.default_count or fmt.complete_strip_can_be_underfilled
    )
    if not counts:
        raise ValueError(f"no automatic count hypotheses configured for {fmt.format_id}")
    supported_count = planning_evidence.supported_count
    if supported_count in counts:
        counts = (
            int(supported_count),
            *tuple(count for count in counts if count != supported_count),
        )
    return CountHypothesisPlan(
        hypotheses=tuple(
            CountHypothesis(
                count,
                PARTIAL,
                (
                    (0.0,)
                    if count == fmt.default_count
                    else planning_evidence.offsets_for_count(count) or partial_offsets
                ),
                "physical_count_evidence" if count == supported_count else "automatic_count",
                count == supported_count,
            )
            for count in counts
        ),
        automatic=True,
        requested_count=None,
        planning_evidence=planning_evidence,
    )
