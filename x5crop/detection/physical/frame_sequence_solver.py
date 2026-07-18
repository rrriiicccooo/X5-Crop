from __future__ import annotations

from ...domain import (
    BoundaryAxis,
    EvidenceState,
    FrameDimensionPrior,
    FrameSequenceSearchScope,
    PhysicalSearchFact,
    PhysicalSearchOutcome,
)
from ...image.content import ContentRegionObservation
from ...strip_modes import FULL, PARTIAL
from . import frame_sequence_candidate_resolution as candidate_resolution
from . import frame_sequence_candidates as sequence_candidates
from . import frame_sequence_consensus as sequence_consensus
from . import frame_sequence_construction as construction
from . import frame_sequence_result as sequence_result
from . import frame_sequence_separator_assignment as separator_assignment
from . import sequence_completion
from .frame_dimensions import MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS
from .model import AssignmentConsensusOutcome, BoundaryAssignmentConsensus
from .short_axis import SharedShortAxisPlan, frame_width_search_hint


def solve_frame_sequence(
    search_index: construction.FrameSequenceSearchIndex,
    search_scope: FrameSequenceSearchScope,
    short_axis_plan: SharedShortAxisPlan,
    count: int,
    dimensions: FrameDimensionPrior,
    visible_content: ContentRegionObservation,
    maximum_assignment_evaluations: int,
    *,
    strip_mode: str,
    nominal_count: int,
) -> sequence_result.FrameSequenceSolveResult | sequence_result.FrameSequenceSolveFailure:
    if count <= 0:
        raise ValueError("frame sequence count must be positive")
    if strip_mode not in {FULL, PARTIAL} or nominal_count <= 0:
        raise ValueError("frame sequence solver requires mode and nominal count")
    if maximum_assignment_evaluations <= 0:
        raise ValueError("frame sequence solver budget must be positive")
    supports = search_index.separator_supports.canonical_supports
    shared_short_axis = short_axis_plan.span
    if not shared_short_axis.supports_safe_crop:
        return sequence_result.FrameSequenceSolveFailure(short_axis_plan.search_outcome, 0)
    if supports and any(
        support.measurement.short_axis_span
        != shared_short_axis.measurement_span
        for support in supports
    ):
        raise ValueError(
            "frame sequence solver requires measurements on its shared short axis"
        )
    sequence_completion_search_enabled = bool(
        strip_mode == FULL
        and count == nominal_count
        and count > MINIMUM_COMMON_FRAME_WIDTH_OBSERVATIONS
    )
    direct_builds, direct_evaluations, direct_exhausted = (
        construction.sequence_builds_for_count(
            search_index,
            search_scope,
            shared_short_axis,
            short_axis_plan.photo_height_evidence,
            count,
            dimensions,
            visible_content,
            maximum_assignment_evaluations,
            allow_nominal_slot_sized_gap=False,
        )
    )
    holder_boundaries = candidate_resolution.holder_boundaries(search_scope)
    direct_geometry_complete_before_inference = (
        sequence_completion.direct_nominal_geometry_is_complete(
            direct_builds,
            visible_content,
            holder_boundaries,
            short_axis_plan.photo_height_evidence,
            dimensions,
        )
    )
    if (
        sequence_completion_search_enabled
        and not direct_exhausted
        and not direct_geometry_complete_before_inference
    ):
        direct_builds = tuple(
            sequence_completion.infer_unique_slot_in_direct_nominal_build(
                build,
                visible_content,
                search_scope,
                short_axis_plan.photo_height_evidence,
                dimensions,
            )
            for build in direct_builds
        )
    direct_separator_sequence_complete = any(
        len(build.separator_bindings) == count - 1
        for build in direct_builds
    )
    direct_nominal_geometry_resolved = (
        sequence_completion.direct_nominal_geometry_is_complete(
            direct_builds,
            visible_content,
            holder_boundaries,
            short_axis_plan.photo_height_evidence,
            dimensions,
        )
    )
    direct_common_width_supported = (
        sequence_completion.preferred_direct_common_width_is_supported(
            direct_builds,
            visible_content,
            holder_boundaries,
            short_axis_plan.photo_height_evidence,
            dimensions,
        )
    )
    completion_builds: tuple[sequence_candidates.SequenceBuild, ...] = ()
    completion_evaluations = 0
    completion_exhausted = False
    if (
        sequence_completion_search_enabled
        and direct_common_width_supported
        and not direct_separator_sequence_complete
        and not direct_nominal_geometry_resolved
    ):
        remaining_evaluations = maximum_assignment_evaluations - direct_evaluations
        if direct_exhausted or remaining_evaluations <= 0:
            completion_exhausted = True
        else:
            (
                real_frame_builds,
                completion_evaluations,
                completion_exhausted,
            ) = (
                construction.sequence_builds_for_count(
                    search_index,
                    search_scope,
                    shared_short_axis,
                    short_axis_plan.photo_height_evidence,
                    count - 1,
                    dimensions,
                    visible_content,
                    remaining_evaluations,
                    allow_nominal_slot_sized_gap=True,
                )
            )
            completion_builds = sequence_completion.sequence_completed_builds(
                real_frame_builds,
                search_scope,
                short_axis_plan.photo_height_evidence,
                dimensions,
            )
    direct_selection_builds = direct_builds
    if completion_builds:
        strongest_completion_separator_count = max(
            build.objectives.supported_separator_count
            for build in completion_builds
        )
        direct_selection_builds = tuple(
            build
            for build in direct_builds
            if (
                not sequence_completion.build_has_geometry_only_slot(build)
                and (
                    build.objectives.supported_separator_count
                    > strongest_completion_separator_count
                    or sequence_completion.build_supports_resolved_nominal_slots(
                        build,
                        holder_boundaries,
                        short_axis_plan.photo_height_evidence,
                        dimensions,
                    )
                )
            )
        )
    builds = tuple(
        build
        for build in (*direct_selection_builds, *completion_builds)
        if sequence_completion.build_does_not_contradict_common_width(
            build,
            holder_boundaries,
            short_axis_plan.photo_height_evidence,
            dimensions,
        )
        and (
            strip_mode != FULL
            or any(slot.sequence_inferred for slot in build.slots)
            or sequence_completion.build_satisfies_full_endpoint_extent(
                build,
                holder_boundaries,
                short_axis_plan.photo_height_evidence,
                dimensions,
            )
        )
    )
    total_evaluations = direct_evaluations + completion_evaluations
    budget_exhausted = bool(
        short_axis_plan.search_outcome.budget_exhausted
        or direct_exhausted
        or completion_exhausted
    )
    if not builds:
        return sequence_result.FrameSequenceSolveFailure(
            PhysicalSearchOutcome(
                (
                    PhysicalSearchFact.EXECUTION_BUDGET_EXHAUSTED
                    if budget_exhausted
                    else PhysicalSearchFact.CONSTRAINTS_CONTRADICTED,
                ),
            ),
            total_evaluations,
        )

    interior_supports = construction.interior_separator_supports(supports, search_scope)
    holder_path_ids = {
        path.provenance.observation_id
        for boundary in holder_boundaries.values()
        for path in boundary.supporting_paths
    }
    interior_paths = tuple(
        path
        for path in construction.axis_paths(search_scope, BoundaryAxis.LONG)
        if path.provenance.observation_id not in holder_path_ids
    )
    resolved_builds = []
    for build in builds:
        resolved, common_width = candidate_resolution.resolve_build_physical_boundaries(
            build,
            holder_boundaries,
            short_axis_plan.photo_height_evidence,
            dimensions,
        )
        assigned = separator_assignment.assign_unique_separator_observations(
            resolved,
            common_width,
            interior_supports,
        )
        assigned = candidate_resolution.assign_unique_boundary_path_observations(
            assigned,
            common_width,
            interior_paths,
        )
        if assigned != resolved:
            resolved, common_width = candidate_resolution.resolve_build_physical_boundaries(
                assigned,
                holder_boundaries,
                short_axis_plan.photo_height_evidence,
                dimensions,
            )
        resolved_builds.append((resolved, common_width))
    resolved_builds = tuple(resolved_builds)
    resolved_builds = tuple(
        item
        for item in resolved_builds
        if sequence_candidates.frame_slots_are_strictly_monotonic(item[0].slots)
    )
    if not resolved_builds:
        return sequence_result.FrameSequenceSolveFailure(
            PhysicalSearchOutcome(
                (
                    PhysicalSearchFact.EXECUTION_BUDGET_EXHAUSTED
                    if budget_exhausted
                    else PhysicalSearchFact.CONSTRAINTS_CONTRADICTED,
                ),
            ),
            total_evaluations,
        )
    builds = tuple(build for build, _common_width in resolved_builds)
    content_preserving_builds = tuple(
        build
        for build in builds
        if sequence_candidates.build_preserves_visible_content(build, visible_content)
    )
    if content_preserving_builds:
        builds = content_preserving_builds

    best = sequence_candidates.physically_preferred_builds(builds)
    assignment_consensus = (
        BoundaryAssignmentConsensus(
            AssignmentConsensusOutcome.COMPONENT_UNRESOLVED,
            len(best),
            (),
        )
        if budget_exhausted
        else sequence_consensus.sequence_assignment_consensus(best)
    )
    representative = sequence_candidates.representative_build(best)
    holder_boundaries = candidate_resolution.holder_boundaries(search_scope)
    representative, common_width = candidate_resolution.resolve_build_physical_boundaries(
        representative,
        holder_boundaries,
        short_axis_plan.photo_height_evidence,
        dimensions,
    )
    if not sequence_candidates.frame_slots_are_strictly_monotonic(representative.slots):
        return sequence_result.FrameSequenceSolveFailure(
            PhysicalSearchOutcome((PhysicalSearchFact.CONSTRAINTS_CONTRADICTED,)),
            total_evaluations,
        )
    slots, long_axis_assignments = sequence_completion.apply_edge_occlusion_inference(
        representative.slots,
        representative.long_axis_assignments,
        holder_boundaries,
        common_width,
        strip_mode,
    )
    internal_geometry = (
        sequence_consensus.apply_internal_geometry_uncertainty(
            slots,
            long_axis_assignments,
            best,
        )
        if assignment_consensus.state == EvidenceState.SUPPORTED
        else (slots, long_axis_assignments)
    )
    if internal_geometry is None:
        return sequence_result.FrameSequenceSolveFailure(
            PhysicalSearchOutcome((PhysicalSearchFact.CONSTRAINTS_CONTRADICTED,)),
            total_evaluations,
        )
    slots, long_axis_assignments = internal_geometry
    external_safety_geometry = sequence_consensus.apply_external_safety_envelope(
        slots,
        long_axis_assignments,
        best,
        assignment_consensus,
        search_scope.holder_safety.safe_axis_interval(BoundaryAxis.LONG),
    )
    if external_safety_geometry is None:
        return sequence_result.FrameSequenceSolveFailure(
            PhysicalSearchOutcome((PhysicalSearchFact.CONSTRAINTS_CONTRADICTED,)),
            total_evaluations,
        )
    slots, long_axis_assignments = external_safety_geometry
    if not sequence_candidates.frame_slots_are_strictly_monotonic(slots):
        return sequence_result.FrameSequenceSolveFailure(
            PhysicalSearchOutcome((PhysicalSearchFact.CONSTRAINTS_CONTRADICTED,)),
            total_evaluations,
        )
    slots = sequence_completion.annotate_frame_content_occupancy(
        slots,
        visible_content,
    )
    separator_assignments = separator_assignment.separator_assignments_from_bindings(
        representative.separator_bindings,
        slots,
        common_width,
    )
    inter_frame_spacings = sequence_result.final_inter_frame_spacings(
        slots,
        separator_assignments,
        common_width,
    )
    indexed_anchor_constraints = sequence_result.indexed_anchor_distance_constraints(
        separator_assignments,
        inter_frame_spacings,
        representative.frame_width_px,
    )
    return sequence_result.FrameSequenceSolveResult(
        shared_short_axis=representative.short_axis,
        photo_height_evidence=short_axis_plan.photo_height_evidence,
        frame_width_search_hint=frame_width_search_hint(
            representative.short_axis,
            dimensions,
        ),
        holder_span_scale_hint=construction.holder_span_scale_hint(search_scope, count),
        content_extent_constraint=sequence_result.content_extent_constraint(visible_content),
        indexed_anchor_distance_constraints=indexed_anchor_constraints,
        frame_slots=slots,
        long_axis_assignments=long_axis_assignments,
        separator_assignments=separator_assignments,
        inter_frame_spacings=inter_frame_spacings,
        common_frame_width=common_width,
        residuals=representative.residuals,
        assignment_consensus=assignment_consensus,
        search_outcome=PhysicalSearchOutcome(
            (
                PhysicalSearchFact.SOLUTION_FOUND,
                *(
                    (PhysicalSearchFact.EXECUTION_BUDGET_EXHAUSTED,)
                    if budget_exhausted
                    else ()
                ),
            ),
        ),
        assignment_evaluations=total_evaluations,
    )
