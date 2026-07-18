from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import TYPE_CHECKING

import numpy as np

from ....cache import MeasurementCache
from ....configuration.content import ContentEvidenceParameters
from ....domain import (
    BoundarySide,
    Box,
    EvidenceState,
    PixelInterval,
)
from ....image.evidence import (
    CONTENT_EVIDENCE_NEIGHBORHOOD_RADIUS_PX,
    activation_mask,
)
from .activation import cached_content_evidence_threshold

if TYPE_CHECKING:
    from ..frame_coverage import FrameCoverageEvidence
    from ...physical.model import (
        FrameSequenceSolution,
        FrameSlot,
        SharedShortAxisSafetySpan,
    )

from ...physical.model import FrameBoundarySource


@dataclass(frozen=True)
class ExternalFrameBoundaryObservation:
    frame_index: int
    side: BoundarySide
    boundary_basis: FrameBoundarySource
    inside_region: Box
    outside_region: Box | None
    active_inside_pixels: int
    active_outside_pixels: int
    crossing_track_count: int
    minimum_active_pixels: int
    minimum_crossing_tracks: int
    long_axis_content_spans_boundary: bool
    content_crossing_detected: bool = field(init=False)
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)

    def __post_init__(self) -> None:
        if self.frame_index <= 0:
            raise ValueError("external frame observation requires a frame index")
        if self.side not in {BoundarySide.LEADING, BoundarySide.TRAILING}:
            raise ValueError("external frame preservation only measures long-axis endpoints")
        if not self.inside_region.valid():
            raise ValueError("external frame observation requires an inside region")
        if self.outside_region is not None and not self.outside_region.valid():
            raise ValueError("external frame outside region must have positive extent")
        if min(
            self.active_inside_pixels,
            self.active_outside_pixels,
            self.crossing_track_count,
        ) < 0:
            raise ValueError("external frame measurements must be non-negative")
        if min(self.minimum_active_pixels, self.minimum_crossing_tracks) <= 0:
            raise ValueError("external frame support requirements must be positive")

        crossing_detected = bool(
            self.outside_region is not None
            and self.long_axis_content_spans_boundary
            and self.active_inside_pixels >= self.minimum_active_pixels
            and self.active_outside_pixels >= self.minimum_active_pixels
            and self.crossing_track_count >= self.minimum_crossing_tracks
        )
        if self.outside_region is None:
            state = EvidenceState.NOT_APPLICABLE
            reason = "external_frame_edge_is_canvas_adjacent"
        elif crossing_detected:
            if self.boundary_basis in {
                FrameBoundarySource.DIMENSION_CONSTRAINED,
                FrameBoundarySource.HOLDER_OCCLUSION_INFERENCE,
                FrameBoundarySource.EXTERNAL_SAFETY_ENVELOPE,
                FrameBoundarySource.SEQUENCE_INFERENCE,
            }:
                state = EvidenceState.CONTRADICTED
                reason = "continuous_content_crosses_inferred_frame_boundary"
            else:
                state = EvidenceState.CONTRADICTED
                reason = "continuous_content_crosses_measured_frame_boundary"
        else:
            state = EvidenceState.UNAVAILABLE
            reason = "external_content_crossing_not_corroborated"
        object.__setattr__(self, "content_crossing_detected", crossing_detected)
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "reason", reason)


