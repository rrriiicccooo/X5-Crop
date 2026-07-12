from __future__ import annotations

from dataclasses import fields, is_dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..runtime.policy import DetectionPolicy

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
        "expected_separator_count": int(spec.expected_separator_count),
        "allowed_counts": list(spec.allowed_counts),
        "nominal_frame_size_mm": _plain(spec.nominal_frame_size_mm),
        "frame_size_mm_options": _plain(spec.frame_size_mm_options),
        "frame_aspect": spec.horizontal_content_aspect,
        "aspect_source": "frame_size_mm",
        "complete_strip_can_be_underfilled": bool(spec.complete_strip_can_be_underfilled),
    }


def _physical_runtime_detail(policy: "DetectionPolicy") -> dict[str, Any]:
    return {
        "preprocess": _plain(policy.preprocess),
        "detector_kind": policy.detector_kind,
        "sequence": {
            "boundary_detection": _plain(policy.sequence.boundary_detection),
            "hypothesis_budget": _plain(policy.candidate_plan.sequence_hypotheses),
        },
        "separator": {
            "observation": _plain(policy.separator.observation),
            "profile": _plain(policy.separator.profile),
            "continuity": _plain(policy.separator.continuity),
            "frame_dimensions": _plain(policy.separator.frame_dimension_prior),
        },
        "content": {
            "evidence": _plain(policy.content.evidence),
            "profile": _plain(policy.content.profile),
            "sequence_alignment": _plain(policy.sequence.content_alignment),
        },
    }


def _candidate_runtime_detail(policy: "DetectionPolicy") -> dict[str, Any]:
    return {"candidate_plan": _plain(policy.candidate_plan)}


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
        "output_runtime": {
            "output": _plain(policy.output),
        },
        "diagnostics_runtime": _diagnostics_runtime_detail(policy),
        "notes": list(mode_notes_for_spec(spec, policy.strip_mode)),
    }
