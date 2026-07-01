from __future__ import annotations

from dataclasses import asdict, fields, is_dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .runtime_policy import DetectionPolicy
    from .decision_contract import DetectionDecisionContract


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
    return {
        "content_floating": outer.content_floating,
        "edge_anchor": outer.edge_anchor,
        "base_candidates": _plain(outer.base_candidates),
        "content_floating_outer": _plain(outer.content_floating_outer),
        "edge_anchor_outer": _plain(outer.edge_anchor_outer),
        "separator_first": outer.separator_first,
        "separator_geometry": outer.separator_geometry,
        "separator_outer_allow_oversized_band": outer.separator_outer_allow_oversized_band,
        "separator_outer_oversized_band_max_ratio": outer.separator_outer_oversized_band_max_ratio,
        "separator_outer_oversized_band_score_penalty": outer.separator_outer_oversized_band_score_penalty,
        "separator_gap_search_max_width_ratio": outer.separator_gap_search_max_width_ratio,
        "separator_outer_band": _plain(outer.separator_outer_band),
        "separator_geometry_outer": _plain(outer.separator_geometry_outer),
        "dark_band": outer.dark_band,
        "format_geometry_retry": _plain(outer.format_geometry_retry),
        "grid_refine": _plain(outer.grid_refine),
        "short_axis_aspect_retry": _plain(outer.short_axis_aspect_retry),
        "content_alignment": _plain(outer.content_alignment),
        # Keep the report schema stable: expose only the audited dark-band fields.
        "dark_band_outer": _fields(
            outer.dark_band_outer,
            (
                "mode",
                "required_count",
                "threshold_ratio",
                "threshold_span_ratio",
                "min_width_ratio",
                "max_width_ratio",
                "core_width_cap_ratio",
                "spacing_min_ratio",
                "spacing_max_ratio",
                "source_candidate_count",
                "max_candidates",
                "full_selection_enabled",
                "full_selection_strip_modes",
                "full_selection_requires_required_count",
                "full_selection_requires_help",
                "full_selection_required_support",
                "full_selection_allow_equal_gaps",
                "full_selection_help_supports",
                "full_selection_help_reasons",
            ),
        ),
        "retries": list(outer.retries),
    }


def _separator_detail(policy: "DetectionPolicy") -> dict[str, Any]:
    separator = policy.separator
    return {
        "gate_profile": separator.gate.profile,
        "hard_required_all_gaps": separator.hard_required_all_gaps,
        "wide_retry": separator.wide_retry,
        "wide_retry_max_width_ratio": separator.wide_retry_max_width_ratio,
        "wide_separator_confidence_cap": separator.wide_separator_confidence_cap,
        "geometry_support_modes": list(separator.geometry_support_modes),
        "geometry_support": _plain(separator.geometry_support),
        "profile": _plain(separator.profile),
        "edge_refine_profile": _plain(separator.edge_refine_profile),
        "edge_pair": _plain(separator.edge_pair),
        "hard_gap_trust": _plain(separator.hard_gap_trust),
        "nearby_correction": _plain(separator.nearby_correction),
        "robust_grid": _plain(separator.robust_grid),
        "gap_search": _plain(separator.gap_search),
        "enhanced": _plain(separator.enhanced),
        "gate": _plain(separator.gate),
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
        "overlap_bleed_risk": _plain(diagnostics.overlap_bleed_risk),
        "debug_gap_overlay": _plain(diagnostics.debug_gap_overlay),
        "nearby_separator": _plain(diagnostics.nearby_separator),
        "lucky_pass_risk": _plain(diagnostics.lucky_pass_risk),
        "debug_panels": list(diagnostics.debug_panels),
        "debug_panel_titles": {
            panel.panel_id: panel.title for panel in diagnostics.debug_panel_titles
        },
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
        "gates": list(policy.gates.ordered_gates),
        "partial_holder": _plain(policy.partial_holder),
        "partial_edge_hint": _plain(policy.partial_edge_hint),
        "scoring": _scoring_detail(policy),
        "selection": _selection_detail(policy),
        "candidate_run": _plain(policy.candidate_run),
        "postprocess": _plain(policy.postprocess),
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
        "known_physical_risks": list(spec.known_physical_risks),
    }


def _decision_diagnostics_detail(contract: "DetectionDecisionContract") -> dict[str, Any]:
    diagnostics = contract.diagnostics
    return {
        "debug_panels": list(diagnostics.debug_panels),
        "panel_titles": {
            panel_id: diagnostics.title_for(panel_id) for panel_id in diagnostics.debug_panels
        },
        "hard_gap_color": diagnostics.hard_gap_color,
        "model_gap_color": diagnostics.model_gap_color,
        "risk_gap_color": diagnostics.risk_gap_color,
        "overlay_line_width_policy": diagnostics.overlay_line_width_policy,
    }


def decision_contract_report_detail(contract: "DetectionDecisionContract") -> dict[str, Any]:
    return {
        "policy_id": contract.policy_id,
        "schema_version": contract.schema_version,
        "format_spec": _format_spec_detail(contract),
        "mode_policy": asdict(contract.mode),
        "evidence_policy": asdict(contract.evidence),
        "risk_policy": asdict(contract.risk),
        "candidate_policy": asdict(contract.candidate),
        "decision_policy": asdict(contract.decision),
        "output_policy": asdict(contract.output),
        "diagnostics_policy": _decision_diagnostics_detail(contract),
    }
