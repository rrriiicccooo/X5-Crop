from __future__ import annotations

from ...image.evidence import ContentEvidenceImageParameters
from ..parameters.aggregate import FormatParameters
from ..runtime.content import ContentPolicy


def content_policy(
    params: FormatParameters,
    *,
    evidence_image: ContentEvidenceImageParameters,
) -> ContentPolicy:
    return ContentPolicy(
        evidence_image=evidence_image,
        evidence=params.content.content_evidence,
        profile=params.content.content_profile,
        mask=params.content.content_mask,
        candidate=params.content.content_candidate,
        support=params.content.content_support,
    )
