from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ....formats import FormatPhysicalSpec
from ....geometry.detection_parameters import HardGapTrustParameters
from ....policies.runtime.candidate import ScoringPolicy
from ....units import ScanCalibration
from ...evidence.frame_topology import FrameTopologyEvidence, frame_topology_evidence
from ...evidence.separator_continuity import (
    SeparatorContinuityEvidence,
    separator_cross_axis_continuity_evidence,
    supported_hard_separator_observations,
)
from ...physical.photo_size import (
    FrameDimensionEvidence,
    frame_dimension_evidence,
)
from ..model import BuiltCandidate


@dataclass(frozen=True)
class BasePhysicalAssessment:
    confidence: float
    frame_topology: FrameTopologyEvidence
    separator_continuity: SeparatorContinuityEvidence
    frame_dimensions: FrameDimensionEvidence


def base_physical_assessment(
    gray_work: np.ndarray,
    candidate: BuiltCandidate,
    physical_spec: FormatPhysicalSpec,
    calibration: ScanCalibration,
    scoring_policy: ScoringPolicy,
    hard_gap_trust: HardGapTrustParameters,
) -> BasePhysicalAssessment:
    geometry = candidate.geometry
    topology = frame_topology_evidence(
        geometry.frames,
        geometry.count,
    )
    continuity = separator_cross_axis_continuity_evidence(
        gray_work,
        geometry.visible_sequence_span.box,
        geometry.separators,
        geometry.pitch,
        hard_gap_trust,
    )
    supported_separators = supported_hard_separator_observations(continuity)
    frame_dimensions = frame_dimension_evidence(
        geometry,
        physical_spec,
        calibration,
        separator_observations=supported_separators,
        maximum_photo_width_cv=(
            scoring_policy.base_detection.unstable_photo_width_cv
        ),
        maximum_dimension_error_ratio=(
            scoring_policy.geometry_support.aspect_norm
        ),
    )
    expected = max(0, geometry.count - 1)
    hard_count = len(supported_separators)
    separator_score = 1.0 if expected == 0 else min(
        1.0,
        float(hard_count) / float(expected),
    )
    if frame_dimensions.photo_width_cv is not None:
        width_score = max(
            0.0,
            min(
                1.0,
                1.0
                - float(frame_dimensions.photo_width_cv)
                / float(scoring_policy.base_detection.photo_width_cv_norm),
            ),
        )
        confidence = (
            float(scoring_policy.base_detection.gap_weight) * separator_score
            + float(scoring_policy.base_detection.photo_width_weight) * width_score
        ) / max(
            1e-6,
            float(scoring_policy.base_detection.gap_weight)
            + float(scoring_policy.base_detection.photo_width_weight),
        )
    else:
        confidence = separator_score
    return BasePhysicalAssessment(
        confidence=float(max(0.0, min(1.0, confidence))),
        frame_topology=topology,
        separator_continuity=continuity,
        frame_dimensions=frame_dimensions,
    )
