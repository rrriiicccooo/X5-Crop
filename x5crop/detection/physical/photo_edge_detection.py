from __future__ import annotations

import math

import numpy as np

from ...configuration.photo_edges import PhotoEdgeDetectionParameters
from ...domain import (
    EvidenceState,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
)
from ...formats import FrameSizeMm
from ..evidence.photo_edges import (
    PhotoEdgeCoordinateSpace,
    PhotoEdgeFact,
    PhotoEdgeMeasurementSummary,
    PhotoEdgePairEvidence,
    PhotoEdgePhysicalLabel,
    PhotoEdgePhysicalSelection,
    PhotoEdgeSearchCorridor,
    ordered_photo_edge_facts,
)
from ..evidence.scan_canvas import ScanCanvasEvidence, ScanCanvasOutcome
from .photo_edge_geometry import (
    PhotoEdgeGeometryResult,
    solve_fixed_canvas_photo_edge_geometry,
    solve_image_only_lane_geometry,
)
from .photo_edge_observation import observe_photo_edge_fragments


_PHOTO_EDGE_SIDE_COUNT = 2


def photo_edge_search_corridors(
    scan_canvas: ScanCanvasEvidence,
    frame_size_options: tuple[FrameSizeMm, ...],
    parameters: PhotoEdgeDetectionParameters,
) -> tuple[PhotoEdgeSearchCorridor, ...]:
    if scan_canvas.outcome != ScanCanvasOutcome.SUPPORTED:
        return ()
    profile = scan_canvas.selected_profile
    scale = scan_canvas.pixel_scale
    assert profile is not None and scale is not None
    base_depth = max(
        parameters.local_window_min_px,
        int(
            round(
                scan_canvas.observed_short_axis_px
                * parameters.local_window_height_ratio
            )
        ),
    )
    maximum_depth = max(
        parameters.local_window_min_px,
        int(round(base_depth * max(parameters.multiscale_factors))),
    )
    corridors: list[PhotoEdgeSearchCorridor] = []
    for frame_size in frame_size_options:
        photo_height_px = (
            frame_size.height_mm * scale.short_axis_px_per_mm
        )
        nominal_top = 0.5 * (
            float(scan_canvas.observed_short_axis_px - 1)
            - photo_height_px
        )
        nominal_bottom = nominal_top + photo_height_px
        corridor_id = (
            f"{profile.profile_id}:"
            f"{frame_size.width_mm:g}x{frame_size.height_mm:g}"
        )
        corridors.append(
            PhotoEdgeSearchCorridor(
                physical_label=PhotoEdgePhysicalLabel(
                    scan_canvas_profile_id=profile.profile_id,
                    source_corridor_id=corridor_id,
                    frame_size_mm=frame_size,
                ),
                work_long_axis_px=scan_canvas.observed_long_axis_px,
                work_short_axis_px=scan_canvas.observed_short_axis_px,
                nominal_top_px=nominal_top,
                nominal_bottom_px=nominal_bottom,
                maximum_center_offset_px=(
                    parameters.maximum_center_offset_mm
                    * scale.short_axis_px_per_mm
                ),
                maximum_dimension_deviation_px=(
                    parameters.maximum_photo_dimension_deviation_mm
                    * scale.short_axis_px_per_mm
                ),
                maximum_search_angle_degrees=(
                    parameters.maximum_search_angle_degrees
                ),
                measurement_halo_short_px=maximum_depth + 1,
                measurement_halo_long_px=max(
                    1,
                    math.ceil(0.5 * parameters.long_support_width_px),
                ),
            )
        )
    return tuple(corridors)


def _empty_measurement_summary(
    parameters: PhotoEdgeDetectionParameters,
) -> PhotoEdgeMeasurementSummary:
    return PhotoEdgeMeasurementSummary(
        raw_anchor_count=0,
        supported_transition_count=0,
        neutral_anchor_count=0,
        censored_component_count=0,
        merged_duplicate_count=0,
        fragment_count=0,
        canonical_observation_count=0,
        chunk_size_px=parameters.chunk_size_px,
        peak_temporary_buffer_bytes=0,
    )


