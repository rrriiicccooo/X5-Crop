"""Consume one source-level common-Frame-width authority after closure."""

from __future__ import annotations

from dataclasses import replace

from ...domain import EvidenceState, FiniteInterval, ObservationId
from .observation_types import BoundaryEdgeObservation
from .source_geometry import SourceScanGeometry
from .template_direct_role_authority import (
    DirectRoleAuthorityBasis,
    DirectRoleBindingAuthority,
)
from .template_model import (
    FrameWidthInferenceAssessment,
    FrameWidthInferenceFailureKind,
    SequenceBindingUse,
    SequenceFit,
)
from .template_phase_model import PhaseFitResult, PhaseFitStatus


def calibrate_source_frame_width(
    source_geometry: SourceScanGeometry,
    phase: PhaseFitResult,
    sequence_edges: tuple[BoundaryEdgeObservation, ...],
    *,
    holder_span_px: FiniteInterval,
) -> SourceScanGeometry:
    """Narrow source W from every compatible complete direct Frame.

    A uniquely resolved placement establishes ordinal ownership before this
    operation runs.  All complete direct Frames then contribute one retained
    hull, including non-adjacent Frames and their full measurement
    uncertainty.  No dominant subset, median, or catalogue projection may
    overwrite a native direct boundary.
    """

    fit = phase.best
    if phase.status != PhaseFitStatus.RESOLVED or fit is None:
        return source_geometry
    by_id = {item.observation_id: item for item in sequence_edges}
    physical = source_geometry.width_state.extent_projection_px()
    spans: list[
        tuple[FiniteInterval, tuple[ObservationId, ObservationId]]
    ] = []
    for start, end in zip(
        fit.role_bindings[0::2],
        fit.role_bindings[1::2],
        strict=True,
    ):
        if (
            start is None
            or end is None
            or start.independent_support_id == end.independent_support_id
        ):
            continue
        start_edge = by_id[start.observation_id]
        end_edge = by_id[end.observation_id]
        if fit.template.direction > 0:
            measured = FiniteInterval(
                end_edge.full_position_interval_px.minimum
                - start_edge.full_position_interval_px.maximum,
                end_edge.full_position_interval_px.maximum
                - start_edge.full_position_interval_px.minimum,
            )
        else:
            measured = FiniteInterval(
                start_edge.full_position_interval_px.minimum
                - end_edge.full_position_interval_px.maximum,
                start_edge.full_position_interval_px.maximum
                - end_edge.full_position_interval_px.minimum,
            )
        minimum = max(measured.minimum, physical.minimum)
        maximum = min(measured.maximum, physical.maximum)
        if maximum >= minimum:
            spans.append(
                (
                    FiniteInterval(minimum, maximum),
                    (start.observation_id, end.observation_id),
                )
            )
    if len(spans) < 2:
        return source_geometry
    observed = FiniteInterval(
        min(item[0].minimum for item in spans),
        max(item[0].maximum for item in spans),
    )
    full_span_minimum = (
        observed.minimum
        + fit.pitch_fit.pitch_interval_px.minimum
        * max(0, fit.template.count - 1)
    )
    if full_span_minimum > holder_span_px.width * 1.04:
        return source_geometry
    identities = tuple(
        dict.fromkeys(
            identity
            for _interval, pair in spans
            for identity in pair
        )
    )
    width_state = source_geometry.width_state.intersect_observed_extent(
        observed,
        observation_ids=identities,
    )
    return SourceScanGeometry.from_axis_states(
        source_geometry.frame_spec,
        width_state,
        source_geometry.height_state,
    )


def _supporting_frame_ordinals(
    fit: SequenceFit,
    authority_ids: tuple[ObservationId, ...],
) -> tuple[int, ...]:
    registered = set(authority_ids)
    ordinals: list[int] = []
    pairs = zip(
        fit.role_bindings[0::2],
        fit.role_bindings[1::2],
        strict=True,
    )
    for frame_ordinal, (start, end) in enumerate(pairs, start=1):
        if (
            start is None
            or end is None
            or start.independent_support_id == end.independent_support_id
            or start.observation_id not in registered
            or end.observation_id not in registered
        ):
            continue
        ordinals.append(frame_ordinal)
    return tuple(ordinals)


