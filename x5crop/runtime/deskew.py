from __future__ import annotations

import math

import numpy as np

from ..io.model import ImageProfile
from ..detection.evidence.transform_geometry import (
    TransformGeometryEvidence,
    TransformOutcome,
)
from ..geometry.layout import work_gray
from ..image.deskew import (
    DeskewAngleMeasurement,
    DeskewMeasurementOutcome,
    measure_deskew_angle,
)
from ..image.evidence import make_deskew_fallback_gray
from ..image.gray import make_base_gray_u8
from ..image.transforms import (
    photometric_background_value,
    rotate_array_expand,
)
from ..configuration.preprocess import PreprocessConfiguration
from ..image.statistics import (
    ImageMeasurementStatistics,
    image_measurement_statistics,
)
from ..utils import clamp_float
from ..run_config import RunConfig
from .prepared_workspace import PreparedWorkspace


def _deskew_measurement_preference(
    measurement: DeskewAngleMeasurement,
) -> tuple[bool, int, int, float]:
    fits = tuple(
        fit
        for fit in (measurement.top_fit, measurement.bottom_fit)
        if fit is not None
    )
    return (
        measurement.outcome == DeskewMeasurementOutcome.MEASURED,
        len(fits),
        sum(fit.inliers for fit in fits),
        -max((fit.median_residual for fit in fits), default=float("inf")),
    )


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
        and base.outcome == DeskewMeasurementOutcome.MEASURED
        and base.top_fit is not None
        and base.bottom_fit is not None
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
    return max((base, fallback), key=_deskew_measurement_preference)


def apply_deskew(
    arr: np.ndarray,
    gray: np.ndarray,
    profile: ImageProfile,
    config: RunConfig,
    preprocess: PreprocessConfiguration,
    measurement_statistics: ImageMeasurementStatistics,
    warnings: list[str],
) -> PreparedWorkspace:
    deskew = preprocess.deskew
    if config.deskew == "off":
        return PreparedWorkspace(
            pixels=arr,
            gray=gray,
            transform_geometry=TransformGeometryEvidence(
                outcome=TransformOutcome.DISABLED,
                estimated_angle_degrees=0.0,
                span_px=None,
                span_threshold_px=None,
            ),
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
    if deskew_span < deskew_span_threshold:
        outcome = TransformOutcome.SPAN_BELOW_THRESHOLD
    elif config.deskew_min_angle <= abs(angle) <= config.deskew_max_angle:
        arr = rotate_array_expand(
            arr,
            -angle,
            profile.axes,
            background_value=photometric_background_value(
                arr,
                profile.photometric,
            ),
        )
        gray = make_base_gray_u8(arr, profile.axes, profile.photometric, preprocess.base_gray)
        outcome = TransformOutcome.APPLIED
        warnings.append(f"deskew applied: {-angle:.4f} degrees")
    else:
        outcome = TransformOutcome.ANGLE_OUT_OF_RANGE
    return PreparedWorkspace(
        pixels=arr,
        gray=gray,
        transform_geometry=TransformGeometryEvidence(
            outcome=outcome,
            estimated_angle_degrees=float(angle),
            span_px=float(deskew_span),
            span_threshold_px=float(deskew_span_threshold),
            measurement_outcome=measurement.outcome,
        ),
    )
