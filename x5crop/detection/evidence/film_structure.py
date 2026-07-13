from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math

from ...domain import (
    BoundaryKind,
    BoundaryPathObservation,
    BoundarySide,
    EvidenceState,
    FrameBoundaryReference,
    FrameBoundarySource,
    GrayIntensityTail,
    GrayMaterialObservation,
)
from ..physical.boundary import boundary_supports_holder_material
from ..physical.model import SequenceSolution
from .holder_material import HolderMaterialEvidence


MINIMUM_SAME_SOURCE_MATERIAL_OBSERVATIONS = 2
MINIMUM_CROSS_SOURCE_MATERIAL_OBSERVATIONS = 1


class FilmBaseReferenceSource(str, Enum):
    VISIBLE_FILM_BASE_TRACKS = "visible_film_base_tracks"
    INTERNAL_SEPARATOR_CONSENSUS = "internal_separator_consensus"
    COMBINED_STRUCTURE = "combined_structure"


@dataclass(frozen=True)
class FilmBaseMaterialObservation:
    location: BoundarySide | FrameBoundaryReference
    material: GrayMaterialObservation

    def __post_init__(self) -> None:
        if isinstance(self.location, BoundarySide):
            if self.location not in {BoundarySide.TOP, BoundarySide.BOTTOM}:
                raise ValueError("film-base track location must be top or bottom")
        elif not isinstance(self.location, FrameBoundaryReference):
            raise TypeError("film-base material requires a typed physical location")
        if not isinstance(self.material, GrayMaterialObservation):
            raise TypeError("film-base material requires a gray observation")


@dataclass(frozen=True)
class FilmBaseReference:
    source: FilmBaseReferenceSource | None
    intensity_tail: GrayIntensityTail | None
    observations: tuple[FilmBaseMaterialObservation, ...]
    texture_limit: float
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)

    def __post_init__(self) -> None:
        if not math.isfinite(self.texture_limit) or self.texture_limit < 0.0:
            raise ValueError("film-base texture limit must be finite and non-negative")
        available = self.source is not None
        if available != bool(self.observations) or available != (
            self.intensity_tail is not None
        ):
            raise ValueError("film-base identity must match material availability")
        if self.source is not None and not isinstance(
            self.source,
            FilmBaseReferenceSource,
        ):
            raise TypeError("film-base reference requires a typed source")
        if self.intensity_tail == GrayIntensityTail.MIDRANGE:
            raise ValueError("film-base reference requires a gray-tail consensus")
        if any(
            observation.material.intensity_tail != self.intensity_tail
            for observation in self.observations
        ):
            raise ValueError("film-base materials must share one gray tail")
        if any(
            observation.material.texture_median > self.texture_limit
            for observation in self.observations
        ):
            raise ValueError("film-base materials must satisfy the adaptive texture limit")
        locations = tuple(
            observation.location for observation in self.observations
        )
        if len(locations) != len(set(locations)):
            raise ValueError("film-base material locations must be unique")
        track_count = sum(isinstance(location, BoundarySide) for location in locations)
        separator_count = sum(
            isinstance(location, FrameBoundaryReference) for location in locations
        )
        if self.source == FilmBaseReferenceSource.VISIBLE_FILM_BASE_TRACKS and (
            track_count < MINIMUM_SAME_SOURCE_MATERIAL_OBSERVATIONS
            or separator_count
        ):
            raise ValueError("visible film-base consensus requires distinct edge tracks")
        if self.source == FilmBaseReferenceSource.INTERNAL_SEPARATOR_CONSENSUS and (
            separator_count < MINIMUM_SAME_SOURCE_MATERIAL_OBSERVATIONS
            or track_count
        ):
            raise ValueError("internal film-base consensus requires distinct separators")
        if self.source == FilmBaseReferenceSource.COMBINED_STRUCTURE and (
            track_count < MINIMUM_CROSS_SOURCE_MATERIAL_OBSERVATIONS
            or separator_count < MINIMUM_CROSS_SOURCE_MATERIAL_OBSERVATIONS
        ):
            raise ValueError("combined film-base consensus requires both material sources")
        state = EvidenceState.SUPPORTED if available else EvidenceState.UNAVAILABLE
        object.__setattr__(self, "state", state)
        object.__setattr__(
            self,
            "reason",
            (
                "film_base_material_reference_supported"
                if available
                else "film_base_material_reference_unavailable"
            ),
        )

    @classmethod
    def unavailable(cls, texture_limit: float) -> "FilmBaseReference":
        return cls(None, None, (), texture_limit)


