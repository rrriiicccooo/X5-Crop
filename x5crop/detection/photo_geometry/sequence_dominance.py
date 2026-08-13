"""Direct separator-material dominance inside the sequence axis."""

from __future__ import annotations

from .chains import CompleteFormatChain
from .interval_math import intersect


def minimum_safe_separator_relation(
    left_placement_ids: tuple[str, ...],
    right_placement_ids: tuple[str, ...],
    placements_by_id: dict[str, CompleteFormatChain],
) -> int | None:
    """Prefer the smaller directly observed separator interpretation.

    Two bands describe the same separator alternative only when they occupy
    the same ordinal, share at least one physical edge, and their measured gap
    intervals overlap.  After content veto has passed, the narrower band
    discards less recoverable raster between the two fixed frames.  This is a
    sequence-axis safety relation, not a darkness score or a cross-axis vote.
    """

    if len(left_placement_ids) != len(right_placement_ids):
        return None
    left_not_wider = True
    right_not_wider = True
    left_strict = False
    right_strict = False
    for left_id, right_id in zip(
        left_placement_ids,
        right_placement_ids,
        strict=True,
    ):
        left_bands = {
            item.relation_ordinal: item.observation
            for item in placements_by_id[left_id].sequence.separator_bands
        }
        right_bands = {
            item.relation_ordinal: item.observation
            for item in placements_by_id[right_id].sequence.separator_bands
        }
        if set(left_bands) != set(right_bands):
            return None
        for ordinal in sorted(left_bands):
            left = left_bands[ordinal]
            right = right_bands[ordinal]
            if left.observation_id == right.observation_id:
                continue
            if (
                left.left_edge_observation_id
                not in {
                    right.left_edge_observation_id,
                    right.right_edge_observation_id,
                }
                and left.right_edge_observation_id
                not in {
                    right.left_edge_observation_id,
                    right.right_edge_observation_id,
                }
            ):
                return None
            if intersect(left.gap_interval_px, right.gap_interval_px) is None:
                return None
            if left.gap_interval_px.minimum > right.gap_interval_px.minimum:
                left_not_wider = False
            if left.gap_interval_px.maximum > right.gap_interval_px.maximum:
                left_not_wider = False
            if right.gap_interval_px.minimum > left.gap_interval_px.minimum:
                right_not_wider = False
            if right.gap_interval_px.maximum > left.gap_interval_px.maximum:
                right_not_wider = False
            left_strict = left_strict or (
                left.gap_interval_px.minimum < right.gap_interval_px.minimum
                or left.gap_interval_px.maximum < right.gap_interval_px.maximum
            )
            right_strict = right_strict or (
                right.gap_interval_px.minimum < left.gap_interval_px.minimum
                or right.gap_interval_px.maximum < left.gap_interval_px.maximum
            )
    if left_not_wider and left_strict:
        return 1
    if right_not_wider and right_strict:
        return -1
    if left_not_wider and right_not_wider:
        return 0
    return None


def separator_material_strictly_dominates(
    left_placement_ids: tuple[str, ...],
    right_placement_ids: tuple[str, ...],
    placements_by_id: dict[str, CompleteFormatChain],
) -> bool:
    """Compare role-bound separator material without a score margin."""

    if len(left_placement_ids) != len(right_placement_ids):
        return False
    strict = False
    for left_id, right_id in zip(
        left_placement_ids,
        right_placement_ids,
        strict=True,
    ):
        left_bands = tuple(
            sorted(
                placements_by_id[left_id].sequence.separator_bands,
                key=lambda item: item.relation_ordinal,
            )
        )
        right_bands = tuple(
            sorted(
                placements_by_id[right_id].sequence.separator_bands,
                key=lambda item: item.relation_ordinal,
            )
        )
        if (
            len(left_bands) != len(right_bands)
            or any(
                left_band.relation_ordinal != right_band.relation_ordinal
                for left_band, right_band in zip(
                    left_bands,
                    right_bands,
                    strict=True,
                )
            )
        ):
            return False
        for left_band, right_band in zip(
            left_bands,
            right_bands,
            strict=True,
        ):
            left_observation = left_band.observation
            right_observation = right_band.observation
            if (
                left_observation.observation_id
                == right_observation.observation_id
            ):
                continue
            if (
                left_observation.continuous_support_fraction
                < right_observation.continuous_support_fraction
            ):
                return False
            if (
                left_observation.continuous_support_fraction
                > right_observation.continuous_support_fraction
            ):
                strict = True
            if tuple(
                item.region_index for item in left_observation.material_regions
            ) != tuple(
                item.region_index for item in right_observation.material_regions
            ):
                return False
            for left_region, right_region in zip(
                left_observation.material_regions,
                right_observation.material_regions,
                strict=True,
            ):
                for left_interval, right_interval in (
                    (
                        left_region.darkness_contrast_interval,
                        right_region.darkness_contrast_interval,
                    ),
                    (
                        left_region.texture_contrast_interval,
                        right_region.texture_contrast_interval,
                    ),
                ):
                    if left_interval == right_interval:
                        continue
                    if left_interval.minimum < right_interval.maximum:
                        return False
                    strict = True
    return strict
