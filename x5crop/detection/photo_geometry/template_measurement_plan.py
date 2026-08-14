"""Pure compilation of one bounded template measurement plan.

The compiler consumes only declared physical authority.  It never opens an
image or asks for a pixel measurement.  Query intents are finite and carry
their physical unit explicitly; runtime measurement can project them through
the already selected scale authority without inventing candidate-local work.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import math

from ...configuration.model import HolderLayoutAuthority
from ...domain import Box, FiniteInterval, PositiveInterval
from ...formats import (
    FORMAT_CATALOG_REVISION,
    FRAME_DIMENSION_TOLERANCE_SPEC,
    DIRECT_USE_BUDGET_SPEC,
    FormatSpec,
    FramePhysicalSpec,
)
from ..evidence.scan_canvas import CanvasAxisScaleIntervals
from ..source_core import SourceStripValidationDomain
from .model import PHOTO_BOUNDARY_MEASUREMENT_SPEC
from .source_geometry import centered_short_axis_authority_px
from .template_model import PhaseAuthority, PhaseLatticeAuthority, TemplateSpec


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


def compile_template_measurement_plan(
    *,
    format_spec: FormatSpec,
    frame_spec: FramePhysicalSpec,
    holder_layout_authority: HolderLayoutAuthority,
    count: int,
    full_count: int,
    holder_full_count: int | None = None,
    lane_authority: SourceStripValidationDomain,
    layout: str,
    scale_authority: CanvasAxisScaleIntervals,
) -> TemplateMeasurementPlan:
    """Compile one fixed-format plan without touching pixels."""

    if holder_full_count is None:
        holder_full_count = full_count
    inputs = TemplateMeasurementInputs(
        format_spec=format_spec,
        frame_spec=frame_spec,
        holder_layout_authority=holder_layout_authority,
        count=count,
        full_count=full_count,
        holder_full_count=holder_full_count,
        lane_authority=lane_authority,
        layout=layout,
        scale_authority=scale_authority,
    )
    physical_identity = _stable_identity(
        "template-physical",
        FORMAT_CATALOG_REVISION,
        inputs.format_spec.format_id,
        inputs.frame_spec.identity_fields,
        inputs.holder_layout_authority.value,
        inputs.count,
        inputs.full_count,
        inputs.holder_full_count,
        inputs.lane_authority.lane_id,
        inputs.lane_authority.source_axis_long,
        inputs.lane_authority.authority_profile_id,
        inputs.layout,
    )
    phase_authority = (
        PhaseAuthority.FULL_CENTERED
        if inputs.holder_layout_authority
        == HolderLayoutAuthority.USER_CONFIRMED_FILLED_HOLDER_LAYOUT
        else PhaseAuthority.PARTIAL_FREE
    )
    frame_width_px = _scaled_extent(
        inputs.frame_spec.frame_width_mm,
        inputs.scale_authority.width_axis_px_per_mm,
        FRAME_DIMENSION_TOLERANCE_SPEC.frame_width_tolerance_ratio,
    )
    frame_height_px = _scaled_extent(
        inputs.frame_spec.frame_height_mm,
        inputs.scale_authority.height_axis_px_per_mm,
        FRAME_DIMENSION_TOLERANCE_SPEC.frame_height_tolerance_ratio,
    )
    gap_px = _gap_interval_px(
        inputs.frame_spec,
        inputs.scale_authority.width_axis_px_per_mm,
        frame_width_px,
    )
    pitch_px = FiniteInterval(
        frame_width_px.minimum + gap_px.minimum,
        frame_width_px.maximum + gap_px.maximum,
    )
    long_extent_px = (
        inputs.lane_authority.work_box.width
        if inputs.lane_authority.source_axis_long == "x"
        else inputs.lane_authority.work_box.height
    )
    phase_lattice = PhaseLatticeAuthority(
        period_px=pitch_px,
        cycle_origin_px=0.0,
        minimum_slot_offset=-1,
        maximum_slot_offset=max(
            inputs.full_count,
            int(math.ceil(long_extent_px / pitch_px.minimum)) + 1,
        ),
        phase_authority=phase_authority,
    )
    template_spec = TemplateSpec(
        template_id=f"{physical_identity}:spec",
        frame_width_px=frame_width_px,
        frame_height_px=frame_height_px,
        pitch_px=pitch_px,
        nominal_gap_px=gap_px,
        count=inputs.count,
        phase_authority=phase_authority,
        phase_lattice_authority=phase_lattice,
    )
    query_intents = _query_intents(
        physical_identity=physical_identity,
        frame_spec=inputs.frame_spec,
        count=inputs.count,
    )
    projected_queries = _project_queries(
        inputs.lane_authority.work_box,
        inputs.layout,
        inputs.frame_spec,
        frame_width_px,
        frame_height_px,
        inputs.scale_authority.width_axis_px_per_mm,
        inputs.scale_authority.height_axis_px_per_mm,
    )
    phase_bounds = TemplatePhaseBounds(
        max_hypotheses=MAX_PHASE_OBSERVATIONS * max(6, 2 * inputs.count),
        max_role_count=2 * inputs.count,
        max_direct_observations=MAX_PHASE_OBSERVATIONS,
    )
    role_bounds = TemplateRoleBounds(
        max_role_bindings=2 * inputs.count,
        max_inferred_roles=2 * inputs.count,
        max_local_relations=max(0, inputs.count - 1),
    )
    cross_bounds = TemplateCrossBounds(
        max_registered_runs=MAX_PHASE_OBSERVATIONS,
        max_fitted_observations=MAX_PHASE_OBSERVATIONS,
        max_compatible_pairs=MAX_CROSS_PAIRS,
        max_evaluated_fits=MAX_CROSS_PAIRS,
        max_inferred_observations=2,
    )
    placement_bounds = TemplatePlacementBounds(
        max_direction_candidates=2,
        max_placement_checks=MAX_PLACEMENT_CHECKS,
        max_safety_checks=inputs.count,
    )
    pixel_bounds, work_bounds = _bounds_for_lane(
        inputs.lane_authority.work_box,
        len(query_intents),
        inputs.count,
    )
    sequence_limit = frame_width_px.minimum * (
        DIRECT_USE_BUDGET_SPEC.sequence_ratio_per_side
    )
    cross_limit = frame_height_px.minimum * (
        DIRECT_USE_BUDGET_SPEC.cross_ratio_per_side
    )
    long_leverage = max(1.0, float(long_extent_px))
    short_extent_px = (
        inputs.lane_authority.work_box.height
        if inputs.lane_authority.source_axis_long == "x"
        else inputs.lane_authority.work_box.width
    )
    short_leverage = max(1.0, float(short_extent_px))
    precision_budget = TemplatePrecisionBudget(
        budget_id=_stable_identity(
            "template-precision",
            physical_identity,
            DIRECT_USE_BUDGET_SPEC,
        ),
        sequence_side_limit_px=sequence_limit,
        cross_side_limit_px=cross_limit,
        maximum_pitch_steps=max(0, inputs.count - 1),
        pitch_step_solo_limit_px=(
            None
            if inputs.count <= 1
            else sequence_limit / (inputs.count - 1)
        ),
        direction_solo_limit_degrees=math.degrees(
            min(
                math.atan(sequence_limit / short_leverage),
                math.atan(cross_limit / long_leverage),
            )
        ),
    )
    if 2 * inputs.count > phase_bounds.max_role_count:
        raise ValueError("template phase role bound overflow")
    facts = (
        TemplateStopFact.FIXED_FORMAT_TEMPLATE,
        (
            TemplateStopFact.FULL_CENTERED_PHASE_AUTHORITY
            if phase_authority == PhaseAuthority.FULL_CENTERED
            else TemplateStopFact.PARTIAL_FREE_PHASE_AUTHORITY
        ),
        TemplateStopFact.DIRECT_PHASE_EVIDENCE_REQUIRED,
        TemplateStopFact.REGISTERED_QUERY_SET_COMPLETE,
        TemplateStopFact.NO_PIXEL_ACCESS_DURING_COMPILE,
    )
    stop_facts = TemplateNormalPathStopFacts(
        phase_authority=phase_authority,
        requires_direct_phase_evidence=True,
        facts=facts,
    )
    plan_identity = _stable_identity(
        "template-plan",
        physical_identity,
        tuple(
            (
                item.kind.value,
                item.axis.value,
                item.coordinate_unit.value,
                tuple((p.minimum, p.maximum) for p in item.coordinate_positions),
                item.trace_unit.value,
                tuple((p.minimum, p.maximum) for p in item.trace_positions),
                (item.search_margin_mm.minimum, item.search_margin_mm.maximum),
                (item.expected_span_mm.minimum, item.expected_span_mm.maximum),
            )
            for item in query_intents
        ),
        phase_bounds,
        role_bounds,
        cross_bounds,
        placement_bounds,
    )
    receipt = TemplateCompileReceipt(
        physical_identity=physical_identity,
        plan_identity=plan_identity,
        query_count=len(query_intents),
        role_count=2 * inputs.count,
        cross_fit_upper_bound=cross_bounds.max_evaluated_fits,
        placement_check_count=MAX_PLACEMENT_CHECKS,
        pixel_coordinate_upper_bound=pixel_bounds.max_coordinate_samples,
        work_unit_upper_bound=work_bounds.max_work_units,
        pixel_read_count=0,
        prevalidated=True,
    )
    return TemplateMeasurementPlan(
        format_spec=inputs.format_spec,
        frame_spec=inputs.frame_spec,
        holder_layout_authority=inputs.holder_layout_authority,
        count=inputs.count,
        full_count=inputs.full_count,
        holder_full_count=inputs.holder_full_count,
        lane_id=inputs.lane_authority.lane_id,
        layout=inputs.layout,
        lane_authority=inputs.lane_authority,
        scale_authority=inputs.scale_authority,
        template_spec=template_spec,
        query_intents=query_intents,
        projected_queries=projected_queries,
        phase_bounds=phase_bounds,
        role_bounds=role_bounds,
        cross_bounds=cross_bounds,
        placement_bounds=placement_bounds,
        pixel_bounds=pixel_bounds,
        work_bounds=work_bounds,
        precision_budget=precision_budget,
        normal_path_stop_facts=stop_facts,
        physical_identity=physical_identity,
        plan_identity=plan_identity,
        compile_receipt=receipt,
    )


def _scaled_extent(
    design_mm: float,
    scale: PositiveInterval,
    tolerance_ratio: float,
) -> PositiveInterval:
    return PositiveInterval(
        design_mm * (1.0 - tolerance_ratio) * scale.minimum,
        design_mm * (1.0 + tolerance_ratio) * scale.maximum,
    )


def _gap_interval_px(
    frame_spec: FramePhysicalSpec,
    scale: PositiveInterval,
    width_px: PositiveInterval,
) -> FiniteInterval:
    if frame_spec.format_gap_prior_mm is not None:
        return FiniteInterval(
            frame_spec.format_gap_prior_mm * scale.minimum,
            frame_spec.format_gap_prior_mm * scale.maximum,
        )
    # An absent format prior remains a bounded generic physical interval.  It
    # does not identify a format or authorize placement by itself.
    return FiniteInterval(width_px.minimum * 0.02, width_px.maximum * 0.20)


def _lattice_positions(
    minimum: int,
    maximum: int,
    spacing_px: float,
) -> tuple[int, ...]:
    if maximum <= minimum:
        raise ValueError("query lattice requires positive extent")
    step = max(1, int(round(spacing_px)))
    first = min(maximum - 1, minimum + step // 2)
    values = list(range(first, maximum, step))
    if values[-1] < maximum - 1 - step // 2:
        values.append(maximum - 1)
    return tuple(sorted(set(values)))


def _clip_interval(
    interval: FiniteInterval,
    minimum: float,
    maximum: float,
) -> FiniteInterval:
    return FiniteInterval(
        max(minimum, interval.minimum),
        min(maximum, interval.maximum),
    )


def _project_queries(
    work_box: Box,
    layout: str,
    frame_spec: FramePhysicalSpec,
    frame_width_px: PositiveInterval,
    frame_height_px: PositiveInterval,
    long_scale: PositiveInterval,
    short_scale: PositiveInterval,
) -> TemplateProjectedQueryPlan:
    if layout not in {"horizontal", "vertical"}:
        raise ValueError("query projection requires a canonical layout")
    # SourceStripValidationDomain.work_box is already expressed in the
    # canonical work image: long coordinates are x and short coordinates are
    # y for both layouts.  Registered measurement later maps those canonical
    # coordinates onto the source X/Y axes.  Rotating the box here a second
    # time swaps the extents for vertical scans and registers every query
    # outside its source authority.
    long_min, long_max = work_box.left, work_box.right
    short_min, short_max = work_box.top, work_box.bottom
    if long_min != 0:
        raise ValueError("compiled sequence authority must begin at long zero")
    spec = PHOTO_BOUNDARY_MEASUREMENT_SPEC
    cross_traces = _lattice_positions(
        long_min,
        long_max,
        spec.lattice_spacing_mm(frame_spec.frame_width_mm) * long_scale.maximum,
    )
    short_authority = FiniteInterval(float(short_min), float(short_max - 1))
    center = centered_short_axis_authority_px(short_authority, short_scale)
    halo = spec.measurement_halo_px(short_scale.maximum)
    top = _clip_interval(
        FiniteInterval(
            center.minimum - frame_height_px.maximum / 2.0,
            center.maximum - frame_height_px.minimum / 2.0,
        ),
        float(short_min),
        float(short_max - 1),
    )
    bottom = _clip_interval(
        FiniteInterval(
            center.minimum + frame_height_px.minimum / 2.0,
            center.maximum + frame_height_px.maximum / 2.0,
        ),
        float(short_min),
        float(short_max - 1),
    )
    top_measured = _clip_interval(
        FiniteInterval(top.minimum - halo, top.maximum + halo),
        float(short_min),
        float(short_max - 1),
    )
    bottom_measured = _clip_interval(
        FiniteInterval(bottom.minimum - halo, bottom.maximum + halo),
        float(short_min),
        float(short_max - 1),
    )
    short_center = (short_min + short_max - 1) / 2.0
    half_height = min(
        (short_max - short_min - 2) / 2.0,
        frame_height_px.minimum / 2.0 - halo,
    )
    sequence_traces = _lattice_positions(
        max(short_min, int(math.ceil(short_center - half_height))),
        min(short_max, int(math.floor(short_center + half_height)) + 1),
        spec.lattice_spacing_mm(frame_spec.frame_height_mm) * short_scale.maximum,
    )
    return TemplateProjectedQueryPlan(
        long_extent_px=long_max - long_min,
        cross_trace_positions_px=cross_traces,
        top_core_intervals_px=tuple(top for _ in cross_traces),
        top_measurement_intervals_px=tuple(top_measured for _ in cross_traces),
        bottom_core_intervals_px=tuple(bottom for _ in cross_traces),
        bottom_measurement_intervals_px=tuple(bottom_measured for _ in cross_traces),
        sequence_trace_positions_px=sequence_traces,
        sequence_measurement_interval_px=FiniteInterval(
            float(long_min),
            float(long_max - 1),
        ),
        sequence_ownership_interval_px=FiniteInterval(
            float(long_min),
            float(long_max - 1),
        ),
        measurement_halo_px=halo,
    )


def _query_intents(
    *,
    physical_identity: str,
    frame_spec: FramePhysicalSpec,
    count: int,
) -> tuple[TemplateQueryIntent, ...]:
    early = 1.0 / float(count + 1)
    sequence_positions = (
        (MeasurementIntentKind.OUTER_SEQUENCE_ANCHOR, (0.0, 1.0)),
        (MeasurementIntentKind.EARLY_SEQUENCE_ANCHOR, (early,)),
        (MeasurementIntentKind.MIDDLE_SEQUENCE_ANCHOR, (0.5,)),
        (MeasurementIntentKind.LATE_SEQUENCE_ANCHOR, (1.0 - early,)),
    )
    margin = FiniteInterval(
        max(0.05, min(frame_spec.frame_width_mm, frame_spec.frame_height_mm) * 0.005),
        max(0.10, min(frame_spec.frame_width_mm, frame_spec.frame_height_mm) * 0.02),
    )
    intents: list[TemplateQueryIntent] = []
    for kind, positions in sequence_positions:
        intents.append(
            TemplateQueryIntent(
                intent_id=f"{physical_identity}:{kind.value}",
                kind=kind,
                axis=MeasurementAxis.LONG,
                coordinate_unit=MeasurementUnit.LANE_RATIO,
                coordinate_positions=tuple(FiniteInterval.exact(value) for value in positions),
                trace_unit=MeasurementUnit.LANE_RATIO,
                trace_positions=(FiniteInterval.exact(0.5),),
                search_margin_mm=margin,
                expected_span_mm=FiniteInterval.exact(frame_spec.frame_width_mm),
                registration_index=len(intents),
            )
        )
    for kind, position in (
        (MeasurementIntentKind.TOP, -frame_spec.frame_height_mm / 2.0),
        (MeasurementIntentKind.BOTTOM, frame_spec.frame_height_mm / 2.0),
    ):
        intents.append(
            TemplateQueryIntent(
                intent_id=f"{physical_identity}:{kind.value}",
                kind=kind,
                axis=MeasurementAxis.SHORT,
                coordinate_unit=MeasurementUnit.MILLIMETRES,
                coordinate_positions=(FiniteInterval.exact(position),),
                trace_unit=MeasurementUnit.LANE_RATIO,
                trace_positions=(FiniteInterval.exact(0.5),),
                search_margin_mm=margin,
                expected_span_mm=FiniteInterval.exact(frame_spec.frame_height_mm),
                registration_index=len(intents),
            )
        )
    return tuple(intents)


def _bounds_for_lane(
    work_box: Box,
    query_count: int,
    slot_count: int,
) -> tuple[TemplatePixelBounds, TemplateWorkBounds]:
    # Logical intent count and concrete query count are different contracts.
    # Current measurement can use many lattice traces under the six compiled
    # intents, but it must still remain bounded by source dimensions before
    # any candidate exists.
    coordinate_upper_bound = work_box.width * work_box.height * 16
    if coordinate_upper_bound <= 0 or coordinate_upper_bound > MAX_PIXEL_COORDINATES:
        raise ValueError("template pixel work bound exceeded")
    work_units = (
        query_count
        + (2 * slot_count)
        * MAX_PHASE_OBSERVATIONS
        * max(6, 2 * slot_count)
        + MAX_CROSS_PAIRS
        + MAX_PLACEMENT_CHECKS
    )
    if work_units > MAX_WORK_UNITS:
        raise ValueError("template work bound exceeded")
    pixel = TemplatePixelBounds(
        max_registered_queries=MAX_REGISTERED_QUERIES,
        max_trace_positions=2 * (work_box.width + work_box.height),
        max_coordinate_samples=coordinate_upper_bound,
        max_peak_temporary_bytes=coordinate_upper_bound * 10 + 32 * 1024 * 1024,
    )
    return pixel, TemplateWorkBounds(
        max_query_intents=query_count,
        max_work_units=work_units,
    )


def _stable_identity(prefix: str, *parts: object) -> str:
    payload = repr(parts).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()[:24]
    return f"{prefix}:{digest}"


__all__ = [
    "MeasurementAxis",
    "MeasurementIntentKind",
    "MeasurementUnit",
    "TemplateCompileReceipt",
    "TemplateCrossBounds",
    "TemplateMeasurementInputs",
    "TemplateMeasurementPlan",
    "TemplateNormalPathStopFacts",
    "TemplatePhaseBounds",
    "TemplatePixelBounds",
    "TemplatePlacementBounds",
    "TemplatePrecisionBudget",
    "TemplateQueryIntent",
    "TemplateRoleBounds",
    "TemplateStopFact",
    "TemplateWorkBounds",
    "compile_template_measurement_plan",
]
