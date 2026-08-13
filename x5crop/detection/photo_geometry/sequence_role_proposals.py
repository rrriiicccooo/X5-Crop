"""Role-bound long-axis proposals from direct observations."""

from __future__ import annotations

from ...domain import EvidenceState, FiniteInterval
from ...formats import FramePhysicalSpec
from .chain_proposals import LaneObservationInput
from .interval_math import add, intersect, subtract
from .model import BoundaryRole
from .observation_types import (
    OrdinalBoundaryRole,
    SeparatorBandRoleProposal,
    SequenceRoleProposal,
)
from .physical_identity import physical_fact_id
from .joint_axis_geometry import JointAxisGeometry
from .lane_gap_model import LaneGapModel
from .source_geometry import SourceScanGeometry
from .sequence_models import SequenceDiscoveryKind

def role_relative_projection(
    role: OrdinalBoundaryRole,
    frame_spec: FramePhysicalSpec,
    width_state: JointAxisGeometry,
    gap_model: LaneGapModel | None = None,
) -> FiniteInterval:
    index = role.lane_ordinal - 1
    width_count = index + (1 if role.role == BoundaryRole.END else 0)
    width = width_state.project_affine(
        q_coefficient=width_count * frame_spec.frame_width_mm,
        scale_coefficient=0.0,
    )
    # With no lane model this is only a proposal-coordinate origin.  With an
    # unresolved lane model it is explicitly a zero-gap algebraic basis; the
    # materializer must supply every adjacency as a direct local relation.
    # Neither case grants physical gap authority.
    gap = (
        gap_model.gap_interval_px
        if gap_model is not None
        and gap_model.state == EvidenceState.SUPPORTED
        and gap_model.gap_interval_px is not None
        else FiniteInterval.exact(0.0)
    )
    return add(
        width,
        FiniteInterval(index * gap.minimum, index * gap.maximum),
    )


def role_canonical_relative(
    role: OrdinalBoundaryRole,
    frame_spec: FramePhysicalSpec,
    width_state: JointAxisGeometry,
    gap_model: LaneGapModel | None = None,
) -> float:
    _scale, normalized, _factor = width_state.canonical_state()
    index = role.lane_ordinal - 1
    return (
        (index + (1 if role.role == BoundaryRole.END else 0))
        * frame_spec.frame_width_mm
        * normalized
        + index
        * (
            gap_model.canonical_placement_pitch_px
            - width_state.extent_projection_px().center
            if gap_model is not None
            and gap_model.state == EvidenceState.SUPPORTED
            and gap_model.canonical_placement_pitch_px is not None
            else 0.0
        )
    )


def build_sequence_role_proposals(
    lane: LaneObservationInput,
    geometry: SourceScanGeometry,
    roles: tuple[OrdinalBoundaryRole, ...],
    *,
    discovery_kind: SequenceDiscoveryKind,
) -> tuple[SequenceRoleProposal, ...]:
    runs = {run.run_id: run for run in lane.sequence_profile.runs}
    observed_run_ids = {edge.run_id for edge in lane.sequence_edges}
    band_roles: dict[str, set[BoundaryRole]] = {}
    for band in lane.separator_bands:
        band_roles.setdefault(band.left_run_id, set()).add(BoundaryRole.END)
        band_roles.setdefault(band.right_run_id, set()).add(BoundaryRole.START)
    values: list[SequenceRoleProposal] = []
    for region in lane.sequence_profile.runs:
        run = runs[region.run_id]
        # A tracked profile run is still a measurement intermediate.  Only a
        # canonical BoundaryEdgeObservation may establish an absolute phase;
        # otherwise equal-polarity/ambiguous transition support would bypass
        # the unique observation ledger and become a hidden direct anchor.
        if run.run_id not in observed_run_ids:
            continue
        for role in roles:
            band_bound = role.role in band_roles.get(run.run_id, set())
            if (
                discovery_kind == SequenceDiscoveryKind.DIRECT_EXCEPTION
                and band_bound
            ):
                continue
            if (
                not run.anchor_qualified_for(role.role)
                and not band_bound
            ):
                continue
            relative = role_relative_projection(
                role,
                geometry.frame_spec,
                geometry.width_state,
            )
            values.append(
                SequenceRoleProposal(
                    proposal_id=physical_fact_id(
                        "phase-proposal",
                        geometry.frame_spec.frame_spec_id,
                        run.run_id,
                        role.role_index,
                    ),
                    run_id=run.run_id,
                    role=role,
                    phase_interval_px=subtract(
                        run.coordinate_interval_px,
                        relative,
                    ),
                    transition_ids=run.transition_ids,
                    role_coordinate_px=role_canonical_relative(
                        role,
                        geometry.frame_spec,
                        geometry.width_state,
                    ),
                )
            )
    return tuple(
        sorted(values, key=lambda item: (item.role.role_index, item.proposal_id))
    )


