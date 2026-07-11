from __future__ import annotations

from dataclasses import dataclass

from ..domain import AxisBleedParameters, OutputProtectionPlan
from ..detection.candidate.model import AssessedCandidate
from ..detection.evidence.exposure_overlap import (
    ExposureOverlapEvidence,
    exposure_overlap_evidence,
)
from ..detection.context import DetectionContext
from ..output.protection import output_protection_plan


@dataclass(frozen=True)
class PreparedOutputProtection:
    evidence: ExposureOverlapEvidence
    plan: OutputProtectionPlan


def prepare_output_protection(
    candidate: AssessedCandidate,
    context: DetectionContext,
    base_bleed: AxisBleedParameters,
) -> PreparedOutputProtection:
    evidence = exposure_overlap_evidence(
        candidate.geometry,
        context.measurement_cache,
        separator_policy=context.policy.separator,
        parameters=context.policy.exposure_overlap_evidence,
    )
    geometry = candidate.geometry
    long_axis = "x" if geometry.layout == "horizontal" else "y"
    long_axis_bleed_capacity_px = (
        context.policy.output.exposure_overlap_protection.long_axis_bleed_capacity.resolve_px(
            context.scan_calibration,
            axis=long_axis,
            reference_px=max(1.0, float(geometry.pitch)),
        )
    )
    plan = output_protection_plan(
        evidence.detected,
        evidence.widest_overlap_band_px,
        base_bleed,
        context.policy.output.exposure_overlap_protection,
        long_axis_bleed_capacity_px=long_axis_bleed_capacity_px,
    )
    return PreparedOutputProtection(evidence=evidence, plan=plan)
