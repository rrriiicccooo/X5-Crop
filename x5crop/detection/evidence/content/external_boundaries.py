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
    PhotoAperture,
    PhotoApertureEdgeSource,
)
from ....image.evidence import (
    CONTENT_EVIDENCE_NEIGHBORHOOD_RADIUS_PX,
    activation_mask,
)
from .activation import cached_content_evidence_threshold

if TYPE_CHECKING:
    from ...physical.model import PhotoSequenceSolution


@dataclass(frozen=True)
class ExternalApertureBoundaryObservation:
    photo_index: int
    side: BoundarySide
    boundary_source: PhotoApertureEdgeSource
    inside_region: Box
    outside_region: Box | None
    active_inside_pixels: int
    active_outside_pixels: int
    crossing_track_count: int
    minimum_active_pixels: int
    minimum_crossing_tracks: int
    content_crossing_detected: bool = field(init=False)
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)

    def __post_init__(self) -> None:
        if self.photo_index <= 0:
            raise ValueError("external aperture observation requires a photo index")
        if not self.inside_region.valid():
            raise ValueError("external aperture observation requires an inside region")
        if self.outside_region is not None and not self.outside_region.valid():
            raise ValueError("external aperture outside region must have positive extent")
        if min(
            self.active_inside_pixels,
            self.active_outside_pixels,
            self.crossing_track_count,
        ) < 0:
            raise ValueError("external aperture measurements must be non-negative")
        if min(self.minimum_active_pixels, self.minimum_crossing_tracks) <= 0:
            raise ValueError("external aperture support requirements must be positive")

        crossing_detected = bool(
            self.outside_region is not None
            and self.active_inside_pixels >= self.minimum_active_pixels
            and self.active_outside_pixels >= self.minimum_active_pixels
            and self.crossing_track_count >= self.minimum_crossing_tracks
        )
        if self.outside_region is None:
            state = EvidenceState.NOT_APPLICABLE
            reason = "external_aperture_edge_is_canvas_adjacent"
        elif crossing_detected:
            if self.boundary_source == PhotoApertureEdgeSource.DIMENSION_HYPOTHESIS:
                state = EvidenceState.CONTRADICTED
                reason = "continuous_content_crosses_provisional_aperture"
            else:
                state = EvidenceState.CONTRADICTED
                reason = "continuous_content_crosses_measured_aperture"
        else:
            state = EvidenceState.UNAVAILABLE
            reason = "external_content_crossing_not_corroborated"
        object.__setattr__(self, "content_crossing_detected", crossing_detected)
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "reason", reason)


