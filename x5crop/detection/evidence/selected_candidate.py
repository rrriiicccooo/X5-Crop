from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import numpy as np

from ...cache import AnalysisCache
from ...domain import DetectionCandidate
from ...formats import FormatPhysicalSpec
from ...policies.parameters.outer import OuterAlignmentEvidenceParameters
from ...policies.runtime.content import ContentPolicy
from .content.frame_support import content_evidence_detail
from .content.support import frame_content_support_detail
from .frame_coverage import FrameCoverageEvidence, frame_coverage_evidence
from .outer_alignment import outer_content_alignment_detail


@dataclass(frozen=True)
class SelectedCandidateEvidence:
    candidate: DetectionCandidate
    content: dict[str, Any]
    outer_alignment: dict[str, Any]
    frame_coverage: FrameCoverageEvidence


def complete_selected_candidate_evidence(
    gray: np.ndarray,
    candidate: DetectionCandidate,
    cache: AnalysisCache,
    *,
    content_policy: ContentPolicy,
    alignment_parameters: OuterAlignmentEvidenceParameters,
    physical_spec: FormatPhysicalSpec,
) -> SelectedCandidateEvidence:
    candidate = deepcopy(candidate)
    if not isinstance(candidate.detail.get("exposure_overlap_evidence"), dict):
        raise ValueError("decision requires exposure_overlap_evidence")
    raw_content = content_evidence_detail(
        gray,
        candidate,
        cache,
        content_policy=content_policy,
        horizontal_frame_aspect=physical_spec.horizontal_content_aspect,
    )
    content = frame_content_support_detail(
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
    coverage = frame_coverage_evidence(candidate, physical_spec, cache, content_policy)
    candidate.detail["content_evidence"] = raw_content
    candidate.detail["frame_content_support"] = content
    candidate.detail["outer_content_alignment"] = outer_alignment
    return SelectedCandidateEvidence(
        candidate=candidate,
        content=content,
        outer_alignment=outer_alignment,
        frame_coverage=coverage,
    )
