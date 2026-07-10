from __future__ import annotations

from dataclasses import asdict, fields, is_dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...formats import FormatDescription, FormatPhysicalSpec
    from ..runtime.policy import DetectionPolicy
    from ..decision.contract import DetectionDecisionContract

from ...constants import HARD_GAP_METHODS, MODEL_GAP_METHODS
from .mode_descriptions import mode_notes_for_spec, mode_role_for_spec


def _plain(value: Any) -> Any:
    if is_dataclass(value):
        return {field.name: _plain(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    return value


def _physical_detail(policy: "DetectionPolicy") -> dict[str, Any]:
    spec = policy.physical_spec
    return {
        "family": spec.family,
        "physical_layout": spec.physical_layout,
        "default_count": int(spec.default_count),
        "allowed_counts": list(spec.allowed_counts),
        "nominal_frame_size_mm": _plain(spec.nominal_frame_size_mm),
        "frame_size_mm_options": _plain(spec.frame_size_mm_options),
        "frame_aspect": spec.horizontal_content_aspect,
        "aspect_source": "frame_size_mm",
        "frame_geometry_profile": spec.frame_geometry_profile,
        "complete_strip_can_be_underfilled": bool(spec.complete_strip_can_be_underfilled),
    }


def _physical_runtime_detail(policy: "DetectionPolicy") -> dict[str, Any]:
    return {
        "preprocess": _plain(policy.preprocess),
        "detector_kind": policy.detector_kind,
        "partial_count_offsets": list(policy.partial_count_offsets),
        "outer": {
            "proposal_families": {
                "partial_placement": policy.outer.proposal.geometry.partial_placement.enabled,
                "separator_geometry": True,
            },
            "correction": _plain(policy.outer.correction),
        },
        "separator": {
            "support_mode": "unified_physical_support",
            "width_profile_mode": policy.separator.width_profile.mode,
            "geometry_support_modes": list(policy.separator.geometry_support.active_modes()),
            "hard_methods": sorted(HARD_GAP_METHODS),
            "model_methods": sorted(MODEL_GAP_METHODS),
        },
        "content": {
            "evidence": _plain(policy.content.evidence),
            "profile": _plain(policy.content.profile),
            "mask": _plain(policy.content.mask),
            "candidate": _plain(policy.content.candidate),
        },
    }


def _candidate_runtime_detail(policy: "DetectionPolicy") -> dict[str, Any]:
    return {
        "candidate_plan": _plain(policy.candidate_plan),
        "partial_holder": _plain(policy.partial_holder),
        "partial_edge_hint": _plain(policy.partial_edge_hint),
        "selection": _plain(policy.candidate_selection),
        "scoring": {
            "weights": {
                "geometry": policy.scoring.calibration.geometry_weight,
                "content": policy.scoring.calibration.content_weight,
                "separator": policy.scoring.calibration.separator_weight,
            },
        },
    }


def _decision_runtime_detail(policy: "DetectionPolicy") -> dict[str, Any]:
    return {
        "decision": _plain(policy.decision),
        "exposure_overlap_evidence": _plain(policy.exposure_overlap_evidence),
        "exposure_overlap_protection": _plain(
            policy.output.exposure_overlap_protection
        ),
    }


def _diagnostics_runtime_detail(policy: "DetectionPolicy") -> dict[str, Any]:
    return {
        "debug_panels": list(policy.diagnostics.debug_panels),
        "debug_panel_titles": {
            panel.panel_id: panel.title for panel in policy.diagnostics.debug_panel_titles
        },
    }


def detection_policy_report_detail(policy: "DetectionPolicy") -> dict[str, Any]:
    spec = policy.physical_spec
    return {
        "policy_id": policy.policy_id,
        "format_id": spec.format_id,
        "strip_mode": policy.strip_mode,
        "role": mode_role_for_spec(spec, policy.strip_mode),
        "physical": _physical_detail(policy),
        "physical_runtime": _physical_runtime_detail(policy),
        "candidate_runtime": _candidate_runtime_detail(policy),
        "decision_runtime": _decision_runtime_detail(policy),
        "output_runtime": {
            "approved_geometry_adjustment": _plain(policy.approved_geometry_adjustment),
            "output": _plain(policy.output),
        },
        "diagnostics_runtime": _diagnostics_runtime_detail(policy),
        "notes": list(mode_notes_for_spec(spec, policy.strip_mode)),
    }


def _format_spec_detail(
    contract: "DetectionDecisionContract",
    description: "FormatDescription",
) -> dict[str, Any]:
    spec = contract.physical_spec
    return {
        "format_id": spec.format_id,
        "family": spec.family,
        "nominal_frame_count": spec.default_count,
        "allowed_count_range": list(spec.allowed_counts),
        "nominal_frame_size_mm": _plain(spec.nominal_frame_size_mm),
        "frame_size_mm_options": _plain(spec.frame_size_mm_options),
        "frame_aspect": spec.horizontal_content_aspect,
        "aspect_source": "frame_size_mm",
        "expected_separator_count": spec.expected_separator_count,
        "complete_strip_can_be_underfilled": bool(spec.complete_strip_can_be_underfilled),
        "full_mode_behavior": description.full_mode_behavior,
        "partial_mode_behavior": description.partial_mode_behavior,
        "outer_trust_profile": description.outer_trust_profile,
        "separator_visibility_expectation": description.separator_visibility,
        "geometry_tolerance": description.geometry_tolerance,
        "known_physical_notes": list(description.known_physical_notes),
    }


def decision_contract_report_detail(
    contract: "DetectionDecisionContract",
    description: "FormatDescription",
) -> dict[str, Any]:
    return {
        "policy_id": contract.policy_id,
        "format_spec": _format_spec_detail(contract, description),
        "mode_policy": _decision_mode_detail(
            contract.physical_spec,
            contract.strip_mode,
        ),
        "evidence_policy": asdict(contract.evidence),
        "decision_policy": asdict(contract.decision),
        "candidate_selection_policy": asdict(contract.candidate_selection),
    }


def _decision_mode_detail(
    spec: "FormatPhysicalSpec",
    strip_mode: str,
) -> dict[str, Any]:
    partial = strip_mode == "partial"
    return {
        "mode": strip_mode,
        "nominal_count": spec.default_count,
        "allowed_counts": list(spec.allowed_counts),
        "expected_separator_count": spec.expected_separator_count,
        "count_behavior": (
            "fixed_nominal_count" if not partial else "candidate_count_search"
        ),
        "outer_behavior": (
            "outer_must_match_content_and_geometry"
            if not partial
            else "outer_edges_are_untrusted_until_supported"
        ),
        "stop_condition": (
            "all_expected_internal_separators_supported"
            if not partial
            else "first_safe_candidate_or_review"
        ),
        "partial_edge_trust": (
            "not_applicable" if not partial else "requires_safe_edge_evidence"
        ),
    }
