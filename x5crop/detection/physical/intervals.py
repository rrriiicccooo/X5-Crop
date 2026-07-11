from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class PixelInterval:
    minimum: float
    maximum: float

    def __post_init__(self) -> None:
        if self.maximum < self.minimum:
            raise ValueError("pixel interval maximum must not be below minimum")

    @classmethod
    def exact(cls, value: float) -> "PixelInterval":
        return cls(float(value), float(value))

    @classmethod
    def zero(cls) -> "PixelInterval":
        return cls.exact(0.0)

    def intersects(self, other: "PixelInterval") -> bool:
        return max(self.minimum, other.minimum) <= min(self.maximum, other.maximum)

    def plus(self, other: "PixelInterval") -> "PixelInterval":
        return PixelInterval(
            self.minimum + other.minimum,
            self.maximum + other.maximum,
        )

    def minus(self, other: "PixelInterval") -> "PixelInterval":
        return PixelInterval(
            self.minimum - other.maximum,
            self.maximum - other.minimum,
        )

    def scaled(self, factor: float) -> "PixelInterval":
        low = self.minimum * float(factor)
        high = self.maximum * float(factor)
        return PixelInterval(min(low, high), max(low, high))


def sum_pixel_intervals(intervals: tuple[PixelInterval, ...]) -> PixelInterval:
    return PixelInterval(
        sum(interval.minimum for interval in intervals),
        sum(interval.maximum for interval in intervals),
    )
