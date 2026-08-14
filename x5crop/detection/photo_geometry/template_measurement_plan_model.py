"""Canonical records and bounds emitted by template measurement compilation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ...configuration.model import HolderLayoutAuthority
from ...domain import FiniteInterval
from ...formats import FormatSpec, FramePhysicalSpec
from ..evidence.scan_canvas import CanvasAxisScaleIntervals
from ..source_core import SourceStripValidationDomain
from .template_model import PhaseAuthority, TemplateSpec



MAX_QUERY_INTENTS = 6
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
    OUTER_SEQUENCE_ANCHOR = "outer_sequence_anchor"
    EARLY_SEQUENCE_ANCHOR = "early_sequence_anchor"
    MIDDLE_SEQUENCE_ANCHOR = "middle_sequence_anchor"
    LATE_SEQUENCE_ANCHOR = "late_sequence_anchor"
    TOP = "top"
    BOTTOM = "bottom"


class TemplateStopFact(str, Enum):
    FIXED_FORMAT_TEMPLATE = "fixed_format_template"
    FULL_CENTERED_PHASE_AUTHORITY = "full_centered_phase_authority"
    PARTIAL_FREE_PHASE_AUTHORITY = "partial_free_phase_authority"
    DIRECT_PHASE_EVIDENCE_REQUIRED = "direct_phase_evidence_required"
    REGISTERED_QUERY_SET_COMPLETE = "registered_query_set_complete"
    NO_PIXEL_ACCESS_DURING_COMPILE = "no_pixel_access_during_compile"


@dataclass(frozen=True)
class TemplateMeasurementInputs:
    """Typed authority consumed by :func:`compile_template_measurement_plan`."""

    format_spec: FormatSpec
    frame_spec: FramePhysicalSpec
    holder_layout_authority: HolderLayoutAuthority
    count: int
    full_count: int
    holder_full_count: int
    lane_authority: SourceStripValidationDomain
    layout: str
    scale_authority: CanvasAxisScaleIntervals

    def __post_init__(self) -> None:
        if not isinstance(self.format_spec, FormatSpec):
            raise TypeError("measurement inputs require a typed format spec")
        if not isinstance(self.frame_spec, FramePhysicalSpec):
            raise TypeError("measurement inputs require a frame physical spec")
        if self.frame_spec != self.format_spec.frame:
            raise ValueError("format and frame physical authority disagree")
        if not isinstance(
            self.holder_layout_authority,
            HolderLayoutAuthority,
        ):
            raise TypeError("measurement inputs require holder layout authority")
        if not isinstance(self.count, int) or isinstance(self.count, bool):
            raise TypeError("measurement count must be an integer")
        if (
            not isinstance(self.full_count, int)
            or isinstance(self.full_count, bool)
            or not isinstance(self.holder_full_count, int)
            or isinstance(self.holder_full_count, bool)
        ):
            raise TypeError("full counts must be integers")
        if (
            self.count <= 0
            or self.full_count <= 0
            or self.holder_full_count <= 0
            or self.count > self.full_count
        ):
            raise ValueError("measurement count is outside holder authority")
        if self.holder_layout_authority == HolderLayoutAuthority.USER_CONFIRMED_FILLED_HOLDER_LAYOUT:
            if self.count != self.full_count:
                raise ValueError("filled-holder layout requires the full count")
        elif self.holder_layout_authority != HolderLayoutAuthority.USER_CONFIRMED_NONFILLING_LAYOUT:
            raise TypeError("measurement inputs require a canonical layout authority")
        if self.layout not in {"horizontal", "vertical"}:
            raise ValueError("measurement layout must be horizontal or vertical")
        if not isinstance(self.lane_authority, SourceStripValidationDomain):
            raise TypeError("measurement inputs require source/lane authority")
        expected_long_axis = "x" if self.layout == "horizontal" else "y"
        if self.lane_authority.source_axis_long != expected_long_axis:
            raise ValueError("lane authority does not match measurement layout")
        if not isinstance(self.scale_authority, CanvasAxisScaleIntervals):
            raise TypeError("measurement inputs require existing scale authority")
        if self.scale_authority.holder_profile_id != self.lane_authority.authority_profile_id:
            raise ValueError("scale and lane authority profiles disagree")
        expected_axes = (
            ("x", "y") if self.layout == "horizontal" else ("y", "x")
        )
        if (
            self.scale_authority.source_width_axis,
            self.scale_authority.source_height_axis,
        ) != expected_axes:
            raise ValueError("scale authority axes do not match measurement layout")
        holder_count = self.format_spec.holder_full_count(
            self.lane_authority.authority_profile_id
        )
        if holder_count is None:
            raise ValueError("format has no full count for lane authority profile")
        if holder_count != self.holder_full_count:
            raise ValueError("declared holder count disagrees with format authority")
        lane_count = self.format_spec.layout.lane_count
        if self.holder_full_count % lane_count:
            raise ValueError("holder count cannot be distributed across lanes")
        if self.full_count != self.holder_full_count // lane_count:
            raise ValueError("lane full count disagrees with format layout")


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
        sequence_kind = self.kind in {
            MeasurementIntentKind.OUTER_SEQUENCE_ANCHOR,
            MeasurementIntentKind.EARLY_SEQUENCE_ANCHOR,
            MeasurementIntentKind.MIDDLE_SEQUENCE_ANCHOR,
            MeasurementIntentKind.LATE_SEQUENCE_ANCHOR,
        }
        if sequence_kind:
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
    max_local_relations: int

    def __post_init__(self) -> None:
        if min(
            self.max_role_bindings,
            self.max_inferred_roles,
            self.max_local_relations,
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
    max_peak_temporary_bytes: int

    def __post_init__(self) -> None:
        if min(
            self.max_registered_queries,
            self.max_trace_positions,
            self.max_coordinate_samples,
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
class TemplatePrecisionBudget:
    """Output-derived solo limits; final safety remains selected-only."""

    budget_id: str
    sequence_side_limit_px: float
    cross_side_limit_px: float
    maximum_pitch_steps: int
    pitch_step_solo_limit_px: float | None
    direction_solo_limit_degrees: float

    def __post_init__(self) -> None:
        if (
            not self.budget_id
            or self.sequence_side_limit_px <= 0.0
            or self.cross_side_limit_px <= 0.0
            or self.maximum_pitch_steps < 0
            or (
                self.pitch_step_solo_limit_px is not None
                and self.pitch_step_solo_limit_px <= 0.0
            )
            or self.direction_solo_limit_degrees <= 0.0
        ):
            raise ValueError("template precision budget is invalid")


@dataclass(frozen=True)
class TemplateNormalPathStopFacts:
    phase_authority: PhaseAuthority
    requires_direct_phase_evidence: bool
    facts: tuple[TemplateStopFact, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.phase_authority, PhaseAuthority):
            raise TypeError("normal-path facts require phase authority")
        if not isinstance(self.requires_direct_phase_evidence, bool):
            raise TypeError("normal-path direct-evidence flag must be boolean")
        if not self.facts or len(set(self.facts)) != len(self.facts):
            raise ValueError("normal-path facts must be unique and non-empty")
        if TemplateStopFact.DIRECT_PHASE_EVIDENCE_REQUIRED not in self.facts:
            raise ValueError("normal path must retain direct phase authority")
        expected = (
            TemplateStopFact.FULL_CENTERED_PHASE_AUTHORITY
            if self.phase_authority == PhaseAuthority.FULL_CENTERED
            else TemplateStopFact.PARTIAL_FREE_PHASE_AUTHORITY
        )
        if expected not in self.facts:
            raise ValueError("normal-path phase authority fact is missing")


@dataclass(frozen=True)
class TemplateCompileReceipt:
    """Proof that compilation was finite and pixel-free."""

    physical_identity: str
    plan_identity: str
    query_count: int
    role_count: int
    cross_fit_upper_bound: int
    placement_check_count: int
    pixel_coordinate_upper_bound: int
    work_unit_upper_bound: int
    pixel_read_count: int
    prevalidated: bool

    def __post_init__(self) -> None:
        values = (
            self.query_count,
            self.role_count,
            self.cross_fit_upper_bound,
            self.placement_check_count,
            self.pixel_coordinate_upper_bound,
            self.work_unit_upper_bound,
            self.pixel_read_count,
        )
        if (
            not self.physical_identity
            or not self.plan_identity
            or any(not isinstance(value, int) or value < 0 for value in values)
            or self.pixel_read_count != 0
            or not self.prevalidated
        ):
            raise ValueError("template compile receipt is invalid")
        if not isinstance(self.prevalidated, bool):
            raise TypeError("template compile prevalidation must be boolean")

    def validate_bounds(
        self,
        *,
        phase: TemplatePhaseBounds,
        cross: TemplateCrossBounds,
        placement: TemplatePlacementBounds,
        pixel: TemplatePixelBounds,
        work: TemplateWorkBounds,
    ) -> None:
        if self.query_count > min(pixel.max_registered_queries, work.max_query_intents):
            raise ValueError("template query bound exceeded")
        if self.role_count > phase.max_role_count:
            raise ValueError("template role bound exceeded")
        if self.cross_fit_upper_bound != cross.max_evaluated_fits:
            raise ValueError("template cross bound exceeded")
        if self.placement_check_count > placement.max_placement_checks:
            raise ValueError("template placement bound exceeded")
        if self.pixel_coordinate_upper_bound > pixel.max_coordinate_samples:
            raise ValueError("template pixel bound exceeded")
        if self.work_unit_upper_bound > work.max_work_units:
            raise ValueError("template work bound exceeded")


@dataclass(frozen=True)
class TemplateMeasurementPlan:
    """Canonical, immutable output of template compilation."""

    format_spec: FormatSpec
    frame_spec: FramePhysicalSpec
    holder_layout_authority: HolderLayoutAuthority
    count: int
    full_count: int
    holder_full_count: int
    lane_id: str
    layout: str
    lane_authority: SourceStripValidationDomain
    scale_authority: CanvasAxisScaleIntervals
    template_spec: TemplateSpec
    query_intents: tuple[TemplateQueryIntent, ...]
    projected_queries: TemplateProjectedQueryPlan
    phase_bounds: TemplatePhaseBounds
    role_bounds: TemplateRoleBounds
    cross_bounds: TemplateCrossBounds
    placement_bounds: TemplatePlacementBounds
    pixel_bounds: TemplatePixelBounds
    work_bounds: TemplateWorkBounds
    precision_budget: TemplatePrecisionBudget
    normal_path_stop_facts: TemplateNormalPathStopFacts
    physical_identity: str
    plan_identity: str
    compile_receipt: TemplateCompileReceipt

    def __post_init__(self) -> None:
        if not isinstance(self.lane_authority, SourceStripValidationDomain):
            raise TypeError("template plan requires source/lane authority")
        if not isinstance(self.scale_authority, CanvasAxisScaleIntervals):
            raise TypeError("template plan requires scale authority")
        if not isinstance(self.holder_layout_authority, HolderLayoutAuthority):
            raise TypeError("template plan requires holder layout authority")
        if not isinstance(self.count, int) or isinstance(self.count, bool):
            raise TypeError("template plan count must be an integer")
        if (
            not isinstance(self.full_count, int)
            or isinstance(self.full_count, bool)
            or not isinstance(self.holder_full_count, int)
            or isinstance(self.holder_full_count, bool)
        ):
            raise TypeError("template plan full counts must be integers")
        if not isinstance(self.normal_path_stop_facts, TemplateNormalPathStopFacts):
            raise TypeError("template plan requires stop facts")
        if not isinstance(self.compile_receipt, TemplateCompileReceipt):
            raise TypeError("template plan requires compile receipt")
        if (
            not isinstance(self.format_spec, FormatSpec)
            or not isinstance(self.frame_spec, FramePhysicalSpec)
            or self.frame_spec != self.format_spec.frame
            or not isinstance(self.holder_layout_authority, HolderLayoutAuthority)
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
            or (
                self.holder_layout_authority
                == HolderLayoutAuthority.USER_CONFIRMED_FILLED_HOLDER_LAYOUT
                and self.count != self.full_count
            )
            or self.scale_authority.holder_profile_id
            != self.lane_authority.authority_profile_id
            or (
                self.scale_authority.source_width_axis,
                self.scale_authority.source_height_axis,
            )
            != (("x", "y") if self.layout == "horizontal" else ("y", "x"))
            or not isinstance(self.template_spec, TemplateSpec)
            or not isinstance(self.projected_queries, TemplateProjectedQueryPlan)
            or not isinstance(self.precision_budget, TemplatePrecisionBudget)
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
        if self.compile_receipt.physical_identity != self.physical_identity:
            raise ValueError("compile receipt physical identity disagrees")
        if self.compile_receipt.plan_identity != self.plan_identity:
            raise ValueError("compile receipt plan identity disagrees")
        if self.compile_receipt.query_count != len(self.query_intents):
            raise ValueError("compile receipt query count disagrees")
        self.compile_receipt.validate_bounds(
            phase=self.phase_bounds,
            cross=self.cross_bounds,
            placement=self.placement_bounds,
            pixel=self.pixel_bounds,
            work=self.work_bounds,
        )

    @property
    def phase_authority(self) -> PhaseAuthority:
        return self.template_spec.phase_authority

    def validate_execution(
        self,
        *,
        registered_query_count: int,
        trace_position_count: int,
        coordinate_sample_count: int,
    ) -> None:
        """Validate actual registered pixel work against the compiled budget.

        A logical intent may compile to several finite pixel queries.  Those
        two counts are deliberately separate: the compile receipt proves six
        kinds of planned work, while the execution receipt proves how much
        raster work those intents actually produced for this lane.
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
