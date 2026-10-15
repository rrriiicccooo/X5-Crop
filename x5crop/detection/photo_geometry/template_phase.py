"""Sequence phase pass flow, retained proposals and finalization."""

from __future__ import annotations

from dataclasses import replace

from .observation_types import BoundaryEdgeObservation
from .template_model import SequenceBindingUse, TemplateSearchReceipt
from .template_frame_width import SourceFrameWidthAuthority
from .template_adjacency_coverage import assess_adjacency_observation_coverage
from .template_adjacency_topology import observe_adjacency_continuity
from .template_phase_model import (
    PhaseFailureKind,
    PhaseFitResult,
    PhaseFitStatus,
    PhaseRetainedProposalBasis,
    TemplatePhaseCandidateCompetition,
    TemplatePhaseInput,
    _TerminalPhaseDiagnostic,
)
from .template_native_retention import carry_native_phase_retention
from .template_source_clipped import carry_source_clipped_phase_retention
from . import (
    template_phase_candidate_model as _candidate_model,
    template_phase_competition as _competition,
    template_phase_refinement as _refinement,
    template_phase_state as _state,
)


def _aggregate_phase_work(
    result: PhaseFitResult,
    *prior: TemplateSearchReceipt,
    adjacency_relation_evaluation_count: int | None = None,
) -> PhaseFitResult:
    receipts = (*prior, result.receipt)
    receipt = TemplateSearchReceipt(
        observation_count=result.receipt.observation_count,
        role_count=result.receipt.role_count,
        phase_lookup_count=sum(item.phase_lookup_count for item in receipts),
        role_binding_count=sum(item.role_binding_count for item in receipts),
        adjacency_relation_evaluation_count=(
            sum(
                item.adjacency_relation_evaluation_count
                for item in receipts
            )
            if adjacency_relation_evaluation_count is None
            else adjacency_relation_evaluation_count
        ),
        local_refinement_lookup_count=sum(
            item.local_refinement_lookup_count for item in receipts
        ),
        local_refinement_binding_count=sum(
            item.local_refinement_binding_count for item in receipts
        ),
        phase_hypothesis_count=sum(
            item.phase_hypothesis_count for item in receipts
        ),
        phase_offset_lookup_count=sum(
            item.phase_offset_lookup_count for item in receipts
        ),
        direct_observation_count=result.receipt.direct_observation_count,
        inferred_role_count=result.receipt.inferred_role_count,
        peak_temporary_bytes=max(
            item.peak_temporary_bytes for item in receipts
        ),
        fit_pass_count=sum(item.fit_pass_count for item in receipts),
        separator_lattice_hypothesis_count=sum(
            item.separator_lattice_hypothesis_count for item in receipts
        ),
        candidate_direct_role_authority_evaluation_count=sum(
            item.candidate_direct_role_authority_evaluation_count
            for item in receipts
        ),
        candidate_direct_role_authority_terminal_count=sum(
            item.candidate_direct_role_authority_terminal_count
            for item in receipts
        ),
        candidate_direct_role_authority_role_check_count=sum(
            item.candidate_direct_role_authority_role_check_count
            for item in receipts
        ),
        candidate_direct_role_projection_evaluation_count=sum(
            item.candidate_direct_role_projection_evaluation_count
            for item in receipts
        ),
        candidate_direct_role_projection_success_count=sum(
            item.candidate_direct_role_projection_success_count
            for item in receipts
        ),
        candidate_direct_role_projection_binding_count=sum(
            item.candidate_direct_role_projection_binding_count
            for item in receipts
        ),
        candidate_nominal_grid_solve_count=sum(
            item.candidate_nominal_grid_solve_count for item in receipts
        ),
        candidate_nominal_grid_solve_success_count=sum(
            item.candidate_nominal_grid_solve_success_count
            for item in receipts
        ),
        selected_direct_role_projection_evaluation_count=sum(
            item.selected_direct_role_projection_evaluation_count
            for item in receipts
        ),
        selected_direct_role_projection_binding_count=sum(
            item.selected_direct_role_projection_binding_count
            for item in receipts
        ),
        selected_nominal_grid_solve_count=sum(
            item.selected_nominal_grid_solve_count for item in receipts
        ),
        selected_nominal_grid_solve_success_count=sum(
            item.selected_nominal_grid_solve_success_count
            for item in receipts
        ),
    )
    receipt.validate_bounds()
    return replace(result, receipt=receipt)


