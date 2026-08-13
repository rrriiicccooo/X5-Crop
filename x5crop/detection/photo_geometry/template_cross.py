"""Fixed-height short-axis template fitting.

This module owns the small, candidate-independent pass that turns registered
top/bottom cross observations into one short-axis fit.  The height is a
physical template fact: observations can support it or veto it, but they do
not recalibrate it.  A direct pair is preferred over one-sided inference and
only one best/runner-up pair is retained.

The public types intentionally contain no chain, placement, or materialized
candidate objects.  Callers may provide already fitted ``CrossRoleBinding``
values, or use :meth:`CrossRoleBinding.from_measurement` for one registered
profile run and one fitted boundary observation.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from enum import Enum
import math
from typing import Sequence

from ...domain import FiniteInterval, ObservationId, PositiveInterval
from .line_observations import PhotoBoundaryObservation
from .model import BoundaryAxis, BoundaryRole, independent_spatial_support_count
from .observation_types import ProfileRun
from .output_model import SharedStripDirection
from .template_model import TemplateSpec


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


def _distance(left: FiniteInterval, right: FiniteInterval) -> float:
    if left.maximum < right.minimum:
        return right.minimum - left.maximum
    if right.maximum < left.minimum:
        return left.minimum - right.maximum
    return 0.0


def _hull(left: FiniteInterval, right: FiniteInterval) -> FiniteInterval:
    return FiniteInterval(
        min(left.minimum, right.minimum),
        max(left.maximum, right.maximum),
    )


def _observation_coordinate(
    observation: object,
    *,
    lane_reference_trace_px: float,
    boundary_axis: BoundaryAxis,
) -> FiniteInterval:
    """Project a fitted line once, without importing a proposal owner."""

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
    """Role ledger provenance for one short-axis edge."""

    DIRECT = "direct"
    FIXED_HEIGHT_INFERRED = "fixed_height_inferred"


@dataclass(frozen=True)
class CrossRoleBinding:
    """One registered top/bottom role measured at the lane reference.

    ``fit_interval_px`` and ``full_interval_px`` separate the robust fit from
    the complete physical safety interval.  When omitted they use the
    measured coordinate interval.  Inferred bindings retain the source
    observation IDs in ``source_observation_ids``; the synthetic identity is
    never used as direction authority.
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
    full_direction_interval_degrees: FiniteInterval | None = None
    evidence: CrossEvidence = CrossEvidence.DIRECT
    source_observation_ids: tuple[ObservationId, ...] = ()

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
        if self.canonical_direction_degrees is not None:
            if self.full_direction_interval_degrees is None:
                raise ValueError("cross canonical direction needs full interval")
            if not self.full_direction_interval_degrees.contains(
                float(self.canonical_direction_degrees), epsilon=1.0e-9
            ):
                raise ValueError("cross canonical direction is outside full interval")
        if self.full_direction_interval_degrees is not None and not isinstance(
            self.full_direction_interval_degrees, FiniteInterval
        ):
            raise TypeError("cross full direction interval must be FiniteInterval")

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
        full = coordinate
        line = getattr(observation, "line", None)
        offset = getattr(observation, "offset_interval_px", None)
        if line is not None and isinstance(offset, FiniteInterval):
            # The line offset interval is the complete physical uncertainty
            # at the reference trace.  Keep the coordinate fit interval
            # narrower only when a fitted interval is exposed by the owner.
            full = coordinate
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
            full_interval_px=full,
            canonical_direction_degrees=canonical,
            full_direction_interval_degrees=direction,
        )


