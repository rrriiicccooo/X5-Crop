"""Bounded sequence phase refinement."""

from __future__ import annotations

from dataclasses import replace
from typing import Sequence

from ...domain import EvidenceState, FiniteInterval, ObservationId
from .measurement_model import PhotoBoundaryMeasurementSet
from .model import PHOTO_BOUNDARY_MEASUREMENT_SPEC
from .observation_types import BoundaryEdgeObservation, SeparatorBandObservation
from .template_model import (
    FrameWidthInferenceFailureKind,
    SequenceBindingUse,
    SequenceFit,
    ordered_template_roles,
)
from .template_frame_width import (
    SourceFrameWidthAuthority,
    apply_correlated_frame_width_inference,
    apply_placement_source_frame_width,
    assess_placement_source_frame_width_topology,
)
from .template_adjacency_coverage import (
    AdjacencyCoverageState,
    assess_adjacency_observation_coverage,
)
from .template_adjacency_topology import (
    assess_phase_candidate_adjacency,
    AdjacencyContinuityKind,
    observe_adjacency_continuity,
)
from .template_lattice_authority import (
    assess_global_lattice_authority,
    direct_role_constraint_rank,
)
from .template_direct_role_authority import (
    assess_direct_role_binding_authority,
    intrinsic_direct_role_authority_bases,
)
from .template_outer_frame_authority import assess_outer_frame_observation_authority
from .template_phase_model import (
    PhaseCandidateAuthorityProjection,
    PhaseCandidateProjectionOutcome,
    PhaseFailureKind,
    PhaseFitResult,
    PhaseFitStatus,
    PhaseWinnerBasis,
    TemplatePhaseInput,
)
from .template_nominal_grid_authority import (
    failed_nominal_grid_evidence,
    nominal_grid_evidence_id,
)
from .template_nominal_grid_model import (
    CalibratedNominalGridEvidence,
    NominalGridFailureKind,
)
from . import (
    template_phase_candidate_model as _candidate_model,
    template_phase_observations as _observations,
    template_phase_projection as _projection,
    template_phase_state as _state,
)


def _local_role_candidates(result: PhaseFitResult) -> tuple[SequenceFit, ...]:
    if result.best is None:
        return ()
    if result.status == PhaseFitStatus.RESOLVED:
        return (result.best,)
    if (result.status == PhaseFitStatus.AMBIGUOUS
            and result.failure_kind in {
                PhaseFailureKind.DISCRETE_PHASE_AMBIGUOUS,
                PhaseFailureKind.ADJACENCY_TOPOLOGY_AMBIGUOUS,
            }
            and result.runner_up is not None):
        return result.best, result.runner_up
    return ()


def assess_retained_phase_adjacencies(
    result: PhaseFitResult,
    phase_input: TemplatePhaseInput,
    *,
    source_frame_width_authority: SourceFrameWidthAuthority | None,
) -> PhaseFitResult:
    """Close each final retained candidate's own registered role associations.

    Native completion can introduce an independent endpoint after the bounded
    candidate pool has been compressed. Its role ledger must be reassessed
    before interpreting a missing partner as absent physical counterevidence.
    A contradicted runner does not prove the unretained pool has one survivor.
    """

    if result.retained_adjacency_assessments:
        raise ValueError("retained adjacency finalization must run exactly once")
    if not phase_input.sequence_measurement_sets or result.best is None:
        return result
    assessments = tuple(
        assess_phase_candidate_adjacency(
            fit, phase_input.observations, phase_input.separator_bands,
            phase_input.sequence_measurement_sets, phase_input.overlap_edge_pair_observations,
            outer_material_boundaries=phase_input.outer_material_boundaries,
            authorized_source_frame_width_px=(
                source_frame_width_authority.width_px
                if source_frame_width_authority is not None
                and source_frame_width_authority.state == EvidenceState.SUPPORTED
                and source_frame_width_authority.matches_placement(fit)
                else None
            ),
        )
        for fit in (result.best, result.runner_up) if fit is not None
    )
    # Logical accounting includes the retained ledgers and the largest live
    # registered index/coverage structure. No pixel, seed or solver work runs.
    retained_bytes = sum(1024 + len(item.fit.role_bindings) * 384 + sum(
        128 + 32 * (len(trace.covering_query_ids) + len(trace.covered_intervals_px))
        for coverage in item.coverage for trace in coverage.trace_coverage
    ) for item in assessments)
    temporary_bytes = 128 * (len(phase_input.observations) + len(phase_input.separator_bands)
                            + len(phase_input.overlap_edge_pair_observations))
    receipt = replace(result.receipt, peak_temporary_bytes=max(
        result.receipt.peak_temporary_bytes, retained_bytes + temporary_bytes,
    ))
    receipt.validate_bounds()
    contradicted_best = result.status == PhaseFitStatus.RESOLVED and assessments[0].state == EvidenceState.CONTRADICTED
    contradiction_kind = (
        PhaseFailureKind.SEPARATOR_MATERIAL_CONFLICT
        if assessments[0].direct_role_authority.state == EvidenceState.CONTRADICTED
        else PhaseFailureKind.ADJACENCY_CONTINUITY_UNRESOLVED
    )
    return replace(
        result, retained_adjacency_assessments=assessments, receipt=receipt,
        status=PhaseFitStatus.UNRESOLVED if contradicted_best else result.status,
        failure_kind=contradiction_kind if contradicted_best else result.failure_kind,
        ambiguity_reason=("final native roles or registered adjacency associations are contradicted"
                          if contradicted_best else result.ambiguity_reason),
        winner_basis=None if contradicted_best else result.winner_basis,
    )


