from __future__ import annotations

from typing import Any

import numpy as np

from ....domain import Detection
from ....formats import FormatSpec
from ....runtime import AnalysisCache
from ....runtime_config import RuntimeConfig
from .content_aligned import retry_with_content_aligned_outer
from .geometry import retry_with_geometry_outer_correction


def retry_with_outer_correction_proposals(
    gray: np.ndarray,
    config: RuntimeConfig,
    fmt: FormatSpec,
    detection: Detection,
    content_detail: dict[str, Any],
    outer_alignment: dict[str, Any],
    cache: AnalysisCache,
) -> tuple[Detection, dict[str, Any], dict[str, Any], bool]:
    retried, suppress_outer_mismatch = retry_with_geometry_outer_correction(
        gray,
        config,
        fmt,
        detection,
        content_detail,
        outer_alignment,
        cache,
    )
    if retried is not None:
        return (
            retried,
            dict(retried.detail.get("content_evidence", {})),
            dict(retried.detail.get("outer_content_alignment", {})),
            suppress_outer_mismatch,
        )

    if bool(outer_alignment.get("used", False)) and not bool(outer_alignment.get("ok", True)):
        retried = retry_with_content_aligned_outer(gray, config, fmt, detection, outer_alignment, cache)
        if retried is not None:
            return (
                retried,
                dict(retried.detail.get("content_evidence", {})),
                dict(retried.detail.get("outer_content_alignment", {})),
                False,
            )
        detection.detail["outer_correction"] = {
            "used": False,
            "reason": "no_valid_content_aligned_outer_retry",
        }

    return detection, content_detail, outer_alignment, False
