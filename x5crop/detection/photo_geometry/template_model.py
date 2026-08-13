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
from .model import BoundaryRole


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


class PhaseAuthority(str, Enum):
    """How much placement authority a template may consume."""

    DIRECT = "direct"
    FULL_CENTERED = "full_centered"
    PARTIAL_FREE = "partial_free"


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
    phase_authority: PhaseAuthority
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
        if not isinstance(self.phase_authority, PhaseAuthority):
            raise TypeError("template phase authority must be typed")
        if self.direction not in {-1, 1}:
            raise ValueError("template direction must be -1 or +1")
        if self.cross is not None and not self.cross:
            raise ValueError("template cross identity must not be empty")
        if self.pitch_px.maximum < self.frame_width_px.minimum:
            raise ValueError("template pitch cannot be smaller than frame width")
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
    """Typed direct anchor accepted by the pure phase solver.

    A role may be left unbound for a raw ``BoundaryEdgeObservation``.  The
    solver binds it against the indexed theoretical roles exactly once.
    """

    observation_id: ObservationId
    coordinate_interval_px: FiniteInterval
    role: TemplateRole | None = None
    direct: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.observation_id, ObservationId):
            raise TypeError("phase anchor identity must be ObservationId")
        if not isinstance(self.coordinate_interval_px, FiniteInterval):
            raise TypeError("phase anchor coordinate must be FiniteInterval")
        if not isinstance(self.direct, bool):
            raise TypeError("phase anchor direct flag must be boolean")


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
    phase_interval_px: FiniteInterval
    canonical_phase_px: float
    pitch_fit: PitchFit
    canonical_role_positions_px: tuple[float, ...]
    role_positions_px: tuple[FiniteInterval, ...]
    role_observation_ids: tuple[ObservationId | None, ...]
    matched_role_indices: tuple[int, ...]
    inferred_role_indices: tuple[int, ...]
    direct_observation_ids: tuple[ObservationId, ...]
    local_advance_relations: tuple[LocalAdvanceRelation, ...] = ()
    support_count: int = 0
    contradicted_observation_count: int = 0
    residual_sum_px: float = 0.0
    center_compatible: bool = True
    direct_support_fraction: float = 0.0
    polarity_match_count: int = 0

    def __post_init__(self) -> None:
        if not self.phase_interval_px.contains(self.canonical_phase_px, epsilon=1.0e-9):
            raise ValueError("sequence phase is outside its interval")
        if (
            len(self.canonical_role_positions_px) != 2 * self.template.count
            or len(self.role_positions_px) != 2 * self.template.count
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
        expected_roles = set(range(2 * self.template.count))
        matched = set(self.matched_role_indices)
        inferred = set(self.inferred_role_indices)
        if not matched.issubset(expected_roles) or not inferred.issubset(expected_roles):
            raise ValueError("sequence role binding index is invalid")
        if matched & inferred or len(matched) + len(inferred) > len(expected_roles):
            raise ValueError("sequence role binding is not disjoint")
        if self.support_count < 0 or self.support_count != len(matched):
            raise ValueError("sequence support count is inconsistent")
        if self.contradicted_observation_count < 0:
            raise ValueError("sequence contradiction count is invalid")
        if not isinstance(self.center_compatible, bool):
            raise TypeError("sequence center compatibility must be boolean")
        if (
            not math.isfinite(self.direct_support_fraction)
            or self.direct_support_fraction < 0.0
            or self.direct_support_fraction > self.support_count + 1.0e-9
        ):
            raise ValueError("sequence direct support is invalid")
        if not 0 <= self.polarity_match_count <= self.support_count:
            raise ValueError("sequence polarity support is invalid")
        if not math.isfinite(self.residual_sum_px) or self.residual_sum_px < 0.0:
            raise ValueError("sequence residual is invalid")
        if tuple(item.relation_ordinal for item in self.local_advance_relations) != tuple(
            range(1, len(self.local_advance_relations) + 1)
        ):
            raise ValueError("local relation ordinals must be contiguous")
        if len(set(self.direct_observation_ids)) != len(self.direct_observation_ids):
            raise ValueError("sequence direct observations must be unique")
        if any(
            identity is not None and not isinstance(identity, ObservationId)
            for identity in self.role_observation_ids
        ):
            raise TypeError("sequence role observations must be typed identities")

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
    direct_observation_count: int
    inferred_role_count: int
    peak_temporary_bytes: int = 0

    def __post_init__(self) -> None:
        values = (
            self.observation_count,
            self.role_count,
            self.phase_lookup_count,
            self.role_binding_count,
            self.local_relation_evaluation_count,
            self.phase_hypothesis_count,
            self.direct_observation_count,
            self.inferred_role_count,
            self.peak_temporary_bytes,
        )
        if any(not isinstance(value, int) or value < 0 for value in values):
            raise ValueError("template work receipt values must be non-negative integers")
        if self.role_count == 0 and self.role_binding_count:
            raise ValueError("role bindings require roles")
        if self.direct_observation_count > self.observation_count:
            raise ValueError("direct observations exceed registrations")
        if self.inferred_role_count > self.role_count:
            raise ValueError("inferred roles exceed template roles")

    def validate_bounds(
        self,
        *,
        observation_count: int | None = None,
        role_count: int | None = None,
        slot_count: int | None = None,
    ) -> None:
        """Reject any receipt that cannot come from one indexed pass.

        Phase lookup and role binding are each at most ``H * R``.  Local
        relations are per adjacency (``count - 1``), never per candidate
        chain.  The method fails explicitly; callers must not truncate work.
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
        max_hypotheses = h * max(6, r)
        if (
            self.phase_lookup_count > max_hypotheses
            or self.phase_hypothesis_count > max_hypotheses
            or self.role_binding_count > self.phase_hypothesis_count * r
            or self.local_relation_evaluation_count > max(0, slot_count - 1)
        ):
            raise ValueError("template indexed work exceeded its structural bound")


__all__ = [
    "LocalAdvanceKind",
    "LocalAdvanceRelation",
    "PhaseAnchor",
    "PhaseAuthority",
    "PitchFit",
    "SequenceFit",
    "TemplateRole",
    "TemplateSearchReceipt",
    "TemplateSpec",
    "ordered_template_roles",
]