@dataclass(frozen=True)
class TemplateCrossInput:
    """Inputs for one fixed-height short-axis fit.

    ``top_bindings``/``bottom_bindings`` are the preferred registration
    boundary.  ``top_runs`` and ``bottom_runs`` plus fitted observation sets
    are accepted as a convenience and are converted once by
    :func:`fit_template_cross`.
    """

    template: TemplateSpec
    fixed_height_px: FiniteInterval | PositiveInterval | float | None = None
    holder_short_axis_center_px: FiniteInterval | float | None = None
    lane_reference_trace_px: float = 0.0
    top_bindings: tuple[CrossRoleBinding, ...] = ()
    bottom_bindings: tuple[CrossRoleBinding, ...] = ()
    top_runs: tuple[ProfileRun, ...] = ()
    bottom_runs: tuple[ProfileRun, ...] = ()
    top_observations: tuple[PhotoBoundaryObservation, ...] = ()
    bottom_observations: tuple[PhotoBoundaryObservation, ...] = ()
    boundary_axis: BoundaryAxis = BoundaryAxis.Y
    maximum_registered_runs: int = 256
    maximum_fitted_observations: int = 256
    maximum_compatible_pairs: int = 256
    maximum_evaluated_fits: int = 512
    minimum_shared_trace_support: int = 2

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
        if self.template.frame_height_px is not None:
            template_height = _interval(self.template.frame_height_px)
            if _intersect(height, template_height) is None:
                raise ValueError("fixed height contradicts template frame height")
        if self.holder_short_axis_center_px is not None:
            object.__setattr__(
                self,
                "holder_short_axis_center_px",
                _interval(self.holder_short_axis_center_px),
            )
        if not math.isfinite(float(self.lane_reference_trace_px)):
            raise ValueError("lane reference trace must be finite")
        if self.boundary_axis not in {BoundaryAxis.X, BoundaryAxis.Y}:
            raise ValueError("cross boundary axis is invalid")
        bounds = (
            self.maximum_registered_runs,
            self.maximum_fitted_observations,
            self.maximum_compatible_pairs,
            self.maximum_evaluated_fits,
        )
        if any(not isinstance(value, int) or value <= 0 for value in bounds):
            raise ValueError("cross work bounds must be positive integers")
        if self.minimum_shared_trace_support < 0:
            raise ValueError("cross shared-support minimum cannot be negative")


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
    """One selected short-axis fit with direct/inferred role provenance."""

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

    def __post_init__(self) -> None:
        if not self.template_id or not self.fixed_height_px.contains(
            self.bottom_canonical_px - self.top_canonical_px,
            epsilon=max(self.fixed_height_px.width, 1.0),
        ) and self.direct_pair:
            raise ValueError("direct cross fit does not preserve fixed height")
        if not self.top_full_interval_px.contains(
            self.top_canonical_px, epsilon=1.0e-9
        ) or not self.bottom_full_interval_px.contains(
            self.bottom_canonical_px, epsilon=1.0e-9
        ):
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
        if not 0.0 <= self.continuous_support_fraction <= 1.0:
            raise ValueError("cross continuous support is invalid")
        if not math.isfinite(self.residual_sum_px) or self.residual_sum_px < 0.0:
            raise ValueError("cross residual is invalid")

    @property
    def direct_observation_ids(self) -> tuple[ObservationId, ...]:
        return tuple(item.observation_id for item in self.direct_bindings)

    @property
    def inferred_observation_ids(self) -> tuple[ObservationId, ...]:
        return tuple(
            identity
            for item in self.inferred_bindings
            for identity in item.source_observation_ids
        )

    @property
    def role_ledger(self) -> tuple[CrossRoleBinding, ...]:
        return self.direct_bindings + self.inferred_bindings


@dataclass(frozen=True)
class CrossFitCompetition:
    """Best/runner-up decision; only a clearly separated best is authority."""

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


def _shared_trace_support(top: CrossRoleBinding, bottom: CrossRoleBinding) -> int:
    if not top.trace_coordinates_px or not bottom.trace_coordinates_px:
        return 0
    queried = tuple(
        sorted(set(top.trace_coordinates_px) | set(bottom.trace_coordinates_px))
    )
    common = tuple(
        sorted(set(top.trace_coordinates_px).intersection(bottom.trace_coordinates_px))
    )
    if common:
        return independent_spatial_support_count(queried, common)
    # The registered top and bottom corridors may use staggered trace
    # lattices.  Two independently spanning lines still co-support fixed H;
    # exact pixel-coordinate equality is not a physical requirement.
    return min(
        independent_spatial_support_count(queried, top.trace_coordinates_px),
        independent_spatial_support_count(queried, bottom.trace_coordinates_px),
    )


def _center_compatible(
    top: FiniteInterval,
    bottom: FiniteInterval,
    center: FiniteInterval | None,
) -> bool:
    if center is None:
        return True
    midpoint = FiniteInterval(
        (top.minimum + bottom.minimum) / 2.0,
        (top.maximum + bottom.maximum) / 2.0,
    )
    return _intersect(midpoint, center) is not None


def _direction_for(
    direct: tuple[CrossRoleBinding, ...],
) -> SharedStripDirection | None:
    values = tuple(
        item
        for item in direct
        if item.full_direction_interval_degrees is not None
    )
    if not values:
        return None
    common = values[0].full_direction_interval_degrees
    assert common is not None
    for item in values[1:]:
        interval = item.full_direction_interval_degrees
        assert interval is not None
        common = _intersect(common, interval)
        if common is None:
            return None
    canonical_values = tuple(
        float(item.canonical_direction_degrees)
        for item in values
        if item.canonical_direction_degrees is not None
    )
    canonical = (
        sum(canonical_values) / len(canonical_values)
        if canonical_values
        else common.center
    )
    canonical = min(common.maximum, max(common.minimum, canonical))
    identities = tuple(sorted((item.observation_id for item in values), key=str))
    direction_id = "template-cross-direction:" + ":".join(map(str, identities))
    return SharedStripDirection(
        direction_id=direction_id,
        selected_observation_ids=identities,
        full_angle_interval_degrees=common,
        canonical_angle_degrees=canonical,
    )