class ApertureContactOutcome(str, Enum):
    HOLDER_TO_IMAGE = "holder_to_image"
    HOLDER_TO_FILM_BASE = "holder_to_film_base"
    CANVAS_CLIP = "canvas_clip"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class ApertureContactSideEvidence:
    side: BoundarySide
    outcome: ApertureContactOutcome
    path: BoundaryPathObservation | None
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)

    def __post_init__(self) -> None:
        if self.path is not None and self.path.side != self.side:
            raise ValueError("aperture contact side must match its boundary path")
        if not isinstance(self.outcome, ApertureContactOutcome):
            raise TypeError("aperture contact requires a typed outcome")
        if self.path is None and self.outcome != ApertureContactOutcome.UNRESOLVED:
            raise ValueError("missing aperture path must remain unresolved")
        holder_contact = self.outcome in {
            ApertureContactOutcome.HOLDER_TO_IMAGE,
            ApertureContactOutcome.HOLDER_TO_FILM_BASE,
        }
        if holder_contact and (
            self.path is None
            or self.path.kind == BoundaryKind.CANVAS_CLIP
            or self.path.outer_material is None
            or self.path.inner_material is None
        ):
            raise ValueError("holder aperture contact requires measured material sides")
        if (
            self.outcome == ApertureContactOutcome.CANVAS_CLIP
            and (self.path is None or self.path.kind != BoundaryKind.CANVAS_CLIP)
        ):
            raise ValueError("canvas aperture contact requires a canvas boundary")
        state, reason = {
            ApertureContactOutcome.HOLDER_TO_IMAGE: (
                EvidenceState.SUPPORTED,
                "holder_material_contacts_visible_image",
            ),
            ApertureContactOutcome.HOLDER_TO_FILM_BASE: (
                EvidenceState.SUPPORTED,
                "holder_material_contacts_film_base",
            ),
            ApertureContactOutcome.CANVAS_CLIP: (
                EvidenceState.NOT_APPLICABLE,
                "boundary_is_canvas_clip",
            ),
            ApertureContactOutcome.UNRESOLVED: (
                EvidenceState.UNAVAILABLE,
                "aperture_contact_unresolved",
            ),
        }[self.outcome]
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "reason", reason)


@dataclass(frozen=True)
class ApertureContactEvidence:
    sides: tuple[ApertureContactSideEvidence, ...]
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)

    def __post_init__(self) -> None:
        if tuple(item.side for item in self.sides) != tuple(BoundarySide):
            raise ValueError("aperture contact evidence requires four ordered sides")
        states = tuple(item.state for item in self.sides)
        state = (
            EvidenceState.SUPPORTED
            if any(item == EvidenceState.SUPPORTED for item in states)
            else EvidenceState.UNAVAILABLE
            if any(item == EvidenceState.UNAVAILABLE for item in states)
            else EvidenceState.NOT_APPLICABLE
        )
        object.__setattr__(self, "state", state)
        object.__setattr__(
            self,
            "reason",
            (
                "aperture_contact_observed"
                if state == EvidenceState.SUPPORTED
                else "aperture_contact_unresolved"
                if state == EvidenceState.UNAVAILABLE
                else "aperture_contact_not_applicable"
            ),
        )


