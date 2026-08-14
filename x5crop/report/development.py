"""Development-only template evidence, competition, and work facts."""

from __future__ import annotations

from typing import Any

from ..detection.workspace import DetectionWorkspace
from .read_models import typed_read_model
from ..detection.photo_geometry.template_phase_model import PhaseFitStatus
from ..detection.photo_geometry.template_stability import (
    leave_one_anchor_out_phase_stability,
)


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
    geometry = detection.candidate.geometry
    stability_by_lane = {}
    for lane in geometry.lane_reconstructions:
        phase = lane.prepared.phase_competition
        stability_by_lane[lane.lane_id] = (
            None
            if phase.status != PhaseFitStatus.RESOLVED or phase.best is None
            else leave_one_anchor_out_phase_stability(
                phase,
                lane.prepared.sequence_edges,
                lane.prepared.separator_bands,
                lane.prepared.template_spec,
                holder_span_px=lane.prepared.width_authority_px,
            )
        )
    return {
        "measurement": {
            "field": {
                "provenance": typed_read_model(
                    workspace.boundary_measurement_field.provenance
                ),
                "candidate_independent_registered_queries": True,
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
                for measurement_set in lane.prepared.measurement_sets
            ],
        },
        "source_placement_selection": typed_read_model(
            geometry.source_placement_selection
        ),
        "root_gate": {
            "candidate": typed_read_model(detection.candidate.gate),
            "decision": typed_read_model(detection.decision),
        },
        "lanes": [
            {
                "lane_id": lane.lane_id,
                "template_spec": typed_read_model(lane.prepared.template_spec),
                "search": {
                    "anchor_domain": typed_read_model(lane.prepared.anchor_domain),
                    "sequence_profile": typed_read_model(
                        lane.prepared.sequence_profile
                    ),
                    "cross_profile": typed_read_model(lane.prepared.cross_profile),
                },
                "observations": {
                    "sequence_edges": typed_read_model(
                        lane.prepared.sequence_edges
                    ),
                    "separator_bands": typed_read_model(
                        lane.prepared.separator_bands
                    ),
                    "side_transition_regions": typed_read_model(
                        lane.prepared.side_regions
                    ),
                    "raw_top_bottom_lines": typed_read_model(
                        lane.prepared.raw_cross_observations
                    ),
                    "registered_top_bottom_bindings": typed_read_model(
                        (
                            *lane.prepared.top_cross_bindings,
                            *lane.prepared.bottom_cross_bindings,
                        )
                    ),
                },
                "evidence_use_ledger": typed_read_model(
                    lane.prepared.evidence_use_ledger
                ),
                "phase_competition": typed_read_model(
                    lane.prepared.phase_competition
                ),
                "phase_stability": typed_read_model(
                    stability_by_lane[lane.lane_id]
                ),
                "cross_competition": typed_read_model(
                    lane.prepared.cross_competition
                ),
                "placement_competition": typed_read_model(
                    lane.placement_competition
                ),
                "winner_basis": {
                    "state": lane.placement_competition.state.value,
                    "phase": (
                        None
                        if lane.prepared.phase_competition.winner_basis is None
                        else lane.prepared.phase_competition.winner_basis.value
                    ),
                    "failure": typed_read_model(
                        lane.placement_competition.failure
                    ),
                    "selected_placement_id": (
                        lane.placement_competition.selected_placement_id
                    ),
                    "runner_up_placement_id": (
                        lane.placement_competition.runner_up_placement_id
                    ),
                },
                "content_veto_facts": typed_read_model(lane.content_veto_facts),
                "precision_ledger": typed_read_model(lane.precision_ledger),
                "measurement_work": typed_read_model(
                    lane.prepared.measurement_work
                ),
                "work": {
                    "measurement_query_count": (
                        lane.prepared.measurement_work.measurement_query_count
                    ),
                    "pixel_query_count": (
                        lane.prepared.measurement_work.pixel_query_count
                    ),
                    "basic_profile_coordinate_count": (
                        lane.prepared.sequence_profile.coordinate_count
                        + lane.prepared.cross_profile.coordinate_count
                    ),
                    "basic_profile_run_count": (
                        len(lane.prepared.sequence_profile.runs)
                        + len(lane.prepared.cross_profile.runs)
                    ),
                    "registered_sequence_observation_count": (
                        len(lane.prepared.sequence_edges)
                    ),
                    "phase_hypothesis_count": (
                        lane.prepared.phase_competition.receipt
                        .phase_hypothesis_count
                    ),
                    "phase_fit_pass_count": (
                        lane.prepared.phase_competition.receipt.fit_pass_count
                    ),
                    "phase_role_lookup_count": (
                        lane.prepared.phase_competition.receipt.phase_lookup_count
                    ),
                    "phase_role_binding_count": (
                        lane.prepared.phase_competition.receipt.role_binding_count
                    ),
                    "local_relation_evaluation_count": (
                        lane.prepared.phase_competition.receipt
                        .local_relation_evaluation_count
                    ),
                    "cross_registered_run_count": (
                        lane.prepared.cross_competition.receipt
                        .registered_run_count
                    ),
                    "cross_fit_evaluation_count": (
                        lane.prepared.cross_competition.receipt.evaluated_fit_count
                    ),
                    "placement_evaluation_count": (
                        lane.work.placement_evaluation_count
                    ),
                    "boundary_evaluation_count": (
                        lane.work.boundary_evaluation_count
                    ),
                    "content_evaluation_count": (
                        lane.work.content_evaluation_count
                    ),
                    "domain_pixels": (
                        lane.prepared.lane.domain.work_box.width
                        * lane.prepared.lane.domain.work_box.height
                    ),
                    "peak_temporary_bytes": max(
                        lane.prepared.measurement_work.peak_temporary_bytes,
                        lane.work.peak_temporary_bytes,
                    ),
                },
            }
            for lane in geometry.lane_reconstructions
        ],
    }