def _carry_terminal_phase_diagnostic(
    result: PhaseFitResult,
    prior: PhaseFitResult,
) -> PhaseFitResult:
    """Carry at most one failed record across the same registered phase flow."""

    if result.template != prior.template or (
        result.registered_direct_observation_ids
        != prior.registered_direct_observation_ids
    ):
        raise ValueError("terminal diagnostic crosses registered phase input")
    result = _carry_native_phase_diagnostic(result, prior)
    records = tuple(
        item for item in (prior._terminal_diagnostic, result._terminal_diagnostic)
        if item is not None
    )
    if not records:
        return result

    def rank(item: _TerminalPhaseDiagnostic) -> tuple[object, ...]:
        return (
            *_candidate_model._rank(_candidate_model._BoundFit(item.fit, _candidate_model._phase_residual_compatible(item.fit))),
            0,
            -len(item.projection.projected_out_bindings),
            tuple(
                (binding.role_index, str(binding.observation_id))
                for binding in item.projection.projected_out_bindings
            ),
        )

    # The original rank is used only within failed diagnostic records.
    # A retained record costs O(R), including its original authority ledger.
    receipt = replace(
        result.receipt,
        peak_temporary_bytes=max(
            result.receipt.peak_temporary_bytes,
            prior.receipt.peak_temporary_bytes,
        ) + result.receipt.role_count * 128,
    )
    receipt.validate_bounds()
    return replace(
        result, _terminal_diagnostic=max(records, key=rank), receipt=receipt,
    )


def _carry_native_phase_diagnostic(
    result: PhaseFitResult,
    prior: PhaseFitResult,
) -> PhaseFitResult:
    """Carry the independent Review record only within one template identity."""

    if result.status == PhaseFitStatus.BOUND_EXCEEDED:
        return replace(
            result, _native_phase_retention=None,
            _source_clipped_phase_retention=None,
        )
    if result.template != prior.template:
        return result
    retention = carry_native_phase_retention(
        prior._native_phase_retention,
        result._native_phase_retention,
        template=result.template,
        registered_direct_observation_ids=result.registered_direct_observation_ids,
    )
    source_retention = carry_source_clipped_phase_retention(
        prior._source_clipped_phase_retention,
        result._source_clipped_phase_retention,
        template=result.template,
        registered_direct_observation_ids=result.registered_direct_observation_ids,
    )
    if not source_retention.record_scan_count:
        source_retention = None
    return replace(
        result, _native_phase_retention=retention,
        _source_clipped_phase_retention=source_retention,
    )


def _retain_empty_terminal_diagnostic_runner(result: PhaseFitResult) -> PhaseFitResult:
    """Fill a late empty Review slot with an existing failed proposal."""

    diagnostic = result._terminal_diagnostic
    if (
        diagnostic is None
        or result.status != PhaseFitStatus.UNRESOLVED
        or result.best is None
        or result.runner_up is not None
        or _state._same_continuous_placement(result.best, diagnostic.fit)
    ):
        return replace(result, _terminal_diagnostic=None)
    return replace(
        result,
        runner_up=diagnostic.fit,
        runner_phase_candidate_authority_projection=diagnostic.projection,
        _terminal_diagnostic=None,
    )


