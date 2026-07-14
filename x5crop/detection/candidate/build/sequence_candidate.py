from __future__ import annotations

from dataclasses import dataclass

from ....cache import MeasurementCache
from ....cache.separator import cached_separator_profile
from ....configuration.candidate import SequenceSolverParameters
from ....configuration.separator import SeparatorConfiguration
from ....domain import (
    BoundarySide,
    Box,
    EvidenceState,
    FrameDimensionPrior,
    PhotoSequenceSearchScope,
    PhysicalSearchFact,
    PhysicalSearchOutcome,
    combined_physical_search_outcome,
)
from ....formats import FormatPhysicalSpec
from ....image.content import ContentRegionObservation
from ...context import DetectionRequest
from ...physical.model import PhotoSequenceSolution
from ...physical.separator.observations import (
    measure_separator_cross_axis_support,
    propose_separator_bands,
)
from ...physical.sequence_solver import (
    PhotoSequenceSolveFailure,
    photo_aperture_cross_axis_plan,
    solve_photo_sequence,
)
from ..model import BuiltCandidate
from ..plan.model import CountHypothesis


@dataclass(frozen=True)
class SequenceCandidateBuildOutcome:
    candidate: BuiltCandidate | None
    physical_search: PhysicalSearchOutcome
    assignment_evaluations: int

    def __post_init__(self) -> None:
        if self.assignment_evaluations < 0:
            raise ValueError("candidate build evaluation count cannot be negative")
        if (
            self.physical_search.state == EvidenceState.CONTRADICTED
            and self.candidate is not None
        ) or (
            self.physical_search.state == EvidenceState.SUPPORTED
            and self.candidate is None
        ):
            raise ValueError(
                "candidate availability must match its physical search outcome"
            )


def _separator_measurement_corridor(
    search_scope: PhotoSequenceSearchScope,
) -> Box:
    holder = search_scope.holder_span.box
    by_side = {item.side: item for item in search_scope.holder_boundaries}
    top = by_side.get(BoundarySide.TOP)
    bottom = by_side.get(BoundarySide.BOTTOM)
    corridor = Box(
        holder.left,
        int(round(top.position.maximum)) if top is not None else holder.top,
        holder.right,
        int(round(bottom.position.minimum)) if bottom is not None else holder.bottom,
    )
    return corridor if corridor.valid() else holder


def build_sequence_candidate(
    request: DetectionRequest,
    fmt: FormatPhysicalSpec,
    count_hypothesis: CountHypothesis,
    search_scope: PhotoSequenceSearchScope,
    dimensions: FrameDimensionPrior,
    visible_content: ContentRegionObservation,
    *,
    cache: MeasurementCache,
    separator_configuration: SeparatorConfiguration,
    solver_parameters: SequenceSolverParameters,
) -> SequenceCandidateBuildOutcome:
    if cache.layout != request.layout:
        raise ValueError("candidate build requires matching measurement cache")
    corridor = _separator_measurement_corridor(search_scope)
    profile = cached_separator_profile(
        cache,
        corridor,
        separator_configuration.profile,
    )
    proposed = propose_separator_bands(
        profile,
        gray_work=cache.gray_work,
        corridor=corridor,
        statistics=cache.image_statistics,
        parameters=separator_configuration.observation,
    )
    cross_axis_plan = photo_aperture_cross_axis_plan(
        search_scope,
        dimensions,
        int(count_hypothesis.count),
        solver_parameters.maximum_dimension_hypotheses,
    )
    if not cross_axis_plan.hypotheses:
        return SequenceCandidateBuildOutcome(
            None,
            cross_axis_plan.search_outcome,
            0,
        )
    support_set = measure_separator_cross_axis_support(
        proposed,
        gray_work=cache.gray_work,
        corridor=corridor,
        statistics=cache.image_statistics,
        parameters=separator_configuration.observation,
        cross_axis_hypotheses=cross_axis_plan.hypotheses,
    )
    solved = solve_photo_sequence(
        support_set.supports,
        search_scope,
        cross_axis_plan,
        int(count_hypothesis.count),
        dimensions,
        visible_content,
        solver_parameters.maximum_assignment_evaluations,
        solver_parameters.maximum_solution_alternatives,
    )
    if isinstance(solved, PhotoSequenceSolveFailure):
        return SequenceCandidateBuildOutcome(
            None,
            solved.search_outcome,
            solved.assignment_evaluations,
        )
    physical_search = solved.search_outcome
    if support_set.budget_exhausted:
        physical_search = combined_physical_search_outcome(
            (
                physical_search,
                PhysicalSearchOutcome(
                    (PhysicalSearchFact.EXECUTION_BUDGET_EXHAUSTED,),
                ),
            )
        )
    geometry = PhotoSequenceSolution(
        format_id=fmt.format_id,
        layout=request.layout,
        strip_mode=count_hypothesis.strip_mode,
        count=int(count_hypothesis.count),
        holder_span=search_scope.holder_span,
        photo_apertures=solved.photo_apertures,
        aperture_edge_assignments=solved.aperture_edge_assignments,
        separator_observations=tuple(
            support.observation for support in support_set.supports
        ),
        separator_assignments=solved.separator_assignments,
        inter_photo_spacings=solved.inter_photo_spacings,
        frame_dimension_prior=dimensions,
        photo_width_constraint_px=solved.photo_width_constraint_px,
        photo_height_constraint_px=solved.photo_height_constraint_px,
        residuals=solved.residuals,
        assignment_consensus=solved.assignment_consensus,
        raw_boundary_paths=search_scope.raw_boundary_paths,
        holder_boundaries=search_scope.holder_boundaries,
    )
    return SequenceCandidateBuildOutcome(
        BuiltCandidate(
            geometry=geometry,
            count_hypothesis=count_hypothesis,
            build_diagnostics=(),
        ),
        physical_search,
        solved.assignment_evaluations,
    )
