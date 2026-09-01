"""Small, current-only contracts for indexed photo templates.

The types in this module deliberately stop at a sequence fit.  They do not
own candidate chains, materialisation, crop geometry, or pixel queries.  A
template is a fixed physical rule (frame width, pitch and slot count); direct
observations may calibrate or veto that rule, but never create a second
runtime path.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
import math
from ...domain import EvidenceState, FiniteInterval, ObservationId, PositiveInterval
from .template_nominal_grid_model import CalibratedNominalGridFitState


MAX_TEMPLATE_FIT_PASSES = 6
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
    and cannot authorize an adjacency relation by itself.
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
            <= self.authority.period_px.maximum + 1.0e-9
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


class SeparatorRelationKind(str, Enum):
    """A positive-material separator's departure from nominal pitch."""

    NOMINAL = "nominal"
    NORMAL = "normal"
    WIDE = "wide"
    NARROW = "narrow"


def measured_separator_relation_kind(
    canonical_delta_px: float,
) -> SeparatorRelationKind:
    """Classify one direct separator against the realized nominal Grid."""

    if not math.isfinite(canonical_delta_px):
        raise ValueError("separator adjustment must be finite")
    if abs(canonical_delta_px) <= 1.0e-9:
        return SeparatorRelationKind.NORMAL
    return (
        SeparatorRelationKind.WIDE
        if canonical_delta_px > 0.0
        else SeparatorRelationKind.NARROW
    )


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

class LatticeParameterFitBasis(str, Enum):
    """Most constrained solve used by one continuous placement lineage."""

    TEMPLATE_INTERVAL_CENTER = "template_interval_center"
    CALIBRATED_NOMINAL_GRID = "calibrated_nominal_grid"
    DIRECT_LEAST_SQUARES = "direct_least_squares"
    BOUNDED_DIRECT_LEAST_SQUARES = "bounded_direct_least_squares"


def most_constrained_lattice_parameter_fit_basis(
    *bases: LatticeParameterFitBasis,
) -> LatticeParameterFitBasis:
    """Union continuous-fit provenance without changing evidence authority."""

    if not bases or any(
        not isinstance(basis, LatticeParameterFitBasis) for basis in bases
    ):
        raise TypeError("lattice parameter fit bases must be typed")
    priority = {
        LatticeParameterFitBasis.TEMPLATE_INTERVAL_CENTER: 0,
        LatticeParameterFitBasis.CALIBRATED_NOMINAL_GRID: 1,
        LatticeParameterFitBasis.DIRECT_LEAST_SQUARES: 2,
        LatticeParameterFitBasis.BOUNDED_DIRECT_LEAST_SQUARES: 3,
    }
    return max(bases, key=priority.__getitem__)


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
    validation_only_role_indices: tuple[int, ...] = ()
    validation_observation_ids: tuple[ObservationId, ...] = ()

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
            or tuple(sorted(set(self.validation_only_role_indices)))
            != self.validation_only_role_indices
            or any(index < 0 for index in self.validation_only_role_indices)
            or any(
                index not in self.inferred_role_indices
                for index in self.validation_only_role_indices
            )
            or len(set(self.validation_observation_ids))
            != len(self.validation_observation_ids)
            or any(
                not isinstance(identity, ObservationId)
                for identity in self.validation_observation_ids
            )
            or len(self.validation_only_role_indices)
            != len(self.validation_observation_ids)
            or not set(self.validation_observation_ids).isdisjoint(
                self.observation_ids
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
            or self.validation_only_role_indices
            or self.validation_observation_ids
            or not isinstance(
                self.failure_kind,
                FrameWidthInferenceFailureKind,
            )
        ):
            raise ValueError("unavailable Frame width inference carries authority")


