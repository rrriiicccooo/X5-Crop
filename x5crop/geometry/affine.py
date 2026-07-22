from __future__ import annotations

from dataclasses import dataclass
import math

from ..domain import Box, PixelInterval, WorkspaceExtent


AFFINE_INVERTIBILITY_FLOOR = 1e-12


@dataclass(frozen=True)
class AffineCoordinateTransform:
    matrix: tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ]
    source_extent: WorkspaceExtent
    output_extent: WorkspaceExtent

    def __post_init__(self) -> None:
        values = tuple(value for row in self.matrix for value in row)
        if any(not math.isfinite(value) for value in values):
            raise ValueError("affine coordinate transform must be finite")
        if self.matrix[2] != (0.0, 0.0, 1.0):
            raise ValueError("image coordinate transform must be affine")
        determinant = (
            self.matrix[0][0] * self.matrix[1][1]
            - self.matrix[0][1] * self.matrix[1][0]
        )
        if abs(determinant) < AFFINE_INVERTIBILITY_FLOOR:
            raise ValueError("image coordinate transform must be invertible")

    @classmethod
    def identity(cls, width: int, height: int) -> "AffineCoordinateTransform":
        extent = WorkspaceExtent(width=width, height=height)
        return cls(
            matrix=(
                (1.0, 0.0, 0.0),
                (0.0, 1.0, 0.0),
                (0.0, 0.0, 1.0),
            ),
            source_extent=extent,
            output_extent=extent,
        )

    @classmethod
    def expanded_rotation(
        cls,
        width: int,
        height: int,
        angle_degrees: float,
    ) -> "AffineCoordinateTransform":
        if width <= 0 or height <= 0:
            raise ValueError("expanded rotation requires a positive source extent")
        if not math.isfinite(angle_degrees):
            raise ValueError("expanded rotation angle must be finite")
        angle = math.radians(angle_degrees)
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        cx = (width - 1) / 2.0
        cy = (height - 1) / 2.0
        corners = (
            (0.0, 0.0),
            (float(width - 1), 0.0),
            (0.0, float(height - 1)),
            (float(width - 1), float(height - 1)),
        )
        rotated = tuple(
            (
                (x - cx) * cos_a - (y - cy) * sin_a,
                (x - cx) * sin_a + (y - cy) * cos_a,
            )
            for x, y in corners
        )
        minimum_x = min(point[0] for point in rotated)
        maximum_x = max(point[0] for point in rotated)
        minimum_y = min(point[1] for point in rotated)
        maximum_y = max(point[1] for point in rotated)
        output_width = int(math.ceil(maximum_x - minimum_x + 1.0))
        output_height = int(math.ceil(maximum_y - minimum_y + 1.0))
        output_cx = (output_width - 1) / 2.0
        output_cy = (output_height - 1) / 2.0
        return cls(
            matrix=(
                (
                    cos_a,
                    -sin_a,
                    output_cx - cos_a * cx + sin_a * cy,
                ),
                (
                    sin_a,
                    cos_a,
                    output_cy - sin_a * cx - cos_a * cy,
                ),
                (0.0, 0.0, 1.0),
            ),
            source_extent=WorkspaceExtent(width=width, height=height),
            output_extent=WorkspaceExtent(
                width=output_width,
                height=output_height,
            ),
        )

    @property
    def is_identity(self) -> bool:
        return bool(
            self.source_extent == self.output_extent
            and self.matrix
            == (
                (1.0, 0.0, 0.0),
                (0.0, 1.0, 0.0),
                (0.0, 0.0, 1.0),
            )
        )

    def map_point(self, x: float, y: float) -> tuple[float, float]:
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError("mapped image coordinate must be finite")
        return (
            self.matrix[0][0] * x
            + self.matrix[0][1] * y
            + self.matrix[0][2],
            self.matrix[1][0] * x
            + self.matrix[1][1] * y
            + self.matrix[1][2],
        )

    def map_box(self, box: Box) -> Box:
        points = tuple(
            self.map_point(x, y)
            for x, y in (
                (float(box.left), float(box.top)),
                (float(box.right), float(box.top)),
                (float(box.left), float(box.bottom)),
                (float(box.right), float(box.bottom)),
            )
        )
        return Box(
            math.floor(min(point[0] for point in points)),
            math.floor(min(point[1] for point in points)),
            math.ceil(max(point[0] for point in points)),
            math.ceil(max(point[1] for point in points)),
        ).clamp(self.output_extent.width, self.output_extent.height)

    def map_intervals(
        self,
        x: PixelInterval,
        y: PixelInterval,
    ) -> tuple[PixelInterval, PixelInterval]:
        points = tuple(
            self.map_point(x_value, y_value)
            for x_value in (x.minimum, x.maximum)
            for y_value in (y.minimum, y.maximum)
        )
        return (
            PixelInterval(
                min(point[0] for point in points),
                max(point[0] for point in points),
            ),
            PixelInterval(
                min(point[1] for point in points),
                max(point[1] for point in points),
            ),
        )
