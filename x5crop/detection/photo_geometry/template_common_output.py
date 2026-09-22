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
)
from .template_family_membership import MembershipState
from .template_feasible_geometry import project_format_placement
from .template_measurement_plan_model import MAX_CROSS_PAIRS
from .template_output import common_aperture_output_footprint, output_footprint_from_template_placement
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
