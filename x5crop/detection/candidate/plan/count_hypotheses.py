from __future__ import annotations

from dataclasses import dataclass, replace
from ....formats import FormatPhysicalSpec
from ....strip_modes import FULL, PARTIAL
from ...evidence.count_planning import CountPlanningEvidence


@dataclass(frozen=True)
class CountHypothesis:
    count: int
    strip_mode: str
    offsets: tuple[float, ...]
    placement_source: str
    source: str
    allowed_by_physical_spec: bool


@dataclass(frozen=True)
class CountHypothesisPlan:
    hypotheses: tuple[CountHypothesis, ...]
    automatic: bool
    requested_count: int | None
    planning_evidence: CountPlanningEvidence

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
                    "offset_not_applicable",
                    "format_default" if requested_count is None else "requested_count",
                    True,
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
                    "configured_partial_offsets",
                    "requested_count",
                    True,
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
    return CountHypothesisPlan(
        hypotheses=tuple(
            CountHypothesis(
                count,
                PARTIAL,
                (
                    (0.0,)
                    if count == fmt.default_count
                    else planning_evidence.offsets_for_count(count)
                ),
                (
                    "offset_not_applicable"
                    if count == fmt.default_count
                    else (
                        "hard_separator_bands"
                        if planning_evidence.offsets_for_count(count)
                        else "deferred"
                    )
                ),
                "automatic_count",
                True,
            )
            for count in counts
        ),
        automatic=True,
        requested_count=None,
        planning_evidence=planning_evidence,
    )


def with_count_hypothesis_placement(
    plan: CountHypothesisPlan,
    hypothesis: CountHypothesis,
    offsets: tuple[float, ...],
    placement_source: str,
) -> tuple[CountHypothesisPlan, CountHypothesis]:
    resolved = replace(
        hypothesis,
        offsets=tuple(float(offset) for offset in offsets),
        placement_source=str(placement_source),
    )
    hypotheses = tuple(
        resolved if item.count == hypothesis.count else item
        for item in plan.hypotheses
    )
    return replace(plan, hypotheses=hypotheses), resolved
