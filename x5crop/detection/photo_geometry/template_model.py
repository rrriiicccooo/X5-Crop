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
from ...domain import EvidenceState, FiniteInterval, ObservationId, PositiveInterval


MAX_TEMPLATE_FIT_PASSES = 5
TEMPLATE_ROLE_REFINEMENT_RADIUS_RATIO = 0.11
MIN_TEMPLATE_ROLE_REFINEMENT_RADIUS_PX = 3.0
GENERIC_SEPARATOR_GAP_MINIMUM_FRAME_RATIO = 0.02
GENERIC_SEPARATOR_GAP_MAXIMUM_FRAME_RATIO = 0.20
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


def generic_separator_gap_interval_px(
    frame_width_px: FiniteInterval | PositiveInterval,
) -> FiniteInterval:
    """Return the bounded search prior for formats without a gap seed.

    This interval only compiles candidate-independent search and lattice work.
    It is not aperture compatibility, does not override a measured separator,
    and cannot authorize a local advance by itself.
    """

    if not isinstance(frame_width_px, (FiniteInterval, PositiveInterval)):
        raise TypeError("generic separator gap requires an interval width")
    if frame_width_px.minimum <= 0.0:
        raise ValueError("generic separator gap requires a positive width")
    return FiniteInterval(
        frame_width_px.minimum
        * GENERIC_SEPARATOR_GAP_MINIMUM_FRAME_RATIO,
        frame_width_px.maximum
        * GENERIC_SEPARATOR_GAP_MAXIMUM_FRAME_RATIO,
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


def phase_lattice_fit_from_absolute(
    template: "TemplateSpec",
    *,
    absolute_phase_px: float,
    period_px: float,
    uncertainty_px: float,
) -> PhaseLatticeFit | None:
    """Project one absolute pixel phase into the compiled lattice authority."""

    authority = template.phase_lattice_authority
    normalized = template.direction * (
        absolute_phase_px - authority.cycle_origin_px
    )
    offset = math.floor(normalized / period_px)
    if not authority.contains_offset(offset):
        return None
    cycle = normalized - offset * period_px
    if cycle >= period_px - 1.0e-9:
        cycle = 0.0
        offset += 1
        if not authority.contains_offset(offset):
            return None
    radius = min(max(0.0, uncertainty_px), cycle, period_px - cycle)
    cycle_interval = FiniteInterval(cycle - radius, cycle + radius)
    projected = tuple(
        authority.cycle_origin_px
        + template.direction * (value + offset * period_px)
        for value in (cycle_interval.minimum, cycle_interval.maximum)
    )
    return PhaseLatticeFit(
        authority=authority,
        cycle_phase_interval_px=cycle_interval,
        canonical_cycle_phase_px=cycle,
        integer_slot_offset=offset,
        canonical_period_px=period_px,
        absolute_phase_interval_px=FiniteInterval(min(projected), max(projected)),
        canonical_absolute_phase_px=absolute_phase_px,
        direction=template.direction,
    )


class LocalAdvanceKind(str, Enum):
    """A local departure from the normal pitch relation."""

    NOMINAL = "nominal"
    WIDE = "wide"
    NARROW = "narrow"


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


class FrameWidthInferenceFailureKind(str, Enum):
    """Why one required correlated-W inference has no direct authority."""

    COMPLETE_FRAME_UNOBSERVED = "complete_frame_unobserved"
    COMMON_WIDTH_AUTHORITY_UNAVAILABLE = (
        "common_width_authority_unavailable"
    )


@dataclass(frozen=True)
class FrameWidthInferenceAssessment:
    """One correlated common-W authority shared by all inferred roles."""

    state: EvidenceState
    inferred_role_indices: tuple[int, ...]
    supporting_frame_ordinals: tuple[int, ...]
    width_px: PositiveInterval | None
    canonical_width_px: float | None
    observation_ids: tuple[ObservationId, ...]
    failure_kind: FrameWidthInferenceFailureKind | None

    def __post_init__(self) -> None:
        supported = self.state == EvidenceState.SUPPORTED
        unavailable = self.state == EvidenceState.UNAVAILABLE
        if (
            not (supported or unavailable)
            or not self.inferred_role_indices
            or tuple(sorted(set(self.inferred_role_indices)))
            != self.inferred_role_indices
            or any(index < 0 for index in self.inferred_role_indices)
            or tuple(sorted(set(self.supporting_frame_ordinals)))
            != self.supporting_frame_ordinals
            or any(ordinal <= 0 for ordinal in self.supporting_frame_ordinals)
            or len(set(self.observation_ids)) != len(self.observation_ids)
            or any(
                not isinstance(identity, ObservationId)
                for identity in self.observation_ids
            )
        ):
            raise ValueError("Frame width inference assessment is invalid")
        if supported:
            if (
                not isinstance(self.width_px, PositiveInterval)
                or self.width_px.minimum <= 0.0
                or self.canonical_width_px is None
                or not self.width_px.minimum - 1.0e-9
                <= self.canonical_width_px
                <= self.width_px.maximum + 1.0e-9
                or len(self.supporting_frame_ordinals) < 2
                or len(self.observation_ids) < 4
                or self.failure_kind is not None
            ):
                raise ValueError("supported Frame width inference is incomplete")
        elif (
            self.width_px is not None
            or self.canonical_width_px is not None
            or self.supporting_frame_ordinals
            or self.observation_ids
            or not isinstance(
                self.failure_kind,
                FrameWidthInferenceFailureKind,
            )
        ):
            raise ValueError("unavailable Frame width inference carries authority")


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
        return self.kind != LocalAdvanceKind.NOMINAL


@dataclass(frozen=True)
class SequenceRoleLineEvidence:
    """One bound sequence edge's fitted line, retained for output safety only."""

    observation_id: ObservationId
    reference_trace_px: float
    fit_position_interval_px: FiniteInterval
    fit_direction_interval_degrees: FiniteInterval

    def __post_init__(self) -> None:
        if (
            not isinstance(self.observation_id, ObservationId)
            or not math.isfinite(self.reference_trace_px)
            or not isinstance(self.fit_position_interval_px, FiniteInterval)
            or not isinstance(
                self.fit_direction_interval_degrees,
                FiniteInterval,
            )
        ):
            raise ValueError("sequence role line evidence is invalid")


class SequenceBindingUse(str, Enum):
    """Authority granted to one observation after fixed-template fitting."""

    PHASE_ANCHOR = "phase_anchor"
    LOCAL_REFINEMENT = "local_refinement"


@dataclass(frozen=True)
class SequenceRoleBinding:
    """One template role bound atomically to one native observation."""

    use: SequenceBindingUse
    observation_id: ObservationId
    independent_support_id: ObservationId
    canonical_position_px: float
    fit_position_interval_px: FiniteInterval
    full_position_interval_px: FiniteInterval
    line_evidence: SequenceRoleLineEvidence | None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.use, SequenceBindingUse)
            or not isinstance(self.observation_id, ObservationId)
            or not isinstance(self.independent_support_id, ObservationId)
            or not math.isfinite(self.canonical_position_px)
            or not isinstance(self.fit_position_interval_px, FiniteInterval)
            or not isinstance(self.full_position_interval_px, FiniteInterval)
        ):
            raise ValueError("sequence role binding is invalid")
        if not self.fit_position_interval_px.contains(
            self.canonical_position_px,
            epsilon=1.0e-9,
        ):
            raise ValueError("sequence role binding excludes its canonical position")
        if (
            not self.full_position_interval_px.contains(
                self.fit_position_interval_px.minimum,
                epsilon=1.0e-9,
            )
            or not self.full_position_interval_px.contains(
                self.fit_position_interval_px.maximum,
                epsilon=1.0e-9,
            )
        ):
            raise ValueError("sequence role binding full interval excludes fit")
        if self.line_evidence is not None and (
            self.line_evidence.observation_id != self.observation_id
            or not self.full_position_interval_px.contains(
                self.line_evidence.fit_position_interval_px.minimum,
                epsilon=1.0e-9,
            )
            or not self.full_position_interval_px.contains(
                self.line_evidence.fit_position_interval_px.maximum,
                epsilon=1.0e-9,
            )
        ):
            raise ValueError("sequence role line evidence lost its binding")


