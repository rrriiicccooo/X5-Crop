from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from ....image.evidence import (
    ContentEvidenceImageParameters,
    make_content_evidence_gray,
)
from ....policies.parameters.content import ContentEvidenceParameters
from ....policies.runtime.content import ContentPolicy
from ....utils import sampled_percentile

CONTENT_SIGNAL_COMPOSITE = "gradient+neighbor_texture+local_contrast+tonal_presence"
CACHED_CONTENT_SIGNAL_COMPOSITE = "cached_" + CONTENT_SIGNAL_COMPOSITE


@dataclass(frozen=True)
class ContentSignal:
    evidence_u8: np.ndarray
    evidence_float: np.ndarray
    composite: str = CONTENT_SIGNAL_COMPOSITE


def content_policy_cache_key(content_policy: ContentPolicy) -> tuple[Any, ...]:
    return (content_policy,)


def content_signal_from_gray(
    gray: np.ndarray,
    params: ContentEvidenceImageParameters,
) -> ContentSignal:
    evidence_u8 = make_content_evidence_gray(
        gray,
        params,
    )
    return ContentSignal(
        evidence_u8=evidence_u8,
        evidence_float=evidence_u8.astype(np.float32) / 255.0,
    )


def content_evidence_threshold(
    evidence_float: np.ndarray,
    evidence_params: ContentEvidenceParameters,
) -> float:
    outer_p70 = float(sampled_percentile(evidence_float, [evidence_params.percentile])[0])
    return max(
        evidence_params.threshold_min,
        min(
            evidence_params.threshold_max,
            outer_p70 * evidence_params.threshold_multiplier,
        ),
    )