def _with_local_role_refinement(
    result: PhaseFitResult,
    observations: Sequence[BoundaryEdgeObservation],
    separator_bands: Sequence[SeparatorBandObservation],
    sequence_measurement_sets: Sequence[PhotoBoundaryMeasurementSet] = (),
    *,
    frame_width_authority_px: FiniteInterval | None = None,
    additional_fit_pass: bool = False,
    excluded_role_bindings: frozenset[
        tuple[int, ObservationId]
    ] = frozenset(),
) -> PhaseFitResult:
    candidates = _local_role_candidates(result)
    if not candidates:
        return result
    ambiguous = len(candidates) == 2
    if ambiguous and frame_width_authority_px is not None:
        raise ValueError("ambiguous local roles cannot share selected source W")
    authority_ids = (
        frozenset(
            intrinsic_direct_role_authority_bases(
                tuple(observations),
                tuple(sequence_measurement_sets),
            )
        )
        if sequence_measurement_sets
        else frozenset()
    )
    refinements = tuple(
        _observations._refine_local_role_bindings(
            candidate,
            observations,
            separator_bands,
            intrinsic_coordinate_authority_ids=authority_ids,
            frame_width_authority_px=frame_width_authority_px,
            excluded_role_bindings=excluded_role_bindings,
        )
        for candidate in candidates
    )
    receipt = replace(
        result.receipt,
        fit_pass_count=(
            result.receipt.fit_pass_count
            + int(additional_fit_pass)
            + len(refinements) - 1
        ),
        local_refinement_lookup_count=(
            result.receipt.local_refinement_lookup_count
            + sum(item.role_lookup_count for item in refinements)
        ),
        local_refinement_binding_count=(
            result.receipt.local_refinement_binding_count
            + sum(item.binding_count for item in refinements)
        ),
        inferred_role_count=len(refinements[0].fit.unbound_role_indices),
    )
    receipt.validate_bounds()
    return replace(
        result,
        best=refinements[0].fit,
        runner_up=refinements[1].fit if ambiguous else result.runner_up,
        receipt=receipt,
    )


