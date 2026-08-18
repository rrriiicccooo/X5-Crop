"""Boundary semantics and the canonical registered-measurement spec."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math


PHOTO_BOUNDARY_MEASUREMENT_REVISION = "x5crop_photo_boundary_measurement_v1"


class BoundaryAxis(str, Enum):
    X = "x"
    Y = "y"


class BoundaryRole(str, Enum):
    TOP = "top"
    BOTTOM = "bottom"
    START = "start"
    END = "end"
    LONG_BOUNDARY = "long_boundary"


class BoundaryEvidenceState(str, Enum):
    SUPPORT = "support"
    CONTRADICTION = "contradiction"
    UNOBSERVABLE = "unobservable"


class PositionSource(str, Enum):
    OBSERVED_TRANSITION = "observed_transition"
    INFERRED_OPPOSITE_EDGE = "inferred_opposite_edge"
    INFERRED_SEQUENCE = "inferred_sequence"


class DirectionAuthority(str, Enum):
    SHARED_TOP_BOTTOM_DIRECTION = "shared_top_bottom_direction"
    BOUNDED_SEQUENCE_EDGE_DIRECTION = "bounded_sequence_edge_direction"


class AuthoritySide(str, Enum):
    LEFT = "left"
    TOP = "top"
    RIGHT = "right"
    BOTTOM = "bottom"


class ClippedRequirement(str, Enum):
    VISIBLE_PLACEMENT = "visible_placement"


class QueryPurpose(str, Enum):
    COARSE_STRIP_LONG = "coarse_strip_long"
    COARSE_STRIP_SHORT = "coarse_strip_short"
    TOP_CORRIDOR = "top_corridor"
    BOTTOM_CORRIDOR = "bottom_corridor"
    SEQUENCE_BASELINE = "sequence_baseline"
    SEQUENCE_ANCHOR_WINDOW = "sequence_anchor_window"


@dataclass(frozen=True)
class PhotoBoundaryMeasurementSpec:
    """Canonical registered transition and robust-fit measurement contract."""

    lattice_support_divisor: float = 12.0
    lattice_minimum_mm: float = 2.0
    lattice_maximum_mm: float = 4.0
    local_window_mm: float = 0.25
    transition_gap_mm: float = 0.05
    gradient_z_minimum: float = 3.0
    tone_or_texture_z_minimum: float = 3.0
    maximum_measurable_line_angle_degrees: float = 4.0
    line_connection_allowance_mm: float = 0.10
    maximum_missing_lattice_steps: int = 1
    robust_loss_minimum_scale_mm: float = 0.05
    robust_fit_maximum_evaluations: int = 128
    robust_fit_tolerance: float = 1.0e-8
    inlier_minimum_threshold_mm: float = 0.10
    inlier_mad_multiplier: float = 3.0
    angle_endpoint_uncertainty_multiplier: float = 2.0
    maximum_streaming_block_pixels: int = 1_048_576
    transition_coordinate_sampling_uncertainty_px: float = 0.5

    def __post_init__(self) -> None:
        positive = (
            self.lattice_support_divisor,
            self.lattice_minimum_mm,
            self.lattice_maximum_mm,
            self.local_window_mm,
            self.transition_gap_mm,
            self.gradient_z_minimum,
            self.tone_or_texture_z_minimum,
            self.maximum_measurable_line_angle_degrees,
            self.line_connection_allowance_mm,
            self.robust_loss_minimum_scale_mm,
            self.robust_fit_tolerance,
            self.inlier_minimum_threshold_mm,
            self.inlier_mad_multiplier,
            self.angle_endpoint_uncertainty_multiplier,
            self.transition_coordinate_sampling_uncertainty_px,
        )
        if any(not math.isfinite(value) or value <= 0.0 for value in positive):
            raise ValueError("photo-boundary measurement spec must be positive")
        if self.lattice_minimum_mm > self.lattice_maximum_mm:
            raise ValueError("measurement lattice bounds are reversed")
        if (
            self.maximum_missing_lattice_steps < 0
            or self.robust_fit_maximum_evaluations <= 0
            or self.maximum_streaming_block_pixels <= 0
        ):
            raise ValueError("photo-boundary discrete limits are invalid")

    def lattice_spacing_mm(self, expected_support_mm: float) -> float:
        if not math.isfinite(expected_support_mm) or expected_support_mm <= 0.0:
            raise ValueError("lattice support must be finite and positive")
        return min(
            self.lattice_maximum_mm,
            max(
                self.lattice_minimum_mm,
                expected_support_mm / self.lattice_support_divisor,
            ),
        )

    def transition_gap_px(self, scale_px_per_mm: float) -> int:
        if not math.isfinite(scale_px_per_mm) or scale_px_per_mm <= 0.0:
            raise ValueError("transition scale must be finite and positive")
        return max(1, int(math.ceil(self.transition_gap_mm * scale_px_per_mm)))

    def local_window_px(self, scale_px_per_mm: float) -> int:
        if not math.isfinite(scale_px_per_mm) or scale_px_per_mm <= 0.0:
            raise ValueError("window scale must be finite and positive")
        return max(1, int(math.ceil(self.local_window_mm * scale_px_per_mm)))

    def measurement_halo_px(self, scale_px_per_mm: float) -> int:
        """Exact raster footprint required on each side of a transition."""

        return self.local_window_px(scale_px_per_mm) + self.transition_gap_px(
            scale_px_per_mm
        )

    @property
    def paired_sampling_uncertainty_px(self) -> float:
        """Separation uncertainty of two independently localized samples."""

        return 2.0 * self.transition_coordinate_sampling_uncertainty_px

    def line_connection_allowance_px(self, scale_px_per_mm: float) -> float:
        if not math.isfinite(scale_px_per_mm) or scale_px_per_mm <= 0.0:
            raise ValueError("line connection scale must be finite and positive")
        return (
            self.line_connection_allowance_mm * scale_px_per_mm
            + self.paired_sampling_uncertainty_px
        )


PHOTO_BOUNDARY_MEASUREMENT_SPEC = PhotoBoundaryMeasurementSpec()

SPATIAL_SUPPORT_REGION_COUNT = 3
MINIMUM_INDEPENDENT_SUPPORT_REGIONS = 2


def independent_spatial_support_count(
    queried_traces: tuple[int | float, ...],
    observed_traces: tuple[int | float, ...],
) -> int:
    if not queried_traces or not observed_traces:
        return 0
    minimum = float(min(queried_traces))
    maximum = float(max(queried_traces))
    if maximum <= minimum:
        return 1
    return len(
        {
            spatial_support_region_index(queried_traces, trace)
            for trace in observed_traces
            if minimum <= float(trace) <= maximum
        }
    )


def spatial_support_region_index(
    queried_traces: tuple[int | float, ...],
    trace: int | float,
) -> int:
    if not queried_traces:
        raise ValueError("spatial support region requires query traces")
    minimum = float(min(queried_traces))
    maximum = float(max(queried_traces))
    value = float(trace)
    if not minimum <= value <= maximum:
        raise ValueError("trace leaves spatial support authority")
    if maximum <= minimum:
        return 0
    return min(
        SPATIAL_SUPPORT_REGION_COUNT - 1,
        int(
            SPATIAL_SUPPORT_REGION_COUNT
            * (value - minimum)
            / (maximum - minimum)
        ),
    )
