from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class Box:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)

    def valid(self) -> bool:
        return self.right > self.left and self.bottom > self.top

    def clamp(self, width: int, height: int) -> "Box":
        return Box(
            max(0, min(width, self.left)),
            max(0, min(height, self.top)),
            max(0, min(width, self.right)),
            max(0, min(height, self.bottom)),
        )

    def expand(self, bleed_x: int, bleed_y: int, width: int, height: int) -> "Box":
        return Box(
            self.left - bleed_x,
            self.top - bleed_y,
            self.right + bleed_x,
            self.bottom + bleed_y,
        ).clamp(width, height)


@dataclass
class Gap:
    index: int
    center: float
    score: float
    method: str
    start: Optional[float] = None
    end: Optional[float] = None
    lane_box: Optional[dict[str, int]] = None

    @property
    def width(self) -> float:
        if self.start is None or self.end is None:
            return 0.0
        return max(0.0, float(self.end) - float(self.start))


@dataclass(frozen=True)
class OuterCandidate:
    name: str
    box: Box
    strategy: str = "unknown_outer"
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class Detection:
    film_format: str
    layout: str
    strip_mode: str
    count: int
    outer: Box
    frames: list[Box]
    gaps: list[Gap]
    confidence: float
    final_review_reasons: list[str]
    detail: dict[str, Any]


@dataclass
class ImageProfile:
    shape: tuple[int, ...]
    dtype: str
    axes: str
    photometric: str
    compression: str
    sample_format: Optional[Any]
    bits_per_sample: Optional[Any]
    samples_per_pixel: Optional[int]
    planar_config: Optional[str]
    resolution: Optional[tuple[Any, Any]]
    resolution_unit: Optional[Any]
    icc_profile: Optional[bytes]


@dataclass
class ProcessResult:
    source: str
    status: str
    confidence: float
    film_format: str
    layout: str
    strip_mode: str
    count: int
    final_review_reasons: list[str]
    output_files: list[str]
    review_copy: Optional[str]
    outer_box: dict[str, int]
    frame_boxes: list[dict[str, int]]
    gaps: list[dict[str, Any]]
    detail: dict[str, Any]
    profile: dict[str, Any]
    warnings: list[str]
    version: str = ""
    policy_id: str = ""
    report_record: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "Box",
    "Detection",
    "Gap",
    "ImageProfile",
    "OuterCandidate",
    "ProcessResult",
]