_INDEPENDENT_WIDTH_ROLE_BASES = frozenset(
    {
        DirectRoleAuthorityBasis.SOURCE_WIDE_EDGE,
        DirectRoleAuthorityBasis.CROSS_HEIGHT_UNION,
        DirectRoleAuthorityBasis.SEPARATOR_PAIR,
    }
)


def _predicted_role_interval_from_opposite(
    fit: SequenceFit,
    role_index: int,
) -> FiniteInterval | None:
    opposite_index = role_index + 1 if role_index % 2 == 0 else role_index - 1
    opposite = fit.role_bindings[opposite_index]
    if opposite is None:
        return None
    width = fit.pitch_fit.frame_width_px
    interval = opposite.full_position_interval_px
    if role_index % 2 == 0:
        if fit.template.direction > 0:
            return FiniteInterval(
                interval.minimum - width.maximum,
                interval.maximum - width.minimum,
            )
        return FiniteInterval(
            interval.minimum + width.minimum,
            interval.maximum + width.maximum,
        )
    if fit.template.direction > 0:
        return FiniteInterval(
            interval.minimum + width.minimum,
            interval.maximum + width.maximum,
        )
    return FiniteInterval(
        interval.minimum - width.maximum,
        interval.maximum - width.minimum,
    )


def _overlaps(left: FiniteInterval, right: FiniteInterval) -> bool:
    return not (
        left.maximum < right.minimum or right.maximum < left.minimum
    )


def _yield_local_roles_to_correlated_width(
    fit: SequenceFit,
    direct_role_authority: DirectRoleBindingAuthority | None,
    sequence_edges: tuple[BoundaryEdgeObservation, ...],
    frame_width_observation_ids: tuple[ObservationId, ...],
) -> tuple[
    SequenceFit,
    tuple[int, ...],
    tuple[ObservationId, ...],
    tuple[int, ...],
]:
    """Remove only local weak coordinates that an independent W supersedes."""

    if (
        direct_role_authority is None
        or direct_role_authority.state == EvidenceState.CONTRADICTED
        or not direct_role_authority.unsupported_role_indices
        or not sequence_edges
    ):
        return fit, (), (), ()
    facts = {
        item.role_index: item for item in direct_role_authority.facts
    }
    width_ids = set(frame_width_observation_ids)
    strong_frames: list[int] = []
    strong_observations: set[ObservationId] = set()
    for slot_index in range(fit.template.count):
        start_index = 2 * slot_index
        end_index = start_index + 1
        start = fit.role_bindings[start_index]
        end = fit.role_bindings[end_index]
        start_fact = facts.get(start_index)
        end_fact = facts.get(end_index)
        if (
            start is None
            or end is None
            or start_fact is None
            or end_fact is None
            or start_fact.state != EvidenceState.SUPPORTED
            or end_fact.state != EvidenceState.SUPPORTED
            or not set(start_fact.bases) & _INDEPENDENT_WIDTH_ROLE_BASES
            or not set(end_fact.bases) & _INDEPENDENT_WIDTH_ROLE_BASES
            or start.observation_id not in width_ids
            or end.observation_id not in width_ids
            or start.independent_support_id == end.independent_support_id
        ):
            continue
        strong_frames.append(slot_index + 1)
        strong_observations.update(
            (start.observation_id, end.observation_id)
        )
    if (
        len(strong_frames) < 2
        or len(frame_width_observation_ids) < 4
        or not width_ids.issubset(strong_observations)
    ):
        return fit, (), (), ()

    validation_only_indices: list[int] = []
    validation_ids: list[ObservationId] = []
    for role_index in direct_role_authority.unsupported_role_indices:
        fact = facts[role_index]
        binding = fit.role_bindings[role_index]
        opposite_index = (
            role_index + 1 if role_index % 2 == 0 else role_index - 1
        )
        opposite_fact = facts.get(opposite_index)
        if (
            binding is None
            or binding.use != SequenceBindingUse.LOCAL_REFINEMENT
            or fact.state != EvidenceState.UNAVAILABLE
            or fact.independent_support_region_count != 2
            or opposite_fact is None
            or opposite_fact.state != EvidenceState.SUPPORTED
            or not set(opposite_fact.bases) & _INDEPENDENT_WIDTH_ROLE_BASES
        ):
            continue
        predicted = _predicted_role_interval_from_opposite(fit, role_index)
        if predicted is None:
            continue
        role = fit.template.roles[role_index].role
        compatible = tuple(
            item.observation_id
            for item in sequence_edges
            if role in item.qualified_anchor_roles
            and _overlaps(item.full_position_interval_px, predicted)
        )
        if compatible != (binding.observation_id,):
            continue
        validation_only_indices.append(role_index)
        validation_ids.append(binding.observation_id)
    if not validation_only_indices:
        return fit, (), (), ()
    bindings = list(fit.role_bindings)
    for role_index in validation_only_indices:
        bindings[role_index] = None
    if any(
        start is None and end is None
        for start, end in zip(bindings[0::2], bindings[1::2], strict=True)
    ):
        return fit, (), (), ()
    return (
        replace(
            fit,
            role_bindings=tuple(bindings),
            contradicted_observation_count=(
                fit.contradicted_observation_count
                + len(validation_only_indices)
            ),
        ),
        tuple(validation_only_indices),
        tuple(validation_ids),
        tuple(strong_frames),
    )


