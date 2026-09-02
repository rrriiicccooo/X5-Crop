"""Development-only template evidence, competition, and work facts."""

from __future__ import annotations

from typing import Any

from ..detection.workspace import DetectionWorkspace
from .read_models import typed_read_model
from ..detection.photo_geometry.template_alignment_diagnostic import (
    template_alignment_diagnostic,
)
from ..detection.photo_geometry.template_phase_model import PhaseFitStatus
from ..detection.photo_geometry.template_stability import (
    leave_one_anchor_out_phase_stability,
)
from .summary import template_alignment_path


def _measurement_set_read_model(measurement_set: object) -> dict[str, object]:
    return {
        "query": typed_read_model(measurement_set.query),
        "state": measurement_set.state.value,
        "coverage": typed_read_model(measurement_set.coverage),
        "transition_count": len(measurement_set.transitions),
        "transitions": typed_read_model(measurement_set.transitions),
        "cross_height_transition_count": len(
            measurement_set.cross_height_transitions
        ),
        "cross_height_transitions": typed_read_model(
            measurement_set.cross_height_transitions
        ),
        "broad_material_transition_count": len(
            measurement_set.broad_material_transitions
        ),
        "broad_material_transitions": typed_read_model(
            measurement_set.broad_material_transitions
        ),
    }


