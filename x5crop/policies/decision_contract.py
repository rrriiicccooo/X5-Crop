from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any

from ..formats import FormatSpec, format_spec
from .ids import POLICY_ID_STEMS, REPORT_SCHEMA_VERSION, decision_policy_id_for


@dataclass(frozen=True)
class ModePolicy:
    mode: str
    nominal_count: int
    allowed_counts: tuple[int, ...]
    expected_separator_count: int
    count_behavior: str
    outer_behavior: str
    stop_condition: str
    partial_edge_trust: str


@dataclass(frozen=True)
class EvidencePolicy:
    min_outer_area_ratio: float = 0.30
    max_outer_area_ratio: float = 0.985
    max_width_cv_ratio: float = 0.030
    min_geometry_score: float = 0.70
    min_content_score: float = 0.72
    min_hard_separator_ratio: float = 0.50
    min_hard_separator_count: int = 1
    max_equal_gap_count: int = 0
    max_content_gap_count: int = 0
    max_model_gap_share: float = 0.70
    allow_geometry_supported_separator: bool = False
    geometry_supported_min_hard_ratio: float = 0.35
    geometry_supported_max_width_cv_ratio: float = 0.010
    partial_requires_safe_edge: bool = True


@dataclass(frozen=True)
class RiskPolicy:
    review_on_outer_content_mismatch: bool = True
    review_on_overlap_risk: bool = True
    review_on_lucky_pass_risk: bool = True
    review_on_close_competition: bool = True
    candidate_close_margin: float = 0.020
    suppress_close_competition_when_partial_edge_safe: bool = True
    content_only_candidates_review_only: bool = True
    fallback_candidates_review_only: bool = True


@dataclass(frozen=True)
class CandidatePolicy:
    separator_candidate_can_pass: bool = True
    content_candidate_can_pass: bool = False
    fallback_candidate_can_pass: bool = False
    aggressive_candidate_default: str = "review_only"
    weak_grid_can_pass_alone: bool = False
    equal_gap_can_pass_alone: bool = False


@dataclass(frozen=True)
class DecisionPolicy:
    confidence_threshold_default: float = 0.85
    review_confidence_cap: float = 0.84
    policy_id: str = "evidence_guarded_decision"
    separator_incomplete_reason: str = "separator_evidence_incomplete"
    geometry_unstable_reason: str = "geometry_unstable"
    outer_content_mismatch_reason: str = "outer_content_mismatch"
    candidate_competition_close_reason: str = "candidate_competition_close"
    overlap_risk_reason: str = "overlap_risk"
    content_only_evidence_reason: str = "content_only_evidence"
    partial_edge_uncertain_reason: str = "partial_edge_uncertain"
    decision_insufficient_reason: str = "evidence_combination_insufficient"


@dataclass(frozen=True)
class OutputPolicy:
    preserve_tiff_metadata: bool = True
    detection_long_axis_bleed: int = 0
    detection_short_axis_bleed: int = 0
    output_long_axis_bleed_default: int = 20
    output_short_axis_bleed_default: int = 10
    overlap_risk_long_axis_bleed: int = 50


@dataclass(frozen=True)
class DecisionDiagnosticsPolicy:
    debug_panels: tuple[str, ...] = (
        "original_gray",
        "debug_boxes",
        "separator_evidence",
    )
    panel_titles: dict[str, str] | None = None
    hard_gap_color: str = "red"
    model_gap_color: str = "yellow_or_purple"
    risk_gap_color: str = "cyan_or_magenta"
    overlay_line_width_policy: str = "hard/model/diagnostic widths are policy-owned"

    def title_for(self, panel_id: str) -> str:
        titles = self.panel_titles or {
            "original_gray": "Original gray context",
            "debug_boxes": "Debug boxes",
            "separator_evidence": "Separator evidence",
            "frame_geometry": "Frame geometry",
            "outer_candidates": "Outer candidates",
            "selected_candidate": "Selected candidate",
            "risk_review": "Risk / review overlay",
        }
        return titles.get(panel_id, panel_id.replace("_", " ").title())


@dataclass(frozen=True)
class DetectionDecisionContract:
    policy_id: str
    schema_version: str
    format: FormatSpec
    mode: ModePolicy
    evidence: EvidencePolicy
    risk: RiskPolicy
    candidate: CandidatePolicy
    decision: DecisionPolicy
    output: OutputPolicy
    diagnostics: DecisionDiagnosticsPolicy

    def report_detail(self) -> dict[str, Any]:
        data = {
            "policy_id": self.policy_id,
            "schema_version": self.schema_version,
            "format_spec": {
                "format_id": self.format.format_id.value,
                "family": self.format.family,
                "nominal_frame_count": self.format.default_count,
                "allowed_count_range": list(self.format.allowed_counts),
                "frame_aspect": self.format.frame_aspect,
                "expected_separator_count": self.format.expected_separator_count,
                "full_mode_behavior": self.format.full_mode_behavior,
                "partial_mode_behavior": self.format.partial_mode_behavior,
                "outer_trust_profile": self.format.outer_trust_profile,
                "separator_visibility_expectation": self.format.separator_visibility,
                "geometry_tolerance": self.format.geometry_tolerance,
                "known_physical_risks": list(self.format.known_physical_risks),
            },
            "mode_policy": asdict(self.mode),
            "evidence_policy": asdict(self.evidence),
            "risk_policy": asdict(self.risk),
            "candidate_policy": asdict(self.candidate),
            "decision_policy": asdict(self.decision),
            "output_policy": asdict(self.output),
            "diagnostics_policy": {
                "debug_panels": list(self.diagnostics.debug_panels),
                "panel_titles": {
                    panel_id: self.diagnostics.title_for(panel_id)
                    for panel_id in self.diagnostics.debug_panels
                },
                "hard_gap_color": self.diagnostics.hard_gap_color,
                "model_gap_color": self.diagnostics.model_gap_color,
                "risk_gap_color": self.diagnostics.risk_gap_color,
                "overlay_line_width_policy": self.diagnostics.overlay_line_width_policy,
            },
        }
        return data