@dataclass(frozen=True)
class SeparatorRelation:
    """One positive-separator adjacency in the shared sequence model.

    A measured relation retains the native positive END -> START gap.  Its
    prefix delta is correlated with the shared ``W`` and ``pitch`` through
    ``signed_gap = pitch - W + delta``; it is never a second free frame width.
    A nominal relation carries no direct measurement and keeps ``delta = 0``.
    A relation at ordinal ``i`` affects slot ``i + 1`` and every later slot
    exactly once.
    """

    relation_ordinal: int
    kind: SeparatorRelationKind
    delta_interval_px: FiniteInterval
    canonical_delta_px: float
    separator_band_observation_id: ObservationId | None = None
    end_edge_observation_id: ObservationId | None = None
    next_start_edge_observation_id: ObservationId | None = None
    signed_gap_interval_px: FiniteInterval | None = None
    canonical_signed_gap_px: float | None = None

    def __post_init__(self) -> None:
        if self.relation_ordinal <= 0:
            raise ValueError("adjacency relation ordinal must be positive")
        if not isinstance(self.kind, SeparatorRelationKind):
            raise TypeError("adjacency relation kind must be typed")
        if not self.delta_interval_px.contains(self.canonical_delta_px, epsilon=1.0e-9):
            raise ValueError(
                "adjacency relation canonical delta is outside interval"
            )
        direct_ids = (
            self.separator_band_observation_id,
            self.end_edge_observation_id,
            self.next_start_edge_observation_id,
        )
        if self.kind == SeparatorRelationKind.NOMINAL and (
            self.delta_interval_px != FiniteInterval.exact(0.0)
            or self.canonical_delta_px != 0.0
            or any(item is not None for item in direct_ids)
            or self.signed_gap_interval_px is not None
            or self.canonical_signed_gap_px is not None
        ):
            raise ValueError(
                "nominal adjacency relation must have zero adjustment"
            )
        if self.kind != SeparatorRelationKind.NOMINAL:
            if (
                any(not isinstance(item, ObservationId) for item in direct_ids)
                or len(set(direct_ids)) != len(direct_ids)
                or self.signed_gap_interval_px is None
                or self.signed_gap_interval_px.minimum <= 0.0
                or self.canonical_signed_gap_px is None
                or not self.signed_gap_interval_px.contains(
                    self.canonical_signed_gap_px,
                    epsilon=1.0e-9,
                )
            ):
                raise ValueError(
                    "measured separator relation needs one positive direct gap"
                )
            if self.kind != measured_separator_relation_kind(
                self.canonical_delta_px
            ):
                raise ValueError(
                    "measured separator kind disagrees with its adjustment"
                )

    @property
    def observation_ids(self) -> tuple[ObservationId, ...]:
        if self.kind == SeparatorRelationKind.NOMINAL:
            return ()
        assert self.separator_band_observation_id is not None
        assert self.end_edge_observation_id is not None
        assert self.next_start_edge_observation_id is not None
        return (
            self.separator_band_observation_id,
            self.end_edge_observation_id,
            self.next_start_edge_observation_id,
        )

    @property
    def is_anomaly(self) -> bool:
        return self.kind in {
            SeparatorRelationKind.WIDE,
            SeparatorRelationKind.NARROW,
        }

    @property
    def is_measured(self) -> bool:
        return self.kind != SeparatorRelationKind.NOMINAL


class ContactRelationKind(str, Enum):
    """Explicit discriminator for the contact branch of the sum type."""

    CONTACT = "contact"


@dataclass(frozen=True)
class ContactRelation:
    """One proven shared physical edge between adjacent Frames.

    ``delta`` remains the prefix projection used by the single sequence
    model.  It is not an independent degree of freedom: every joint feasible
    state additionally enforces ``delta = W - pitch``, which is equivalent to
    ``END(i) == START(i + 1)``.
    """

    relation_ordinal: int
    contact_observation_id: ObservationId
    physical_edge_id: ObservationId
    shared_edge_observation_id: ObservationId
    delta_interval_px: FiniteInterval
    canonical_delta_px: float
    supporting_observation_ids: tuple[ObservationId, ...]
    kind: ContactRelationKind = field(
        init=False,
        default=ContactRelationKind.CONTACT,
    )

    def __post_init__(self) -> None:
        if (
            self.relation_ordinal <= 0
            or self.kind != ContactRelationKind.CONTACT
            or not isinstance(self.contact_observation_id, ObservationId)
            or not isinstance(self.physical_edge_id, ObservationId)
            or not isinstance(self.shared_edge_observation_id, ObservationId)
            or self.physical_edge_id != self.shared_edge_observation_id
            or not self.delta_interval_px.contains(
                self.canonical_delta_px,
                epsilon=1.0e-9,
            )
            or not self.supporting_observation_ids
            or tuple(dict.fromkeys(self.supporting_observation_ids))
            != self.supporting_observation_ids
            or self.physical_edge_id not in self.supporting_observation_ids
            or self.shared_edge_observation_id
            not in self.supporting_observation_ids
            or any(
                not isinstance(identity, ObservationId)
                for identity in self.supporting_observation_ids
            )
        ):
            raise ValueError("contact relation is invalid")

    @property
    def observation_ids(self) -> tuple[ObservationId, ...]:
        return self.supporting_observation_ids

    @property
    def is_anomaly(self) -> bool:
        return True