def development_report_facts(
    detection: object,
    workspace: DetectionWorkspace,
) -> dict[str, Any]:
    geometry = detection.candidate.geometry
    stability_by_lane = {}
    alignment_by_lane = {}
    for lane in geometry.lane_reconstructions:
        phase = lane.prepared.phase_competition
        alignment_by_lane[lane.lane_id] = template_alignment_diagnostic(
            phase,
            lane.prepared.sequence_edges,
            lane.prepared.separator_bands,
        )
        stability_by_lane[lane.lane_id] = (
            None
            if phase.status != PhaseFitStatus.RESOLVED or phase.best is None
            else leave_one_anchor_out_phase_stability(
                phase,
                lane.prepared.phase_input,
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
        "source_placement_proposal": typed_read_model(
            geometry.source_placement_proposal
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
                    "coarse_strip_support": typed_read_model(
                        lane.prepared.coarse_support
                    ),
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
                    "contact_edge_observations": typed_read_model(
                        lane.prepared.phase_input.contact_edge_observations
                    ),
                    "overlap_edge_pair_observations": typed_read_model(
                        lane.prepared.phase_input.overlap_edge_pair_observations
                    ),
                    "side_transition_regions": typed_read_model(
                        lane.prepared.side_regions
                    ),
                    "cross_height_transition_regions": typed_read_model(
                        lane.prepared.cross_height_regions
                    ),
                    "cross_height_edges": typed_read_model(
                        lane.prepared.cross_height_edges
                    ),
                    "cross_height_edge_resolutions": typed_read_model(
                        lane.prepared.cross_height_edge_resolutions
                    ),
                    "broad_material_transition_regions": typed_read_model(
                        lane.prepared.broad_material_regions
                    ),
                    "broad_material_edges": typed_read_model(
                        lane.prepared.broad_material_edges
                    ),
                    "broad_material_edge_resolutions": typed_read_model(
                        lane.prepared.broad_material_edge_resolutions
                    ),
                    "raw_top_bottom_lines": typed_read_model(
                        lane.prepared.raw_cross_observations
                    ),
                    "cross_boundary_family_resolutions": typed_read_model(
                        lane.prepared.cross_boundary_family_resolutions
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
                "template_alignment": typed_read_model(
                    alignment_by_lane[lane.lane_id]
                ),
                "phase_competition": typed_read_model(
                    lane.prepared.phase_competition
                ),
                "source_frame_width_authority": typed_read_model(
                    lane.prepared.source_frame_width_authority
                ),
                "source_frame_width_topology_assessment": typed_read_model(
                    lane.prepared.phase_competition
                    .source_frame_width_topology_assessment
                ),
                "alignment_path": (
                    template_alignment_path(
                        lane.prepared.phase_competition,
                        alignment_by_lane[lane.lane_id],
                    )
                ),
                "phase_stability": typed_read_model(
                    stability_by_lane[lane.lane_id]
                ),
                "cross_competition": typed_read_model(
                    lane.prepared.cross_competition
                ),
                "aperture_aspect_ratio_authority": typed_read_model(
                    lane.prepared.cross_competition
                    .aperture_aspect_ratio_authority
                ),
                "placement_competition": typed_read_model(
                    lane.placement_competition
                ),
                "placement_proposal": typed_read_model(
                    lane.placement_proposal
                ),
                "winner_basis": {
                    "state": lane.placement_competition.state.value,
                    "phase": (
                        None
                        if lane.prepared.phase_competition.winner_basis is None
                        else lane.prepared.phase_competition.winner_basis.value
                    ),
                    "cross": (
                        None
                        if lane.prepared.cross_competition.winner_basis is None
                        else lane.prepared.cross_competition.winner_basis.value
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
                "enclosing_support_aperture_authority": typed_read_model(
                    lane.enclosing_support_aperture_authority
                ),
                "holder_fill_assessment": typed_read_model(
                    lane.holder_fill_assessment
                ),
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
                    "registered_cross_height_transition_count": sum(
                        len(item.cross_height_transitions)
                        for item in lane.prepared.measurement_sets
                    ),
                    "registered_cross_height_edge_count": len(
                        lane.prepared.cross_height_edges
                    ),
                    "registered_broad_material_transition_count": sum(
                        len(item.broad_material_transitions)
                        for item in lane.prepared.measurement_sets
                    ),
                    "registered_broad_material_edge_count": len(
                        lane.prepared.broad_material_edges
                    ),
                    "cross_height_resolution_failure_count": sum(
                        item.state.value == "contradicted"
                        for item in lane.prepared.cross_height_edge_resolutions
                    ),
                    "broad_material_resolution_failure_count": sum(
                        item.state.value == "contradicted"
                        for item in lane.prepared.broad_material_edge_resolutions
                    ),
                    "phase_hypothesis_count": (
                        lane.prepared.phase_competition.receipt
                        .phase_hypothesis_count
                    ),
                    "candidate_direct_role_authority_evaluation_count": (
                        lane.prepared.phase_competition.receipt
                        .candidate_direct_role_authority_evaluation_count
                    ),
                    "candidate_direct_role_authority_terminal_count": (
                        lane.prepared.phase_competition.receipt
                        .candidate_direct_role_authority_terminal_count
                    ),
                    "candidate_direct_role_authority_role_check_count": (
                        lane.prepared.phase_competition.receipt
                        .candidate_direct_role_authority_role_check_count
                    ),
                    "candidate_direct_role_projection_evaluation_count": (
                        lane.prepared.phase_competition.receipt
                        .candidate_direct_role_projection_evaluation_count
                    ),
                    "candidate_direct_role_projection_success_count": (
                        lane.prepared.phase_competition.receipt
                        .candidate_direct_role_projection_success_count
                    ),
                    "candidate_direct_role_projection_binding_count": (
                        lane.prepared.phase_competition.receipt
                        .candidate_direct_role_projection_binding_count
                    ),
                    "separator_lattice_hypothesis_count": (
                        lane.prepared.phase_competition.receipt
                        .separator_lattice_hypothesis_count
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
                    "adjacency_relation_evaluation_count": (
                        lane.prepared.phase_competition.receipt
                        .adjacency_relation_evaluation_count
                    ),
                    "local_refinement_lookup_count": (
                        lane.prepared.phase_competition.receipt
                        .local_refinement_lookup_count
                    ),
                    "local_refinement_binding_count": (
                        lane.prepared.phase_competition.receipt
                        .local_refinement_binding_count
                    ),
                    "cross_registered_run_count": (
                        lane.prepared.cross_competition.receipt
                        .total_registered_run_count
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