def _fit_from_candidate(
    candidate: _Candidate,
    *,
    template: TemplateSpec,
    fixed_height: FiniteInterval,
    lane_reference_trace_px: float,
    center: FiniteInterval | None,
) -> CrossFit:
    top = candidate.top
    bottom = candidate.bottom
    if candidate.direct_pair:
        top_fit = top.fit_interval_px
        bottom_fit = bottom.fit_interval_px
        top_full = top.full_interval_px
        bottom_full = bottom.full_interval_px
        direct = (top, bottom)
        inferred: tuple[CrossRoleBinding, ...] = ()
    elif top.role == BoundaryRole.TOP:
        top_fit = top.fit_interval_px
        bottom_fit = _add(top.fit_interval_px, fixed_height)
        top_full = top.full_interval_px
        bottom_full = _add(top.full_interval_px, fixed_height)
        inferred = (
            CrossRoleBinding(
                role=BoundaryRole.BOTTOM,
                run_id=f"inferred:{top.run_id}:bottom",
                observation_id=top.observation_id,
                coordinate_interval_px=_add(top.coordinate_interval_px, fixed_height),
                trace_coordinates_px=top.trace_coordinates_px,
                support_fraction=top.support_fraction,
                continuous_support_fraction=top.continuous_support_fraction,
                fit_residual_px=top.fit_residual_px,
                fit_interval_px=bottom_fit,
                full_interval_px=bottom_full,
                evidence=CrossEvidence.FIXED_HEIGHT_INFERRED,
                source_observation_ids=(top.observation_id,),
            ),
        )
        direct = (top,)
    else:
        bottom_fit = bottom.fit_interval_px
        top_fit = _subtract(bottom.fit_interval_px, fixed_height)
        bottom_full = bottom.full_interval_px
        top_full = _subtract(bottom.full_interval_px, fixed_height)
        inferred = (
            CrossRoleBinding(
                role=BoundaryRole.TOP,
                run_id=f"inferred:{bottom.run_id}:top",
                observation_id=bottom.observation_id,
                coordinate_interval_px=_subtract(bottom.coordinate_interval_px, fixed_height),
                trace_coordinates_px=bottom.trace_coordinates_px,
                support_fraction=bottom.support_fraction,
                continuous_support_fraction=bottom.continuous_support_fraction,
                fit_residual_px=bottom.fit_residual_px,
                fit_interval_px=top_fit,
                full_interval_px=top_full,
                evidence=CrossEvidence.FIXED_HEIGHT_INFERRED,
                source_observation_ids=(bottom.observation_id,),
            ),
        )
        direct = (bottom,)
    top_canonical = top.coordinate_interval_px.center
    bottom_canonical = bottom.coordinate_interval_px.center
    if not candidate.direct_pair:
        if top.role == BoundaryRole.TOP:
            bottom_canonical = top_canonical + fixed_height.center
        else:
            top_canonical = bottom_canonical - fixed_height.center
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
        selected_direction=_direction_for(direct),
        direct_pair=candidate.direct_pair,
        shared_trace_support_count=candidate.shared_support,
        continuous_support_fraction=candidate.continuous_support,
        residual_sum_px=candidate.residual,
        center_compatible=candidate.center_compatible,
    )


def _candidate_key(candidate: _Candidate) -> tuple[int, int, int, float, float, tuple[str, str]]:
    # This is an evidence ordering, not a scalar confidence score.  Direct
    # pair and the holder-centred short-axis fact precede observation quality.
    return (
        int(candidate.direct_pair),
        int(candidate.center_compatible),
        candidate.shared_support,
        candidate.continuous_support,
        -candidate.residual,
        (str(candidate.top.observation_id), str(candidate.bottom.observation_id)),
    )


def _sampling_equivalent(left: CrossFit, right: CrossFit) -> bool:
    tolerance = max(
        2.0,
        min(left.fixed_height_px.center, right.fixed_height_px.center) * 0.03,
    )
    return max(
        abs(left.top_canonical_px - right.top_canonical_px),
        abs(left.bottom_canonical_px - right.bottom_canonical_px),
    ) <= tolerance


