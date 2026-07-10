from __future__ import annotations

from ..parameters.aggregate import FormatParameters
from ..runtime.exposure_overlap import ExposureOverlapEvidencePolicy


def exposure_overlap_evidence_policy(
    params: FormatParameters,
) -> ExposureOverlapEvidencePolicy:
    evidence = params.output.exposure_overlap_evidence
    return ExposureOverlapEvidencePolicy(
        model_gap_window_ratio=float(evidence.model_gap_window_ratio),
        model_gap_window_min_px=int(evidence.model_gap_window_min_px),
        model_gap_window_max_px=int(evidence.model_gap_window_max_px),
        mean_min=float(evidence.mean_min),
        weak_continuity=float(evidence.weak_continuity),
        weak_activity=float(evidence.weak_activity),
        medium_continuity=float(evidence.medium_continuity),
        medium_activity=float(evidence.medium_activity),
        strong_continuity=float(evidence.strong_continuity),
        strong_activity=float(evidence.strong_activity),
    )