def retain_pre_local_phase_proposal(
    result: PhaseFitResult,
    *,
    prior: PhaseFitResult,
) -> PhaseFitResult:
    """Keep one complete positioned phase after local evidence rejects eligibility.

    ``prior`` is the uniquely positioned direct or calibrated-Grid solution
    that exists before local refinement or adjacency continuity introduces
    counterevidence. A later refit may therefore withhold the candidate, but it
    must not erase that already complete pre-Gate proposal. The retained fit
    never changes ``result.status`` or ``result.failure_kind`` and cannot
    acquire candidate or automatic-approval authority.
    """

    if result.template != prior.template:
        raise ValueError("retained phase proposal crosses template identity")
    if (
        result.best is not None
        or result.status == PhaseFitStatus.BOUND_EXCEEDED
        or prior.status != PhaseFitStatus.RESOLVED
        or prior.best is None
    ):
        return result
    calibrated = prior.best.calibrated_nominal_grid_fit_state is not None
    return replace(
        result,
        best=prior.best,
        runner_up=prior.runner_up,
        best_phase_candidate_authority_projection=(
            prior.best_phase_candidate_authority_projection
        ),
        runner_phase_candidate_authority_projection=(
            prior.runner_phase_candidate_authority_projection
        ),
        retained_proposal_basis=(
            PhaseRetainedProposalBasis
            .CALIBRATED_NOMINAL_GRID_BEFORE_LOCAL_COUNTEREVIDENCE
            if calibrated
            else PhaseRetainedProposalBasis
            .DIRECT_LATTICE_BEFORE_LOCAL_COUNTEREVIDENCE
        ),
    )


