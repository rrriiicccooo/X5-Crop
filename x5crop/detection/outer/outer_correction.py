from __future__ import annotations

from typing import Any

import numpy as np

from ...runtime_config import RuntimeConfig
from ...domain import Detection
from ...formats import FormatSpec
from ...runtime import AnalysisCache
from .retry_content import retry_with_content_aligned_outer
from .retry_geometry import format_geometry_model_detail, retry_with_format_geometry_outer
from .retry_short_axis import retry_with_short_axis_aspect_outer


def retry_with_outer_correction_proposals(
    gray: np.ndarray,
    config: RuntimeConfig,
    fmt: FormatSpec,
    detection: Detection,
    content_detail: dict[str, Any],
    outer_alignment: dict[str, Any],
    cache: AnalysisCache,
) -> tuple[Detection, dict[str, Any], dict[str, Any], bool]:
    retried = retry_with_short_axis_aspect_outer(gray, config, fmt, detection, content_detail, cache)
    if retried is not None:
        return (
            retried,
            dict(retried.detail.get("content_evidence", {})),
            dict(retried.detail.get("outer_content_alignment", {})),
            True,
        )

    geometry_detail = format_geometry_model_detail(gray, detection, config, fmt, cache)
    detection.detail["format_geometry_model"] = geometry_detail
    retried = retry_with_format_geometry_outer(gray, config, fmt, detection, outer_alignment, cache)
    if retried is not None:
        return (
            retried,
            dict(retried.detail.get("content_evidence", {})),
            dict(retried.detail.get("outer_content_alignment", {})),
            False,
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