@dataclass(frozen=True)
class ExternalAperturePreservationEvidence:
    workspace_extent: Box
    photo_sequence_envelope: Box
    photo_count: int
    observations: tuple[ExternalApertureBoundaryObservation, ...]
    threshold: float | None
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)

    def __post_init__(self) -> None:
        if self.photo_count <= 0:
            raise ValueError("external aperture evidence requires a photo count")
        if not self.workspace_extent.valid():
            raise ValueError("external aperture evidence requires a valid workspace")
        if not self.photo_sequence_envelope.valid():
            raise ValueError("external aperture evidence requires a valid envelope")
        workspace = self.workspace_extent
        sequence = self.photo_sequence_envelope
        if not (
            workspace.left <= sequence.left < sequence.right <= workspace.right
            and workspace.top <= sequence.top < sequence.bottom <= workspace.bottom
        ):
            raise ValueError("photo sequence envelope must fit the workspace")
        if not self.observations:
            raise ValueError("external aperture evidence requires aperture observations")
        expected = tuple(
            (photo_index, side)
            for photo_index in range(1, self.photo_count + 1)
            for side in (
                *((BoundarySide.LEADING,) if photo_index == 1 else ()),
                BoundarySide.TOP,
                BoundarySide.BOTTOM,
                *(
                    (BoundarySide.TRAILING,)
                    if photo_index == self.photo_count
                    else ()
                ),
            )
        )
        observed = tuple(
            (item.photo_index, item.side) for item in self.observations
        )
        if observed != expected:
            raise ValueError(
                "external aperture evidence requires every photo cross-axis edge "
                "and only the sequence endpoint long-axis edges"
            )
        if any(
            item.state == EvidenceState.CONTRADICTED
            for item in self.observations
        ):
            state = EvidenceState.CONTRADICTED
            reason = "visible_content_crosses_external_aperture"
        elif all(
            item.state == EvidenceState.NOT_APPLICABLE
            for item in self.observations
        ):
            state = EvidenceState.NOT_APPLICABLE
            reason = "all_external_aperture_edges_are_canvas_adjacent"
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
    aperture: PhotoAperture,
    side: BoundarySide,
    band: int,
    workspace: Box,
) -> tuple[Box, Box | None]:
    sequence = aperture.frame_crop_envelope.box.clamp(
        workspace.right,
        workspace.bottom,
    )

    def measured_middle(
        start: int,
        end: int,
        lower_uncertainty: float,
        upper_uncertainty: float,
    ) -> tuple[int, int]:
        measured_start = max(start, int(math.ceil(lower_uncertainty)) + band)
        measured_end = min(end, int(math.floor(upper_uncertainty)) - band)
        if measured_end > measured_start:
            return measured_start, measured_end
        midpoint = max(start, min(end - 1, (start + end) // 2))
        return midpoint, midpoint + 1

    if side == BoundarySide.LEADING:
        orthogonal_start, orthogonal_end = measured_middle(
            sequence.top,
            sequence.bottom,
            aperture.top.position.maximum,
            aperture.bottom.position.minimum,
        )
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
        orthogonal_start, orthogonal_end = measured_middle(
            sequence.top,
            sequence.bottom,
            aperture.top.position.maximum,
            aperture.bottom.position.minimum,
        )
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
    elif side == BoundarySide.TOP:
        orthogonal_start, orthogonal_end = measured_middle(
            sequence.left,
            sequence.right,
            aperture.leading.position.maximum,
            aperture.trailing.position.minimum,
        )
        inside = Box(
            orthogonal_start,
            sequence.top,
            orthogonal_end,
            min(sequence.bottom, sequence.top + band),
        )
        outside = (
            None
            if sequence.top <= workspace.top
            else Box(
                orthogonal_start,
                max(workspace.top, sequence.top - band),
                orthogonal_end,
                sequence.top,
            )
        )
    elif side == BoundarySide.BOTTOM:
        orthogonal_start, orthogonal_end = measured_middle(
            sequence.left,
            sequence.right,
            aperture.leading.position.maximum,
            aperture.trailing.position.minimum,
        )
        inside = Box(
            orthogonal_start,
            max(sequence.top, sequence.bottom - band),
            orthogonal_end,
            sequence.bottom,
        )
        outside = (
            None
            if sequence.bottom >= workspace.bottom
            else Box(
                orthogonal_start,
                sequence.bottom,
                orthogonal_end,
                min(workspace.bottom, sequence.bottom + band),
            )
        )
    else:
        raise ValueError(f"unsupported external aperture side: {side}")
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
        raise ValueError(f"unsupported external aperture side: {side}")
    track_count = min(inside_tracks.size, outside_tracks.size)
    return int(
        np.count_nonzero(
            inside_tracks[:track_count] & outside_tracks[:track_count]
        )
    )


def external_aperture_preservation_evidence(
    geometry: PhotoSequenceSolution,
    cache: MeasurementCache,
    parameters: ContentEvidenceParameters,
) -> ExternalAperturePreservationEvidence:
    if cache.layout != geometry.layout:
        raise ValueError("external aperture evidence requires matching cache layout")
    height, width = cache.content_evidence_float_work.shape
    workspace = Box(0, 0, width, height)
    sequence = geometry.photo_sequence_envelope.clamp(width, height)
    if not sequence.valid():
        raise ValueError("external aperture evidence requires valid photo geometry")
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
    observations: list[ExternalApertureBoundaryObservation] = []
    last_index = len(geometry.photo_apertures)
    for aperture in geometry.photo_apertures:
        sides = (
            *((BoundarySide.LEADING,) if aperture.index == 1 else ()),
            BoundarySide.TOP,
            BoundarySide.BOTTOM,
            *((BoundarySide.TRAILING,) if aperture.index == last_index else ()),
        )
        for side in sides:
            resolution = getattr(aperture, side.value)
            inside, outside = _boundary_regions(
                aperture,
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
                ExternalApertureBoundaryObservation(
                    photo_index=aperture.index,
                    side=side,
                    boundary_source=resolution.source,
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
                )
            )
    return ExternalAperturePreservationEvidence(
        workspace,
        sequence,
        geometry.count,
        tuple(observations),
        threshold,
    )
