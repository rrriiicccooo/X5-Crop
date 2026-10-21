"""Replayable holder and source-domain admission facts for one phase member."""

from __future__ import annotations

from dataclasses import dataclass
import math

from ...domain import FiniteInterval, ObservationId
from .template_model import SequenceFit
from .template_source_domain import PhaseSourceDomain


def _strict_bool(value: object, name: str) -> None:
    if type(value) is not bool:
        raise TypeError(f"{name} must be a bool")


def _strict_role_count(role_count: object) -> int:
    if type(role_count) is not int:
        raise TypeError("phase admission role count must be an integer")
    if role_count <= 0 or role_count % 2:
        raise ValueError("phase admission role count must be a positive even integer")
    return role_count


def admission_proof_work_bound(role_count: int) -> int:
    """Return the fixed role-sized work bound for an admission proof."""

    return 6 * _strict_role_count(role_count)


def admission_proof_bytes_bound(role_count: int) -> int:
    """Return the fixed temporary-byte bound for an admission proof."""

    return 2048 + 512 * _strict_role_count(role_count)


def _validate_positions(
    positions: object,
    *,
    expected_length: int | None = None,
    name: str,
) -> tuple[float, ...]:
    if not isinstance(positions, tuple):
        raise TypeError(f"{name} must be a tuple")
    if expected_length is not None and len(positions) != expected_length:
        raise ValueError(f"{name} length disagrees with the role count")
    if not positions or len(positions) % 2:
        raise ValueError(f"{name} must contain a positive even role count")
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in positions):
        raise TypeError(f"{name} must contain finite numbers")
    return positions


def _validate_terminal_indices(
    indices: object,
    *,
    role_count: int,
    name: str,
) -> tuple[int, ...]:
    if not isinstance(indices, tuple):
        raise TypeError(f"{name} must be a tuple")
    if any(type(index) is not int for index in indices):
        raise TypeError(f"{name} must contain integers")
    if tuple(sorted(set(indices))) != indices:
        raise ValueError(f"{name} must be sorted and unique")
    if any(index not in (0, role_count - 1) for index in indices):
        raise ValueError(f"{name} must contain only terminal role indices")
    return indices


@dataclass(frozen=True)
class HolderModelRangeViolation:
    """A failed model coordinate with its own native input, when present.

    A binding is recorded evidence, not independent coordinate authority.
    Neither its presence nor source-terminal classification grants admission.
    """

    role_index: int
    model_coordinate_px: float
    observation_id: ObservationId | None
    native_canonical_coordinate_px: float | None
    native_full_interval_px: FiniteInterval | None
    source_terminal_clipped: bool

    def __post_init__(self):
        if (type(self.role_index) is not int or self.role_index < 0
                or type(self.model_coordinate_px) not in (int, float)
                or not math.isfinite(self.model_coordinate_px)
                or type(self.source_terminal_clipped) is not bool):
            raise ValueError("holder range violation lost its model input")
        if self.observation_id is None:
            if self.native_canonical_coordinate_px is not None or self.native_full_interval_px is not None:
                raise ValueError("unbound holder role cannot invent a native coordinate")
        elif (not isinstance(self.observation_id, ObservationId)
                or type(self.native_canonical_coordinate_px) not in (int, float)
                or not math.isfinite(self.native_canonical_coordinate_px)
                or not isinstance(self.native_full_interval_px, FiniteInterval)
                or not self.native_full_interval_px.contains(self.native_canonical_coordinate_px, epsilon=1.0e-9)):
            raise ValueError("holder range violation lost its native binding")


def _holder_violations(fit, holder_span_px, slack, terminals):
    if holder_span_px is None:
        return ()
    return tuple(HolderModelRangeViolation(i, coordinate,
        None if b is None else b.observation_id,
        None if b is None else b.canonical_position_px,
        None if b is None else b.full_position_interval_px, i in terminals)
        for i, (coordinate, b) in enumerate(zip(fit.model_role_positions_px, fit.role_bindings, strict=True))
        if coordinate < holder_span_px.minimum - slack or coordinate > holder_span_px.maximum + slack)


