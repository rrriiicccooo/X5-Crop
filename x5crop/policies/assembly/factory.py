from __future__ import annotations

from ...formats import FormatPhysicalSpec
from ...image.evidence import (
    ContentEvidenceImageParameters,
    DeskewFallbackEvidenceParameters,
    SeparatorEvidenceImageParameters,
)
from ...image.gray import BaseGrayParameters
from ..parameters.aggregate import FormatParameters
from ...strip_modes import FULL, PARTIAL
from .candidate import partial_holder_policy
from .outer import outer_policy
from .separator import separator_policy
from ..runtime.candidate import ScoringPolicy
from ..runtime.content import ContentPolicy
from ..runtime.diagnostics import RuntimeDiagnosticsPolicy
from ..runtime.output import OutputPolicy
from ..runtime.policy import DetectionPolicy
from ..runtime.preprocess import RuntimePreprocessPolicy


def _detector_kind(spec: FormatPhysicalSpec, strip_mode: str) -> str:
    if spec.physical_layout == "dual_lane" and strip_mode == FULL:
        return "dual_lane"
    if spec.physical_layout == "dual_lane" and strip_mode == PARTIAL:
        return "review_only"
    return "standard_strip"


def build_detection_policy(
    spec: FormatPhysicalSpec,
    params: FormatParameters,
    strip_mode: str,
) -> DetectionPolicy:
    detector_kind = _detector_kind(spec, strip_mode)
    preprocess = RuntimePreprocessPolicy(
        base_gray=BaseGrayParameters(),
        deskew=params.preprocess.deskew,
        deskew_fallback_evidence=DeskewFallbackEvidenceParameters(),
        separator_evidence_image=SeparatorEvidenceImageParameters(),
        content_evidence_image=ContentEvidenceImageParameters(),
    )
    separator = separator_policy(strip_mode, detector_kind, params)
    return DetectionPolicy(
        physical_spec=spec,
        strip_mode=strip_mode,
        preprocess=preprocess,
        detector_kind=detector_kind,
        partial_count_offsets=params.candidate.partial_counts.offsets,
        outer=outer_policy(detector_kind, strip_mode, params),
        separator=separator,
        content=ContentPolicy(
            evidence_image=preprocess.content_evidence_image,
            evidence=params.content.content_evidence,
            profile=params.content.content_profile,
            mask=params.content.content_mask,
            candidate=params.content.content_candidate,
            support=params.content.content_support,
        ),
        partial_holder=partial_holder_policy(detector_kind, strip_mode, params),
        partial_edge_hint=params.candidate.partial_edge_hint,
        frame_fit=(
            params.candidate.partial_frame_fit
            if strip_mode == "partial"
            else params.candidate.full_frame_fit
        ),
        scoring=ScoringPolicy(
            calibration=params.candidate.scoring_calibration,
            base_detection=params.candidate.base_detection_score,
            geometry_support=params.candidate.geometry_support_score,
            separator_support=params.candidate.separator_support_score,
        ),
        candidate_selection=params.candidate.selection_consensus,
        candidate_plan=params.candidate.candidate_plan,
        exposure_overlap_evidence=params.output.exposure_overlap_evidence,
        approved_geometry_adjustment=params.output.approved_geometry_adjustment,
        output=OutputPolicy(
            exposure_overlap_protection=params.output.exposure_overlap_protection,
            edge_bleed_protection=params.output.edge_bleed_protection,
        ),
        diagnostics=RuntimeDiagnosticsPolicy(
            debug_gap_overlay=params.diagnostics.debug_gap_overlay,
            nearby_separator_search=params.separator.nearby_separator_refinement,
            nearby_separator_comparison=params.diagnostics.nearby_separator_diagnostics,
        ),
    )
