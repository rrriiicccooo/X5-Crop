"""Compact production report facts for one completed local crop."""

from __future__ import annotations

from typing import Any

from ..detection.photo_geometry.template_alignment_diagnostic import (
    template_alignment_diagnostic,
)
from .read_models import typed_read_model


def template_alignment_path(phase: object, alignment: object) -> str | None:
    if phase.retained_proposal_basis is not None:
        return "retained_phase_proposal"
    if phase.best is None or alignment.pattern.value == "unresolved":
        return None
    if any(relation.is_anomaly for relation in phase.best.adjacency_relations):
        return "adjacency_relations"
    return "normal"


def measurement_summary(detection: object, workspace: object) -> dict[str, Any]:
    field = workspace.boundary_measurement_field
    return {
        "owner": "PhotoBoundaryMeasurementField",
        "source_extent": typed_read_model(field.source_extent),
        "layout": field.layout,
        "scan_canvas_state": detection.source_core.scan_canvas_state.value,
        "incomplete_reasons": list(detection.source_core.incomplete_reasons),
    }


def photo_geometry_summary(detection: object) -> dict[str, Any]:
    core = detection.source_core
    geometry = detection.candidate.geometry
    holder = core.matched_holder
    selected_profile_id = None if holder is None else holder.profile.profile_id
    proposal = geometry.source_placement_proposal
    selection = geometry.source_placement_selection
    alignments = {
        lane.lane_id: template_alignment_diagnostic(
            lane.prepared.phase_competition,
            lane.prepared.sequence_edges,
            lane.prepared.separator_bands,
        )
        for lane in geometry.lane_reconstructions
    }
    return {
        "selected_scan_canvas_profile_id": selected_profile_id,
        "matched_holder": typed_read_model(holder),
        "resolved_slot_count": typed_read_model(core.resolved_slot_count),
        "resolved_output_slots": typed_read_model(detection.resolved_output_slots),
        "output_slot_count": detection.output_slot_count,
        "slot_identities": typed_read_model(detection.output_slot_identities),
        "source_placement_proposal": typed_read_model(proposal),
        "source_placement_selection": {
            "state": selection.state.value,
            "failure": typed_read_model(selection.failure),
            "selected_placement_ids": list(selection.selected_placement_ids),
            "runner_up_placement_ids": list(selection.runner_up_placement_ids),
        },
        "lanes": [
            {
                "lane_id": lane.lane_id,
                "template_id": lane.prepared.template_spec.template_id,
                "source_scan_geometry": typed_read_model(
                    lane.prepared.source_scan_geometry
                ),
                "source_frame_width_authority": typed_read_model(
                    lane.prepared.source_frame_width_authority
                ),
                "source_frame_width_topology_assessment": typed_read_model(
                    lane.prepared.phase_competition
                    .source_frame_width_topology_assessment
                ),
                "contact_edge_observations": typed_read_model(
                    lane.prepared.phase_input.contact_edge_observations
                ),
                "overlap_edge_pair_observations": typed_read_model(
                    lane.prepared.phase_input.overlap_edge_pair_observations
                ),
                "aperture_aspect_ratio_authority": typed_read_model(
                    lane.prepared.cross_competition
                    .aperture_aspect_ratio_authority
                ),
                "coarse_strip_support": {
                    "long_authority": (
                        lane.prepared.coarse_support.long_axis.authority.value
                    ),
                    "short_authority": (
                        lane.prepared.coarse_support.short_axis.authority.value
                    ),
                    "long_interval_px": typed_read_model(
                        lane.prepared.coarse_support.long_axis.interval_px
                    ),
                    "short_interval_px": typed_read_model(
                        lane.prepared.coarse_support.short_axis.interval_px
                    ),
                },
                "phase_status": lane.prepared.phase_competition.status.value,
                "phase_failure_kind": (
                    None
                    if lane.prepared.phase_competition.failure_kind is None
                    else lane.prepared.phase_competition.failure_kind.value
                ),
                "phase_failure_reason": (
                    lane.prepared.phase_competition.ambiguity_reason
                ),
                "phase_retained_proposal_basis": (
                    None
                    if lane.prepared.phase_competition.retained_proposal_basis
                    is None
                    else lane.prepared.phase_competition
                    .retained_proposal_basis.value
                ),
                "cross_status": lane.prepared.cross_competition.status.value,
                "cross_failure_kind": (
                    None
                    if lane.prepared.cross_competition.failure_kind is None
                    else lane.prepared.cross_competition.failure_kind.value
                ),
                "cross_failure_reason": lane.prepared.cross_competition.reason,
                "cross_retained_proposal_basis": (
                    None
                    if lane.prepared.cross_competition
                    .retained_proposal_basis is None
                    else lane.prepared.cross_competition
                    .retained_proposal_basis.value
                ),
                "cross_line_projection_basis": (
                    None
                    if lane.prepared.cross_competition.best is None
                    else lane.prepared.cross_competition.best
                    .line_projection_basis.value
                ),
                "cross_height_projection_basis": (
                    None
                    if lane.prepared.cross_competition.best is None
                    else lane.prepared.cross_competition.best
                    .height_projection_basis.value
                ),
                "cross_height_inference_basis": (
                    None
                    if lane.prepared.cross_competition.best is None
                    or lane.prepared.cross_competition.best
                    .height_inference_basis is None
                    else lane.prepared.cross_competition.best
                    .height_inference_basis.value
                ),
                "placement_state": lane.placement_competition.state.value,
                "placement_failure": typed_read_model(
                    lane.placement_competition.failure
                ),
                "placement_proposal": typed_read_model(
                    lane.placement_proposal
                ),
                "direct_role_aperture_domain_authority": typed_read_model(
                    lane.placement_competition
                    .direct_role_aperture_domain_authority
                ),
                "template_alignment": {
                    "path": template_alignment_path(
                        lane.prepared.phase_competition,
                        alignments[lane.lane_id],
                    ),
                    "pattern": alignments[lane.lane_id].pattern.value,
                    "absolute_phase_px": (
                        alignments[lane.lane_id].absolute_phase_px
                    ),
                    "canonical_pitch_px": (
                        alignments[lane.lane_id].canonical_pitch_px
                    ),
                    "pitch_delta_from_compiled_center_px": (
                        alignments[lane.lane_id]
                        .pitch_delta_from_compiled_center_px
                    ),
                    "maximum_absolute_role_residual_px": (
                        alignments[lane.lane_id]
                        .maximum_absolute_role_residual_px
                    ),
                    "adjacency_relations": typed_read_model(
                        alignments[lane.lane_id].adjacency_relations
                    ),
                    "global_lattice_authority": typed_read_model(
                        alignments[lane.lane_id].global_lattice_authority
                    ),
                    "calibrated_nominal_grid_evidence": typed_read_model(
                        alignments[lane.lane_id]
                        .calibrated_nominal_grid_evidence
                    ),
                    "adjacency_observation_coverage": typed_read_model(
                        alignments[lane.lane_id]
                        .adjacency_observation_coverage
                    ),
                    "adjacency_continuity_observations": typed_read_model(
                        alignments[lane.lane_id]
                        .adjacency_continuity_observations
                    ),
                    "direct_role_binding_authority": typed_read_model(
                        alignments[lane.lane_id]
                        .direct_role_binding_authority
                    ),
                    "outer_frame_observation_authority": typed_read_model(
                        alignments[lane.lane_id]
                        .outer_frame_observation_authority
                    ),
                    "frame_width_inference": typed_read_model(
                        alignments[lane.lane_id].frame_width_inference
                    ),
                    "unbound_direct_observation_count": len(
                        alignments[lane.lane_id]
                        .unbound_direct_observation_ids
                    ),
                    "unresolved_reason": (
                        alignments[lane.lane_id].unresolved_reason
                    ),
                },
                "selected_cross_boundary_use": (
                    None
                    if lane.selected_placement is None
                    or lane.prepared.cross_competition.best is None
                    else lane.prepared.cross_competition.best.boundary_use.value
                ),
                "selected_placement_id": (
                    None
                    if lane.selected_placement is None
                    else lane.selected_placement.placement_id
                ),
                "runner_up_placement_id": (
                    lane.placement_competition.runner_up_placement_id
                ),
                "photo_group_outer": typed_read_model(
                    None
                    if lane.holder_fill_assessment is None
                    else lane.holder_fill_assessment.outer
                ),
                "holder_fill_assessment": typed_read_model(
                    lane.holder_fill_assessment
                ),
                "output_footprints": typed_read_model(lane.output_footprints),
                "calibrated_nominal_grid_authority": typed_read_model(
                    lane.calibrated_nominal_grid_authority
                ),
                "enclosing_support_aperture_authority": typed_read_model(
                    lane.enclosing_support_aperture_authority
                ),
                "direct_use_budget_assessments": typed_read_model(
                    lane.direct_use_budget_assessments
                ),
                "peak_temporary_bytes": max(
                    lane.prepared.measurement_work.peak_temporary_bytes,
                    lane.work.peak_temporary_bytes,
                ),
            }
            for lane in geometry.lane_reconstructions
        ],
    }
