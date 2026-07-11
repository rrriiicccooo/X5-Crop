from __future__ import annotations

from ....cache import MeasurementCache
from ....domain import Box
from ....formats import FormatPhysicalSpec
from ....policies.runtime.content import ContentPolicy
from ....geometry.detection_parameters import (
    SeparatorWidthProfileSearchParameters,
)
from ....units import ScanCalibration
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
    cache: MeasurementCache,
    fmt: FormatPhysicalSpec,
    content_policy: ContentPolicy,
    width_profile_parameters: SeparatorWidthProfileSearchParameters,
    calibration: ScanCalibration,
    long_axis: str,
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
            content_policy,
        )
        return with_count_hypothesis_placement(
            plan,
            hypothesis,
            guidance.offsets,
            guidance.source,
        )

    evidence = supplemental_count_placement_evidence(
        fmt,
        hypothesis.count,
        cache,
        plan.planning_evidence,
        width_profile_parameters=width_profile_parameters,
        calibration=calibration,
        long_axis=long_axis,
    )
    if evidence.offsets:
        offsets = evidence.offsets
        source = evidence.source
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
            content_policy,
        )
        offsets = guidance.offsets
        source = guidance.source
    return with_count_hypothesis_placement(
        plan,
        hypothesis,
        offsets,
        source,
    )