@dataclass(frozen=True)
class SeparatorSequenceEvidence:
    expected_count: int
    hard_count: int
    dimension_constrained_count: int
    hard_boundaries: tuple[FrameBoundaryReference, ...]
    missing_boundaries: tuple[FrameBoundaryReference, ...]
    hard_tonal_evidence: tuple[float, ...]
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)

    def __post_init__(self) -> None:
        if min(
            self.expected_count,
            self.hard_count,
            self.dimension_constrained_count,
        ) < 0:
            raise ValueError("separator sequence counts cannot be negative")
        if self.hard_count != len(self.hard_boundaries):
            raise ValueError("hard separator count must match boundary references")
        if len(self.hard_tonal_evidence) != self.hard_count:
            raise ValueError("hard separator tonal evidence must be complete")
        references = (*self.hard_boundaries, *self.missing_boundaries)
        if len(references) != self.expected_count or len(set(references)) != len(
            references
        ):
            raise ValueError(
                "separator boundary references must be complete and unique"
            )
        state = (
            EvidenceState.NOT_APPLICABLE
            if self.expected_count == 0
            else EvidenceState.SUPPORTED
            if not self.missing_boundaries
            else EvidenceState.UNAVAILABLE
        )
        reason = (
            "single_frame_has_no_internal_separator"
            if self.expected_count == 0
            else "complete_independent_separator_sequence"
            if state == EvidenceState.SUPPORTED
            else "independent_separator_sequence_incomplete"
        )
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "reason", reason)


@dataclass(frozen=True)
class FilmStructureEvidence:
    separator_sequence: SeparatorSequenceEvidence
    film_base_reference: FilmBaseReference
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)

    def __post_init__(self) -> None:
        if self.separator_sequence.state == EvidenceState.NOT_APPLICABLE:
            state = EvidenceState.NOT_APPLICABLE
            reason = "single_frame_has_no_internal_film_structure"
        elif self.separator_sequence.state != EvidenceState.SUPPORTED:
            state = EvidenceState.UNAVAILABLE
            reason = "film_structure_sequence_incomplete"
        elif self.film_base_reference.state != EvidenceState.SUPPORTED:
            state = EvidenceState.UNAVAILABLE
            reason = "film_structure_material_reference_unavailable"
        else:
            state = EvidenceState.SUPPORTED
            reason = "film_structure_sequence_and_material_supported"
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "reason", reason)


def separator_sequence_evidence(
    geometry: SequenceSolution,
) -> SeparatorSequenceEvidence:
    expected = max(0, geometry.count - 1)
    accepted = tuple(
        boundary
        for boundary in geometry.frame_boundaries
        if boundary.hard_separator
        and boundary.assignment is not None
        and boundary.assignment.observation.cross_axis.state
        == EvidenceState.SUPPORTED
    )
    indexes = tuple(sorted(boundary.boundary_index for boundary in accepted))
    missing = tuple(
        index for index in range(1, expected + 1) if index not in indexes
    )
    dimension_count = sum(
        boundary.source == FrameBoundarySource.DIMENSION_CONSTRAINED
        for boundary in geometry.frame_boundaries
    )
    return SeparatorSequenceEvidence(
        expected_count=expected,
        hard_count=len(accepted),
        dimension_constrained_count=dimension_count,
        hard_boundaries=tuple(
            FrameBoundaryReference(None, index) for index in indexes
        ),
        missing_boundaries=tuple(
            FrameBoundaryReference(None, index) for index in missing
        ),
        hard_tonal_evidence=tuple(
            float(boundary.assignment.observation.tonal_evidence)
            for boundary in accepted
            if boundary.assignment is not None
        ),
    )


def _tail_groups(
    observations: tuple[FilmBaseMaterialObservation, ...],
) -> dict[GrayIntensityTail, tuple[FilmBaseMaterialObservation, ...]]:
    return {
        tail: tuple(
            observation
            for observation in observations
            if observation.material.intensity_tail == tail
        )
        for tail in (GrayIntensityTail.LOW, GrayIntensityTail.HIGH)
    }


def _film_base_material_eligible(
    material: GrayMaterialObservation,
    edge_texture_limit: float,
) -> bool:
    return bool(
        material.intensity_tail != GrayIntensityTail.MIDRANGE
        and material.texture_median <= edge_texture_limit
    )


