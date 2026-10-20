"""Validate every registered phase member with its own output context.

This portfolio is conditional evidence over the complete recorded producers.
It does not select a phase, grant an ordinal mapping, or publish an output.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum

from ...domain import EvidenceState, FiniteInterval, ObservationId
from ...run_local_identity import run_local_id
from .lane_preparation import TemplateCrossContext, prepare_template_cross_context
from .line_observations import PhotoBoundaryObservation
from .output_model import CommonOutputFootprint, DirectUseBudgetAssessment, OutputFootprint
from .source_geometry import SourceScanGeometry
from .template_adjacency_topology import PhaseCandidateAdjacencyAssessment, assess_phase_candidate_adjacency
from .template_cross_model import CrossFit, CrossFitStatus, CrossFailureKind, CrossSearchReceipt
from .template_aspect_ratio_model import ApertureAspectRatioAuthority
from .template_family_membership import MembershipState
from .template_direct_role_aperture_domain import assess_direct_role_aperture_domain_authority
from .template_direct_role_authority import intrinsic_direct_role_authority_bases
from .template_feasible_geometry import project_format_placement
from .template_frame_width import SourceFrameWidthAuthority, calibrate_source_frame_width
from .template_lattice_authority import global_lattice_authority_matches_fit
from .template_measurement_plan_model import MAX_CROSS_PAIRS, MAX_WORK_UNITS
from .template_model import SequenceFit, SourceFrameWidthAuthorityBasis, TemplateSearchReceipt, TemplateSpec
from .template_model import MAX_TEMPLATE_FIT_PASSES
from .template_output import (
    common_phase_output_footprint, output_footprint_from_template_placement,
    template_direct_use_budget_assessment,
)
from .template_phase_candidate_model import _phase_residual_compatible
from .template_phase_membership import PhaseCompetitionMember, PhaseCompetitionScope
from .template_phase_model import (
    GlobalLatticeAuthorityEvidence, PhaseCandidateAuthorityProjection,
    PhaseFailureKind, PhaseFitResult, PhaseFitStatus,
)
from .template_phase_observations import _refine_local_role_bindings
from .template_phase_refinement import (
    _apply_final_lattice_contract, _attach_selected_candidate_authorities,
    _project_late_local_candidate, conditional_phase_geometry_failure,
)
from .template_placement import FormatPlacement, compose_format_placement, resolved_cross_support_domains_px
from .template_registration import local_cross_refinements_closed, membership_projection_coverage
from .template_coarse_sides import CoarsePairGeometryPreparation
from .template_residual import derive_adjacency_relations


class PhaseMemberOutputGap(str, Enum):
    PROJECTION_NOT_EVALUATED = "projection_not_evaluated"
    PROJECTION_FAILED = "projection_failed"
    RESIDUAL_INCOMPATIBLE = "residual_incompatible"
    HOLDER_ADMISSION_UNAVAILABLE = "holder_admission_unavailable"
    SOURCE_DOMAIN_UNAVAILABLE = "source_domain_unavailable"
    PHASE_ANCHOR_CEILING_UNAVAILABLE = "phase_anchor_ceiling_unavailable"
    PHASE_GEOMETRY_UNAVAILABLE = "phase_geometry_unavailable"
    LATTICE_IDENTITY_UNQUALIFIED = "lattice_identity_unqualified"
    NATIVE_ADJACENCY_CONTRADICTED = "native_adjacency_contradicted"
    SOURCE_WIDTH_CONFLICT = "source_width_conflict"
    CROSS_CONTEXT_UNAVAILABLE = "cross_context_unavailable"
    CROSS_UNRESOLVED = "cross_unresolved"
    CROSS_MEMBERSHIP_INCOMPLETE = "cross_membership_incomplete"
    APERTURE_DOMAIN_UNAVAILABLE = "aperture_domain_unavailable"
    ENCLOSING_APERTURE_CONFLICT = "enclosing_aperture_conflict"
    OUTPUT_UNAVAILABLE = "output_unavailable"
    OUTPUT_PREREQUISITE_UNAVAILABLE = "output_prerequisite_unavailable"
    OUTPUT_BUDGET_UNAVAILABLE = "output_budget_unavailable"
    WORK_BOUND_EXCEEDED = "work_bound_exceeded"


# Separate validation work from the measurement compiler's single-pass budget.
# At most the existing six producer passes are retained. Each owner's local
# numerical bounds still apply; reaching this aggregate cap invalidates the
# complete proof, including any already evaluated prefix.
MAX_COMPLETE_PHASE_OUTPUT_WORK_UNITS = MAX_TEMPLATE_FIT_PASSES * MAX_WORK_UNITS


@dataclass(frozen=True)
class PhaseMemberCrossInput:
    template: TemplateSpec
    fixed_height_px: FiniteInterval
    canonical_fixed_height_px: float
    longitudinal_support_domain_groups_px: tuple[tuple[FiniteInterval, ...], ...]


@dataclass(frozen=True)
class PhaseMemberCrossCompetition:
    status: CrossFitStatus
    best: CrossFit | None
    runner_up: CrossFit | None
    receipt: CrossSearchReceipt
    failure_kind: CrossFailureKind | None
    aperture_aspect_ratio_authority: ApertureAspectRatioAuthority


def _member_registration_ids(observations: tuple[PhotoBoundaryObservation, ...]) -> tuple[ObservationId, ...]:
    # A replay reserves canonical names before allocating new member lines.
    # Sort the same physical collection independently of those new ordinals.
    return tuple(item.observation_id for item in sorted(observations, key=lambda item: (
        item.role.value, str(item.observation_id).rpartition(":")[0],
        tuple(sorted(map(str, item.transition_ids))),
    )))


@dataclass(frozen=True)
class PhaseMemberCrossContext:
    """Replayable member facts; shared registered lines remain lane-owned."""
    source_scan_geometry: SourceScanGeometry
    initial_source_scan_geometry: SourceScanGeometry
    cross_input: PhaseMemberCrossInput
    competition: PhaseMemberCrossCompetition
    membership_state: MembershipState | None
    membership_scope_states: tuple[MembershipState, ...]
    membership_projection_complete: bool
    local_refinements_closed: bool
    solver_top_observation_ids: tuple[ObservationId, ...]
    solver_bottom_observation_ids: tuple[ObservationId, ...]
    registration_observation_ids: tuple[ObservationId, ...]

    def __post_init__(self) -> None:
        from .template_aspect_ratio import apply_inferred_aperture_height
        from .template_cross import calibrate_source_frame_height
        initial = self.initial_source_scan_geometry
        if (self.cross_input.fixed_height_px != initial.height_state.extent_projection_px()
                or self.cross_input.canonical_fixed_height_px != initial.height_state.extent_projection_px().center):
            raise ValueError("member Cross lost its independent initial H")
        expected = calibrate_source_frame_height(apply_inferred_aperture_height(
            initial, self.competition.aperture_aspect_ratio_authority), self.competition)
        if replace(expected, geometry_id=self.source_scan_geometry.geometry_id) != self.source_scan_geometry:
            raise ValueError("member H borrowed another Cross result")

    @classmethod
    def from_context(cls, context: TemplateCrossContext):
        cross = context.competition
        registration = context.registration
        coverage = membership_projection_coverage(registration.membership_receipt,
            registration.observations, (*context.cross_input.top_bindings, *context.cross_input.bottom_bindings))
        membership = registration.membership_receipt
        return cls(context.source_scan_geometry, context.initial_source_scan_geometry,
            PhaseMemberCrossInput(context.cross_input.template, context.cross_input.fixed_height_px,
                context.cross_input.canonical_fixed_height_px, context.cross_input.longitudinal_support_domain_groups_px),
            PhaseMemberCrossCompetition(cross.status, cross.best, cross.runner_up, cross.receipt,
                cross.failure_kind, cross.aperture_aspect_ratio_authority),
            None if membership is None else membership.state,
            () if membership is None else tuple(scope.state for scope in membership.scopes),
            coverage is not None, local_cross_refinements_closed(registration.work_receipt),
            tuple(binding.observation_id for binding in context.cross_input.top_bindings),
            tuple(binding.observation_id for binding in context.cross_input.bottom_bindings),
            _member_registration_ids(registration.observations))


@dataclass(frozen=True)
class PhaseMemberOutputWork:
    role_lookup_count: int = 0
    local_binding_count: int = 0
    late_projection_count: int = 0
    phase_authority_check_bound: int = 0
    width_evaluation_count: int = 0
    cross_context_count: int = 0
    cross_evaluated_fit_count: int = 0
    coarse_geometry_lookup_count: int = 0
    coarse_geometry_preparation_count: int = 0
    cross_local_fit_count: int = 0
    cross_local_event_count: int = 0
    cross_local_scope_count: int = 0
    cross_local_trace_count: int = 0
    adjacency_relation_check_count: int = 0
    adjacency_trace_check_count: int = 0
    registered_fact_check_bound: int = 0
    projection_extreme_count: int = 0
    composition_count: int = 0
    projection_count: int = 0
    output_evaluation_count: int = 0
    budget_evaluation_count: int = 0
    peak_temporary_bytes: int = 0

    def __post_init__(self) -> None:
        if any(type(value) is not int or value < 0 for value in self.__dict__.values()):
            raise ValueError("phase member output work must be nonnegative integers")
        if (self.late_projection_count > 1 or self.width_evaluation_count > 1
                or self.cross_context_count > 1 or self.composition_count > 1
                or self.projection_count > self.composition_count
                or self.coarse_geometry_preparation_count > self.coarse_geometry_lookup_count
                or self.budget_evaluation_count > self.output_evaluation_count):
            raise ValueError("phase member output exceeded its single reconstruction")


@dataclass(frozen=True)
class PhaseMemberOutputProof:
    scope_id: str
    record_ordinal: int
    local_fit: SequenceFit | None
    late_projection: PhaseCandidateAuthorityProjection | None
    phase_assessment: PhaseFitResult | None
    source_frame_width_authority: SourceFrameWidthAuthority | None
    adjacency: PhaseCandidateAdjacencyAssessment | None
    cross_context: PhaseMemberCrossContext | None
    placement: FormatPlacement | None
    output_footprints: tuple[OutputFootprint, ...]
    budgets: tuple[DirectUseBudgetAssessment, ...]
    gaps: tuple[PhaseMemberOutputGap, ...]
    detail: str | None
    work: PhaseMemberOutputWork

    def __post_init__(self) -> None:
        if (not self.scope_id or type(self.record_ordinal) is not int or self.record_ordinal < 0
                or len(set(self.gaps)) != len(self.gaps)
                or any(not isinstance(gap, PhaseMemberOutputGap) for gap in self.gaps)):
            raise ValueError("phase member proof lost its registered identity or gaps")
        if len(self.output_footprints) != len(self.budgets):
            raise ValueError("phase member proof lost output budgets")
        if PhaseMemberOutputGap.OUTPUT_PREREQUISITE_UNAVAILABLE in self.gaps and (
            len(self.gaps) < 2 or self.cross_context is None or self.phase_assessment is None
            or self.cross_context.competition.status != CrossFitStatus.RESOLVED
            or self.placement is not None or self.output_footprints or self.budgets
            or any((self.work.composition_count, self.work.projection_count,
                    self.work.output_evaluation_count, self.work.budget_evaluation_count))
        ):
            raise ValueError("unqualified member must retain its own prerequisites without claiming output evaluation")
        if self.phase_assessment is not None:
            fit = self.phase_assessment.best
            if fit is None or self.phase_assessment.status == PhaseFitStatus.RESOLVED:
                raise ValueError("conditional member evidence cannot declare a phase winner")
            if self.adjacency is None or self.adjacency.fit != fit:
                raise ValueError("phase member adjacency belongs to another final fit")
            if (self.source_frame_width_authority is not None
                    and self.source_frame_width_authority.state == EvidenceState.SUPPORTED
                    and not self.source_frame_width_authority.matches_placement(fit)):
                raise ValueError("phase member borrowed another placement's W")
            lattice = self.phase_assessment.global_lattice_authority
            if (lattice is not None and lattice.state == EvidenceState.SUPPORTED
                    and not global_lattice_authority_matches_fit(lattice, fit)
                    and PhaseMemberOutputGap.LATTICE_IDENTITY_UNQUALIFIED not in self.gaps):
                raise ValueError("phase member borrowed another placement's lattice")
            if self.cross_context is not None and (
                    self.cross_context.cross_input.template != fit.template
                    or self.cross_context.cross_input.longitudinal_support_domain_groups_px
                    != (resolved_cross_support_domains_px(fit),)):
                raise ValueError("phase member borrowed another longitudinal Cross domain")
            if self.cross_context is not None and self.source_frame_width_authority is not None:
                own_width = self.cross_context.initial_source_scan_geometry.width_state
                authority = self.source_frame_width_authority
                if authority.state == EvidenceState.SUPPORTED:
                    if (own_width.extent_projection_px() != authority.width_px
                            or own_width.observation_ids != authority.observation_ids):
                        raise ValueError("member Cross W changed its own width authority")
                elif own_width.observation_ids:
                    raise ValueError("member Cross borrowed a calibrated W without its own authority")
        if self.placement is not None:
            if (self.phase_assessment is None or self.cross_context is None
                    or self.placement.sequence_fit != self.phase_assessment.best
                    or self.placement.cross_fit != self.cross_context.competition.best
                    or self.placement.source_scan_geometry != self.cross_context.source_scan_geometry):
                raise ValueError("phase member output changed its own W/H/Cross context")
        elif self.output_footprints:
            raise ValueError("phase member output has no placement")
        if self.state == EvidenceState.SUPPORTED and (
            self.placement is None or len(self.output_footprints) != self.placement.output_slot_count
            or any(budget.state != EvidenceState.SUPPORTED for budget in self.budgets)
            or any(not output.source_authority_supported for output in self.output_footprints)
            or self.adjacency is None or self.adjacency.state != EvidenceState.SUPPORTED
            or self.phase_assessment is None or conditional_phase_geometry_failure(self.phase_assessment) is not None
            or self.cross_context is None or self.cross_context.competition.status != CrossFitStatus.RESOLVED
            or not self.cross_context.membership_projection_complete or not self.cross_context.local_refinements_closed
            or self.cross_context.membership_state != MembershipState.COMPLETE
            or any(state != MembershipState.COMPLETE for state in self.cross_context.membership_scope_states)
        ):
            raise ValueError("qualified phase member lacks complete safe output")

    @property
    def state(self) -> EvidenceState:
        return EvidenceState.SUPPORTED if not self.gaps else EvidenceState.UNAVAILABLE


def _conditional_phase(lane, scope, fit, projection) -> PhaseFitResult:
    receipt = TemplateSearchReceipt(
        observation_count=len(lane.phase_input.observations), role_count=len(fit.role_bindings),
        phase_lookup_count=0, role_binding_count=0, adjacency_relation_evaluation_count=0,
        local_refinement_lookup_count=0, local_refinement_binding_count=0,
        phase_hypothesis_count=0, phase_offset_lookup_count=0,
        direct_observation_count=0, inferred_role_count=len(fit.unbound_role_indices),
    )
    return PhaseFitResult(
        fit.template, fit, None, PhaseFitStatus.UNRESOLVED,
        "conditional registered member; discrete selection remains unresolved", receipt,
        lane.phase_competition.registered_direct_observation_ids,
        PhaseFailureKind.DISCRETE_PHASE_AMBIGUOUS,
        best_phase_candidate_authority_projection=projection,
    )


def assess_phase_member_output(lane, scope: PhaseCompetitionScope,
                               member: PhaseCompetitionMember, *,
                               coarse_geometry_preparation=None) -> PhaseMemberOutputProof:
    """Rebuild a given member without using selected W, H or Cross results."""
    gaps = []
    detail = None
    work = PhaseMemberOutputWork()
    local = late = assessed = width = adjacency = context = placement = None
    outputs = budgets = ()

    def result():
        measured_work = replace(work, peak_temporary_bytes=max(work.peak_temporary_bytes,
            4096 + work.role_lookup_count * 32 + work.cross_evaluated_fit_count * 1024
            + work.output_evaluation_count * 4096))
        return PhaseMemberOutputProof(scope.scope_id, member.record_ordinal, local, late,
            assessed, width, adjacency, None if context is None else PhaseMemberCrossContext.from_context(context),
            placement, outputs, budgets,
            tuple(dict.fromkeys(gaps)), detail, measured_work)

    unprojected = member.projection is None
    if not unprojected and (not member.projection.eligible or member.projected_fit is None):
        gaps.append(PhaseMemberOutputGap.PROJECTION_FAILED)
        detail = member.projection.reason
        return result()
    if not (member.input_residual_compatible if unprojected else member.projected_residual_compatible):
        gaps.append(PhaseMemberOutputGap.RESIDUAL_INCOMPATIBLE)
        return result()
    if not member.holder_admitted:
        gaps.append(PhaseMemberOutputGap.HOLDER_ADMISSION_UNAVAILABLE)
    if member.source_domain_admitted is False:
        gaps.append(PhaseMemberOutputGap.SOURCE_DOMAIN_UNAVAILABLE)
    if not member.phase_anchor_ceiling_satisfied:
        gaps.append(PhaseMemberOutputGap.PHASE_ANCHOR_CEILING_UNAVAILABLE)
    fit = member.input_fit if unprojected else member.projected_fit
    phase_input = replace(lane.phase_input, template=fit.template,
        phase_authority_px=scope.phase_authority_px,
        global_lattice_evidence=GlobalLatticeAuthorityEvidence(
            phase_observation_ids=tuple(identity for identity in
                lane.phase_input.global_lattice_evidence.phase_observation_ids
                if scope.phase_authority_px is not None and identity in fit.phase_anchor_observation_ids),
            pitch_observation_ids=lane.phase_input.global_lattice_evidence.pitch_observation_ids,
        ))
    intrinsic = intrinsic_direct_role_authority_bases(
        phase_input.observations, phase_input.sequence_measurement_sets)
    refined = _refine_local_role_bindings(fit, phase_input.observations, phase_input.separator_bands,
        intrinsic_coordinate_authority_ids=frozenset(intrinsic))
    local = refined.fit
    projected, late = _project_late_local_candidate(local, phase_input, allow_direct_rank=True)
    work = replace(work, role_lookup_count=refined.role_lookup_count,
        local_binding_count=refined.binding_count, late_projection_count=int(late is not None))
    if projected is None:
        gaps.append(PhaseMemberOutputGap.PROJECTION_FAILED)
        detail = None if late is None else late.reason
        return result()
    fit = projected
    if not _phase_residual_compatible(fit):
        gaps.append(PhaseMemberOutputGap.RESIDUAL_INCOMPATIBLE)
    phase = _conditional_phase(lane, scope, fit, late or member.projection)
    phase = _attach_selected_candidate_authorities(phase, phase_input, directly_observed_ordinals=())
    analysis = derive_adjacency_relations(fit, phase.adjacency_continuity_observations)
    ordinals = tuple(fact.relation_ordinal for fact in analysis.adjacency_facts)
    scales = lane.lane.scan_canvas.axis_scales
    source = SourceScanGeometry.create(lane.source_scan_geometry.frame_spec,
        width_scale_px_per_mm=scales.width_axis_px_per_mm,
        height_scale_px_per_mm=scales.height_axis_px_per_mm)
    source, width = calibrate_source_frame_width(source, phase, phase_input.observations)
    phase_input = replace(phase_input, global_lattice_evidence=replace(
        phase_input.global_lattice_evidence,
        frame_width_observation_ids=(width.observation_ids
            if width.basis == SourceFrameWidthAuthorityBasis.INDEPENDENT_COMPLETE_FRAMES else ()),
    ))
    assessed = _apply_final_lattice_contract(phase, phase_input,
        directly_observed_ordinals=ordinals, source_frame_width_authority=width)
    fit = assessed.best
    lattice = assessed.global_lattice_authority
    if (lattice is not None and lattice.state == EvidenceState.SUPPORTED
            and not global_lattice_authority_matches_fit(lattice, fit)):
        gaps.append(PhaseMemberOutputGap.LATTICE_IDENTITY_UNQUALIFIED)
    adjacency = assess_phase_candidate_adjacency(fit, phase_input.observations,
        phase_input.separator_bands, phase_input.sequence_measurement_sets,
        phase_input.overlap_edge_pair_observations,
        outer_material_boundaries=phase_input.outer_material_boundaries,
        authorized_source_frame_width_px=(width.width_px
            if width.state == EvidenceState.SUPPORTED and width.matches_placement(fit) else None))
    work = replace(work, phase_authority_check_bound=4, width_evaluation_count=1)
    work = replace(work, registered_fact_check_bound=4 * (
        len(phase_input.observations) + len(phase_input.separator_bands)
        + sum(len(item.transitions) for item in phase_input.sequence_measurement_sets)
        + len(fit.role_bindings)))
    work = replace(work, adjacency_relation_check_count=adjacency.adjacency_check_count + analysis.evaluated_adjacency_count,
                   adjacency_trace_check_count=adjacency.coverage_trace_check_count)
    failure = conditional_phase_geometry_failure(assessed)
    if unprojected and (assessed.direct_role_binding_authority is None
            or assessed.direct_role_binding_authority.state != EvidenceState.SUPPORTED):
        gaps.append(PhaseMemberOutputGap.PROJECTION_NOT_EVALUATED)
    if failure is not None:
        gaps.append(PhaseMemberOutputGap.PHASE_GEOMETRY_UNAVAILABLE)
        detail = failure[1]
    if adjacency.state != EvidenceState.SUPPORTED:
        gaps.append(PhaseMemberOutputGap.NATIVE_ADJACENCY_CONTRADICTED
                    if adjacency.state == EvidenceState.CONTRADICTED
                    else PhaseMemberOutputGap.PHASE_GEOMETRY_UNAVAILABLE)
    if width.state == EvidenceState.CONTRADICTED:
        gaps.append(PhaseMemberOutputGap.SOURCE_WIDTH_CONFLICT)
    if lane.base_cross_registration is None:
        gaps.append(PhaseMemberOutputGap.CROSS_CONTEXT_UNAVAILABLE)
        return result()
    work = replace(work, cross_context_count=1)
    before = (0, 0) if coarse_geometry_preparation is None else (
        coarse_geometry_preparation.lookup_count, coarse_geometry_preparation.preparation_count)
    try:
        context = prepare_template_cross_context(lane, lane.base_cross_registration,
            template=fit.template, phase=assessed, source_geometry=source,
            source_frame_width_authority=width, sequence_fits=(fit,),
            coarse_geometry_preparation=coarse_geometry_preparation)
    except ValueError as error:
        gaps.append(PhaseMemberOutputGap.CROSS_CONTEXT_UNAVAILABLE)
        detail = str(error)
    finally:
        if coarse_geometry_preparation is not None:
            work = replace(work,
                coarse_geometry_lookup_count=coarse_geometry_preparation.lookup_count - before[0],
                coarse_geometry_preparation_count=coarse_geometry_preparation.preparation_count - before[1])
    if context is None:
        return result()
    cross = context.competition
    local_work = context.registration.work_receipt
    base_work = lane.base_cross_registration.work_receipt
    work = replace(work, cross_evaluated_fit_count=cross.receipt.evaluated_fit_count,
        cross_local_fit_count=max(0, local_work.fit_attempt_count - base_work.fit_attempt_count),
        cross_local_event_count=max(0, local_work.constrained_fit_event_count - base_work.constrained_fit_event_count),
        cross_local_scope_count=local_work.local_refinement_scope_count - base_work.local_refinement_scope_count,
        cross_local_trace_count=sum(len(scope.trace_selections) for scope in local_work.local_refinement_scopes)
            - sum(len(scope.trace_selections) for scope in base_work.local_refinement_scopes))
    if cross.status != CrossFitStatus.RESOLVED or cross.best is None:
        gaps.append(PhaseMemberOutputGap.CROSS_UNRESOLVED)
        return result()
    coverage = membership_projection_coverage(context.registration.membership_receipt,
        context.registration.observations,
        (*context.cross_input.top_bindings, *context.cross_input.bottom_bindings))
    if coverage is None or not local_cross_refinements_closed(context.registration.work_receipt):
        gaps.append(PhaseMemberOutputGap.CROSS_MEMBERSHIP_INCOMPLETE)
    direct = assessed.direct_role_binding_authority
    if direct is not None and direct.aperture_domain_required_role_indices:
        domain = assess_direct_role_aperture_domain_authority(fit, cross.best, direct)
        if domain.state != EvidenceState.SUPPORTED:
            gaps.append(PhaseMemberOutputGap.APERTURE_DOMAIN_UNAVAILABLE)
    if gaps:
        # The member keeps its own W/H/Cross facts. A failed prerequisite
        # cannot acquire output qualification through downstream geometry.
        # This is not physical exclusion from the complete common set.
        gaps.append(PhaseMemberOutputGap.OUTPUT_PREREQUISITE_UNAVAILABLE)
        return result()
    lattice = assessed.global_lattice_authority
    if lattice is not None and (lattice.state != EvidenceState.SUPPORTED
            or not global_lattice_authority_matches_fit(lattice, fit)):
        lattice = None
    work = replace(work, composition_count=1)
    try:
        placement = compose_format_placement(lane_id=lane.lane.domain.lane_id,
            frame_spec=source.frame_spec, source_scan_geometry=context.source_scan_geometry,
            sequence_fit=fit, global_lattice_authority=lattice, cross_fit=cross.best,
            width_axis=lane.width_axis, height_axis=lane.height_axis,
            width_authority_px=lane.width_authority_px, height_authority_px=lane.height_authority_px,
            template=fit.template,
            placement_id=run_local_id("phase-member-output", scope.scope_id, member.record_ordinal))
        if placement.enclosing_support_aperture_authority.state == EvidenceState.CONTRADICTED:
            gaps.append(PhaseMemberOutputGap.ENCLOSING_APERTURE_CONFLICT)
        work = replace(work, projection_count=1)
        projection = project_format_placement(placement)
        work = replace(work, projection_extreme_count=projection.extreme_evaluation_count)
        native = []
        for ordinal in range(1, placement.output_slot_count + 1):
            work = replace(work, output_evaluation_count=work.output_evaluation_count + 1)
            native.append(output_footprint_from_template_placement(placement, projection,
                lane=lane.lane, lane_ordinal=ordinal, layout=lane.layout))
        outputs = tuple(native)
        budgets = tuple(template_direct_use_budget_assessment(placement, output) for output in outputs)
        work = replace(work, budget_evaluation_count=len(budgets))
        if any(item.state != EvidenceState.SUPPORTED for item in budgets):
            gaps.append(PhaseMemberOutputGap.OUTPUT_BUDGET_UNAVAILABLE)
    except ValueError as error:
        outputs = budgets = ()
        gaps.append(PhaseMemberOutputGap.OUTPUT_UNAVAILABLE)
        detail = str(error)
    work = replace(work, peak_temporary_bytes=4096 + len(fit.role_bindings) * 1024
        + work.cross_evaluated_fit_count * 1024 + work.output_evaluation_count * 4096)
    return result()


@dataclass(frozen=True)
class CompletePhaseOutputProof:
    scopes: tuple[PhaseCompetitionScope, ...]
    members: tuple[PhaseMemberOutputProof, ...]
    common_outputs: tuple[CommonOutputFootprint, ...]
    common_failure: str | None
    work_units: int
    peak_temporary_bytes: int
    bound_exceeded: bool
    scope: str = "complete_recorded_phase_validation"
    common_work_units: int = 0
    state: EvidenceState = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "state", EvidenceState.SUPPORTED
            if self.common_outputs and self.common_failure is None else EvidenceState.UNAVAILABLE)
        expected = tuple((scope.scope_id, member.record_ordinal)
                         for scope in self.scopes for member in scope.members)
        if (tuple((p.scope_id, p.record_ordinal) for p in self.members) != expected
                or type(self.bound_exceeded) is not bool
                or type(self.work_units) is not int or self.work_units < 0
                or type(self.common_work_units) is not int or not 0 <= self.common_work_units <= self.work_units
                or type(self.peak_temporary_bytes) is not int or self.peak_temporary_bytes < 0
                or self.scope != "complete_recorded_phase_validation"):
            raise ValueError("complete phase output omitted or changed a producer member")
        if self.common_outputs and (self.bound_exceeded
                or any(member.state != EvidenceState.SUPPORTED for member in self.members)):
            raise ValueError("common phase window lacks a qualified complete member set")
        if self.common_outputs:
            slots = self.members[0].placement.output_slot_count
            source = self.members[0].placement.source_scan_geometry
            if (len(self.common_outputs) != slots
                    or any(not isinstance(output, CommonOutputFootprint) for output in self.common_outputs)
                    or any(member.placement.source_scan_geometry != source for member in self.members)
                    or any(output.members != tuple(member.output_footprints[index] for member in self.members)
                           for index, output in enumerate(self.common_outputs))):
                raise ValueError("complete common window changed its full member or slot set")
            if self.common_failure is None and any(not output.budget_supported or not output.source_authority_supported
                                                  for output in self.common_outputs):
                raise ValueError("complete common window lacks every member's safe budget")


def build_complete_phase_output(lane, *, retained_review_bytes: int = 0) -> CompletePhaseOutputProof | None:
    return _build_complete_phase_output(lane, retained_review_bytes=retained_review_bytes,
                                       preparation=CoarsePairGeometryPreparation())


def _build_complete_phase_output(lane, *, retained_review_bytes, preparation) -> CompletePhaseOutputProof | None:
    if type(retained_review_bytes) is not int or retained_review_bytes < 0:
        raise ValueError("retained Review bytes must be a nonnegative integer")
    # Resolved single-winner and no-runner cases do not ask for a plural
    # common window. The complete producer ledger is retained in every case.
    if lane.phase_competition.runner_up is None or lane.phase_competition.status == PhaseFitStatus.RESOLVED:
        return None
    scopes = lane.phase_competition.competition_scopes
    proofs = []
    units = 0
    retained_bytes = sum(scope.retained_bytes for scope in scopes)
    preparation_reserve = preparation.reserve_bytes(lane.coarse_support.enclosing_side_facts)
    extent = None if lane.phase_input.source_domain is None else lane.phase_input.source_domain.source_extent
    memory_limit = None if extent is None else 10 * extent.width * extent.height + 32 * 1024 * 1024
    exceeded = lane.phase_competition.status == PhaseFitStatus.BOUND_EXCEEDED or any(
        scope.bound_exceeded for scope in scopes)
    for scope in scopes:
        for member in scope.members:
            temporary_bound = (4096 + len(member.input_fit.role_bindings) * 1024
                               + MAX_CROSS_PAIRS * 1024 + scope.template.count * 4096)
            if memory_limit is not None and retained_review_bytes + retained_bytes + temporary_bound + preparation_reserve > memory_limit:
                exceeded = True
            if exceeded:
                proof = PhaseMemberOutputProof(scope.scope_id, member.record_ordinal,
                    None, None, None, None, None, None, None, (), (),
                    (PhaseMemberOutputGap.WORK_BOUND_EXCEEDED,), None, PhaseMemberOutputWork())
            else:
                proof = assess_phase_member_output(lane, scope, member,
                                                  coarse_geometry_preparation=preparation)
                work = proof.work
                units += (work.role_lookup_count + work.local_binding_count
                    + work.phase_authority_check_bound * len(member.input_fit.role_bindings)
                    + work.cross_evaluated_fit_count + work.output_evaluation_count
                    + work.budget_evaluation_count + work.cross_local_fit_count
                    + work.cross_local_event_count + work.adjacency_relation_check_count
                    + work.cross_local_scope_count + work.cross_local_trace_count
                    + work.adjacency_trace_check_count + work.registered_fact_check_bound
                    + work.projection_extreme_count + work.composition_count
                    + work.projection_count + work.width_evaluation_count + work.cross_context_count)
                units += work.coarse_geometry_lookup_count + work.coarse_geometry_preparation_count
                exceeded = units > MAX_COMPLETE_PHASE_OUTPUT_WORK_UNITS
            proofs.append(proof)
            retained_bytes += (4096 + len(proof.output_footprints) * 8192
                + (0 if proof.phase_assessment is None else len(proof.phase_assessment.best.role_bindings) * 1024)
                + (0 if proof.cross_context is None else proof.cross_context.competition.receipt.evaluated_fit_count * 1024))
    if (sum(proof.work.coarse_geometry_lookup_count for proof in proofs) != preparation.lookup_count
            or sum(proof.work.coarse_geometry_preparation_count for proof in proofs) != preparation.preparation_count
            or preparation.retained_bytes > preparation_reserve):
        raise ValueError("complete phase output lost shared raw geometry work")
    native = tuple(proof for proof in proofs if proof.placement is not None)
    outputs = ()
    common_work = 0
    failure = None
    if not scopes or not proofs:
        failure = "registered phase member set is unavailable"
    elif exceeded:
        failure = "complete phase reconstruction work bound exceeded"
    elif any(proof.state != EvidenceState.SUPPORTED for proof in proofs):
        failure = "one or more complete phase members lack independent output qualification"
    elif len(native) > MAX_CROSS_PAIRS:
        exceeded = True
        failure = "complete phase common output member bound exceeded"
    elif len(native) <= 1:
        failure = "common phase output requires a bounded complete plural member set"
    else:
        requested_work = sum(1 + 128 * len(native) + points * max(1, points.bit_length())
            for points in (sum(len(proof.output_footprints[index].mandatory_source_footprint) for proof in native)
                           for index in range(native[0].placement.output_slot_count)))
        if units + requested_work > MAX_COMPLETE_PHASE_OUTPUT_WORK_UNITS:
            exceeded = True
            failure = "complete phase common output work bound exceeded"
        else:
            common_work = requested_work
            units += common_work
            try:
                outputs = tuple(common_phase_output_footprint(
                    tuple(proof.placement for proof in native),
                    tuple(proof.output_footprints[ordinal] for proof in native))
                    for ordinal in range(native[0].placement.output_slot_count))
                if any(not output.budget_supported or not output.source_authority_supported for output in outputs):
                    failure = "the complete common fixed window does not satisfy every member's protection budget"
            except ValueError as error:
                failure = str(error)
    retained = sum(scope.retained_bytes for scope in scopes) + sum(
        4096 + len(proof.output_footprints) * 8192
        + (0 if proof.phase_assessment is None else len(proof.phase_assessment.best.role_bindings) * 1024)
        + (0 if proof.cross_context is None else proof.cross_context.competition.receipt.evaluated_fit_count * 1024)
        for proof in proofs)
    retained += len(outputs) * (4096 + 128 * len(native))
    peak = retained + max((proof.work.peak_temporary_bytes for proof in proofs), default=0) + preparation.retained_bytes
    return CompletePhaseOutputProof(scopes, tuple(proofs), outputs, failure, units, peak, exceeded,
                                   common_work_units=common_work)
