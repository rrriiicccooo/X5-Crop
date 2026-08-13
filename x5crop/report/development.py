"""Development-only detection facts for Debug Analysis and verification."""

from __future__ import annotations

from typing import Any

from ..detection.workspace import DetectionWorkspace
from .chain_records import complete_chains_read_model
from .read_models import typed_read_model


def _measurement_set_read_model(measurement_set: object) -> dict[str, object]:
    return {
        "query": typed_read_model(measurement_set.query),
        "state": measurement_set.state.value,
        "coverage": typed_read_model(measurement_set.coverage),
        "transition_count": len(measurement_set.transitions),
        "transitions": typed_read_model(measurement_set.transitions),
    }


def development_report_facts(
    detection: object,
    workspace: DetectionWorkspace,
) -> dict[str, Any]:
    """Build the complete audit view only when a developer explicitly asks."""

    geometry = detection.candidate.geometry
    return {
        "measurement": {
            "field": {
                "provenance": typed_read_model(
                    workspace.boundary_measurement_field.provenance
                ),
                "streaming_transition_records_only": True,
            },
            "source_lanes": [
                {
                    "domain": typed_read_model(lane.domain),
                    "scan_canvas": typed_read_model(lane.scan_canvas),
                    "axis_scale_intervals": typed_read_model(
                        lane.scan_canvas.axis_scales
                    ),
                }
                for lane in detection.source_core.lanes
            ],
            "content_occupancy": typed_read_model(
                detection.source_core.content_occupancy
            ),
            "queries": [
                _measurement_set_read_model(measurement_set)
                for lane in geometry.lane_reconstructions
                for measurement_set in lane.measurement_sets
            ],
        },
        "source_placement_selection": typed_read_model(
            geometry.source_placement_selection
        ),
        "lanes": [
            {
                "lane_id": lane.lane_id,
                "search": {
                    "anchor_domain": typed_read_model(lane.anchor_domain),
                    "sequence_profile": typed_read_model(lane.sequence_profile),
                    "provisional_cross_profile": typed_read_model(
                        lane.cross_profile
                    ),
                },
                "observations": {
                    "sequence_edges": typed_read_model(lane.sequence_edges),
                    "separator_bands": typed_read_model(lane.separator_bands),
                    "lane_gap_model": typed_read_model(lane.lane_gap_model),
                    "side_transition_regions": typed_read_model(
                        lane.side_transition_regions
                    ),
                    "raw_top_bottom_lines": typed_read_model(
                        lane.raw_top_bottom_observations
                    ),
                    "cross_axis_proposals": typed_read_model(
                        lane.cross_axis_proposals
                    ),
                },
                "direction_classes": typed_read_model(lane.direction_classes),
                "complete_chains": complete_chains_read_model(
                    lane.placement_selection.chains
                ),
                "producer_bounds": typed_read_model(lane.producer_bounds),
                "clusters": typed_read_model(lane.placement_selection.clusters),
                "content_veto_assessments": typed_read_model(
                    lane.placement_selection.content_veto_assessments
                ),
                "work": typed_read_model(lane.work),
            }
            for lane in geometry.lane_reconstructions
        ],
    }
