"""Normalized report records for complete physical chains."""

from __future__ import annotations

from typing import Any

from ..detection.photo_geometry.chain_record_model import CompleteChainRecord
from ..detection.photo_geometry.chain_observation_accounting import (
    ObservationDisposition,
)
from .read_models import typed_read_model


def complete_chain_read_model(record: CompleteChainRecord) -> dict[str, Any]:
    """Serialize one chain without copying the runtime placement object graph."""

    by_disposition = {
        disposition: tuple(
            fact
            for fact in record.observation_facts
            if fact.disposition == disposition
        )
        for disposition in ObservationDisposition
    }
    return {
        "chain_id": record.chain_id,
        "placement_id": record.placement_id,
        "lane_id": record.lane_id,
        "sampling_boxes": typed_read_model(record.sampling_boxes),
        "sampling_authority_boxes": typed_read_model(
            record.sampling_authority_boxes
        ),
        "authority_profile_ids": list(record.authority_profile_ids),
        "boundary_intervals_px": typed_read_model(record.boundary_intervals_px),
        "direction_id": record.direction_id,
        "source_scan_geometry_id": record.source_scan_geometry_id,
        "evidence": {
            "direct_observation_count": record.direct_observation_count,
            "separator_band_count": record.separator_band_count,
            "structural_pair_count": record.structural_pair_count,
            "cross_axis_pair_supported": record.cross_axis_pair_supported,
            "cross_axis_support_region_count": (
                record.cross_axis_support_region_count
            ),
            "cross_axis_observation_ids": list(
                map(str, record.cross_axis_observation_ids)
            ),
            "direct_observation_ids": list(map(str, record.direct_observation_ids)),
            "structural_observation_ids": list(
                map(str, record.structural_observation_ids)
            ),
            "normal_gap_supported": record.normal_gap_supported,
            "separator_support_region_count": (
                record.separator_support_region_count
            ),
            "lane_direction_disagreement_degrees": (
                record.lane_direction_disagreement_degrees
            ),
            "direction_observation_ids": list(
                map(str, record.direction_observation_ids)
            ),
            "separator_material_quality": record.separator_material_quality,
            "local_advance_authorized": record.local_advance_authorized,
        },
        "ledger": [
            {
                "entry_id": item.entry_id,
                "ordinal": item.ordinal,
                "evidence_tier": item.evidence_tier.value,
                "observation_ids": list(map(str, item.observation_ids)),
                "physical_interval_px": typed_read_model(
                    item.physical_interval_px
                ),
            }
            for item in record.ledger
        ],
        "observation_dispositions": {
            disposition.value: [
                {
                    "observation_id": str(fact.observation_id),
                    "roles": list(fact.roles),
                }
                for fact in by_disposition[disposition]
            ]
            for disposition in ObservationDisposition
        },
    }


def selected_chain_summary(record: CompleteChainRecord) -> dict[str, Any]:
    """Serialize only the selected chain facts needed by a normal run."""

    return {
        "chain_id": record.chain_id,
        "placement_id": record.placement_id,
        "lane_id": record.lane_id,
        "sampling_boxes": typed_read_model(record.sampling_boxes),
        "sampling_authority_boxes": typed_read_model(
            record.sampling_authority_boxes
        ),
        "authority_profile_ids": list(record.authority_profile_ids),
        "boundary_intervals_px": typed_read_model(record.boundary_intervals_px),
        "direction_id": record.direction_id,
        "source_scan_geometry_id": record.source_scan_geometry_id,
        "authority": {
            "direct_observation_count": record.direct_observation_count,
            "separator_band_count": record.separator_band_count,
            "structural_pair_count": record.structural_pair_count,
            "cross_axis_pair_supported": record.cross_axis_pair_supported,
            "cross_axis_support_region_count": (
                record.cross_axis_support_region_count
            ),
            "normal_gap_supported": record.normal_gap_supported,
            "separator_support_region_count": (
                record.separator_support_region_count
            ),
            "lane_direction_disagreement_degrees": (
                record.lane_direction_disagreement_degrees
            ),
            "local_advance_authorized": record.local_advance_authorized,
        },
    }


def complete_chains_read_model(
    records: tuple[CompleteChainRecord, ...],
) -> list[dict[str, Any]]:
    return [complete_chain_read_model(record) for record in records]
