from __future__ import annotations

import math

import numpy as np

from ..domain import EvidenceState, ImageProfile
from ..detection.evidence.transform_geometry import TransformGeometryEvidence
from ..geometry.layout import work_gray
from ..image.deskew import (
    DeskewAngleMeasurement,
    deskew_measurement_quality,
    measure_deskew_angle,
)
from ..image.evidence import make_deskew_fallback_gray
from ..image.gray import make_base_gray_u8
from ..image.transforms import rotate_array_expand
from ..configuration.preprocess import PreprocessConfiguration
from ..image.statistics import (
    ImageMeasurementStatistics,
    image_measurement_statistics,
)
from ..utils import clamp_float
from ..run_config import RunConfig


def _select_deskew_measurement(
    gray: np.ndarray,
    config: RunConfig,
    preprocess: PreprocessConfiguration,
    base_statistics: ImageMeasurementStatistics,
) -> DeskewAngleMeasurement:
    parameters = preprocess.deskew
    base = measure_deskew_angle(
        gray,
        config.layout,
        parameters,
        base_statistics,
    )
    if config.deskew_fallback == "off":
        return base
    if (
        config.deskew_fallback == "auto"
        and deskew_measurement_quality(base, parameters)
        >= parameters.auto_quality_ok
    ):
        return base
    fallback_gray = make_deskew_fallback_gray(
        gray,
        preprocess.deskew_fallback_evidence,
    )
    fallback_statistics = image_measurement_statistics(
        work_gray(fallback_gray, config.layout),
        preprocess.image_statistics,
    )
    fallback = measure_deskew_angle(
        fallback_gray,
        config.layout,
        parameters,
        fallback_statistics,
    )
    return (
        fallback
        if deskew_measurement_quality(fallback, parameters)
        > deskew_measurement_quality(base, parameters)
        + parameters.fallback_quality_gain
        else base
    )


def apply_deskew(
    arr: np.ndarray,
    gray: np.ndarray,
    profile: ImageProfile,
    config: RunConfig,
    preprocess: PreprocessConfiguration,
    measurement_statistics: ImageMeasurementStatistics,
    warnings: list[str],
) -> tuple[np.ndarray, np.ndarray, TransformGeometryEvidence]:
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

    measurement = _select_deskew_measurement(
        gray,
        config,
        preprocess,
        measurement_statistics,
    )
    angle = measurement.angle_degrees
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
    if measurement.reason is not None and reason == "span_below_threshold":
        reason = measurement.reason
    return arr, gray, TransformGeometryEvidence(
        state=state,
        applied=applied,
        estimated_angle_degrees=float(angle),
        applied_angle_degrees=applied_angle,
        reason=reason,
        span_px=float(deskew_span),
        span_threshold_px=float(deskew_span_threshold),
    )
