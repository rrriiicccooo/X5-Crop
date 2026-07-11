from __future__ import annotations

from ....domain import Box, DetectionCandidate
from ....policies.parameters.scoring import SelectionConsensusParameters


def _candidate_assessment(candidate: DetectionCandidate) -> dict:
    assessment = candidate.detail.get("candidate_assessment", {})
    return dict(assessment) if isinstance(assessment, dict) else {}


def _candidate_gate_allows_selection(candidate: DetectionCandidate) -> bool:
    gate = _candidate_assessment(candidate).get("candidate_gate", {})
    return bool(isinstance(gate, dict) and gate.get("passed", False))


def calibrated_candidate_rank(
    detection: DetectionCandidate,
) -> tuple[int, int, float, float, int]:
    assessment = _candidate_assessment(detection)
    joint = float(assessment.get("joint_score", 0.0))
    plan = detection.detail.get("candidate_plan", {})
    hypothesis = plan.get("count_hypothesis", {}) if isinstance(plan, dict) else {}
    physically_supported_count = bool(
        isinstance(hypothesis, dict) and hypothesis.get("physically_supported", False)
    )
    return (
        1 if _candidate_gate_allows_selection(detection) else 0,
        1 if physically_supported_count else 0,
        float(detection.confidence),
        joint,
        int(detection.count),
    )


def select_source_candidate(candidates: list[DetectionCandidate]) -> DetectionCandidate:
    return max(candidates, key=calibrated_candidate_rank)


def is_partial_occupancy_candidate(detection: DetectionCandidate) -> bool:
    if detection.strip_mode != "partial" or not _candidate_gate_allows_selection(detection):
        return False
    gate = _candidate_assessment(detection).get("candidate_gate", {})
    paths = gate.get("proof_paths", []) if isinstance(gate, dict) else []
    return any(
        isinstance(path, dict)
        and path.get("code") == "partial_occupancy_led"
        and path.get("state") == "supported"
        for path in paths
    )


def _candidate_summary(candidate: DetectionCandidate) -> dict:
    assessment = _candidate_assessment(candidate)
    return {
        "format_id": candidate.format_id,
        "count": int(candidate.count),
        "strip_mode": candidate.strip_mode,
        "confidence": float(candidate.confidence),
        "candidate_gate": assessment.get("candidate_gate", {}),
        "failed_checks": list(assessment.get("failed_checks", [])),
        "diagnostics": list(assessment.get("diagnostics", [])),
        "candidate_scores": {
            key: assessment[key]
            for key in (
                "joint_score",
                "geometry_score",
                "separator_score",
                "content_score",
                "content_quality_score",
            )
            if key in assessment
        },
        "candidate_plan": candidate.detail.get("candidate_plan", {}),
        "separator_gap_search": candidate.detail.get("separator_gap_search", {}),
    }


def _box_edge_distance(left: Box, right: Box, scale: float) -> float:
    return max(
        abs(left.left - right.left),
        abs(left.top - right.top),
        abs(left.right - right.right),
        abs(left.bottom - right.bottom),
    ) / max(1.0, scale)


def _geometry_distance(left: DetectionCandidate, right: DetectionCandidate) -> float | None:
    if left.count != right.count or left.strip_mode != right.strip_mode:
        return None
    if len(left.frames) != len(right.frames):
        return None
    long_extent = max(
        left.outer.width if left.layout == "horizontal" else left.outer.height,
        right.outer.width if right.layout == "horizontal" else right.outer.height,
    )
    pitch = float(long_extent) / max(1, left.count)
    distances = [_box_edge_distance(left.outer, right.outer, pitch)]
    distances.extend(
        _box_edge_distance(left_box, right_box, pitch)
        for left_box, right_box in zip(left.frames, right.frames)
    )
    return max(distances, default=0.0)


def _geometry_clusters(
    candidates: list[DetectionCandidate],
    tolerance: float,
) -> list[list[DetectionCandidate]]:
    clusters: list[list[DetectionCandidate]] = []
    for candidate in candidates:
        for cluster in clusters:
            distance = _geometry_distance(candidate, cluster[0])
            if distance is not None and distance <= tolerance:
                cluster.append(candidate)
                break
        else:
            clusters.append([candidate])
    return clusters


def select_detection_candidate(
    candidates: list[DetectionCandidate],
    selection_policy: SelectionConsensusParameters,
) -> DetectionCandidate:
    ranked = sorted(candidates, key=calibrated_candidate_rank, reverse=True)
    best = ranked[0]
    eligible = [candidate for candidate in ranked if _candidate_gate_allows_selection(candidate)]
    consensus_candidates = eligible or [best]
    clusters = _geometry_clusters(
        consensus_candidates,
        selection_policy.geometry_tolerance_ratio,
    )
    selected_cluster = next(cluster for cluster in clusters if best in cluster)
    competing = [cluster[0] for cluster in clusters if cluster is not selected_cluster]
    next_cluster = max(competing, key=calibrated_candidate_rank) if competing else None
    confidence_margin = (
        None
        if next_cluster is None
        else float(best.confidence) - float(next_cluster.confidence)
    )
    geometry_disagreement = bool(
        next_cluster is not None
        and confidence_margin is not None
        and confidence_margin < selection_policy.confidence_tie_margin
    )
    best.detail["selection_geometry_consensus"] = {
        "agreed": not geometry_disagreement,
        "geometry_disagreement": geometry_disagreement,
        "cluster_count": len(clusters),
        "eligible_candidate_count": len(eligible),
        "eligible_cluster_count": len(clusters) if eligible else 0,
        "selected_cluster_size": len(selected_cluster),
        "geometry_tolerance_ratio": float(selection_policy.geometry_tolerance_ratio),
        "confidence_tie_margin": float(selection_policy.confidence_tie_margin),
        "margin_to_competing_cluster": confidence_margin,
        "format_id": best.format_id,
        "top_candidates": [
            {"rank": index, "selected": candidate is best, **_candidate_summary(candidate)}
            for index, candidate in enumerate(ranked[: selection_policy.top_n], start=1)
        ],
        "clusters": [
            {
                "index": index,
                "candidate_count": len(cluster),
                "representative": _candidate_summary(cluster[0]),
            }
            for index, cluster in enumerate(clusters, start=1)
        ],
    }
    return best