def _refine_selected_roles_with_candidate_elimination(
    result: PhaseFitResult,
    phase_input: TemplatePhaseInput,
    *,
    excluded_role_bindings: frozenset[
        tuple[int, ObservationId]
    ] = frozenset(),
) -> PhaseFitResult:
    """Reject a winner contradicted only after selected local refinement.

    Candidate ranking is bounded before selected-only local refinement.  A
    newly attached line can therefore complete an exact reversed
    END/material/START pair that was not present in the candidate authority
    ledger.  Reassess that one selected fit, eliminate it through the existing
    typed direct-role contradiction, and promote only the already retained,
    authority-eligible runner.  At most two selected fits are refined; no new
    observation or TIFF query is created.
    """

    current = result
    exclusions = excluded_role_bindings
    for candidate_index in range(2):
        current = _with_local_role_refinement(
            current,
            phase_input.observations,
            phase_input.separator_bands,
            phase_input.sequence_measurement_sets,
            additional_fit_pass=candidate_index > 0,
            excluded_role_bindings=exclusions,
        )
        if (
            current.status != PhaseFitStatus.RESOLVED
            or current.best is None
            or not phase_input.sequence_measurement_sets
        ):
            return current
        authority = assess_direct_role_binding_authority(
            current.best,
            phase_input.observations,
            phase_input.separator_bands,
            phase_input.sequence_measurement_sets,
            outer_material_boundaries=(
                phase_input.outer_material_boundaries
            ),
        )
        if authority.state != EvidenceState.CONTRADICTED:
            return current
        projection = PhaseCandidateAuthorityProjection(
            input_direct_role_authority=authority,
            outcome=PhaseCandidateProjectionOutcome.DIRECT_ROLE_CONTRADICTION,
            basis=None,
            projected_out_bindings=(),
            retained_direct_constraint_rank=direct_role_constraint_rank(
                current.best,
                authority.supported_role_indices,
            ),
            reason=(
                authority.reason or "direct-role evidence is contradicted"
            ),
        )
        receipt = replace(
            current.receipt,
            selected_direct_role_projection_evaluation_count=(
                current.receipt
                .selected_direct_role_projection_evaluation_count
                + 1
            ),
        )
        receipt.validate_bounds()
        runner_projection = (
            current.runner_phase_candidate_authority_projection
        )
        if (
            candidate_index > 0
            or current.runner_up is None
            or runner_projection is None
            or not runner_projection.eligible
        ):
            return replace(
                current,
                status=PhaseFitStatus.UNRESOLVED,
                ambiguity_reason=projection.reason,
                failure_kind=(
                    PhaseFailureKind.SEPARATOR_MATERIAL_CONFLICT
                ),
                winner_basis=None,
                best_phase_candidate_authority_projection=projection,
                receipt=receipt,
            )
        exclusions = frozenset(
            (item.role_index, item.observation_id)
            for item in authority.facts
            if item.state == EvidenceState.CONTRADICTED
        )
        current = replace(
            current,
            best=current.runner_up,
            runner_up=current.best,
            status=PhaseFitStatus.RESOLVED,
            ambiguity_reason=None,
            failure_kind=None,
            winner_basis=PhaseWinnerBasis.UNIQUE_DIRECT_ROLE_AUTHORITY,
            best_phase_candidate_authority_projection=runner_projection,
            runner_phase_candidate_authority_projection=projection,
            eliminated_candidate_authority_projections=(
                *current.eliminated_candidate_authority_projections,
                projection,
            ),
            receipt=receipt,
            global_lattice_authority=None,
            calibrated_nominal_grid_evidence=None,
            adjacency_observation_coverage=(),
            adjacency_continuity_observations=(),
            direct_role_binding_authority=None,
            outer_frame_observation_authority=None,
        )
    raise AssertionError("selected candidate elimination exceeded its bound")


def _eliminated_candidate_role_bindings(
    result: PhaseFitResult,
) -> frozenset[tuple[int, ObservationId]]:
    """Return exact role/edge assignments rejected by hard counterevidence."""

    return frozenset(
        (fact.role_index, fact.observation_id)
        for projection in result.eliminated_candidate_authority_projections
        for fact in projection.input_direct_role_authority.facts
        if fact.state == EvidenceState.CONTRADICTED
    )


