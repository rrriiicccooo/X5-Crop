"""Canonical records and bounds emitted by template measurement compilation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ...domain import FiniteInterval
from ...formats import FormatSpec, FramePhysicalSpec
from ..evidence.scan_canvas import CanvasAxisScaleIntervals
from ..source_core import SourceStripValidationDomain
from .template_model import TemplateSpec
from .template_nominal_grid_model import CalibratedNominalGridPrior

MAX_QUERY_INTENTS = 8
MAX_REGISTERED_QUERIES = 64
MAX_PHASE_OBSERVATIONS = 512
MAX_CROSS_PAIRS = 4096
MAX_PLACEMENT_CHECKS = 4
MAX_PIXEL_COORDINATES = 32_000_000_000
MAX_WORK_UNITS = 1_000_000


class MeasurementUnit(str, Enum):
    MILLIMETRES = "mm"
    LANE_RATIO = "lane_ratio"


class MeasurementAxis(str, Enum):
    LONG = "long"
    SHORT = "short"


class MeasurementIntentKind(str, Enum):
    COARSE_LONG_SUPPORT = "coarse_long_support"
    COARSE_SHORT_SUPPORT = "coarse_short_support"
    OUTER_SEQUENCE_ANCHOR = "outer_sequence_anchor"
    EARLY_SEQUENCE_ANCHOR = "early_sequence_anchor"
    MIDDLE_SEQUENCE_ANCHOR = "middle_sequence_anchor"
    LATE_SEQUENCE_ANCHOR = "late_sequence_anchor"
    TOP = "top"
    BOTTOM = "bottom"


@dataclass(frozen=True)
class TemplateQueryIntent:
    """One pre-registered finite intent, before any pixel projection."""

    intent_id: str
    kind: MeasurementIntentKind
    axis: MeasurementAxis
    coordinate_unit: MeasurementUnit
    coordinate_positions: tuple[FiniteInterval, ...]
    trace_unit: MeasurementUnit
    trace_positions: tuple[FiniteInterval, ...]
    search_margin_mm: FiniteInterval
    expected_span_mm: FiniteInterval
    registration_index: int

    def __post_init__(self) -> None:
        if (
            not self.intent_id
            or not isinstance(self.kind, MeasurementIntentKind)
            or not isinstance(self.axis, MeasurementAxis)
            or not isinstance(self.coordinate_unit, MeasurementUnit)
            or not isinstance(self.trace_unit, MeasurementUnit)
            or not self.coordinate_positions
            or not self.trace_positions
            or self.registration_index < 0
            or self.search_margin_mm.minimum <= 0.0
            or self.expected_span_mm.minimum <= 0.0
        ):
            raise ValueError("template query intent is incomplete")
        if tuple(sorted(self.coordinate_positions)) != self.coordinate_positions:
            raise ValueError("template coordinate positions must be ordered")
        if tuple(sorted(self.trace_positions)) != self.trace_positions:
            raise ValueError("template trace positions must be ordered")
        coarse_kind = self.kind in {
            MeasurementIntentKind.COARSE_LONG_SUPPORT,
            MeasurementIntentKind.COARSE_SHORT_SUPPORT,
        }
        sequence_kind = self.kind in {
            MeasurementIntentKind.OUTER_SEQUENCE_ANCHOR,
            MeasurementIntentKind.EARLY_SEQUENCE_ANCHOR,
            MeasurementIntentKind.MIDDLE_SEQUENCE_ANCHOR,
            MeasurementIntentKind.LATE_SEQUENCE_ANCHOR,
        }
        if coarse_kind:
            expected_axis = (
                MeasurementAxis.LONG
                if self.kind == MeasurementIntentKind.COARSE_LONG_SUPPORT
                else MeasurementAxis.SHORT
            )
            if (
                self.axis != expected_axis
                or self.coordinate_unit != MeasurementUnit.LANE_RATIO
            ):
                raise ValueError("coarse support must cover one lane axis")
        elif sequence_kind:
            if self.axis != MeasurementAxis.LONG:
                raise ValueError("sequence anchors use the long axis")
            if self.coordinate_unit != MeasurementUnit.LANE_RATIO:
                raise ValueError("sequence anchors use lane-ratio positions")
        elif self.kind in {MeasurementIntentKind.TOP, MeasurementIntentKind.BOTTOM}:
            if self.axis != MeasurementAxis.SHORT:
                raise ValueError("top/bottom intents use the short axis")
            if self.coordinate_unit != MeasurementUnit.MILLIMETRES:
                raise ValueError("top/bottom intents use millimetre positions")
        else:
            raise ValueError("unknown measurement intent kind")
        if self.trace_unit != MeasurementUnit.LANE_RATIO:
            raise ValueError("trace positions must use lane ratios")
        if any(
            position.minimum < -1.0e-12 or position.maximum > 1.0 + 1.0e-12
            for position in self.trace_positions
        ):
            raise ValueError("trace ratio is outside the lane")
        if self.coordinate_unit == MeasurementUnit.LANE_RATIO and any(
            position.minimum < -1.0e-12 or position.maximum > 1.0 + 1.0e-12
            for position in self.coordinate_positions
        ):
            raise ValueError("coordinate ratio is outside the lane")


@dataclass(frozen=True)
class TemplateProjectedQueryPlan:
    """Finite pixel projection owned by the compiler, before measurement."""

    long_extent_px: int
    cross_trace_positions_px: tuple[int, ...]
    top_core_intervals_px: tuple[FiniteInterval, ...]
    top_measurement_intervals_px: tuple[FiniteInterval, ...]
    bottom_core_intervals_px: tuple[FiniteInterval, ...]
    bottom_measurement_intervals_px: tuple[FiniteInterval, ...]
    sequence_trace_positions_px: tuple[int, ...]
    sequence_measurement_interval_px: FiniteInterval
    sequence_ownership_interval_px: FiniteInterval
    measurement_halo_px: int

    def __post_init__(self) -> None:
        cross_count = len(self.cross_trace_positions_px)
        if (
            self.long_extent_px <= 0
            or cross_count <= 0
            or not self.sequence_trace_positions_px
            or self.measurement_halo_px <= 0
            or any(
                len(values) != cross_count
                for values in (
                    self.top_core_intervals_px,
                    self.top_measurement_intervals_px,
                    self.bottom_core_intervals_px,
                    self.bottom_measurement_intervals_px,
                )
            )
            or self.sequence_measurement_interval_px.minimum
            > self.sequence_ownership_interval_px.minimum
            or self.sequence_measurement_interval_px.maximum
            < self.sequence_ownership_interval_px.maximum
        ):
            raise ValueError("projected template query plan is invalid")
        for core_values, measured_values in (
            (self.top_core_intervals_px, self.top_measurement_intervals_px),
            (self.bottom_core_intervals_px, self.bottom_measurement_intervals_px),
        ):
            if any(
                measured.minimum > core.minimum
                or measured.maximum < core.maximum
                for core, measured in zip(core_values, measured_values, strict=True)
            ):
                raise ValueError("projected measurement interval misses its core")


@dataclass(frozen=True)
class TemplatePhaseBounds:
    max_hypotheses: int
    max_role_count: int
    max_direct_observations: int

    def __post_init__(self) -> None:
        if min(
            self.max_hypotheses,
            self.max_role_count,
            self.max_direct_observations,
        ) <= 0:
            raise ValueError("phase bounds must be positive")


@dataclass(frozen=True)
class TemplateRoleBounds:
    max_role_bindings: int
    max_inferred_roles: int
    max_adjacency_relations: int

    def __post_init__(self) -> None:
        if min(
            self.max_role_bindings,
            self.max_inferred_roles,
            self.max_adjacency_relations,
        ) < 0:
            raise ValueError("role bounds cannot be negative")


@dataclass(frozen=True)
class TemplateCrossBounds:
    max_registered_runs: int
    max_fitted_observations: int
    max_compatible_pairs: int
    max_evaluated_fits: int
    max_inferred_observations: int

    def __post_init__(self) -> None:
        if min(
            self.max_registered_runs,
            self.max_fitted_observations,
            self.max_compatible_pairs,
            self.max_evaluated_fits,
            self.max_inferred_observations,
        ) < 0:
            raise ValueError("cross bounds cannot be negative")


@dataclass(frozen=True)
class TemplatePlacementBounds:
    max_direction_candidates: int
    max_placement_checks: int
    max_safety_checks: int

    def __post_init__(self) -> None:
        if min(
            self.max_direction_candidates,
            self.max_placement_checks,
            self.max_safety_checks,
        ) < 0:
            raise ValueError("placement bounds cannot be negative")


@dataclass(frozen=True)
class TemplatePixelBounds:
    max_registered_queries: int
    max_trace_positions: int
    max_coordinate_samples: int
    max_pixel_queries: int
    max_peak_temporary_bytes: int

    def __post_init__(self) -> None:
        if min(
            self.max_registered_queries,
            self.max_trace_positions,
            self.max_coordinate_samples,
            self.max_pixel_queries,
            self.max_peak_temporary_bytes,
        ) <= 0:
            raise ValueError("pixel bounds must be positive")


@dataclass(frozen=True)
class TemplateWorkBounds:
    max_query_intents: int
    max_work_units: int

    def __post_init__(self) -> None:
        if min(self.max_query_intents, self.max_work_units) <= 0:
            raise ValueError("work bounds must be positive")


@dataclass(frozen=True)
class TemplateMeasurementPlan:
    """Canonical, immutable output of template compilation."""

    format_spec: FormatSpec
    frame_spec: FramePhysicalSpec
    count: int
    full_count: int
    holder_full_count: int
    lane_id: str
    layout: str
    lane_authority: SourceStripValidationDomain
    scale_authority: CanvasAxisScaleIntervals
    template_spec: TemplateSpec
    calibrated_nominal_grid_prior: CalibratedNominalGridPrior
    query_intents: tuple[TemplateQueryIntent, ...]
    projected_queries: TemplateProjectedQueryPlan
    phase_bounds: TemplatePhaseBounds
    role_bounds: TemplateRoleBounds
    cross_bounds: TemplateCrossBounds
    placement_bounds: TemplatePlacementBounds
    pixel_bounds: TemplatePixelBounds
    work_bounds: TemplateWorkBounds
    physical_identity: str
    plan_identity: str

    def __post_init__(self) -> None:
        if not isinstance(self.lane_authority, SourceStripValidationDomain):
            raise TypeError("template plan requires source/lane authority")
        if not isinstance(self.scale_authority, CanvasAxisScaleIntervals):
            raise TypeError("template plan requires scale authority")
        if not isinstance(self.count, int) or isinstance(self.count, bool):
            raise TypeError("template plan count must be an integer")
        if (
            not isinstance(self.full_count, int)
            or isinstance(self.full_count, bool)
            or not isinstance(self.holder_full_count, int)
            or isinstance(self.holder_full_count, bool)
        ):
            raise TypeError("template plan full counts must be integers")
        if (
            not isinstance(self.format_spec, FormatSpec)
            or not isinstance(self.frame_spec, FramePhysicalSpec)
            or self.frame_spec != self.format_spec.frame
            or self.count <= 0
            or self.full_count <= 0
            or self.count > self.full_count
            or self.holder_full_count <= 0
            or not self.lane_id
            or self.layout not in {"horizontal", "vertical"}
            or self.lane_authority.lane_id != self.lane_id
            or self.lane_authority.source_axis_long
            != ("x" if self.layout == "horizontal" else "y")
            or self.format_spec.holder_full_count(
                self.lane_authority.authority_profile_id
            )
            != self.holder_full_count
            or self.holder_full_count % self.format_spec.layout.lane_count
            or self.full_count
            != self.holder_full_count // self.format_spec.layout.lane_count
            or self.scale_authority.holder_profile_id
            != self.lane_authority.authority_profile_id
            or (
                self.scale_authority.source_width_axis,
                self.scale_authority.source_height_axis,
            )
            != (("x", "y") if self.layout == "horizontal" else ("y", "x"))
            or not isinstance(self.template_spec, TemplateSpec)
            or not isinstance(
                self.calibrated_nominal_grid_prior,
                CalibratedNominalGridPrior,
            )
            or self.calibrated_nominal_grid_prior.template_id
            != self.template_spec.template_id
            or self.calibrated_nominal_grid_prior.format_id
            != self.format_spec.format_id
            or not isinstance(self.projected_queries, TemplateProjectedQueryPlan)
            or self.template_spec.count != self.count
            or not self.query_intents
            or len(self.query_intents) > MAX_QUERY_INTENTS
            or tuple(item.registration_index for item in self.query_intents)
            != tuple(range(len(self.query_intents)))
            or len({item.intent_id for item in self.query_intents})
            != len(self.query_intents)
            or self.physical_identity == self.plan_identity
        ):
            raise ValueError("template measurement plan is inconsistent")
        if len(self.query_intents) > min(
            self.pixel_bounds.max_registered_queries,
            self.work_bounds.max_query_intents,
        ):
            raise ValueError("template query bound exceeded")
        if 2 * self.count > self.phase_bounds.max_role_count:
            raise ValueError("template role bound exceeded")
        if (
            self.placement_bounds.max_placement_checks > MAX_PLACEMENT_CHECKS
            or self.pixel_bounds.max_coordinate_samples > MAX_PIXEL_COORDINATES
            or self.work_bounds.max_work_units > MAX_WORK_UNITS
        ):
            raise ValueError("template work bound exceeded")

    def validate_execution(
        self,
        *,
        registered_query_count: int,
        trace_position_count: int,
        coordinate_sample_count: int,
    ) -> None:
        """Validate actual registered pixel work against the compiled budget.

        A logical intent may compile to several finite pixel queries.  Those
        two counts are deliberately separate: the plan bounds finite compiled
        work, while execution records how much raster work was produced for
        this lane.
        """

        values = (
            registered_query_count,
            trace_position_count,
            coordinate_sample_count,
        )
        if any(not isinstance(value, int) or value < 0 for value in values):
            raise ValueError("template execution work must be non-negative")
        if registered_query_count > self.pixel_bounds.max_registered_queries:
            raise ValueError("template registered-query bound exceeded")
        if trace_position_count > self.pixel_bounds.max_trace_positions:
            raise ValueError("template trace-position bound exceeded")
        if coordinate_sample_count > self.pixel_bounds.max_coordinate_samples:
            raise ValueError("template coordinate-sample bound exceeded")

    def validate_measurement_receipt(
        self,
        *,
        pixel_query_count: int,
        peak_temporary_bytes: int,
    ) -> None:
        values = (pixel_query_count, peak_temporary_bytes)
        if any(not isinstance(value, int) or value < 0 for value in values):
            raise ValueError("template measurement receipt is invalid")
        if pixel_query_count > self.pixel_bounds.max_pixel_queries:
            raise ValueError("template pixel-query bound exceeded")
        if peak_temporary_bytes > self.pixel_bounds.max_peak_temporary_bytes:
            raise ValueError("template temporary-memory bound exceeded")
