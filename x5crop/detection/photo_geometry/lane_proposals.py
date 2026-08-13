"""Per-lane orchestration of bounded cross and sequence proposals."""

from __future__ import annotations

from ...formats import FramePhysicalSpec
from .chain_proposals import (
    FrameChainProposals,
    LaneObservationInput,
    LanePhysicalProposals,
)
from .cross_proposals import build_cross_axis_proposals
from .direction_proposals import direction_class_key, physical_bound_direction_classes
from .observation_types import (
    SequenceGroupingWork,
    SequenceHypothesisGroup,
)
from .physical_identity import physical_fact_id
from .sequence_grouping import (
    build_separator_band_groups,
    build_sequence_groups,
    ordered_ordinal_roles,
)
from .sequence_role_proposals import (
    build_separator_band_role_proposals,
    build_sequence_role_proposals,
)
from .source_geometry import SourceScanGeometry
from .sequence_models import SequenceDiscoveryKind

def build_lane_physical_proposals(
    lane: LaneObservationInput,
    frame_spec: FramePhysicalSpec,
) -> LanePhysicalProposals:
    geometry = SourceScanGeometry.create(
        frame_spec,
        width_scale_px_per_mm=lane.width_scale_px_per_mm,
        height_scale_px_per_mm=lane.height_scale_px_per_mm,
    )
    roles = ordered_ordinal_roles(lane.output_slot_count)
    cross_proposals = build_cross_axis_proposals(lane, geometry)
    frame_proposals: list[FrameChainProposals] = []
    discovery_kinds = (
        SequenceDiscoveryKind.NORMAL_DEFAULT,
        SequenceDiscoveryKind.DIRECT_EXCEPTION,
    )
    for discovery_kind in discovery_kinds:
        band_proposals = build_separator_band_role_proposals(
            lane,
            geometry,
            roles,
        )
        if (
            discovery_kind == SequenceDiscoveryKind.NORMAL_DEFAULT
            and band_proposals
        ):
            proposals = tuple(
                proposal
                for band in band_proposals
                for proposal in (
                    band.left_role_proposal,
                    band.right_role_proposal,
                )
            )
            groups, work = build_separator_band_groups(
                band_proposals,
                relation_count=lane.output_slot_count - 1,
            )
        else:
            isolated_proposals = build_sequence_role_proposals(
                lane,
                geometry,
                roles,
                discovery_kind=discovery_kind,
            )
            isolated_groups, isolated_work = build_sequence_groups(
                isolated_proposals,
                roles,
                frame_width_lower_px=(
                    geometry.width_state.extent_projection_px().minimum
                ),
            )
            if discovery_kind == SequenceDiscoveryKind.DIRECT_EXCEPTION:
                # Without a supported G_source, an exceptional chain may not
                # infer any adjacency.  Every internal END/START role must be
                # directly present; otherwise the group is only a collection
                # of isolated lines, not a complete physical sequence.
                required_local_roles = set(
                    range(1, lane.output_slot_count * 2 - 1)
                )
                isolated_groups = tuple(
                    group
                    for group in isolated_groups
                    if required_local_roles.issubset(
                        role.role.role_index
                        for role in group.role_proposals
                    )
                )
                band_groups = tuple(
                    SequenceHypothesisGroup(
                        group_id=physical_fact_id(
                            "direct-separator-band-seed",
                            band.proposal_id,
                        ),
                        phase_interval_px=band.phase_interval_px,
                        role_proposals=(
                            band.left_role_proposal,
                            band.right_role_proposal,
                        ),
                        separator_band_proposals=(band,),
                        ambiguous_proposal_ids=(),
                        exclusion_authorized=True,
                    )
                    for band in band_proposals
                )
                proposals = tuple(
                    (
                        *isolated_proposals,
                        *(
                            role
                            for band in band_proposals
                            for role in (
                                band.left_role_proposal,
                                band.right_role_proposal,
                            )
                        ),
                    )
                )
                groups = (*isolated_groups, *band_groups)
                work = SequenceGroupingWork(
                    phase_seed_count=(
                        isolated_work.phase_seed_count + len(band_groups)
                    ),
                    ordinal_role_lookup_count=(
                        isolated_work.ordinal_role_lookup_count
                    ),
                    ordinal_role_match_count=(
                        isolated_work.ordinal_role_match_count
                        + 2 * len(band_groups)
                    ),
                )
            else:
                proposals = isolated_proposals
                groups = isolated_groups
                work = isolated_work
        if groups:
            frame_proposals.append(
                FrameChainProposals(
                    frame_spec=frame_spec,
                    discovery_kind=discovery_kind,
                    initial_source_scan_geometry=geometry,
                    roles=roles,
                    role_proposals=proposals,
                    separator_band_proposals=band_proposals,
                    sequence_groups=groups,
                    grouping_work=work,
                )
            )
    observations = tuple(
        {
            str(observation.observation_id): observation
            for cross_proposal in cross_proposals
            for observation in cross_proposal.raw_observations
        }.values()
    )
    directions = physical_bound_direction_classes(cross_proposals)
    return LanePhysicalProposals(
        lane=lane,
        frame_proposals=tuple(frame_proposals),
        cross_proposals=cross_proposals,
        raw_top_bottom_observations=tuple(
            sorted(observations, key=lambda item: str(item.observation_id))
        ),
        direction_classes=tuple(
            sorted(directions, key=direction_class_key)
        ),
    )
