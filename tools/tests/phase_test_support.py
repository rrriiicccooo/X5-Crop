"""Shared physical fixtures for sequence phase contract tests."""

from __future__ import annotations

from dataclasses import replace

from tools.tests.template_test_support import (
    phase_edge as edge,
    phase_sequence_measurement,
)
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.observation_types import BoundaryEdgeObservation
from x5crop.detection.photo_geometry.template_model import (
    SequenceBindingUse,
    SourceFrameWidthAuthorityBasis,
    template_role_refinement_radius_px,
)
from x5crop.detection.photo_geometry.template_frame_width import (
    apply_placement_source_frame_width,
    SourceFrameWidthAuthority,
    SourceFrameWidthAuthorityPlacementScope,
)
from x5crop.detection.photo_geometry.template_overlap import observe_overlap_edge_pairs
from x5crop.detection.photo_geometry.template_adjacency_coverage import assess_adjacency_observation_coverage
from x5crop.detection.photo_geometry.template_adjacency_topology import observe_adjacency_continuity
from x5crop.detection.photo_geometry.template_phase_refinement import refine_template_phase_with_source_frame_width
from x5crop.detection.photo_geometry.template_phase import (
    finalize_template_phase_candidate,
    fit_template_phase_candidate_with_adjacency_relations,
)
from x5crop.detection.photo_geometry.template_phase_model import (
    PhaseFitStatus,
    TemplatePhaseInput,
)
from x5crop.domain import EvidenceState, FiniteInterval, ObservationId


def _continuity_for_residual(fit, observations, bands):
    measurement = phase_sequence_measurement(
        "residual",
        FiniteInterval(0.0, 1000.0),
    )
    coverage = assess_adjacency_observation_coverage(
        fit,
        (measurement,),
        directly_observed_ordinals=(),
    )
    overlap_pairs = observe_overlap_edge_pairs(
        tuple(observations),
        tuple(bands),
        (measurement,),
        direction=fit.template.direction,
        maximum_overlap_px=template_role_refinement_radius_px(
            fit.template.pitch_px.maximum
        ),
    )
    return observe_adjacency_continuity(
        fit,
        tuple(observations),
        tuple(bands),
        coverage,
        overlap_pairs,
    )


def _fit_with_independent_source_width(
    phase_input: TemplatePhaseInput,
    observation_ids: tuple[ObservationId, ...],
    supporting_frame_ordinals: tuple[int, ...],
):
    """Run the production placement-bound flow with a typed test W authority."""

    candidate = fit_template_phase_candidate_with_adjacency_relations(
        phase_input
    )
    fit = candidate.result.best
    assert candidate.result.status == PhaseFitStatus.RESOLVED and fit is not None
    authority = SourceFrameWidthAuthority(
        authority_id="test-independent-source-width",
        state=EvidenceState.SUPPORTED,
        placement_scope=(
            SourceFrameWidthAuthorityPlacementScope.RESOLVED_PLACEMENT
        ),
        placement_integer_slot_offset=(
            fit.phase_lattice_fit.integer_slot_offset
        ),
        placement_phase_anchor_observation_ids=tuple(
            binding.observation_id
            if binding is not None
            and binding.use == SequenceBindingUse.PHASE_ANCHOR
            else None
            for binding in fit.role_bindings
        ),
        supporting_role_observation_ids=tuple(
            binding.observation_id
            if binding is not None
            and binding.observation_id in set(observation_ids)
            else None
            for binding in fit.role_bindings
        ),
        basis=SourceFrameWidthAuthorityBasis.INDEPENDENT_COMPLETE_FRAMES,
        supporting_frame_ordinals=supporting_frame_ordinals,
        supporting_constraint_ids=(),
        width_px=FiniteInterval(
            fit.pitch_fit.frame_width_px.minimum,
            fit.pitch_fit.frame_width_px.maximum,
        ),
        canonical_width_px=fit.pitch_fit.canonical_frame_width_px,
        observation_ids=tuple(sorted(observation_ids, key=str)),
        failure_kind=None,
        reason=None,
    )
    selected = apply_placement_source_frame_width(candidate.result, authority)
    selected = refine_template_phase_with_source_frame_width(
        selected,
        authority,
        phase_input.observations,
        phase_input.separator_bands,
        phase_input.sequence_measurement_sets,
    )
    return finalize_template_phase_candidate(
        replace(candidate, result=selected),
        phase_input,
        source_frame_width_authority=authority,
    )


def _phase_candidate_group(
    prefix: str,
    offset_px: float,
    *,
    short: bool = False,
) -> tuple[BoundaryEdgeObservation, ...]:
    values = []
    for index, (coordinate, role) in enumerate(
        (
            (40.0, BoundaryRole.START),
            (140.0, BoundaryRole.END),
            (160.0, BoundaryRole.START),
            (260.0, BoundaryRole.END),
        )
    ):
        observation = replace(
            edge(f"{prefix}:{index}", coordinate + offset_px),
            qualified_anchor_roles=(role,),
            polarity=1 if role == BoundaryRole.START else -1,
        )
        if short:
            observation = replace(
                observation,
                trace_coordinates_px=(10, 20),
                support_fraction=2.0 / 3.0,
                continuous_support_fraction=2.0 / 3.0,
            )
        values.append(observation)
    return tuple(values)


def _local_line(
    name: str,
    coordinate: float,
    role: BoundaryRole,
) -> BoundaryEdgeObservation:
    direction = FiniteInterval.exact(0.0)
    return replace(
        edge(name, coordinate),
        qualified_anchor_roles=(role,),
        canonical_direction_degrees=0.0,
        fit_direction_interval_degrees=direction,
        full_direction_interval_degrees=direction,
        # Exclude this line from global phase fitting while retaining its
        # typed local line evidence.
        fit_residual_px=20.0,
    )
