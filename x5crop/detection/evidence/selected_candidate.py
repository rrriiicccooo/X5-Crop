from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import numpy as np

from ...cache import AnalysisCache
from ...domain import DetectionCandidate
from ...policies.parameters.outer import OuterAlignmentEvidenceParameters
from ...policies.runtime.content import ContentPolicy
from .content.containment import content_containment_detail
from .content.frame_support import content_evidence_detail
from .outer_alignment import outer_content_alignment_detail


@dataclass(frozen=True)
class SelectedCandidateEvidence:
    candidate: DetectionCandidate
    content: dict[str, Any]
    outer_alignment: dict[str, Any]


def complete_selected_candidate_evidence(
    gray: np.ndarray,
    candidate: DetectionCandidate,
    cache: AnalysisCache,
    *,
    content_policy: ContentPolicy,
    alignment_parameters: OuterAlignmentEvidenceParameters,
    horizontal_frame_aspect: float,
) -> SelectedCandidateEvidence:
    candidate = deepcopy(candidate)
    if not isinstance(candidate.detail.get("exposure_overlap_evidence"), dict):
        raise ValueError("decision requires exposure_overlap_evidence")
    if not isinstance(candidate.detail.get("output_protection_plan"), dict):
        raise ValueError("decision requires output_protection_plan")

    raw_content = content_evidence_detail(
        gray,
        candidate,
        cache,
        content_policy=content_policy,
        horizontal_frame_aspect=horizontal_frame_aspect,
    )
    content = content_containment_detail(
        raw_content,
        content_policy.evidence,
        expected_count=candidate.count,
    )
    outer_alignment = outer_content_alignment_detail(
        gray,
        candidate,
        cache,
        alignment_policy=alignment_parameters,
    )
    candidate.detail["content_evidence"] = raw_content
    candidate.detail["content_containment"] = content
    candidate.detail["outer_content_alignment"] = outer_alignment
    return SelectedCandidateEvidence(
        candidate=candidate,
        content=content,
        outer_alignment=outer_alignment,
    )
