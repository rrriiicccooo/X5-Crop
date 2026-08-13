"""Select one source placement from finite, already-legal combinations."""

from __future__ import annotations

from dataclasses import replace

from ...domain import EvidenceState
from .chains import CompleteFormatChain
from .placement_clusters import LanePlacementSelection
from .source_combinations import (
    compatible_source_geometry_clusters,
    eligible_clusters,
    source_combination,
)
from .source_dominance import (
    minimum_safe_source_variant_strictly_dominates,
    source_strictly_dominates,
)
from .source_selection_model import (
    SourcePlacementCombination,
    SourcePlacementSelection,
)


def select_source_placement_clusters(
    lane_selections: tuple[LanePlacementSelection, ...],
    placements_by_lane: tuple[dict[str, CompleteFormatChain], ...],
) -> tuple[tuple[LanePlacementSelection, ...], SourcePlacementSelection]:
    if (
        not lane_selections
        or len(lane_selections) != len(placements_by_lane)
        or len(lane_selections) > 2
    ):
        raise ValueError("source selection requires one or two aligned lanes")
    eligible_by_lane = tuple(
        eligible_clusters(selection) for selection in lane_selections
    )
    combinations: list[SourcePlacementCombination] = []
    if len(lane_selections) == 1:
        for cluster in eligible_by_lane[0]:
            combination = source_combination((cluster,), placements_by_lane)
            if combination is not None:
                combinations.append(combination)
    else:
        for left in eligible_by_lane[0]:
            left_placement = placements_by_lane[0][
                left.representative_placement_id
            ]
            for right, shared in compatible_source_geometry_clusters(
                eligible_by_lane[1],
                placements_by_lane[1],
                left_placement,
            ):
                combination = source_combination(
                    (left, right),
                    placements_by_lane,
                    shared_scan_geometry=shared,
                )
                if combination is not None:
                    combinations.append(combination)
    ordered = tuple(
        sorted(
            {item.combination_id: item for item in combinations}.values(),
            key=lambda item: item.combination_id,
        )
    )
    if len(ordered) == 1:
        selected = ordered[0]
    else:
        placements_by_id = {
            placement_id: placement
            for lane_placements in placements_by_lane
            for placement_id, placement in lane_placements.items()
        }
        # Evidence authority comes before minimum-safe placement.  A line
        # that sits farther inside the photograph is not "safe" merely
        # because it produces a smaller rectangle: it must first be at least
        # as authoritative as the competing observation on its own physical
        # axis.  This ordering is especially important for top/bottom, where
        # a weak internal line can otherwise eliminate a better measured
        # outer boundary before cross-axis evidence is compared.
        authority_candidates = tuple(
            item
            for item in ordered
            if not any(
                item is not other
                and source_strictly_dominates(
                    other,
                    item,
                    placements_by_id,
                )
                for other in ordered
            )
        )
        # The strict physical-evidence relation is finite and acyclic by
        # construction.  Keep the empty case unresolved rather
        # than manufacturing a placement.
        evidence_frontier = authority_candidates or ordered
        if len(evidence_frontier) == 1:
            selected = evidence_frontier[0]
        else:
            # Only equally authoritative surviving variants may now be
            # normalized to their minimum safe existing placement.  This
            # relation never averages, unions, or splices boundaries.
            minimum_safe_frontier = tuple(
                item
                for item in evidence_frontier
                if not any(
                    item is not other
                    and minimum_safe_source_variant_strictly_dominates(
                        other,
                        item,
                        placements_by_id,
                    )
                    for other in evidence_frontier
                )
            )
            frontier = minimum_safe_frontier or evidence_frontier
            selected = frontier[0] if len(frontier) == 1 else None
    if selected is None:
        resolved_lanes = lane_selections
    else:
        resolved_lanes = tuple(
            replace(
                selection,
                selected_cluster_id=cluster_id,
                selected_placement_id=placement_id,
                state=EvidenceState.SUPPORTED,
            )
            for selection, cluster_id, placement_id in zip(
                lane_selections,
                selected.lane_cluster_ids,
                selected.lane_placement_ids,
                strict=True,
            )
        )
    return (
        resolved_lanes,
        SourcePlacementSelection(
            combinations=ordered,
            selected_combination_id=(
                None if selected is None else selected.combination_id
            ),
            shared_scan_geometry=(
                None if selected is None else selected.shared_scan_geometry
            ),
            state=(
                EvidenceState.UNAVAILABLE
                if selected is None
                else EvidenceState.SUPPORTED
            ),
        ),
    )