def mode_policy_for(spec: FormatSpec, strip_mode: str) -> ModePolicy:
    partial = strip_mode == "partial"
    return ModePolicy(
        mode=strip_mode,
        nominal_count=spec.default_count,
        allowed_counts=spec.allowed_counts,
        expected_separator_count=(
            max(0, spec.default_count - 1)
            if not partial
            else max(0, max(spec.allowed_counts) - 1)
        ),
        count_behavior=(
            "fixed_nominal_count" if not partial else "candidate_count_search"
        ),
        outer_behavior=(
            "outer_must_match_content_and_geometry"
            if not partial
            else "outer_edges_are_untrusted_until_supported"
        ),
        stop_condition=(
            "all_expected_internal_separators_supported"
            if not partial
            else "first_safe_candidate_or_review"
        ),
        partial_edge_trust=(
            "not_applicable" if not partial else "requires_safe_edge_evidence"
        ),
    )


def evidence_policy_for(format_id: str, strip_mode: str) -> EvidencePolicy:
    policy = EvidencePolicy()
    overrides: dict[str, dict[str, Any]] = {
        "135": {
            "min_hard_separator_ratio": 0.35,
            "min_hard_separator_count": 2,
            "max_width_cv_ratio": 0.030,
            "max_model_gap_share": 0.70,
        },
        "135-dual": {
            "min_hard_separator_ratio": 0.50,
            "min_hard_separator_count": 2,
            "max_width_cv_ratio": 0.035,
        },
        "half": {
            "min_hard_separator_ratio": 0.55,
            "min_hard_separator_count": 2,
            "max_width_cv_ratio": 0.012,
            "allow_geometry_supported_separator": True,
            "geometry_supported_min_hard_ratio": 0.20,
            "geometry_supported_max_width_cv_ratio": 0.010,
            "max_outer_area_ratio": 0.990,
        },
        "xpan": {
            "min_hard_separator_ratio": 0.67,
            "min_hard_separator_count": 1,
            "max_width_cv_ratio": 0.035,
        },
        "120-645": {
            "min_hard_separator_ratio": 0.67,
            "min_hard_separator_count": 2,
            "max_width_cv_ratio": 0.035,
        },
        "120-66": {
            "min_hard_separator_ratio": 0.90,
            "min_hard_separator_count": 2,
            "max_width_cv_ratio": 0.040,
            "max_outer_area_ratio": 0.990,
        },
        "120-67": {
            "min_hard_separator_ratio": 0.75,
            "min_hard_separator_count": 2,
            "max_width_cv_ratio": 0.040,
        },
    }
    values = overrides.get(format_id, {})
    if strip_mode == "partial":
        values = {
            **values,
            "min_hard_separator_ratio": min(
                float(values.get("min_hard_separator_ratio", policy.min_hard_separator_ratio)),
                0.35,
            ),
            "max_width_cv_ratio": max(
                float(values.get("max_width_cv_ratio", policy.max_width_cv_ratio)),
                0.045,
            ),
            "max_outer_area_ratio": max(
                float(values.get("max_outer_area_ratio", policy.max_outer_area_ratio)),
                0.990,
            ),
            "partial_requires_safe_edge": True,
        }
    return replace(policy, **values)


def policy_id_for(format_id: str, strip_mode: str) -> str:
    return decision_policy_id_for(format_id, strip_mode)


def decision_contract_for(format_id: str, strip_mode: str) -> DetectionDecisionContract:
    spec = format_spec(format_id)
    policy_id = policy_id_for(format_id, strip_mode)
    decision = replace(DecisionPolicy(), policy_id=policy_id)
    return DetectionDecisionContract(
        policy_id=policy_id,
        schema_version=REPORT_SCHEMA_VERSION,
        format=spec,
        mode=mode_policy_for(spec, strip_mode),
        evidence=evidence_policy_for(format_id, strip_mode),
        risk=RiskPolicy(),
        candidate=CandidatePolicy(),
        decision=decision,
        output=OutputPolicy(),
        diagnostics=DecisionDiagnosticsPolicy(),
    )


__all__ = [
    "REPORT_SCHEMA_VERSION",
    "CandidatePolicy",
    "DetectionDecisionContract",
    "DecisionPolicy",
    "DecisionDiagnosticsPolicy",
    "EvidencePolicy",
    "ModePolicy",
    "OutputPolicy",
    "POLICY_ID_STEMS",
    "RiskPolicy",
    "decision_contract_for",
    "policy_id_for",
]
