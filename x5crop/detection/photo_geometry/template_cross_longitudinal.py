"""Canonical longitudinal projection authority for short-axis geometry."""

from __future__ import annotations

from ...domain import EvidenceState, FiniteInterval, ObservationId
from .model import SPATIAL_SUPPORT_REGION_COUNT
from .physical_identity import physical_fact_id
from .template_cross_model import (
    CrossLongitudinalProjectionAuthority,
    CrossLongitudinalProjectionBasis,
    CrossLongitudinalProjectionFailureKind,
)


def covered_template_domain_ordinals(
    trace_coordinates_px: tuple[int, ...],
    domains: tuple[FiniteInterval, ...],
) -> tuple[int, ...]:
    """Return one-based template domains containing at least one direct trace."""

    return tuple(
        ordinal
        for ordinal, domain in enumerate(domains, start=1)
        if any(
            domain.contains(float(trace), epsilon=0.5)
            for trace in trace_coordinates_px
        )
    )


def covers_all_template_domains(
    trace_coordinates_px: tuple[int, ...],
    domains: tuple[FiniteInterval, ...],
) -> bool:
    """Whether direct traces occur in every selected Frame domain."""

    return bool(domains) and len(
        covered_template_domain_ordinals(trace_coordinates_px, domains)
    ) == len(domains)


def assess_cross_longitudinal_projection(
    *,
    supporting_observation_ids: tuple[ObservationId, ...],
    trace_coordinates_px: tuple[int, ...],
    domains: tuple[FiniteInterval, ...],
    source_spanning_continuous: bool,
    require_complete_template_domains: bool = False,
) -> CrossLongitudinalProjectionAuthority:
    """Assess whether direct Cross support may span the complete placement.

    A straight Cross line may interpolate between direct support, but it may
    not obtain production authority by extrapolating beyond the observed
    longitudinal extent. Source-spanning continuity is the stronger direct
    path. A single-role H inference requires every selected Frame domain; a
    two-sided pair may instead use complementary direct support that has
    already closed the pair locally and collectively includes both ends of
    the selected placement.
    """

    identities = tuple(sorted(set(supporting_observation_ids), key=str))
    if not identities or any(
        not isinstance(identity, ObservationId) for identity in identities
    ):
        raise ValueError("Cross projection needs direct observation identities")
    traces = tuple(sorted(set(trace_coordinates_px)))
    covered = covered_template_domain_ordinals(traces, domains)
    required = min(SPATIAL_SUPPORT_REGION_COUNT, len(domains))
    bracketed = bool(domains) and covered[:1] == (1,) and covered[-1:] == (
        len(domains),
    )
    authority_id = physical_fact_id(
        "cross-longitudinal-projection",
        *(str(identity) for identity in identities),
        len(domains),
        *(str(ordinal) for ordinal in covered),
    )

    basis: CrossLongitudinalProjectionBasis | None = None
    failure: CrossLongitudinalProjectionFailureKind | None = None
    if source_spanning_continuous:
        basis = (
            CrossLongitudinalProjectionBasis.SOURCE_SPANNING_CONTINUOUS
        )
        bracketed = True
    elif not domains:
        failure = (
            CrossLongitudinalProjectionFailureKind
            .TEMPLATE_DOMAINS_UNAVAILABLE
        )
    elif require_complete_template_domains and len(covered) != len(domains):
        failure = (
            CrossLongitudinalProjectionFailureKind
            .COMPLETE_TEMPLATE_DOMAIN_SUPPORT_UNAVAILABLE
        )
    elif len(covered) < required:
        failure = (
            CrossLongitudinalProjectionFailureKind
            .INDEPENDENT_DOMAIN_SUPPORT_UNAVAILABLE
        )
    elif not bracketed:
        failure = (
            CrossLongitudinalProjectionFailureKind
            .TEMPLATE_EXTENT_UNBRACKETED
        )
    elif len(covered) == len(domains):
        basis = CrossLongitudinalProjectionBasis.COMPLETE_TEMPLATE_DOMAINS
    else:
        basis = CrossLongitudinalProjectionBasis.BRACKETED_TEMPLATE_EXTENT

    return CrossLongitudinalProjectionAuthority(
        authority_id=authority_id,
        state=(
            EvidenceState.SUPPORTED
            if basis is not None
            else EvidenceState.UNAVAILABLE
        ),
        template_domain_count=len(domains),
        required_independent_domain_count=required,
        supported_domain_ordinals=covered,
        template_extent_bracketed=bracketed,
        supporting_observation_ids=identities,
        basis=basis,
        failure_kind=failure,
    )
