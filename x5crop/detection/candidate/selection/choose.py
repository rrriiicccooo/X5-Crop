from __future__ import annotations

from x5crop.domain import EvidenceState
from ...geometry_resolution import GeometryResolution
from ...physical.model import PhotoSequenceSolution, ReviewOnlyContainment
from ..model import (
    AssessedCandidate,
    CandidateEvidence,
    DualLaneEvidence,
    ReviewOnlyEvidence,
)
from ..plan.model import CountHypothesisSource
from .model import (
    GeometryCluster,
    SelectionConsensus,
    SelectionResult,
)


def candidate_rank(
    candidate: AssessedCandidate,
) -> tuple[int, int, int, int, int, int, int, float, float]:
    quality = candidate.evidence_quality
    residuals = quality.physical_residuals
    partial_auto_count = (
        candidate.geometry.count
        if candidate.geometry.strip_mode == "partial"
        and candidate.count_hypothesis.source == CountHypothesisSource.AUTOMATIC
        else 0
    )
    dimension_residual = (
        residuals.dimension
        if residuals is not None and residuals.dimension is not None
        else float("inf")
    )
    boundary_residual = (
        residuals.boundary_uncertainty
        if residuals is not None
        else float("inf")
    )
    return (
        int(quality.covered_content_px),
        -int(quality.uncovered_content_px),
        -int(quality.internal_boundary_contradiction_count),
        -int(quality.other_contradiction_count),
        len(quality.supported_proof_paths),
        1 if candidate.assessment.gate is not None else 0,
        int(partial_auto_count),
        -float(dimension_residual),
        -float(boundary_residual),
    )


def candidate_dominates(
    left: AssessedCandidate,
    right: AssessedCandidate,
) -> bool:
    left_rank = candidate_rank(left)
    right_rank = candidate_rank(right)
    return bool(
        all(
            left_value >= right_value
            for left_value, right_value in zip(left_rank, right_rank)
        )
        and any(
            left_value > right_value
            for left_value, right_value in zip(left_rank, right_rank)
        )
    )


def geometry_equivalent(
    left: AssessedCandidate,
    right: AssessedCandidate,
) -> bool:
    left_geometry = left.geometry
    right_geometry = right.geometry
    if isinstance(left_geometry, ReviewOnlyContainment) or isinstance(
        right_geometry,
        ReviewOnlyContainment,
    ):
        return bool(
            isinstance(left_geometry, ReviewOnlyContainment)
            and isinstance(right_geometry, ReviewOnlyContainment)
            and left_geometry.count == right_geometry.count
            and left_geometry.strip_mode == right_geometry.strip_mode
            and left_geometry.containment_fallback
            == right_geometry.containment_fallback
        )
    if (
        left_geometry.count != right_geometry.count
        or left_geometry.strip_mode != right_geometry.strip_mode
        or len(left_geometry.photo_apertures) != len(right_geometry.photo_apertures)
    ):
        return False
    if isinstance(left_geometry, PhotoSequenceSolution) and isinstance(
        right_geometry,
        PhotoSequenceSolution,
    ):
        return all(
            all(
                left_edge.position.intersects(right_edge.position)
                for left_edge, right_edge in zip(
                    (
                        left_photo.leading,
                        left_photo.trailing,
                        left_photo.top,
                        left_photo.bottom,
                    ),
                    (
                        right_photo.leading,
                        right_photo.trailing,
                        right_photo.top,
                        right_photo.bottom,
                    ),
                    strict=True,
                )
            )
            for left_photo, right_photo in zip(
                left_geometry.photo_apertures,
                right_geometry.photo_apertures,
                strict=True,
            )
        )
    return left_geometry.photo_apertures == right_geometry.photo_apertures


def geometry_clusters(
    candidates: tuple[AssessedCandidate, ...],
) -> tuple[GeometryCluster, ...]:
    groups: list[list[AssessedCandidate]] = []
    for candidate in candidates:
        for group in groups:
            if all(
                geometry_equivalent(candidate, existing)
                for existing in group
            ):
                group.append(candidate)
                break
        else:
            groups.append([candidate])
    return tuple(
        GeometryCluster(
            candidates=tuple(group),
            representative=max(group, key=candidate_rank),
        )
        for group in groups
    )


