"""Fixed-height, current-only short-axis template fitting.

The template and holder geometry are physical authority.  Registered edge
observations may support or veto that authority, but they do not create a
new height or a new direction.  This module deliberately stops at a small
fit/competition contract and has no dependency on downstream placement
objects.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, replace
from enum import Enum
import math
from typing import Sequence

from ...domain import FiniteInterval, ObservationId, PositiveInterval
from .line_observations import PhotoBoundaryObservation
from .model import (
    BoundaryAxis,
    BoundaryRole,
    MINIMUM_INDEPENDENT_SUPPORT_REGIONS,
    SPATIAL_SUPPORT_REGION_COUNT,
    independent_spatial_support_count,
)
from .observation_types import ProfileRun
from .output_model import SharedStripDirection
from .template_model import TemplateSpec


# Only overlapping measurement/model intervals describe one continuous
# answer.  The selected-output 3% budget is an acceptance limit, not authority
# to merge distinct observed edges into one placement.
_CONTINUOUS_SHIFT_RATIO = 0.0
_CONTINUOUS_HEIGHT_RATIO = 0.0
_CONTINUOUS_DIRECTION_DEGREES = 0.0


def _interval(value: FiniteInterval | PositiveInterval | float | int) -> FiniteInterval:
    if isinstance(value, FiniteInterval):
        return value
    if isinstance(value, PositiveInterval):
        return FiniteInterval(value.minimum, value.maximum)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return FiniteInterval.exact(float(value))
    raise TypeError("cross interval must be finite interval or number")


def _add(left: FiniteInterval, right: FiniteInterval) -> FiniteInterval:
    return FiniteInterval(left.minimum + right.minimum, left.maximum + right.maximum)


def _subtract(left: FiniteInterval, right: FiniteInterval) -> FiniteInterval:
    return FiniteInterval(left.minimum - right.maximum, left.maximum - right.minimum)


def _intersect(left: FiniteInterval, right: FiniteInterval) -> FiniteInterval | None:
    minimum = max(left.minimum, right.minimum)
    maximum = min(left.maximum, right.maximum)
    if minimum > maximum:
        return None
    return FiniteInterval(minimum, maximum)


def _midpoint_interval(left: FiniteInterval, right: FiniteInterval) -> FiniteInterval:
    return FiniteInterval(
        (left.minimum + right.minimum) / 2.0,
        (left.maximum + right.maximum) / 2.0,
    )


def _scale_interval(interval: FiniteInterval, factor: float) -> FiniteInterval:
    values = (interval.minimum * factor, interval.maximum * factor)
    return FiniteInterval(min(values), max(values))


def _observation_coordinate(
    observation: object,
    *,
    lane_reference_trace_px: float,
    boundary_axis: BoundaryAxis,
) -> FiniteInterval:
    """Project one fitted observation exactly once at the lane reference."""

    direct = getattr(observation, "coordinate_interval_px", None)
    if isinstance(direct, FiniteInterval):
        return direct
    line = getattr(observation, "line", None)
    offset = getattr(observation, "offset_interval_px", None)
    if line is None or not isinstance(offset, FiniteInterval):
        raise TypeError("cross observation needs coordinate or fitted line interval")
    if boundary_axis == BoundaryAxis.Y:
        normal = float(line.normal_y)
        other = float(line.normal_x)
    else:
        normal = float(line.normal_x)
        other = float(line.normal_y)
    if abs(normal) <= 1.0e-12:
        raise ValueError("cross observation line cannot project at lane reference")
    values = tuple(
        (value - other * lane_reference_trace_px) / normal
        for value in (offset.minimum, offset.maximum)
    )
    return FiniteInterval(min(values), max(values))


def _observation_direction(
    observation: object,
) -> tuple[float | None, FiniteInterval | None]:
    canonical = getattr(observation, "canonical_direction_degrees", None)
    if canonical is None:
        fitted = getattr(observation, "fit_angle_interval_degrees", None)
        if isinstance(fitted, FiniteInterval):
            canonical = fitted.center
    full = getattr(observation, "full_direction_interval_degrees", None)
    if full is None:
        full = getattr(observation, "angle_interval_degrees", None)
    if full is not None and not isinstance(full, FiniteInterval):
        raise TypeError("cross direction interval must be FiniteInterval")
    if canonical is not None and not math.isfinite(float(canonical)):
        raise ValueError("cross direction canonical angle is not finite")
    if canonical is not None and full is None:
        raise ValueError("cross direction canonical angle needs full interval")
    return (None if canonical is None else float(canonical), full)


class CrossEvidence(str, Enum):
    """Role-ledger provenance for one short-axis edge."""

    DIRECT = "direct"
    FIXED_HEIGHT_INFERRED = "fixed_height_inferred"


@dataclass(frozen=True)
class CrossRoleBinding:
    """One registered top/bottom role measured at the lane reference.

    Role and polarity are registration responsibilities.  Fitting consumes
    this typed role and never attempts to reclassify it.  The two support
    provenance fields are copied from ``PhotoBoundaryObservation`` so that a
    one-sided fit cannot turn an isolated strong line into placement authority.
    """

    role: BoundaryRole
    run_id: str
    observation_id: ObservationId
    coordinate_interval_px: FiniteInterval
    trace_coordinates_px: tuple[int, ...] = ()
    support_fraction: float = 1.0
    continuous_support_fraction: float = 1.0
    fit_residual_px: float = 0.0
    fit_interval_px: FiniteInterval | None = None
    full_interval_px: FiniteInterval | None = None
    canonical_direction_degrees: float | None = None
    fit_direction_interval_degrees: FiniteInterval | None = None
    full_direction_interval_degrees: FiniteInterval | None = None
    evidence: CrossEvidence = CrossEvidence.DIRECT
    source_observation_ids: tuple[ObservationId, ...] = ()
    independent_support_region_count: int = 0
    source_spanning_continuous: bool = False
    role_authorized: bool = True

    def __post_init__(self) -> None:
        if self.role not in {BoundaryRole.TOP, BoundaryRole.BOTTOM}:
            raise ValueError("cross role binding requires top or bottom")
        if not self.run_id:
            raise ValueError("cross role binding requires a run identity")
        identity = (
            self.observation_id
            if isinstance(self.observation_id, ObservationId)
            else ObservationId(str(self.observation_id))
        )
        object.__setattr__(self, "observation_id", identity)
        if not isinstance(self.coordinate_interval_px, FiniteInterval):
            object.__setattr__(self, "coordinate_interval_px", _interval(self.coordinate_interval_px))
        if self.fit_interval_px is None:
            object.__setattr__(self, "fit_interval_px", self.coordinate_interval_px)
        elif not isinstance(self.fit_interval_px, FiniteInterval):
            object.__setattr__(self, "fit_interval_px", _interval(self.fit_interval_px))
        if self.full_interval_px is None:
            object.__setattr__(self, "full_interval_px", self.coordinate_interval_px)
        elif not isinstance(self.full_interval_px, FiniteInterval):
            object.__setattr__(self, "full_interval_px", _interval(self.full_interval_px))
        if self.fit_interval_px is None or self.full_interval_px is None:
            raise AssertionError("cross intervals were not initialized")
        if (
            self.fit_interval_px.minimum < self.full_interval_px.minimum
            or self.fit_interval_px.maximum > self.full_interval_px.maximum
        ):
            raise ValueError("cross fit interval must remain inside full interval")
        if tuple(sorted(set(self.trace_coordinates_px))) != self.trace_coordinates_px:
            raise ValueError("cross trace coordinates must be sorted and unique")
        if not 0.0 <= self.support_fraction <= 1.0:
            raise ValueError("cross support fraction is invalid")
        if not 0.0 <= self.continuous_support_fraction <= 1.0:
            raise ValueError("cross continuous support fraction is invalid")
        if not math.isfinite(self.fit_residual_px) or self.fit_residual_px < 0.0:
            raise ValueError("cross fit residual is invalid")
        if not isinstance(self.evidence, CrossEvidence):
            raise TypeError("cross evidence must be typed")
        if (
            not isinstance(self.independent_support_region_count, int)
            or self.independent_support_region_count < 0
            or not isinstance(self.source_spanning_continuous, bool)
            or not isinstance(self.role_authorized, bool)
        ):
            raise ValueError("cross support provenance is invalid")
        if self.full_direction_interval_degrees is not None and not isinstance(
            self.full_direction_interval_degrees, FiniteInterval
        ):
            raise TypeError("cross full direction interval must be FiniteInterval")
        if self.fit_direction_interval_degrees is not None and not isinstance(
            self.fit_direction_interval_degrees, FiniteInterval
        ):
            raise TypeError("cross fit direction interval must be FiniteInterval")
        if self.canonical_direction_degrees is not None:
            if (
                self.fit_direction_interval_degrees is None
                or self.full_direction_interval_degrees is None
            ):
                raise ValueError("cross canonical direction needs fit and full intervals")
            if (
                self.fit_direction_interval_degrees.minimum
                < self.full_direction_interval_degrees.minimum
                or self.fit_direction_interval_degrees.maximum
                > self.full_direction_interval_degrees.maximum
            ):
                raise ValueError("cross fit direction must remain inside full interval")
            if not self.fit_direction_interval_degrees.contains(
                float(self.canonical_direction_degrees), epsilon=1.0e-9
            ):
                raise ValueError("cross canonical direction is outside fit interval")
            if not self.full_direction_interval_degrees.contains(
                float(self.canonical_direction_degrees), epsilon=1.0e-9
            ):
                raise ValueError("cross canonical direction is outside full interval")
        source = tuple(
            item if isinstance(item, ObservationId) else ObservationId(str(item))
            for item in self.source_observation_ids
        )
        if self.evidence == CrossEvidence.DIRECT:
            source = (identity,)
        elif not source:
            raise ValueError("inferred cross binding needs source observations")
        if len(set(source)) != len(source):
            raise ValueError("cross source observations must be unique")
        object.__setattr__(self, "source_observation_ids", source)

    @classmethod
    def from_measurement(
        cls,
        run: ProfileRun,
        observation: PhotoBoundaryObservation,
        *,
        lane_reference_trace_px: float,
        boundary_axis: BoundaryAxis = BoundaryAxis.Y,
    ) -> "CrossRoleBinding":
        """Bind one run to one already fitted observation exactly once."""

        if run.role_hint not in {BoundaryRole.TOP, BoundaryRole.BOTTOM}:
            raise ValueError("cross measurement run must carry top/bottom role")
        if getattr(observation, "role", run.role_hint) != run.role_hint:
            raise ValueError("cross run and fitted observation roles disagree")
        coordinate = _observation_coordinate(
            observation,
            lane_reference_trace_px=lane_reference_trace_px,
            boundary_axis=boundary_axis,
        )
        fit = getattr(observation, "fit_position_interval_px", None)
        if not isinstance(fit, FiniteInterval):
            fit = coordinate
        canonical, direction = _observation_direction(observation)
        return cls(
            role=run.role_hint,
            run_id=run.run_id,
            observation_id=observation.observation_id,
            coordinate_interval_px=coordinate,
            trace_coordinates_px=tuple(run.trace_coordinates_px),
            support_fraction=float(run.support_fraction),
            continuous_support_fraction=float(run.continuous_support_fraction),
            fit_residual_px=float(observation.fit_residual_px),
            fit_interval_px=fit,
            full_interval_px=coordinate,
            canonical_direction_degrees=canonical,
            fit_direction_interval_degrees=(
                observation.fit_angle_interval_degrees
            ),
            full_direction_interval_degrees=direction,
            independent_support_region_count=int(
                getattr(observation, "independent_support_region_count", 0)
            ),
            source_spanning_continuous=bool(
                getattr(observation, "source_spanning_continuous", False)
            ),
            role_authorized=(
                float(
                    getattr(
                        observation,
                        (
                            "left_background_preference_fraction"
                            if run.role_hint == BoundaryRole.TOP
                            else "right_background_preference_fraction"
                        ),
                        0.0,
                    )
                )
                > 0.5
            ),
        )


@dataclass(frozen=True)
class TemplateCrossInput:
    """Inputs for one fixed-height short-axis fit."""

    template: TemplateSpec
    fixed_height_px: FiniteInterval | PositiveInterval | float | None = None
    canonical_fixed_height_px: float | None = None
    holder_short_axis_center_px: FiniteInterval | float | None = None
    lane_reference_trace_px: float = 0.0
    top_bindings: tuple[CrossRoleBinding, ...] = ()
    bottom_bindings: tuple[CrossRoleBinding, ...] = ()
    top_runs: tuple[ProfileRun, ...] = ()
    bottom_runs: tuple[ProfileRun, ...] = ()
    top_observations: tuple[PhotoBoundaryObservation, ...] = ()
    bottom_observations: tuple[PhotoBoundaryObservation, ...] = ()
    registered_trace_coordinates_px: tuple[int, ...] = ()
    longitudinal_support_domains_px: tuple[FiniteInterval, ...] = ()
    boundary_axis: BoundaryAxis = BoundaryAxis.Y
    maximum_registered_runs: int = 256
    maximum_fitted_observations: int = 256
    maximum_compatible_pairs: int = 4096
    maximum_evaluated_fits: int = 4096
    minimum_shared_trace_support: int = 2
    parallel_direction_tolerance_degrees: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.template, TemplateSpec):
            raise TypeError("template cross input requires TemplateSpec")
        if self.fixed_height_px is None:
            if self.template.frame_height_px is None:
                raise ValueError("fixed template height is required")
            height = _interval(self.template.frame_height_px)
        else:
            height = _interval(self.fixed_height_px)
        if height.minimum <= 0.0:
            raise ValueError("fixed template height must be positive")
        object.__setattr__(self, "fixed_height_px", height)
        canonical_height = (
            height.center
            if self.canonical_fixed_height_px is None
            else float(self.canonical_fixed_height_px)
        )
        if (
            not math.isfinite(canonical_height)
            or not height.contains(canonical_height, epsilon=1.0e-9)
        ):
            raise ValueError("canonical fixed height leaves physical authority")
        object.__setattr__(self, "canonical_fixed_height_px", canonical_height)
        if self.template.frame_height_px is not None:
            template_height = _interval(self.template.frame_height_px)
            if _intersect(height, template_height) is None:
                raise ValueError("fixed height contradicts template frame height")
        if self.holder_short_axis_center_px is not None:
            object.__setattr__(self, "holder_short_axis_center_px", _interval(self.holder_short_axis_center_px))
        if not math.isfinite(float(self.lane_reference_trace_px)):
            raise ValueError("lane reference trace must be finite")
        if self.boundary_axis not in {BoundaryAxis.X, BoundaryAxis.Y}:
            raise ValueError("cross boundary axis is invalid")
        registered = tuple(self.registered_trace_coordinates_px)
        if registered and (
            tuple(sorted(set(registered))) != registered
            or any(not isinstance(value, int) for value in registered)
        ):
            raise ValueError("cross registered trace domain is invalid")
        domains = tuple(self.longitudinal_support_domains_px)
        if domains and (
            len(domains) != self.template.count
            or any(not isinstance(item, FiniteInterval) for item in domains)
            or any(
                left.maximum >= right.minimum
                for left, right in zip(domains, domains[1:])
            )
        ):
            raise ValueError("cross longitudinal support domains are invalid")
        bounds = (
            self.maximum_registered_runs,
            self.maximum_fitted_observations,
            self.maximum_compatible_pairs,
            self.maximum_evaluated_fits,
        )
        if any(not isinstance(value, int) or value <= 0 for value in bounds):
            raise ValueError("cross work bounds must be positive integers")
        if not isinstance(self.minimum_shared_trace_support, int) or self.minimum_shared_trace_support < 0:
            raise ValueError("cross shared-support minimum cannot be negative")
        if (
            not math.isfinite(self.parallel_direction_tolerance_degrees)
            or self.parallel_direction_tolerance_degrees < 0.0
        ):
            raise ValueError("cross parallel-direction tolerance is invalid")


@dataclass(frozen=True)
class CrossSearchReceipt:
    """Auditable work counts and their explicit structural bounds."""

    registered_run_count: int
    fitted_observation_count: int
    compatible_pair_count: int
    single_side_inference_count: int
    evaluated_fit_count: int
    registered_run_bound: int
    fitted_observation_bound: int
    compatible_pair_bound: int
    evaluated_fit_bound: int

    def __post_init__(self) -> None:
        values = (
            self.registered_run_count,
            self.fitted_observation_count,
            self.compatible_pair_count,
            self.single_side_inference_count,
            self.evaluated_fit_count,
            self.registered_run_bound,
            self.fitted_observation_bound,
            self.compatible_pair_bound,
            self.evaluated_fit_bound,
        )
        if any(not isinstance(value, int) or value < 0 for value in values):
            raise ValueError("cross search receipt counts must be non-negative")
        if any(
            value <= 0
            for value in (
                self.registered_run_bound,
                self.fitted_observation_bound,
                self.compatible_pair_bound,
                self.evaluated_fit_bound,
            )
        ):
            raise ValueError("cross search receipt bounds must be positive")

    def validate_bounds(self) -> None:
        if self.registered_run_count > self.registered_run_bound:
            raise ValueError("cross registered-run bound exceeded")
        if self.fitted_observation_count > self.fitted_observation_bound:
            raise ValueError("cross fitted-observation bound exceeded")
        if self.compatible_pair_count > self.compatible_pair_bound:
            raise ValueError("cross compatible-pair bound exceeded")
        if self.evaluated_fit_count > self.evaluated_fit_bound:
            raise ValueError("cross evaluated-fit bound exceeded")


class CrossFitStatus(str, Enum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    BOUND_EXCEEDED = "bound_exceeded"


@dataclass(frozen=True)
class CrossFit:
    """One short-axis fit with direct/inferred role and closure provenance."""

    template_id: str
    lane_reference_trace_px: float
    fixed_height_px: FiniteInterval
    top_canonical_px: float
    bottom_canonical_px: float
    top_fit_interval_px: FiniteInterval
    bottom_fit_interval_px: FiniteInterval
    top_full_interval_px: FiniteInterval
    bottom_full_interval_px: FiniteInterval
    direct_bindings: tuple[CrossRoleBinding, ...]
    inferred_bindings: tuple[CrossRoleBinding, ...]
    selected_direction: SharedStripDirection | None
    direct_pair: bool
    shared_trace_support_count: int
    continuous_support_fraction: float
    residual_sum_px: float
    center_compatible: bool
    height_compatibility_px: FiniteInterval | None = None
    shift_interval_px: FiniteInterval | None = None
    center_interval_px: FiniteInterval | None = None
    parallel_direction_interval_degrees: FiniteInterval | None = None
    direction_provenance_ids: tuple[ObservationId, ...] = ()
    single_side_inferred: bool = False
    direct_provenance_ids: tuple[ObservationId, ...] = ()
    independent_support_region_count: int = 0
    longitudinal_support_domain_count: int = 0
    role_authorized_pair_support_domain_count: int = 0

    def __post_init__(self) -> None:
        if not self.template_id:
            raise ValueError("cross fit requires a template identity")
        if not self.fixed_height_px.contains(
            self.bottom_canonical_px - self.top_canonical_px,
            epsilon=max(self.fixed_height_px.width, 1.0e-8),
        ) and self.direct_pair:
            raise ValueError("direct cross fit does not preserve fixed height")
        if not self.top_full_interval_px.contains(self.top_canonical_px, epsilon=1.0e-9) or not self.bottom_full_interval_px.contains(self.bottom_canonical_px, epsilon=1.0e-9):
            raise ValueError("cross canonical positions must be inside full intervals")
        if (
            self.top_fit_interval_px.minimum < self.top_full_interval_px.minimum
            or self.top_fit_interval_px.maximum > self.top_full_interval_px.maximum
            or self.bottom_fit_interval_px.minimum < self.bottom_full_interval_px.minimum
            or self.bottom_fit_interval_px.maximum > self.bottom_full_interval_px.maximum
        ):
            raise ValueError("cross fit interval leaves its full interval")
        if self.direct_pair and len(self.direct_bindings) != 2:
            raise ValueError("direct cross fit requires two direct bindings")
        if not self.direct_pair and len(self.direct_bindings) != 1:
            raise ValueError("single-side cross fit requires one direct binding")
        if any(item.evidence != CrossEvidence.DIRECT for item in self.direct_bindings):
            raise ValueError("direct ledger contains inferred binding")
        if any(item.evidence != CrossEvidence.FIXED_HEIGHT_INFERRED for item in self.inferred_bindings):
            raise ValueError("inferred ledger contains direct binding")
        if self.shared_trace_support_count < 0:
            raise ValueError("cross shared support count is invalid")
        if not 0 <= self.independent_support_region_count <= 3:
            raise ValueError("cross independent support count is invalid")
        if not 0 <= self.longitudinal_support_domain_count <= 3:
            raise ValueError("cross longitudinal support count is invalid")
        if not 0 <= self.role_authorized_pair_support_domain_count <= 3:
            raise ValueError("cross role-authorized support count is invalid")
        if not 0.0 <= self.continuous_support_fraction <= 1.0:
            raise ValueError("cross continuous support is invalid")
        if not math.isfinite(self.residual_sum_px) or self.residual_sum_px < 0.0:
            raise ValueError("cross residual is invalid")
        if not isinstance(self.center_compatible, bool) or not isinstance(self.single_side_inferred, bool):
            raise ValueError("cross closure flags are invalid")
        for interval in (
            self.height_compatibility_px,
            self.shift_interval_px,
            self.center_interval_px,
            self.parallel_direction_interval_degrees,
        ):
            if interval is not None and not isinstance(interval, FiniteInterval):
                raise TypeError("cross closure interval must be FiniteInterval")
        ids = tuple(
            item if isinstance(item, ObservationId) else ObservationId(str(item))
            for item in self.direction_provenance_ids
        )
        if len(set(ids)) != len(ids):
            raise ValueError("cross direction provenance IDs must be unique")
        object.__setattr__(self, "direction_provenance_ids", ids)
        direct_ids = tuple(
            item if isinstance(item, ObservationId) else ObservationId(str(item))
            for item in self.direct_provenance_ids
        )
        if not direct_ids:
            direct_ids = tuple(item.observation_id for item in self.direct_bindings)
        if len(set(direct_ids)) != len(direct_ids):
            raise ValueError("cross direct provenance IDs must be unique")
        object.__setattr__(self, "direct_provenance_ids", direct_ids)

    @property
    def direct_observation_ids(self) -> tuple[ObservationId, ...]:
        return self.direct_provenance_ids

    @property
    def inferred_observation_ids(self) -> tuple[ObservationId, ...]:
        return tuple(identity for item in self.inferred_bindings for identity in item.source_observation_ids)

    @property
    def role_ledger(self) -> tuple[CrossRoleBinding, ...]:
        return self.direct_bindings + self.inferred_bindings


@dataclass(frozen=True)
class CrossFitCompetition:
    """Best/runner-up decision; only a clearly single physical group resolves."""

    template_id: str
    best: CrossFit | None
    runner_up: CrossFit | None
    status: CrossFitStatus
    reason: str | None
    receipt: CrossSearchReceipt

    def __post_init__(self) -> None:
        if self.status == CrossFitStatus.RESOLVED and self.best is None:
            raise ValueError("resolved cross competition requires a best fit")
        if self.status == CrossFitStatus.BOUND_EXCEEDED and self.best is not None:
            raise ValueError("bound-exceeded cross competition cannot select a fit")
        if self.reason is not None and not self.reason:
            raise ValueError("cross competition reason cannot be empty")


@dataclass(frozen=True)
class _Candidate:
    top: CrossRoleBinding
    bottom: CrossRoleBinding
    direct_pair: bool
    shared_support: int
    continuous_support: float
    residual: float
    center_compatible: bool
    height_compatibility: FiniteInterval
    canonical_height_px: float
    shift_interval: FiniteInterval
    center_interval: FiniteInterval | None
    direction_interval: FiniteInterval | None
    direction_ready: bool
    support_trace_coordinates_px: tuple[int, ...]
    top_full_override: FiniteInterval | None = None
    bottom_full_override: FiniteInterval | None = None


def _shared_trace_coordinates(
    top: CrossRoleBinding,
    bottom: CrossRoleBinding,
) -> tuple[int, ...]:
    if not top.trace_coordinates_px or not bottom.trace_coordinates_px:
        return ()
    common = tuple(sorted(set(top.trace_coordinates_px).intersection(bottom.trace_coordinates_px)))
    if common:
        return common
    # Registered corridors can use staggered lattices.  Independent regions
    # on both lines still provide one local direct relation without inventing
    # common pixels.  Their midpoint names that shared physical support.
    maximum_distance = max(1.0, _median_trace_step((*top.trace_coordinates_px, *bottom.trace_coordinates_px)))
    return tuple(
        sorted(
            {
                int(round((left + right) / 2.0))
                for left in top.trace_coordinates_px
                for right in bottom.trace_coordinates_px
                if abs(left - right) <= maximum_distance
            }
        )
    )


def _median_trace_step(values: Sequence[int]) -> float:
    ordered = tuple(sorted(set(values)))
    if len(ordered) < 2:
        return 1.0
    steps = tuple(right - left for left, right in zip(ordered, ordered[1:]))
    return float(sorted(steps)[len(steps) // 2])


def _direction_closure(
    top: CrossRoleBinding,
    bottom: CrossRoleBinding,
    *,
    parallel_tolerance_degrees: float,
) -> tuple[FiniteInterval | None, bool, bool]:
    """Return (parallel interval, direction-ready, contradiction)."""

    # Statistical fit intervals decide whether two fragments can be the same
    # parallel physical edge family.  The wider full intervals are retained
    # for selected-output safety; using them here lets an isolated noisy line
    # become a competing placement merely because its uncertainty is broad.
    top_interval = top.fit_direction_interval_degrees
    bottom_interval = bottom.fit_direction_interval_degrees
    if top_interval is not None and bottom_interval is not None:
        per_edge = parallel_tolerance_degrees / 2.0
        common = _intersect(
            FiniteInterval(
                top_interval.minimum - per_edge,
                top_interval.maximum + per_edge,
            ),
            FiniteInterval(
                bottom_interval.minimum - per_edge,
                bottom_interval.maximum + per_edge,
            ),
        )
        if common is None:
            return None, False, True
        ready = (
            top.canonical_direction_degrees is not None
            and bottom.canonical_direction_degrees is not None
        )
        return common, ready, False
    if top_interval is not None:
        return top_interval, top.canonical_direction_degrees is not None, False
    if bottom_interval is not None:
        return bottom_interval, bottom.canonical_direction_degrees is not None, False
    return None, False, False


def _single_direction_ready(binding: CrossRoleBinding) -> bool:
    return (
        binding.fit_direction_interval_degrees is not None
        and binding.full_direction_interval_degrees is not None
        and binding.canonical_direction_degrees is not None
    )


def _direct_candidate(
    top: CrossRoleBinding,
    bottom: CrossRoleBinding,
    *,
    fixed_height: FiniteInterval,
    canonical_height_px: float,
    center: FiniteInterval | None,
    minimum_shared_trace_support: int,
    parallel_direction_tolerance_degrees: float,
) -> _Candidate | None:
    expected_bottom = _add(top.full_interval_px, fixed_height)
    if _intersect(bottom.full_interval_px, expected_bottom) is None:
        return None
    height = _intersect(fixed_height, _subtract(bottom.full_interval_px, top.full_interval_px))
    shift = _intersect(top.full_interval_px, _subtract(bottom.full_interval_px, fixed_height))
    if height is None or shift is None:
        return None
    support_traces = _shared_trace_coordinates(top, bottom)
    if not support_traces:
        return None
    direction, direction_ready, contradiction = _direction_closure(
        top,
        bottom,
        parallel_tolerance_degrees=parallel_direction_tolerance_degrees,
    )
    if contradiction:
        return None
    midpoint = _midpoint_interval(top.full_interval_px, bottom.full_interval_px)
    center_interval = _intersect(midpoint, center) if center is not None else midpoint
    selected_canonical_height = (
        height.center
        if top.source_spanning_continuous
        or bottom.source_spanning_continuous
        else canonical_height_px
    )
    return _Candidate(
        top=top,
        bottom=bottom,
        direct_pair=True,
        shared_support=0,
        continuous_support=min(top.continuous_support_fraction, bottom.continuous_support_fraction),
        residual=top.fit_residual_px + bottom.fit_residual_px,
        center_compatible=center_interval is not None,
        height_compatibility=height,
        canonical_height_px=selected_canonical_height,
        shift_interval=shift,
        center_interval=center_interval,
        direction_interval=direction,
        direction_ready=direction_ready,
        support_trace_coordinates_px=support_traces,
    )


def _single_candidate(
    binding: CrossRoleBinding,
    *,
    fixed_height: FiniteInterval,
    canonical_height_px: float,
    center: FiniteInterval | None,
) -> _Candidate | None:
    # A single edge needs independent spatial support and direct direction.
    # Without holder-centre authority it must additionally span the complete
    # registered domain before its coordinate can own placement.
    if (
        binding.independent_support_region_count
        < SPATIAL_SUPPORT_REGION_COUNT
        or not _single_direction_ready(binding)
        or (center is None and not binding.source_spanning_continuous)
    ):
        return None
    if center is not None:
        half_height = _scale_interval(fixed_height, 0.5)
        centered_top = _subtract(center, half_height)
        centered_bottom = _add(center, half_height)
        expected_side = (
            centered_top
            if binding.role == BoundaryRole.TOP
            else centered_bottom
        )
        if _intersect(binding.full_interval_px, expected_side) is None:
            return None
        # Format H and holder centre own the canonical placement.  Their broad
        # compatibility intervals answer only whether this model is legal;
        # they are not selected-placement measurement uncertainty.  Safety
        # starts at the canonical fixed rectangle and expands only toward the
        # directly observed side.
        canonical_center = center.center
        canonical_top = canonical_center - canonical_height_px / 2.0
        canonical_bottom = canonical_center + canonical_height_px / 2.0
        # Holder-centre uncertainty is only a compatibility fact.  The fixed
        # physical H interval, however, is genuine selected-template
        # uncertainty: keeping the canonical centre fixed moves the two sides
        # symmetrically.  This is later checked against the sole 3% direct-use
        # budget and never becomes a competing placement.
        top_full = FiniteInterval(
            canonical_center - fixed_height.maximum / 2.0,
            canonical_center - fixed_height.minimum / 2.0,
        )
        bottom_full = FiniteInterval(
            canonical_center + fixed_height.minimum / 2.0,
            canonical_center + fixed_height.maximum / 2.0,
        )
        if binding.role == BoundaryRole.TOP:
            top_full = _hull_intervals((top_full, binding.full_interval_px))
        else:
            bottom_full = _hull_intervals(
                (bottom_full, binding.full_interval_px)
            )
        return _Candidate(
            top=binding,
            bottom=binding,
            direct_pair=False,
            shared_support=0,
            continuous_support=binding.continuous_support_fraction,
            residual=binding.fit_residual_px,
            center_compatible=True,
            height_compatibility=fixed_height,
            canonical_height_px=canonical_height_px,
            shift_interval=FiniteInterval.exact(canonical_top),
            center_interval=center,
            direction_interval=binding.full_direction_interval_degrees,
            direction_ready=True,
            support_trace_coordinates_px=binding.trace_coordinates_px,
            top_full_override=top_full,
            bottom_full_override=bottom_full,
        )
    if binding.role == BoundaryRole.TOP:
        top = binding
        bottom = binding
        top_full = binding.full_interval_px
        height = fixed_height
        if center is not None:
            height = _intersect(
                height,
                _scale_interval(_subtract(center, top_full), 2.0),
            )
            if height is None:
                return None
        bottom_full = _add(top_full, height)
    else:
        top = binding
        bottom = binding
        bottom_full = binding.full_interval_px
        height = fixed_height
        if center is not None:
            height = _intersect(
                height,
                _scale_interval(_subtract(bottom_full, center), 2.0),
            )
            if height is None:
                return None
        top_full = _subtract(bottom_full, height)
    if center is not None:
        # The holder-centre interval and fixed-H relation jointly locate the
        # inferred side.  Intersect both equivalent expressions so uncertainty
        # is not counted independently a second time.
        centered_top = _subtract(_scale_interval(center, 2.0), bottom_full)
        centered_bottom = _subtract(_scale_interval(center, 2.0), top_full)
        top_full = _intersect(top_full, centered_top)
        bottom_full = _intersect(bottom_full, centered_bottom)
        if top_full is None or bottom_full is None:
            return None
    shift = top_full
    midpoint = _midpoint_interval(top_full, bottom_full)
    center_interval = _intersect(midpoint, center) if center is not None else midpoint
    return _Candidate(
        top=top,
        bottom=bottom,
        direct_pair=False,
        shared_support=0,
        continuous_support=binding.continuous_support_fraction,
        residual=binding.fit_residual_px,
        center_compatible=center_interval is not None,
        height_compatibility=height,
        canonical_height_px=canonical_height_px,
        shift_interval=shift,
        center_interval=center_interval,
        direction_interval=binding.full_direction_interval_degrees,
        direction_ready=True,
        support_trace_coordinates_px=binding.trace_coordinates_px,
        top_full_override=top_full,
        bottom_full_override=bottom_full,
    )


def _covers_template_domains(
    binding: CrossRoleBinding,
    domains: tuple[FiniteInterval, ...],
) -> bool:
    """Whether one role-authorized side is observed across every frame domain."""

    return bool(domains) and binding.role_authorized and all(
        any(domain.contains(float(trace), epsilon=0.5) for trace in binding.trace_coordinates_px)
        for domain in domains
    )


def _longitudinal_domain_count(
    traces: tuple[int, ...],
    domains: tuple[FiniteInterval, ...],
) -> int:
    return sum(
        any(domain.contains(float(trace), epsilon=0.5) for trace in traces)
        for domain in domains
    )


def _direction_for(
    direct: tuple[CrossRoleBinding, ...],
    *,
    parallel_interval: FiniteInterval | None = None,
) -> SharedStripDirection | None:
    if not direct or any(
        item.fit_direction_interval_degrees is None
        or item.full_direction_interval_degrees is None
        or item.canonical_direction_degrees is None
        for item in direct
    ):
        return None
    fit_intervals = tuple(item.fit_direction_interval_degrees for item in direct)
    full_intervals = tuple(item.full_direction_interval_degrees for item in direct)
    assert all(item is not None for item in fit_intervals)
    assert all(item is not None for item in full_intervals)
    common = parallel_interval
    if common is None:
        common = fit_intervals[0]
        assert common is not None
        for item in direct[1:]:
            interval = item.fit_direction_interval_degrees
            assert interval is not None
            common = _intersect(common, interval)
            if common is None:
                return None
    canonical_values = tuple(
        float(item.canonical_direction_degrees) for item in direct
    )
    identities = tuple(item.observation_id for item in direct)
    spanning_intervals = tuple(
        item.full_direction_interval_degrees
        for item in direct
        if item.source_spanning_continuous
    )
    safety_intervals = spanning_intervals or full_intervals
    safety = FiniteInterval(
        min(item.minimum for item in safety_intervals if item is not None),
        max(item.maximum for item in safety_intervals if item is not None),
    )
    common = _intersect(common, safety)
    if common is None:
        return None
    canonical = min(
        common.maximum,
        max(common.minimum, sum(canonical_values) / len(canonical_values)),
    )
    return SharedStripDirection(
        direction_id="template-cross-direction:" + ":".join(map(str, identities)),
        selected_observation_ids=identities,
        # The intersection above proves that one shared canonical direction
        # exists.  Safety must still retain the complete directly measured
        # source-spanning variation.  A local opposite fragment may validate H
        # and direction compatibility, but its local angle uncertainty cannot
        # be extrapolated over the complete source.  When both physical sides
        # span the domain, both intervals remain in the safety hull.
        full_angle_interval_degrees=safety,
        canonical_angle_degrees=canonical,
    )


def _fit_from_candidate(
    candidate: _Candidate,
    *,
    template: TemplateSpec,
    fixed_height: FiniteInterval,
    lane_reference_trace_px: float,
) -> CrossFit:
    top = candidate.top
    bottom = candidate.bottom
    if candidate.direct_pair:
        top_fit = top.fit_interval_px
        bottom_fit = bottom.fit_interval_px
        observed_center = _midpoint_interval(
            top.full_interval_px,
            bottom.full_interval_px,
        ).center
        top_canonical = observed_center - candidate.canonical_height_px / 2.0
        bottom_canonical = observed_center + candidate.canonical_height_px / 2.0
        top_full = _hull_intervals(
            (top.full_interval_px, FiniteInterval.exact(top_canonical))
        )
        bottom_full = _hull_intervals(
            (bottom.full_interval_px, FiniteInterval.exact(bottom_canonical))
        )
        direct = (top, bottom)
        inferred: tuple[CrossRoleBinding, ...] = ()
    elif top.role == BoundaryRole.TOP:
        inferred_height = candidate.height_compatibility
        top_full = candidate.top_full_override or top.full_interval_px
        bottom_full = (
            candidate.bottom_full_override
            if candidate.bottom_full_override is not None
            else _add(top.full_interval_px, inferred_height)
        )
        top_fit = _intersect(top.fit_interval_px, top_full) or FiniteInterval.exact(
            candidate.shift_interval.center
        )
        bottom_fit = _add(top.fit_interval_px, inferred_height)
        bottom_fit = _intersect(bottom_fit, bottom_full) or FiniteInterval.exact(
            candidate.shift_interval.center + candidate.height_compatibility.center
        )
        direct = (top,)
        inferred = (
            CrossRoleBinding(
                role=BoundaryRole.BOTTOM,
                run_id=f"inferred:{top.run_id}:bottom",
                observation_id=top.observation_id,
                coordinate_interval_px=_add(top.coordinate_interval_px, inferred_height),
                trace_coordinates_px=top.trace_coordinates_px,
                support_fraction=top.support_fraction,
                continuous_support_fraction=top.continuous_support_fraction,
                fit_residual_px=top.fit_residual_px,
                fit_interval_px=bottom_fit,
                full_interval_px=bottom_full,
                canonical_direction_degrees=top.canonical_direction_degrees,
                fit_direction_interval_degrees=(
                    top.fit_direction_interval_degrees
                ),
                full_direction_interval_degrees=top.full_direction_interval_degrees,
                evidence=CrossEvidence.FIXED_HEIGHT_INFERRED,
                source_observation_ids=(top.observation_id,),
                independent_support_region_count=top.independent_support_region_count,
                source_spanning_continuous=top.source_spanning_continuous,
                role_authorized=top.role_authorized,
            ),
        )
    else:
        inferred_height = candidate.height_compatibility
        bottom_full = (
            candidate.bottom_full_override
            if candidate.bottom_full_override is not None
            else bottom.full_interval_px
        )
        top_full = (
            candidate.top_full_override
            or _subtract(bottom.full_interval_px, inferred_height)
        )
        bottom_fit = _intersect(bottom.fit_interval_px, bottom_full) or FiniteInterval.exact(
            candidate.shift_interval.center + candidate.height_compatibility.center
        )
        top_fit = _subtract(bottom.fit_interval_px, inferred_height)
        top_fit = _intersect(top_fit, top_full) or FiniteInterval.exact(
            candidate.shift_interval.center
        )
        direct = (bottom,)
        inferred = (
            CrossRoleBinding(
                role=BoundaryRole.TOP,
                run_id=f"inferred:{bottom.run_id}:top",
                observation_id=bottom.observation_id,
                coordinate_interval_px=_subtract(bottom.coordinate_interval_px, inferred_height),
                trace_coordinates_px=bottom.trace_coordinates_px,
                support_fraction=bottom.support_fraction,
                continuous_support_fraction=bottom.continuous_support_fraction,
                fit_residual_px=bottom.fit_residual_px,
                fit_interval_px=top_fit,
                full_interval_px=top_full,
                canonical_direction_degrees=bottom.canonical_direction_degrees,
                fit_direction_interval_degrees=(
                    bottom.fit_direction_interval_degrees
                ),
                full_direction_interval_degrees=bottom.full_direction_interval_degrees,
                evidence=CrossEvidence.FIXED_HEIGHT_INFERRED,
                source_observation_ids=(bottom.observation_id,),
                independent_support_region_count=bottom.independent_support_region_count,
                source_spanning_continuous=bottom.source_spanning_continuous,
                role_authorized=bottom.role_authorized,
            ),
        )
    if not candidate.direct_pair:
        top_canonical = candidate.shift_interval.center
        bottom_canonical = top_canonical + candidate.canonical_height_px
    selected_direction = _direction_for(
        direct,
        parallel_interval=candidate.direction_interval,
    )
    return CrossFit(
        template_id=template.template_id,
        lane_reference_trace_px=lane_reference_trace_px,
        fixed_height_px=fixed_height,
        top_canonical_px=top_canonical,
        bottom_canonical_px=bottom_canonical,
        top_fit_interval_px=top_fit,
        bottom_fit_interval_px=bottom_fit,
        top_full_interval_px=top_full,
        bottom_full_interval_px=bottom_full,
        direct_bindings=direct,
        inferred_bindings=inferred,
        selected_direction=selected_direction,
        direct_pair=candidate.direct_pair,
        shared_trace_support_count=candidate.shared_support,
        continuous_support_fraction=candidate.continuous_support,
        residual_sum_px=candidate.residual,
        center_compatible=candidate.center_compatible,
        height_compatibility_px=candidate.height_compatibility,
        shift_interval_px=candidate.shift_interval,
        center_interval_px=candidate.center_interval,
        parallel_direction_interval_degrees=candidate.direction_interval,
        direction_provenance_ids=(selected_direction.selected_observation_ids if selected_direction is not None else ()),
        single_side_inferred=not candidate.direct_pair,
        independent_support_region_count=candidate.shared_support,
    )


def _close_intervals(
    left: FiniteInterval,
    right: FiniteInterval,
    *,
    tolerance: float,
) -> bool:
    if _intersect(left, right) is not None:
        return True
    if left.maximum < right.minimum:
        return right.minimum - left.maximum <= tolerance
    return left.minimum - right.maximum <= tolerance


def _same_physical_group(left: _Candidate, right: _Candidate) -> bool:
    if left.direct_pair != right.direct_pair:
        return False
    left_ids = {left.top.observation_id, left.bottom.observation_id}
    right_ids = {right.top.observation_id, right.bottom.observation_id}
    if left_ids.isdisjoint(right_ids):
        # Nearby local closures are still discrete answers unless the ledger
        # proves that they are connected through the same direct physical
        # anchor.  Spatial region coverage alone cannot create that missing
        # relationship.
        return False
    shift_tolerance = min(
        left.height_compatibility.center,
        right.height_compatibility.center,
    ) * _CONTINUOUS_SHIFT_RATIO
    if not _close_intervals(
        left.shift_interval,
        right.shift_interval,
        tolerance=shift_tolerance,
    ):
        return False
    height_tolerance = min(
        left.height_compatibility.center,
        right.height_compatibility.center,
    ) * _CONTINUOUS_HEIGHT_RATIO
    if not _close_intervals(
        left.height_compatibility,
        right.height_compatibility,
        tolerance=height_tolerance,
    ):
        return False
    if left.center_compatible != right.center_compatible:
        return False
    if left.center_interval is None or right.center_interval is None:
        if left.center_interval is not None or right.center_interval is not None:
            return False
    elif not _close_intervals(
        left.center_interval,
        right.center_interval,
        tolerance=shift_tolerance,
    ):
        return False
    if left.direction_interval is None or right.direction_interval is None:
        return left.direction_interval is None and right.direction_interval is None
    return _close_intervals(
        left.direction_interval,
        right.direction_interval,
        tolerance=_CONTINUOUS_DIRECTION_DEGREES,
    )


def _common_interval(
    intervals: Sequence[FiniteInterval],
) -> FiniteInterval | None:
    if not intervals:
        return None
    common = intervals[0]
    for interval in intervals[1:]:
        common = _intersect(common, interval)
        if common is None:
            return None
    return common


def _merge_group_interval(
    intervals: Sequence[FiniteInterval],
    *,
    tolerance: float,
) -> FiniteInterval | None:
    common = _common_interval(intervals)
    if common is not None:
        return common
    if not intervals:
        return None
    minimum = min(item.minimum for item in intervals)
    maximum = max(item.maximum for item in intervals)
    ordered = sorted(intervals, key=lambda item: item.minimum)
    if any(
        right.minimum - left.maximum > tolerance
        for left, right in zip(ordered, ordered[1:])
    ):
        return None
    return FiniteInterval(minimum, maximum)


def _group_candidates(candidates: Sequence[_Candidate]) -> tuple[tuple[_Candidate, ...], ...]:
    groups: list[list[_Candidate]] = []
    for candidate in sorted(
        candidates,
        key=lambda item: (
            item.shift_interval.center,
            str(item.top.observation_id),
            str(item.bottom.observation_id),
        ),
    ):
        for group in groups:
            heights = [item.height_compatibility for item in group] + [candidate.height_compatibility]
            directions = [
                item.direction_interval
                for item in group
                if item.direction_interval is not None
            ]
            if candidate.direction_interval is not None:
                directions.append(candidate.direction_interval)
            common_direction = (
                _merge_group_interval(
                    directions,
                    tolerance=_CONTINUOUS_DIRECTION_DEGREES,
                )
                if directions
                else None
            )
            direction_shape_matches = (
                all(item.direction_interval is None for item in group)
                and candidate.direction_interval is None
            ) or (
                all(item.direction_interval is not None for item in group)
                and candidate.direction_interval is not None
                and common_direction is not None
            )
            # A shared direct observation is one physical anchor, not another
            # vote.  Candidate pairs connected through that same top or bottom
            # role describe one closure network whose model uncertainty is
            # continuous.  Pairs with no shared identity remain discrete even
            # when their coordinates happen to be nearby.
            if any(
                _same_physical_group(item, candidate) for item in group
            ) and direction_shape_matches:
                group.append(candidate)
                break
        else:
            groups.append([candidate])
    return tuple(tuple(group) for group in groups)


def _group_direction(
    group: Sequence[_Candidate],
) -> SharedStripDirection | None:
    bindings: list[CrossRoleBinding] = []
    seen: set[ObservationId] = set()
    for candidate in group:
        direct = (candidate.top, candidate.bottom) if candidate.direct_pair else (candidate.top,)
        for binding in direct:
            if binding.observation_id in seen:
                continue
            seen.add(binding.observation_id)
            bindings.append(binding)
    if not bindings or any(
        item.fit_direction_interval_degrees is None
        or item.full_direction_interval_degrees is None
        or item.canonical_direction_degrees is None
        for item in bindings
    ):
        return None
    full_intervals = tuple(item.full_direction_interval_degrees for item in bindings)
    assert all(interval is not None for interval in full_intervals)
    common = _merge_group_interval(
        tuple(
            candidate.direction_interval
            for candidate in group
            if candidate.direction_interval is not None
        ),
        tolerance=_CONTINUOUS_DIRECTION_DEGREES,
    )
    if common is None:
        return None
    identities = tuple(item.observation_id for item in bindings)
    spanning_intervals = tuple(
        item.full_direction_interval_degrees
        for item in bindings
        if item.source_spanning_continuous
    )
    safety_intervals = spanning_intervals or full_intervals
    safety = FiniteInterval(
        min(interval.minimum for interval in safety_intervals),
        max(interval.maximum for interval in safety_intervals),
    )
    canonical_interval = _intersect(common, safety)
    if canonical_interval is None:
        return None
    canonical = min(
        canonical_interval.maximum,
        max(
            canonical_interval.minimum,
            sum(float(item.canonical_direction_degrees) for item in bindings)
            / len(bindings),
        ),
    )
    return SharedStripDirection(
        direction_id="template-cross-direction:" + ":".join(map(str, identities)),
        selected_observation_ids=identities,
        full_angle_interval_degrees=safety,
        canonical_angle_degrees=canonical,
    )


def _fit_from_group(
    group: Sequence[_Candidate],
    *,
    template: TemplateSpec,
    fixed_height: FiniteInterval,
    lane_reference_trace_px: float,
    registered_trace_coordinates_px: tuple[int, ...],
    longitudinal_support_domains_px: tuple[FiniteInterval, ...],
) -> CrossFit:
    """Collapse one continuous physical group without hulling alternatives."""

    def support_region_count(traces: tuple[int, ...]) -> int:
        count = independent_spatial_support_count(
            registered_trace_coordinates_px,
            traces,
        )
        count = max(count, support_domain_count(traces))
        return min(SPATIAL_SUPPORT_REGION_COUNT, count)

    def support_domain_count(traces: tuple[int, ...]) -> int:
        if not longitudinal_support_domains_px:
            return 0
        return min(
            SPATIAL_SUPPORT_REGION_COUNT,
            sum(
                any(
                    domain.contains(float(trace), epsilon=0.5)
                    for trace in traces
                )
                for domain in longitudinal_support_domains_px
            ),
        )

    def role_authorized_pair_domain_count(
        candidates: Sequence[_Candidate],
    ) -> int:
        return max(
            (
                support_domain_count(candidate.support_trace_coordinates_px)
                for candidate in candidates
                if candidate.direct_pair
                and candidate.top.role_authorized
                and candidate.bottom.role_authorized
            ),
            default=0,
        )

    role_authorized_group = tuple(
        candidate
        for candidate in group
        if candidate.direct_pair
        and candidate.top.role_authorized
        and candidate.bottom.role_authorized
        and support_domain_count(candidate.support_trace_coordinates_px)
        >= min(MINIMUM_INDEPENDENT_SUPPORT_REGIONS, template.count)
    )
    if role_authorized_group:
        group = role_authorized_group

    representative = _fit_from_candidate(
        group[0],
        template=template,
        fixed_height=fixed_height,
        lane_reference_trace_px=lane_reference_trace_px,
    )

    if len(group) == 1:
        candidate = group[0]
        direct = (
            (candidate.top, candidate.bottom)
            if candidate.direct_pair
            else (candidate.top,)
        )
        support_traces = tuple(sorted(set(candidate.support_trace_coordinates_px)))
        return replace(
            representative,
            shared_trace_support_count=len(support_traces),
            direct_provenance_ids=tuple(item.observation_id for item in direct),
            independent_support_region_count=support_region_count(
                support_traces
            ),
            longitudinal_support_domain_count=support_domain_count(
                support_traces
            ),
            role_authorized_pair_support_domain_count=(
                role_authorized_pair_domain_count((candidate,))
            ),
        )
    top_fit = _hull_intervals(
        tuple(
            (item.top_full_override or item.top.fit_interval_px)
            if not item.direct_pair
            else item.top.fit_interval_px
            for item in group
        )
    )
    bottom_fit = _hull_intervals(
        tuple(
            (item.bottom_full_override or item.bottom.fit_interval_px)
            if not item.direct_pair
            else item.bottom.fit_interval_px
            for item in group
        )
    )
    top_full = _hull_intervals(
        tuple(
            item.top_full_override or item.top.full_interval_px
            for item in group
        )
    )
    bottom_full = _hull_intervals(
        tuple(
            item.bottom_full_override or item.bottom.full_interval_px
            for item in group
        )
    )
    shift_tolerance = min(
        item.height_compatibility.center for item in group
    ) * _CONTINUOUS_SHIFT_RATIO
    shift = _hull_intervals(tuple(item.shift_interval for item in group))
    height_values = tuple(item.height_compatibility for item in group)
    height = _hull_intervals(height_values)
    centers = tuple(
        item.center_interval
        for item in group
        if item.center_interval is not None
    )
    center_interval = (
        _hull_intervals(centers)
        if centers
        else None
    )
    directions = tuple(
        item.direction_interval
        for item in group
        if item.direction_interval is not None
    )
    direction_interval = (
        _common_interval(directions)
        if directions
        else None
    )
    feasible_top = _common_interval(
        (
            shift,
            top_full,
            _subtract(bottom_full, height),
        )
    )
    if feasible_top is None:
        raise AssertionError("physical group has no canonical top closure")
    top_canonical = feasible_top.center
    feasible_height = _intersect(
        height,
        FiniteInterval(
            bottom_full.minimum - top_canonical,
            bottom_full.maximum - top_canonical,
        ),
    )
    if feasible_height is None:
        raise AssertionError("physical group has no canonical height closure")
    bottom_canonical = top_canonical + feasible_height.center
    direct_ids: list[ObservationId] = []
    seen: set[ObservationId] = set()
    for candidate in group:
        direct = (candidate.top, candidate.bottom) if candidate.direct_pair else (candidate.top,)
        for binding in direct:
            if binding.observation_id not in seen:
                seen.add(binding.observation_id)
                direct_ids.append(binding.observation_id)
    inferred = representative.inferred_bindings
    if inferred and direct_ids:
        inferred = tuple(
            replace(item, source_observation_ids=tuple(direct_ids))
            for item in inferred
        )
    selected_direction = _group_direction(group)
    support_traces = tuple(
        sorted(
            {
                trace
                for item in group
                for trace in item.support_trace_coordinates_px
            }
        )
    )
    independent_regions = support_region_count(support_traces)
    return replace(
        representative,
        top_canonical_px=top_canonical,
        bottom_canonical_px=bottom_canonical,
        top_fit_interval_px=top_fit,
        bottom_fit_interval_px=bottom_fit,
        top_full_interval_px=top_full,
        bottom_full_interval_px=bottom_full,
        inferred_bindings=inferred,
        selected_direction=selected_direction,
        shared_trace_support_count=len(support_traces),
        continuous_support_fraction=min(item.continuous_support for item in group),
        residual_sum_px=max(item.residual for item in group),
        center_compatible=all(item.center_compatible for item in group),
        height_compatibility_px=height,
        shift_interval_px=shift,
        center_interval_px=center_interval,
        parallel_direction_interval_degrees=direction_interval,
        direction_provenance_ids=(
            selected_direction.selected_observation_ids
            if selected_direction is not None
            else ()
        ),
        direct_provenance_ids=tuple(direct_ids),
        independent_support_region_count=independent_regions,
        longitudinal_support_domain_count=support_domain_count(support_traces),
        role_authorized_pair_support_domain_count=(
            role_authorized_pair_domain_count(group)
        ),
    )


def _hull_intervals(intervals: Sequence[FiniteInterval]) -> FiniteInterval:
    if not intervals:
        raise ValueError("cannot hull an empty interval set")
    return FiniteInterval(
        min(interval.minimum for interval in intervals),
        max(interval.maximum for interval in intervals),
    )


def _coerce_bindings(
    direct: Sequence[CrossRoleBinding],
    runs: Sequence[ProfileRun],
    observations: Sequence[PhotoBoundaryObservation],
    *,
    lane_reference_trace_px: float,
    boundary_axis: BoundaryAxis,
) -> tuple[CrossRoleBinding, ...]:
    values = list(direct)
    used: set[ObservationId] = {item.observation_id for item in values}
    if runs:
        for run in runs:
            if any(item.run_id == run.run_id for item in values):
                continue
            matches = tuple(
                observation
                for observation in observations
                if observation.observation_id not in used
                and (
                    observation.observation_id == ObservationId(run.run_id)
                    or set(map(str, run.transition_ids)).intersection(
                        map(str, observation.transition_ids)
                    )
                )
            )
            if not matches and len(observations) == 1:
                matches = observations
            if len(matches) != 1:
                continue
            observation = matches[0]
            values.append(
                CrossRoleBinding.from_measurement(
                    run,
                    observation,
                    lane_reference_trace_px=lane_reference_trace_px,
                    boundary_axis=boundary_axis,
                )
            )
            used.add(observation.observation_id)
    if observations and not runs:
        for observation in observations:
            if observation.observation_id in used:
                continue
            role = getattr(observation, "role", None)
            if role not in {BoundaryRole.TOP, BoundaryRole.BOTTOM}:
                continue
            canonical, direction = _observation_direction(observation)
            values.append(
                CrossRoleBinding(
                    role=role,
                    run_id=f"observation:{observation.observation_id}",
                    observation_id=observation.observation_id,
                    coordinate_interval_px=_observation_coordinate(
                        observation,
                        lane_reference_trace_px=lane_reference_trace_px,
                        boundary_axis=boundary_axis,
                    ),
                    fit_residual_px=float(observation.fit_residual_px),
                    canonical_direction_degrees=canonical,
                    fit_direction_interval_degrees=getattr(
                        observation,
                        "fit_angle_interval_degrees",
                        None,
                    ),
                    full_direction_interval_degrees=direction,
                    independent_support_region_count=int(
                        getattr(observation, "independent_support_region_count", 0)
                    ),
                    source_spanning_continuous=bool(
                        getattr(observation, "source_spanning_continuous", False)
                    ),
                    role_authorized=(
                        float(
                            getattr(
                                observation,
                                (
                                    "left_background_preference_fraction"
                                    if role == BoundaryRole.TOP
                                    else "right_background_preference_fraction"
                                ),
                                0.0,
                            )
                        )
                        > 0.5
                    ),
                )
            )
            used.add(observation.observation_id)
    by_identity: dict[ObservationId, CrossRoleBinding] = {}
    for item in values:
        if item.observation_id in by_identity:
            raise ValueError("cross observation registered more than once")
        by_identity[item.observation_id] = item
    return tuple(
        sorted(
            by_identity.values(),
            key=lambda item: (item.coordinate_interval_px.center, str(item.observation_id)),
        )
    )


def _receipt(
    *,
    inputs: TemplateCrossInput,
    registered_runs: int,
    fitted_observations: int,
    compatible_pairs: int,
    single_side_inferences: int,
    evaluated_fits: int,
) -> CrossSearchReceipt:
    return CrossSearchReceipt(
        registered_run_count=registered_runs,
        fitted_observation_count=fitted_observations,
        compatible_pair_count=compatible_pairs,
        single_side_inference_count=single_side_inferences,
        evaluated_fit_count=evaluated_fits,
        registered_run_bound=inputs.maximum_registered_runs,
        fitted_observation_bound=inputs.maximum_fitted_observations,
        compatible_pair_bound=inputs.maximum_compatible_pairs,
        evaluated_fit_bound=inputs.maximum_evaluated_fits,
    )


def fit_template_cross(inputs: TemplateCrossInput) -> CrossFitCompetition:
    """Fit one fixed-H short-axis template with bounded interval search."""

    if not isinstance(inputs, TemplateCrossInput):
        raise TypeError("fit_template_cross requires TemplateCrossInput")
    top = _coerce_bindings(
        inputs.top_bindings,
        inputs.top_runs,
        inputs.top_observations,
        lane_reference_trace_px=inputs.lane_reference_trace_px,
        boundary_axis=inputs.boundary_axis,
    )
    bottom = _coerce_bindings(
        inputs.bottom_bindings,
        inputs.bottom_runs,
        inputs.bottom_observations,
        lane_reference_trace_px=inputs.lane_reference_trace_px,
        boundary_axis=inputs.boundary_axis,
    )
    if any(item.role != BoundaryRole.TOP for item in top):
        raise ValueError("top registration contains a non-top role")
    if any(item.role != BoundaryRole.BOTTOM for item in bottom):
        raise ValueError("bottom registration contains a non-bottom role")
    all_ids = tuple(item.observation_id for item in (*top, *bottom))
    if len(set(all_ids)) != len(all_ids):
        raise ValueError("cross observation registered more than once")
    registered_run_ids = {
        *(run.run_id for run in inputs.top_runs),
        *(run.run_id for run in inputs.bottom_runs),
        *(item.run_id for item in top),
        *(item.run_id for item in bottom),
    }
    registered_runs = len(registered_run_ids)
    fitted_observations = len(all_ids)
    empty_receipt = lambda: _receipt(
        inputs=inputs,
        registered_runs=registered_runs,
        fitted_observations=fitted_observations,
        compatible_pairs=0,
        single_side_inferences=0,
        evaluated_fits=0,
    )
    if registered_runs > inputs.maximum_registered_runs or fitted_observations > inputs.maximum_fitted_observations:
        return CrossFitCompetition(
            template_id=inputs.template.template_id,
            best=None,
            runner_up=None,
            status=CrossFitStatus.BOUND_EXCEEDED,
            reason="cross registration bound exceeded",
            receipt=empty_receipt(),
        )
    if not top and not bottom:
        return CrossFitCompetition(
            template_id=inputs.template.template_id,
            best=None,
            runner_up=None,
            status=CrossFitStatus.UNRESOLVED,
            reason="cross fit requires top or bottom direct evidence",
            receipt=empty_receipt(),
        )
    fixed_height = inputs.fixed_height_px
    assert isinstance(fixed_height, FiniteInterval)
    registered_trace_coordinates = (
        inputs.registered_trace_coordinates_px
        or tuple(
            sorted(
                {
                    trace
                    for binding in (*top, *bottom)
                    for trace in binding.trace_coordinates_px
                }
            )
        )
    )
    required_support_regions = inputs.minimum_shared_trace_support

    direct_candidates: list[_Candidate] = []
    compatible_pairs = 0
    # Sorted starts plus prefix maxima enumerate every interval overlap.  No
    # nearest-neighbour or used-bottom shortcut may discard a valid answer.
    if top and bottom:
        ordered_top = tuple(sorted(top, key=lambda item: (item.full_interval_px.minimum, str(item.observation_id))))
        ordered_bottom = tuple(sorted(bottom, key=lambda item: (item.full_interval_px.minimum, str(item.observation_id))))
        starts = tuple(item.full_interval_px.minimum for item in ordered_bottom)
        prefix_max: list[float] = []
        running = -math.inf
        for item in ordered_bottom:
            running = max(running, item.full_interval_px.maximum)
            prefix_max.append(running)
        for top_item in ordered_top:
            expected = _add(top_item.full_interval_px, fixed_height)
            start_index = bisect_left(prefix_max, expected.minimum)
            index = start_index
            while index < len(ordered_bottom) and starts[index] <= expected.maximum:
                bottom_item = ordered_bottom[index]
                candidate = _direct_candidate(
                    top_item,
                    bottom_item,
                    fixed_height=fixed_height,
                    canonical_height_px=float(inputs.canonical_fixed_height_px),
                    center=inputs.holder_short_axis_center_px,
                    minimum_shared_trace_support=inputs.minimum_shared_trace_support,
                    parallel_direction_tolerance_degrees=(
                        inputs.parallel_direction_tolerance_degrees
                    ),
                )
                if candidate is not None:
                    compatible_pairs += 1
                    direct_candidates.append(candidate)
                    if compatible_pairs > inputs.maximum_compatible_pairs:
                        receipt = _receipt(
                            inputs=inputs,
                            registered_runs=registered_runs,
                            fitted_observations=fitted_observations,
                            compatible_pairs=compatible_pairs,
                            single_side_inferences=0,
                            evaluated_fits=0,
                        )
                        return CrossFitCompetition(
                            template_id=inputs.template.template_id,
                            best=None,
                            runner_up=None,
                            status=CrossFitStatus.BOUND_EXCEEDED,
                            reason="cross compatible-pair bound exceeded",
                            receipt=receipt,
                        )
                index += 1
    spanning_top = tuple(item for item in top if item.source_spanning_continuous)
    spanning_bottom = tuple(item for item in bottom if item.source_spanning_continuous)
    template_spanning_top = tuple(
        item
        for item in top
        if _covers_template_domains(
            item,
            inputs.longitudinal_support_domains_px,
        )
    )
    template_spanning_bottom = tuple(
        item
        for item in bottom
        if _covers_template_domains(
            item,
            inputs.longitudinal_support_domains_px,
        )
    )
    role_authorized_direct_pairs = tuple(
        candidate
        for candidate in direct_candidates
        if candidate.top.role_authorized
        and candidate.bottom.role_authorized
        and _longitudinal_domain_count(
            candidate.support_trace_coordinates_px,
            inputs.longitudinal_support_domains_px,
        )
        >= min(MINIMUM_INDEPENDENT_SUPPORT_REGIONS, inputs.template.count)
    )
    if spanning_top and spanning_bottom:
        # When both physical roles have source-spanning evidence, fragments do
        # not own either placement coordinate.  Only the two-sided spanning
        # closure may authorize a direct fixed-H placement.
        spanning_pairs = [
            item
            for item in direct_candidates
            if item.top.source_spanning_continuous
            and item.bottom.source_spanning_continuous
        ]
        candidates = spanning_pairs
    elif bool(spanning_top) != bool(spanning_bottom):
        # One domain-spanning role owns the cross coordinate.  A fragmented
        # opposite observation participates only when it directly closes H,
        # shared trace support, and direction with that anchor.  Otherwise
        # fixed H supplies the missing side.  Distinct direct closures remain
        # distinct answers and are never averaged.
        spanning = spanning_top or spanning_bottom
        spanning_ids = {item.observation_id for item in spanning}
        spanning_pairs = [
            candidate
            for candidate in direct_candidates
            if candidate.top.observation_id in spanning_ids
            or candidate.bottom.observation_id in spanning_ids
        ]
        candidates = spanning_pairs or [
            candidate
            for item in spanning
            if (candidate := _single_candidate(
                item,
                fixed_height=fixed_height,
                canonical_height_px=float(inputs.canonical_fixed_height_px),
                center=inputs.holder_short_axis_center_px,
            )) is not None
        ]
    elif role_authorized_direct_pairs:
        candidates = list(role_authorized_direct_pairs)
    elif template_spanning_top or template_spanning_bottom:
        # A role-authorized side observed inside every template frame domain
        # owns one source-wide side track even when it does not reach the raw
        # lane-domain endpoints.  Opposite local fragments can validate a
        # direct closure, but cannot create competing placements.  If both
        # roles cover the complete template, retain only their direct pairs;
        # otherwise fixed H infers the missing side.
        owner_ids = {
            item.observation_id
            for item in (*template_spanning_top, *template_spanning_bottom)
        }
        both_roles_span = bool(template_spanning_top and template_spanning_bottom)
        owner_pairs = [
            candidate
            for candidate in direct_candidates
            if candidate.top.observation_id in owner_ids
            and candidate.bottom.observation_id in owner_ids
        ]
        if both_roles_span and owner_pairs:
            candidates = owner_pairs
        else:
            candidates = [
                candidate
                for item in (*template_spanning_top, *template_spanning_bottom)
                if (candidate := _single_candidate(
                    item,
                    fixed_height=fixed_height,
                    canonical_height_px=float(inputs.canonical_fixed_height_px),
                    center=inputs.holder_short_axis_center_px,
                )) is not None
            ]
    elif inputs.holder_short_axis_center_px is not None:
        # With no domain-spanning coordinate, retain the finite local direct
        # closures as one network problem.  Only a unique compatible network
        # whose combined shared support covers front/middle/back can own H and
        # cross position.  No individual fragment receives placement authority.
        if direct_candidates:
            candidates = list(direct_candidates)
            required_support_regions = SPATIAL_SUPPORT_REGION_COUNT
        else:
            candidates = [
                candidate
                for item in (*top, *bottom)
                if (candidate := _single_candidate(
                    item,
                    fixed_height=fixed_height,
                    canonical_height_px=float(inputs.canonical_fixed_height_px),
                    center=inputs.holder_short_axis_center_px,
                )) is not None
            ]
    elif direct_candidates:
        candidates = list(direct_candidates)
    elif not top or not bottom:
        one_sided = top if top else bottom
        candidates = [
            candidate
            for item in one_sided
            if (candidate := _single_candidate(
                item,
                fixed_height=fixed_height,
                canonical_height_px=float(inputs.canonical_fixed_height_px),
                center=inputs.holder_short_axis_center_px,
            ))
            is not None
        ]
    single_count = sum(not item.direct_pair for item in candidates)
    receipt = _receipt(
        inputs=inputs,
        registered_runs=registered_runs,
        fitted_observations=fitted_observations,
        compatible_pairs=compatible_pairs,
        single_side_inferences=single_count,
        evaluated_fits=len(candidates),
    )
    if len(candidates) > inputs.maximum_evaluated_fits:
        return CrossFitCompetition(
            template_id=inputs.template.template_id,
            best=None,
            runner_up=None,
            status=CrossFitStatus.BOUND_EXCEEDED,
            reason="cross evaluated-fit bound exceeded",
            receipt=receipt,
        )
    receipt.validate_bounds()
    if not candidates:
        reason = (
            "direct top/bottom evidence contradicts fixed height"
            if top and bottom
            else "single-side evidence lacks independent support or direction"
        )
        return CrossFitCompetition(
            template_id=inputs.template.template_id,
            best=None,
            runner_up=None,
            status=CrossFitStatus.UNRESOLVED,
            reason=reason,
            receipt=receipt,
        )

    # Holder center is a hard closure.  If a direct candidate exists but all
    # are off-center, do not let support or residual clutter replace it.
    if inputs.holder_short_axis_center_px is not None:
        centered = tuple(item for item in candidates if item.center_compatible)
        if centered:
            candidates = list(centered)
        else:
            fits = tuple(
                _fit_from_candidate(
                    item,
                    template=inputs.template,
                    fixed_height=fixed_height,
                    lane_reference_trace_px=inputs.lane_reference_trace_px,
                )
                for item in candidates
            )
            return CrossFitCompetition(
                template_id=inputs.template.template_id,
                best=None,
                runner_up=fits[0] if fits else None,
                status=CrossFitStatus.UNRESOLVED,
                reason="cross holder center contradicts direct evidence",
                receipt=receipt,
            )

    # Direction is never inferred from the template.  A complete directional
    # candidate wins over a candidate whose direction interval is unavailable;
    # if none is complete, retain evidence but refuse resolution.
    ready = tuple(item for item in candidates if item.direction_ready)
    if ready:
        candidates = list(ready)

    direct_candidates_for_selection = tuple(item for item in candidates if item.direct_pair)
    if direct_candidates_for_selection:
        candidates = list(direct_candidates_for_selection)
    groups = _group_candidates(candidates)
    representative_fits = tuple(
        _fit_from_group(
            group,
            template=inputs.template,
            fixed_height=fixed_height,
            lane_reference_trace_px=inputs.lane_reference_trace_px,
            registered_trace_coordinates_px=registered_trace_coordinates,
            longitudinal_support_domains_px=(
                inputs.longitudinal_support_domains_px
            ),
        )
        for group in groups
    )
    def has_role_authorized_pair(item: CrossFit) -> bool:
        return (
            item.direct_pair
            and item.role_authorized_pair_support_domain_count
            >= min(MINIMUM_INDEPENDENT_SUPPORT_REGIONS, inputs.template.count)
        )

    def has_source_spanning_direct_side(item: CrossFit) -> bool:
        return item.direct_pair and any(
            binding.source_spanning_continuous
            for binding in item.direct_bindings
        )

    authoritative = tuple(
        item
        for item in representative_fits
        if (
            has_role_authorized_pair(item)
            or has_source_spanning_direct_side(item)
            or (
                not item.direct_pair
                and item.independent_support_region_count
                >= required_support_regions
            )
        )
    )
    ordered_fits = authoritative or representative_fits
    best = ordered_fits[0] if ordered_fits else None
    runner = ordered_fits[1] if len(ordered_fits) > 1 else None
    if best is None:
        return CrossFitCompetition(
            template_id=inputs.template.template_id,
            best=None,
            runner_up=None,
            status=CrossFitStatus.UNRESOLVED,
            reason="cross fit has no physical group",
            receipt=receipt,
        )
    if len(authoritative) > 1 or (not authoritative and len(groups) > 1):
        return CrossFitCompetition(
            template_id=inputs.template.template_id,
            best=best,
            runner_up=runner,
            status=CrossFitStatus.UNRESOLVED,
            reason="non-equivalent cross fits remain",
            receipt=receipt,
        )
    if not authoritative:
        return CrossFitCompetition(
            template_id=inputs.template.template_id,
            best=best,
            runner_up=runner,
            status=CrossFitStatus.UNRESOLVED,
            reason="cross fit lacks independent spatial support",
            receipt=receipt,
        )
    if best.selected_direction is None:
        return CrossFitCompetition(
            template_id=inputs.template.template_id,
            best=best,
            runner_up=runner,
            status=CrossFitStatus.UNRESOLVED,
            reason="cross direction unavailable",
            receipt=receipt,
        )
    return CrossFitCompetition(
        template_id=inputs.template.template_id,
        best=best,
        runner_up=runner,
        status=CrossFitStatus.RESOLVED,
        reason=None,
        receipt=receipt,
    )


__all__ = [
    "CrossEvidence",
    "CrossFit",
    "CrossFitCompetition",
    "CrossFitStatus",
    "CrossRoleBinding",
    "CrossSearchReceipt",
    "TemplateCrossInput",
    "fit_template_cross",
]
