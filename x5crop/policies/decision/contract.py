from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from ...formats import FormatSpec, format_spec
from .overrides import evidence_policy_values
from ..ids import REPORT_SCHEMA_VERSION, decision_policy_id_for

if TYPE_CHECKING:
    from ..runtime.policy import DetectionPolicy


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
    max_photo_width_cv_ratio: float = 0.030
    min_geometry_score: float = 0.70
    min_content_score: float = 0.72
    min_hard_separator_ratio: float = 0.50
    min_hard_separator_count: int = 1
    max_equal_gap_count: int = 0
    max_content_gap_count: int = 0
    max_model_gap_share: float = 0.70
    allow_geometry_supported_separator: bool = False
    geometry_supported_min_hard_ratio: float = 0.35
    geometry_supported_max_photo_width_cv_ratio: float = 0.010
    partial_requires_safe_edge: bool = False


@dataclass(frozen=True)
class RiskPolicy:
    review_on_outer_content_mismatch: bool = True
    review_on_overlap_risk: bool = True
    review_on_lucky_pass_risk: bool = True
    review_on_close_competition: bool = True
    candidate_close_margin: float = 0.020
    suppress_close_competition_when_partial_edge_safe: bool = True
    content_only_candidates_review_only: bool = True
    safety_candidates_review_only: bool = True


@dataclass(frozen=True)
class DecisionPolicy:
    confidence_threshold_default: float = 0.85
    review_confidence_cap: float = 0.84
    policy_id: str = "evidence_guarded_decision"
    align_outer_to_content: bool = True
    outer_alignment_disabled_reason: str = "disabled_by_policy"
    content_aspect_conflict_cap: float = 0.82
    content_low_confidence_cap: float = 0.84
    outer_mismatch_cap: float = 0.84
    lucky_pass_risk_cap: float = 0.84
    likely_partial_review_reason: str = "likely_partial_strip"
    outer_candidate_disagreement_review_reason: str = "outer_candidate_disagreement"
    deskew_uncertain_review_reason: str = "deskew_uncertain"
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
    decision: DecisionPolicy
    output: OutputPolicy
    diagnostics: DecisionDiagnosticsPolicy

    def report_detail(self) -> dict[str, Any]:
        from ..reporting import decision_contract_report_detail

        return decision_contract_report_detail(self)

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


def evidence_policy_for(
    format_id: str,
    strip_mode: str,
    detection_policy: DetectionPolicy | None = None,
) -> EvidencePolicy:
    policy = EvidencePolicy()
    values = evidence_policy_values(format_id, strip_mode, policy, detection_policy)
    return replace(policy, **values)


def decision_policy_for(detection_policy: DetectionPolicy) -> DecisionPolicy:
    policy_id = decision_policy_id_for(detection_policy.format_id, detection_policy.strip_mode)
    return replace(
        DecisionPolicy(),
        policy_id=policy_id,
        confidence_threshold_default=detection_policy.scoring.confidence_threshold_default,
        review_confidence_cap=detection_policy.candidate_selection.confidence_cap,
        align_outer_to_content=detection_policy.decision.align_outer_to_content,
        outer_alignment_disabled_reason=detection_policy.decision.outer_alignment_disabled_reason,
        content_aspect_conflict_cap=detection_policy.decision.content_aspect_conflict_cap,
        content_low_confidence_cap=detection_policy.decision.content_low_confidence_cap,
        outer_mismatch_cap=detection_policy.decision.outer_mismatch_cap,
        lucky_pass_risk_cap=detection_policy.decision.lucky_pass_risk_cap,
        likely_partial_review_reason=detection_policy.decision.likely_partial_review_reason,
        outer_candidate_disagreement_review_reason=detection_policy.decision.outer_candidate_disagreement_review_reason,
        deskew_uncertain_review_reason=detection_policy.decision.deskew_uncertain_review_reason,
    )


def risk_policy_for(detection_policy: DetectionPolicy) -> RiskPolicy:
    return RiskPolicy(
        candidate_close_margin=float(detection_policy.candidate_selection.close_margin),
    )


def output_policy_for(detection_policy: DetectionPolicy) -> OutputPolicy:
    output = detection_policy.output
    return OutputPolicy(
        detection_long_axis_bleed=output.detection_long_axis_bleed,
        detection_short_axis_bleed=output.detection_short_axis_bleed,
        output_long_axis_bleed_default=output.output_long_axis_bleed_default,
        output_short_axis_bleed_default=output.output_short_axis_bleed_default,
        overlap_risk_long_axis_bleed=output.overlap_risk_long_axis_bleed,
    )


def diagnostics_policy_for(detection_policy: DetectionPolicy) -> DecisionDiagnosticsPolicy:
    diagnostics = detection_policy.diagnostics
    return DecisionDiagnosticsPolicy(
        debug_panels=diagnostics.debug_panels,
        panel_titles={
            panel.panel_id: panel.title for panel in diagnostics.debug_panel_titles
        },
    )


def decision_contract_for_policy(detection_policy: DetectionPolicy) -> DetectionDecisionContract:
    spec = format_spec(detection_policy.format_id)
    policy_id = decision_policy_id_for(detection_policy.format_id, detection_policy.strip_mode)
    return DetectionDecisionContract(
        policy_id=policy_id,
        schema_version=detection_policy.report.schema_version,
        format=spec,
        mode=mode_policy_for(spec, detection_policy.strip_mode),
        evidence=evidence_policy_for(
            detection_policy.format_id,
            detection_policy.strip_mode,
            detection_policy,
        ),
        risk=risk_policy_for(detection_policy),
        decision=decision_policy_for(detection_policy),
        output=output_policy_for(detection_policy),
        diagnostics=diagnostics_policy_for(detection_policy),
    )


def decision_contract_for(format_id: str, strip_mode: str) -> DetectionDecisionContract:
    from ..registry import get_detection_policy

    return decision_contract_for_policy(get_detection_policy(format_id, strip_mode))


__all__ = [
    "REPORT_SCHEMA_VERSION",
    "DetectionDecisionContract",
    "DecisionPolicy",
    "DecisionDiagnosticsPolicy",
    "EvidencePolicy",
    "ModePolicy",
    "OutputPolicy",
    "RiskPolicy",
    "decision_contract_for",
    "decision_contract_for_policy",
    "decision_policy_for",
    "diagnostics_policy_for",
    "evidence_policy_for",
    "output_policy_for",
    "risk_policy_for",
]
