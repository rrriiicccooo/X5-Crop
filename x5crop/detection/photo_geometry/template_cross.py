"""Orchestrate bounded fixed-height short-axis template fitting."""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import replace
import math
from ...domain import FiniteInterval
from .model import (
    BoundaryAxis,
    BoundaryRole,
    MINIMUM_INDEPENDENT_SUPPORT_REGIONS,
    SPATIAL_SUPPORT_REGION_COUNT,
)
from .output_model import OutputBoundaryUse
from .template_cross_candidates import (
    _covers_template_domains,
    _direct_candidate,
    _fit_from_candidate,
    _fit_from_group,
    _group_candidates,
    _longitudinal_domain_count,
    _single_candidate,
    _template_local_refinement_candidates,
)
from .template_cross_model import (
    CrossFit,
    CrossFitCompetition,
    CrossFitStatus,
    CrossRoleBinding,
    CrossSearchReceipt,
    TemplateCrossInput,
    _add,
    _intersect,
    _midpoint_interval,
)
from .template_cross_support import (
    SupportFitStatus,
    fit_enclosing_support,
)


def _receipt(
    *,
    inputs: TemplateCrossInput,
    registered_runs: int,
    fitted_observations: int,
    compatible_pairs: int,
    single_side_inferences: int,
    evaluated_fits: int,
) -> CrossSearchReceipt:
    return CrossSearchReceipt(
        registered_run_count=registered_runs,
        fitted_observation_count=fitted_observations,
        compatible_pair_count=compatible_pairs,
        single_side_inference_count=single_side_inferences,
        evaluated_fit_count=evaluated_fits,
        registered_run_bound=inputs.maximum_registered_runs,
        fitted_observation_bound=inputs.maximum_fitted_observations,
        compatible_pair_bound=inputs.maximum_compatible_pairs,
        evaluated_fit_bound=inputs.maximum_evaluated_fits,
    )


def _remove_contained_local_side_tracks(
    candidates,
    longitudinal_domains: tuple[FiniteInterval, ...],
):
    """Remove a local side fragment contained by a broader direct track.

    This is set dominance, not a score: the two candidates must share the
    opposite direct boundary, the broader same-role observation must contain
    every trace of the fragment, and it must reach a strictly larger set of
    already fixed template-frame domains.  Disjoint tracks and equal-domain
    alternatives remain competing placements.
    """

    if not longitudinal_domains:
        return list(candidates)

    def dominates(broader, fragment) -> bool:
        if not broader.direct_pair or not fragment.direct_pair:
            return False
        if broader.top.observation_id == fragment.top.observation_id:
            broad_side, local_side = broader.bottom, fragment.bottom
        elif broader.bottom.observation_id == fragment.bottom.observation_id:
            broad_side, local_side = broader.top, fragment.top
        else:
            return False
        if (
            broad_side.observation_id == local_side.observation_id
            or broad_side.role != local_side.role
            or not broad_side.role_authorized
            or not local_side.role_authorized
        ):
            return False
        broad_traces = set(broad_side.trace_coordinates_px)
        local_traces = set(local_side.trace_coordinates_px)
        return (
            bool(local_traces)
            and local_traces < broad_traces
            and _longitudinal_domain_count(
                broad_side.trace_coordinates_px,
                longitudinal_domains,
            )
            > _longitudinal_domain_count(
                local_side.trace_coordinates_px,
                longitudinal_domains,
            )
        )

    return [
        candidate
        for candidate in candidates
        if not any(
            other is not candidate and dominates(other, candidate)
            for other in candidates
        )
    ]


