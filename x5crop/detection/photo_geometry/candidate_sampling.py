"""Lightweight sampling-equivalence geometry without output authority."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain import Box
from ...geometry.affine import AffineCoordinateTransform
from ...geometry.convex import clip_convex_polygon_to_box, mapped_half_open_box
from ..source_core import SourceLaneEvidence
from .chains import CompleteFormatChain
from .corridors import source_lane_box
from .frame_footprints import retained_frame_safety_footprint


@dataclass(frozen=True)
class ChainSamplingGeometry:
    """Boxes needed to compare chains; never authorizes saved output."""

    placement_id: str
    lane_id: str
    sampling_boxes: tuple[Box, ...]
    sampling_authority_boxes: tuple[Box, ...]
    authority_profile_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        count = len(self.sampling_boxes)
        if (
            not self.placement_id
            or not self.lane_id
            or count <= 0
            or len(self.sampling_authority_boxes) != count
            or len(self.authority_profile_ids) != count
            or any(not box.valid() for box in self.sampling_boxes)
            or any(not box.valid() for box in self.sampling_authority_boxes)
            or any(not identity for identity in self.authority_profile_ids)
        ):
            raise ValueError("chain sampling geometry is invalid")


def chain_sampling_geometry(
    placement: CompleteFormatChain,
    *,
    lane: SourceLaneEvidence,
    layout: str,
    transform: AffineCoordinateTransform,
) -> ChainSamplingGeometry:
    authority = source_lane_box(lane, layout)
    mapped_boxes: list[Box] = []
    for ordinal in range(1, placement.output_slot_count + 1):
        required = retained_frame_safety_footprint(placement, ordinal)
        constrained = clip_convex_polygon_to_box(required, authority)
        mapped = mapped_half_open_box(constrained, transform.map_point)
        if (
            mapped.left < 0
            or mapped.top < 0
            or mapped.right > transform.output_extent.width
            or mapped.bottom > transform.output_extent.height
        ):
            raise ValueError("mapped footprint exceeds affine output authority")
        mapped_boxes.append(mapped)
    return ChainSamplingGeometry(
        placement_id=placement.placement_id,
        lane_id=placement.lane_id,
        sampling_boxes=tuple(mapped_boxes),
        sampling_authority_boxes=(authority,) * placement.output_slot_count,
        authority_profile_ids=(
            lane.domain.authority_profile_id,
        )
        * placement.output_slot_count,
    )
