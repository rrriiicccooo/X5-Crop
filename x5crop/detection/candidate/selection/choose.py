from __future__ import annotations

from x5crop.domain import EvidenceState, PhysicalSearchOutcome
from ...geometry_resolution import GeometryResolution
from ...physical.model import (
    DualLaneFrameSolution,
    FrameSequenceSolution,
    ReviewOnlyContainment,
)
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


def _sequence_frame_slots_resolved(
    geometry: FrameSequenceSolution,
) -> bool:
    slots = geometry.frame_slots
    if not (
        slots
        and len(slots) == geometry.count
        and all(
            slot.leading.geometry_resolved and slot.trailing.geometry_resolved
            for slot in slots
        )
        and all(envelope.box.valid() for envelope in geometry.frame_crop_envelopes)
    ):
        return False
    if geometry.count == 1:
        slot = slots[0]
        return bool(
            slot.leading.independently_observed
            and slot.trailing.independently_observed
        )
    return geometry.common_frame_width.state == EvidenceState.SUPPORTED


def _candidate_frame_slots_resolved(
    geometry: FrameSequenceSolution | DualLaneFrameSolution,
) -> bool:
    if isinstance(geometry, FrameSequenceSolution):
        return _sequence_frame_slots_resolved(geometry)
    return bool(
        geometry.lane_solutions
        and all(
            _sequence_frame_slots_resolved(lane)
            for lane in geometry.lane_solutions
        )
    )


def candidate_rank(
    candidate: AssessedCandidate,
) -> tuple[int, int, int, int, int, int, float, float]:
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
        1 if quality.uncovered_content_px == 0 else 0,
        -int(quality.uncovered_content_px),
        -int(quality.internal_boundary_contradiction_count),
        -int(quality.other_contradiction_count),
        len(quality.supported_proof_paths),
        int(partial_auto_count),
        -float(dimension_residual),
        -float(boundary_residual),
    )


def candidate_dominates(
    left: AssessedCandidate,
    right: AssessedCandidate,
) -> bool:
    def axes(candidate: AssessedCandidate) -> tuple[int, int, int, int, int, float, float]:
        quality = candidate.evidence_quality
        residuals = quality.physical_residuals
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
        partial_auto_count = (
            candidate.geometry.count
            if candidate.geometry.strip_mode == "partial"
            and candidate.count_hypothesis.source
            == CountHypothesisSource.AUTOMATIC
            else 0
        )
        return (
            -int(quality.uncovered_content_px),
            -int(quality.internal_boundary_contradiction_count),
            -int(quality.other_contradiction_count),
            len(quality.supported_proof_paths),
            int(partial_auto_count),
            -float(dimension_residual),
            -float(boundary_residual),
        )

    left_axes = axes(left)
    right_axes = axes(right)
    return all(
        left_value >= right_value
        for left_value, right_value in zip(left_axes, right_axes, strict=True)
    ) and any(
        left_value > right_value
        for left_value, right_value in zip(left_axes, right_axes, strict=True)
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
            and left_geometry.holder_safety == right_geometry.holder_safety
        )
    if (
        left_geometry.count != right_geometry.count
        or left_geometry.strip_mode != right_geometry.strip_mode
        or len(left_geometry.frame_slots) != len(right_geometry.frame_slots)
    ):
        return False
    if isinstance(left_geometry, FrameSequenceSolution) and isinstance(
        right_geometry,
        FrameSequenceSolution,
    ):
        return bool(
            left_geometry.shared_short_axis.top.intersects(
                right_geometry.shared_short_axis.top
            )
            and left_geometry.shared_short_axis.bottom.intersects(
                right_geometry.shared_short_axis.bottom
            )
            and all(
                left_slot.sequence_inferred == right_slot.sequence_inferred
                and left_slot.visible_long_axis.intersects(
                    right_slot.visible_long_axis
                )
                and left_slot.leading.position.intersects(
                    right_slot.leading.position
                )
                and left_slot.trailing.position.intersects(
                    right_slot.trailing.position
                )
                for left_slot, right_slot in zip(
                    left_geometry.frame_slots,
                    right_geometry.frame_slots,
                    strict=True,
                )
            )
        )
    return left_geometry.frame_slots == right_geometry.frame_slots


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
    larger_count_search_complete: bool,
    physical_search: PhysicalSearchOutcome,
) -> GeometryResolution:
    evidence_model = selected.assessment.evidence
    if isinstance(evidence_model, ReviewOnlyEvidence):
        return GeometryResolution(
            count_resolved=False,
            frame_slots_resolved=False,
            shared_short_axis_safe=False,
            content_preservation_compatible=False,
            larger_count_search_complete=(
                larger_count_search_complete
            ),
            alternative_geometries_resolved=(
                consensus != SelectionConsensus.DISAGREED
            ),
            assignment_consensus_resolved=False,
            physical_search=physical_search,
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
    fixed_count = bool(
        hypothesis.source
        in {CountHypothesisSource.FORMAT_DEFAULT, CountHypothesisSource.REQUESTED}
    )
    assignment_consensus_resolved = (
        selected.geometry.assignment_consensus.state == EvidenceState.SUPPORTED
    )
    frame_slots_resolved = _candidate_frame_slots_resolved(selected.geometry)
    if isinstance(selected.geometry, FrameSequenceSolution):
        shared_short_axis_safe = selected.geometry.shared_short_axis.supports_safe_crop
    elif isinstance(selected.geometry, DualLaneFrameSolution):
        shared_short_axis_safe = all(
            lane.shared_short_axis.supports_safe_crop
            for lane in selected.geometry.lane_solutions
        )
    else:
        shared_short_axis_safe = False
    count_resolved = bool(
        fixed_count
        or (
            frame_slots_resolved
            and assignment_consensus_resolved
            and physical_search.state == EvidenceState.SUPPORTED
        )
    )
    content_preservation_compatible = bool(
        all(
            item.frame_coverage.state != EvidenceState.CONTRADICTED
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
        frame_slots_resolved=frame_slots_resolved,
        shared_short_axis_safe=shared_short_axis_safe,
        content_preservation_compatible=content_preservation_compatible,
        larger_count_search_complete=larger_count_search_complete,
        alternative_geometries_resolved=alternative_geometries_resolved,
        assignment_consensus_resolved=assignment_consensus_resolved,
        physical_search=physical_search,
    )


def select_candidates(
    candidates: tuple[AssessedCandidate, ...],
    *,
    larger_count_search_complete: bool,
    physical_search: PhysicalSearchOutcome,
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
        larger_count_search_complete=larger_count_search_complete,
        physical_search=physical_search,
    )
    return SelectionResult(
        selected=selected,
        ranked_candidates=ranked,
        clusters=clusters,
        consensus=consensus,
        geometry_resolution=resolution,
    )
