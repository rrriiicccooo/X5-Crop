"""Construct and group bounded short-axis physical fit candidates."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Sequence

from ...domain import FiniteInterval
from .interval_math import (
    add as _add,
    intersect as _intersect,
    subtract as _subtract,
)
from .model import (
    BoundaryRole,
    MINIMUM_INDEPENDENT_SUPPORT_REGIONS,
    SPATIAL_SUPPORT_REGION_COUNT,
    independent_spatial_support_count,
)
from .output_model import OutputBoundaryUse, SharedStripDirection
from .template_cross_geometry import (
    direction_closure as _direction_closure,
    shared_direction_for as _direction_for,
    shared_trace_coordinates as _shared_trace_coordinates,
    single_direction_ready as _single_direction_ready,
)
from .template_cross_model import (
    CrossEvidence,
    CrossFailureKind,
    CrossFit,
    CrossHeightInferenceBasis,
    CrossPairSupportMode,
    CrossRoleBinding,
)
from .template_model import TemplateSpec


@dataclass(frozen=True)
class _Candidate:
    top: CrossRoleBinding
    bottom: CrossRoleBinding
    direct_pair: bool
    shared_support: int
    continuous_support: float
    residual: float
    height_compatibility: FiniteInterval
    canonical_height_px: float
    shift_interval: FiniteInterval
    direction_interval: FiniteInterval | None
    direction_ready: bool
    support_trace_coordinates_px: tuple[int, ...]
    authority_trace_coordinates_px: tuple[int, ...]
    pair_support_mode: CrossPairSupportMode | None
    height_inference_basis: CrossHeightInferenceBasis | None
    top_full_override: FiniteInterval | None = None
    bottom_full_override: FiniteInterval | None = None
    source_direction: SharedStripDirection | None = None


def _fits_source_direction(
    binding: CrossRoleBinding,
    source_direction: SharedStripDirection,
) -> bool:
    """Use fitted local slope for membership, full slope only for safety."""

    return (
        binding.fit_direction_interval_degrees is not None
        and _intersect(
            binding.fit_direction_interval_degrees,
            source_direction.observed_angle_interval_degrees,
        )
        is not None
    )


def _direct_candidate(
    top: CrossRoleBinding,
    bottom: CrossRoleBinding,
    *,
    fixed_height: FiniteInterval,
    canonical_height_px: float,
    minimum_shared_trace_support: int,
    longitudinal_support_domains_px: tuple[FiniteInterval, ...] = (),
    source_direction: SharedStripDirection | None = None,
) -> tuple[_Candidate | None, CrossFailureKind | None]:
    # Aperture coordinates require photo-boundary role authority on both
    # sides. Role-unknown material/holder lines belong to the separate
    # enclosing-support owner even when their span happens to match H.
    if not top.role_authorized or not bottom.role_authorized:
        return None, CrossFailureKind.DIRECT_ROLE_AUTHORITY_UNAVAILABLE
    expected_bottom = _add(top.full_interval_px, fixed_height)
    if _intersect(bottom.full_interval_px, expected_bottom) is None:
        return None, CrossFailureKind.FIXED_HEIGHT_INCOMPATIBLE
    height = _intersect(fixed_height, _subtract(bottom.full_interval_px, top.full_interval_px))
    shift = _intersect(top.full_interval_px, _subtract(bottom.full_interval_px, fixed_height))
    if height is None or shift is None:
        return None, CrossFailureKind.FIXED_HEIGHT_INCOMPATIBLE
    support_traces = _shared_trace_coordinates(top, bottom)
    if len(support_traces) >= minimum_shared_trace_support:
        pair_support_mode = CrossPairSupportMode.SHARED_TRACES
        authority_traces = support_traces
    else:
        authority_traces = tuple(
            sorted(
                set(top.trace_coordinates_px).union(
                    bottom.trace_coordinates_px
                )
            )
        )
        if (
            top.evidence != CrossEvidence.DIRECT
            or bottom.evidence != CrossEvidence.DIRECT
            or top.independent_support_region_count
            < MINIMUM_INDEPENDENT_SUPPORT_REGIONS
            or bottom.independent_support_region_count
            < MINIMUM_INDEPENDENT_SUPPORT_REGIONS
            or not longitudinal_support_domains_px
            or not all(
                any(
                    domain.contains(float(trace), epsilon=0.5)
                    for trace in authority_traces
                )
                for domain in longitudinal_support_domains_px
            )
        ):
            return None, CrossFailureKind.PAIR_SUPPORT_UNAVAILABLE
        pair_support_mode = CrossPairSupportMode.COMPLEMENTARY_DOMAINS
        support_traces = ()
    if source_direction is None:
        direction, direction_ready, contradiction = _direction_closure(
            top,
            bottom,
        )
        if contradiction:
            return None, CrossFailureKind.DIRECTION_INCOMPATIBLE
    else:
        if any(
            not _fits_source_direction(item, source_direction)
            for item in (top, bottom)
        ):
            return None, CrossFailureKind.DIRECTION_INCOMPATIBLE
        # The whole-strip observation validates that both local fragments
        # belong to the same strip and bounds their local cross relation.
        # It never owns cosmetic output deskew; small local departures remain
        # a straight-model residual instead of entering the coarse fit.
        direction = source_direction.observed_angle_interval_degrees
        direction_ready = True
    return (
        _Candidate(
            top=top,
            bottom=bottom,
            direct_pair=True,
            shared_support=0,
            continuous_support=min(
                top.continuous_support_fraction,
                bottom.continuous_support_fraction,
            ),
            residual=top.fit_residual_px + bottom.fit_residual_px,
            height_compatibility=height,
            canonical_height_px=canonical_height_px,
            shift_interval=shift,
            direction_interval=direction,
            direction_ready=direction_ready,
            support_trace_coordinates_px=support_traces,
            authority_trace_coordinates_px=authority_traces,
            pair_support_mode=pair_support_mode,
            height_inference_basis=None,
            source_direction=None,
        ),
        None,
    )


def _single_candidate(
    binding: CrossRoleBinding,
    *,
    fixed_height: FiniteInterval,
    canonical_height_px: float,
    height_inference_basis: CrossHeightInferenceBasis,
    source_direction: SharedStripDirection | None = None,
    template_domain_complete: bool = False,
) -> _Candidate | None:
    # A single edge needs independent spatial support and direct direction.
    # It must additionally span the complete registered domain before its
    # coordinate can own placement.  A direct,
    # role-authorized binding with a direct trace in every selected frame
    # domain (and at least three selected domains) is a separate bounded
    # authority: it may own fixed-H placement even when its aggregate support
    # ledger reports only two independent regions. The caller must establish
    # this per-domain direct-trace fact from the registered lattice; this flag
    # never lowers the general support requirement for local edges.
    if not isinstance(height_inference_basis, CrossHeightInferenceBasis):
        raise TypeError("single-side cross needs a typed H inference basis")
    if (
        not binding.role_authorized
        or (
            binding.independent_support_region_count
            < SPATIAL_SUPPORT_REGION_COUNT
            and not template_domain_complete
        )
        or (
            source_direction is None
            and not _single_direction_ready(binding)
        )
        or (
            source_direction is not None
            and not _fits_source_direction(binding, source_direction)
        )
        or (
            not binding.source_spanning_continuous
            and not template_domain_complete
        )
    ):
        return None
    if binding.role == BoundaryRole.TOP:
        top = binding
        bottom = binding
        top_full = binding.full_interval_px
        bottom_full = _add(
            top_full,
            fixed_height,
        )
    else:
        top = binding
        bottom = binding
        bottom_full = binding.full_interval_px
        top_full = _subtract(
            bottom_full,
            fixed_height,
        )
    shift = top_full
    return _Candidate(
        top=top,
        bottom=bottom,
        direct_pair=False,
        shared_support=0,
        continuous_support=binding.continuous_support_fraction,
        residual=binding.fit_residual_px,
        height_compatibility=fixed_height,
        canonical_height_px=canonical_height_px,
        shift_interval=shift,
        direction_interval=(
            source_direction.full_angle_interval_degrees
            if source_direction is not None
            else binding.full_direction_interval_degrees
        ),
        direction_ready=True,
        support_trace_coordinates_px=binding.trace_coordinates_px,
        authority_trace_coordinates_px=binding.trace_coordinates_px,
        pair_support_mode=None,
        height_inference_basis=height_inference_basis,
        top_full_override=top_full,
        bottom_full_override=bottom_full,
        source_direction=source_direction,
    )


def _covers_template_domains(
    binding: CrossRoleBinding,
    domains: tuple[FiniteInterval, ...],
) -> bool:
    """Whether one role-authorized side is observed across every frame domain."""

    return bool(domains) and binding.role_authorized and all(
        any(domain.contains(float(trace), epsilon=0.5) for trace in binding.trace_coordinates_px)
        for domain in domains
    )


def _longitudinal_domain_count(
    traces: tuple[int, ...],
    domains: tuple[FiniteInterval, ...],
) -> int:
    return sum(
        any(domain.contains(float(trace), epsilon=0.5) for trace in traces)
        for domain in domains
    )


def _fit_from_candidate(
    candidate: _Candidate,
    *,
    template: TemplateSpec,
    lane_reference_trace_px: float,
) -> CrossFit:
    top = candidate.top
    bottom = candidate.bottom
    inferred_evidence = {
        CrossHeightInferenceBasis.APERTURE_ASPECT_RATIO: (
            CrossEvidence.ASPECT_RATIO_HEIGHT_INFERRED
        ),
        CrossHeightInferenceBasis.CALIBRATED_FORMAT_HEIGHT: (
            CrossEvidence.CALIBRATED_FORMAT_HEIGHT_INFERRED
        ),
    }
    if candidate.direct_pair:
        top_fit = top.fit_interval_px
        bottom_fit = bottom.fit_interval_px
        top_full = top.full_interval_px
        bottom_full = bottom.full_interval_px
        target_top = top_fit.center
        target_bottom = bottom_fit.center
        height = min(
            max(
                target_bottom - target_top,
                candidate.height_compatibility.minimum,
            ),
            candidate.height_compatibility.maximum,
        )
        feasible_top = _intersect(
            top_full,
            _subtract(bottom_full, FiniteInterval.exact(height)),
        )
        if feasible_top is None:
            raise AssertionError("direct cross pair lost its fixed-height closure")
        top_canonical = min(
            max((target_top + target_bottom - height) / 2.0, feasible_top.minimum),
            feasible_top.maximum,
        )
        bottom_canonical = top_canonical + height
        direct = (top, bottom)
        inferred: tuple[CrossRoleBinding, ...] = ()
    elif top.role == BoundaryRole.TOP:
        inferred_height = FiniteInterval.exact(candidate.canonical_height_px)
        top_full = candidate.top_full_override or top.full_interval_px
        bottom_full = (
            candidate.bottom_full_override
            if candidate.bottom_full_override is not None
            else _add(top.full_interval_px, inferred_height)
        )
        top_fit = _intersect(top.fit_interval_px, top_full) or FiniteInterval.exact(
            candidate.shift_interval.center
        )
        bottom_fit = _add(top.fit_interval_px, inferred_height)
        bottom_fit = _intersect(bottom_fit, bottom_full) or FiniteInterval.exact(
            candidate.shift_interval.center + candidate.height_compatibility.center
        )
        direct = (top,)
        inferred = (
            CrossRoleBinding(
                role=BoundaryRole.BOTTOM,
                run_id=f"inferred:{top.run_id}:bottom",
                observation_id=top.observation_id,
                coordinate_interval_px=_add(top.coordinate_interval_px, inferred_height),
                trace_coordinates_px=top.trace_coordinates_px,
                support_fraction=top.support_fraction,
                continuous_support_fraction=top.continuous_support_fraction,
                fit_residual_px=top.fit_residual_px,
                fit_interval_px=bottom_fit,
                full_interval_px=bottom_full,
                canonical_direction_degrees=top.canonical_direction_degrees,
                fit_direction_interval_degrees=(
                    top.fit_direction_interval_degrees
                ),
                full_direction_interval_degrees=top.full_direction_interval_degrees,
                evidence=inferred_evidence[candidate.height_inference_basis],
                source_observation_ids=(top.observation_id,),
                independent_support_region_count=top.independent_support_region_count,
                source_spanning_continuous=top.source_spanning_continuous,
                role_authorized=top.role_authorized,
            ),
        )
    else:
        inferred_height = FiniteInterval.exact(candidate.canonical_height_px)
        bottom_full = (
            candidate.bottom_full_override
            if candidate.bottom_full_override is not None
            else bottom.full_interval_px
        )
        top_full = (
            candidate.top_full_override
            or _subtract(bottom.full_interval_px, inferred_height)
        )
        bottom_fit = _intersect(bottom.fit_interval_px, bottom_full) or FiniteInterval.exact(
            candidate.shift_interval.center + candidate.height_compatibility.center
        )
        top_fit = _subtract(bottom.fit_interval_px, inferred_height)
        top_fit = _intersect(top_fit, top_full) or FiniteInterval.exact(
            candidate.shift_interval.center
        )
        direct = (bottom,)
        inferred = (
            CrossRoleBinding(
                role=BoundaryRole.TOP,
                run_id=f"inferred:{bottom.run_id}:top",
                observation_id=bottom.observation_id,
                coordinate_interval_px=_subtract(bottom.coordinate_interval_px, inferred_height),
                trace_coordinates_px=bottom.trace_coordinates_px,
                support_fraction=bottom.support_fraction,
                continuous_support_fraction=bottom.continuous_support_fraction,
                fit_residual_px=bottom.fit_residual_px,
                fit_interval_px=top_fit,
                full_interval_px=top_full,
                canonical_direction_degrees=bottom.canonical_direction_degrees,
                fit_direction_interval_degrees=(
                    bottom.fit_direction_interval_degrees
                ),
                full_direction_interval_degrees=bottom.full_direction_interval_degrees,
                evidence=inferred_evidence[candidate.height_inference_basis],
                source_observation_ids=(bottom.observation_id,),
                independent_support_region_count=bottom.independent_support_region_count,
                source_spanning_continuous=bottom.source_spanning_continuous,
                role_authorized=bottom.role_authorized,
            ),
        )
    if not candidate.direct_pair:
        top_canonical = candidate.shift_interval.center
        bottom_canonical = top_canonical + candidate.canonical_height_px
    selected_direction = candidate.source_direction or _direction_for(
        direct,
        parallel_interval=candidate.direction_interval,
    )
    return CrossFit(
        template_id=template.template_id,
        lane_reference_trace_px=lane_reference_trace_px,
        fixed_height_px=candidate.height_compatibility,
        top_canonical_px=top_canonical,
        bottom_canonical_px=bottom_canonical,
        top_fit_interval_px=top_fit,
        bottom_fit_interval_px=bottom_fit,
        top_full_interval_px=top_full,
        bottom_full_interval_px=bottom_full,
        direct_bindings=direct,
        inferred_bindings=inferred,
        selected_direction=selected_direction,
        direct_pair=candidate.direct_pair,
        shared_trace_support_count=candidate.shared_support,
        continuous_support_fraction=candidate.continuous_support,
        residual_sum_px=candidate.residual,
        boundary_use=OutputBoundaryUse.APERTURE_PAIR,
        pair_support_mode=candidate.pair_support_mode,
        height_compatibility_px=candidate.height_compatibility,
        shift_interval_px=candidate.shift_interval,
        parallel_direction_interval_degrees=candidate.direction_interval,
        direction_provenance_ids=(selected_direction.selected_observation_ids if selected_direction is not None else ()),
        single_side_inferred=not candidate.direct_pair,
        height_inference_basis=candidate.height_inference_basis,
        independent_support_region_count=candidate.shared_support,
    )


def _group_candidates(candidates: Sequence[_Candidate]) -> tuple[tuple[_Candidate, ...], ...]:
    groups: dict[tuple[bool, object, object], list[_Candidate]] = {}
    for candidate in candidates:
        key = (
            candidate.direct_pair,
            candidate.top.observation_id,
            candidate.bottom.observation_id,
        )
        groups.setdefault(key, []).append(candidate)
    return tuple(tuple(group) for group in groups.values())


def _fit_from_group(
    group: Sequence[_Candidate],
    *,
    template: TemplateSpec,
    lane_reference_trace_px: float,
    registered_trace_coordinates_px: tuple[int, ...],
    longitudinal_support_domains_px: tuple[FiniteInterval, ...],
) -> CrossFit:
    """Collapse one continuous physical group without hulling alternatives."""

    def support_region_count(traces: tuple[int, ...]) -> int:
        count = independent_spatial_support_count(
            registered_trace_coordinates_px,
            traces,
        )
        count = max(count, support_domain_count(traces))
        return min(SPATIAL_SUPPORT_REGION_COUNT, count)

    def support_domain_count(traces: tuple[int, ...]) -> int:
        if not longitudinal_support_domains_px:
            return 0
        return min(
            SPATIAL_SUPPORT_REGION_COUNT,
            sum(
                any(
                    domain.contains(float(trace), epsilon=0.5)
                    for trace in traces
                )
                for domain in longitudinal_support_domains_px
            ),
        )

    def role_authorized_pair_domain_count(
        candidates: Sequence[_Candidate],
    ) -> int:
        return max(
            (
                support_domain_count(candidate.authority_trace_coordinates_px)
                for candidate in candidates
                if candidate.direct_pair
                and candidate.top.role_authorized
                and candidate.bottom.role_authorized
            ),
            default=0,
        )

    role_authorized_group = tuple(
        candidate
        for candidate in group
        if candidate.direct_pair
        and candidate.top.role_authorized
        and candidate.bottom.role_authorized
        and support_domain_count(candidate.authority_trace_coordinates_px)
        >= min(MINIMUM_INDEPENDENT_SUPPORT_REGIONS, template.count)
    )
    if role_authorized_group:
        group = role_authorized_group

    representative = _fit_from_candidate(
        group[0],
        template=template,
        lane_reference_trace_px=lane_reference_trace_px,
    )

    candidate = group[0]
    if any(
        item.direct_pair != candidate.direct_pair
        or item.top.observation_id != candidate.top.observation_id
        or item.bottom.observation_id != candidate.bottom.observation_id
        or item.height_inference_basis != candidate.height_inference_basis
        for item in group[1:]
    ):
        raise AssertionError("cross group merged distinct physical bindings")
    direct = (
        (candidate.top, candidate.bottom)
        if candidate.direct_pair
        else (candidate.top,)
    )
    support_traces = tuple(
        sorted(
            {
                trace
                for item in group
                for trace in item.support_trace_coordinates_px
            }
        )
    )
    authority_traces = tuple(
        sorted(
            {
                trace
                for item in group
                for trace in item.authority_trace_coordinates_px
            }
        )
    )
    return replace(
        representative,
        shared_trace_support_count=len(support_traces),
        continuous_support_fraction=min(item.continuous_support for item in group),
        residual_sum_px=max(item.residual for item in group),
        direct_provenance_ids=tuple(item.observation_id for item in direct),
        independent_support_region_count=support_region_count(authority_traces),
        longitudinal_support_domain_count=support_domain_count(authority_traces),
        role_authorized_pair_support_domain_count=(
            role_authorized_pair_domain_count(group)
        ),
    )