def _project_late_local_candidate(
    fit: SequenceFit,
    phase_input: TemplatePhaseInput,
    *,
    source_frame_width_authority: SourceFrameWidthAuthority | None = None,
    allow_direct_rank: bool = False,
) -> tuple[SequenceFit | None, PhaseCandidateAuthorityProjection | None]:
    """Yield unsupported late local bindings back to this candidate's lattice.

    Candidate projection runs before local relation analysis.  Local
    refinement must remain free to bind registered lines while topology is
    being derived, but a short line that still lacks coordinate authority
    after that analysis cannot become output geometry merely because it was
    added later.  Reuse the same bounded projection owner on this candidate's
    discrete identity whether its remaining coordinates close a direct-rank
    lattice or require the calibrated Grid.  The line remains typed projection
    provenance and counterevidence; it cannot acquire authority from the time
    at which it was attached.
    """

    if (
        not phase_input.sequence_measurement_sets
        or (
            fit.calibrated_nominal_grid_fit_state is None
            and not allow_direct_rank
        )
    ):
        return fit, None
    authority = assess_direct_role_binding_authority(
        fit,
        phase_input.observations,
        phase_input.separator_bands,
        phase_input.sequence_measurement_sets,
        outer_material_boundaries=phase_input.outer_material_boundaries,
        authorized_source_frame_width_px=(
            None
            if source_frame_width_authority is None
            or source_frame_width_authority.state != EvidenceState.SUPPORTED
            else source_frame_width_authority.width_px
        ),
    )
    if authority.state == EvidenceState.CONTRADICTED:
        return None, PhaseCandidateAuthorityProjection(
            input_direct_role_authority=authority,
            outcome=PhaseCandidateProjectionOutcome.DIRECT_ROLE_CONTRADICTION,
            basis=None,
            projected_out_bindings=(),
            retained_direct_constraint_rank=direct_role_constraint_rank(
                fit, authority.supported_role_indices,
            ),
            reason=authority.reason or "direct-role evidence is contradicted",
        )
    if authority.state != EvidenceState.UNAVAILABLE:
        return fit, None
    unsupported_bindings = tuple(
        fit.role_bindings[role_index]
        for role_index in authority.unsupported_role_indices
    )
    if not unsupported_bindings or any(
        binding is None
        or binding.use != SequenceBindingUse.LOCAL_REFINEMENT
        for binding in unsupported_bindings
    ):
        return fit, None

    template = phase_input.template
    separator_support = _observations.prepare_phase_separator_support(
        phase_input.observations,
        phase_input.separator_bands,
        maximum_material_gap_px=template.gap_prior_px.maximum,
    )
    phase_separator_bands = separator_support.bands
    separator_support_ids = separator_support.resolution.edge_component_ids
    qualified_observations = separator_support.observations
    facts = _observations._facts(
        qualified_observations,
        separator_support_ids=separator_support_ids,
        registered_trace_positions_px=(
            phase_input.sequence_measurement_sets[0].query.trace_positions_px
            if phase_input.sequence_measurement_sets else ()
        ),
    )
    direct = tuple(item for item in facts if item.direct)
    separator_pairs = _observations._separator_pair_facts(
        phase_separator_bands,
        direct,
        maximum_material_gap_px=template.gap_prior_px.maximum,
    )
    width = FiniteInterval(
        template.frame_width_px.minimum,
        template.frame_width_px.maximum,
    )
    gap_pitch = FiniteInterval(
        width.minimum + template.gap_prior_px.minimum,
        width.maximum + template.gap_prior_px.maximum,
    )
    pitch = FiniteInterval(
        max(gap_pitch.minimum, template.pitch_px.minimum),
        min(gap_pitch.maximum, template.pitch_px.maximum),
    )
    fit_residual_limit_px = (
        None
        if phase_input.scale_px_per_mm is None
        else PHOTO_BOUNDARY_MEASUREMENT_SPEC.line_connection_allowance_px(
            phase_input.scale_px_per_mm.maximum
        )
    )
    projected, projection = _projection.project_candidate_to_authorized_direct_roles(
        _candidate_model._BoundFit(fit, True),
        authority,
        facts,
        separator_pairs,
        ordered_template_roles(template.count),
        template,
        fit.adjacency_relations,
        pitch,
        phase_input.phase_authority_px,
        fit_residual_limit_px,
        phase_input.calibrated_nominal_grid_prior,
        frozenset(
            (role_index, binding.observation_id)
            for role_index, binding in enumerate(fit.role_bindings)
            if binding is not None
            and binding.use == SequenceBindingUse.PHASE_ANCHOR
        ),
    )
    if projected is not None and not projected.residual_compatible:
        # Initial competition separates compatible and incompatible refits.
        # A late refit has no new competition pass, so it cannot silently
        # turn the latter into an eligible direct-rank projection. Keep the
        # positioned input as Review geometry through the caller's existing
        # failed-projection retention path.
        return None, replace(
            projection,
            outcome=PhaseCandidateProjectionOutcome.REFIT_UNAVAILABLE,
            basis=None,
            reason=(
                "late authorized direct coordinates exceed the fixed "
                "template phase residual compatibility limit"
            ),
        )
    return None if projected is None else projected.fit, projection


