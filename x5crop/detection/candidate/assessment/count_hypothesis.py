from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ....domain import DetectionCandidate
from ...evidence.separator_summary import separator_support_detail_summary
from ..plan.count_hypotheses import CountHypothesis


def _candidate_passes_gate(candidate: DetectionCandidate) -> bool:
    assessment = candidate.detail.get("candidate_assessment")
    if not isinstance(assessment, dict):
        return False
    gate = assessment.get("candidate_gate")
    return bool(isinstance(gate, dict) and gate.get("passed", False))


@dataclass(frozen=True)
class PhysicalCountResolution:
    count_resolved: bool
    placement_resolved: bool
    evidence: dict[str, Any]

    def report_detail(self) -> dict[str, Any]:
        return {
            "count_resolved": bool(self.count_resolved),
            "placement_resolved": bool(self.placement_resolved),
            "evidence": dict(self.evidence),
        }


def physical_count_resolution(
    candidate: DetectionCandidate,
    hypothesis: CountHypothesis,
) -> PhysicalCountResolution:
    assessment = candidate.detail.get("candidate_assessment", {})
    assessment = dict(assessment) if isinstance(assessment, dict) else {}
    separator = assessment.get("separator_support", {})
    separator = dict(separator) if isinstance(separator, dict) else {}
    separator_summary = separator_support_detail_summary(separator)
    topology = candidate.detail.get("frame_topology_evidence", {})
    topology = dict(topology) if isinstance(topology, dict) else {}
    continuity = candidate.detail.get("separator_cross_axis_continuity", {})
    continuity = dict(continuity) if isinstance(continuity, dict) else {}
    photo_size = candidate.detail.get("photo_width_stability", {})
    photo_size = dict(photo_size) if isinstance(photo_size, dict) else {}

    expected_gaps = max(0, int(hypothesis.count) - 1)
    hard_separator_complete = bool(
        expected_gaps > 0
        and separator_summary.hard_separator_gaps >= expected_gaps
    )
    topology_valid = all(
        bool(topology.get(key, False))
        for key in (
            "frame_extent_valid",
            "frame_order_valid",
            "frame_overlap_absent",
        )
    )
    separator_continuous = bool(continuity.get("ok", False))
    photo_size_consistent = bool(
        photo_size.get("used", False) and not photo_size.get("unstable", True)
    )
    count_resolved = all(
        (
            hypothesis.physically_supported,
            int(candidate.count) == int(hypothesis.count),
            hard_separator_complete,
            topology_valid,
            separator_continuous,
            photo_size_consistent,
        )
    )
    return PhysicalCountResolution(
        count_resolved=bool(count_resolved),
        placement_resolved=bool(count_resolved),
        evidence={
            "hypothesis_physically_supported": bool(hypothesis.physically_supported),
            "expected_gap_count": int(expected_gaps),
            "hard_separator_gap_count": int(separator_summary.hard_separator_gaps),
            "hard_separator_complete": bool(hard_separator_complete),
            "separator_cross_axis_continuity_ok": bool(separator_continuous),
            "photo_size_consistent": bool(photo_size_consistent),
            "frame_topology_valid": bool(topology_valid),
        },
    )


@dataclass(frozen=True)
class CountHypothesisEvaluation:
    hypothesis: CountHypothesis
    candidates: tuple[DetectionCandidate, ...]
    count_resolved: bool
    placement_resolved: bool
    candidate_auto_ready: bool
    resolved_offsets: tuple[float, ...]
    resolution_checks: tuple[dict[str, Any], ...]

    def report_detail(self) -> dict[str, Any]:
        confidences = [float(candidate.confidence) for candidate in self.candidates]
        return {
            **self.hypothesis.report_detail(),
            "candidate_count": len(self.candidates),
            "candidate_gate_pass_count": sum(
                1 for candidate in self.candidates if _candidate_passes_gate(candidate)
            ),
            "max_confidence": max(confidences) if confidences else None,
            "count_resolved": bool(self.count_resolved),
            "placement_resolved": bool(self.placement_resolved),
            "candidate_auto_ready": bool(self.candidate_auto_ready),
            "resolved_offsets": [float(offset) for offset in self.resolved_offsets],
            "resolution_checks": [dict(check) for check in self.resolution_checks],
        }