@dataclass(frozen=True)
class ExternalFramePreservationEvidence:
    workspace_extent: Box
    frame_sequence_envelope: Box
    frame_count: int
    observations: tuple[ExternalFrameBoundaryObservation, ...]
    threshold: float | None
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)

    def __post_init__(self) -> None:
        if self.frame_count <= 0:
            raise ValueError("external frame evidence requires a frame count")
        if not self.workspace_extent.valid():
            raise ValueError("external frame evidence requires a valid workspace")
        if not self.frame_sequence_envelope.valid():
            raise ValueError("external frame evidence requires a valid envelope")
        workspace = self.workspace_extent
        sequence = self.frame_sequence_envelope
        if not (
            workspace.left <= sequence.left < sequence.right <= workspace.right
            and workspace.top <= sequence.top < sequence.bottom <= workspace.bottom
        ):
            raise ValueError("photo sequence envelope must fit the workspace")
        if not self.observations:
            raise ValueError("external frame evidence requires frame observations")
        expected = (
            (1, BoundarySide.LEADING),
            (self.frame_count, BoundarySide.TRAILING),
        )
        observed = tuple(
            (item.frame_index, item.side) for item in self.observations
        )
        if observed != expected:
            raise ValueError(
                "external frame evidence requires only the two sequence endpoints"
            )
        if any(
            item.state == EvidenceState.CONTRADICTED
            for item in self.observations
        ):
            state = EvidenceState.CONTRADICTED
            reason = "visible_content_crosses_external_frame"
        elif all(
            item.state == EvidenceState.NOT_APPLICABLE
            for item in self.observations
        ):
            state = EvidenceState.NOT_APPLICABLE
            reason = "all_external_frame_edges_are_canvas_adjacent"
        else:
            state = EvidenceState.UNAVAILABLE
            reason = (
                "content_evidence_has_no_dynamic_range"
                if self.threshold is None
                else "external_content_crossing_not_observed"
            )
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "reason", reason)