def _project_retained_late_local_refinements(
    result: PhaseFitResult,
    phase_input: TemplatePhaseInput,
    *,
    source_frame_width_authority: SourceFrameWidthAuthority | None = None,
    allow_direct_rank: bool = False,
) -> PhaseFitResult:
    """Project each retained fit without turning discrete ambiguity into a winner."""

    candidates = _local_role_candidates(result)
    if not candidates:
        return result
    ambiguous = len(candidates) == 2
    if ambiguous and source_frame_width_authority is not None:
        raise ValueError("ambiguous local projection cannot share selected source W")
    records = tuple(
        _project_late_local_candidate(
            candidate,
            phase_input,
            source_frame_width_authority=source_frame_width_authority,
            allow_direct_rank=allow_direct_rank,
        )
        for candidate in candidates
    )
    projections = tuple(
        projection for _fit, projection in records if projection is not None
    )
    if not projections:
        return result
    retained_fits = tuple(
        original if projected is None else projected
        for original, (projected, _projection) in zip(
            candidates, records, strict=True
        )
    )
    projected, projection = records[0]
    nominal_solve_count = sum(
        item.outcome in {
            PhaseCandidateProjectionOutcome.CALIBRATED_NOMINAL_GRID,
            PhaseCandidateProjectionOutcome.CALIBRATED_NOMINAL_GRID_CONFLICT,
        }
        for item in projections
    )
    receipt = replace(
        result.receipt,
        selected_direct_role_projection_evaluation_count=(
            result.receipt.selected_direct_role_projection_evaluation_count
            + len(projections)
        ),
        selected_direct_role_projection_binding_count=(
            result.receipt.selected_direct_role_projection_binding_count
            + sum(len(item.projected_out_bindings) for item in projections)
        ),
        selected_nominal_grid_solve_count=(
            result.receipt.selected_nominal_grid_solve_count
            + nominal_solve_count
        ),
        selected_nominal_grid_solve_success_count=(
            result.receipt.selected_nominal_grid_solve_success_count
            + sum(
                item.outcome
                == PhaseCandidateProjectionOutcome.CALIBRATED_NOMINAL_GRID
                for item in projections
            )
        ),
        inferred_role_count=(
            len(retained_fits[0].unbound_role_indices)
        ),
    )
    receipt.validate_bounds()
    if projected is None and not ambiguous:
        assert projection is not None
        return replace(
            result,
            status=PhaseFitStatus.UNRESOLVED,
            ambiguity_reason=projection.reason,
            failure_kind=_state._projection_failure_kind(projection.outcome),
            winner_basis=None,
            best_phase_candidate_authority_projection=projection,
            receipt=receipt,
        )
    return replace(
        result,
        best=retained_fits[0],
        runner_up=retained_fits[1] if ambiguous else result.runner_up,
        best_phase_candidate_authority_projection=(
            projection or result.best_phase_candidate_authority_projection
        ),
        runner_phase_candidate_authority_projection=(
            records[1][1] or result.runner_phase_candidate_authority_projection
            if ambiguous
            else result.runner_phase_candidate_authority_projection
        ),
        receipt=receipt,
        global_lattice_authority=None,
        calibrated_nominal_grid_evidence=None,
        adjacency_observation_coverage=(),
        adjacency_continuity_observations=(),
        direct_role_binding_authority=None,
        outer_frame_observation_authority=None,
    )


