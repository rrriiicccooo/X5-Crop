from __future__ import annotations

from dataclasses import dataclass

from ..cache import MeasurementCache
from ..configuration.model import DetectionConfiguration
from ..geometry.layout import require_work_layout
from ..strip_modes import FULL, PARTIAL
from ..units import ScanCalibration


@dataclass(frozen=True)
class DetectionRequest:
    layout: str
    strip_mode: str
    requested_count: int | None

    def __post_init__(self) -> None:
        require_work_layout(self.layout)
        if self.strip_mode not in {FULL, PARTIAL}:
            raise ValueError(f"unsupported detection strip mode: {self.strip_mode}")
        if self.requested_count is not None and self.requested_count <= 0:
            raise ValueError("requested detection count must be positive")


@dataclass(frozen=True)
class DetectionContext:
    scan_calibration: ScanCalibration
    request: DetectionRequest
    configuration: DetectionConfiguration
    lane_configuration: DetectionConfiguration | None
    measurement_cache: MeasurementCache

    def __post_init__(self) -> None:
        if self.request.strip_mode != self.configuration.strip_mode:
            raise ValueError("detection request and configuration mode must match")
        if self.measurement_cache.layout != self.request.layout:
            raise ValueError("measurement cache and detection request layout must match")
        if (
            self.request.requested_count is not None
            and self.request.requested_count
            not in self.configuration.physical_spec.allowed_counts
        ):
            raise ValueError("requested count must be allowed by the physical spec")

        if self.configuration.detector_kind == "dual_lane":
            expected_lane_format = self.configuration.physical_spec.lane_format_id
            if (
                self.lane_configuration is None
                or self.lane_configuration.strip_mode != FULL
                or self.lane_configuration.physical_spec.format_id
                != expected_lane_format
            ):
                raise ValueError(
                    "dual-lane detection requires its resolved full lane configuration"
                )
        elif self.lane_configuration is not None:
            raise ValueError("only dual-lane detection accepts a lane configuration")