@dataclass(frozen=True)
class PhaseMemberAdmissionProof:
    """The minimal raw/current geometry facts needed to replay admission."""

    template_id: str
    direction: int
    holder_span_px: FiniteInterval | None
    holder_slack_px: float
    source_domain: PhaseSourceDomain | None
    original_model_role_positions_px: tuple[float, ...]
    current_model_role_positions_px: tuple[float, ...]
    original_holder_admitted: bool
    current_holder_admitted: bool
    original_source_domain_admitted: bool | None
    current_source_domain_admitted: bool | None
    original_source_terminal_role_indices: tuple[int, ...]
    current_source_terminal_role_indices: tuple[int, ...]
    original_holder_violations: tuple[HolderModelRangeViolation, ...] = ()
    current_holder_violations: tuple[HolderModelRangeViolation, ...] = ()

    def __post_init__(self) -> None:
        if type(self.template_id) is not str or not self.template_id:
            raise TypeError("phase admission template identity must be a non-empty string")
        if type(self.direction) is not int or self.direction not in {-1, 1}:
            raise ValueError("phase admission direction must be -1 or +1")
        if self.holder_span_px is not None and not isinstance(
            self.holder_span_px, FiniteInterval
        ):
            raise TypeError("phase admission holder span must be a finite interval")
        if type(self.holder_slack_px) is not float or not math.isfinite(self.holder_slack_px):
            raise TypeError("phase admission holder slack must be a finite float")
        if self.holder_slack_px < 0.0:
            raise ValueError("phase admission holder slack must be non-negative")
        if self.source_domain is not None and not isinstance(
            self.source_domain, PhaseSourceDomain
        ):
            raise TypeError("phase admission source domain must be typed")

        original_positions = _validate_positions(
            self.original_model_role_positions_px,
            name="original model role positions",
        )
        current_positions = _validate_positions(
            self.current_model_role_positions_px,
            expected_length=len(original_positions),
            name="current model role positions",
        )
        role_count = len(original_positions)
        _validate_terminal_indices(
            self.original_source_terminal_role_indices,
            role_count=role_count,
            name="original source terminal role indices",
        )
        _validate_terminal_indices(
            self.current_source_terminal_role_indices,
            role_count=role_count,
            name="current source terminal role indices",
        )
        _strict_bool(self.original_holder_admitted, "original holder admission")
        _strict_bool(self.current_holder_admitted, "current holder admission")
        for positions, admitted, terminals, violations in (
            (original_positions, self.original_holder_admitted, self.original_source_terminal_role_indices,
             self.original_holder_violations),
            (current_positions, self.current_holder_admitted, self.current_source_terminal_role_indices,
             self.current_holder_violations),
        ):
            expected = (() if self.holder_span_px is None else tuple(i for i, p in enumerate(positions)
                if p < self.holder_span_px.minimum - self.holder_slack_px
                or p > self.holder_span_px.maximum + self.holder_slack_px))
            if (not isinstance(violations, tuple)
                    or tuple(v.role_index for v in violations) != expected
                    or admitted != (not expected)
                    or any(v.model_coordinate_px != positions[v.role_index]
                           or v.source_terminal_clipped != (v.role_index in terminals) for v in violations)):
                raise ValueError("holder admission omitted or changed a failing model role")
        for value, name in (
            (self.original_source_domain_admitted, "original source-domain admission"),
            (self.current_source_domain_admitted, "current source-domain admission"),
        ):
            if value is not None:
                _strict_bool(value, name)

        if self.source_domain is None:
            if (
                self.original_source_domain_admitted is not None
                or self.current_source_domain_admitted is not None
                or self.original_source_terminal_role_indices
                or self.current_source_terminal_role_indices
            ):
                raise ValueError(
                    "source-domain facts must be empty when no source domain is present"
                )
        elif (
            self.original_source_domain_admitted is None
            or self.current_source_domain_admitted is None
        ):
            raise TypeError(
                "source-domain facts require bool admission states"
            )

    def matches_inputs(
        self,
        original: SequenceFit,
        current: SequenceFit,
        holder_span_px: FiniteInterval | None,
        source_domain: PhaseSourceDomain | None,
    ) -> bool:
        """Return whether this proof is bound to the supplied fit inputs."""

        if not isinstance(original, SequenceFit) or not isinstance(current, SequenceFit):
            return False
        if holder_span_px is not None and not isinstance(holder_span_px, FiniteInterval):
            return False
        if source_domain is not None and not isinstance(source_domain, PhaseSourceDomain):
            return False
        if (
            original.template.template_id != self.template_id
            or current.template.template_id != self.template_id
            or original.template.direction != self.direction
            or current.template.direction != self.direction
            or tuple(original.model_role_positions_px)
            != self.original_model_role_positions_px
            or tuple(current.model_role_positions_px)
            != self.current_model_role_positions_px
            or holder_span_px != self.holder_span_px
            or source_domain != self.source_domain
        ):
            return False
        original_slack = (
            original.template.frame_width_px.minimum
            + original.template.frame_width_px.maximum
        ) * 0.02
        current_slack = (
            current.template.frame_width_px.minimum
            + current.template.frame_width_px.maximum
        ) * 0.02
        return (
            self.holder_slack_px == original_slack
            and self.holder_slack_px == current_slack
            and self.original_holder_violations == _holder_violations(
                original, holder_span_px, original_slack, self.original_source_terminal_role_indices)
            and self.current_holder_violations == _holder_violations(
                current, holder_span_px, current_slack, self.current_source_terminal_role_indices)
        )

    def matches_original_fit(self, fit: SequenceFit) -> bool:
        return (fit.template.template_id == self.template_id and fit.template.direction == self.direction
            and fit.model_role_positions_px == self.original_model_role_positions_px
            and self.original_holder_violations == _holder_violations(
                fit, self.holder_span_px, self.holder_slack_px, self.original_source_terminal_role_indices))

    def matches_current_fit(self, fit: SequenceFit) -> bool:
        return (fit.template.template_id == self.template_id and fit.template.direction == self.direction
            and fit.model_role_positions_px == self.current_model_role_positions_px
            and self.current_holder_violations == _holder_violations(
                fit, self.holder_span_px, self.holder_slack_px, self.current_source_terminal_role_indices))