def refine_template_phase_with_source_frame_width(
    result: PhaseFitResult,
    authority: SourceFrameWidthAuthority,
    observations: Sequence[BoundaryEdgeObservation],
    separator_bands: Sequence[SeparatorBandObservation],
    sequence_measurement_sets: Sequence[PhotoBoundaryMeasurementSet],
) -> PhaseFitResult:
    """Bind only roles uniquely selected by an independent source-level W.

    The discrete placement must already be resolved and source W independently
    closed either by complete Frames or by a retained full-rank direct
    lattice. This selected-candidate-only pass may bind a registered native
    edge pair that the broader format interval could not distinguish. An
    ambiguous retained proposal consumes W for its existing missing roles but
    does not run this additional local rebinding pass.
    """

    if authority.state != EvidenceState.SUPPORTED:
        return result
    if result.status != PhaseFitStatus.RESOLVED:
        return result
    if result.best is None:
        raise ValueError("resolved source W requires one placement")
    if not result.best.unbound_role_indices:
        return result
    if (
        not authority.matches_placement(result.best)
        or authority.width_px is None
    ):
        raise ValueError("source W authority belongs to a different placement")
    return _with_local_role_refinement(
        result,
        observations,
        separator_bands,
        sequence_measurement_sets,
        frame_width_authority_px=authority.width_px,
        additional_fit_pass=True,
        excluded_role_bindings=_eliminated_candidate_role_bindings(result),
    )


def _attach_selected_candidate_authorities(
    result: PhaseFitResult,
    phase_input: TemplatePhaseInput,
    *,
    directly_observed_ordinals: tuple[int, ...],
    source_frame_width_authority: SourceFrameWidthAuthority | None = None,
) -> PhaseFitResult:
    """Measure selected-candidate authorities without changing its status."""

    direct_role_authority = (
        None
        if result.best is None or not phase_input.sequence_measurement_sets
        else assess_direct_role_binding_authority(
            result.best,
            phase_input.observations,
            phase_input.separator_bands,
            phase_input.sequence_measurement_sets,
            outer_material_boundaries=(
                phase_input.outer_material_boundaries
            ),
            authorized_source_frame_width_px=(
                None
                if source_frame_width_authority is None
                or source_frame_width_authority.state
                != EvidenceState.SUPPORTED
                else source_frame_width_authority.width_px
            ),
        )
    )
    authority = (
        None
        if result.best is None
        else assess_global_lattice_authority(
            result.best,
            phase_input,
            direct_role_authority=direct_role_authority,
        )
    )
    coverage = (
        ()
        if result.best is None
        else assess_adjacency_observation_coverage(
            result.best,
            phase_input.sequence_measurement_sets,
            directly_observed_ordinals=directly_observed_ordinals,
        )
    )
    continuity = (
        ()
        if result.best is None
        else observe_adjacency_continuity(
            result.best,
            phase_input.observations,
            phase_input.separator_bands,
            coverage,
            phase_input.overlap_edge_pair_observations,
            direct_role_authority=direct_role_authority,
        )
    )
    outer_authority = (
        None
        if result.best is None
        else assess_outer_frame_observation_authority(result.best)
    )
    nominal_evidence = None
    nominal_state = (
        None
        if result.best is None
        else result.best.calibrated_nominal_grid_fit_state
    )
    if nominal_state is not None:
        unobserved_frames = result.best.completely_unobserved_frame_ordinals
        inferred = tuple(
            item for item in coverage if item.normal_inference_required
        )
        ordinals = tuple(item.relation_ordinal for item in inferred)
        query_ids = tuple(
            sorted(
                {
                    query_id
                    for item in inferred
                    for query_id in item.covering_query_ids
                }
            )
        )
        if direct_role_authority is not None and (
            direct_role_authority.state == EvidenceState.CONTRADICTED
        ):
            nominal_evidence = failed_nominal_grid_evidence(
                nominal_state,
                inferred_adjacency_ordinals=ordinals,
                covering_query_ids=query_ids,
                state=EvidenceState.CONTRADICTED,
                failure_kind=NominalGridFailureKind.COUNTEREVIDENCE,
                reason=(
                    direct_role_authority.reason
                    or "direct role evidence contradicts the nominal Grid"
                ),
            )
        elif any(
            item.state != AdjacencyCoverageState.COMPLETE for item in inferred
        ):
            nominal_evidence = failed_nominal_grid_evidence(
                nominal_state,
                inferred_adjacency_ordinals=ordinals,
                covering_query_ids=query_ids,
                state=EvidenceState.UNAVAILABLE,
                failure_kind=(
                    NominalGridFailureKind.ADJACENCY_COVERAGE_INCOMPLETE
                ),
                reason=(
                    "one or more nominal adjacency corridors were not fully "
                    "covered by registered measurements"
                ),
            )
        else:
            nominal_evidence = CalibratedNominalGridEvidence(
                evidence_id=nominal_grid_evidence_id(
                    nominal_state,
                    ordinals,
                    unobserved_frames,
                    query_ids,
                ),
                state=EvidenceState.SUPPORTED,
                prior_id=nominal_state.prior_id,
                phase_anchor_role_indices=(
                    nominal_state.phase_anchor_role_indices
                ),
                phase_anchor_observation_ids=(
                    nominal_state.phase_anchor_observation_ids
                ),
                inferred_adjacency_ordinals=ordinals,
                unobserved_frame_ordinals=unobserved_frames,
                covering_query_ids=query_ids,
                failure_kind=None,
                reason=None,
            )
    result = replace(
        result,
        global_lattice_authority=authority,
        calibrated_nominal_grid_evidence=nominal_evidence,
        adjacency_observation_coverage=coverage,
        adjacency_continuity_observations=continuity,
        direct_role_binding_authority=direct_role_authority,
        outer_frame_observation_authority=outer_authority,
    )
    return result