def _unobserved_evidence(
    scan_canvas: ScanCanvasEvidence,
    parameters: PhotoEdgeDetectionParameters,
    *,
    source_sha256: str,
    observation_id: str,
) -> PhotoEdgePairEvidence:
    state = (
        EvidenceState.CONTRADICTED
        if scan_canvas.outcome == ScanCanvasOutcome.ASPECT_CONTRADICTED
        else EvidenceState.UNAVAILABLE
    )
    fact = (
        PhotoEdgeFact.PAIR_GEOMETRY_CONTRADICTED
        if state == EvidenceState.CONTRADICTED
        else PhotoEdgeFact.PAIR_GEOMETRY_UNAVAILABLE
    )
    provenance = MeasurementProvenance(
        root_measurement=MeasurementIdentity.PHOTO_EDGES,
        observation_id=ObservationId(observation_id),
        dependencies=(
            MeasurementIdentity.SCAN_CANVAS_GEOMETRY,
            MeasurementIdentity.FORMAT_PHYSICAL_SPEC,
        ),
        description="photo-edge observation stopped by scan-canvas evidence",
    )
    return PhotoEdgePairEvidence(
        source_sha256=source_sha256,
        search_corridors=(),
        measurement_summary=_empty_measurement_summary(parameters),
        fragment_summaries=(),
        audit_observations=(),
        hypotheses=(),
        selected_pair_id=None,
        physical_selection=None,
        state=state,
        facts=(fact,),
        coordinate_space=PhotoEdgeCoordinateSpace.SOURCE,
        provenance=provenance,
    )


def _classify_photo_edge_geometry(
    geometry: PhotoEdgeGeometryResult,
    canonical_observation_count: int,
    parameters: PhotoEdgeDetectionParameters,
) -> tuple[
    EvidenceState,
    tuple[PhotoEdgeFact, ...],
    ObservationId | None,
    PhotoEdgePhysicalSelection | None,
]:
    non_contradicted = tuple(
        hypothesis
        for hypothesis in geometry.hypotheses
        if hypothesis.state != EvidenceState.CONTRADICTED
    )
    supported = tuple(
        hypothesis
        for hypothesis in non_contradicted
        if hypothesis.state == EvidenceState.SUPPORTED
    )
    if geometry.budget_exhausted:
        return (
            EvidenceState.UNAVAILABLE,
            (PhotoEdgeFact.PAIR_GEOMETRY_UNAVAILABLE,),
            None,
            None,
        )
    if geometry.search_unavailable:
        return (
            EvidenceState.UNAVAILABLE,
            (PhotoEdgeFact.PAIR_GEOMETRY_UNAVAILABLE,),
            None,
            None,
        )
    if len(non_contradicted) > 1:
        return (
            EvidenceState.UNAVAILABLE,
            (PhotoEdgeFact.COMPETING_PAIRS_UNRESOLVED,),
            None,
            None,
        )
    if len(supported) == 1:
        selected = supported[0]
        return (
            EvidenceState.SUPPORTED,
            (),
            selected.observation_id,
            PhotoEdgePhysicalSelection.from_label(
                selected.physical_labels[0]
            ),
        )
    if len(non_contradicted) == 1:
        return (
            EvidenceState.UNAVAILABLE,
            (
                non_contradicted[0].facts
                or (PhotoEdgeFact.PAIR_GEOMETRY_UNAVAILABLE,)
            ),
            None,
            None,
        )
    if canonical_observation_count < (
        _PHOTO_EDGE_SIDE_COUNT
        * parameters.minimum_independent_observations
    ):
        return (
            EvidenceState.UNAVAILABLE,
            (PhotoEdgeFact.OBSERVATIONS_UNAVAILABLE,),
            None,
            None,
        )
    return (
        EvidenceState.CONTRADICTED,
        (PhotoEdgeFact.PAIR_GEOMETRY_CONTRADICTED,),
        None,
        None,
    )


