"""Bind dual-lane candidates to one source W/H state before selection."""

from __future__ import annotations

from dataclasses import replace

from .chain_materialization import materialize_complete_chain_at_source_geometry
from .chains import CompleteFormatChain, SourcePlacementMaterialization


def _compatible_shared_states(
    left: tuple[CompleteFormatChain, ...],
    right: tuple[CompleteFormatChain, ...],
):
    indexed_right = tuple(
        sorted(
            right,
            key=lambda item: (
                item.source_scan_geometry.width_state
                .feasible_scale_interval().minimum,
                item.placement_id,
            ),
        )
    )
    for left_chain in left:
        left_geometry = left_chain.source_scan_geometry
        left_width = left_geometry.width_state.feasible_scale_interval()
        left_height = left_geometry.height_state.feasible_scale_interval()
        for right_chain in indexed_right:
            if right_chain.frame_spec != left_chain.frame_spec:
                continue
            right_geometry = right_chain.source_scan_geometry
            right_width = right_geometry.width_state.feasible_scale_interval()
            if right_width.minimum > left_width.maximum:
                break
            right_height = right_geometry.height_state.feasible_scale_interval()
            if (
                right_width.maximum < left_width.minimum
                or right_height.maximum < left_height.minimum
                or right_height.minimum > left_height.maximum
            ):
                continue
            try:
                shared = left_geometry.intersect_source_state(right_geometry)
            except ValueError:
                continue
            yield left_chain, right_chain, shared


def bind_shared_source_geometry_before_selection(
    materialization: SourcePlacementMaterialization,
) -> SourcePlacementMaterialization:
    """Return candidates whose source W/H was fixed before evidence voting."""

    if len(materialization.placements_by_lane) <= 1:
        return materialization
    if len(materialization.placements_by_lane) != 2:
        raise ValueError("shared source geometry supports one or two lanes")

    proposals = materialization.lane_proposals
    rebound: tuple[
        dict[str, CompleteFormatChain],
        dict[str, CompleteFormatChain],
    ] = ({}, {})
    cache: dict[tuple[int, str, str], CompleteFormatChain | None] = {}
    for left, right, shared in _compatible_shared_states(
        materialization.placements_by_lane[0],
        materialization.placements_by_lane[1],
    ):
        pair: list[CompleteFormatChain] = []
        for lane_index, chain in enumerate((left, right)):
            key = (lane_index, chain.placement_id, shared.geometry_id)
            if key not in cache:
                try:
                    cache[key] = materialize_complete_chain_at_source_geometry(
                        proposals[lane_index],
                        chain,
                        shared,
                    )
                except ValueError:
                    cache[key] = None
            candidate = cache[key]
            if candidate is None:
                break
            pair.append(candidate)
        if len(pair) != 2:
            continue
        if pair[0].source_scan_geometry != pair[1].source_scan_geometry:
            raise ValueError("dual-lane candidates lost shared source geometry")
        for lane_index, candidate in enumerate(pair):
            rebound[lane_index][candidate.placement_id] = candidate

    placements = tuple(
        tuple(values[key] for key in sorted(values)) for values in rebound
    )
    return replace(
        materialization,
        placements_by_lane=placements,
        proposed_complete_chain_counts_by_lane=tuple(
            max(previous, len(current))
            for previous, current in zip(
                materialization.proposed_complete_chain_counts_by_lane,
                placements,
                strict=True,
            )
        ),
    )