def assess_phase_member_admission(
    original_fit: SequenceFit,
    current_fit: SequenceFit,
    *,
    holder_span_px: FiniteInterval | None,
    source_domain: PhaseSourceDomain | None,
) -> PhaseMemberAdmissionProof:
    """Build a replayable admission fact record without changing admission."""

    if not isinstance(original_fit, SequenceFit) or not isinstance(
        current_fit, SequenceFit
    ):
        raise TypeError("phase admission requires typed sequence fits")
    if original_fit.template != current_fit.template:
        raise ValueError("phase admission fits must use the same template")
    if len(original_fit.role_bindings) != len(current_fit.role_bindings):
        raise ValueError("phase admission fits must have the same role count")
    if original_fit.template.direction != current_fit.template.direction:
        raise ValueError("phase admission fits must use the same direction")
    if holder_span_px is not None and not isinstance(holder_span_px, FiniteInterval):
        raise TypeError("phase admission holder span must be a finite interval")
    if source_domain is not None and not isinstance(source_domain, PhaseSourceDomain):
        raise TypeError("phase admission source domain must be typed")

    # These imports stay local so this proof owner cannot create a module cycle
    # if the phase competition owner later consumes the proof as a report fact.
    from .template_phase_competition import _candidate_respects_holder
    from .template_source_domain import source_clipped_terminal_roles

    role_count = len(original_fit.role_bindings)
    _strict_role_count(role_count)
    holder_slack_px = (
        original_fit.template.frame_width_px.minimum
        + original_fit.template.frame_width_px.maximum
    ) * 0.02
    original_holder_admitted = _candidate_respects_holder(
        original_fit,
        holder_span_px=holder_span_px,
        holder_slack_px=holder_slack_px,
    )
    current_holder_admitted = _candidate_respects_holder(
        current_fit,
        holder_span_px=holder_span_px,
        holder_slack_px=holder_slack_px,
    )
    if source_domain is None:
        original_source_domain_admitted = None
        current_source_domain_admitted = None
        original_terminals = ()
        current_terminals = ()
    else:
        original_terminal_result = source_clipped_terminal_roles(
            original_fit, source_domain
        )
        current_terminal_result = source_clipped_terminal_roles(
            current_fit, source_domain
        )
        original_source_domain_admitted = original_terminal_result is not None
        current_source_domain_admitted = current_terminal_result is not None
        original_terminals = (
            () if original_terminal_result is None else tuple(original_terminal_result)
        )
        current_terminals = (
            () if current_terminal_result is None else tuple(current_terminal_result)
        )
    return PhaseMemberAdmissionProof(
        template_id=original_fit.template.template_id,
        direction=original_fit.template.direction,
        holder_span_px=holder_span_px,
        holder_slack_px=holder_slack_px,
        source_domain=source_domain,
        original_model_role_positions_px=tuple(original_fit.model_role_positions_px),
        current_model_role_positions_px=tuple(current_fit.model_role_positions_px),
        original_holder_admitted=original_holder_admitted,
        current_holder_admitted=current_holder_admitted,
        original_source_domain_admitted=original_source_domain_admitted,
        current_source_domain_admitted=current_source_domain_admitted,
        original_source_terminal_role_indices=original_terminals,
        current_source_terminal_role_indices=current_terminals,
        original_holder_violations=_holder_violations(original_fit, holder_span_px, holder_slack_px, original_terminals),
        current_holder_violations=_holder_violations(current_fit, holder_span_px, holder_slack_px, current_terminals),
    )