def observe_fixed_canvas_photo_edges(
    gray_work: np.ndarray,
    scan_canvas: ScanCanvasEvidence,
    frame_size_options: tuple[FrameSizeMm, ...],
    parameters: PhotoEdgeDetectionParameters,
    *,
    source_sha256: str,
    observation_id: str = "source_photo_edge_pair_evidence",
) -> PhotoEdgePairEvidence:
    if scan_canvas.outcome != ScanCanvasOutcome.SUPPORTED:
        return _unobserved_evidence(
            scan_canvas,
            parameters,
            source_sha256=source_sha256,
            observation_id=observation_id,
        )
    scale = scan_canvas.pixel_scale
    assert scale is not None
    corridors = photo_edge_search_corridors(
        scan_canvas,
        frame_size_options,
        parameters,
    )
    observed = observe_photo_edge_fragments(
        gray_work,
        corridors,
        parameters,
        source_sha256=source_sha256,
        observation_prefix=observation_id,
    )
    geometry = solve_fixed_canvas_photo_edge_geometry(
        observed.fragments,
        corridors,
        scale,
        parameters,
        observation_prefix=observation_id,
        long_extent_px=gray_work.shape[1],
        short_extent_px=gray_work.shape[0],
    )
    hypotheses = geometry.hypotheses
    state, facts, selected_pair_id, physical_selection = (
        _classify_photo_edge_geometry(
            geometry,
            observed.summary.canonical_observation_count,
            parameters,
        )
    )
    provenance = MeasurementProvenance(
        root_measurement=MeasurementIdentity.PHOTO_EDGES,
        observation_id=ObservationId(observation_id),
        dependencies=(
            MeasurementIdentity.GRAY_WORK,
            MeasurementIdentity.SCAN_CANVAS_GEOMETRY,
            MeasurementIdentity.FORMAT_PHYSICAL_SPEC,
        ),
        description="source cross-region photo-edge pair evidence",
        boundary_anchors=tuple(
            observation.observation_id
            for observation in geometry.audit_observations
        ),
    )
    return PhotoEdgePairEvidence(
        source_sha256=source_sha256,
        search_corridors=corridors,
        measurement_summary=observed.summary,
        fragment_summaries=geometry.fragment_summaries,
        audit_observations=geometry.audit_observations,
        hypotheses=hypotheses,
        selected_pair_id=selected_pair_id,
        physical_selection=physical_selection,
        state=state,
        facts=ordered_photo_edge_facts(set(facts)),
        coordinate_space=PhotoEdgeCoordinateSpace.SOURCE,
        provenance=provenance,
    )


def observe_image_only_lane_photo_edges(
    gray_work: np.ndarray,
    frame_size_mm: FrameSizeMm,
    parameters: PhotoEdgeDetectionParameters,
    *,
    source_sha256: str,
    observation_id: str,
) -> PhotoEdgePairEvidence:
    observed = observe_photo_edge_fragments(
        gray_work,
        (),
        parameters,
        source_sha256=source_sha256,
        observation_prefix=observation_id,
    )
    geometry = solve_image_only_lane_geometry(
        observed.fragments,
        frame_size_mm,
        parameters,
        observation_prefix=observation_id,
        long_extent_px=gray_work.shape[1],
        short_extent_px=gray_work.shape[0],
    )
    hypotheses = geometry.hypotheses
    state, facts, selected_pair_id, physical_selection = (
        _classify_photo_edge_geometry(
            geometry,
            observed.summary.canonical_observation_count,
            parameters,
        )
    )
    provenance = MeasurementProvenance(
        root_measurement=MeasurementIdentity.PHOTO_EDGES,
        observation_id=ObservationId(observation_id),
        dependencies=(
            MeasurementIdentity.GRAY_WORK,
            MeasurementIdentity.FORMAT_PHYSICAL_SPEC,
        ),
        description="source image-only lane photo-edge pair evidence",
        boundary_anchors=tuple(
            observation.observation_id
            for observation in geometry.audit_observations
        ),
    )
    return PhotoEdgePairEvidence(
        source_sha256=source_sha256,
        search_corridors=(),
        measurement_summary=observed.summary,
        fragment_summaries=geometry.fragment_summaries,
        audit_observations=geometry.audit_observations,
        hypotheses=hypotheses,
        selected_pair_id=selected_pair_id,
        physical_selection=physical_selection,
        state=state,
        facts=ordered_photo_edge_facts(set(facts)),
        coordinate_space=PhotoEdgeCoordinateSpace.SOURCE,
        provenance=provenance,
    )