def fit_template_phase_candidate_with_adjacency_relations(
    phase_input: TemplatePhaseInput,
) -> TemplatePhaseCandidateCompetition:
    """Resolve discrete/local competition before placement-bound source W."""

    if not isinstance(phase_input, TemplatePhaseInput):
        raise TypeError(
            "adjacency-relation phase fit requires TemplatePhaseInput"
        )
    observations = phase_input.observations
    separator_bands = phase_input.separator_bands
    template = phase_input.template
    scale_px_per_mm = phase_input.scale_px_per_mm
    holder_span_px = phase_input.holder_span_px
    phase_authority_px = phase_input.phase_authority_px
    max_observations = phase_input.max_observations

    normal = _competition.fit_template_phase(
        observations,
        template,
        separator_bands=separator_bands,
        outer_material_boundaries=(
            phase_input.outer_material_boundaries
        ),
        scale_px_per_mm=scale_px_per_mm,
        holder_span_px=holder_span_px,
        source_domain=phase_input.source_domain,
        phase_authority_px=phase_authority_px,
        contact_edge_observations=phase_input.contact_edge_observations,
        overlap_edge_pair_observations=(
            phase_input.overlap_edge_pair_observations
        ),
        sequence_measurement_sets=phase_input.sequence_measurement_sets,
        calibrated_nominal_grid_prior=(
            phase_input.calibrated_nominal_grid_prior
        ),
        max_observations=max_observations,
    )
    if normal.status != PhaseFitStatus.RESOLVED or normal.best is None:
        # Discrete identity ambiguity does not erase a positioned candidate's
        # own local pixels. Complete only the two already retained fits, then
        # remove any newly attached coordinates lacking their own authority.
        # Their order, ambiguity and absence of a winner remain unchanged.
        normal = _refinement._with_local_role_refinement(
            normal,
            observations,
            separator_bands,
            phase_input.sequence_measurement_sets,
        )
        normal = _refinement._project_retained_late_local_refinements(
            normal,
            phase_input,
            allow_direct_rank=True,
        )
        assessed = _refinement._attach_selected_candidate_authorities(
            normal,
            phase_input,
            directly_observed_ordinals=(),
        )
        return TemplatePhaseCandidateCompetition(assessed, ())
    pre_local_proposal = normal
    normal = _refinement._refine_selected_roles_with_candidate_elimination(
        normal,
        phase_input,
    )
    if normal.status != PhaseFitStatus.RESOLVED or normal.best is None:
        # Source W is measured immediately after this handoff. Its typed
        # facts must describe the restored native fit, not the empty result.
        normal = retain_pre_local_phase_proposal(
            normal,
            prior=pre_local_proposal,
        )
        assessed = _refinement._attach_selected_candidate_authorities(
            normal,
            phase_input,
            directly_observed_ordinals=(),
        )
        return TemplatePhaseCandidateCompetition(assessed, ())
    assert normal.best is not None
    # Import here keeps the residual owner dependent on the canonical phase
    # types without creating a module import cycle.
    from .template_residual import (
        AdjacencyRelationFailureKind,
        derive_adjacency_relations,
    )

    initial_coverage = assess_adjacency_observation_coverage(
        normal.best,
        phase_input.sequence_measurement_sets,
        directly_observed_ordinals=(),
    )
    continuity = observe_adjacency_continuity(
        normal.best,
        tuple(
            item
            for item in observations
            if isinstance(item, BoundaryEdgeObservation)
        ),
        separator_bands,
        initial_coverage,
        phase_input.overlap_edge_pair_observations,
        direct_role_authority=normal.direct_role_binding_authority,
    )

    analysis = derive_adjacency_relations(
        normal.best,
        continuity,
    )
    directly_observed_ordinals = tuple(
        item.relation_ordinal for item in analysis.adjacency_facts
    )
    if analysis.unresolved_reason is not None:
        unresolved = replace(
            normal,
            status=PhaseFitStatus.UNRESOLVED,
            ambiguity_reason=analysis.unresolved_reason,
            failure_kind=(
                PhaseFailureKind.ADJACENCY_TOPOLOGY_UNRESOLVED
                if analysis.failure_kind
                == AdjacencyRelationFailureKind.ADJACENCY_TOPOLOGY_UNRESOLVED
                else PhaseFailureKind.ADJACENCY_CONTINUITY_UNRESOLVED
                if analysis.failure_kind
                == AdjacencyRelationFailureKind.ADJACENCY_CONTINUITY_UNRESOLVED
                else PhaseFailureKind.ADJACENCY_RELATION_AMBIGUOUS
            ),
            winner_basis=None,
            receipt=replace(
                normal.receipt,
                adjacency_relation_evaluation_count=(
                    analysis.evaluated_adjacency_count
                ),
            ),
        )
        assessed = _refinement._attach_selected_candidate_authorities(
            unresolved,
            phase_input,
            directly_observed_ordinals=directly_observed_ordinals,
        )
        return TemplatePhaseCandidateCompetition(
            assessed,
            directly_observed_ordinals,
        )
    if not analysis.relations:
        measured = replace(
            normal,
            receipt=replace(
                normal.receipt,
                adjacency_relation_evaluation_count=(
                    analysis.evaluated_adjacency_count
                ),
            ),
        )
        measured = _refinement._project_retained_late_local_refinements(
            measured,
            phase_input,
        )
        assessed = _refinement._attach_selected_candidate_authorities(
            measured,
            phase_input,
            directly_observed_ordinals=directly_observed_ordinals,
        )
        return TemplatePhaseCandidateCompetition(
            assessed,
            directly_observed_ordinals,
        )
    adjusted = _competition.fit_template_phase(
        observations,
        template,
        separator_bands=separator_bands,
        outer_material_boundaries=(
            phase_input.outer_material_boundaries
        ),
        scale_px_per_mm=scale_px_per_mm,
        holder_span_px=holder_span_px,
        source_domain=phase_input.source_domain,
        phase_authority_px=phase_authority_px,
        adjacency_relations=analysis.relations,
        contact_edge_observations=phase_input.contact_edge_observations,
        overlap_edge_pair_observations=(
            phase_input.overlap_edge_pair_observations
        ),
        sequence_measurement_sets=phase_input.sequence_measurement_sets,
        calibrated_nominal_grid_prior=(
            phase_input.calibrated_nominal_grid_prior
        ),
        phase_anchor_authority_ceiling=tuple(
            (role_index, binding.observation_id)
            for role_index, binding in enumerate(normal.best.role_bindings)
            if binding is not None
            and binding.use == SequenceBindingUse.PHASE_ANCHOR
        ),
        max_observations=max_observations,
    )
    adjusted = replace(
        adjusted,
        eliminated_candidate_authority_projections=(
            normal.eliminated_candidate_authority_projections
        ),
    )
    adjusted = _refinement._refine_selected_roles_with_candidate_elimination(
        adjusted,
        phase_input,
        excluded_role_bindings=_refinement._eliminated_candidate_role_bindings(normal),
    )
    adjusted = _state._inherit_prior_lattice_fit_basis(adjusted, normal)
    adjusted = _aggregate_phase_work(
        adjusted,
        normal.receipt,
        adjacency_relation_evaluation_count=(
            analysis.evaluated_adjacency_count
        ),
    )
    adjusted = _carry_terminal_phase_diagnostic(adjusted, normal)
    adjusted = _refinement._project_retained_late_local_refinements(
        adjusted,
        phase_input,
    )
    adjusted = retain_pre_local_phase_proposal(
        adjusted,
        prior=normal,
    )
    assessed = _refinement._attach_selected_candidate_authorities(
        adjusted,
        phase_input,
        directly_observed_ordinals=directly_observed_ordinals,
    )
    return TemplatePhaseCandidateCompetition(
        assessed,
        directly_observed_ordinals,
    )


