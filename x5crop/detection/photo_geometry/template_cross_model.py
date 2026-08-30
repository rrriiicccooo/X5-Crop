"""Canonical records for fixed-height short-axis template fitting."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math

from ...domain import FiniteInterval, ObservationId, PositiveInterval
from ...formats import OUTPUT_PROTECTION_SPEC
from .line_observations import PhotoBoundaryObservation
from .interval_math import intersect, subtract
from .model import (
    BoundaryAxis,
    BoundaryRole,
)
from .observation_types import ProfileRun
from .output_model import OutputBoundaryUse, SharedStripDirection
from .template_aspect_ratio_model import (
    ApertureAspectRatioAuthority,
    unavailable_aperture_aspect_ratio_authority,
)
from .template_model import TemplateSpec

def _interval(value: FiniteInterval | PositiveInterval | float | int) -> FiniteInterval:
    if isinstance(value, FiniteInterval):
        return value
    if isinstance(value, PositiveInterval):
        return FiniteInterval(value.minimum, value.maximum)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return FiniteInterval.exact(float(value))
    raise TypeError("cross interval must be finite interval or number")


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
    TEMPLATE_LOCAL_REFINEMENT = "template_local_refinement"
    ASPECT_RATIO_HEIGHT_INFERRED = "aspect_ratio_height_inferred"


@dataclass(frozen=True)
class EnclosingSupportPair:
    """Direct, larger support envelope kept outside the fixed-H aperture."""

    top_canonical_px: float
    bottom_canonical_px: float
    top_full_interval_px: FiniteInterval
    bottom_full_interval_px: FiniteInterval
    top_provenance_ids: tuple[ObservationId, ...]
    bottom_provenance_ids: tuple[ObservationId, ...]
    observed_span_px: FiniteInterval
    reference_trace_px: float
    trace_coordinates_px: tuple[int, ...]
    top_trace_intervals_px: tuple[FiniteInterval, ...]
    bottom_trace_intervals_px: tuple[FiniteInterval, ...]
    top_straight_model_residual_px: float = 0.0
    bottom_straight_model_residual_px: float = 0.0

    def __post_init__(self) -> None:
        if not all(
            math.isfinite(float(value))
            for value in (
                self.top_canonical_px,
                self.bottom_canonical_px,
                self.reference_trace_px,
            )
        ):
            raise ValueError("support boundary canonical positions must be finite")
        if self.bottom_canonical_px <= self.top_canonical_px:
            raise ValueError("support boundary order is invalid")
        if not isinstance(self.top_full_interval_px, FiniteInterval) or not isinstance(
            self.bottom_full_interval_px, FiniteInterval
        ):
            raise TypeError("support boundary intervals must be FiniteInterval")
        if not isinstance(self.observed_span_px, FiniteInterval):
            raise TypeError("support observed span must be FiniteInterval")
        if not self.top_full_interval_px.contains(self.top_canonical_px, epsilon=1.0e-9):
            raise ValueError("support top leaves its direct interval")
        if not self.bottom_full_interval_px.contains(self.bottom_canonical_px, epsilon=1.0e-9):
            raise ValueError("support bottom leaves its direct interval")
        expected_span = subtract(
            self.bottom_full_interval_px,
            self.top_full_interval_px,
        )
        if self.observed_span_px != expected_span or self.observed_span_px.minimum <= 0.0:
            raise ValueError("support span must come from direct boundaries")
        if (
            tuple(sorted(set(self.trace_coordinates_px)))
            != self.trace_coordinates_px
            or len(self.trace_coordinates_px) < 2
            or len(self.top_trace_intervals_px)
            != len(self.trace_coordinates_px)
            or len(self.bottom_trace_intervals_px)
            != len(self.trace_coordinates_px)
            or any(
                not isinstance(item, FiniteInterval)
                for item in (
                    *self.top_trace_intervals_px,
                    *self.bottom_trace_intervals_px,
                )
            )
            or not math.isfinite(self.top_straight_model_residual_px)
            or not math.isfinite(self.bottom_straight_model_residual_px)
            or self.top_straight_model_residual_px < 0.0
            or self.bottom_straight_model_residual_px < 0.0
        ):
            raise ValueError("support pair requires aligned direct trace intervals")
        top_ids = tuple(
            item if isinstance(item, ObservationId) else ObservationId(str(item))
            for item in self.top_provenance_ids
        )
        bottom_ids = tuple(
            item if isinstance(item, ObservationId) else ObservationId(str(item))
            for item in self.bottom_provenance_ids
        )
        if not top_ids or not bottom_ids:
            raise ValueError("support boundary provenance is required")
        if len(set(top_ids)) != len(top_ids) or len(set(bottom_ids)) != len(bottom_ids):
            raise ValueError("support boundary provenance must be unique")
        object.__setattr__(self, "top_provenance_ids", top_ids)
        object.__setattr__(self, "bottom_provenance_ids", bottom_ids)


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
    enclosing_pair_id: str | None = None
    trace_position_intervals_px: tuple[FiniteInterval, ...] = ()
    observed_direction_interval_degrees: FiniteInterval | None = None

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
        if self.trace_position_intervals_px and len(
            self.trace_position_intervals_px
        ) != len(self.trace_coordinates_px):
            raise ValueError("cross trace intervals disagree with trace coordinates")
        if any(
            not isinstance(item, FiniteInterval)
            for item in self.trace_position_intervals_px
        ):
            raise TypeError("cross trace positions must use finite intervals")
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
            or (
                self.enclosing_pair_id is not None
                and not self.enclosing_pair_id
            )
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
        if self.observed_direction_interval_degrees is None:
            object.__setattr__(
                self,
                "observed_direction_interval_degrees",
                self.full_direction_interval_degrees,
            )
        elif not isinstance(
            self.observed_direction_interval_degrees,
            FiniteInterval,
        ):
            raise TypeError("cross observed direction must be FiniteInterval")
        observed_direction = self.observed_direction_interval_degrees
        if (
            self.full_direction_interval_degrees is not None
            and observed_direction is not None
            and (
                not observed_direction.contains(
                    self.full_direction_interval_degrees.minimum,
                    epsilon=1.0e-9,
                )
                or not observed_direction.contains(
                    self.full_direction_interval_degrees.maximum,
                    epsilon=1.0e-9,
                )
            )
        ):
            raise ValueError("cross observed direction lost feasible direction")
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
        if self.evidence in {
            CrossEvidence.DIRECT,
            CrossEvidence.TEMPLATE_LOCAL_REFINEMENT,
        }:
            source = (identity,)
        elif not source:
            raise ValueError("inferred cross binding needs source observations")
        if len(set(source)) != len(source):
            raise ValueError("cross source observations must be unique")
        object.__setattr__(self, "source_observation_ids", source)

    def projected_shift_px(
        self,
        *,
        source_trace_px: float,
        target_trace_px: float,
    ) -> float | None:
        """Project only inside this binding's directly observed trace domain."""

        if not math.isfinite(source_trace_px) or not math.isfinite(
            target_trace_px
        ):
            raise ValueError("cross projection traces must be finite")
        if (
            not self.role_authorized
            or self.canonical_direction_degrees is None
            or len(self.trace_coordinates_px) < 2
            or target_trace_px < self.trace_coordinates_px[0] - 0.5
            or target_trace_px > self.trace_coordinates_px[-1] + 0.5
        ):
            return None
        return math.tan(
            math.radians(self.canonical_direction_degrees)
        ) * (target_trace_px - source_trace_px)

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
        observed_traces = tuple(
            getattr(observation, "trace_coordinates_px", ())
        )
        trace_intervals = tuple(
            getattr(observation, "trace_position_intervals_px", ())
        )
        return cls(
            role=run.role_hint,
            run_id=run.run_id,
            observation_id=observation.observation_id,
            coordinate_interval_px=coordinate,
            trace_coordinates_px=(
                observed_traces
                if observed_traces
                else tuple(run.trace_coordinates_px)
            ),
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
            observed_direction_interval_degrees=(
                getattr(
                    observation,
                    "angle_interval_degrees",
                    direction,
                )
            ),
            trace_position_intervals_px=trace_intervals,
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
    lane_reference_trace_px: float = 0.0
    source_direction: SharedStripDirection | None = None
    top_bindings: tuple[CrossRoleBinding, ...] = ()
    bottom_bindings: tuple[CrossRoleBinding, ...] = ()
    registered_trace_coordinates_px: tuple[int, ...] = ()
    longitudinal_support_domains_px: tuple[FiniteInterval, ...] = ()
    boundary_axis: BoundaryAxis = BoundaryAxis.Y
    maximum_registered_runs: int = 256
    maximum_fitted_observations: int = 256
    maximum_compatible_pairs: int = 4096
    maximum_evaluated_fits: int = 4096
    registered_run_count: int | None = None
    fitted_observation_count: int | None = None
    minimum_shared_trace_support: int = 2
    aperture_aspect_ratio_authority: ApertureAspectRatioAuthority = field(
        default_factory=unavailable_aperture_aspect_ratio_authority
    )

    def __post_init__(self) -> None:
        if not isinstance(self.template, TemplateSpec):
            raise TypeError("template cross input requires TemplateSpec")
        if not isinstance(
            self.aperture_aspect_ratio_authority,
            ApertureAspectRatioAuthority,
        ):
            raise TypeError("cross input requires typed aspect-ratio authority")
        if self.source_direction is not None and not isinstance(
            self.source_direction,
            SharedStripDirection,
        ):
            raise TypeError("cross source direction must be shared and typed")
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
            if intersect(height, template_height) is None:
                raise ValueError("fixed height contradicts template frame height")
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
                left.maximum > right.minimum
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
        binding_run_count = len(
            {item.run_id for item in (*self.top_bindings, *self.bottom_bindings)}
        )
        observation_count = len(
            {
                item.observation_id
                for item in (*self.top_bindings, *self.bottom_bindings)
            }
        )
        registered_run_count = self.registered_run_count
        fitted_observation_count = self.fitted_observation_count
        if (
            registered_run_count is not None
            and (not isinstance(registered_run_count, int) or registered_run_count < 0)
        ) or (
            fitted_observation_count is not None
            and (
                not isinstance(fitted_observation_count, int)
                or fitted_observation_count < 0
            )
        ):
            raise ValueError("cross input registration receipt is invalid")
        object.__setattr__(
            self,
            "registered_run_count",
            max(binding_run_count, registered_run_count or 0),
        )
        object.__setattr__(
            self,
            "fitted_observation_count",
            max(observation_count, fitted_observation_count or 0),
        )
        if (
            not isinstance(self.minimum_shared_trace_support, int)
            or self.minimum_shared_trace_support < 0
        ):
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


class CrossWinnerBasis(str, Enum):
    """Exclusive physical proof that selected one short-axis fit."""

    ONLY_AUTHORITATIVE_FIT = "only_authoritative_fit"
    UNIQUE_ENCLOSING_SUPPORT = "unique_enclosing_support"


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
    boundary_use: OutputBoundaryUse
    enclosing_support_pair: EnclosingSupportPair | None = None
    height_compatibility_px: FiniteInterval | None = None
    shift_interval_px: FiniteInterval | None = None
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
        if not isinstance(self.boundary_use, OutputBoundaryUse):
            raise TypeError("cross fit requires a typed boundary use")
        if not self.fixed_height_px.contains(
            self.bottom_canonical_px - self.top_canonical_px,
            epsilon=max(self.fixed_height_px.width, 1.0e-8),
        ):
            raise ValueError("cross aperture does not preserve fixed height")
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
        if any(
            item.evidence
            not in {
                CrossEvidence.DIRECT,
                CrossEvidence.TEMPLATE_LOCAL_REFINEMENT,
            }
            for item in self.direct_bindings
        ):
            raise ValueError("direct ledger contains inferred binding")
        if any(
            item.evidence != CrossEvidence.ASPECT_RATIO_HEIGHT_INFERRED
            for item in self.inferred_bindings
        ):
            raise ValueError("inferred ledger contains direct binding")
        if self.boundary_use == OutputBoundaryUse.APERTURE_PAIR:
            if self.enclosing_support_pair is not None:
                raise ValueError("aperture fit cannot carry support output")
        elif self.boundary_use == OutputBoundaryUse.ENCLOSING_SUPPORT_PAIR:
            support = self.enclosing_support_pair
            if not self.direct_pair or len(self.direct_bindings) != 2 or self.inferred_bindings:
                raise ValueError("enclosing support requires two-sided direct bindings")
            if not isinstance(support, EnclosingSupportPair):
                raise TypeError("enclosing support output must be typed")
            if self.selected_direction is None:
                raise ValueError("enclosing support requires shared direction")
            top_binding, bottom_binding = self.direct_bindings
            if (
                top_binding.role != BoundaryRole.TOP
                or bottom_binding.role != BoundaryRole.BOTTOM
                or support.top_full_interval_px != top_binding.full_interval_px
                or support.bottom_full_interval_px != bottom_binding.full_interval_px
                or support.top_provenance_ids != (top_binding.observation_id,)
                or support.bottom_provenance_ids != (bottom_binding.observation_id,)
            ):
                raise ValueError("support output must preserve direct bindings")
            span = support.observed_span_px
            aperture_height = self.bottom_canonical_px - self.top_canonical_px
            if span.minimum <= aperture_height:
                raise ValueError("support span does not enclose canonical H")
            if (
                span.maximum
                > OUTPUT_PROTECTION_SPEC.maximum_enclosing_support_height_ratio
                * aperture_height
                + 1.0e-9
            ):
                raise ValueError("support span exceeds universal 1.1H bound")
            if (
                support.top_full_interval_px.minimum > self.top_canonical_px + 1.0e-9
                or support.bottom_full_interval_px.maximum < self.bottom_canonical_px - 1.0e-9
            ):
                raise ValueError("support does not contain fixed-H aperture")
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
        if not isinstance(self.single_side_inferred, bool):
            raise ValueError("cross closure flags are invalid")
        for interval in (
            self.height_compatibility_px,
            self.shift_interval_px,
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
    def bound_observation_ids(self) -> tuple[ObservationId, ...]:
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
    winner_basis: CrossWinnerBasis | None
    reason: str | None
    receipt: CrossSearchReceipt
    aperture_aspect_ratio_authority: ApertureAspectRatioAuthority = field(
        default_factory=unavailable_aperture_aspect_ratio_authority
    )

    def __post_init__(self) -> None:
        if not isinstance(
            self.aperture_aspect_ratio_authority,
            ApertureAspectRatioAuthority,
        ):
            raise TypeError("cross competition requires aspect-ratio authority")
        if self.status == CrossFitStatus.RESOLVED and (
            self.best is None
            or not isinstance(self.winner_basis, CrossWinnerBasis)
        ):
            raise ValueError(
                "resolved cross competition requires a best fit and winner basis"
            )
        if self.status != CrossFitStatus.RESOLVED and self.winner_basis is not None:
            raise ValueError("unresolved cross competition cannot have a winner basis")
        if self.status == CrossFitStatus.BOUND_EXCEEDED and self.best is not None:
            raise ValueError("bound-exceeded cross competition cannot select a fit")
        if self.reason is not None and not self.reason:
            raise ValueError("cross competition reason cannot be empty")
