"""Orchestrate bounded fixed-height short-axis template fitting."""

from __future__ import annotations

from bisect import bisect_left
import math
from typing import Sequence

from ...domain import FiniteInterval, ObservationId
from .line_observations import PhotoBoundaryObservation
from .model import (
    BoundaryAxis,
    BoundaryRole,
    MINIMUM_INDEPENDENT_SUPPORT_REGIONS,
    SPATIAL_SUPPORT_REGION_COUNT,
)
from .observation_types import ProfileRun
from .template_cross_candidates import (
    _covers_template_domains,
    _direct_candidate,
    _fit_from_candidate,
    _fit_from_group,
    _group_candidates,
    _longitudinal_domain_count,
    _single_candidate,
)
from .template_cross_model import (
    CrossFitCompetition,
    CrossFitStatus,
    CrossRoleBinding,
    CrossSearchReceipt,
    TemplateCrossInput,
    _add,
    _observation_coordinate,
    _observation_direction,
)


def _coerce_bindings(
    direct: Sequence[CrossRoleBinding],
    runs: Sequence[ProfileRun],
    observations: Sequence[PhotoBoundaryObservation],
    *,
    lane_reference_trace_px: float,
    boundary_axis: BoundaryAxis,
) -> tuple[CrossRoleBinding, ...]:
    values = list(direct)
    used: set[ObservationId] = {item.observation_id for item in values}
    if runs:
        for run in runs:
            if any(item.run_id == run.run_id for item in values):
                continue
            matches = tuple(
                observation
                for observation in observations
                if observation.observation_id not in used
                and (
                    observation.observation_id == ObservationId(run.run_id)
                    or set(map(str, run.transition_ids)).intersection(
                        map(str, observation.transition_ids)
                    )
                )
            )
            if not matches and len(observations) == 1:
                matches = observations
            if len(matches) != 1:
                continue
            observation = matches[0]
            values.append(
                CrossRoleBinding.from_measurement(
                    run,
                    observation,
                    lane_reference_trace_px=lane_reference_trace_px,
                    boundary_axis=boundary_axis,
                )
            )
            used.add(observation.observation_id)
    if observations and not runs:
        for observation in observations:
            if observation.observation_id in used:
                continue
            role = getattr(observation, "role", None)
            if role not in {BoundaryRole.TOP, BoundaryRole.BOTTOM}:
                continue
            canonical, direction = _observation_direction(observation)
            values.append(
                CrossRoleBinding(
                    role=role,
                    run_id=f"observation:{observation.observation_id}",
                    observation_id=observation.observation_id,
                    coordinate_interval_px=_observation_coordinate(
                        observation,
                        lane_reference_trace_px=lane_reference_trace_px,
                        boundary_axis=boundary_axis,
                    ),
                    fit_residual_px=float(observation.fit_residual_px),
                    canonical_direction_degrees=canonical,
                    fit_direction_interval_degrees=getattr(
                        observation,
                        "fit_angle_interval_degrees",
                        None,
                    ),
                    full_direction_interval_degrees=direction,
                    independent_support_region_count=int(
                        getattr(observation, "independent_support_region_count", 0)
                    ),
                    source_spanning_continuous=bool(
                        getattr(observation, "source_spanning_continuous", False)
                    ),
                    role_authorized=(
                        float(
                            getattr(
                                observation,
                                (
                                    "left_background_preference_fraction"
                                    if role == BoundaryRole.TOP
                                    else "right_background_preference_fraction"
                                ),
                                0.0,
                            )
                        )
                        > 0.5
                    ),
                )
            )
            used.add(observation.observation_id)
    by_identity: dict[ObservationId, CrossRoleBinding] = {}
    for item in values:
        if item.observation_id in by_identity:
            raise ValueError("cross observation registered more than once")
        by_identity[item.observation_id] = item
    return tuple(
        sorted(
            by_identity.values(),
            key=lambda item: (item.coordinate_interval_px.center, str(item.observation_id)),
        )
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


def fit_template_cross(inputs: TemplateCrossInput) -> CrossFitCompetition:
    """Fit one fixed-H short-axis template with bounded interval search."""

    if not isinstance(inputs, TemplateCrossInput):
        raise TypeError("fit_template_cross requires TemplateCrossInput")
    top = _coerce_bindings(
        inputs.top_bindings,
        inputs.top_runs,
        inputs.top_observations,
        lane_reference_trace_px=inputs.lane_reference_trace_px,
        boundary_axis=inputs.boundary_axis,
    )
    bottom = _coerce_bindings(
        inputs.bottom_bindings,
        inputs.bottom_runs,
        inputs.bottom_observations,
        lane_reference_trace_px=inputs.lane_reference_trace_px,
        boundary_axis=inputs.boundary_axis,
    )
    if any(item.role != BoundaryRole.TOP for item in top):
        raise ValueError("top registration contains a non-top role")
    if any(item.role != BoundaryRole.BOTTOM for item in bottom):
        raise ValueError("bottom registration contains a non-bottom role")
    all_ids = tuple(item.observation_id for item in (*top, *bottom))
    if len(set(all_ids)) != len(all_ids):
        raise ValueError("cross observation registered more than once")
    registered_run_ids = {
        *(run.run_id for run in inputs.top_runs),
        *(run.run_id for run in inputs.bottom_runs),
        *(item.run_id for item in top),
        *(item.run_id for item in bottom),
    }
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
    required_support_regions = inputs.minimum_shared_trace_support

    direct_candidates: list[_Candidate] = []
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
                    parallel_direction_tolerance_degrees=(
                        inputs.parallel_direction_tolerance_degrees
                    ),
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
    spanning_top = tuple(item for item in top if item.source_spanning_continuous)
    spanning_bottom = tuple(item for item in bottom if item.source_spanning_continuous)
    template_spanning_top = tuple(
        item
        for item in top
        if _covers_template_domains(
            item,
            inputs.longitudinal_support_domains_px,
        )
    )
    template_spanning_bottom = tuple(
        item
        for item in bottom
        if _covers_template_domains(
            item,
            inputs.longitudinal_support_domains_px,
        )
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
        authorized_spanning_pairs = [
            item
            for item in spanning_pairs
            if item.top.role_authorized and item.bottom.role_authorized
        ]
        candidates = authorized_spanning_pairs or spanning_pairs
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
        authorized_spanning_pairs = [
            candidate
            for candidate in spanning_pairs
            if candidate.top.role_authorized and candidate.bottom.role_authorized
        ]
        spanning_pairs = authorized_spanning_pairs or spanning_pairs
        candidates = spanning_pairs or [
            candidate
            for item in spanning
            if (candidate := _single_candidate(
                item,
                fixed_height=fixed_height,
                canonical_height_px=float(inputs.canonical_fixed_height_px),
                center=inputs.holder_short_axis_center_px,
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
            ))
            is not None
        ]
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

    # Holder center is a hard closure.  If a direct candidate exists but all
    # are off-center, do not let support or residual clutter replace it.
    if inputs.holder_short_axis_center_px is not None:
        centered = tuple(item for item in candidates if item.center_compatible)
        if centered:
            candidates = list(centered)
        else:
            fits = tuple(
                _fit_from_candidate(
                    item,
                    template=inputs.template,
                    fixed_height=fixed_height,
                    lane_reference_trace_px=inputs.lane_reference_trace_px,
                )
                for item in candidates
            )
            return CrossFitCompetition(
                template_id=inputs.template.template_id,
                best=None,
                runner_up=fits[0] if fits else None,
                status=CrossFitStatus.UNRESOLVED,
                reason="cross holder center contradicts direct evidence",
                receipt=receipt,
            )

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
        return CrossFitCompetition(
            template_id=inputs.template.template_id,
            best=None,
            runner_up=None,
            status=CrossFitStatus.UNRESOLVED,
            reason="cross fit has no physical group",
            receipt=receipt,
        )
    if len(authoritative) > 1 or (not authoritative and len(groups) > 1):
        return CrossFitCompetition(
            template_id=inputs.template.template_id,
            best=best,
            runner_up=runner,
            status=CrossFitStatus.UNRESOLVED,
            reason="non-equivalent cross fits remain",
            receipt=receipt,
        )
    if not authoritative:
        return CrossFitCompetition(
            template_id=inputs.template.template_id,
            best=best,
            runner_up=runner,
            status=CrossFitStatus.UNRESOLVED,
            reason="cross fit lacks independent spatial support",
            receipt=receipt,
        )
    if best.selected_direction is None:
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
