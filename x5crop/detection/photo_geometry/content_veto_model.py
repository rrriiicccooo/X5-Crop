"""Typed negative-only content facts for placement selection."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ...domain import ObservationId
from .model import BoundaryRole


class ContentVetoReason(str, Enum):
    SLOT_CONTENT_CROPPED_IN = "slot_content_cropped_in"
    SEPARATOR_CORE_CONTENT_CROSSING = "separator_core_content_crossing"
    OUTER_SLOT_CONTENT_OMITTED = "outer_slot_content_omitted"


@dataclass(frozen=True)
class ContentVetoFact:
    reason: ContentVetoReason
    slot_ordinal: int
    boundary_role: BoundaryRole | None
    observation_ids: tuple[ObservationId, ...]

    def __post_init__(self) -> None:
        if (
            self.slot_ordinal <= 0
            or not self.observation_ids
            or len(set(self.observation_ids)) != len(self.observation_ids)
            or (
                self.reason == ContentVetoReason.SLOT_CONTENT_CROPPED_IN
                and self.boundary_role not in {BoundaryRole.TOP, BoundaryRole.BOTTOM}
            )
            or (
                self.reason == ContentVetoReason.SEPARATOR_CORE_CONTENT_CROSSING
                and self.boundary_role is not None
            )
            or (
                self.reason == ContentVetoReason.OUTER_SLOT_CONTENT_OMITTED
                and self.boundary_role not in {BoundaryRole.START, BoundaryRole.END}
            )
        ):
            raise ValueError("content veto fact is invalid")


@dataclass(frozen=True)
class ContentVetoAssessment:
    assessment_id: str
    placement_id: str
    facts: tuple[ContentVetoFact, ...]
    adjacent_start_end_content_is_neutral: bool = True
    contact_or_overlap_crossing_is_neutral: bool = True
    missing_content_is_neutral: bool = True

    def __post_init__(self) -> None:
        if (
            not self.assessment_id
            or not self.placement_id
            or not self.adjacent_start_end_content_is_neutral
            or not self.contact_or_overlap_crossing_is_neutral
            or not self.missing_content_is_neutral
        ):
            raise ValueError("content veto assessment is invalid")

    @property
    def vetoed(self) -> bool:
        return bool(self.facts)