def film_base_reference(
    geometry: SequenceSolution,
    holder_material: HolderMaterialEvidence,
    *,
    edge_texture_limit: float,
) -> FilmBaseReference:
    if not math.isfinite(edge_texture_limit) or edge_texture_limit < 0.0:
        raise ValueError("film-base track texture limit must be finite and non-negative")
    track_materials = tuple(
        FilmBaseMaterialObservation(path.side, path.inner_material)
        for path in holder_material.paths
        if path.side in {BoundarySide.TOP, BoundarySide.BOTTOM}
        and path.inner_material is not None
        and _film_base_material_eligible(
            path.inner_material,
            edge_texture_limit,
        )
    )
    separator_materials = tuple(
        FilmBaseMaterialObservation(
            FrameBoundaryReference(None, assignment.boundary_index),
            assignment.observation.material,
        )
        for assignment in geometry.separator_assignments
        if assignment.used_for_boundary
        and assignment.independent
        and assignment.observation.cross_axis.state == EvidenceState.SUPPORTED
        and _film_base_material_eligible(
            assignment.observation.material,
            edge_texture_limit,
        )
    )
    track_groups = _tail_groups(track_materials)
    separator_groups = _tail_groups(separator_materials)
    candidates: list[
        tuple[
            FilmBaseReferenceSource,
            GrayIntensityTail,
            tuple[FilmBaseMaterialObservation, ...],
        ]
    ] = []
    for tail in (GrayIntensityTail.LOW, GrayIntensityTail.HIGH):
        tracks = track_groups[tail]
        separators = separator_groups[tail]
        if (
            len(tracks) >= MINIMUM_CROSS_SOURCE_MATERIAL_OBSERVATIONS
            and len(separators) >= MINIMUM_CROSS_SOURCE_MATERIAL_OBSERVATIONS
        ):
            candidates.append(
                (
                    FilmBaseReferenceSource.COMBINED_STRUCTURE,
                    tail,
                    (*tracks, *separators),
                )
            )
        elif len(tracks) >= MINIMUM_SAME_SOURCE_MATERIAL_OBSERVATIONS:
            candidates.append(
                (
                    FilmBaseReferenceSource.VISIBLE_FILM_BASE_TRACKS,
                    tail,
                    tracks,
                )
            )
        elif len(separators) >= MINIMUM_SAME_SOURCE_MATERIAL_OBSERVATIONS:
            candidates.append(
                (
                    FilmBaseReferenceSource.INTERNAL_SEPARATOR_CONSENSUS,
                    tail,
                    separators,
                )
            )
    if len(candidates) != 1:
        return FilmBaseReference.unavailable(edge_texture_limit)
    source, tail, observations = candidates[0]
    return FilmBaseReference(source, tail, observations, edge_texture_limit)


def aperture_contact_outcome(
    path: BoundaryPathObservation | None,
    edge_texture_limit: float,
    film_base: FilmBaseReference | None = None,
) -> ApertureContactOutcome:
    if film_base is not None and edge_texture_limit != film_base.texture_limit:
        raise ValueError("aperture contact must use the film-base texture limit")
    if path is None:
        return ApertureContactOutcome.UNRESOLVED
    if path.kind == BoundaryKind.CANVAS_CLIP:
        return ApertureContactOutcome.CANVAS_CLIP
    if not boundary_supports_holder_material(path, edge_texture_limit):
        return ApertureContactOutcome.UNRESOLVED
    if path.inner_material is None:
        return ApertureContactOutcome.UNRESOLVED
    if path.inner_material.texture_median > edge_texture_limit:
        return ApertureContactOutcome.HOLDER_TO_IMAGE
    if (
        film_base is not None
        and film_base.state == EvidenceState.SUPPORTED
        and path.inner_material.intensity_tail == film_base.intensity_tail
    ):
        return ApertureContactOutcome.HOLDER_TO_FILM_BASE
    return ApertureContactOutcome.UNRESOLVED


def aperture_contact_evidence(
    geometry: SequenceSolution,
    film_base: FilmBaseReference,
) -> ApertureContactEvidence:
    paths = {path.side: path for path in geometry.boundary_paths}
    return ApertureContactEvidence(
        tuple(
            ApertureContactSideEvidence(
                side,
                aperture_contact_outcome(
                    paths.get(side),
                    film_base.texture_limit,
                    film_base,
                ),
                paths.get(side),
            )
            for side in BoundarySide
        )
    )


def film_structure_evidence(
    geometry: SequenceSolution,
    film_base: FilmBaseReference,
) -> FilmStructureEvidence:
    return FilmStructureEvidence(
        separator_sequence_evidence(geometry),
        film_base,
    )