def _apply_final_lattice_contract(
    result: PhaseFitResult,
    phase_input: TemplatePhaseInput,
    *,
    directly_observed_ordinals: tuple[int, ...],
    source_frame_width_authority: SourceFrameWidthAuthority | None,
) -> PhaseFitResult:
    """Require direct-role, global, and local authority for one placement."""

    # A local native-edge pass or late authority projection may rebuild the
    # continuous fit after source W was first closed. The source-W owner must
    # narrow that final retained placement again before any authority or
    # inference ledger is assessed; this is idempotent, does not register new
    # evidence and never changes ambiguity status or removes the runner.
    if (
        source_frame_width_authority is not None
        and source_frame_width_authority.state == EvidenceState.SUPPORTED
        and result.best is not None
    ):
        result = apply_placement_source_frame_width(
            result,
            source_frame_width_authority,
        )
    result = _attach_selected_candidate_authorities(
        result,
        phase_input,
        directly_observed_ordinals=directly_observed_ordinals,
        source_frame_width_authority=source_frame_width_authority,
    )
    if (
        result.best is not None
        and (
            result.best.calibrated_nominal_grid_fit_state is None
            or (
                source_frame_width_authority is not None
                and source_frame_width_authority.state
                == EvidenceState.SUPPORTED
            )
        )
    ):
        assessed_best = apply_correlated_frame_width_inference(
            result.best,
            source_frame_width_authority=source_frame_width_authority,
            direct_role_authority=result.direct_role_binding_authority,
            sequence_edges=phase_input.observations,
            projected_counterevidence_role_indices=tuple(
                item.role_index
                for item in (
                    ()
                    if result.best_phase_candidate_authority_projection is None
                    else result.best_phase_candidate_authority_projection
                    .projected_out_bindings
                )
            ),
        )
        receipt = replace(
            result.receipt,
            inferred_role_count=len(assessed_best.unbound_role_indices),
        )
        receipt.validate_bounds()
        result = replace(
            result,
            best=assessed_best,
            receipt=receipt,
        )
    if (
        source_frame_width_authority is not None
        and source_frame_width_authority.state == EvidenceState.SUPPORTED
    ):
        # Only an authorized correlated-W inference transfers boundary
        # ownership. Assess that final ledger, not every role that happened
        # to be unbound earlier in the placement-bound flow.
        result = assess_placement_source_frame_width_topology(
            result,
            source_frame_width_authority,
        )
    result = _attach_selected_candidate_authorities(
        result,
        phase_input,
        directly_observed_ordinals=directly_observed_ordinals,
        source_frame_width_authority=source_frame_width_authority,
    )
    direct_role_authority = result.direct_role_binding_authority
    authority = result.global_lattice_authority
    nominal_evidence = result.calibrated_nominal_grid_evidence
    coverage = result.adjacency_observation_coverage
    continuity = result.adjacency_continuity_observations
    outer_authority = result.outer_frame_observation_authority
    inferred = tuple(item for item in coverage if item.normal_inference_required)
    continuity_unresolved = next(
        (
            item
            for item in continuity
            if item.kind == AdjacencyContinuityKind.UNRESOLVED
        ),
        None,
    )
    if (
        result.status == PhaseFitStatus.RESOLVED
        and continuity_unresolved is not None
    ):
        return replace(
            result,
            status=PhaseFitStatus.UNRESOLVED,
            ambiguity_reason=(
                continuity_unresolved.reason
                or "adjacency continuity is unresolved"
            ),
            failure_kind=PhaseFailureKind.ADJACENCY_CONTINUITY_UNRESOLVED,
            winner_basis=None,
        )
    if (
        result.status == PhaseFitStatus.RESOLVED
        and direct_role_authority is not None
        and direct_role_authority.state != EvidenceState.SUPPORTED
    ):
        return replace(
            result,
            status=PhaseFitStatus.UNRESOLVED,
            ambiguity_reason=direct_role_authority.reason,
            failure_kind=(
                PhaseFailureKind.SEPARATOR_MATERIAL_CONFLICT
                if direct_role_authority.state == EvidenceState.CONTRADICTED
                else PhaseFailureKind.DIRECT_ROLE_BINDING_AUTHORITY_UNAVAILABLE
            ),
            winner_basis=None,
        )
    if (
        result.status == PhaseFitStatus.RESOLVED
        and inferred
        and (
            authority is None
            or authority.state != EvidenceState.SUPPORTED
        )
        and nominal_evidence is None
    ):
        return replace(
            result,
            status=PhaseFitStatus.UNRESOLVED,
            ambiguity_reason=(
                "an inferred normal adjacency requires independently closed "
                "global phase, W, and pitch authority"
            ),
            failure_kind=(
                PhaseFailureKind.GLOBAL_LATTICE_AUTHORITY_UNAVAILABLE
            ),
            winner_basis=None,
        )
    if (
        result.status == PhaseFitStatus.RESOLVED
        and any(
            item.state != AdjacencyCoverageState.COMPLETE
            for item in inferred
        )
    ):
        missing = ", ".join(
            str(item.relation_ordinal)
            for item in inferred
            if item.state != AdjacencyCoverageState.COMPLETE
        )
        return replace(
            result,
            status=PhaseFitStatus.UNRESOLVED,
            ambiguity_reason=(
                "registered sequence queries do not fully cover inferred "
                f"normal adjacency ordinals: {missing}"
            ),
            failure_kind=(
                PhaseFailureKind.ADJACENCY_OBSERVATION_COVERAGE_INCOMPLETE
            ),
            winner_basis=None,
        )
    if (
        result.status == PhaseFitStatus.RESOLVED
        and inferred
        and nominal_evidence is None
        and (
            outer_authority is None
            or outer_authority.state != EvidenceState.SUPPORTED
        )
    ):
        return replace(
            result,
            status=PhaseFitStatus.UNRESOLVED,
            ambiguity_reason=(
                "normal Grid inference requires one directly bound long-axis "
                "role on each outer output frame"
            ),
            failure_kind=(
                PhaseFailureKind.OUTER_FRAME_OBSERVATION_AUTHORITY_UNAVAILABLE
            ),
            winner_basis=None,
        )
    if result.status == PhaseFitStatus.RESOLVED and result.best is not None:
        width_inference = result.best.frame_width_inference
        if (
            nominal_evidence is None
            and
            width_inference is not None
            and width_inference.state != EvidenceState.SUPPORTED
        ):
            return replace(
                result,
                status=PhaseFitStatus.UNRESOLVED,
                ambiguity_reason=(
                    "measured source W does not intersect this placement's W"
                    if width_inference.failure_kind
                    == FrameWidthInferenceFailureKind.SOURCE_WIDTH_PLACEMENT_CONFLICT
                    else "direct-lattice W cannot discard a registered local "
                    "boundary and then authorize missing roles"
                    if width_inference.failure_kind
                    == FrameWidthInferenceFailureKind
                    .DIRECT_LATTICE_COUNTEREVIDENCE
                    else "missing opposite Frame roles require one independently "
                    "closed source-level common W"
                ),
                failure_kind=(
                    PhaseFailureKind.FRAME_WIDTH_INFERENCE_UNAVAILABLE
                ),
                winner_basis=None,
            )
    return result