def geometry_resolution_for_selection(
    selected: AssessedCandidate,
    *,
    consensus: SelectionConsensus,
    larger_count_hypotheses_resolved: bool,
    candidate_search_budget_exhausted: bool,
) -> GeometryResolution:
    if (
        selected.geometry.search_budget_exhausted
        and not candidate_search_budget_exhausted
    ):
        raise ValueError("candidate search must include selected geometry exhaustion")
    evidence_model = selected.assessment.evidence
    if isinstance(evidence_model, ReviewOnlyEvidence):
        return GeometryResolution(
            count_resolved=False,
            placement_resolved=False,
            boundaries_resolved=False,
            content_preservation_compatible=False,
            larger_count_hypotheses_resolved=(
                larger_count_hypotheses_resolved
            ),
            alternative_geometries_resolved=(
                consensus != SelectionConsensus.DISAGREED
            ),
            assignment_geometry_resolved=False,
            search_budget_exhausted=candidate_search_budget_exhausted,
        )
    evidence_sets = (
        evidence_model.lane_evidence
        if isinstance(evidence_model, DualLaneEvidence)
        else (evidence_model,)
    )
    if not all(isinstance(item, CandidateEvidence) for item in evidence_sets):
        raise TypeError("physical selection requires physical candidate evidence")
    evidence = tuple(
        item for item in evidence_sets if isinstance(item, CandidateEvidence)
    )
    hypothesis = selected.count_hypothesis
    gate = selected.assessment.gate
    if gate is None:
        raise ValueError("physical selection requires CandidateGate")
    proof_path_supported = any(
        path.state == EvidenceState.SUPPORTED
        for path in gate.proof_paths
    )
    fixed_count = bool(
        hypothesis.source
        in {CountHypothesisSource.FORMAT_DEFAULT, CountHypothesisSource.REQUESTED}
    )
    assignment_geometry_resolved = (
        selected.geometry.assignment_consensus.state == EvidenceState.SUPPORTED
    )
    automatic_count_supported = bool(
        all(
            item.photo_aperture_coverage.state == EvidenceState.SUPPORTED
            for item in evidence
        )
        and all(
            item.frame_dimensions.state == EvidenceState.SUPPORTED
            for item in evidence
        )
        and all(
            item.content_preservation_state == EvidenceState.SUPPORTED
            for item in evidence
        )
        and proof_path_supported
        and assignment_geometry_resolved
        and not candidate_search_budget_exhausted
    )
    count_resolved = bool(
        fixed_count or automatic_count_supported
    )
    aperture_boundaries_resolved = bool(
        selected.geometry.photo_apertures
        and all(
            aperture.all_boundaries_supported
            for aperture in selected.geometry.photo_apertures
        )
    )
    placement_resolved = bool(
        count_resolved
        and len(selected.geometry.photo_apertures) == selected.geometry.count
        and all(
            envelope.box.valid()
            for envelope in selected.geometry.frame_crop_envelopes
        )
        and aperture_boundaries_resolved
        and proof_path_supported
        and assignment_geometry_resolved
        and not candidate_search_budget_exhausted
    )
    boundaries_resolved = aperture_boundaries_resolved
    content_preservation_compatible = bool(
        all(
            item.photo_aperture_coverage.state != EvidenceState.CONTRADICTED
            for item in evidence
        )
        and all(
            item.content_preservation_state != EvidenceState.CONTRADICTED
            for item in evidence
        )
    )
    alternative_geometries_resolved = (
        consensus != SelectionConsensus.DISAGREED
    )
    return GeometryResolution(
        count_resolved=count_resolved,
        placement_resolved=placement_resolved,
        boundaries_resolved=boundaries_resolved,
        content_preservation_compatible=content_preservation_compatible,
        larger_count_hypotheses_resolved=larger_count_hypotheses_resolved,
        alternative_geometries_resolved=alternative_geometries_resolved,
        assignment_geometry_resolved=assignment_geometry_resolved,
        search_budget_exhausted=candidate_search_budget_exhausted,
    )


def select_candidates(
    candidates: tuple[AssessedCandidate, ...],
    *,
    larger_count_hypotheses_resolved: bool,
    candidate_search_budget_exhausted: bool,
) -> SelectionResult:
    if not candidates:
        raise ValueError("candidate selection requires at least one candidate")
    ranked = tuple(sorted(candidates, key=candidate_rank, reverse=True))
    clusters = geometry_clusters(ranked)
    selected = ranked[0]
    selected_cluster = next(
        cluster
        for cluster in clusters
        if any(candidate is selected for candidate in cluster.candidates)
    )
    competing = tuple(
        cluster for cluster in clusters if cluster is not selected_cluster
    )
    unresolved_competitors = tuple(
        cluster
        for cluster in competing
        if not candidate_dominates(selected, cluster.representative)
    )
    disagreement = bool(unresolved_competitors)
    if disagreement:
        consensus = SelectionConsensus.DISAGREED
    elif len(selected_cluster.candidates) > 1:
        consensus = SelectionConsensus.AGREED
    else:
        consensus = SelectionConsensus.UNCONTESTED
    resolution = geometry_resolution_for_selection(
        selected,
        consensus=consensus,
        larger_count_hypotheses_resolved=larger_count_hypotheses_resolved,
        candidate_search_budget_exhausted=candidate_search_budget_exhausted,
    )
    return SelectionResult(
        selected=selected,
        ranked_candidates=ranked,
        clusters=clusters,
        consensus=consensus,
        geometry_resolution=resolution,
    )
