from __future__ import annotations

from dataclasses import dataclass

from ....cache import MeasurementCache
from ....cache.separator import cached_separator_profile
from ....configuration.candidate import SequenceSolverParameters
from ....configuration.separator import SeparatorConfiguration
from ....domain import (
    BoundarySide,
    Box,
    FrameDimensionPrior,
    PhotoSequenceSearchScope,
)
from ....formats import FormatPhysicalSpec
from ...context import DetectionRequest
from ...physical.model import PhotoSequenceSolution
from ...physical.separator.observations import (
    measure_separator_cross_axis_support,
    propose_separator_bands,
)
from ...physical.sequence_solver import (
    PhotoSequenceSolveUnavailableReason,
    PhotoSequenceSolveUnavailable,
    photo_aperture_cross_axis_plan,
    solve_photo_sequence,
)
from ..model import BuiltCandidate
from ..plan.count_hypotheses import CountHypothesis


@dataclass(frozen=True)
class SequenceCandidateBuildOutcome:
    candidate: BuiltCandidate | None
    unavailable: PhotoSequenceSolveUnavailable | None
    assignment_evaluations: int

    def __post_init__(self) -> None:
        if (self.candidate is None) == (self.unavailable is None):
            raise ValueError("candidate build outcome requires exactly one result")
        if self.assignment_evaluations < 0:
            raise ValueError("candidate build assignment evaluations cannot be negative")


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
        solver_parameters.maximum_dimension_hypotheses,
    )
    if not cross_axis_plan.hypotheses:
        unavailable = PhotoSequenceSolveUnavailable(
            PhotoSequenceSolveUnavailableReason.GEOMETRY_CONSTRAINTS,
            cross_axis_plan.assignment_evaluations,
        )
        return SequenceCandidateBuildOutcome(
            None,
            unavailable,
            unavailable.assignment_evaluations,
        )
    observation_set = measure_separator_cross_axis_support(
        proposed,
        gray_work=cache.gray_work,
        corridor=corridor,
        statistics=cache.image_statistics,
        parameters=separator_configuration.observation,
        cross_axis_hypotheses=cross_axis_plan.hypotheses,
    )
    solved = solve_photo_sequence(
        observation_set.observations,
        search_scope,
        cross_axis_plan,
        int(count_hypothesis.count),
        dimensions,
        solver_parameters.maximum_assignment_evaluations,
        solver_parameters.maximum_solution_alternatives,
    )
    if isinstance(solved, PhotoSequenceSolveUnavailable):
        return SequenceCandidateBuildOutcome(
            None,
            solved,
            solved.assignment_evaluations,
        )
    geometry = PhotoSequenceSolution(
        format_id=fmt.format_id,
        layout=request.layout,
        strip_mode=count_hypothesis.strip_mode,
        count=int(count_hypothesis.count),
        holder_span=search_scope.holder_span,
        photo_apertures=solved.photo_apertures,
        aperture_edge_assignments=solved.aperture_edge_assignments,
        separator_observations=observation_set.observations,
        separator_assignments=solved.separator_assignments,
        inter_photo_spacings=solved.inter_photo_spacings,
        frame_dimension_prior=dimensions,
        photo_width_constraint_px=solved.photo_width_constraint_px,
        photo_height_constraint_px=solved.photo_height_constraint_px,
        residuals=solved.residuals,
        assignment_consensus=solved.assignment_consensus,
        search_budget_exhausted=bool(
            observation_set.budget_exhausted
            or solved.search_budget_exhausted
        ),
        automatic_processing_supported=True,
        sequence_provenance=search_scope.provenance,
        raw_boundary_paths=search_scope.raw_boundary_paths,
        holder_boundaries=search_scope.holder_boundaries,
    )
    return SequenceCandidateBuildOutcome(
        BuiltCandidate(
            geometry=geometry,
            count_hypothesis=count_hypothesis,
            build_diagnostics=(),
        ),
        None,
        solved.assignment_evaluations,
    )
