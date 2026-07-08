from __future__ import annotations

from dataclasses import asdict, fields, is_dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..runtime.policy import DetectionPolicy
    from ..decision.contract import DetectionDecisionContract


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


def _fields(value: Any, names: tuple[str, ...]) -> dict[str, Any]:
    return {name: _plain(getattr(value, name)) for name in names}


def _detector_detail(policy: "DetectionPolicy") -> dict[str, Any]:
    return _plain(policy.detector)


def _outer_detail(policy: "DetectionPolicy") -> dict[str, Any]:
    outer = policy.outer
    proposal = outer.proposal
    geometry = proposal.geometry
    separator = geometry.separator
    correction = outer.correction
    return {
        "proposal": {
            "base": _plain(proposal.base),
            "geometry": {
                "partial_placement": _plain(geometry.partial_placement),
                "separator": {
                    "local": _plain(separator.local),
                    "full_width": _plain(separator.full_width),
                    "width_profile_family": _plain(separator.width_profile_family),
                    "separator_outer_allow_oversized_band": separator.separator_outer_allow_oversized_band,
                    "separator_outer_oversized_band_max_ratio": separator.separator_outer_oversized_band_max_ratio,
                    "separator_outer_oversized_band_score_penalty": separator.separator_outer_oversized_band_score_penalty,
                    "separator_gap_search_max_width_ratio": separator.separator_gap_search_max_width_ratio,
                    "band": _plain(separator.band),
                    "full_width_outer": _plain(separator.full_width_outer),
                },
                "grid_refine": _plain(geometry.grid_refine),
            },
        },
        "correction": _plain(correction),
    }


def _separator_detail(policy: "DetectionPolicy") -> dict[str, Any]:
    separator = policy.separator
    width_profile_search = _plain(separator.width_profile_search)
    width_profile_policy = _fields(
        separator.width_profile,
        (
            "mode",
            "max_width_ratio",
            "required_count",
            "spacing_min_ratio",
            "spacing_max_ratio",
            "source_candidate_count",
            "band_candidate_count",
            "sequence_candidate_count",
            "max_candidates",
        ),
    )
    return {
        "support_mode": "unified_physical_support",
        "hard_required_all_gaps": separator.hard_required_all_gaps,
        "separator_proposal": {
            "width_aware": {
                "enabled": True,
                "max_width_ratio": separator.gap_search.max_width_ratio,
                "theoretical_separator_width": separator.width_profile.mode != "off",
                "observed_width_profile": separator.width_profile.mode != "off",
            },
        },
        "width_profile": {**width_profile_search, **width_profile_policy},
        "width_profile_search": width_profile_search,
        "model_gap_proposal": _plain(separator.model_gap_proposal),
        "refinement": _plain(separator.refinement),
        "geometry_support_modes": list(separator.geometry_support_modes),
        "geometry_support": _plain(separator.geometry_support),
        "profile": _plain(separator.profile),
        "edge_refine_profile": _plain(separator.edge_refine_profile),
        "edge_pair": _plain(separator.edge_pair),
        "hard_gap_trust": _plain(separator.hard_gap_trust),
        "nearby_refinement": _plain(separator.nearby_refinement),
        "robust_grid": _plain(separator.robust_grid),
        "gap_search": _plain(separator.gap_search),
        "hard_methods": list(separator.hard_methods),
        "model_methods": list(separator.model_methods),
        "support": _plain(separator.support),
    }


def _content_detail(policy: "DetectionPolicy") -> dict[str, Any]:
    return _plain(policy.content)


def _scoring_detail(policy: "DetectionPolicy") -> dict[str, Any]:
    return _plain(policy.scoring)


def _selection_detail(policy: "DetectionPolicy") -> dict[str, Any]:
    return _plain(policy.candidate_selection)


def _runtime_diagnostics_detail(policy: "DetectionPolicy") -> dict[str, Any]:
    diagnostics = policy.diagnostics
    return {
        "debug_gap_overlay": _plain(diagnostics.debug_gap_overlay),
        "nearby_separator": _plain(diagnostics.nearby_separator),
        "debug_panels": list(diagnostics.debug_panels),
        "debug_panel_titles": {
            panel.panel_id: panel.title for panel in diagnostics.debug_panel_titles
        },
    }


def _output_evidence_detail(policy: "DetectionPolicy") -> dict[str, Any]:
    return {
        "output_overlap": _plain(policy.output_evidence.output_overlap),
    }


def _report_detail(policy: "DetectionPolicy") -> dict[str, Any]:
    return {
        "schema_version": policy.report.schema_version,
        "sections": list(policy.report.sections),
    }


def detection_policy_report_detail(policy: "DetectionPolicy") -> dict[str, Any]:
    return {
        "policy_id": policy.policy_id,
        "format": policy.format_id,
        "strip_mode": policy.strip_mode,
        "family": policy.family,
        "role": policy.role,
        "detector": _detector_detail(policy),
        "outer": _outer_detail(policy),
        "separator": _separator_detail(policy),
        "content": _content_detail(policy),
        "partial_holder": _plain(policy.partial_holder),
        "partial_edge_hint": _plain(policy.partial_edge_hint),
        "scoring": _scoring_detail(policy),
        "selection": _selection_detail(policy),
        "candidate_plan": _plain(policy.candidate_plan),
        "output_evidence": _output_evidence_detail(policy),
        "decision": _plain(policy.decision),
        "finalization": _plain(policy.finalization),
        "output": _plain(policy.output),
        "diagnostics": _runtime_diagnostics_detail(policy),
        "report": _report_detail(policy),
        "notes": list(policy.notes),
    }


def _format_spec_detail(contract: "DetectionDecisionContract") -> dict[str, Any]:
    spec = contract.format
    return {
        "format_id": spec.format_id.value,
        "family": spec.family,
        "nominal_frame_count": spec.default_count,
        "allowed_count_range": list(spec.allowed_counts),
        "frame_aspect": spec.frame_aspect,
        "expected_separator_count": spec.expected_separator_count,
        "full_mode_behavior": spec.full_mode_behavior,
        "partial_mode_behavior": spec.partial_mode_behavior,
        "outer_trust_profile": spec.outer_trust_profile,
        "separator_visibility_expectation": spec.separator_visibility,
        "geometry_tolerance": spec.geometry_tolerance,
        "known_physical_notes": list(spec.known_physical_notes),
    }


def decision_contract_report_detail(contract: "DetectionDecisionContract") -> dict[str, Any]:
    return {
        "policy_id": contract.policy_id,
        "schema_version": contract.schema_version,
        "format_spec": _format_spec_detail(contract),
        "mode_policy": asdict(contract.mode),
        "evidence_policy": asdict(contract.evidence),
        "decision_policy": asdict(contract.decision),
    }
