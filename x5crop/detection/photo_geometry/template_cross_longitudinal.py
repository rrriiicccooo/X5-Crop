"""Canonical longitudinal projection authority for short-axis geometry."""

from __future__ import annotations

from bisect import bisect_left
import math

from ...domain import EvidenceState, FiniteInterval, ObservationId
from .model import SPATIAL_SUPPORT_REGION_COUNT
from .physical_identity import physical_fact_id
from .template_cross_model import (
    CrossLongitudinalProjectionAuthority,
    CrossLongitudinalProjectionBasis,
    CrossLongitudinalProjectionFailureKind,
)


def _ordered_finite_traces(trace_coordinates_px):
    return tuple(sorted(value for value in map(float, trace_coordinates_px)
                        if math.isfinite(value)))


def _domain_has_trace(traces: tuple[float, ...], domain: FiniteInterval) -> bool:
    # Same closed +/-0.5 px containment as FiniteInterval.contains, without
    # rescanning every trace for each Frame in every compatible Cross pair.
    index = bisect_left(traces, domain.minimum - 0.5)
    return index < len(traces) and traces[index] <= domain.maximum + 0.5


def _covered_domain_ordinals(
    traces: tuple[float, ...],
    domains: tuple[FiniteInterval, ...],
) -> tuple[int, ...]:
    return tuple(
        ordinal
        for ordinal, domain in enumerate(domains, start=1)
        if _domain_has_trace(traces, domain)
    )


def covered_template_domain_ordinals(
    trace_coordinates_px: tuple[int, ...],
    domains: tuple[FiniteInterval, ...],
) -> tuple[int, ...]:
    """Return one-based template domains containing at least one direct trace."""

    return _covered_domain_ordinals(_ordered_finite_traces(trace_coordinates_px), domains)


def covers_all_template_domains(
    trace_coordinates_px: tuple[int, ...],
    domain_groups: tuple[tuple[FiniteInterval, ...], ...],
) -> bool:
    """Whether every retained candidate has direct support in every Frame."""

    traces = _ordered_finite_traces(trace_coordinates_px)
    return bool(domain_groups) and all(
        bool(domains)
        and all(_domain_has_trace(traces, domain) for domain in domains)
        for domains in domain_groups
    )


def assess_cross_longitudinal_projection(
    *,
    supporting_observation_ids: tuple[ObservationId, ...],
    trace_coordinates_px: tuple[int, ...],
    domain_groups: tuple[tuple[FiniteInterval, ...], ...],
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
    ordered_traces = _ordered_finite_traces(traces)
    domain_count = len(domain_groups[0]) if domain_groups else 0
    covered = tuple(
        _covered_domain_ordinals(ordered_traces, domains)
        for domains in domain_groups
    )
    required = min(SPATIAL_SUPPORT_REGION_COUNT, domain_count)
    bracketed = bool(domain_groups) and all(
        ordinals[:1] == (1,) and ordinals[-1:] == (domain_count,)
        for ordinals in covered
    )
    complete = bool(domain_groups) and all(
        len(ordinals) == domain_count for ordinals in covered
    )
    authority_id = physical_fact_id(
        "cross-longitudinal-projection",
        *(str(identity) for identity in identities),
        domain_count,
        repr(domain_groups),
        repr(covered),
    )

    basis: CrossLongitudinalProjectionBasis | None = None
    failure: CrossLongitudinalProjectionFailureKind | None = None
    if source_spanning_continuous:
        basis = (
            CrossLongitudinalProjectionBasis.SOURCE_SPANNING_CONTINUOUS
        )
        bracketed = True
    elif not domain_groups:
        failure = (
            CrossLongitudinalProjectionFailureKind
            .TEMPLATE_DOMAINS_UNAVAILABLE
        )
    elif require_complete_template_domains and not complete:
        failure = (
            CrossLongitudinalProjectionFailureKind
            .COMPLETE_TEMPLATE_DOMAIN_SUPPORT_UNAVAILABLE
        )
    elif any(len(ordinals) < required for ordinals in covered):
        failure = (
            CrossLongitudinalProjectionFailureKind
            .INDEPENDENT_DOMAIN_SUPPORT_UNAVAILABLE
        )
    elif not bracketed:
        failure = (
            CrossLongitudinalProjectionFailureKind
            .TEMPLATE_EXTENT_UNBRACKETED
        )
    elif complete:
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
        template_domain_count=domain_count,
        required_independent_domain_count=required,
        candidate_support_domains_px=domain_groups,
        supported_domain_ordinals_by_candidate=covered,
        template_extent_bracketed=bracketed,
        supporting_observation_ids=identities,
        basis=basis,
        failure_kind=failure,
    )