def fit_template_cross(inputs: TemplateCrossInput) -> CrossFitCompetition:
    """Fit one fixed-H short-axis template with bounded interval search."""

    if not isinstance(inputs, TemplateCrossInput):
        raise TypeError("fit_template_cross requires TemplateCrossInput")
    top = inputs.top_bindings
    bottom = inputs.bottom_bindings
    if any(item.role != BoundaryRole.TOP for item in top):
        raise ValueError("top registration contains a non-top role")
    if any(item.role != BoundaryRole.BOTTOM for item in bottom):
        raise ValueError("bottom registration contains a non-bottom role")
    all_ids = tuple(item.observation_id for item in (*top, *bottom))
    if len(set(all_ids)) != len(all_ids):
        raise ValueError("cross observation registered more than once")
    registered_run_ids = {item.run_id for item in (*top, *bottom)}
    registered_runs = len(registered_run_ids)
    fitted_observations = len(all_ids)
    empty_receipt = lambda: _receipt(
        inputs=inputs,
        registered_runs=registered_runs,
        fitted_observations=fitted_observations,
        compatible_pairs=0,
        single_side_inferences=0,
        evaluated_fits=0,
    )
    if registered_runs > inputs.maximum_registered_runs or fitted_observations > inputs.maximum_fitted_observations:
        return CrossFitCompetition(
            template_id=inputs.template.template_id,
            best=None,
            runner_up=None,
            status=CrossFitStatus.BOUND_EXCEEDED,
            reason="cross registration bound exceeded",
            receipt=empty_receipt(),
        )
    if not top and not bottom:
        return CrossFitCompetition(
            template_id=inputs.template.template_id,
            best=None,
            runner_up=None,
            status=CrossFitStatus.UNRESOLVED,
            reason="cross fit requires top or bottom direct evidence",
            receipt=empty_receipt(),
        )
    fixed_height = inputs.fixed_height_px
    assert isinstance(fixed_height, FiniteInterval)
    registered_trace_coordinates = (
        inputs.registered_trace_coordinates_px
        or tuple(
            sorted(
                {
                    trace
                    for binding in (*top, *bottom)
                    for trace in binding.trace_coordinates_px
                }
            )
        )
    )

    enclosing_support_fit: CrossFit | None = None
    support_competition = None
    support_checked = False
    support_receipt_accounted = False

    def unique_enclosing_support() -> CrossFit | None:
        nonlocal enclosing_support_fit, support_competition, support_checked
        if support_checked:
            return enclosing_support_fit
        support_checked = True
        # Prefer one already closed coarse pair.  If none was compiled, only
        # role-unknown source support lines may form an enclosing output pair;
        # photo-aperture roles are never reinterpreted here.
        explicit_pair_ids = {
            item.enclosing_pair_id
            for item in (*top, *bottom)
            if item.enclosing_pair_id is not None
        }
        if explicit_pair_ids:
            support_top = tuple(
                item for item in top if item.enclosing_pair_id is not None
            )
            support_bottom = tuple(
                item for item in bottom if item.enclosing_pair_id is not None
            )
        else:
            support_top = tuple(item for item in top if not item.role_authorized)
            support_bottom = tuple(
                item for item in bottom if not item.role_authorized
            )
        competition = fit_enclosing_support(
            template=inputs.template,
            fixed_height=fixed_height,
            canonical_height_px=float(inputs.canonical_fixed_height_px),
            reference_trace_px=inputs.lane_reference_trace_px,
            holder_center=inputs.holder_short_axis_center_px,
            top_bindings=support_top,
            bottom_bindings=support_bottom,
            registered_trace_coordinates_px=registered_trace_coordinates,
            longitudinal_support_domains_px=inputs.longitudinal_support_domains_px,
            minimum_shared_trace_support=inputs.minimum_shared_trace_support,
            maximum_evaluated_candidates=inputs.maximum_evaluated_fits,
        )
        support_competition = competition
        if competition.status != SupportFitStatus.RESOLVED or competition.best is None:
            return None
        candidate = competition.best
        midpoint = _midpoint_interval(
            candidate.top_binding.full_interval_px,
            candidate.bottom_binding.full_interval_px,
        )
        center_interval = (
            _intersect(midpoint, inputs.holder_short_axis_center_px)
            if inputs.holder_short_axis_center_px is not None
            else midpoint
        )
        if center_interval is None:
            return None
        center = center_interval.center
        canonical_height = float(inputs.canonical_fixed_height_px)
        top_canonical = center - canonical_height / 2.0
        bottom_canonical = center + canonical_height / 2.0
        top_full = FiniteInterval(
            center - fixed_height.maximum / 2.0,
            center - fixed_height.minimum / 2.0,
        )
        bottom_full = FiniteInterval(
            center + fixed_height.minimum / 2.0,
            center + fixed_height.maximum / 2.0,
        )
        direction = candidate.selected_direction
        enclosing_support_fit = CrossFit(
            template_id=inputs.template.template_id,
            lane_reference_trace_px=inputs.lane_reference_trace_px,
            fixed_height_px=fixed_height,
            top_canonical_px=top_canonical,
            bottom_canonical_px=bottom_canonical,
            top_fit_interval_px=FiniteInterval.exact(top_canonical),
            bottom_fit_interval_px=FiniteInterval.exact(bottom_canonical),
            top_full_interval_px=top_full,
            bottom_full_interval_px=bottom_full,
            direct_bindings=(candidate.top_binding, candidate.bottom_binding),
            inferred_bindings=(),
            selected_direction=direction,
            direct_pair=True,
            shared_trace_support_count=candidate.shared_trace_support_count,
            continuous_support_fraction=min(
                candidate.top_binding.continuous_support_fraction,
                candidate.bottom_binding.continuous_support_fraction,
            ),
            residual_sum_px=(
                candidate.top_binding.fit_residual_px
                + candidate.bottom_binding.fit_residual_px
            ),
            center_compatible=True,
            boundary_use=OutputBoundaryUse.ENCLOSING_SUPPORT_PAIR,
            enclosing_support_pair=candidate.pair,
            height_compatibility_px=fixed_height,
            shift_interval_px=top_full,
            center_interval_px=center_interval,
            parallel_direction_interval_degrees=(
                direction.full_angle_interval_degrees
            ),
            direction_provenance_ids=direction.selected_observation_ids,
            direct_provenance_ids=(
                candidate.top_binding.observation_id,
                candidate.bottom_binding.observation_id,
            ),
            independent_support_region_count=(
                candidate.independent_support_region_count
            ),
            longitudinal_support_domain_count=(
                candidate.longitudinal_support_domain_count
            ),
        )
        return enclosing_support_fit

    def support_resolution(
        receipt: CrossSearchReceipt,
    ) -> tuple[CrossFitCompetition | None, CrossSearchReceipt]:
        nonlocal support_receipt_accounted
        support_fit = unique_enclosing_support()
        evaluated = (
            0
            if support_competition is None or support_receipt_accounted
            else support_competition.evaluated_candidate_count
        )
        support_receipt_accounted = True
        receipt = replace(
            receipt,
            evaluated_fit_count=receipt.evaluated_fit_count + evaluated,
        )
        if (
            support_competition is not None
            and support_competition.status == SupportFitStatus.BOUND_EXCEEDED
        ) or receipt.evaluated_fit_count > receipt.evaluated_fit_bound:
            return (
                CrossFitCompetition(
                    template_id=inputs.template.template_id,
                    best=None,
                    runner_up=None,
                    status=CrossFitStatus.BOUND_EXCEEDED,
                    reason="cross evaluated-fit bound exceeded",
                    receipt=receipt,
                ),
                receipt,
            )
        receipt.validate_bounds()
        if support_fit is None:
            return None, receipt
        return (
            CrossFitCompetition(
                template_id=inputs.template.template_id,
                best=support_fit,
                runner_up=None,
                status=CrossFitStatus.RESOLVED,
                reason=None,
                receipt=receipt,
            ),
            receipt,
        )

    required_support_regions = inputs.minimum_shared_trace_support
    direct_candidates: list[_Candidate] = []
    candidates: list[_Candidate] = []
    compatible_pairs = 0
    # Sorted starts plus prefix maxima enumerate every interval overlap.  No
    # nearest-neighbour or used-bottom shortcut may discard a valid answer.
    if top and bottom:
        ordered_top = tuple(sorted(top, key=lambda item: (item.full_interval_px.minimum, str(item.observation_id))))
        ordered_bottom = tuple(sorted(bottom, key=lambda item: (item.full_interval_px.minimum, str(item.observation_id))))
        starts = tuple(item.full_interval_px.minimum for item in ordered_bottom)
        prefix_max: list[float] = []
        running = -math.inf
        for item in ordered_bottom:
            running = max(running, item.full_interval_px.maximum)
            prefix_max.append(running)
        for top_item in ordered_top:
            expected = _add(top_item.full_interval_px, fixed_height)
            start_index = bisect_left(prefix_max, expected.minimum)
            index = start_index
            while index < len(ordered_bottom) and starts[index] <= expected.maximum:
                bottom_item = ordered_bottom[index]
                candidate = _direct_candidate(
                    top_item,
                    bottom_item,
                    fixed_height=fixed_height,
                    canonical_height_px=float(inputs.canonical_fixed_height_px),
                    center=inputs.holder_short_axis_center_px,
                    minimum_shared_trace_support=inputs.minimum_shared_trace_support,
                    source_direction=inputs.source_direction,
                )
                if candidate is not None:
                    compatible_pairs += 1
                    direct_candidates.append(candidate)
                    if compatible_pairs > inputs.maximum_compatible_pairs:
                        receipt = _receipt(
                            inputs=inputs,
                            registered_runs=registered_runs,
                            fitted_observations=fitted_observations,
                            compatible_pairs=compatible_pairs,
                            single_side_inferences=0,
                            evaluated_fits=0,
                        )
                        return CrossFitCompetition(
                            template_id=inputs.template.template_id,
                            best=None,
                            runner_up=None,
                            status=CrossFitStatus.BOUND_EXCEEDED,
                            reason="cross compatible-pair bound exceeded",
                            receipt=receipt,
                        )
                index += 1
    spanning_top = tuple(
        item
        for item in top
        if item.role_authorized and item.source_spanning_continuous
    )
    spanning_bottom = tuple(
        item
        for item in bottom
        if item.role_authorized and item.source_spanning_continuous
    )
    template_spanning_top = tuple(
        item
        for item in top
        if item.role_authorized
        and _covers_template_domains(
            item,
            inputs.longitudinal_support_domains_px,
        )
    )
    template_spanning_bottom = tuple(
        item
        for item in bottom
        if item.role_authorized
        and _covers_template_domains(
            item,
            inputs.longitudinal_support_domains_px,
        )
    )
    if not direct_candidates:
        anchors = tuple(
            item
            for item in (*template_spanning_top, *template_spanning_bottom)
            if _single_candidate(
                item,
                fixed_height=fixed_height,
                canonical_height_px=float(inputs.canonical_fixed_height_px),
                center=inputs.holder_short_axis_center_px,
                source_direction=inputs.source_direction,
            )
            is not None
        )
        for anchor in anchors:
            opposites = bottom if anchor.role == BoundaryRole.TOP else top
            localized = _template_local_refinement_candidates(
                anchor,
                opposites,
                fixed_height=fixed_height,
                canonical_height_px=float(inputs.canonical_fixed_height_px),
                center=inputs.holder_short_axis_center_px,
                minimum_shared_trace_support=inputs.minimum_shared_trace_support,
                longitudinal_support_domains_px=(
                    inputs.longitudinal_support_domains_px
                ),
                source_direction=inputs.source_direction,
            )
            compatible_pairs += len(localized)
            direct_candidates.extend(localized)
            if compatible_pairs > inputs.maximum_compatible_pairs:
                receipt = _receipt(
                    inputs=inputs,
                    registered_runs=registered_runs,
                    fitted_observations=fitted_observations,
                    compatible_pairs=compatible_pairs,
                    single_side_inferences=0,
                    evaluated_fits=0,
                )
                return CrossFitCompetition(
                    template_id=inputs.template.template_id,
                    best=None,
                    runner_up=None,
                    status=CrossFitStatus.BOUND_EXCEEDED,
                    reason="cross compatible-pair bound exceeded",
                    receipt=receipt,
                )
    role_authorized_direct_pairs = tuple(
        candidate
        for candidate in direct_candidates
        if candidate.top.role_authorized
        and candidate.bottom.role_authorized
        and _longitudinal_domain_count(
            candidate.support_trace_coordinates_px,
            inputs.longitudinal_support_domains_px,
        )
        >= min(MINIMUM_INDEPENDENT_SUPPORT_REGIONS, inputs.template.count)
    )
    if spanning_top and spanning_bottom:
        # When both physical roles have source-spanning evidence, fragments do
        # not own either placement coordinate.  Only the two-sided spanning
        # closure may authorize a direct fixed-H placement.
        spanning_pairs = [
            item
            for item in direct_candidates
            if item.top.source_spanning_continuous
            and item.bottom.source_spanning_continuous
        ]
        candidates = spanning_pairs
    elif bool(spanning_top) != bool(spanning_bottom):
        # One domain-spanning role owns the cross coordinate.  A fragmented
        # opposite observation participates only when it directly closes H,
        # shared trace support, and direction with that anchor.  Otherwise
        # fixed H supplies the missing side.  Distinct direct closures remain
        # distinct answers and are never averaged.
        spanning = spanning_top or spanning_bottom
        spanning_ids = {item.observation_id for item in spanning}
        spanning_pairs = [
            candidate
            for candidate in direct_candidates
            if candidate.top.observation_id in spanning_ids
            or candidate.bottom.observation_id in spanning_ids
        ]
        candidates = spanning_pairs or [
            candidate
            for item in spanning
            if (candidate := _single_candidate(
                item,
                fixed_height=fixed_height,
                canonical_height_px=float(inputs.canonical_fixed_height_px),
                center=inputs.holder_short_axis_center_px,
                source_direction=inputs.source_direction,
            )) is not None
        ]
    elif role_authorized_direct_pairs:
        candidates = list(role_authorized_direct_pairs)
    elif template_spanning_top or template_spanning_bottom:
        # A role-authorized side observed inside every template frame domain
        # owns one source-wide side track even when it does not reach the raw
        # lane-domain endpoints.  Opposite local fragments can validate a
        # direct closure, but cannot create competing placements.  If both
        # roles cover the complete template, retain only their direct pairs;
        # otherwise fixed H infers the missing side.
        owner_ids = {
            item.observation_id
            for item in (*template_spanning_top, *template_spanning_bottom)
        }
        both_roles_span = bool(template_spanning_top and template_spanning_bottom)
        owner_pairs = [
            candidate
            for candidate in direct_candidates
            if candidate.top.observation_id in owner_ids
            and candidate.bottom.observation_id in owner_ids
        ]
        if both_roles_span and owner_pairs:
            candidates = owner_pairs
        else:
            candidates = [
                candidate
                for item in (*template_spanning_top, *template_spanning_bottom)
                if (candidate := _single_candidate(
                    item,
                    fixed_height=fixed_height,
                    canonical_height_px=float(inputs.canonical_fixed_height_px),
                    center=inputs.holder_short_axis_center_px,
                    source_direction=inputs.source_direction,
                )) is not None
            ]
    elif inputs.holder_short_axis_center_px is not None:
        # With no domain-spanning coordinate, retain the finite local direct
        # closures as one network problem.  Only a unique compatible network
        # whose combined shared support covers front/middle/back can own H and
        # cross position.  No individual fragment receives placement authority.
        if direct_candidates:
            candidates = list(direct_candidates)
            required_support_regions = SPATIAL_SUPPORT_REGION_COUNT
        else:
            candidates = [
                candidate
                for item in (*top, *bottom)
                if (candidate := _single_candidate(
                    item,
                    fixed_height=fixed_height,
                    canonical_height_px=float(inputs.canonical_fixed_height_px),
                    center=inputs.holder_short_axis_center_px,
                    source_direction=inputs.source_direction,
                )) is not None
            ]
    elif direct_candidates:
        candidates = list(direct_candidates)
    elif not top or not bottom:
        one_sided = top if top else bottom
        candidates = [
            candidate
            for item in one_sided
            if (candidate := _single_candidate(
                item,
                fixed_height=fixed_height,
                canonical_height_px=float(inputs.canonical_fixed_height_px),
                center=inputs.holder_short_axis_center_px,
                source_direction=inputs.source_direction,
            ))
            is not None
        ]
    candidate_count_before_track_dominance = len(candidates)
    candidates = _remove_contained_local_side_tracks(
        candidates,
        inputs.longitudinal_support_domains_px,
    )
    contained_side_track_basis = (
        len(candidates) == 1
        and candidate_count_before_track_dominance > len(candidates)
    )
    single_count = sum(not item.direct_pair for item in candidates)
    receipt = _receipt(
        inputs=inputs,
        registered_runs=registered_runs,
        fitted_observations=fitted_observations,
        compatible_pairs=compatible_pairs,
        single_side_inferences=single_count,
        evaluated_fits=len(candidates),
    )
    if len(candidates) > inputs.maximum_evaluated_fits:
        return CrossFitCompetition(
            template_id=inputs.template.template_id,
            best=None,
            runner_up=None,
            status=CrossFitStatus.BOUND_EXCEEDED,
            reason="cross evaluated-fit bound exceeded",
            receipt=receipt,
        )
    receipt.validate_bounds()
    if not candidates:
        support_result, receipt = support_resolution(receipt)
        if support_result is not None:
            return support_result
        reason = (
            "direct top/bottom evidence contradicts fixed height"
            if top and bottom
            else "single-side evidence lacks independent support or direction"
        )
        return CrossFitCompetition(
            template_id=inputs.template.template_id,
            best=None,
            runner_up=None,
            status=CrossFitStatus.UNRESOLVED,
            reason=reason,
            receipt=receipt,
        )

    # A unique two-sided enclosing support is stronger output authority than
    # a one-sided aperture whose opposite edge is only format-inferred. The
    # two boundary uses remain distinct and are never mixed.
    if all(not item.direct_pair for item in candidates):
        support_result, receipt = support_resolution(receipt)
        if support_result is not None:
            return support_result

    # The holder centre is not photo-boundary authority.  It may establish a
    # bounded opposite side for a single direct anchor and it remains a hard
    # compatibility fact for enclosing support, but it cannot select between
    # or veto complete role-authorized aperture pairs.  A unique direct pair
    # owns its measured cross offset; multiple legal pairs remain discrete
    # placements below.

    # Direction is never inferred from the template.  A complete directional
    # candidate wins over a candidate whose direction interval is unavailable;
    # if none is complete, retain evidence but refuse resolution.
    ready = tuple(item for item in candidates if item.direction_ready)
    if ready:
        candidates = list(ready)

    direct_candidates_for_selection = tuple(item for item in candidates if item.direct_pair)
    if direct_candidates_for_selection:
        candidates = list(direct_candidates_for_selection)
    groups = _group_candidates(candidates)
    representative_fits = tuple(
        _fit_from_group(
            group,
            template=inputs.template,
            fixed_height=fixed_height,
            lane_reference_trace_px=inputs.lane_reference_trace_px,
            registered_trace_coordinates_px=registered_trace_coordinates,
            longitudinal_support_domains_px=(
                inputs.longitudinal_support_domains_px
            ),
        )
        for group in groups
    )
    def has_role_authorized_pair(item: CrossFit) -> bool:
        return (
            item.direct_pair
            and item.role_authorized_pair_support_domain_count
            >= min(MINIMUM_INDEPENDENT_SUPPORT_REGIONS, inputs.template.count)
        )

    def has_source_spanning_direct_side(item: CrossFit) -> bool:
        return item.direct_pair and any(
            binding.source_spanning_continuous
            for binding in item.direct_bindings
        )

    authoritative = tuple(
        item
        for item in representative_fits
        if (
            has_role_authorized_pair(item)
            or has_source_spanning_direct_side(item)
            or (contained_side_track_basis and item.direct_pair)
            or (
                not item.direct_pair
                and item.independent_support_region_count
                >= required_support_regions
            )
        )
    )
    ordered_fits = authoritative or representative_fits
    best = ordered_fits[0] if ordered_fits else None
    runner = ordered_fits[1] if len(ordered_fits) > 1 else None
    if best is None:
        support_result, receipt = support_resolution(receipt)
        if support_result is not None:
            return support_result
        return CrossFitCompetition(
            template_id=inputs.template.template_id,
            best=None,
            runner_up=None,
            status=CrossFitStatus.UNRESOLVED,
            reason="cross fit has no physical group",
            receipt=receipt,
        )
    if len(authoritative) > 1 or (not authoritative and len(groups) > 1):
        support_result, receipt = support_resolution(receipt)
        if support_result is not None:
            return support_result
        return CrossFitCompetition(
            template_id=inputs.template.template_id,
            best=best,
            runner_up=runner,
            status=CrossFitStatus.UNRESOLVED,
            reason="non-equivalent cross fits remain",
            receipt=receipt,
        )
    if not authoritative:
        support_result, receipt = support_resolution(receipt)
        if support_result is not None:
            return support_result
        return CrossFitCompetition(
            template_id=inputs.template.template_id,
            best=best,
            runner_up=runner,
            status=CrossFitStatus.UNRESOLVED,
            reason="cross fit lacks independent spatial support",
            receipt=receipt,
        )
    if best.selected_direction is None:
        support_result, receipt = support_resolution(receipt)
        if support_result is not None:
            return support_result
        return CrossFitCompetition(
            template_id=inputs.template.template_id,
            best=best,
            runner_up=runner,
            status=CrossFitStatus.UNRESOLVED,
            reason="cross direction unavailable",
            receipt=receipt,
        )
    return CrossFitCompetition(
        template_id=inputs.template.template_id,
        best=best,
        runner_up=runner,
        status=CrossFitStatus.RESOLVED,
        reason=None,
        receipt=receipt,
    )


__all__ = ["fit_template_cross"]