def finalize_template_phase_candidate(
    candidate: TemplatePhaseCandidateCompetition,
    phase_input: TemplatePhaseInput,
    *,
    source_frame_width_authority: SourceFrameWidthAuthority | None,
) -> PhaseFitResult:
    """Apply placement-bound lattice and inference contracts to one competition."""

    if not isinstance(candidate, TemplatePhaseCandidateCompetition):
        raise TypeError("phase finalization requires a candidate competition")
    if candidate.result.template != phase_input.template:
        raise ValueError("phase candidate and final input use different templates")
    result = _refinement._apply_final_lattice_contract(
        candidate.result,
        phase_input,
        directly_observed_ordinals=(
            candidate.directly_observed_adjacency_ordinals
        ),
        source_frame_width_authority=source_frame_width_authority,
    )
    if (
        result.status != PhaseFitStatus.UNRESOLVED
        or result.failure_kind
        != PhaseFailureKind.DIRECT_ROLE_BINDING_AUTHORITY_UNAVAILABLE
    ):
        return _retain_empty_terminal_diagnostic_runner(result)
    projected = _refinement._project_retained_late_local_refinements(
        candidate.result,
        phase_input,
        source_frame_width_authority=source_frame_width_authority,
        allow_direct_rank=True,
    )
    result = _refinement._apply_final_lattice_contract(
        projected,
        phase_input,
        directly_observed_ordinals=(
            candidate.directly_observed_adjacency_ordinals
        ),
        source_frame_width_authority=source_frame_width_authority,
    )
    return _retain_empty_terminal_diagnostic_runner(result)


def fit_template_phase_with_adjacency_relations(
    phase_input: TemplatePhaseInput,
) -> PhaseFitResult:
    """Run canonical candidate competition and final lattice assessment."""

    candidate = fit_template_phase_candidate_with_adjacency_relations(
        phase_input
    )
    return finalize_template_phase_candidate(
        candidate,
        phase_input,
        source_frame_width_authority=None,
    )


def account_prior_phase_fit(
    result: PhaseFitResult,
    prior: PhaseFitResult,
) -> PhaseFitResult:
    """Attach a prior calibration fit to the lane's auditable work receipt."""

    return _aggregate_phase_work(
        _carry_native_phase_diagnostic(
            _state._inherit_prior_lattice_fit_basis(result, prior), prior,
        ),
        prior.receipt,
    )
