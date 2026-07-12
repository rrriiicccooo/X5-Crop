from __future__ import annotations

from dataclasses import dataclass

from ..cache import MeasurementCache
from ..domain import ImageProfile
from ..configuration.model import DetectionConfiguration
from ..units import ScanCalibration


@dataclass(frozen=True)
class DetectionRequest:
    layout: str
    strip_mode: str
    requested_count: int | None


@dataclass(frozen=True)
class DetectionContext:
    image_profile: ImageProfile
    scan_calibration: ScanCalibration
    request: DetectionRequest
    configuration: DetectionConfiguration
    lane_configuration: DetectionConfiguration | None
    measurement_cache: MeasurementCache