class OverlapRelationKind(str, Enum):
    """Explicit discriminator for the overlap branch of the sum type."""

    OVERLAP = "overlap"


@dataclass(frozen=True)
class OverlapRelation:
    """One proven reversed END/START pair between adjacent Frames.

    ``signed_gap_interval_px`` is strictly negative in template direction.
    ``delta`` is not an independent degree of freedom: every feasible state
    enforces ``delta - W + pitch`` inside that directly measured interval.
    """

    relation_ordinal: int
    overlap_observation_id: ObservationId
    end_edge_observation_id: ObservationId
    next_start_edge_observation_id: ObservationId
    signed_gap_interval_px: FiniteInterval
    canonical_signed_gap_px: float
    delta_interval_px: FiniteInterval
    canonical_delta_px: float
    supporting_observation_ids: tuple[ObservationId, ...]
    kind: OverlapRelationKind = field(
        init=False,
        default=OverlapRelationKind.OVERLAP,
    )

    def __post_init__(self) -> None:
        if (
            self.relation_ordinal <= 0
            or self.kind != OverlapRelationKind.OVERLAP
            or not isinstance(self.overlap_observation_id, ObservationId)
            or not isinstance(self.end_edge_observation_id, ObservationId)
            or not isinstance(
                self.next_start_edge_observation_id,
                ObservationId,
            )
            or self.end_edge_observation_id
            == self.next_start_edge_observation_id
            or self.signed_gap_interval_px.maximum >= 0.0
            or not self.signed_gap_interval_px.contains(
                self.canonical_signed_gap_px,
                epsilon=1.0e-9,
            )
            or not self.delta_interval_px.contains(
                self.canonical_delta_px,
                epsilon=1.0e-9,
            )
            or self.supporting_observation_ids
            != (
                self.end_edge_observation_id,
                self.next_start_edge_observation_id,
            )
        ):
            raise ValueError("overlap relation is invalid")

    @property
    def observation_ids(self) -> tuple[ObservationId, ...]:
        return self.supporting_observation_ids

    @property
    def is_anomaly(self) -> bool:
        return True


AdjacencyRelation = SeparatorRelation | ContactRelation | OverlapRelation


def adjacency_relation_evidence_identity(
    relation: AdjacencyRelation,
) -> tuple[object, ...]:
    """Return the direct physical fact preserved across correlated refits."""

    if isinstance(relation, SeparatorRelation):
        return (
            "separator_nominal" if not relation.is_measured else "separator",
            relation.relation_ordinal,
            relation.observation_ids,
            relation.signed_gap_interval_px,
        )
    if isinstance(relation, ContactRelation):
        return (
            "contact",
            relation.relation_ordinal,
            relation.contact_observation_id,
            relation.physical_edge_id,
            relation.shared_edge_observation_id,
            relation.supporting_observation_ids,
        )
    return (
        "overlap",
        relation.relation_ordinal,
        relation.overlap_observation_id,
        relation.end_edge_observation_id,
        relation.next_start_edge_observation_id,
        relation.signed_gap_interval_px,
        relation.supporting_observation_ids,
    )


def adjacency_prefix_coefficients(
    relations: tuple[AdjacencyRelation, ...],
    slot_index: int,
) -> tuple[int, int, float]:
    """Return ``W``, pitch and measured-gap coefficients for one slot.

    Every directly measured adjacency contributes ``W - pitch`` exactly once,
    plus its measured signed gap.  Nominal unobserved adjacency contributes
    the ordinary pitch term.  This is the canonical algebra shared by phase
    fitting and rank accounting.
    """

    if slot_index < 0:
        raise ValueError("adjacency prefix slot must be non-negative")
    applicable = relations[: min(slot_index, len(relations))]
    measured_count = sum(
        isinstance(item, (ContactRelation, OverlapRelation))
        or (
            isinstance(item, SeparatorRelation)
            and item.kind != SeparatorRelationKind.NOMINAL
        )
        for item in applicable
    )
    fixed_delta = sum(
        item.canonical_signed_gap_px
        if isinstance(item, SeparatorRelation)
        and item.kind != SeparatorRelationKind.NOMINAL
        else item.canonical_signed_gap_px
        if isinstance(item, OverlapRelation)
        else 0.0
        for item in applicable
    )
    return measured_count, slot_index - measured_count, fixed_delta


