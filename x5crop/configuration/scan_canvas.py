from __future__ import annotations

from dataclasses import dataclass

from ..formats.scan_canvas import ScanCanvasPhysicalSpec
from ..utils import require_unit_interval


@dataclass(frozen=True)
class ScanCanvasDetectionConfiguration:
    profiles: tuple[ScanCanvasPhysicalSpec, ...]
    maximum_aspect_error_ratio: float = 0.005

    def __post_init__(self) -> None:
        profile_ids = tuple(profile.profile_id for profile in self.profiles)
        if len(set(profile_ids)) != len(profile_ids):
            raise ValueError(
                "scan-canvas detection profiles must be unique"
            )
        require_unit_interval(
            "scan-canvas maximum aspect error",
            self.maximum_aspect_error_ratio,
        )
        if self.maximum_aspect_error_ratio <= 0.0:
            raise ValueError(
                "scan-canvas maximum aspect error must be positive"
            )
