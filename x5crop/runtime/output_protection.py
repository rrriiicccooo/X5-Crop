from __future__ import annotations

import numpy as np

from ..cache import AnalysisCache
from ..domain import DetectionCandidate
from ..detection.evidence.exposure_overlap import exposure_overlap_evidence_detail
from ..output.protection import (
    AxisBleedParameters,
    OutputProtectionPlan,
    output_protection_plan,
)
from ..policies.runtime.policy import DetectionPolicy
from ..run_config import RunConfig


def prepare_output_protection(
    gray: np.ndarray,
    detection: DetectionCandidate,
    config: RunConfig,
    analysis_cache: AnalysisCache,
    policy: DetectionPolicy,
) -> OutputProtectionPlan:
    evidence = exposure_overlap_evidence_detail(
        gray,
        detection,
        analysis_cache,
        separator_policy=policy.separator,
        exposure_overlap_policy=policy.exposure_overlap_evidence,
    )
    plan = output_protection_plan(
        evidence,
        AxisBleedParameters(
            long_axis=int(config.bleed_x),
            short_axis=int(config.bleed_y),
        ),
        policy.output,
    )
    detection.detail["exposure_overlap_evidence"] = evidence
    detection.detail["output_protection_plan"] = plan.report_detail()
    return plan
