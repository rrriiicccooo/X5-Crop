"""Immutable physical signature of one selected complete chain."""

from __future__ import annotations

from .chains import CompleteFormatChain


def selected_chain_physical_signature(
    chain: CompleteFormatChain,
) -> tuple[object, ...]:
    """Cover every physical fact selection authorized before sampling."""

    direction = chain.lane_geometry.direction
    return (
        chain.placement_id,
        chain.frame_spec,
        chain.output_slot_count,
        chain.source_scan_geometry.geometry_id,
        chain.source_scan_geometry.width_state.vertices,
        chain.source_scan_geometry.height_state.vertices,
        direction.direction_id,
        direction.canonical_angle_degrees,
        direction.full_angle_interval_degrees,
        (
            chain.sequence.lane_gap_model.gap_model_id,
            chain.sequence.lane_gap_model.state,
            chain.sequence.lane_gap_model.gap_interval_px,
            chain.sequence.lane_gap_model.supporting_observation_ids,
            chain.sequence.lane_gap_model.unresolved_observation_ids,
        ),
        tuple(
            (
                relation.relation_ordinal,
                relation.kind,
                relation.delta_interval_px,
                relation.canonical_delta_px,
                relation.observation_ids,
            )
            for relation in chain.sequence.local_advance_relations
        ),
        tuple(
            (
                str(band.observation.observation_id),
                band.relation_ordinal,
                band.left_role_index,
                band.right_role_index,
            )
            for band in chain.sequence.separator_bands
        ),
        tuple(
            (
                observation.role.role_index,
                observation.run_id,
                None
                if observation.observation_id is None
                else str(observation.observation_id),
                observation.fit_position_interval_px,
                observation.full_position_interval_px,
                observation.safety_position_interval_px,
            )
            for observation in chain.sequence.observations
        ),
        chain.sequence.canonical_positions_px,
        chain.sequence.full_positions_px,
        chain.cross.top_canonical_positions_px,
        chain.cross.bottom_canonical_positions_px,
        chain.cross.top_full_positions_px,
        chain.cross.bottom_full_positions_px,
        tuple(
            (
                evidence.role,
                evidence.run_id,
                str(evidence.observation.observation_id),
                evidence.fit_position_at_lane_reference_px,
                evidence.full_position_at_lane_reference_px,
            )
            for evidence in chain.cross.evidence
        ),
        tuple(
            (
                frame.lane_ordinal,
                tuple(
                    (
                        boundary.role,
                        boundary.canonical_position_px,
                        boundary.full_position_interval_px,
                        boundary.full_direction_interval_degrees,
                        boundary.position_observation_ids,
                    )
                    for boundary in (
                        frame.start,
                        frame.end,
                        frame.top,
                        frame.bottom,
                    )
                ),
            )
            for frame in chain.fixed_frames.frames
        ),
    )
