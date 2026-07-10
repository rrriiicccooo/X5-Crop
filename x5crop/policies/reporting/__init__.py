from __future__ import annotations

from dataclasses import asdict, fields, is_dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..runtime.policy import DetectionPolicy
    from ..decision.contract import DetectionDecisionContract

from ...formats import format_description
from ...formats.traits import runtime_traits_for_spec
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
    traits = runtime_traits_for_spec(spec)
    return {
        "family": spec.family,
        "physical_layout": spec.physical_layout,
        "default_count": int(spec.default_count),
        "allowed_counts": list(spec.allowed_counts),
        "nominal_frame_size_mm": _plain(spec.nominal_frame_size_mm),
        "frame_size_mm_options": _plain(spec.frame_size_mm_options),
        "frame_aspect": spec.frame_aspect,
        "aspect_source": "frame_size_mm",
        "runtime_traits": _plain(traits),
        "complete_strip_can_be_underfilled": bool(spec.complete_strip_can_be_underfilled),
    }


def _physical_runtime_detail(policy: "DetectionPolicy") -> dict[str, Any]:
    return {
        "preprocess": _plain(policy.preprocess),
        "detector": {
            "kind": policy.detector.kind,
            "review_only": _plain(policy.detector.review_only),
        },
        "count_hypotheses": _plain(policy.count_hypotheses),
        "outer": {
            "proposal_families": {
                "base": policy.outer.proposal.base.enabled,
                "partial_placement": policy.outer.proposal.geometry.partial_placement.enabled,
                "separator_geometry": True,
            },
            "correction": _plain(policy.outer.correction),
        },
        "separator": {
            "support_mode": "unified_physical_support",
            "hard_required_all_gaps": policy.separator.hard_required_all_gaps,
            "width_profile_mode": policy.separator.width_profile.mode,
            "geometry_support_modes": list(policy.separator.geometry_support_modes),
            "hard_methods": list(policy.separator.hard_methods),
            "model_methods": list(policy.separator.model_methods),
        },
        "content": {
            "validates_candidates": bool(policy.content.validates_candidates),
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
            "hard_full_confidence_floor": policy.scoring.hard_full_confidence_floor,
            "weights": {
                "geometry": policy.scoring.geometry_weight,
                "content": policy.scoring.content_weight,
                "separator": policy.scoring.separator_weight,
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
        "report_schema_id": policy.report.schema_id,
        "report_schema_revision": policy.report.schema_revision,
        "report_sections": list(policy.report.sections),
    }


def detection_policy_report_detail(policy: "DetectionPolicy") -> dict[str, Any]:
    spec = policy.physical_spec
    return {
        "policy_id": policy.policy_id,
        "format": spec.name,
        "strip_mode": policy.strip_mode,
        "role": mode_role_for_spec(spec, policy.strip_mode),
        "physical": _physical_detail(policy),
        "physical_runtime": _physical_runtime_detail(policy),
        "candidate_runtime": _candidate_runtime_detail(policy),
        "decision_runtime": _decision_runtime_detail(policy),
        "output_runtime": {
            "finalization": _plain(policy.finalization),
            "output": _plain(policy.output),
        },
        "diagnostics_runtime": _diagnostics_runtime_detail(policy),
        "notes": list(mode_notes_for_spec(spec, policy.strip_mode)),
    }


def _format_spec_detail(contract: "DetectionDecisionContract") -> dict[str, Any]:
    spec = contract.format
    description = format_description(spec.format_id)
    return {
        "format_id": spec.format_id.value,
        "family": spec.family,
        "nominal_frame_count": spec.default_count,
        "allowed_count_range": list(spec.allowed_counts),
        "nominal_frame_size_mm": _plain(spec.nominal_frame_size_mm),
        "frame_size_mm_options": _plain(spec.frame_size_mm_options),
        "frame_aspect": spec.frame_aspect,
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


def decision_contract_report_detail(contract: "DetectionDecisionContract") -> dict[str, Any]:
    return {
        "policy_id": contract.policy_id,
        "format_spec": _format_spec_detail(contract),
        "mode_policy": asdict(contract.mode),
        "evidence_policy": asdict(contract.evidence),
        "decision_policy": asdict(contract.decision),
    }
