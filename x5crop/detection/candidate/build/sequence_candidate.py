from __future__ import annotations

from dataclasses import dataclass

from ....cache import MeasurementCache
from ....cache.separator import cached_separator_profile
from ....domain import (
    Box,
    CropEnvelope,
    FrameDimensionPrior,
    HolderSpan,
    SequenceHypothesis,
)
from ....formats import FormatPhysicalSpec
from ....configuration.separator import SeparatorConfiguration
from ....configuration.candidate import SequenceSolverParameters
from ...context import DetectionRequest
from ...physical.model import SequenceSolution
from ...physical.boundary import holder_occlusion_constraint
from ...physical.separator.assignment import boundary_position_constraint
from ...physical.separator.observations import (
    measure_focused_separator_band,
    measure_separator_bands,
)
from ...physical.sequence_solver import (
    SequenceSolveUnavailable,
    solve_frame_sequence,
)
from ..model import BuiltCandidate
from ..plan.count_hypotheses import CountHypothesis


@dataclass(frozen=True)
class SequenceCandidateBuildOutcome:
    candidate: BuiltCandidate | None
    unavailable: SequenceSolveUnavailable | None
    assignment_evaluations: int

    def __post_init__(self) -> None:
        if (self.candidate is None) == (self.unavailable is None):
            raise ValueError("candidate build outcome requires exactly one result")
        if self.assignment_evaluations < 0:
            raise ValueError("candidate build assignment evaluations cannot be negative")


def _separator_measurement_corridor(
    holder_span: HolderSpan,
    crop_envelope: CropEnvelope,
) -> Box:
    holder = holder_span.box
    crop = crop_envelope.box
    corridor = Box(
        holder.left,
        max(holder.top, crop.top),
        holder.right,
        min(holder.bottom, crop.bottom),
    )
    return corridor if corridor.valid() else holder


def build_sequence_candidate(
    request: DetectionRequest,
    fmt: FormatPhysicalSpec,
    count_hypothesis: CountHypothesis,
    sequence_hypothesis: SequenceHypothesis,
    dimensions: FrameDimensionPrior,
    *,
    cache: MeasurementCache,
    separator_configuration: SeparatorConfiguration,
    solver_parameters: SequenceSolverParameters,
    planning_budget_exhausted: bool,
) -> SequenceCandidateBuildOutcome:
    if cache.layout != request.layout:
        raise ValueError("candidate build requires matching measurement cache")
    count = int(count_hypothesis.count)
    height, width = cache.gray_work.shape
    holder_span = HolderSpan(Box(0, 0, width, height))
    visible_sequence_span = sequence_hypothesis.visible_sequence_span
    corridor = _separator_measurement_corridor(
        holder_span,
        sequence_hypothesis.crop_envelope,
    )
    profile = cached_separator_profile(
        cache,
        corridor,
        separator_configuration.profile,
    )
    observation_set = measure_separator_bands(
        profile,
        gray_work=cache.gray_work,
        corridor=corridor,
        statistics=cache.image_statistics,
        parameters=separator_configuration.observation,
    )
    observations = observation_set.observations
    occlusion_constraint = holder_occlusion_constraint(
        sequence_hypothesis.boundary_paths,
        dimensions.width_px,
        cache.image_statistics.edge_texture_limit,
    )
    focused_observations = tuple(
        (boundary_index, observation)
        for boundary_index in range(1, count)
        if (
            observation := measure_focused_separator_band(
                profile,
                boundary_position_constraint(
                    visible_sequence_span,
                    boundary_index,
                    count,
                    dimensions,
                    occlusion_constraint,
                ).position,
                gray_work=cache.gray_work,
                corridor=corridor,
                statistics=cache.image_statistics,
                parameters=separator_configuration.observation,
            )
        )
        is not None
    )
    solved = solve_frame_sequence(
        observations,
        focused_observations,
        visible_sequence_span,
        count,
        dimensions,
        sequence_hypothesis.boundary_paths,
        solver_parameters.maximum_assignment_evaluations,
        edge_texture_limit=cache.image_statistics.edge_texture_limit,
    )
    if isinstance(solved, SequenceSolveUnavailable):
        return SequenceCandidateBuildOutcome(
            None,
            solved,
            solved.assignment_evaluations,
        )
    return SequenceCandidateBuildOutcome(
        BuiltCandidate(
            geometry=SequenceSolution(
                format_id=fmt.format_id,
                layout=request.layout,
                strip_mode=count_hypothesis.strip_mode,
                count=count,
                holder_span=holder_span,
                visible_sequence_span=visible_sequence_span,
                crop_envelope=sequence_hypothesis.crop_envelope,
                photo_intervals=solved.photo_intervals,
                frames=solved.frames,
                separator_observations=observations,
                separator_assignments=solved.assignments,
                frame_boundaries=solved.boundaries,
                inter_frame_spacings=solved.relations,
                holder_occlusion=solved.holder_occlusion,
                frame_dimension_prior=dimensions,
                residuals=solved.residuals,
                assignment_consensus=solved.assignment_consensus,
                search_budget_exhausted=bool(
                    planning_budget_exhausted
                    or observation_set.budget_exhausted
                    or solved.search_budget_exhausted
                ),
                automatic_processing_supported=True,
                sequence_provenance=sequence_hypothesis.provenance,
                boundary_paths=sequence_hypothesis.boundary_paths,
            ),
            count_hypothesis=count_hypothesis,
            build_diagnostics=(),
        ),
        None,
        solved.assignment_evaluations,
    )