def _boundary_regions(
    frame: FrameSlot,
    short_axis: SharedShortAxisSafetySpan,
    side: BoundarySide,
    band: int,
    workspace: Box,
) -> tuple[Box, Box | None]:
    sequence = frame.crop_envelope(short_axis).box.clamp(
        workspace.right,
        workspace.bottom,
    )

    orthogonal_start = max(
        sequence.top,
        int(math.ceil(short_axis.top.maximum)) + band,
    )
    orthogonal_end = min(
        sequence.bottom,
        int(math.floor(short_axis.bottom.minimum)) - band,
    )
    if orthogonal_end <= orthogonal_start:
        midpoint = max(
            sequence.top,
            min(sequence.bottom - 1, (sequence.top + sequence.bottom) // 2),
        )
        orthogonal_start, orthogonal_end = midpoint, midpoint + 1

    if side == BoundarySide.LEADING:
        inside = Box(
            sequence.left,
            orthogonal_start,
            min(sequence.right, sequence.left + band),
            orthogonal_end,
        )
        outside = (
            None
            if sequence.left <= workspace.left
            else Box(
                max(workspace.left, sequence.left - band),
                orthogonal_start,
                sequence.left,
                orthogonal_end,
            )
        )
    elif side == BoundarySide.TRAILING:
        inside = Box(
            max(sequence.left, sequence.right - band),
            orthogonal_start,
            sequence.right,
            orthogonal_end,
        )
        outside = (
            None
            if sequence.right >= workspace.right
            else Box(
                sequence.right,
                orthogonal_start,
                min(workspace.right, sequence.right + band),
                orthogonal_end,
            )
        )
    else:
        raise ValueError(f"unsupported external frame side: {side}")
    return inside, outside


def _active_region(active: np.ndarray, region: Box) -> np.ndarray:
    return active[region.top : region.bottom, region.left : region.right]


def _crossing_track_count(
    active: np.ndarray,
    inside: Box,
    outside: Box,
    side: BoundarySide,
    boundary_halo_px: int,
) -> int:
    if boundary_halo_px < 0:
        raise ValueError("content crossing boundary halo cannot be negative")
    inside_active = _active_region(active, inside)
    outside_active = _active_region(active, outside)
    sample_offset = int(boundary_halo_px)
    if side == BoundarySide.LEADING:
        if min(inside_active.shape[1], outside_active.shape[1]) <= sample_offset:
            return 0
        inside_tracks = inside_active[:, sample_offset]
        outside_tracks = outside_active[:, -(sample_offset + 1)]
    elif side == BoundarySide.TRAILING:
        if min(inside_active.shape[1], outside_active.shape[1]) <= sample_offset:
            return 0
        inside_tracks = inside_active[:, -(sample_offset + 1)]
        outside_tracks = outside_active[:, sample_offset]
    elif side == BoundarySide.TOP:
        if min(inside_active.shape[0], outside_active.shape[0]) <= sample_offset:
            return 0
        inside_tracks = inside_active[sample_offset, :]
        outside_tracks = outside_active[-(sample_offset + 1), :]
    elif side == BoundarySide.BOTTOM:
        if min(inside_active.shape[0], outside_active.shape[0]) <= sample_offset:
            return 0
        inside_tracks = inside_active[-(sample_offset + 1), :]
        outside_tracks = outside_active[sample_offset, :]
    else:
        raise ValueError(f"unsupported external frame side: {side}")
    track_count = min(inside_tracks.size, outside_tracks.size)
    return int(
        np.count_nonzero(
            inside_tracks[:track_count] & outside_tracks[:track_count]
        )
    )


def _reliable_content_spans_boundary(
    coverage: FrameCoverageEvidence,
    boundary: PixelInterval,
) -> bool:
    uncertainty = int(coverage.content_position_uncertainty_px)
    return any(
        float(start + uncertainty) < boundary.minimum
        and float(end - uncertainty) > boundary.maximum
        for start, end in coverage.content_runs
    )


def external_frame_preservation_evidence(
    geometry: FrameSequenceSolution,
    cache: MeasurementCache,
    parameters: ContentEvidenceParameters,
    coverage: FrameCoverageEvidence,
) -> ExternalFramePreservationEvidence:
    if cache.layout != geometry.layout:
        raise ValueError("external frame evidence requires matching cache layout")
    height, width = cache.content_evidence_float_work.shape
    workspace = Box(0, 0, width, height)
    sequence = geometry.frame_sequence_envelope.clamp(width, height)
    if not sequence.valid():
        raise ValueError("external frame evidence requires valid frame geometry")
    band = max(
        int(parameters.boundary_band_min_px),
        int(round(min(sequence.width, sequence.height) * parameters.boundary_band_ratio)),
    )
    threshold = cached_content_evidence_threshold(cache, workspace, parameters)
    active = (
        np.zeros_like(cache.content_evidence_float_work, dtype=bool)
        if threshold is None
        else activation_mask(cache.content_evidence_float_work, threshold)
    )
    minimum_active = int(parameters.minimum_active_pixels)
    minimum_tracks = max(1, int(math.ceil(math.sqrt(minimum_active))))
    observations: list[ExternalFrameBoundaryObservation] = []
    endpoints = (
        (geometry.frame_slots[0], BoundarySide.LEADING),
        (geometry.frame_slots[-1], BoundarySide.TRAILING),
    )
    for frame, side in endpoints:
        resolution = getattr(frame, side.value)
        inside, outside = _boundary_regions(
            frame,
            geometry.shared_short_axis,
            side,
            band,
            workspace,
        )
        inside_active = _active_region(active, inside)
        outside_active = (
            np.empty((0, 0), dtype=bool)
            if outside is None
            else _active_region(active, outside)
        )
        observations.append(
            ExternalFrameBoundaryObservation(
                frame_index=frame.index,
                side=side,
                boundary_basis=resolution.source,
                inside_region=inside,
                outside_region=outside,
                active_inside_pixels=int(np.count_nonzero(inside_active)),
                active_outside_pixels=int(np.count_nonzero(outside_active)),
                crossing_track_count=(
                    0
                    if outside is None or threshold is None
                    else _crossing_track_count(
                        active,
                        inside,
                        outside,
                        side,
                        CONTENT_EVIDENCE_NEIGHBORHOOD_RADIUS_PX,
                    )
                ),
                minimum_active_pixels=minimum_active,
                minimum_crossing_tracks=minimum_tracks,
                long_axis_content_spans_boundary=(
                    _reliable_content_spans_boundary(
                        coverage,
                        resolution.position,
                    )
                ),
            )
        )
    return ExternalFramePreservationEvidence(
        workspace,
        sequence,
        geometry.count,
        tuple(observations),
        threshold,
    )
