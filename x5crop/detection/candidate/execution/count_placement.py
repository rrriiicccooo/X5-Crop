from __future__ import annotations

from ....cache import AnalysisCache
from ....domain import Box
from ....formats import FormatPhysicalSpec
from ....policies.runtime.policy import DetectionPolicy
from ...evidence.count_planning import supplemental_count_placement_evidence
from ...guidance.count_placement import content_count_placement_guidance
from ..plan.count_hypotheses import (
    CountHypothesis,
    CountHypothesisPlan,
    with_count_hypothesis_placement,
)


def resolve_automatic_count_placement(
    plan: CountHypothesisPlan,
    hypothesis: CountHypothesis,
    cache: AnalysisCache,
    fmt: FormatPhysicalSpec,
    policy: DetectionPolicy,
) -> tuple[CountHypothesisPlan, CountHypothesis]:
    if not plan.automatic or hypothesis.offsets:
        return plan, hypothesis

    if hypothesis.count == 1:
        source_outer = plan.planning_evidence.source_outer or Box(
            0,
            0,
            int(cache.gray_work.shape[1]),
            int(cache.gray_work.shape[0]),
        )
        guidance = content_count_placement_guidance(
            cache,
            fmt,
            hypothesis.count,
            source_outer,
            policy.content,
        )
        return with_count_hypothesis_placement(
            plan,
            hypothesis,
            guidance.offsets,
            guidance.source,
            guidance.detail,
        )

    evidence = supplemental_count_placement_evidence(
        cache.gray_work,
        fmt,
        hypothesis.count,
        cache,
        plan.planning_evidence,
        width_profile_parameters=policy.separator.width_profile_search,
    )
    if evidence.offsets:
        offsets = evidence.offsets
        source = evidence.source
        detail = evidence.detail
    else:
        source_outer = plan.planning_evidence.source_outer or Box(
            0,
            0,
            int(cache.gray_work.shape[1]),
            int(cache.gray_work.shape[0]),
        )
        guidance = content_count_placement_guidance(
            cache,
            fmt,
            hypothesis.count,
            source_outer,
            policy.content,
        )
        offsets = guidance.offsets
        source = guidance.source
        detail = {
            **guidance.detail,
            "separator_width_evidence": evidence.detail,
        }
    return with_count_hypothesis_placement(
        plan,
        hypothesis,
        offsets,
        source,
        detail,
    )