def realize_adjacency_relations(
    relations: tuple[AdjacencyRelation, ...],
    *,
    frame_width_interval_px: FiniteInterval,
    pitch_interval_px: FiniteInterval,
    frame_width_px: float,
    pitch_px: float,
) -> tuple[AdjacencyRelation, ...]:
    """Bind every measured delta to one shared W/pitch authority and state."""

    contact_delta = frame_width_px - pitch_px
    contact_interval = FiniteInterval(
        frame_width_interval_px.minimum - pitch_interval_px.maximum,
        frame_width_interval_px.maximum - pitch_interval_px.minimum,
    )
    realized: list[AdjacencyRelation] = []
    for relation in relations:
        if isinstance(relation, ContactRelation):
            realized.append(
                replace(
                    relation,
                    delta_interval_px=contact_interval,
                    canonical_delta_px=contact_delta,
                )
            )
            continue
        if isinstance(relation, SeparatorRelation) and relation.is_measured:
            assert relation.canonical_signed_gap_px is not None
            assert relation.signed_gap_interval_px is not None
            delta = contact_delta + relation.canonical_signed_gap_px
            delta_interval = FiniteInterval(
                relation.signed_gap_interval_px.minimum
                + frame_width_interval_px.minimum
                - pitch_interval_px.maximum,
                relation.signed_gap_interval_px.maximum
                + frame_width_interval_px.maximum
                - pitch_interval_px.minimum,
            )
            realized.append(
                replace(
                    relation,
                    kind=measured_separator_relation_kind(delta),
                    delta_interval_px=delta_interval,
                    canonical_delta_px=delta,
                )
            )
            continue
        if isinstance(relation, OverlapRelation):
            delta_interval = FiniteInterval(
                relation.signed_gap_interval_px.minimum
                + frame_width_interval_px.minimum
                - pitch_interval_px.maximum,
                relation.signed_gap_interval_px.maximum
                + frame_width_interval_px.maximum
                - pitch_interval_px.minimum,
            )
            realized.append(
                replace(
                    relation,
                    delta_interval_px=delta_interval,
                    canonical_delta_px=(
                        contact_delta + relation.canonical_signed_gap_px
                    ),
                )
            )
            continue
        realized.append(relation)
    return tuple(realized)


def adjacency_relation_required_bindings(
    relations: tuple[AdjacencyRelation, ...],
) -> tuple[tuple[int, ObservationId], ...]:
    """Return direct role atoms required by every measured relation."""

    return tuple(
        binding
        for relation in relations
        if isinstance(relation, (ContactRelation, OverlapRelation))
        or (
            isinstance(relation, SeparatorRelation)
            and relation.kind != SeparatorRelationKind.NOMINAL
        )
        for binding in (
            (
                2 * relation.relation_ordinal - 1,
                relation.shared_edge_observation_id
                if isinstance(relation, ContactRelation)
                else relation.end_edge_observation_id,
            ),
            (
                2 * relation.relation_ordinal,
                relation.shared_edge_observation_id
                if isinstance(relation, ContactRelation)
                else relation.next_start_edge_observation_id,
            ),
        )
    )


