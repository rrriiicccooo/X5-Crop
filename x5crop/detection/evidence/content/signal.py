from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from ....image.evidence import make_content_evidence_gray
from ....policies.registry import get_detection_policy
from ....policies.runtime.content import ContentEvidencePolicy, ContentPolicy
from ....utils import sampled_percentile

CONTENT_SIGNAL_COMPOSITE = "gradient+neighbor_texture+local_contrast+tonal_presence"
CACHED_CONTENT_SIGNAL_COMPOSITE = "cached_" + CONTENT_SIGNAL_COMPOSITE


@dataclass(frozen=True)
class ContentSignal:
    evidence_u8: np.ndarray
    evidence_float: np.ndarray
    composite: str = CONTENT_SIGNAL_COMPOSITE


def resolve_content_policy(
    format_name: str,
    strip_mode: str = "full",
    content_policy: Optional[ContentPolicy] = None,
) -> ContentPolicy:
    return content_policy or get_detection_policy(format_name, strip_mode).content


def content_policy_cache_key(content_policy: ContentPolicy) -> tuple[Any, ...]:
    return (content_policy,)


def content_signal_from_gray(gray: np.ndarray) -> ContentSignal:
    evidence_u8 = make_content_evidence_gray(gray)
    return ContentSignal(
        evidence_u8=evidence_u8,
        evidence_float=evidence_u8.astype(np.float32) / 255.0,
    )


def content_evidence_threshold(
    evidence_float: np.ndarray,
    evidence_params: ContentEvidencePolicy,
) -> float:
    outer_p70 = float(sampled_percentile(evidence_float, [evidence_params.percentile])[0])
    return max(
        evidence_params.threshold_min,
        min(
            evidence_params.threshold_max,
            outer_p70 * evidence_params.threshold_multiplier,
        ),
    )


__all__ = [
    "CACHED_CONTENT_SIGNAL_COMPOSITE",
    "CONTENT_SIGNAL_COMPOSITE",
    "ContentSignal",
    "content_evidence_threshold",
    "content_policy_cache_key",
    "content_signal_from_gray",
    "resolve_content_policy",
]