def _coerce_bindings(
    direct: Sequence[CrossRoleBinding],
    runs: Sequence[ProfileRun],
    observations: Sequence[PhotoBoundaryObservation],
    *,
    lane_reference_trace_px: float,
    boundary_axis: BoundaryAxis,
) -> tuple[CrossRoleBinding, ...]:
    values = list(direct)
    if runs:
        used: set[ObservationId] = {item.observation_id for item in values}
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
    # A pre-fitted observation without a ProfileRun is still direct evidence;
    # retain it once and use its role field.
    if observations and not runs:
        used = {item.observation_id for item in values}
        for observation in observations:
            if observation.observation_id in used:
                continue
            role = getattr(observation, "role", None)
            if role not in {BoundaryRole.TOP, BoundaryRole.BOTTOM}:
                continue
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
                    canonical_direction_degrees=_observation_direction(observation)[0],
                    full_direction_interval_degrees=_observation_direction(observation)[1],
                )
            )
    by_identity: dict[ObservationId, CrossRoleBinding] = {}
    for item in values:
        if item.observation_id in by_identity:
            raise ValueError("cross observation registered more than once")
        by_identity[item.observation_id] = item
    return tuple(sorted(by_identity.values(), key=lambda item: (item.coordinate_interval_px.center, str(item.observation_id))))


