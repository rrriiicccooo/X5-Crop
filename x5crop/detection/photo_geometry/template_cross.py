"""Orchestrate bounded fixed-height short-axis template fitting."""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import replace
from heapq import nsmallest
import math
from ...domain import EvidenceState, FiniteInterval, ObservationId
from .interval_math import (
    add as _add,
    intersect as _intersect,
    midpoint as _midpoint_interval,
)
from .model import (
    BoundaryRole,
    MINIMUM_INDEPENDENT_SUPPORT_REGIONS,
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    SPATIAL_SUPPORT_REGION_COUNT,
)
from .output_model import OutputBoundaryUse
from .source_geometry import SourceScanGeometry
from .template_cross_candidates import (
    _covers_template_domains,
    _direct_candidate,
    _fit_from_group,
    _group_candidates,
    _longitudinal_domain_count,
    _retained_grid_candidate,
    _single_candidate,
)
from .template_cross_model import (
    CrossEvidence,
    CrossFailureKind,
    CrossFit,
    CrossFitCompetition,
    CrossHeightInferenceBasis,
    CrossRetainedProposalBasis,
    CrossRoleBinding,
    CrossFitStatus,
    CrossWinnerBasis,
    CrossSearchReceipt,
    TemplateCrossInput,
)
from .template_cross_support import (
    SupportFitStatus,
    fit_enclosing_support,
)
from .template_aspect_ratio import (
    consume_aperture_aspect_ratio_for_cross,
    reconcile_direct_aperture_height,
    require_aperture_aspect_ratio_for_cross,
)
from .template_aspect_ratio_model import ApertureAspectRatioFailureKind


def calibrate_source_frame_height(
    source_geometry: SourceScanGeometry,
    competition: CrossFitCompetition,
) -> SourceScanGeometry:
    """Narrow source H only from one selected direct aperture pair."""

    fit = competition.best
    if (
        competition.status != CrossFitStatus.RESOLVED
        or fit is None
        or not fit.direct_pair
        or fit.boundary_use != OutputBoundaryUse.APERTURE_PAIR
    ):
        return source_geometry
    observation_ids = fit.bound_observation_ids
    if len(observation_ids) != 2:
        return source_geometry
    height_state = source_geometry.height_state.intersect_observed_extent(
        fit.height_compatibility_px,
        observation_ids=observation_ids,
    )
    return SourceScanGeometry.from_axis_states(
        source_geometry.frame_spec,
        source_geometry.width_state,
        height_state,
    )


