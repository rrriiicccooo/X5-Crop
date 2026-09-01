"""Authorize partial-height sequence edges inside one resolved aperture domain."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from ...domain import EvidenceState, FiniteInterval, ObservationId
from .output_model import OutputBoundaryUse
from .template_cross_model import CrossFit
from .template_direct_role_authority import (
    DirectRoleAuthorityBasis,
    DirectRoleAuthorityFact,
    DirectRoleBindingAuthority,
)
from .template_model import SequenceFit
from .trace_support import PIXEL_CENTER_HALF_EXTENT_PX


class DirectRoleApertureDomainBasis(str, Enum):
    """The two-sided short-axis fact that owns one aperture domain."""

    DIRECT_APERTURE_PAIR = "direct_aperture_pair"
    ENCLOSING_SUPPORT_APERTURE = "enclosing_support_aperture"


class DirectRoleApertureDomainFailureKind(str, Enum):
    """Why a partial-height long edge cannot use the resolved cross fit."""

    TWO_SIDED_CROSS_DOMAIN_UNAVAILABLE = (
        "two_sided_cross_domain_unavailable"
    )
    APERTURE_DOMAIN_COLLAPSED = "aperture_domain_collapsed"
    SUPPORT_OUTSIDE_APERTURE_DOMAIN = "support_outside_aperture_domain"


@dataclass(frozen=True)
class DirectRoleApertureDomainFact:
    """Containment of one partial-height edge over all feasible cross states."""

    role_index: int
    observation_id: ObservationId
    role_position_interval_px: FiniteInterval
    support_trace_interval_px: FiniteInterval
    guaranteed_aperture_interval_px: FiniteInterval | None
    basis: DirectRoleApertureDomainBasis | None
    cross_observation_ids: tuple[ObservationId, ...]
    state: EvidenceState
    failure_kind: DirectRoleApertureDomainFailureKind | None

    def __post_init__(self) -> None:
        supported = self.state == EvidenceState.SUPPORTED
        contradicted = self.state == EvidenceState.CONTRADICTED
        unavailable = self.state == EvidenceState.UNAVAILABLE
        domain = self.guaranteed_aperture_interval_px
        contained = bool(
            domain is not None
            and domain.contains(
                self.support_trace_interval_px.minimum,
                epsilon=1.0e-9,
            )
            and domain.contains(
                self.support_trace_interval_px.maximum,
                epsilon=1.0e-9,
            )
        )
        has_cross_domain = self.basis is not None and bool(
            self.cross_observation_ids
        )
        collapsed = (
            self.failure_kind
            == DirectRoleApertureDomainFailureKind.APERTURE_DOMAIN_COLLAPSED
        )
        outside = (
            self.failure_kind
            == DirectRoleApertureDomainFailureKind.SUPPORT_OUTSIDE_APERTURE_DOMAIN
        )
        if (
            self.role_index < 0
            or not isinstance(self.observation_id, ObservationId)
            or not isinstance(self.role_position_interval_px, FiniteInterval)
            or not isinstance(self.support_trace_interval_px, FiniteInterval)
            or (
                domain is not None
                and not isinstance(domain, FiniteInterval)
            )
            or (
                self.basis is not None
                and not isinstance(
                    self.basis,
                    DirectRoleApertureDomainBasis,
                )
            )
            or (
                self.failure_kind is not None
                and not isinstance(
                    self.failure_kind,
                    DirectRoleApertureDomainFailureKind,
                )
            )
            or tuple(dict.fromkeys(self.cross_observation_ids))
            != self.cross_observation_ids
            or any(
                not isinstance(item, ObservationId)
                for item in self.cross_observation_ids
            )
            or self.state
            not in {
                EvidenceState.SUPPORTED,
                EvidenceState.CONTRADICTED,
                EvidenceState.UNAVAILABLE,
            }
            or supported
            != (
                has_cross_domain
                and self.failure_kind is None
                and contained
            )
            or contradicted
            != (
                has_cross_domain
                and (
                    (collapsed and domain is None)
                    or (
                        outside
                        and domain is not None
                        and not contained
                    )
                )
            )
            or unavailable
            != (
                self.basis is None
                and domain is None
                and self.failure_kind
                == DirectRoleApertureDomainFailureKind.TWO_SIDED_CROSS_DOMAIN_UNAVAILABLE
            )
        ):
            raise ValueError("direct-role aperture-domain fact is invalid")


@dataclass(frozen=True)
class DirectRoleApertureDomainAuthority:
    """Canonical selection authority for all partial-height direct roles."""

    state: EvidenceState
    facts: tuple[DirectRoleApertureDomainFact, ...]
    unsupported_role_indices: tuple[int, ...]
    reason: str | None

    def __post_init__(self) -> None:
        indices = tuple(item.role_index for item in self.facts)
        unsupported = tuple(
            item.role_index
            for item in self.facts
            if item.state != EvidenceState.SUPPORTED
        )
        expected = (
            EvidenceState.CONTRADICTED
            if any(
                item.state == EvidenceState.CONTRADICTED
                for item in self.facts
            )
            else EvidenceState.UNAVAILABLE
            if unsupported
            else EvidenceState.SUPPORTED
        )
        if (
            not self.facts
            or indices != tuple(sorted(set(indices)))
            or unsupported != self.unsupported_role_indices
            or self.state != expected
            or (expected == EvidenceState.SUPPORTED) != (self.reason is None)
            or self.reason is not None
            and (not isinstance(self.reason, str) or not self.reason)
        ):
            raise ValueError("direct-role aperture-domain authority is invalid")


def _projected_boundary_interval(
    base: FiniteInterval,
    *,
    role_position: FiniteInterval,
    lane_reference_trace_px: float,
    angle_degrees: FiniteInterval,
) -> FiniteInterval:
    positions = tuple(
        base_position
        + math.tan(math.radians(angle))
        * (long_position - lane_reference_trace_px)
        for base_position in (base.minimum, base.maximum)
        for angle in (angle_degrees.minimum, angle_degrees.maximum)
        for long_position in (
            role_position.minimum,
            role_position.maximum,
        )
    )
    return FiniteInterval(min(positions), max(positions))


def _cross_basis(
    cross: CrossFit,
) -> DirectRoleApertureDomainBasis | None:
    if not cross.direct_pair or cross.selected_direction is None:
        return None
    if cross.boundary_use == OutputBoundaryUse.APERTURE_PAIR:
        return DirectRoleApertureDomainBasis.DIRECT_APERTURE_PAIR
    if (
        cross.boundary_use == OutputBoundaryUse.ENCLOSING_SUPPORT_PAIR
        and cross.enclosing_support_pair is not None
    ):
        return DirectRoleApertureDomainBasis.ENCLOSING_SUPPORT_APERTURE
    return None


def assess_direct_role_aperture_domain_authority(
    sequence: SequenceFit,
    cross: CrossFit,
    direct_role_authority: DirectRoleBindingAuthority,
) -> DirectRoleApertureDomainAuthority:
    """Require every partial edge fragment to stay inside every aperture state.

    The owner consumes only already selected, registered evidence.  It neither
    reads pixels nor creates a geometry candidate.
    """

    required = tuple(
        item
        for item in direct_role_authority.facts
        if item.state == EvidenceState.SUPPORTED
        and DirectRoleAuthorityBasis.PARTIAL_HEIGHT_SEPARATOR_PAIR
        in item.bases
    )
    if not required:
        raise ValueError("aperture-domain authority requires a partial-height role")
    basis = _cross_basis(cross)
    direction = cross.selected_direction
    cross_ids = tuple(
        dict.fromkeys(
            (
                *cross.direct_provenance_ids,
                *(
                    ()
                    if direction is None
                    else direction.selected_observation_ids
                ),
            )
        )
    )
    facts: list[DirectRoleApertureDomainFact] = []
    for authority_fact in required:
        binding = sequence.role_bindings[authority_fact.role_index]
        if (
            binding is None
            or binding.observation_id != authority_fact.observation_id
        ):
            raise ValueError(
                "partial-height aperture authority lost its selected binding"
            )
        traces = authority_fact.trace_coordinates_px
        if not traces:
            raise ValueError(
                "partial-height aperture authority lost registered traces"
            )
        trace_interval = FiniteInterval(
            float(min(traces)) - PIXEL_CENTER_HALF_EXTENT_PX,
            float(max(traces)) + PIXEL_CENTER_HALF_EXTENT_PX,
        )
        domain: FiniteInterval | None = None
        failure = (
            DirectRoleApertureDomainFailureKind.TWO_SIDED_CROSS_DOMAIN_UNAVAILABLE
        )
        state = EvidenceState.UNAVAILABLE
        if basis is not None and direction is not None:
            top = _projected_boundary_interval(
                cross.top_full_interval_px,
                role_position=binding.full_position_interval_px,
                lane_reference_trace_px=cross.lane_reference_trace_px,
                angle_degrees=direction.full_angle_interval_degrees,
            )
            bottom = _projected_boundary_interval(
                cross.bottom_full_interval_px,
                role_position=binding.full_position_interval_px,
                lane_reference_trace_px=cross.lane_reference_trace_px,
                angle_degrees=direction.full_angle_interval_degrees,
            )
            if top.maximum >= bottom.minimum:
                failure = (
                    DirectRoleApertureDomainFailureKind.APERTURE_DOMAIN_COLLAPSED
                )
                state = EvidenceState.CONTRADICTED
            else:
                domain = FiniteInterval(top.maximum, bottom.minimum)
                contained = domain.contains(
                    trace_interval.minimum,
                    epsilon=1.0e-9,
                ) and domain.contains(
                    trace_interval.maximum,
                    epsilon=1.0e-9,
                )
                state = (
                    EvidenceState.SUPPORTED
                    if contained
                    else EvidenceState.CONTRADICTED
                )
                failure = (
                    None
                    if contained
                    else DirectRoleApertureDomainFailureKind.SUPPORT_OUTSIDE_APERTURE_DOMAIN
                )
        facts.append(
            DirectRoleApertureDomainFact(
                role_index=authority_fact.role_index,
                observation_id=authority_fact.observation_id,
                role_position_interval_px=binding.full_position_interval_px,
                support_trace_interval_px=trace_interval,
                guaranteed_aperture_interval_px=domain,
                basis=basis,
                cross_observation_ids=cross_ids,
                state=state,
                failure_kind=failure,
            )
        )
    typed_facts = tuple(facts)
    contradicted = tuple(
        item.role_index
        for item in typed_facts
        if item.state == EvidenceState.CONTRADICTED
    )
    unavailable = tuple(
        item.role_index
        for item in typed_facts
        if item.state == EvidenceState.UNAVAILABLE
    )
    state = (
        EvidenceState.CONTRADICTED
        if contradicted
        else EvidenceState.UNAVAILABLE
        if unavailable
        else EvidenceState.SUPPORTED
    )
    reason = (
        "partial-height direct edge leaves the guaranteed aperture domain at "
        "role indices: " + ", ".join(map(str, contradicted))
        if contradicted
        else "partial-height direct edge lacks a unique two-sided aperture "
        "domain at role indices: " + ", ".join(map(str, unavailable))
        if unavailable
        else None
    )
    return DirectRoleApertureDomainAuthority(
        state=state,
        facts=typed_facts,
        unsupported_role_indices=tuple(
            item.role_index
            for item in typed_facts
            if item.state != EvidenceState.SUPPORTED
        ),
        reason=reason,
    )


__all__ = [
    "DirectRoleApertureDomainAuthority",
    "DirectRoleApertureDomainBasis",
    "DirectRoleApertureDomainFact",
    "DirectRoleApertureDomainFailureKind",
    "assess_direct_role_aperture_domain_authority",
]