def build_separator_band_role_proposals(
    lane: LaneObservationInput,
    geometry: SourceScanGeometry,
    roles: tuple[OrdinalBoundaryRole, ...],
) -> tuple[SeparatorBandRoleProposal, ...]:
    """Bind a complete normal separator to an adjacency as one observation."""

    slot_count = len(roles) // 2
    if slot_count < 2:
        return ()
    run_by_id = {run.run_id: run for run in lane.sequence_profile.runs}
    frame_width_px = geometry.width_state.extent_projection_px()
    canonical_frame_width_px = geometry.width_state.canonical_state()[1]
    values: list[SeparatorBandRoleProposal] = []
    for band in lane.separator_bands:
        left_run = run_by_id.get(band.left_run_id)
        right_run = run_by_id.get(band.right_run_id)
        if left_run is None or right_run is None:
            continue
        for relation_ordinal in range(1, slot_count):
            left_role = roles[relation_ordinal * 2 - 1]
            right_role = roles[relation_ordinal * 2]
            left_relative = FiniteInterval(
                relation_ordinal * frame_width_px.minimum,
                relation_ordinal * frame_width_px.maximum,
            )
            right_relative = FiniteInterval(
                relation_ordinal * frame_width_px.minimum
                + band.gap_interval_px.minimum,
                relation_ordinal * frame_width_px.maximum
                + band.gap_interval_px.maximum,
            )
            left_phase = subtract(
                left_run.coordinate_interval_px,
                left_relative,
            )
            right_phase = subtract(
                right_run.coordinate_interval_px,
                right_relative,
            )
            phase = intersect(left_phase, right_phase)
            if phase is None:
                continue
            left = SequenceRoleProposal(
                proposal_id=physical_fact_id(
                    "separator-band-role",
                    band.observation_id,
                    relation_ordinal,
                    "left",
                ),
                run_id=left_run.run_id,
                role=left_role,
                phase_interval_px=left_phase,
                transition_ids=left_run.transition_ids,
                role_coordinate_px=(
                    relation_ordinal * canonical_frame_width_px
                ),
                separator_band_observation_id=band.observation_id,
            )
            right = SequenceRoleProposal(
                proposal_id=physical_fact_id(
                    "separator-band-role",
                    band.observation_id,
                    relation_ordinal,
                    "right",
                ),
                run_id=right_run.run_id,
                role=right_role,
                phase_interval_px=right_phase,
                transition_ids=right_run.transition_ids,
                role_coordinate_px=(
                    relation_ordinal * canonical_frame_width_px
                    + band.gap_interval_px.center
                ),
                separator_band_observation_id=band.observation_id,
            )
            values.append(
                SeparatorBandRoleProposal(
                    proposal_id=physical_fact_id(
                        "separator-band-binding",
                        band.observation_id,
                        relation_ordinal,
                    ),
                    band_observation_id=band.observation_id,
                    relation_ordinal=relation_ordinal,
                    phase_interval_px=phase,
                    gap_interval_px=band.gap_interval_px,
                    left_role_proposal=left,
                    right_role_proposal=right,
                )
            )
    return tuple(
        sorted(
            values,
            key=lambda item: (
                item.relation_ordinal,
                item.proposal_id,
            ),
        )
    )
