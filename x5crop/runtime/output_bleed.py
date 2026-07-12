from __future__ import annotations

from ..domain import AxisBleedParameters, OutputBleedPlan
from ..detection.candidate.model import AssessedCandidate
from ..detection.context import DetectionContext
from ..output.bleed_plan import output_bleed_plan


def prepare_output_bleed(
    candidate: AssessedCandidate,
    context: DetectionContext,
    base_bleed: AxisBleedParameters,
) -> OutputBleedPlan:
    spacings = candidate.assessment.evidence.frame_sequence.spacings
    overlaps = tuple(
        spacing
        for spacing in spacings
        if spacing.kind == "overlap" and spacing.independently_observed
    )
    widest_overlap_band_px = max(
        (-float(spacing.signed_width_px.minimum) for spacing in overlaps),
        default=0.0,
    )
    geometry = candidate.geometry
    long_axis = "x" if geometry.layout == "horizontal" else "y"
    long_axis_bleed_capacity_px = (
        context.policy.output.long_axis_bleed_capacity.resolve_px(
            context.scan_calibration,
            axis=long_axis,
            reference_px=max(
                1.0,
                float(geometry.frame_dimension_prior.width_px.midpoint),
            ),
        )
    )
    return output_bleed_plan(
        bool(overlaps),
        widest_overlap_band_px,
        base_bleed,
        context.policy.output,
        long_axis_bleed_capacity_px=long_axis_bleed_capacity_px,
    )
