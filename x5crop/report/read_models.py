from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any

from ..detection.candidate.model import AssessedCandidate
from ..detection.decision.model import FinalDetection


def typed_read_model(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: typed_read_model(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, dict):
        return {str(key): typed_read_model(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [typed_read_model(item) for item in value]
    return value


def gate_check_read_model(check: Any) -> dict[str, Any]:
    return {
        "code": check.code,
        "stage": check.stage,
        "state": check.state.value,
        "consequence": check.consequence,
        "final_review_reason": check.final_review_reason,
        "blocks": bool(check.blocks),
    }


def exposure_overlap_read_model(evidence: Any) -> dict[str, Any]:
    return {
        "state": evidence.state.value,
        "reason": evidence.reason,
        "detected": evidence.detected,
        "widest_overlap_band_px": evidence.widest_overlap_band_px,
        "class_counts": dict(evidence.class_counts),
        "gaps": [
            {
                "index": gap.index,
                "method": gap.method,
                "role": gap.role,
                "center": gap.center,
                "expected_center": gap.expected_center,
                "score": gap.score,
                "width_px": gap.width_px,
                "hard_trust": gap.hard_trust,
                "exposure_overlap_class": gap.exposure_overlap_class,
                "exposure_overlap_like": gap.exposure_overlap_like,
                "signal_window": typed_read_model(gap.signal_window),
                "pixel_signals": typed_read_model(gap.pixel_signals),
            }
            for gap in evidence.gaps
        ],
    }


def output_protection_read_model(plan: Any) -> dict[str, Any]:
    return {
        "base_bleed": {
            "long_axis": plan.base_bleed.long_axis,
            "short_axis": plan.base_bleed.short_axis,
        },
        "output_bleed": {
            "long_axis": plan.output_bleed.long_axis,
            "short_axis": plan.output_bleed.short_axis,
        },
        "exposure_overlap_detected": plan.exposure_overlap_detected,
        "required_long_axis_bleed_px": plan.required_long_axis_bleed_px,
        "available_long_axis_bleed_px": plan.available_long_axis_bleed_px,
        "feasible": plan.feasible,
        "reason": plan.reason,
    }


def scan_calibration_read_model(calibration: Any) -> dict[str, Any]:
    return {
        "x_px_per_mm": calibration.x_px_per_mm,
        "y_px_per_mm": calibration.y_px_per_mm,
        "source": calibration.source,
        "trusted": calibration.trusted,
        "warnings": list(calibration.warnings),
    }


def pixel_interval_read_model(interval: Any) -> dict[str, float]:
    return {
        "minimum": float(interval.minimum),
        "maximum": float(interval.maximum),
    }


def boundary_observation_read_model(observation: Any) -> dict[str, Any] | None:
    if observation is None:
        return None
    return {
        "side": observation.side,
        "position": pixel_interval_read_model(observation.position),
        "kind": observation.kind,
        "provenance": typed_read_model(observation.provenance),
    }


def holder_occlusion_read_model(evidence: Any) -> dict[str, Any]:
    def side_read_model(side: Any) -> dict[str, Any]:
        return {
            "side": side.side,
            "state": side.state.value,
            "hidden_width_px": pixel_interval_read_model(side.hidden_width_px),
            "reason": side.reason,
            "boundary": boundary_observation_read_model(side.boundary),
        }

    return {
        "leading": side_read_model(evidence.leading),
        "trailing": side_read_model(evidence.trailing),
    }


def frame_sequence_read_model(evidence: Any) -> dict[str, Any]:
    conservation = evidence.conservation
    return {
        "holder_occlusion": holder_occlusion_read_model(evidence.holder_occlusion),
        "spacings": [
            {
                "index": spacing.index,
                "state": spacing.state.value,
                "kind": spacing.kind,
                "signed_width_px": pixel_interval_read_model(
                    spacing.signed_width_px
                ),
                "reason": spacing.reason,
            }
            for spacing in evidence.spacings
        ],
        "conservation": {
            "state": conservation.state.value,
            "reason": conservation.reason,
            "visible_length_px": pixel_interval_read_model(
                conservation.visible_length_px
            ),
            "holder_occlusion_px": pixel_interval_read_model(
                conservation.holder_occlusion_px
            ),
            "frame_total_px": pixel_interval_read_model(
                conservation.frame_total_px
            ),
            "spacing_total_px": pixel_interval_read_model(
                conservation.spacing_total_px
            ),
            "physical_sequence_px": pixel_interval_read_model(
                conservation.physical_sequence_px
            ),
        },
    }


def candidate_gate_read_model(candidate: AssessedCandidate) -> dict[str, Any]:
    gate = candidate.assessment.gate
    return {
        "passed": bool(gate.passed),
        "checks": [gate_check_read_model(check) for check in gate.checks],
        "proof_paths": [
            {
                "code": path.code,
                "state": path.state.value,
                "supporting_evidence": list(path.supporting_evidence),
            }
            for path in gate.proof_paths
        ],
        "failed_checks": list(gate.failed_checks),
        "diagnostics": list(gate.diagnostics),
    }


def candidate_evidence_read_model(candidate: AssessedCandidate) -> dict[str, Any]:
    evidence = candidate.assessment.evidence
    topology = evidence.frame_topology
    coverage = evidence.frame_coverage
    frame_sequence = evidence.frame_sequence
    sequence = evidence.separator_sequence
    continuity = evidence.separator_continuity
    dimensions = evidence.frame_dimensions
    content = evidence.frame_content
    holder_texture = evidence.holder_texture
    preservation = evidence.content_preservation
    alignment = evidence.outer_alignment
    occupancy = evidence.holder_occupancy
    completeness = occupancy.strip_completeness
    partial = evidence.partial_edge_safety
    independence = evidence.independence
    return {
        "frame_topology": {
            "state": topology.state.value,
            "expected_count": topology.expected_count,
            "actual_count": topology.actual_count,
            "count_matches": topology.count_matches,
            "extent_valid": topology.extent_valid,
            "order_valid": topology.order_valid,
            "overlap_absent": topology.overlap_absent,
            "invalid_extent_indexes": list(topology.invalid_extent_indexes),
            "order_invalid_indexes": list(topology.order_invalid_indexes),
            "overlap_pairs": typed_read_model(topology.overlap_pairs),
            "boxes": typed_read_model(topology.boxes),
        },
        "frame_coverage": {
            "state": coverage.state.value,
            "reason": coverage.reason,
            "holder_interval": list(coverage.holder_interval),
            "film_interval": typed_read_model(coverage.film_interval),
            "frame_intervals": typed_read_model(coverage.frame_intervals),
            "content_runs": typed_read_model(coverage.content_runs),
            "uncovered_content": typed_read_model(coverage.uncovered_content),
            "unexplained_content_region_count": (
                coverage.unexplained_content_region_count
            ),
        },
        "frame_sequence": frame_sequence_read_model(frame_sequence),
        "separator_sequence": {
            "state": sequence.state.value,
            "reason": sequence.reason,
            "expected_count": sequence.expected_count,
            "hard_count": sequence.hard_count,
            "model_count": sequence.model_count,
            "hard_indexes": list(sequence.hard_indexes),
            "missing_indexes": list(sequence.missing_indexes),
            "hard_scores": list(sequence.hard_scores),
        },
        "separator_continuity": {
            "state": continuity.state.value,
            "reason": continuity.reason,
            "minimum_coverage_ratio": continuity.minimum_coverage_ratio,
            "minimum_continuity_ratio": continuity.minimum_continuity_ratio,
            "records": [
                {
                    "index": record.index,
                    "method": record.method,
                    "measured": record.measured,
                    "state": record.state.value,
                    "coverage_ratio": record.coverage_ratio,
                    "continuity_ratio": record.continuity_ratio,
                    "break_count": record.break_count,
                    "straightness": record.straightness,
                    "reason": record.reason,
                }
                for record in continuity.records
            ],
            "observations": typed_read_model(continuity.observations),
        },
        "frame_dimensions": {
            "state": dimensions.state.value,
            "reason": dimensions.reason,
            "nominal_width_mm": dimensions.nominal_width_mm,
            "nominal_height_mm": dimensions.nominal_height_mm,
            "nominal_aspect": dimensions.nominal_aspect,
            "photo_widths_px": list(dimensions.photo_widths_px),
            "photo_width_cv": dimensions.photo_width_cv,
            "separator_widths_px": list(dimensions.separator_widths_px),
            "separator_width_cv": dimensions.separator_width_cv,
            "observed_width_mm": dimensions.observed_width_mm,
            "observed_height_mm": dimensions.observed_height_mm,
            "observed_aspect": dimensions.observed_aspect,
            "aspect_error_ratio": dimensions.aspect_error_ratio,
            "maximum_dimension_error_ratio": (
                dimensions.maximum_dimension_error_ratio
            ),
            "calibration_used": dimensions.calibration_used,
        },
        "frame_content": {
            "state": content.state.value,
            "reason": content.reason,
            "threshold": content.threshold,
            "median_mean": content.median_mean,
            "median_coverage": content.median_coverage,
            "composite": content.composite,
            "observations": [
                {
                    "index": item.index,
                    "mean": item.mean,
                    "coverage": item.coverage,
                    "content_present": item.content_present,
                    "boundary_contact_sides": list(
                        item.boundary_contact_sides
                    ),
                }
                for item in content.observations
            ],
        },
        "holder_texture": {
            "state": holder_texture.state.value,
            "reason": holder_texture.reason,
            "content_holder_mean_contrast": (
                holder_texture.content_holder_mean_contrast
            ),
            "content_holder_coverage_contrast": (
                holder_texture.content_holder_coverage_contrast
            ),
            "regions": [
                {
                    "name": region.name,
                    "box": typed_read_model(region.box),
                    "mean": region.mean,
                    "coverage": region.coverage,
                    "texture": region.texture,
                }
                for region in holder_texture.regions
            ],
        },
        "content_preservation": {
            "state": preservation.state.value,
            "reason": preservation.reason,
            "uncovered_content": typed_read_model(
                preservation.uncovered_content
            ),
            "boundary_contact_frame_indexes": list(
                preservation.boundary_contact_frame_indexes
            ),
            "confirmed_outer_undercrop_sides": list(
                preservation.confirmed_outer_undercrop_sides
            ),
            "partial_edge_state": preservation.partial_edge_state.value,
        },
        "outer_alignment": {
            "state": alignment.state.value,
            "reason": alignment.reason,
            "film_span": typed_read_model(alignment.film_span),
            "content_span": typed_read_model(alignment.content_span),
            "content_measurement_sources": list(
                alignment.content_measurement_sources
            ),
            "confirmed_undercrop_sides": list(
                alignment.confirmed_undercrop_sides
            ),
            "unconfirmed_undercrop_sides": list(
                alignment.unconfirmed_undercrop_sides
            ),
            "overcontains_long_axis": alignment.overcontains_long_axis,
            "overcontains_short_axis": alignment.overcontains_short_axis,
            "leading_slack_px": alignment.leading_slack_px,
            "trailing_slack_px": alignment.trailing_slack_px,
            "top_slack_px": alignment.top_slack_px,
            "bottom_slack_px": alignment.bottom_slack_px,
            "border_tonal_fraction": dict(alignment.border_tonal_fraction),
        },
        "holder_occupancy": {
            "state": occupancy.state.value,
            "strip_completeness": {
                "frame_count_complete": completeness.frame_count_complete,
                "frame_sequence_complete": completeness.frame_sequence_complete,
                "count": completeness.count,
                "nominal_count": completeness.nominal_count,
                "valid_frame_count": completeness.valid_frame_count,
                "expected_separator_count": completeness.expected_separator_count,
                "observed_separator_count": completeness.observed_separator_count,
            },
            "expected_film_span_mm": occupancy.expected_film_span_mm,
            "observed_film_span_px": occupancy.observed_film_span_px,
            "leading_slack_px": occupancy.leading_slack_px,
            "trailing_slack_px": occupancy.trailing_slack_px,
            "leading_slack_mm": occupancy.leading_slack_mm,
            "trailing_slack_mm": occupancy.trailing_slack_mm,
            "holder_fill_ratio": occupancy.holder_fill_ratio,
            "occupancy_status": occupancy.occupancy_status,
            "complete_underfilled_strip": occupancy.complete_underfilled_strip,
            "content_support_available": occupancy.content_support_available,
            "frame_coverage_state": occupancy.frame_coverage_state.value,
            "photo_dimensions_stable": occupancy.photo_dimensions_stable,
            "holder_span": typed_read_model(occupancy.holder_span),
            "film_span": typed_read_model(occupancy.film_span),
            "calibration_used": occupancy.calibration_used,
        },
        "partial_edge_safety": {
            "state": partial.state.value,
            "reason": partial.reason,
            "boundary_support": partial.boundary_support,
            "hard_separator_count": partial.hard_separator_count,
            "expected_separator_count": partial.expected_separator_count,
            "content_coverage_state": partial.content_coverage_state.value,
            "holder_occupancy_state": partial.holder_occupancy_state.value,
            "complete_underfilled_strip": partial.complete_underfilled_strip,
            "diagnostics": list(partial.diagnostics),
        },
        "independence": {
            "state": independence.state.value,
            "reason": independence.reason,
            "outer_root_measurement": independence.outer_root_measurement,
            "separator_root_measurements": list(
                independence.separator_root_measurements
            ),
            "cyclic_measurements": list(independence.cyclic_measurements),
        },
    }


def candidate_read_model(candidate: AssessedCandidate) -> dict[str, Any]:
    geometry = candidate.geometry
    hypothesis = candidate.count_hypothesis
    return {
        "format_id": geometry.format_id,
        "strip_mode": geometry.strip_mode,
        "count": int(geometry.count),
        "source": geometry.source,
        "outer_proposal": geometry.outer_proposal_name,
        "outer_strategy": geometry.outer_proposal_strategy,
        "film_span": typed_read_model(geometry.film_span.box),
        "frame_boxes": typed_read_model(geometry.image_frames),
        "confidence": float(candidate.assessment.scores.confidence),
        "scores": typed_read_model(candidate.assessment.scores),
        "candidate_gate": candidate_gate_read_model(candidate),
        "count_hypothesis": (
            None
            if hypothesis is None
            else {
                "count": hypothesis.count,
                "strip_mode": hypothesis.strip_mode,
                "offsets": list(hypothesis.offsets),
                "placement_source": hypothesis.placement_source,
                "source": hypothesis.source,
                "allowed_by_physical_spec": (
                    hypothesis.allowed_by_physical_spec
                ),
            }
        ),
        "evidence": candidate_evidence_read_model(candidate),
        "diagnostics": list(candidate.assessment.diagnostics),
    }


def candidate_table(detection: FinalDetection) -> list[dict[str, Any]]:
    selection = detection.require_trace().selection
    return [
        {
            "rank": index,
            "selected": candidate is selection.selected,
            **candidate_read_model(candidate),
        }
        for index, candidate in enumerate(
            selection.ranked_candidates,
            start=1,
        )
    ]


def selection_read_model(detection: FinalDetection) -> dict[str, Any]:
    selection = detection.require_trace().selection
    resolution = selection.geometry_resolution
    count_resolution = selection.count_resolution
    return {
        "consensus": selection.consensus,
        "geometry_resolution": {
            "state": resolution.state.value,
            "count_resolved": resolution.count_resolved,
            "placement_resolved": resolution.placement_resolved,
            "boundaries_resolved": resolution.boundaries_resolved,
            "coverage_resolved": resolution.coverage_resolved,
            "larger_counts_evaluated": resolution.larger_counts_evaluated,
            "alternative_geometries_resolved": (
                resolution.alternative_geometries_resolved
            ),
            "reasons": list(resolution.reasons),
        },
        "count_resolution": (
            None
            if count_resolution is None
            else {
                "selected_count": count_resolution.selected_count,
                "search_order": list(count_resolution.search_order),
                "evaluated_counts": list(count_resolution.evaluated_counts),
                "stopped_after_count": count_resolution.stopped_after_count,
                "reason": count_resolution.reason,
            }
        ),
        "clusters": [
            {
                "candidate_count": len(cluster.candidates),
                "representative": candidate_read_model(
                    cluster.representative
                ),
            }
            for cluster in selection.clusters
        ],
    }


def decision_gate_detail(detection: FinalDetection) -> dict[str, Any]:
    gate = detection.decision_gate
    return {
        "passed": bool(gate.passed),
        "checks": [gate_check_read_model(check) for check in gate.checks],
        "reason_inputs": [
            {"check": check, "final_review_reason": reason}
            for check, reason in gate.reason_inputs
        ],
    }
