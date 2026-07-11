from __future__ import annotations

from ....policies.parameters.content import ContentSupportParameters
from ....policies.runtime.candidate import ScoringPolicy
from ..model import CandidateEvidence, CandidateScores


def candidate_scores(
    evidence: CandidateEvidence,
    source: str,
    base_confidence: float,
    scoring_policy: ScoringPolicy,
    content_support: ContentSupportParameters,
) -> CandidateScores:
    content_policy = content_support
    if evidence.frame_content.median_mean is None:
        content = 0.0
    else:
        mean_score = min(
            1.0,
            float(evidence.frame_content.median_mean) / content_policy.mean_norm,
        )
        coverage_score = min(
            1.0,
            float(evidence.frame_content.median_coverage or 0.0)
            / content_policy.coverage_norm,
        )
        content = max(
            0.0,
            min(
                1.0,
                content_policy.coverage_weight * coverage_score
                + content_policy.mean_weight * mean_score,
            ),
        )

    dimensions = evidence.frame_dimensions
    width_score = (
        None
        if dimensions.photo_width_cv is None
        else max(
            0.0,
            min(
                1.0,
                1.0
                - float(dimensions.photo_width_cv)
                / scoring_policy.geometry_support.photo_width_cv_norm,
            ),
        )
    )
    aspect_score = (
        None
        if dimensions.maximum_dimension_error_ratio is None
        else max(
            0.0,
            min(
                1.0,
                1.0
                - float(dimensions.maximum_dimension_error_ratio)
                / scoring_policy.geometry_support.aspect_norm,
            ),
        )
    )
    weighted_geometry: list[tuple[float, float]] = [
        (
            scoring_policy.geometry_support.count_weight,
            1.0 if evidence.frame_topology.count_matches else 0.0,
        )
    ]
    if width_score is not None:
        weighted_geometry.append(
            (scoring_policy.geometry_support.photo_width_weight, width_score)
        )
    if aspect_score is not None:
        weighted_geometry.append(
            (scoring_policy.geometry_support.aspect_weight, aspect_score)
        )
    geometry_weight = max(
        1e-6,
        sum(weight for weight, _score in weighted_geometry),
    )
    geometry = sum(
        weight * score for weight, score in weighted_geometry
    ) / geometry_weight

    sequence = evidence.separator_sequence
    if sequence.expected_count == 0:
        separator = 0.0
    else:
        hard_ratio = min(
            1.0,
            float(sequence.hard_count) / float(sequence.expected_count),
        )
        model_ratio = min(
            1.0,
            float(sequence.hard_count)
            + scoring_policy.separator_support.model_equal_credit
            * float(sequence.model_count),
        ) / float(sequence.expected_count)
        separator = (
            scoring_policy.separator_support.hard_weight * hard_ratio
            + scoring_policy.separator_support.model_weight * model_ratio
        )

    calibration = scoring_policy.calibration
    joint = (
        calibration.geometry_weight * geometry
        + calibration.content_weight * content
        + calibration.separator_weight * separator
        + (calibration.separator_source_bias if source == "separator" else 0.0)
    )
    joint = float(max(0.0, min(1.0, joint)))
    confidence = float(max(0.0, min(1.0, max(base_confidence, joint))))
    return CandidateScores(
        confidence=confidence,
        base=float(base_confidence),
        geometry=float(geometry),
        separator=float(separator),
        content=float(content),
        joint=joint,
    )
