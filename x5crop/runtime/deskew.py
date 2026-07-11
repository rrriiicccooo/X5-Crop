from __future__ import annotations

import math
from typing import Any

from ..domain import ImageProfile
from ..detection.evidence.transform_geometry import TransformGeometryEvidence
from x5crop.domain import EvidenceState
from ..geometry.layout import work_gray
from ..image.deskew import choose_deskew_angle
from ..image.gray import make_base_gray_u8
from ..image.transforms import rotate_array_expand
from ..policies.runtime.preprocess import RuntimePreprocessPolicy
from ..utils import clamp_float
from ..run_config import RunConfig


def apply_deskew(
    arr: Any,
    gray: Any,
    profile: ImageProfile,
    config: RunConfig,
    preprocess: RuntimePreprocessPolicy,
    warnings: list[str],
) -> tuple[Any, Any, TransformGeometryEvidence]:
    deskew = preprocess.deskew
    if config.deskew == "off":
        return arr, gray, TransformGeometryEvidence(
            state=EvidenceState.SUPPORTED,
            applied=False,
            estimated_angle_degrees=0.0,
            applied_angle_degrees=0.0,
            reason="deskew_disabled",
            span_px=None,
            span_threshold_px=None,
        )

    angle, angle_detail = choose_deskew_angle(
        gray,
        config.layout,
        config.deskew_fallback,
        deskew,
        preprocess.deskew_fallback_evidence,
    )
    deskew_work_width = float(work_gray(gray, config.layout).shape[1])
    deskew_span = abs(math.tan(math.radians(angle)) * deskew_work_width)
    deskew_span_threshold = clamp_float(
        deskew_work_width * deskew.span_skip_ratio,
        deskew.span_skip_min,
        deskew.span_skip_max,
    )
    applied = False
    applied_angle = 0.0
    if deskew_span < deskew_span_threshold:
        state = EvidenceState.SUPPORTED
        reason = "span_below_threshold"
    elif config.deskew_min_angle <= abs(angle) <= config.deskew_max_angle:
        arr = rotate_array_expand(arr, -angle, profile.axes)
        gray = make_base_gray_u8(arr, profile.axes, profile.photometric, preprocess.base_gray)
        applied = True
        applied_angle = -float(angle)
        state = EvidenceState.SUPPORTED
        reason = "deskew_applied"
        warnings.append(f"deskew applied: {-angle:.4f} degrees")
    else:
        state = EvidenceState.CONTRADICTED
        reason = "angle_out_of_range"
    if angle_detail.get("reason") and reason == "span_below_threshold":
        reason = str(angle_detail["reason"])
    return arr, gray, TransformGeometryEvidence(
        state=state,
        applied=applied,
        estimated_angle_degrees=float(angle),
        applied_angle_degrees=applied_angle,
        reason=reason,
        span_px=float(deskew_span),
        span_threshold_px=float(deskew_span_threshold),
    )