def apply_correlated_frame_width_inference(
    fit: SequenceFit,
    *,
    frame_width_observation_ids: tuple[ObservationId, ...],
    direct_role_authority: DirectRoleBindingAuthority | None = None,
    sequence_edges: tuple[BoundaryEdgeObservation, ...] = (),
) -> SequenceFit:
    """Infer opposite roles from one shared W without promoting weak lines.

    A non-authoritative ``LOCAL_REFINEMENT`` may become validation-only when
    every W observation belongs to at least two other complete Frames whose
    edges have unconditional coordinate authority.  The weak observation
    remains typed validation provenance, while the opposite edge plus the
    full correlated W interval owns output geometry.  Phase anchors never
    yield this way.
    """

    if fit.frame_width_inference is not None:
        raise ValueError("Frame width inference was already assessed")
    (
        fit,
        validation_only_indices,
        validation_ids,
        independently_supported_ordinals,
    ) = _yield_local_roles_to_correlated_width(
        fit,
        direct_role_authority,
        sequence_edges,
        frame_width_observation_ids,
    )
    missing = fit.unbound_role_indices
    if not missing:
        return fit
    pairs = tuple(
        zip(
            fit.role_bindings[0::2],
            fit.role_bindings[1::2],
            strict=True,
        )
    )
    if any(start is None and end is None for start, end in pairs):
        return replace(
            fit,
            frame_width_inference=FrameWidthInferenceAssessment(
                state=EvidenceState.UNAVAILABLE,
                inferred_role_indices=missing,
                supporting_frame_ordinals=(),
                width_px=None,
                canonical_width_px=None,
                observation_ids=(),
                failure_kind=(
                    FrameWidthInferenceFailureKind.COMPLETE_FRAME_UNOBSERVED
                ),
            ),
        )
    supporting_ordinals = (
        independently_supported_ordinals
        or _supporting_frame_ordinals(
            fit,
            frame_width_observation_ids,
        )
    )
    if (
        len(frame_width_observation_ids) < 4
        or len(set(frame_width_observation_ids))
        != len(frame_width_observation_ids)
        or len(supporting_ordinals) < 2
    ):
        return replace(
            fit,
            frame_width_inference=FrameWidthInferenceAssessment(
                state=EvidenceState.UNAVAILABLE,
                inferred_role_indices=missing,
                supporting_frame_ordinals=(),
                width_px=None,
                canonical_width_px=None,
                observation_ids=(),
                failure_kind=(
                    FrameWidthInferenceFailureKind.COMMON_WIDTH_AUTHORITY_UNAVAILABLE
                ),
            ),
        )
    assessment = FrameWidthInferenceAssessment(
        state=EvidenceState.SUPPORTED,
        inferred_role_indices=missing,
        supporting_frame_ordinals=supporting_ordinals,
        width_px=fit.pitch_fit.frame_width_px,
        canonical_width_px=fit.pitch_fit.canonical_frame_width_px,
        observation_ids=frame_width_observation_ids,
        failure_kind=None,
        validation_only_role_indices=validation_only_indices,
        validation_observation_ids=validation_ids,
    )
    return replace(
        fit,
        frame_width_inference=assessment,
    )


__all__ = [
    "apply_correlated_frame_width_inference",
    "calibrate_source_frame_width",
]