@dataclass(frozen=True)
class SequenceFit:
    """A fixed-count sequence placement with direct/inferred role accounting."""

    template: TemplateSpec
    phase_lattice_fit: PhaseLatticeFit
    pitch_fit: PitchFit
    model_role_positions_px: tuple[float, ...]
    model_role_intervals_px: tuple[FiniteInterval, ...]
    model_full_role_intervals_px: tuple[FiniteInterval, ...]
    role_bindings: tuple[SequenceRoleBinding | None, ...]
    frame_width_inference: FrameWidthInferenceAssessment | None = None
    local_advance_relations: tuple[LocalAdvanceRelation, ...] = ()
    contradicted_observation_count: int = 0
    residual_sum_px: float = 0.0
    phase_support_coverage: float = 0.0

    @property
    def bound_observation_ids(self) -> tuple[ObservationId, ...]:
        return tuple(
            binding.observation_id
            for binding in self.role_bindings
            if binding is not None
        )

    @property
    def independent_support_ids(self) -> tuple[ObservationId, ...]:
        return tuple(
            sorted(
                {
                    binding.independent_support_id
                    for binding in self.role_bindings
                    if binding is not None
                }
            )
        )

    @property
    def phase_anchor_observation_ids(self) -> tuple[ObservationId, ...]:
        return tuple(
            binding.observation_id
            for binding in self.role_bindings
            if binding is not None
            and binding.use == SequenceBindingUse.PHASE_ANCHOR
        )

    @property
    def local_refinement_observation_ids(self) -> tuple[ObservationId, ...]:
        return tuple(
            binding.observation_id
            for binding in self.role_bindings
            if binding is not None
            and binding.use == SequenceBindingUse.LOCAL_REFINEMENT
        )

    @property
    def phase_support_locations(self) -> tuple[int, ...]:
        """Independent lattice locations, not raw edges, with direct evidence."""

        # END(i) and START(i+1) describe one physical adjacency.  Both may
        # measure its width, but together count as one global phase location.
        return tuple(
            sorted(
                {
                    (role_index + 1) // 2
                    for role_index, binding in enumerate(self.role_bindings)
                    if binding is not None
                    and binding.use == SequenceBindingUse.PHASE_ANCHOR
                }
            )
        )

    @property
    def phase_support_count(self) -> int:
        return len(self.phase_support_locations)

    @property
    def binding_observation_ids(self) -> tuple[ObservationId | None, ...]:
        return tuple(
            None if binding is None else binding.observation_id
            for binding in self.role_bindings
        )

    @property
    def unbound_role_indices(self) -> tuple[int, ...]:
        return tuple(
            index
            for index, binding in enumerate(self.role_bindings)
            if binding is None
        )

    def __post_init__(self) -> None:
        if (
            not isinstance(self.phase_lattice_fit, PhaseLatticeFit)
            or self.phase_lattice_fit.authority
            != self.template.phase_lattice_authority
            or self.phase_lattice_fit.direction != self.template.direction
        ):
            raise ValueError("sequence phase lattice disagrees with template")
        if (
            len(self.model_role_positions_px) != 2 * self.template.count
            or len(self.model_role_intervals_px) != 2 * self.template.count
            or len(self.model_full_role_intervals_px)
            != 2 * self.template.count
            or len(self.role_bindings) != 2 * self.template.count
        ):
            raise ValueError("sequence role position count is invalid")
        if (
            any(not math.isfinite(value) for value in self.model_role_positions_px)
            or any(
                not isinstance(interval, FiniteInterval)
                for interval in (
                    *self.model_role_intervals_px,
                    *self.model_full_role_intervals_px,
                )
            )
            or any(
                binding is not None
                and not isinstance(binding, SequenceRoleBinding)
                for binding in self.role_bindings
            )
        ):
            raise TypeError("sequence role ledger has invalid value types")
        if any(
            not interval.contains(canonical, epsilon=1.0e-9)
            for canonical, interval in zip(
                self.model_role_positions_px,
                self.model_role_intervals_px,
                strict=True,
            )
        ):
            raise ValueError("canonical role position is outside its interval")
        if any(
            not full.contains(fit.minimum, epsilon=1.0e-9)
            or not full.contains(fit.maximum, epsilon=1.0e-9)
            for fit, full in zip(
                self.model_role_intervals_px,
                self.model_full_role_intervals_px,
                strict=True,
            )
        ):
            raise ValueError("sequence full role interval excludes fit interval")
        width_inference = self.frame_width_inference
        if width_inference is not None:
            if (
                not isinstance(
                    width_inference,
                    FrameWidthInferenceAssessment,
                )
                or width_inference.inferred_role_indices
                != self.unbound_role_indices
            ):
                raise ValueError("sequence common-W inference ledger is invalid")
            if width_inference.state == EvidenceState.SUPPORTED:
                assert width_inference.width_px is not None
                assert width_inference.canonical_width_px is not None
                if (
                    self.pitch_fit.frame_width_px
                    != PositiveInterval(
                        width_inference.width_px.minimum,
                        width_inference.width_px.maximum,
                    )
                    or self.pitch_fit.canonical_frame_width_px
                    != width_inference.canonical_width_px
                    or any(
                        self.role_bindings[index // 2 * 2] is None
                        and self.role_bindings[index // 2 * 2 + 1] is None
                        for index in width_inference.inferred_role_indices
                    )
                ):
                    raise ValueError(
                        "supported common-W inference disagrees with sequence"
                    )
        phase_authority_role_count = sum(
            binding is not None
            and binding.use == SequenceBindingUse.PHASE_ANCHOR
            for binding in self.role_bindings
        )
        if (
            not self.independent_support_ids
            or not self.phase_support_locations
            or self.phase_support_count > phase_authority_role_count
        ):
            raise ValueError("sequence independent support ledger is invalid")
        if self.contradicted_observation_count < 0:
            raise ValueError("sequence contradiction count is invalid")
        if (
            not math.isfinite(self.phase_support_coverage)
            or not 0.0
            <= self.phase_support_coverage
            <= self.phase_support_count + 1.0e-9
        ):
            raise ValueError("sequence phase support coverage is invalid")
        if not math.isfinite(self.residual_sum_px) or self.residual_sum_px < 0.0:
            raise ValueError("sequence residual is invalid")
        if tuple(item.relation_ordinal for item in self.local_advance_relations) != tuple(
            range(1, len(self.local_advance_relations) + 1)
        ):
            raise ValueError("local relation ordinals must be contiguous")
        if len(self.local_advance_relations) > max(0, self.template.count - 1):
            raise ValueError("local relations exceed template adjacencies")
        bound_ids = self.bound_observation_ids
        if len(set(bound_ids)) != len(bound_ids):
            raise ValueError("one observation cannot bind multiple template roles")
        direction = self.template.direction
        starts = self.model_role_positions_px[0::2]
        ends = self.model_role_positions_px[1::2]
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
        for role, old_canonical, old_interval, old_full_interval, binding in zip(
            template.roles,
            self.model_role_positions_px,
            self.model_role_intervals_px,
            self.model_full_role_intervals_px,
            self.role_bindings,
            strict=True,
        ):
            canonical = (
                old_canonical
                if role.role == BoundaryRole.START or binding is not None
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
            model_role_positions_px=tuple(canonical_positions),
            model_role_intervals_px=tuple(role_intervals),
            model_full_role_intervals_px=tuple(role_full_intervals),
            role_bindings=self.role_bindings,
            local_advance_relations=self.local_advance_relations,
            contradicted_observation_count=self.contradicted_observation_count,
            residual_sum_px=self.residual_sum_px,
            phase_support_coverage=self.phase_support_coverage,
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
    local_refinement_lookup_count: int
    local_refinement_binding_count: int
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
            self.local_refinement_lookup_count,
            self.local_refinement_binding_count,
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
        if (
            self.local_refinement_binding_count
            > self.role_count * self.fit_pass_count
        ):
            raise ValueError("local refinement bindings exceed template roles")
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
        physical rebind, one bounded local-advance refit, source-pitch rebind,
        and its bounded local-advance refit. The method fails explicitly;
        callers must not truncate.
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
            or self.local_refinement_lookup_count
            > self.observation_count * r * self.fit_pass_count
            or self.phase_offset_lookup_count > max_hypotheses
            or self.separator_lattice_hypothesis_count > max_hypotheses
        ):
            raise ValueError("template indexed work exceeded its structural bound")