def _receipt(
    *,
    inputs: TemplateCrossInput,
    registered_top_runs: int,
    registered_bottom_runs: int,
    fitted_observations: int,
    compatible_pairs: int,
    single_side_inferences: int,
    evaluated_fits: int,
) -> CrossSearchReceipt:
    return CrossSearchReceipt(
        registered_top_run_count=registered_top_runs,
        registered_bottom_run_count=registered_bottom_runs,
        fitted_observation_count=fitted_observations,
        compatible_pair_count=compatible_pairs,
        single_side_inference_count=single_side_inferences,
        evaluated_fit_count=evaluated_fits,
        registered_run_bound_per_role=(
            inputs.maximum_registered_runs_per_role
        ),
        fitted_observation_bound=inputs.maximum_fitted_observations,
        compatible_pair_bound=inputs.maximum_compatible_pairs,
        evaluated_fit_bound=inputs.maximum_evaluated_fits,
    )


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
    registered_top_runs = max(
        int(inputs.registered_top_run_count),
        len({item.run_id for item in top}),
    )
    registered_bottom_runs = max(
        int(inputs.registered_bottom_run_count),
        len({item.run_id for item in bottom}),
    )
    fitted_observations = max(
        int(inputs.fitted_observation_count),
        len(all_ids),
    )
    aspect_ratio_authority = inputs.aperture_aspect_ratio_authority
    empty_receipt = lambda: _receipt(
        inputs=inputs,
        registered_top_runs=registered_top_runs,
        registered_bottom_runs=registered_bottom_runs,
        fitted_observations=fitted_observations,
        compatible_pairs=0,
        single_side_inferences=0,
        evaluated_fits=0,
    )
    if (
        registered_top_runs > inputs.maximum_registered_runs_per_role
        or registered_bottom_runs > inputs.maximum_registered_runs_per_role
        or fitted_observations > inputs.maximum_fitted_observations
    ):
        return CrossFitCompetition(
            template_id=inputs.template.template_id,
            best=None,
            runner_up=None,
            status=CrossFitStatus.BOUND_EXCEEDED,
            winner_basis=None,
            reason="cross registration bound exceeded",
            failure_kind=CrossFailureKind.REGISTRATION_BOUND_EXCEEDED,
            receipt=empty_receipt(),
            aperture_aspect_ratio_authority=aspect_ratio_authority,
        )
    if not top and not bottom:
        return CrossFitCompetition(
            template_id=inputs.template.template_id,
            best=None,
            runner_up=None,
            status=CrossFitStatus.UNRESOLVED,
            winner_basis=None,
            reason="cross fit requires top or bottom direct evidence",
            failure_kind=CrossFailureKind.DIRECT_EVIDENCE_UNAVAILABLE,
            receipt=empty_receipt(),
            aperture_aspect_ratio_authority=aspect_ratio_authority,
        )
    fixed_height = inputs.fixed_height_px
    assert isinstance(fixed_height, FiniteInterval)
    inferred_height = (
        aspect_ratio_authority.effective_height_px
        if aspect_ratio_authority.state == EvidenceState.SUPPORTED
        else None
    )
    inferred_canonical_height = (
        aspect_ratio_authority.canonical_height_px
        if inferred_height is not None
        else None
    )

    def inferred_candidate(
        binding,
        *,
        template_domain_complete: bool = False,
    ):
        height = fixed_height if inferred_height is None else inferred_height
        canonical_height = (
            inferred_canonical_height
            if inferred_canonical_height is not None
            else float(inputs.canonical_fixed_height_px)
        )
        basis = (
            CrossHeightInferenceBasis.APERTURE_ASPECT_RATIO
            if inferred_height is not None
            else CrossHeightInferenceBasis.CALIBRATED_FORMAT_HEIGHT
        )
        return _single_candidate(
            binding,
            fixed_height=height,
            canonical_height_px=canonical_height,
            source_direction=inputs.source_direction,
            template_domain_complete=template_domain_complete,
            height_inference_basis=basis,
        )
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

    def retained_cross_proposal_fits() -> tuple[
        tuple[CrossFit, ...],
        CrossRetainedProposalBasis | None,
        int,
    ]:
        """Retain one bounded proposal and runner without granting authority."""

        height = fixed_height if inferred_height is None else inferred_height
        canonical_height = (
            inferred_canonical_height
            if inferred_canonical_height is not None
            else float(inputs.canonical_fixed_height_px)
        )
        basis = (
            CrossHeightInferenceBasis.APERTURE_ASPECT_RATIO
            if inferred_height is not None
            else CrossHeightInferenceBasis.CALIBRATED_FORMAT_HEIGHT
        )
        authorized_top = tuple(
            sorted(
                (
                    item
                    for item in top
                    if item.role_authorized
                    and item.evidence == CrossEvidence.DIRECT
                ),
                key=lambda item: (
                    item.full_interval_px.minimum,
                    item.full_interval_px.maximum,
                    str(item.observation_id),
                ),
            )
        )
        authorized_bottom = tuple(
            sorted(
                (
                    item
                    for item in bottom
                    if item.role_authorized
                    and item.evidence == CrossEvidence.DIRECT
                ),
                key=lambda item: (
                    -item.full_interval_px.maximum,
                    -item.full_interval_px.minimum,
                    str(item.observation_id),
                ),
            )
        )
        anchors: list[CrossRoleBinding] = []
        retained_basis = (
            CrossRetainedProposalBasis
            .CALIBRATED_HEIGHT_FROM_OUTERMOST_REGISTERED_ROLE
        )
        if authorized_top:
            anchors.append(authorized_top[0])
        if authorized_bottom:
            anchors.append(authorized_bottom[0])
        if len(anchors) < 2:
            remaining = (
                authorized_top[1:]
                if authorized_top
                else authorized_bottom[1:]
            )
            anchors.extend(remaining[: 2 - len(anchors)])

        if not anchors:
            # A role-specific registered query may produce a stable physical
            # line while background-sidedness is unavailable, for example
            # where one aperture side leaves the TIFF.  Three independent
            # support regions plus bounded direction may position a Review
            # proposal, but never grant aperture-role or candidate authority.
            hypothesis_top = tuple(
                sorted(
                    (
                        item
                        for item in top
                        if not item.role_authorized
                        and item.evidence == CrossEvidence.DIRECT
                        and item.independent_support_region_count
                        >= SPATIAL_SUPPORT_REGION_COUNT
                    ),
                    key=lambda item: (
                        item.full_interval_px.minimum,
                        item.full_interval_px.maximum,
                        str(item.observation_id),
                    ),
                )
            )
            hypothesis_bottom = tuple(
                sorted(
                    (
                        item
                        for item in bottom
                        if not item.role_authorized
                        and item.evidence == CrossEvidence.DIRECT
                        and item.independent_support_region_count
                        >= SPATIAL_SUPPORT_REGION_COUNT
                    ),
                    key=lambda item: (
                        -item.full_interval_px.maximum,
                        -item.full_interval_px.minimum,
                        str(item.observation_id),
                    ),
                )
            )
            if hypothesis_top:
                anchors.append(hypothesis_top[0])
            if hypothesis_bottom:
                anchors.append(hypothesis_bottom[0])
            if anchors:
                retained_basis = (
                    CrossRetainedProposalBasis
                    .CALIBRATED_HEIGHT_FROM_REGISTERED_ROLE_HYPOTHESIS
                )

        registered_pair_candidates = tuple(
            nsmallest(
                2,
                (
                    candidate
                    for candidate in direct_candidates
                    if candidate.top.evidence == CrossEvidence.DIRECT
                    and candidate.bottom.evidence == CrossEvidence.DIRECT
                ),
                key=lambda candidate: (
                    # The low-side direct aperture role is the conservative
                    # Cross anchor for an unresolved Review proposal. Local
                    # pairs farther inside the film remain runners and
                    # counterevidence; a short parallel fragment cannot
                    # reposition the complete proposal.
                    candidate.top.fit_interval_px.minimum,
                    candidate.top.fit_interval_px.maximum,
                    abs(
                        candidate.bottom.fit_interval_px.center
                        - candidate.top.fit_interval_px.center
                        - canonical_height
                    ),
                    (
                        math.inf
                        if candidate.top.fit_direction_interval_degrees is None
                        or candidate.bottom.fit_direction_interval_degrees is None
                        else abs(
                            candidate.top.fit_direction_interval_degrees.center
                            - candidate.bottom.fit_direction_interval_degrees.center
                        )
                    ),
                    str(candidate.top.observation_id),
                    str(candidate.bottom.observation_id),
                ),
            )
        )
        if registered_pair_candidates:
            retained_pairs = registered_pair_candidates
            return (
                tuple(
                    _fit_from_group(
                        (candidate,),
                        template=inputs.template,
                        lane_reference_trace_px=(
                            inputs.lane_reference_trace_px
                        ),
                        registered_trace_coordinates_px=(
                            registered_trace_coordinates
                        ),
                        longitudinal_support_domains_px=(
                            inputs.longitudinal_support_domains_px
                        ),
                    )
                    for candidate in retained_pairs
                ),
                CrossRetainedProposalBasis
                .OUTERMOST_ADMISSIBLE_REGISTERED_ROLE_PAIR,
                sum(
                    candidate not in candidates
                    for candidate in retained_pairs
                ),
            )

        fits: list[CrossFit] = []
        for anchor in anchors:
            candidate = _retained_grid_candidate(
                anchor,
                fixed_height=height,
                canonical_height_px=canonical_height,
                height_inference_basis=basis,
                source_direction=inputs.source_direction,
            )
            if candidate is None:
                continue
            fit = _fit_from_group(
                (candidate,),
                template=inputs.template,
                lane_reference_trace_px=inputs.lane_reference_trace_px,
                registered_trace_coordinates_px=registered_trace_coordinates,
                longitudinal_support_domains_px=(
                    inputs.longitudinal_support_domains_px
                ),
            )
            if any(
                existing.top_full_interval_px == fit.top_full_interval_px
                and existing.bottom_full_interval_px
                == fit.bottom_full_interval_px
                for existing in fits
            ):
                continue
            fits.append(fit)
        return (
            tuple(fits),
            retained_basis if fits else None,
            len(fits),
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
        center = midpoint.center
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
            boundary_use=OutputBoundaryUse.ENCLOSING_SUPPORT_PAIR,
            pair_support_mode=None,
            enclosing_support_pair=candidate.pair,
            height_compatibility_px=fixed_height,
            shift_interval_px=top_full,
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
                    winner_basis=None,
                    reason="cross evaluated-fit bound exceeded",
                    failure_kind=(
                        CrossFailureKind.EVALUATED_FIT_BOUND_EXCEEDED
                    ),
                    receipt=receipt,
                    aperture_aspect_ratio_authority=aspect_ratio_authority,
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
                winner_basis=CrossWinnerBasis.UNIQUE_ENCLOSING_SUPPORT,
                reason=None,
                failure_kind=None,
                receipt=receipt,
                aperture_aspect_ratio_authority=(
                    inputs.aperture_aspect_ratio_authority
                ),
            ),
            receipt,
        )

    def unresolved(
        receipt: CrossSearchReceipt,
        reason: str,
        failure_kind: CrossFailureKind,
        *,
        best: CrossFit | None = None,
        runner_up: CrossFit | None = None,
        retained_proposal_basis: CrossRetainedProposalBasis | None = None,
    ) -> CrossFitCompetition:
        support_result, receipt = support_resolution(receipt)
        if support_result is not None:
            return support_result
        return CrossFitCompetition(
            template_id=inputs.template.template_id,
            best=best,
            runner_up=runner_up,
            status=CrossFitStatus.UNRESOLVED,
            winner_basis=None,
            reason=reason,
            failure_kind=failure_kind,
            receipt=receipt,
            retained_proposal_basis=retained_proposal_basis,
            aperture_aspect_ratio_authority=aspect_ratio_authority,
        )

    required_support_regions = inputs.minimum_shared_trace_support
    direct_candidates: list[_Candidate] = []
    candidates: list[_Candidate] = []
    compatible_pairs = 0
    pair_failure_kinds: set[CrossFailureKind] = set()
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
                candidate, pair_failure_kind = _direct_candidate(
                    top_item,
                    bottom_item,
                    fixed_height=fixed_height,
                    canonical_height_px=float(inputs.canonical_fixed_height_px),
                    minimum_shared_trace_support=inputs.minimum_shared_trace_support,
                    longitudinal_support_domains_px=(
                        inputs.longitudinal_support_domains_px
                    ),
                    source_direction=inputs.source_direction,
                )
                if pair_failure_kind is not None:
                    pair_failure_kinds.add(pair_failure_kind)
                if candidate is not None:
                    compatible_pairs += 1
                    direct_candidates.append(candidate)
                    if compatible_pairs > inputs.maximum_compatible_pairs:
                        receipt = _receipt(
                            inputs=inputs,
                            registered_top_runs=registered_top_runs,
                            registered_bottom_runs=registered_bottom_runs,
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
                            winner_basis=None,
                            reason="cross compatible-pair bound exceeded",
                            failure_kind=(
                                CrossFailureKind
                                .COMPATIBLE_PAIR_BOUND_EXCEEDED
                            ),
                            receipt=receipt,
                            aperture_aspect_ratio_authority=(
                                aspect_ratio_authority
                            ),
                        )
                index += 1
    def has_template_pair_authority(candidate: _Candidate) -> bool:
        if not candidate.top.role_authorized or not candidate.bottom.role_authorized:
            return False
        domain_count = _longitudinal_domain_count(
            candidate.authority_trace_coordinates_px,
            inputs.longitudinal_support_domains_px,
        )
        return domain_count >= min(
            SPATIAL_SUPPORT_REGION_COUNT,
            inputs.template.count,
        ) or (
            domain_count
            >= min(MINIMUM_INDEPENDENT_SUPPORT_REGIONS, inputs.template.count)
            and (
                _covers_template_domains(
                    candidate.top,
                    inputs.longitudinal_support_domains_px,
                )
                or _covers_template_domains(
                    candidate.bottom,
                    inputs.longitudinal_support_domains_px,
                )
            )
        )

    # A template-wide pair cannot obtain authority by ignoring a strictly
    # farther-out direct role that closes against the same opposite boundary.
    # The farther-out observation remains a negative veto when it lacks global
    # pair authority; when both pairs are globally complete, both remain legal
    # placements and ordinary competition keeps them unresolved.
    outward_contested_pair_ids: set[
        tuple[ObservationId, ObservationId]
    ] = set()
    minimum_local_top_maximum_by_bottom: dict[ObservationId, float] = {}
    maximum_local_bottom_minimum_by_top: dict[ObservationId, float] = {}
    for candidate in direct_candidates:
        if has_template_pair_authority(candidate):
            continue
        bottom_id = candidate.bottom.observation_id
        top_id = candidate.top.observation_id
        minimum_local_top_maximum_by_bottom[bottom_id] = min(
            minimum_local_top_maximum_by_bottom.get(bottom_id, math.inf),
            candidate.top.full_interval_px.maximum,
        )
        maximum_local_bottom_minimum_by_top[top_id] = max(
            maximum_local_bottom_minimum_by_top.get(top_id, -math.inf),
            candidate.bottom.full_interval_px.minimum,
        )
    for candidate in direct_candidates:
        if not has_template_pair_authority(candidate):
            continue
        top_counter = minimum_local_top_maximum_by_bottom.get(
            candidate.bottom.observation_id,
            math.inf,
        )
        bottom_counter = maximum_local_bottom_minimum_by_top.get(
            candidate.top.observation_id,
            -math.inf,
        )
        if (
            top_counter < candidate.top.full_interval_px.minimum - 1.0e-9
            or bottom_counter
            > candidate.bottom.full_interval_px.maximum + 1.0e-9
        ):
            outward_contested_pair_ids.add(
                (
                    candidate.top.observation_id,
                    candidate.bottom.observation_id,
                )
            )
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
    role_authorized_direct_pairs = tuple(
        candidate
        for candidate in direct_candidates
        if has_template_pair_authority(candidate)
        and (
            candidate.top.observation_id,
            candidate.bottom.observation_id,
        )
        not in outward_contested_pair_ids
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
        # One source-spanning role owns the cross coordinate. Fixed H supplies
        # the opposite side when several local fragments remain. One unique
        # direct closure may retain its measured native height, but ambiguous
        # fragments cannot move geometry fixed by whole-strip evidence.
        spanning = spanning_top or spanning_bottom
        spanning_ids = {item.observation_id for item in spanning}
        all_spanning_pairs = [
            candidate
            for candidate in direct_candidates
            if candidate.top.observation_id in spanning_ids
            or candidate.bottom.observation_id in spanning_ids
        ]
        complete_spanning_pairs = [
            candidate
            for candidate in all_spanning_pairs
            if (
                candidate.top.observation_id in spanning_ids
                and _covers_template_domains(
                    candidate.bottom,
                    inputs.longitudinal_support_domains_px,
                )
            )
            or (
                candidate.bottom.observation_id in spanning_ids
                and _covers_template_domains(
                    candidate.top,
                    inputs.longitudinal_support_domains_px,
                )
            )
        ]
        candidates = (
            complete_spanning_pairs
            if complete_spanning_pairs
            else [
                candidate
                for item in spanning
                if (candidate := inferred_candidate(item)) is not None
            ]
        )
    elif role_authorized_direct_pairs:
        candidates = list(role_authorized_direct_pairs)
    elif template_spanning_top or template_spanning_bottom:
        # A role-authorized side with a direct trace in every selected frame
        # domain owns one template-wide side track even when it does not reach
        # the raw lane-domain endpoints.  When at least three selected domains
        # are present, this per-domain registered-lattice fact can authorize
        # fixed-H inference even when the aggregate support ledger reports only
        # two regions; ordinary local two-region fragments still use the
        # generic threshold.
        # Opposite local fragments can validate a direct closure, but cannot
        # create competing placements.  If both roles cover the complete
        # template, retain only their direct pairs; otherwise fixed H infers
        # the missing side.
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
                if (candidate := inferred_candidate(
                    item,
                    template_domain_complete=(
                        len(inputs.longitudinal_support_domains_px)
                        >= SPATIAL_SUPPORT_REGION_COUNT
                        and _covers_template_domains(
                            item,
                            inputs.longitudinal_support_domains_px,
                        )
                    ),
                )) is not None
            ]
    elif direct_candidates:
        candidates = list(direct_candidates)
    elif not top or not bottom:
        one_sided = top if top else bottom
        candidates = [
            candidate
            for item in one_sided
            if (candidate := inferred_candidate(item))
            is not None
        ]
    single_count = sum(not item.direct_pair for item in candidates)
    receipt = _receipt(
        inputs=inputs,
        registered_top_runs=registered_top_runs,
        registered_bottom_runs=registered_bottom_runs,
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
            winner_basis=None,
            reason="cross evaluated-fit bound exceeded",
            failure_kind=CrossFailureKind.EVALUATED_FIT_BOUND_EXCEEDED,
            receipt=receipt,
            aperture_aspect_ratio_authority=aspect_ratio_authority,
        )
    receipt.validate_bounds()

    def unresolved_with_retained_proposal(
        reason: str,
        failure_kind: CrossFailureKind,
        *,
        fallback_best: CrossFit | None = None,
        fallback_runner: CrossFit | None = None,
    ) -> CrossFitCompetition:
        """Keep local hypotheses as counterevidence, not proposal geometry."""

        (
            retained_fits,
            retained_basis,
            added_evaluation_count,
        ) = retained_cross_proposal_fits()
        if not retained_fits:
            return unresolved(
                receipt,
                reason,
                failure_kind,
                best=fallback_best,
                runner_up=fallback_runner,
            )
        retained_receipt = replace(
            receipt,
            single_side_inference_count=(
                receipt.single_side_inference_count
                + sum(item.single_side_inferred for item in retained_fits)
            ),
            evaluated_fit_count=(
                receipt.evaluated_fit_count + added_evaluation_count
            ),
        )
        if (
            retained_receipt.evaluated_fit_count
            > retained_receipt.evaluated_fit_bound
        ):
            return CrossFitCompetition(
                template_id=inputs.template.template_id,
                best=None,
                runner_up=None,
                status=CrossFitStatus.BOUND_EXCEEDED,
                winner_basis=None,
                reason="cross evaluated-fit bound exceeded",
                failure_kind=CrossFailureKind.EVALUATED_FIT_BOUND_EXCEEDED,
                receipt=retained_receipt,
                aperture_aspect_ratio_authority=aspect_ratio_authority,
            )
        retained_receipt.validate_bounds()
        retained_best = retained_fits[0]
        retained_runner = next(
            (
                item
                for item in (
                    *retained_fits[1:],
                    fallback_best,
                    fallback_runner,
                )
                if item is not None
                and (
                    item.top_full_interval_px
                    != retained_best.top_full_interval_px
                    or item.bottom_full_interval_px
                    != retained_best.bottom_full_interval_px
                    or item.bound_observation_ids
                    != retained_best.bound_observation_ids
                )
            ),
            None,
        )
        return unresolved(
            retained_receipt,
            reason,
            failure_kind,
            best=retained_best,
            runner_up=retained_runner,
            retained_proposal_basis=retained_basis,
        )

    if not candidates:
        if outward_contested_pair_ids:
            failure_kind = CrossFailureKind.OUTWARD_ROLE_COUNTEREVIDENCE
            reason = "direct cross role has strictly outward counterevidence"
        elif direct_candidates:
            failure_kind = CrossFailureKind.PHYSICAL_GROUP_UNAVAILABLE
            reason = "direct cross evidence lacks one admissible physical group"
        elif top and bottom:
            failure_kind = next(
                (
                    kind
                    for kind in (
                        CrossFailureKind.PAIR_SUPPORT_UNAVAILABLE,
                        CrossFailureKind.DIRECTION_INCOMPATIBLE,
                        CrossFailureKind.DIRECT_ROLE_AUTHORITY_UNAVAILABLE,
                        CrossFailureKind.FIXED_HEIGHT_INCOMPATIBLE,
                    )
                    if kind in pair_failure_kinds
                ),
                CrossFailureKind.FIXED_HEIGHT_INCOMPATIBLE,
            )
            reason = {
                CrossFailureKind.PAIR_SUPPORT_UNAVAILABLE: (
                    "direct top/bottom pair lacks shared or complete-domain support"
                ),
                CrossFailureKind.DIRECTION_INCOMPATIBLE: (
                    "direct top/bottom directions are incompatible"
                ),
                CrossFailureKind.DIRECT_ROLE_AUTHORITY_UNAVAILABLE: (
                    "direct top/bottom pair lacks role authority"
                ),
                CrossFailureKind.FIXED_HEIGHT_INCOMPATIBLE: (
                    "direct top/bottom evidence contradicts fixed height"
                ),
            }[failure_kind]
        elif any(
            not item.role_authorized for item in (*top, *bottom)
        ):
            failure_kind = CrossFailureKind.DIRECT_ROLE_AUTHORITY_UNAVAILABLE
            reason = "registered cross role lacks direct boundary authority"
        else:
            failure_kind = CrossFailureKind.INDEPENDENT_SUPPORT_UNAVAILABLE
            reason = "single-side evidence lacks independent support or direction"
        if failure_kind in {
            CrossFailureKind.FIXED_HEIGHT_INCOMPATIBLE,
            CrossFailureKind.OUTWARD_ROLE_COUNTEREVIDENCE,
        }:
            return unresolved(receipt, reason, failure_kind)
        return unresolved_with_retained_proposal(reason, failure_kind)

    # A unique two-sided enclosing support is stronger output authority than
    # a one-sided aperture whose opposite edge is only format-inferred. The
    # two boundary uses remain distinct and are never mixed.
    if all(not item.direct_pair for item in candidates):
        support_result, receipt = support_resolution(receipt)
        if support_result is not None:
            return support_result

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
            lane_reference_trace_px=inputs.lane_reference_trace_px,
            registered_trace_coordinates_px=registered_trace_coordinates,
            longitudinal_support_domains_px=(
                inputs.longitudinal_support_domains_px
            ),
        )
        for group in groups
    )

    def direct_pair_id(
        item: CrossFit,
    ) -> tuple[ObservationId, ObservationId] | None:
        if not item.direct_pair or len(item.direct_bindings) != 2:
            return None
        top_binding = next(
            binding
            for binding in item.direct_bindings
            if binding.role == BoundaryRole.TOP
        )
        bottom_binding = next(
            binding
            for binding in item.direct_bindings
            if binding.role == BoundaryRole.BOTTOM
        )
        return (
            top_binding.observation_id,
            bottom_binding.observation_id,
        )

    def has_role_authorized_pair(item: CrossFit) -> bool:
        return (
            item.direct_pair
            and direct_pair_id(item) not in outward_contested_pair_ids
            and (
                item.role_authorized_pair_support_domain_count
                >= min(SPATIAL_SUPPORT_REGION_COUNT, inputs.template.count)
                or any(
                    _covers_template_domains(
                        binding,
                        inputs.longitudinal_support_domains_px,
                    )
                    for binding in item.direct_bindings
                )
            )
        )

    def has_source_spanning_direct_side(item: CrossFit) -> bool:
        if (
            not item.direct_pair
            or direct_pair_id(item) in outward_contested_pair_ids
        ):
            return False
        top_binding = next(
            binding
            for binding in item.direct_bindings
            if binding.role == BoundaryRole.TOP
        )
        bottom_binding = next(
            binding
            for binding in item.direct_bindings
            if binding.role == BoundaryRole.BOTTOM
        )
        return (
            top_binding.source_spanning_continuous
            and bottom_binding.source_spanning_continuous
        ) or (
            top_binding.source_spanning_continuous
            and _covers_template_domains(
                bottom_binding,
                inputs.longitudinal_support_domains_px,
            )
        ) or (
            bottom_binding.source_spanning_continuous
            and _covers_template_domains(
                top_binding,
                inputs.longitudinal_support_domains_px,
            )
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
        return unresolved(
            receipt,
            "cross fit has no physical group",
            CrossFailureKind.PHYSICAL_GROUP_UNAVAILABLE,
        )
    if outward_contested_pair_ids and not authoritative:
        return unresolved(
            receipt,
            "direct cross role has strictly outward counterevidence",
            CrossFailureKind.OUTWARD_ROLE_COUNTEREVIDENCE,
            best=best,
            runner_up=runner,
        )
    if len(authoritative) > 1:
        return unresolved(
            receipt,
            "non-equivalent cross fits remain",
            CrossFailureKind.NON_EQUIVALENT_FITS,
            best=best,
            runner_up=runner,
        )
    if not authoritative and len(groups) > 1:
        return unresolved_with_retained_proposal(
            "non-equivalent cross fits remain",
            CrossFailureKind.NON_EQUIVALENT_FITS,
            fallback_best=best,
            fallback_runner=runner,
        )
    if not authoritative:
        return unresolved_with_retained_proposal(
            "cross fit lacks independent spatial support",
            CrossFailureKind.INDEPENDENT_SUPPORT_UNAVAILABLE,
            fallback_best=best,
            fallback_runner=runner,
        )
    if best.selected_direction is None:
        return unresolved(
            receipt,
            "cross direction unavailable",
            CrossFailureKind.DIRECTION_UNAVAILABLE,
            best=best,
            runner_up=runner,
        )
    if (
        best.height_inference_basis
        == CrossHeightInferenceBasis.CALIBRATED_FORMAT_HEIGHT
        and aspect_ratio_authority.state == EvidenceState.CONTRADICTED
    ):
        blocked_aspect_ratio = require_aperture_aspect_ratio_for_cross(
            aspect_ratio_authority
        )
        return CrossFitCompetition(
            template_id=inputs.template.template_id,
            best=best,
            runner_up=runner,
            status=CrossFitStatus.UNRESOLVED,
            winner_basis=None,
            reason=blocked_aspect_ratio.failure_detail,
            failure_kind=CrossFailureKind.APERTURE_ASPECT_RATIO_CONFLICT,
            receipt=receipt,
            aperture_aspect_ratio_authority=blocked_aspect_ratio,
        )
    resolved_aspect_ratio_authority = aspect_ratio_authority
    if best.direct_pair:
        if (
            best.boundary_use == OutputBoundaryUse.APERTURE_PAIR
            and best.height_compatibility_px is not None
        ):
            resolved_aspect_ratio_authority = reconcile_direct_aperture_height(
                aspect_ratio_authority,
                best.height_compatibility_px,
            )
            if (
                resolved_aspect_ratio_authority.failure_kind
                == ApertureAspectRatioFailureKind.DIRECT_CONFLICT
            ):
                return CrossFitCompetition(
                    template_id=inputs.template.template_id,
                    best=best,
                    runner_up=runner,
                    status=CrossFitStatus.UNRESOLVED,
                    winner_basis=None,
                    reason=resolved_aspect_ratio_authority.failure_detail,
                    failure_kind=(
                        CrossFailureKind.APERTURE_ASPECT_RATIO_CONFLICT
                    ),
                    receipt=receipt,
                    aperture_aspect_ratio_authority=(
                        resolved_aspect_ratio_authority
                    ),
                )
    elif (
        best.height_inference_basis
        == CrossHeightInferenceBasis.APERTURE_ASPECT_RATIO
    ):
        resolved_aspect_ratio_authority = (
            consume_aperture_aspect_ratio_for_cross(
                aspect_ratio_authority
            )
        )
    return CrossFitCompetition(
        template_id=inputs.template.template_id,
        best=best,
        runner_up=runner,
        status=CrossFitStatus.RESOLVED,
        winner_basis=CrossWinnerBasis.ONLY_AUTHORITATIVE_FIT,
        reason=None,
        failure_kind=None,
        receipt=receipt,
        aperture_aspect_ratio_authority=(
            resolved_aspect_ratio_authority
        ),
    )
