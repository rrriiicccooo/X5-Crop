"""Materialize the complete retained H set using the existing output owners."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain import EvidenceState
from ...run_local_identity import run_local_id
from ..gate_checks import DetectionFailureFact, GateGap, failure_fact
from ..source_core import SourceLaneEvidence
from .output_model import CommonOutputFootprint, OutputBoundaryUse, OutputFootprint
from .template_cross_model import (
    CrossFailureKind, CrossFit, CrossFitCompetition, CrossFitStatus,
    CrossHeightProjectionBasis, CrossLineProjectionBasis,
    TemplateCrossInput,
)
from .template_cross_support import SupportFitCompetition, SupportFitStatus, fit_enclosing_support
from .model import BoundaryRole
from .template_family_membership import MembershipState
from .template_feasible_geometry import project_format_placement
from .template_measurement_plan_model import MAX_CROSS_PAIRS
from .template_output import (
    common_aperture_output_footprint, common_direct_use_budget_assessment,
    output_footprint_from_template_placement,
)
from .template_enclosing_support_aperture import not_applicable_enclosing_support_aperture_authority
from .template_aspect_ratio import reconcile_direct_aperture_height
from .template_aspect_ratio_model import ApertureAspectRatioAuthority
from .template_direct_role_aperture_domain import (
    DirectRoleApertureDomainAuthority, assess_direct_role_aperture_domain_authority,
)
from .template_family_membership import MembershipProjectionCoverage
from .template_phase_model import PhaseFitResult, PhaseFitStatus
from .template_placement import FormatPlacement
from .template_registration import CrossRegistrationWorkReceipt


@dataclass(frozen=True)
class CommonHOutputWork:
    member_count: int
    reused_projection_count: int
    projection_count: int
    output_evaluation_count: int
    common_output_evaluation_count: int
    member_budget_evaluation_bound: int

    def __post_init__(self) -> None:
        values = tuple(self.__dict__.values())
        if any(type(value) is not int or value < 0 for value in values) or (
            not 1 < self.member_count <= MAX_CROSS_PAIRS
            or self.reused_projection_count + self.projection_count > self.member_count
            or self.member_budget_evaluation_bound != self.member_count * self.common_output_evaluation_count
        ):
            raise ValueError("common H output work is incomplete or unbounded")


@dataclass(frozen=True)
class CommonHOutput:
    """A shared crop, keeping every native interpretation and its proof.

    Materialization does not grant selection authority. In particular, the
    complete retained group set is not proof of upstream search completeness.
    """

    placement_id: str
    placements: tuple[FormatPlacement, ...]
    group_member_indices: tuple[tuple[int, ...], tuple[int, ...]]
    output_footprints: tuple[CommonOutputFootprint, ...]
    failure: DetectionFailureFact | None
    work: CommonHOutputWork

    def __post_init__(self) -> None:
        ids = tuple(p.placement_id for p in self.placements)
        if (not self.placement_id or self.placement_id in ids
                or len(set(ids)) != len(ids) or len(ids) != self.work.member_count
                or len(self.group_member_indices) != 2
                or any(type(i) is not int or not 0 <= i < len(ids)
                       for view in self.group_member_indices for i in view)
                or set(i for view in self.group_member_indices for i in view) != set(range(len(ids)))):
            raise ValueError("common H output lost its complete group mapping")
        first = self.placements[0]
        if any(p.lane_id != first.lane_id or p.output_slot_count != first.output_slot_count
               or p.sequence_fit != first.sequence_fit or p.source_scan_geometry != first.source_scan_geometry
               or p.global_lattice_authority != first.global_lattice_authority
               for p in self.placements):
            raise ValueError("common H output requires fixed W and shared source authority")
        if self.failure is None:
            if (len(self.output_footprints) != first.output_slot_count
                    or self.work.common_output_evaluation_count != first.output_slot_count
                    or self.work.output_evaluation_count != self.work.projection_count * first.output_slot_count
                    or self.work.projection_count + self.work.reused_projection_count != len(ids)):
                raise ValueError("common H output must cover every member and slot")
            for ordinal, output in enumerate(self.output_footprints, 1):
                if (tuple(m.envelope.placement_id for m in output.members) != ids
                        or any(m.envelope.lane_ordinal != ordinal for m in output.members)):
                    raise ValueError("common H output changed member or slot ownership")
        elif not isinstance(self.failure, DetectionFailureFact) or self.output_footprints:
            raise ValueError("failed common H output cannot expose a partial crop")
        if self.work.output_evaluation_count > self.work.projection_count * first.output_slot_count:
            raise ValueError("common H output evaluation count exceeds member slots")
        if self.work.common_output_evaluation_count > first.output_slot_count:
            raise ValueError("common H output evaluation count exceeds slots")

    @property
    def lane_id(self) -> str:
        return self.placements[0].lane_id

    @property
    def output_slot_count(self) -> int:
        return self.placements[0].output_slot_count

    @property
    def sequence_fit(self):
        return self.placements[0].sequence_fit

    @property
    def source_scan_geometry(self):
        return self.placements[0].source_scan_geometry

    @property
    def width_axis(self):
        return self.placements[0].width_axis

    @property
    def enclosing_support_aperture_authority(self):
        return not_applicable_enclosing_support_aperture_authority()

    @property
    def direct_use_budget_assessments(self):
        return tuple(common_direct_use_budget_assessment(output) for output in self.output_footprints)


@dataclass(frozen=True)
class CommonHOutputAuthority:
    """Member authority for one common crop; final output checks stay in Gate."""

    placement_id: str
    member_placement_ids: tuple[str, ...]
    membership_coverage: tuple[MembershipProjectionCoverage, ...] | None
    aperture_aspect_ratio_authorities: tuple[ApertureAspectRatioAuthority, ...]
    direct_role_aperture_domain_authorities: tuple[DirectRoleApertureDomainAuthority | None, ...]
    enclosing_support_competitions: tuple[SupportFitCompetition, ...]
    state: EvidenceState
    failure: DetectionFailureFact | None

    def __post_init__(self) -> None:
        count = len(self.member_placement_ids)
        if (not self.placement_id or not 1 < count <= MAX_CROSS_PAIRS
                or len(set(self.member_placement_ids)) != count
                or any(not isinstance(identity, str) or not identity for identity in self.member_placement_ids)
                or self.membership_coverage is not None and any(
                    not isinstance(item, MembershipProjectionCoverage) for item in self.membership_coverage)
                or len(self.aperture_aspect_ratio_authorities) != count
                or len(self.direct_role_aperture_domain_authorities) != count
                or len(self.enclosing_support_competitions) != count
                or any(item.evaluated_candidate_count > 1 for item in self.enclosing_support_competitions)
                or self.state not in (EvidenceState.SUPPORTED, EvidenceState.CONTRADICTED, EvidenceState.UNAVAILABLE)
                or (self.state == EvidenceState.SUPPORTED) != (self.failure is None)
                or self.failure is not None and not isinstance(self.failure, DetectionFailureFact)):
            raise ValueError("common H authority lost its complete member proof")
        if self.state == EvidenceState.SUPPORTED and (
            self.membership_coverage is None
            or any(item.status != SupportFitStatus.UNRESOLVED or item.best is not None
                   for item in self.enclosing_support_competitions)
            or any(item.blocks_cross_resolution for item in self.aperture_aspect_ratio_authorities)
            or any(item is not None and item.state != EvidenceState.SUPPORTED
                   for item in self.direct_role_aperture_domain_authorities)
        ):
            raise ValueError("common H authority does not cover all interpretations")


def assess_common_h_output_authority(
    common: CommonHOutput, *, phase: PhaseFitResult, cross: CrossFitCompetition,
    registration: CrossRegistrationWorkReceipt,
    membership_coverage: tuple[MembershipProjectionCoverage, ...] | None,
    cross_input: TemplateCrossInput,
) -> CommonHOutputAuthority:
    expected = common_h_fit_members(cross, registration)
    if (phase.status != PhaseFitStatus.RESOLVED or expected is None
            or tuple(p.cross_fit for p in common.placements) != expected[0]
            or common.group_member_indices != expected[1]
            or any(p.sequence_fit != phase.best for p in common.placements)):
        raise ValueError("common H authority changed its retained fits or fixed W")
    direct = phase.direct_role_binding_authority
    requires_domain = direct is not None and bool(direct.aperture_domain_required_role_indices)
    aspects = tuple(reconcile_direct_aperture_height(
        cross.aperture_aspect_ratio_authority, placement.cross_fit.height_compatibility_px,
    ) for placement in common.placements)
    domains = tuple(assess_direct_role_aperture_domain_authority(
        phase.best, placement.cross_fit, direct,
    ) if requires_domain else None for placement in common.placements)
    traces = cross_input.registered_trace_coordinates_px or tuple(sorted({
        trace for binding in (*cross_input.top_bindings, *cross_input.bottom_bindings)
        for trace in binding.trace_coordinates_px
    }))
    support = tuple(fit_enclosing_support(
        template=cross_input.template, fixed_height=cross_input.fixed_height_px,
        canonical_height_px=cross_input.canonical_fixed_height_px,
        reference_trace_px=cross_input.lane_reference_trace_px,
        top_bindings=tuple(b for b in p.cross_fit.direct_bindings if b.role == BoundaryRole.TOP),
        bottom_bindings=tuple(b for b in p.cross_fit.direct_bindings if b.role == BoundaryRole.BOTTOM),
        registered_trace_coordinates_px=traces,
        longitudinal_support_domain_groups_px=cross_input.longitudinal_support_domain_groups_px,
        minimum_shared_trace_support=cross_input.minimum_shared_trace_support,
        maximum_evaluated_candidates=1,
    ) for p in common.placements)
    failure = None
    state = EvidenceState.SUPPORTED
    if membership_coverage is None:
        state = EvidenceState.UNAVAILABLE
        failure = failure_fact(GateGap.CROSS_AUTHORITY_UNAVAILABLE,
                               detail="an H membership interpretation is unsearched or absent from solver inputs")
    elif any(item.blocks_cross_resolution for item in aspects):
        state = EvidenceState.CONTRADICTED
        failure = failure_fact(GateGap.APERTURE_ASPECT_RATIO_DIRECT_CONFLICT)
    elif any(item.status != SupportFitStatus.UNRESOLVED or item.best is not None for item in support):
        state = EvidenceState.UNAVAILABLE
        failure = failure_fact(GateGap.CROSS_AUTHORITY_UNAVAILABLE,
                               detail="common aperture output does not cover an enclosing-support interpretation")
    else:
        unsupported = next((item for item in domains if item is not None and item.state != EvidenceState.SUPPORTED), None)
        if unsupported is not None:
            state = unsupported.state
            failure = failure_fact(
                GateGap.DIRECT_ROLE_APERTURE_DOMAIN_CONFLICT if state == EvidenceState.CONTRADICTED
                else GateGap.DIRECT_ROLE_APERTURE_DOMAIN_UNAVAILABLE,
                detail=unsupported.reason,
            )
    return CommonHOutputAuthority(
        common.placement_id, tuple(p.placement_id for p in common.placements), membership_coverage,
        aspects, domains, support, state, failure,
    )


def common_h_fit_members(
    cross: CrossFitCompetition, registration: CrossRegistrationWorkReceipt,
) -> tuple[tuple[CrossFit, ...], tuple[tuple[int, ...], tuple[int, ...]]] | None:
    """Retain all groups or none; a display winner cannot define this set."""
    if (cross.status != CrossFitStatus.UNRESOLVED
            or cross.failure_kind != CrossFailureKind.NON_EQUIVALENT_FITS
            or registration.local_refinement_scope_count
            or registration.membership is None
            or registration.membership.state != MembershipState.COMPLETE
            or cross.aperture_aspect_ratio_authority.blocks_cross_resolution):
        return None
    cross.receipt.validate_bounds()
    views = (cross.fit_groups, cross.conditional_fit_groups)
    members: list[CrossFit] = []
    indices: dict[CrossFit, int] = {}
    mapping = []
    for view in views:
        view_indices = []
        for group in view:
            fit = group.fit
            if (not group.independently_supported or not fit.direct_pair
                    or fit.height_compatibility_px is None
                    or fit.boundary_use != OutputBoundaryUse.APERTURE_PAIR
                    or fit.selected_direction is None
                    or fit.line_projection_basis != CrossLineProjectionBasis.COMPLETE_PHYSICAL_DIRECTION
                    or fit.height_projection_basis != CrossHeightProjectionBasis.COMPLETE_PHYSICAL_INTERVAL
                    or fit.longitudinal_projection_authority.state != EvidenceState.SUPPORTED
                    or any(not b.role_authorized or not b.has_independent_spatial_support for b in fit.direct_bindings)):
                return None
            if fit not in indices:
                indices[fit] = len(members)
                members.append(fit)
            view_indices.append(indices[fit])
        mapping.append(tuple(view_indices))
    if not 1 < len(members) <= MAX_CROSS_PAIRS:
        return None
    return tuple(members), (mapping[0], mapping[1])


def materialize_common_h_output(
    placements: tuple[FormatPlacement, ...],
    group_member_indices: tuple[tuple[int, ...], tuple[int, ...]],
    *, lane: SourceLaneEvidence, layout: str,
    reusable: tuple[tuple[FormatPlacement, tuple[OutputFootprint, ...]], ...] = (),
) -> CommonHOutput:
    """Compose no candidates and read no pixels; share existing native outputs."""
    if not 1 < len(placements) <= MAX_CROSS_PAIRS:
        raise ValueError("common H materialization requires a bounded complete set")
    cached = {p.placement_id: (p, outputs) for p, outputs in reusable}
    native = []
    reused = projections = evaluations = common_evaluations = 0
    outputs = ()
    failure = None
    try:
        for placement in placements:
            prior = cached.get(placement.placement_id)
            if prior is not None:
                if prior[0] != placement or len(prior[1]) != placement.output_slot_count:
                    raise ValueError("common H reuse changed a native placement or omitted a slot")
                native.append(prior[1])
                reused += 1
                continue
            projections += 1
            projection = project_format_placement(placement)
            member_outputs = []
            for ordinal in range(1, placement.output_slot_count + 1):
                evaluations += 1
                member_outputs.append(output_footprint_from_template_placement(
                    placement, projection, lane=lane, lane_ordinal=ordinal, layout=layout))
            native.append(tuple(member_outputs))
        common_outputs = []
        for i in range(placements[0].output_slot_count):
            common_evaluations += 1
            common_outputs.append(common_aperture_output_footprint(placements, tuple(member[i] for member in native)))
        outputs = tuple(common_outputs)
    except ValueError as error:
        failure = failure_fact(GateGap.OUTPUT_FOOTPRINT_UNAVAILABLE, detail=str(error))
    return CommonHOutput(
        placement_id=run_local_id("common-h-output", tuple(p.placement_id for p in placements)),
        placements=placements, group_member_indices=group_member_indices,
        output_footprints=outputs, failure=failure,
        work=CommonHOutputWork(len(placements), reused, projections, evaluations,
                              common_evaluations, len(placements) * common_evaluations),
    )