def fit_template_cross(
    inputs: TemplateCrossInput,
) -> CrossFitCompetition:
    """Fit one fixed-H short-axis template in bounded indexed work."""

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
    registered_run_ids = {
        *(run.run_id for run in inputs.top_runs),
        *(run.run_id for run in inputs.bottom_runs),
        *(item.run_id for item in top),
        *(item.run_id for item in bottom),
    }
    registered_runs = len(registered_run_ids)
    fitted_observations = len(top) + len(bottom)
    all_observation_ids = tuple(item.observation_id for item in (*top, *bottom))
    if len(set(all_observation_ids)) != len(all_observation_ids):
        raise ValueError("cross observation registered more than once")
    receipt_base = dict(
        registered_run_count=registered_runs,
        fitted_observation_count=fitted_observations,
        compatible_pair_count=0,
        single_side_inference_count=0,
        evaluated_fit_count=0,
        registered_run_bound=inputs.maximum_registered_runs,
        fitted_observation_bound=inputs.maximum_fitted_observations,
        compatible_pair_bound=inputs.maximum_compatible_pairs,
        evaluated_fit_bound=inputs.maximum_evaluated_fits,
    )
    if registered_runs > inputs.maximum_registered_runs or fitted_observations > inputs.maximum_fitted_observations:
        receipt = CrossSearchReceipt(**receipt_base)
        return CrossFitCompetition(
            template_id=inputs.template.template_id,
            best=None,
            runner_up=None,
            status=CrossFitStatus.BOUND_EXCEEDED,
            reason="cross registration bound exceeded",
            receipt=receipt,
        )
    if not top and not bottom:
        receipt = CrossSearchReceipt(**receipt_base)
        return CrossFitCompetition(
            template_id=inputs.template.template_id,
            best=None,
            runner_up=None,
            status=CrossFitStatus.UNRESOLVED,
            reason="cross fit requires top or bottom direct evidence",
            receipt=receipt,
        )

    fixed_height = inputs.fixed_height_px
    assert isinstance(fixed_height, FiniteInterval)
    candidates: list[_Candidate] = []
    compatible_pairs = 0
    used_bottom: set[ObservationId] = set()
    # A coordinate index emits at most one direct pair per top observation.
    # Looking at the insertion point and its two immediate neighbours keeps
    # pairing bounded without materializing a top×bottom product.
    bottom_index = tuple(sorted(bottom, key=lambda item: item.coordinate_interval_px.center))
    bottom_centers = tuple(item.coordinate_interval_px.center for item in bottom_index)
    for top_item in top:
        expected = _add(top_item.coordinate_interval_px, fixed_height)
        insertion = bisect_left(bottom_centers, expected.center)
        nearby_indices = tuple(
            index
            for index in (insertion - 2, insertion - 1, insertion, insertion + 1)
            if 0 <= index < len(bottom_index)
        )
        options = tuple(
            item
            for index in nearby_indices
            for item in (bottom_index[index],)
            if item.observation_id not in used_bottom
            and _intersect(item.coordinate_interval_px, expected) is not None
            and _shared_trace_support(top_item, item) >= inputs.minimum_shared_trace_support
            and (
                top_item.full_direction_interval_degrees is None
                or item.full_direction_interval_degrees is None
                or _intersect(
                    top_item.full_direction_interval_degrees,
                    item.full_direction_interval_degrees,
                )
                is not None
            )
        )
        if not options:
            continue
        chosen = min(
            options,
            key=lambda item: (
                _distance(item.coordinate_interval_px, expected),
                -_shared_trace_support(top_item, item),
                str(item.observation_id),
            ),
        )
        used_bottom.add(chosen.observation_id)
        compatible_pairs += 1
        shared = _shared_trace_support(top_item, chosen)
        candidates.append(
            _Candidate(
                top=top_item,
                bottom=chosen,
                direct_pair=True,
                shared_support=shared,
                continuous_support=min(
                    top_item.continuous_support_fraction,
                    chosen.continuous_support_fraction,
                ),
                residual=top_item.fit_residual_px + chosen.fit_residual_px,
                center_compatible=_center_compatible(
                    top_item.coordinate_interval_px,
                    chosen.coordinate_interval_px,
                    inputs.holder_short_axis_center_px,
                ),
            )
        )
        if compatible_pairs > inputs.maximum_compatible_pairs:
            break
    receipt_base["compatible_pair_count"] = compatible_pairs
    if compatible_pairs > inputs.maximum_compatible_pairs:
        receipt = CrossSearchReceipt(**receipt_base)
        return CrossFitCompetition(
            template_id=inputs.template.template_id,
            best=None,
            runner_up=None,
            status=CrossFitStatus.BOUND_EXCEEDED,
            reason="cross compatible-pair bound exceeded",
            receipt=receipt,
        )

    # Contradictory two-sided observations veto one-sided inference.  A
    # one-sided candidate is legal only when the opposite registered role is
    # genuinely absent, never when an observed opposite edge disagrees with H.
    if not candidates and (not top or not bottom):
        one_sided = top if top else bottom
        for item in one_sided:
            candidates.append(
                _Candidate(
                    top=item,
                    bottom=item,
                    direct_pair=False,
                    shared_support=len(item.trace_coordinates_px),
                    continuous_support=item.continuous_support_fraction,
                    residual=item.fit_residual_px,
                    center_compatible=_center_compatible(
                        _add(item.coordinate_interval_px, fixed_height)
                        if item.role == BoundaryRole.TOP
                        else _subtract(item.coordinate_interval_px, fixed_height),
                        item.coordinate_interval_px,
                        inputs.holder_short_axis_center_px,
                    ),
                )
            )
    receipt_base["single_side_inference_count"] = sum(
        not item.direct_pair for item in candidates
    )
    receipt_base["evaluated_fit_count"] = len(candidates)
    receipt = CrossSearchReceipt(**receipt_base)
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
        return CrossFitCompetition(
            template_id=inputs.template.template_id,
            best=None,
            runner_up=None,
            status=CrossFitStatus.UNRESOLVED,
            reason="direct top/bottom evidence contradicts fixed height",
            receipt=receipt,
        )
    ranked = sorted(candidates, key=_candidate_key, reverse=True)
    best_candidate = ranked[0]
    runner_candidate = ranked[1] if len(ranked) > 1 else None
    best = _fit_from_candidate(
        best_candidate,
        template=inputs.template,
        fixed_height=fixed_height,
        lane_reference_trace_px=inputs.lane_reference_trace_px,
        center=inputs.holder_short_axis_center_px,
    )
    runner = (
        _fit_from_candidate(
            runner_candidate,
            template=inputs.template,
            fixed_height=fixed_height,
            lane_reference_trace_px=inputs.lane_reference_trace_px,
            center=inputs.holder_short_axis_center_px,
        )
        if runner_candidate is not None
        else None
    )
    if runner is None or _sampling_equivalent(best, runner):
        status = CrossFitStatus.RESOLVED
        reason = None
    else:
        # Explicit lexicographic equality is unresolved.  A one-region
        # advantage, a material direct-support advantage, or a residual
        # separation larger than one pixel is clear; otherwise retain the
        # runner-up and refuse placement authority.
        key_best = _candidate_key(best_candidate)
        key_runner = _candidate_key(runner_candidate)
        clearly_separated = (
            key_best[0] > key_runner[0]
            or key_best[1] > key_runner[1]
            or key_best[2] > key_runner[2]
            or key_best[3] >= key_runner[3] + 0.05
            or key_best[4] > key_runner[4] + 1.0
        )
        status = CrossFitStatus.RESOLVED if clearly_separated else CrossFitStatus.UNRESOLVED
        reason = None if status == CrossFitStatus.RESOLVED else "runner-up is not clearly separated"
    return CrossFitCompetition(
        template_id=inputs.template.template_id,
        best=best,
        runner_up=runner,
        status=status,
        reason=reason,
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
