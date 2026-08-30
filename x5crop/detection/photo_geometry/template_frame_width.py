"""Consume one source-level common-Frame-width authority after closure."""

from __future__ import annotations

from dataclasses import replace

from ...domain import EvidenceState, FiniteInterval, ObservationId
from .observation_types import BoundaryEdgeObservation
from .source_geometry import SourceScanGeometry
from .template_model import (
    FrameWidthInferenceAssessment,
    FrameWidthInferenceFailureKind,
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


def apply_correlated_frame_width_inference(
    fit: SequenceFit,
    *,
    frame_width_observation_ids: tuple[ObservationId, ...],
) -> SequenceFit:
    """Infer multiple opposite roles from one shared W after topology closes.

    The caller must already have closed placement, local topology, global
    lattice authority, adjacency coverage, and both outer Frames.  This owner
    never binds an inferred role, changes a direct native coordinate, or
    creates a Frame whose START and END are both unobserved.
    """

    if fit.frame_width_inference is not None:
        raise ValueError("Frame width inference was already assessed")
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
    supporting_ordinals = _supporting_frame_ordinals(
        fit,
        frame_width_observation_ids,
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
    )
    return replace(
        fit,
        frame_width_inference=assessment,
    )


__all__ = [
    "apply_correlated_frame_width_inference",
    "calibrate_source_frame_width",
]
