from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math


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


@dataclass(frozen=True)
class WorkspaceExtent:
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("workspace extent must have positive dimensions")


@dataclass(frozen=True, order=True)
class PositiveInterval:
    minimum: float
    maximum: float

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.minimum)
            or not math.isfinite(self.maximum)
            or self.minimum <= 0.0
            or self.maximum < self.minimum
        ):
            raise ValueError("positive interval bounds must be finite and ordered")

    @classmethod
    def exact(cls, value: float) -> "PositiveInterval":
        return cls(float(value), float(value))


@dataclass(frozen=True, order=True)
class FiniteInterval:
    minimum: float
    maximum: float

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.minimum)
            or not math.isfinite(self.maximum)
            or self.maximum < self.minimum
        ):
            raise ValueError("finite interval bounds must be finite and ordered")

    @classmethod
    def exact(cls, value: float) -> "FiniteInterval":
        return cls(float(value), float(value))

    @property
    def center(self) -> float:
        return (self.minimum + self.maximum) / 2.0

    @property
    def width(self) -> float:
        return self.maximum - self.minimum

    def contains(self, value: float, *, epsilon: float = 0.0) -> bool:
        if not math.isfinite(value) or epsilon < 0.0:
            return False
        return self.minimum - epsilon <= value <= self.maximum + epsilon


class EvidenceState(str, Enum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"


class MeasurementIdentity(str, Enum):
    BASE_GRAY = "base_gray"
    IMAGE_MEASUREMENT_STATISTICS = "image_measurement_statistics"
    SCAN_CANVAS_GEOMETRY = "scan_canvas_geometry"
    SOURCE_CONTENT = "source_content"
    PHOTO_BOUNDARY = "photo_boundary"


class ObservationId(str):
    def __new__(cls, value: str) -> "ObservationId":
        if not isinstance(value, str) or not value:
            raise ValueError("observation identity must be a non-empty string")
        return str.__new__(cls, value)


@dataclass(frozen=True)
class MeasurementProvenance:
    root_measurement: MeasurementIdentity
    observation_id: ObservationId
    dependencies: tuple[MeasurementIdentity, ...]
    description: str

    def __post_init__(self) -> None:
        if not isinstance(self.root_measurement, MeasurementIdentity):
            raise TypeError("measurement provenance requires a typed root")
        if not isinstance(self.observation_id, ObservationId):
            raise TypeError("measurement provenance requires a typed identity")
        if not self.description:
            raise ValueError("measurement provenance requires a description")
        if (
            len(set(self.dependencies)) != len(self.dependencies)
            or self.root_measurement in self.dependencies
            or any(
                not isinstance(dependency, MeasurementIdentity)
                for dependency in self.dependencies
            )
        ):
            raise ValueError("measurement provenance dependencies are invalid")