def realize_adjacency_relations_at_role_positions(
    relations: tuple[AdjacencyRelation, ...],
    *,
    model_role_positions_px: tuple[float, ...],
    direction: int,
    frame_width_px: float,
    pitch_px: float,
) -> tuple[AdjacencyRelation, ...]:
    """Bind measured adjacency values to one realized continuous state."""

    if direction not in {-1, 1}:
        raise ValueError("topology realization direction is invalid")
    realized: list[AdjacencyRelation] = []
    for relation in relations:
        measured_separator = (
            isinstance(relation, SeparatorRelation)
            and relation.kind != SeparatorRelationKind.NOMINAL
        )
        if (
            not isinstance(relation, (ContactRelation, OverlapRelation))
            and not measured_separator
        ):
            realized.append(relation)
            continue
        end_index = 2 * relation.relation_ordinal - 1
        start_index = 2 * relation.relation_ordinal
        if start_index >= len(model_role_positions_px):
            raise ValueError("topology relation leaves its role ledger")
        signed_gap = direction * (
            model_role_positions_px[start_index]
            - model_role_positions_px[end_index]
        )
        if isinstance(relation, ContactRelation):
            if abs(signed_gap) > 1.0e-7:
                raise ValueError("contact realization lost its shared coordinate")
            realized.append(
                replace(
                    relation,
                    canonical_delta_px=frame_width_px - pitch_px,
                )
            )
            continue
        canonical_delta = frame_width_px - pitch_px + signed_gap
        assert relation.signed_gap_interval_px is not None
        if (
            not relation.signed_gap_interval_px.contains(
                signed_gap,
                epsilon=1.0e-7,
            )
            or not relation.delta_interval_px.contains(
                canonical_delta,
                epsilon=1.0e-7,
            )
        ):
            raise ValueError("adjacency realization left its measured interval")
        if measured_separator:
            assert isinstance(relation, SeparatorRelation)
            realized.append(
                replace(
                    relation,
                    kind=measured_separator_relation_kind(canonical_delta),
                    canonical_signed_gap_px=signed_gap,
                    canonical_delta_px=canonical_delta,
                )
            )
        else:
            realized.append(
                replace(
                    relation,
                    canonical_signed_gap_px=signed_gap,
                    canonical_delta_px=canonical_delta,
                )
            )
    return tuple(realized)


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
    evidence_group_id: ObservationId
    canonical_position_px: float
    fit_position_interval_px: FiniteInterval
    full_position_interval_px: FiniteInterval
    line_evidence: SequenceRoleLineEvidence | None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.use, SequenceBindingUse)
            or not isinstance(self.observation_id, ObservationId)
            or not isinstance(self.evidence_group_id, ObservationId)
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
    lattice_parameter_fit_basis: LatticeParameterFitBasis
    model_role_positions_px: tuple[float, ...]
    model_role_intervals_px: tuple[FiniteInterval, ...]
    model_full_role_intervals_px: tuple[FiniteInterval, ...]
    role_bindings: tuple[SequenceRoleBinding | None, ...]
    calibrated_nominal_grid_fit_state: (
        CalibratedNominalGridFitState | None
    ) = None
    frame_width_inference: FrameWidthInferenceAssessment | None = None
    adjacency_relations: tuple[AdjacencyRelation, ...] = ()
    contradicted_observation_count: int = 0
    residual_sum_px: float = 0.0
    phase_support_coverage: float = 0.0

    @property
    def bound_observation_ids(self) -> tuple[ObservationId, ...]:
        return tuple(
            dict.fromkeys(
                binding.observation_id
                for binding in self.role_bindings
                if binding is not None
            )
        )

    @property
    def evidence_group_ids(self) -> tuple[ObservationId, ...]:
        return tuple(
            sorted(
                {
                    binding.evidence_group_id
                    for binding in self.role_bindings
                    if binding is not None
                }
            )
        )

    @property
    def phase_anchor_observation_ids(self) -> tuple[ObservationId, ...]:
        return tuple(
            dict.fromkeys(
                binding.observation_id
                for binding in self.role_bindings
                if binding is not None
                and binding.use == SequenceBindingUse.PHASE_ANCHOR
            )
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

    @property
    def completely_unobserved_frame_ordinals(self) -> tuple[int, ...]:
        """Frames whose START and END both come only from the Grid model."""

        return tuple(
            ordinal
            for ordinal, (start, end) in enumerate(
                zip(
                    self.role_bindings[0::2],
                    self.role_bindings[1::2],
                    strict=True,
                ),
                start=1,
            )
            if start is None and end is None
        )

    def __post_init__(self) -> None:
        if not isinstance(
            self.lattice_parameter_fit_basis,
            LatticeParameterFitBasis,
        ):
            raise TypeError("sequence lattice fit basis must be typed")
        if (
            not isinstance(self.phase_lattice_fit, PhaseLatticeFit)
            or self.phase_lattice_fit.authority
            != self.template.phase_lattice_authority
            or self.phase_lattice_fit.direction != self.template.direction
        ):
            raise ValueError("sequence phase lattice disagrees with template")
        if (
            self.calibrated_nominal_grid_fit_state is not None
            and not isinstance(
                self.calibrated_nominal_grid_fit_state,
                CalibratedNominalGridFitState,
            )
        ):
            raise TypeError("sequence nominal Grid fit state is invalid")
        if (
            self.lattice_parameter_fit_basis
            == LatticeParameterFitBasis.CALIBRATED_NOMINAL_GRID
        ) != (self.calibrated_nominal_grid_fit_state is not None):
            raise ValueError("sequence nominal Grid basis and state disagree")
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
                    or self.completely_unobserved_frame_ordinals
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
            not self.evidence_group_ids
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
        if tuple(item.relation_ordinal for item in self.adjacency_relations) != tuple(
            range(1, len(self.adjacency_relations) + 1)
        ):
            raise ValueError(
                "adjacency relation ordinals must be contiguous"
            )
        if len(self.adjacency_relations) > max(0, self.template.count - 1):
            raise ValueError(
                "adjacency relations exceed template adjacencies"
            )
        roles_by_observation: dict[ObservationId, list[int]] = {}
        for role_index, binding in enumerate(self.role_bindings):
            if binding is not None:
                roles_by_observation.setdefault(
                    binding.observation_id,
                    [],
                ).append(role_index)
        contacts = {
            item.shared_edge_observation_id: item
            for item in self.adjacency_relations
            if isinstance(item, ContactRelation)
        }
        if len(contacts) != sum(
            isinstance(item, ContactRelation)
            for item in self.adjacency_relations
        ):
            raise ValueError("one physical edge cannot prove two contacts")
        overlap_ids = tuple(
            item.overlap_observation_id
            for item in self.adjacency_relations
            if isinstance(item, OverlapRelation)
        )
        if len(set(overlap_ids)) != len(overlap_ids):
            raise ValueError("one overlap observation cannot prove two relations")
        for identity, role_indices in roles_by_observation.items():
            if len(role_indices) == 1:
                continue
            contact = contacts.get(identity)
            expected = (
                2 * contact.relation_ordinal - 1,
                2 * contact.relation_ordinal,
            ) if contact is not None else ()
            if tuple(role_indices) != expected:
                raise ValueError(
                    "one observation may bind only one proven adjacent contact"
                )
            left = self.role_bindings[expected[0]]
            right = self.role_bindings[expected[1]]
            assert left is not None and right is not None
            if (
                left.evidence_group_id != contact.physical_edge_id
                or right.evidence_group_id != contact.physical_edge_id
                or abs(
                    left.canonical_position_px
                    - right.canonical_position_px
                )
                > 1.0e-9
            ):
                raise ValueError("contact bindings lost their shared edge")
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
        for relation in self.adjacency_relations:
            end_index = 2 * relation.relation_ordinal - 1
            start_index = 2 * relation.relation_ordinal
            end_binding = self.role_bindings[end_index]
            start_binding = self.role_bindings[start_index]
            end = self.model_role_positions_px[end_index]
            next_start = self.model_role_positions_px[start_index]
            if isinstance(relation, ContactRelation):
                if (
                    end_binding is None
                    or start_binding is None
                    or end_binding.observation_id
                    != relation.shared_edge_observation_id
                    or start_binding.observation_id
                    != relation.shared_edge_observation_id
                    or abs(end - next_start) > 1.0e-7
                ):
                    raise ValueError(
                        "contact relation does not share one coordinate"
                    )
                continue
            measured_separator = (
                isinstance(relation, SeparatorRelation)
                and relation.kind != SeparatorRelationKind.NOMINAL
            )
            if not isinstance(relation, OverlapRelation) and not measured_separator:
                continue
            signed_gap = direction * (next_start - end)
            expected_delta = (
                self.pitch_fit.canonical_frame_width_px
                - self.pitch_fit.canonical_pitch_px
                + signed_gap
            )
            expected_end_id = relation.end_edge_observation_id
            expected_start_id = relation.next_start_edge_observation_id
            assert relation.signed_gap_interval_px is not None
            assert relation.canonical_signed_gap_px is not None
            if (
                end_binding is None
                or start_binding is None
                or end_binding.observation_id
                != expected_end_id
                or start_binding.observation_id
                != expected_start_id
                or end_binding.evidence_group_id
                == start_binding.evidence_group_id
                and isinstance(relation, OverlapRelation)
                or not relation.signed_gap_interval_px.contains(
                    signed_gap,
                    epsilon=1.0e-7,
                )
                or abs(signed_gap - relation.canonical_signed_gap_px) > 1.0e-7
                or abs(expected_delta - relation.canonical_delta_px) > 1.0e-7
            ):
                raise ValueError(
                    "measured adjacency lost its direct edge geometry"
                )
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
    adjacency_relation_evaluation_count: int
    local_refinement_lookup_count: int
    local_refinement_binding_count: int
    phase_hypothesis_count: int
    phase_offset_lookup_count: int
    direct_observation_count: int
    inferred_role_count: int
    peak_temporary_bytes: int = 0
    fit_pass_count: int = 1
    separator_lattice_hypothesis_count: int = 0
    candidate_direct_role_authority_evaluation_count: int = 0
    candidate_direct_role_authority_terminal_count: int = 0
    candidate_direct_role_authority_role_check_count: int = 0
    candidate_direct_role_projection_evaluation_count: int = 0
    candidate_direct_role_projection_success_count: int = 0
    candidate_direct_role_projection_binding_count: int = 0
    candidate_nominal_grid_solve_count: int = 0
    candidate_nominal_grid_solve_success_count: int = 0

    def __post_init__(self) -> None:
        values = (
            self.observation_count,
            self.role_count,
            self.phase_lookup_count,
            self.role_binding_count,
            self.adjacency_relation_evaluation_count,
            self.local_refinement_lookup_count,
            self.local_refinement_binding_count,
            self.phase_hypothesis_count,
            self.phase_offset_lookup_count,
            self.direct_observation_count,
            self.inferred_role_count,
            self.peak_temporary_bytes,
            self.fit_pass_count,
            self.separator_lattice_hypothesis_count,
            self.candidate_direct_role_authority_evaluation_count,
            self.candidate_direct_role_authority_terminal_count,
            self.candidate_direct_role_authority_role_check_count,
            self.candidate_direct_role_projection_evaluation_count,
            self.candidate_direct_role_projection_success_count,
            self.candidate_direct_role_projection_binding_count,
            self.candidate_nominal_grid_solve_count,
            self.candidate_nominal_grid_solve_success_count,
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
        if (
            self.candidate_direct_role_authority_terminal_count
            > self.candidate_direct_role_authority_evaluation_count
            or self.candidate_direct_role_authority_evaluation_count
            > self.phase_hypothesis_count
            or self.candidate_direct_role_authority_role_check_count
            > self.role_binding_count
            or self.candidate_direct_role_projection_success_count
            > self.candidate_direct_role_projection_evaluation_count
            or self.candidate_direct_role_projection_evaluation_count
            != self.candidate_direct_role_authority_evaluation_count
            or self.candidate_direct_role_projection_binding_count
            > self.candidate_direct_role_authority_role_check_count
            or self.candidate_direct_role_authority_terminal_count
            + self.candidate_direct_role_projection_success_count
            > self.candidate_direct_role_projection_evaluation_count
            or self.candidate_nominal_grid_solve_success_count
            > self.candidate_nominal_grid_solve_count
            or self.candidate_nominal_grid_solve_count
            > self.candidate_direct_role_projection_evaluation_count
        ):
            raise ValueError("phase-candidate authority work is inconsistent")

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
        pass, never per candidate chain.  Six passes cover provisional fit,
        source-pitch hypothesis and physical rebind, one bounded adjacency
        refit, and one selected source-W native-role refinement.  The method
        fails explicitly; callers must not truncate.
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
            or self.adjacency_relation_evaluation_count
            > max(0, slot_count - 1) * self.fit_pass_count
            or self.local_refinement_lookup_count
            > self.observation_count * r * self.fit_pass_count
            or self.phase_offset_lookup_count > max_hypotheses
            or self.separator_lattice_hypothesis_count > max_hypotheses
        ):
            raise ValueError("template indexed work exceeded its structural bound")
