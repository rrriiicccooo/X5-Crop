"""Small, current-only contracts for indexed photo templates.

The types in this module deliberately stop at a sequence fit.  They do not
own candidate chains, materialisation, crop geometry, or pixel queries.  A
template is a fixed physical rule (frame width, pitch and slot count); direct
observations may calibrate or veto that rule, but never create a second
runtime path.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from ...domain import FiniteInterval, ObservationId, PositiveInterval


MAX_LOCAL_ADVANCE_ANOMALIES = 1
MAX_TEMPLATE_FIT_PASSES = 5
TEMPLATE_ROLE_REFINEMENT_RADIUS_RATIO = 0.11
MIN_TEMPLATE_ROLE_REFINEMENT_RADIUS_PX = 3.0
from .model import BoundaryRole


def template_role_refinement_radius_px(pitch_px: float) -> float:
    """Return the one canonical bounded local role-search radius.

    The ratio scales with scan resolution; the small pixel floor only covers
    raster quantisation at very low resolutions.  This is a refinement window,
    never placement authority.
    """

    if not math.isfinite(pitch_px) or pitch_px <= 0.0:
        raise ValueError("template role refinement requires a positive pitch")
    return max(
        MIN_TEMPLATE_ROLE_REFINEMENT_RADIUS_PX,
        pitch_px * TEMPLATE_ROLE_REFINEMENT_RADIUS_RATIO,
    )


def _finite_interval(value: FiniteInterval | PositiveInterval | float | int) -> FiniteInterval:
    """Coerce one numeric value to an exact finite interval.

    Numeric coercion keeps the public contracts pleasant to use in focused
    tests while all stored values remain the canonical interval type.
    """

    if isinstance(value, FiniteInterval):
        return value
    if isinstance(value, PositiveInterval):
        return FiniteInterval(value.minimum, value.maximum)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return FiniteInterval.exact(float(value))
    raise TypeError("template interval must be finite interval or number")


def _positive_interval(
    value: FiniteInterval | PositiveInterval | float | int,
) -> PositiveInterval:
    if isinstance(value, PositiveInterval):
        return value
    interval = _finite_interval(value)
    if interval.minimum <= 0.0:
        raise ValueError("template positive interval must be positive")
    return PositiveInterval(interval.minimum, interval.maximum)


class PhaseAnchorAuthority(str, Enum):
    """Explicit authority behind a non-pixel phase anchor."""

    USER_PROVIDED = "user_provided"


@dataclass(frozen=True)
class PhaseLatticeAuthority:
    """Finite periodic phase domain compiled before pixel measurement.

    ``cycle_phase`` lives in the direction-normalized interval
    ``[0, period)``.  ``integer_slot_offset`` is a discrete template fact;
    it must never be widened into selected-placement uncertainty.
    """

    period_px: FiniteInterval | PositiveInterval | float
    cycle_origin_px: float
    minimum_slot_offset: int
    maximum_slot_offset: int

    def __post_init__(self) -> None:
        period = _positive_interval(self.period_px)
        object.__setattr__(self, "period_px", period)
        if not math.isfinite(self.cycle_origin_px):
            raise ValueError("phase lattice origin must be finite")
        if (
            not isinstance(self.minimum_slot_offset, int)
            or isinstance(self.minimum_slot_offset, bool)
            or not isinstance(self.maximum_slot_offset, int)
            or isinstance(self.maximum_slot_offset, bool)
            or self.minimum_slot_offset > self.maximum_slot_offset
        ):
            raise ValueError("phase lattice offset bounds are invalid")
    def contains_offset(self, value: int) -> bool:
        return self.minimum_slot_offset <= value <= self.maximum_slot_offset

    def with_period(
        self,
        period_px: FiniteInterval | PositiveInterval | float,
    ) -> "PhaseLatticeAuthority":
        return PhaseLatticeAuthority(
            period_px=period_px,
            cycle_origin_px=self.cycle_origin_px,
            minimum_slot_offset=self.minimum_slot_offset,
            maximum_slot_offset=self.maximum_slot_offset,
        )


@dataclass(frozen=True)
class PhaseLatticeFit:
    """One continuous cycle alignment plus one discrete slot offset."""

    authority: PhaseLatticeAuthority
    cycle_phase_interval_px: FiniteInterval
    canonical_cycle_phase_px: float
    integer_slot_offset: int
    canonical_period_px: float
    absolute_phase_interval_px: FiniteInterval
    canonical_absolute_phase_px: float
    direction: int

    def __post_init__(self) -> None:
        if self.direction not in {-1, 1}:
            raise ValueError("phase lattice direction must be -1 or +1")
        if not self.authority.contains_offset(self.integer_slot_offset):
            raise ValueError("phase lattice offset leaves compiled authority")
        if not (
            self.authority.period_px.minimum - 1.0e-9
            <= self.canonical_period_px
            <= self.authority.period_px.maximum + 1.0e-9
        ):
            raise ValueError("phase lattice period leaves compiled authority")
        if not (
            0.0 <= self.canonical_cycle_phase_px < self.canonical_period_px
            and self.cycle_phase_interval_px.contains(
                self.canonical_cycle_phase_px,
                epsilon=1.0e-9,
            )
            and self.cycle_phase_interval_px.minimum >= 0.0
            and self.cycle_phase_interval_px.maximum
            <= self.canonical_period_px + 1.0e-9
        ):
            raise ValueError("phase lattice cycle phase is invalid")
        expected = self.authority.cycle_origin_px + self.direction * (
            self.canonical_cycle_phase_px
            + self.integer_slot_offset * self.canonical_period_px
        )
        if (
            not math.isfinite(self.canonical_absolute_phase_px)
            or abs(expected - self.canonical_absolute_phase_px) > 1.0e-7
            or not self.absolute_phase_interval_px.contains(
                self.canonical_absolute_phase_px,
                epsilon=1.0e-9,
            )
        ):
            raise ValueError("phase lattice absolute projection is inconsistent")


class LocalAdvanceKind(str, Enum):
    """A local departure from the normal pitch relation."""

    NOMINAL = "nominal"
    WIDE = "wide"
    NARROW = "narrow"
    CONTACT = "contact"
    OVERLAP = "overlap"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, order=True)
class TemplateRole:
    """One indexed sequence boundary (start or end of one slot)."""

    role_index: int
    lane_ordinal: int
    role: BoundaryRole

    def __post_init__(self) -> None:
        if self.role_index < 0 or self.lane_ordinal <= 0:
            raise ValueError("template role index is invalid")
        if self.role not in {BoundaryRole.START, BoundaryRole.END}:
            raise ValueError("template role must be a sequence edge")
        expected = (self.lane_ordinal - 1) * 2 + (
            0 if self.role == BoundaryRole.START else 1
        )
        if self.role_index != expected:
            raise ValueError("template role index does not match its ordinal")

    @property
    def slot_index(self) -> int:
        return self.lane_ordinal - 1


def ordered_template_roles(slot_count: int) -> tuple[TemplateRole, ...]:
    """Return the only legal role order for a fixed slot count."""

    if slot_count <= 0:
        raise ValueError("template requires a positive slot count")
    return tuple(
        TemplateRole(
            role_index=(ordinal - 1) * 2 + edge_index,
            lane_ordinal=ordinal,
            role=role,
        )
        for ordinal in range(1, slot_count + 1)
        for edge_index, role in enumerate((BoundaryRole.START, BoundaryRole.END))
    )


@dataclass(frozen=True)
class TemplateSpec:
    """Fixed physical template rules used by the indexed phase solver."""

    template_id: str
    frame_width_px: FiniteInterval | PositiveInterval | float
    pitch_px: FiniteInterval | PositiveInterval | float
    count: int
    phase_lattice_authority: PhaseLatticeAuthority
    frame_height_px: FiniteInterval | PositiveInterval | float | None = None
    direction: int = 1
    cross: str | None = None
    nominal_gap_px: FiniteInterval | float | None = None

    def __post_init__(self) -> None:
        if not self.template_id:
            raise ValueError("template identity must not be empty")
        object.__setattr__(self, "frame_width_px", _positive_interval(self.frame_width_px))
        object.__setattr__(self, "pitch_px", _positive_interval(self.pitch_px))
        if self.frame_height_px is not None:
            object.__setattr__(
                self,
                "frame_height_px",
                _positive_interval(self.frame_height_px),
            )
        if self.count <= 0:
            raise ValueError("template count must be positive")
        if not isinstance(self.phase_lattice_authority, PhaseLatticeAuthority):
            raise TypeError("template phase lattice authority must be typed")
        if self.direction not in {-1, 1}:
            raise ValueError("template direction must be -1 or +1")
        if self.cross is not None and not self.cross:
            raise ValueError("template cross identity must not be empty")
        if self.pitch_px.maximum < self.frame_width_px.minimum:
            raise ValueError("template pitch cannot be smaller than frame width")
        if (
            self.phase_lattice_authority.period_px.maximum
            < self.pitch_px.minimum
            or self.pitch_px.maximum
            < self.phase_lattice_authority.period_px.minimum
        ):
            raise ValueError("template pitch and phase period are incompatible")
        if self.nominal_gap_px is not None:
            gap = _finite_interval(self.nominal_gap_px)
            if gap.minimum < 0.0:
                raise ValueError("template nominal gap cannot be negative")
            object.__setattr__(self, "nominal_gap_px", gap)
            expected_minimum = self.frame_width_px.minimum + gap.minimum
            expected_maximum = self.frame_width_px.maximum + gap.maximum
            if expected_maximum < self.pitch_px.minimum or self.pitch_px.maximum < expected_minimum:
                raise ValueError("template pitch and nominal gap are incompatible")

    @property
    def roles(self) -> tuple[TemplateRole, ...]:
        return ordered_template_roles(self.count)

    @property
    def derived_gap_px(self) -> FiniteInterval:
        """The interval left after subtracting frame width from pitch."""

        minimum = self.pitch_px.minimum - self.frame_width_px.maximum
        maximum = self.pitch_px.maximum - self.frame_width_px.minimum
        if minimum < 0.0:
            raise ValueError("template pitch/frame interval has no non-negative gap")
        return FiniteInterval(minimum, maximum)

    @property
    def gap_prior_px(self) -> FiniteInterval:
        return (
            self.nominal_gap_px
            if self.nominal_gap_px is not None
            else self.derived_gap_px
        )


@dataclass(frozen=True)
class PhaseAnchor:
    """One user-declared absolute role, consumed by the normal phase solver.

    Pixel observations remain role-free ``BoundaryEdgeObservation`` values.
    This separate authority prevents an automatic edge from declaring its own
    ordinal and then using that declaration as proof of placement.
    """

    observation_id: ObservationId
    coordinate_interval_px: FiniteInterval
    role: TemplateRole
    authority: PhaseAnchorAuthority
    authority_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.observation_id, ObservationId):
            raise TypeError("phase anchor identity must be ObservationId")
        if not isinstance(self.coordinate_interval_px, FiniteInterval):
            raise TypeError("phase anchor coordinate must be FiniteInterval")
        if not isinstance(self.role, TemplateRole):
            raise TypeError("manual phase anchor requires an indexed role")
        if self.authority != PhaseAnchorAuthority.USER_PROVIDED:
            raise ValueError("phase anchor requires explicit user authority")
        if not self.authority_id:
            raise ValueError("phase anchor authority identity must not be empty")


@dataclass(frozen=True)
class PitchFit:
    """Measured/declared pitch relation for one fixed template."""

    frame_width_px: FiniteInterval | PositiveInterval | float
    gap_interval_px: FiniteInterval | float
    pitch_interval_px: FiniteInterval | PositiveInterval | float
    canonical_frame_width_px: float
    canonical_pitch_px: float
    scale_px_per_mm: PositiveInterval | None = None
    observation_ids: tuple[ObservationId, ...] = ()

    def __post_init__(self) -> None:
        width = _positive_interval(self.frame_width_px)
        gap = _finite_interval(self.gap_interval_px)
        pitch = _positive_interval(self.pitch_interval_px)
        object.__setattr__(self, "frame_width_px", width)
        object.__setattr__(self, "gap_interval_px", gap)
        object.__setattr__(self, "pitch_interval_px", pitch)
        if gap.minimum < 0.0:
            raise ValueError("pitch gap interval cannot be negative")
        if not math.isfinite(self.canonical_frame_width_px) or not (
            width.minimum - 1.0e-9
            <= self.canonical_frame_width_px
            <= width.maximum + 1.0e-9
        ):
            raise ValueError("canonical frame width must lie in its interval")
        if not math.isfinite(self.canonical_pitch_px) or not (
            pitch.minimum - 1.0e-9
            <= self.canonical_pitch_px
            <= pitch.maximum + 1.0e-9
        ):
            raise ValueError("canonical pitch must lie in its interval")
        if self.scale_px_per_mm is not None and not isinstance(
            self.scale_px_per_mm,
            PositiveInterval,
        ):
            raise TypeError("pitch scale must be PositiveInterval")
        if len(set(self.observation_ids)) != len(self.observation_ids):
            raise ValueError("pitch observations must be unique")
        if any(not isinstance(item, ObservationId) for item in self.observation_ids):
            raise TypeError("pitch observations must be typed identities")

    def with_calibrated_template(self, template: TemplateSpec) -> "PitchFit":
        """Retain pitch identity while calibrating physical W and gap."""

        if not (
            template.pitch_px.minimum - 1.0e-9
            <= self.canonical_pitch_px
            <= template.pitch_px.maximum + 1.0e-9
        ):
            raise ValueError(
                "calibrated template excludes the selected pitch: "
                f"{self.canonical_pitch_px} not in "
                f"[{template.pitch_px.minimum}, {template.pitch_px.maximum}]"
            )
        width = (template.frame_width_px.minimum + template.frame_width_px.maximum) / 2.0
        return PitchFit(
            frame_width_px=template.frame_width_px,
            gap_interval_px=template.gap_prior_px,
            pitch_interval_px=template.pitch_px,
            canonical_frame_width_px=width,
            canonical_pitch_px=self.canonical_pitch_px,
            scale_px_per_mm=self.scale_px_per_mm,
            observation_ids=self.observation_ids,
        )


@dataclass(frozen=True)
class LocalAdvanceRelation:
    """One adjacency's prefix adjustment from the nominal pitch.

    ``delta_interval_px`` is an adjustment, not a second free frame width.  A
    relation at ordinal ``i`` affects slot ``i + 1`` and every later slot once.
    """

    relation_ordinal: int
    kind: LocalAdvanceKind
    delta_interval_px: FiniteInterval
    canonical_delta_px: float
    observation_ids: tuple[ObservationId, ...] = ()

    def __post_init__(self) -> None:
        if self.relation_ordinal <= 0:
            raise ValueError("local relation ordinal must be positive")
        if not isinstance(self.kind, LocalAdvanceKind):
            raise TypeError("local relation kind must be typed")
        if not self.delta_interval_px.contains(self.canonical_delta_px, epsilon=1.0e-9):
            raise ValueError("local relation canonical delta is outside interval")
        if len(set(self.observation_ids)) != len(self.observation_ids):
            raise ValueError("local relation observations must be unique")
        if any(not isinstance(item, ObservationId) for item in self.observation_ids):
            raise TypeError("local relation observations must be typed identities")
        if self.kind == LocalAdvanceKind.NOMINAL and (
            self.delta_interval_px != FiniteInterval.exact(0.0)
            or self.canonical_delta_px != 0.0
        ):
            raise ValueError("nominal local relation must have zero adjustment")
        if self.kind != LocalAdvanceKind.NOMINAL and not self.observation_ids:
            raise ValueError("non-nominal local relation needs direct evidence")

    @property
    def is_anomaly(self) -> bool:
        return self.kind not in {
            LocalAdvanceKind.NOMINAL,
            LocalAdvanceKind.UNRESOLVED,
        }


@dataclass(frozen=True)
class SequenceFit:
    """A fixed-count sequence placement with direct/inferred role accounting."""

    template: TemplateSpec
    phase_lattice_fit: PhaseLatticeFit
    pitch_fit: PitchFit
    canonical_role_positions_px: tuple[float, ...]
    role_positions_px: tuple[FiniteInterval, ...]
    role_full_position_intervals_px: tuple[FiniteInterval, ...]
    role_observation_ids: tuple[ObservationId | None, ...]
    matched_role_indices: tuple[int, ...]
    inferred_role_indices: tuple[int, ...]
    direct_observation_ids: tuple[ObservationId, ...]
    independent_support_ids: tuple[ObservationId, ...]
    local_advance_relations: tuple[LocalAdvanceRelation, ...] = ()
    contradicted_observation_count: int = 0
    residual_sum_px: float = 0.0
    independent_support_coverage: float = 0.0
    independent_polarity_support_count: int = 0

    @property
    def independent_support_count(self) -> int:
        return len(self.independent_support_ids)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.phase_lattice_fit, PhaseLatticeFit)
            or self.phase_lattice_fit.authority
            != self.template.phase_lattice_authority
            or self.phase_lattice_fit.direction != self.template.direction
        ):
            raise ValueError("sequence phase lattice disagrees with template")
        if (
            len(self.canonical_role_positions_px) != 2 * self.template.count
            or len(self.role_positions_px) != 2 * self.template.count
            or len(self.role_full_position_intervals_px)
            != 2 * self.template.count
            or len(self.role_observation_ids) != 2 * self.template.count
        ):
            raise ValueError("sequence role position count is invalid")
        if any(
            not interval.contains(canonical, epsilon=1.0e-9)
            for canonical, interval in zip(
                self.canonical_role_positions_px,
                self.role_positions_px,
                strict=True,
            )
        ):
            raise ValueError("canonical role position is outside its interval")
        if any(
            not full.contains(fit.minimum, epsilon=1.0e-9)
            or not full.contains(fit.maximum, epsilon=1.0e-9)
            for fit, full in zip(
                self.role_positions_px,
                self.role_full_position_intervals_px,
                strict=True,
            )
        ):
            raise ValueError("sequence full role interval excludes fit interval")
        expected_roles = set(range(2 * self.template.count))
        matched = set(self.matched_role_indices)
        inferred = set(self.inferred_role_indices)
        if not matched.issubset(expected_roles) or not inferred.issubset(expected_roles):
            raise ValueError("sequence role binding index is invalid")
        if matched & inferred or len(matched) + len(inferred) > len(expected_roles):
            raise ValueError("sequence role binding is not disjoint")
        if (
            not self.independent_support_ids
            or len(set(self.independent_support_ids))
            != len(self.independent_support_ids)
            or any(
                not isinstance(identity, ObservationId)
                for identity in self.independent_support_ids
            )
            or self.independent_support_count > len(matched)
        ):
            raise ValueError("sequence independent support ledger is invalid")
        if self.contradicted_observation_count < 0:
            raise ValueError("sequence contradiction count is invalid")
        if (
            not math.isfinite(self.independent_support_coverage)
            or not 0.0
            <= self.independent_support_coverage
            <= self.independent_support_count + 1.0e-9
        ):
            raise ValueError("sequence independent support coverage is invalid")
        if not (
            0
            <= self.independent_polarity_support_count
            <= self.independent_support_count
        ):
            raise ValueError("sequence independent polarity support is invalid")
        if not math.isfinite(self.residual_sum_px) or self.residual_sum_px < 0.0:
            raise ValueError("sequence residual is invalid")
        if tuple(item.relation_ordinal for item in self.local_advance_relations) != tuple(
            range(1, len(self.local_advance_relations) + 1)
        ):
            raise ValueError("local relation ordinals must be contiguous")
        if len(self.local_advance_relations) > max(0, self.template.count - 1):
            raise ValueError("local relations exceed template adjacencies")
        if (
            sum(item.is_anomaly for item in self.local_advance_relations)
            > MAX_LOCAL_ADVANCE_ANOMALIES
        ):
            raise ValueError("local anomaly count exceeds the bounded template model")
        if len(set(self.direct_observation_ids)) != len(self.direct_observation_ids):
            raise ValueError("sequence direct observations must be unique")
        if any(
            identity is not None and not isinstance(identity, ObservationId)
            for identity in self.role_observation_ids
        ):
            raise TypeError("sequence role observations must be typed identities")
        bound_ids = tuple(
            identity for identity in self.role_observation_ids if identity is not None
        )
        if len(set(bound_ids)) != len(bound_ids):
            raise ValueError("one observation cannot bind multiple template roles")
        if tuple(index for index, identity in enumerate(self.role_observation_ids) if identity is not None) != tuple(
            self.matched_role_indices
        ):
            raise ValueError("sequence matched roles disagree with role observations")
        if not set(bound_ids).issubset(self.direct_observation_ids):
            raise ValueError("bound role observations must be direct observations")
        direction = self.template.direction
        starts = self.canonical_role_positions_px[0::2]
        ends = self.canonical_role_positions_px[1::2]
        widths = tuple(
            direction * (end - start)
            for start, end in zip(starts, ends, strict=True)
        )
        if any(
            not (
                self.template.frame_width_px.minimum - 1.0e-7
                <= width
                <= self.template.frame_width_px.maximum + 1.0e-7
            )
            for width in widths
        ):
            raise ValueError("sequence frame order contradicts fixed width")
        if any(
            direction * (right - left) < -1.0e-7
            for left, right in zip(starts, starts[1:])
        ):
            raise ValueError("sequence slot starts are not monotonic")
        if any(
            direction * (next_start - end)
            < -self.template.frame_width_px.maximum - 1.0e-7
            for end, next_start in zip(ends, starts[1:])
        ):
            raise ValueError("sequence local overlap exceeds one frame width")

    def with_calibrated_template(self, template: TemplateSpec) -> "SequenceFit":
        """Preserve the discrete role binding while narrowing physical state."""

        if (
            template.template_id != self.template.template_id
            or template.count != self.template.count
            or template.direction != self.template.direction
        ):
            raise ValueError("calibrated template changes sequence identity")
        width = (
            template.frame_width_px.minimum + template.frame_width_px.maximum
        ) / 2.0
        period = self.pitch_fit.canonical_pitch_px
        if not (
            template.phase_lattice_authority.period_px.minimum - 1.0e-9
            <= period
            <= template.phase_lattice_authority.period_px.maximum + 1.0e-9
        ):
            period = template.phase_lattice_authority.period_px.center
        lattice = self.phase_lattice_fit
        normalized = template.direction * (
            lattice.canonical_absolute_phase_px
            - template.phase_lattice_authority.cycle_origin_px
        )
        cycle = normalized - lattice.integer_slot_offset * period
        if not 0.0 <= cycle < period:
            raise ValueError("calibrated period changes the discrete phase offset")
        cycle_radius = min(
            cycle,
            period - cycle,
            lattice.absolute_phase_interval_px.width / 2.0,
        )
        canonical_positions: list[float] = []
        role_intervals: list[FiniteInterval] = []
        role_full_intervals: list[FiniteInterval] = []
        for role, old_canonical, old_interval, old_full_interval, observation_id in zip(
            template.roles,
            self.canonical_role_positions_px,
            self.role_positions_px,
            self.role_full_position_intervals_px,
            self.role_observation_ids,
            strict=True,
        ):
            canonical = (
                old_canonical
                if role.role == BoundaryRole.START or observation_id is not None
                else canonical_positions[-1] + template.direction * width
            )
            canonical_positions.append(canonical)
            role_intervals.append(
                FiniteInterval(
                    min(old_interval.minimum, canonical),
                    max(old_interval.maximum, canonical),
                )
            )
            role_full_intervals.append(
                FiniteInterval(
                    min(old_full_interval.minimum, canonical),
                    max(old_full_interval.maximum, canonical),
                )
            )
        return SequenceFit(
            template=template,
            phase_lattice_fit=PhaseLatticeFit(
                authority=template.phase_lattice_authority,
                cycle_phase_interval_px=FiniteInterval(
                    cycle - cycle_radius,
                    cycle + cycle_radius,
                ),
                canonical_cycle_phase_px=cycle,
                integer_slot_offset=lattice.integer_slot_offset,
                canonical_period_px=period,
                absolute_phase_interval_px=lattice.absolute_phase_interval_px,
                canonical_absolute_phase_px=lattice.canonical_absolute_phase_px,
                direction=template.direction,
            ),
            pitch_fit=self.pitch_fit.with_calibrated_template(template),
            canonical_role_positions_px=tuple(canonical_positions),
            role_positions_px=tuple(role_intervals),
            role_full_position_intervals_px=tuple(role_full_intervals),
            role_observation_ids=self.role_observation_ids,
            matched_role_indices=self.matched_role_indices,
            inferred_role_indices=self.inferred_role_indices,
            direct_observation_ids=self.direct_observation_ids,
            independent_support_ids=self.independent_support_ids,
            local_advance_relations=self.local_advance_relations,
            contradicted_observation_count=self.contradicted_observation_count,
            residual_sum_px=self.residual_sum_px,
            independent_support_coverage=self.independent_support_coverage,
            independent_polarity_support_count=(
                self.independent_polarity_support_count
            ),
        )

@dataclass(frozen=True)
class TemplateSearchReceipt:
    """Auditable bounded work units for indexed phase fitting.

    Counts describe registrations and lookups only.  There is intentionally
    no chain/materialisation/cache counter: those are not part of this layer.
    """

    observation_count: int
    role_count: int
    phase_lookup_count: int
    role_binding_count: int
    local_relation_evaluation_count: int
    phase_hypothesis_count: int
    phase_offset_lookup_count: int
    direct_observation_count: int
    inferred_role_count: int
    peak_temporary_bytes: int = 0
    fit_pass_count: int = 1
    separator_lattice_hypothesis_count: int = 0

    def __post_init__(self) -> None:
        values = (
            self.observation_count,
            self.role_count,
            self.phase_lookup_count,
            self.role_binding_count,
            self.local_relation_evaluation_count,
            self.phase_hypothesis_count,
            self.phase_offset_lookup_count,
            self.direct_observation_count,
            self.inferred_role_count,
            self.peak_temporary_bytes,
            self.fit_pass_count,
            self.separator_lattice_hypothesis_count,
        )
        if any(not isinstance(value, int) or value < 0 for value in values):
            raise ValueError("template work receipt values must be non-negative integers")
        if self.role_count == 0 and self.role_binding_count:
            raise ValueError("role bindings require roles")
        if self.direct_observation_count > self.observation_count:
            raise ValueError("direct observations exceed registrations")
        if self.inferred_role_count > self.role_count:
            raise ValueError("inferred roles exceed template roles")
        if self.fit_pass_count <= 0:
            raise ValueError("template fit pass count must be positive")
        if self.phase_offset_lookup_count > self.phase_hypothesis_count:
            raise ValueError("phase offset lookups exceed phase hypotheses")

    def validate_bounds(
        self,
        *,
        observation_count: int | None = None,
        role_count: int | None = None,
        slot_count: int | None = None,
        max_fit_passes: int = MAX_TEMPLATE_FIT_PASSES,
    ) -> None:
        """Reject any receipt that cannot come from one indexed pass.

        Phase lookup and role binding are each at most ``H * R``.  Local
        relations are per adjacency (``count - 1``) per declared numeric fit
        pass, never per candidate chain.  Five passes cover provisional fit,
        physical rebind, one local refit, source-pitch rebind, and its one
        local refit.  The method fails explicitly; callers must not truncate.
        """

        h = self.observation_count if observation_count is None else observation_count
        r = self.role_count if role_count is None else role_count
        if h < 0 or r < 0:
            raise ValueError("template work dimensions must be non-negative")
        if slot_count is None:
            if r % 2:
                raise ValueError("role count must be even when slot count is omitted")
            slot_count = r // 2
        if slot_count <= 0 or r != 2 * slot_count:
            raise ValueError("template work dimensions are inconsistent")
        if self.observation_count != h or self.role_count != r:
            raise ValueError("receipt dimensions do not match the requested bound")
        if max_fit_passes <= 0 or self.fit_pass_count > max_fit_passes:
            raise ValueError("template fit pass bound exceeded")
        max_hypotheses = h * max(6, r) * self.fit_pass_count
        if (
            self.phase_lookup_count > max_hypotheses
            or self.phase_hypothesis_count > max_hypotheses
            or self.role_binding_count > self.phase_hypothesis_count * r
            or self.local_relation_evaluation_count
            > max(0, slot_count - 1) * self.fit_pass_count
            or self.phase_offset_lookup_count > max_hypotheses
            or self.separator_lattice_hypothesis_count > max_hypotheses
        ):
            raise ValueError("template indexed work exceeded its structural bound")


__all__ = [
    "LocalAdvanceKind",
    "LocalAdvanceRelation",
    "MAX_TEMPLATE_FIT_PASSES",
    "PhaseAnchor",
    "PhaseLatticeAuthority",
    "PhaseLatticeFit",
    "PitchFit",
    "SequenceFit",
    "TemplateRole",
    "TemplateSearchReceipt",
    "TemplateSpec",
    "ordered_template_roles",
    "template_role_refinement_radius_px",
]
