from __future__ import annotations

import numpy as np

from .....domain import Box
from .....formats import FormatPhysicalSpec
from .....gap_methods import is_hard_gap_method
from .....policies.runtime.outer import GeometryConsistencyCorrectionPolicy
from .....utils import clamp_int
from ....geometry import CandidateGeometry
from ....evidence.outer_alignment import OuterAlignmentEvidence
from ...photo_size import FrameDimensionEvidence
from ...spans import FilmSpan
from .constraints import correction_axes_allowed
from .types import OuterCorrectionProposal


def _long_axis_geometry_proposal(
    geometry: CandidateGeometry,
    physical_spec: FormatPhysicalSpec,
    alignment: OuterAlignmentEvidence,
    policy: GeometryConsistencyCorrectionPolicy,
    canvas_width: int,
) -> OuterCorrectionProposal | None:
    family = policy.long_axis.family
    parameters = policy.long_axis.parameters
    original = geometry.film_span.box
    if family.mode == "off" or geometry.count <= 1:
        return None
    separators = tuple(
        observation
        for observation in geometry.separators
        if is_hard_gap_method(observation.method)
    )
    if (
        len(separators) != geometry.count - 1
        or any(
            observation.start is None or observation.end is None
            for observation in separators
        )
    ):
        return None
    frame_width = float(original.height) * float(
        physical_spec.horizontal_content_aspect
    )
    separator_widths = [
        float(observation.end) - float(observation.start)
        for observation in separators
    ]
    left_estimates: list[float] = []
    right_estimates: list[float] = []
    for observation in separators:
        index = int(observation.index)
        preceding = sum(separator_widths[: max(0, index - 1)])
        following = sum(separator_widths[index:])
        left_estimates.append(
            float(original.left)
            + float(observation.start)
            - (float(index) * frame_width + preceding)
        )
        right_estimates.append(
            float(original.left)
            + float(observation.end)
            + (float(geometry.count - index) * frame_width + following)
        )
    corrected = Box(
        max(0, min(canvas_width - 1, int(round(np.median(left_estimates))))),
        original.top,
        max(1, min(canvas_width, int(round(np.median(right_estimates))))),
        original.bottom,
    )
    if not corrected.valid() or corrected.width >= original.width:
        return None
    shrink_ratio = float(original.width - corrected.width) / max(
        1.0,
        float(original.width),
    )
    if not (
        parameters.min_shrink_ratio
        <= shrink_ratio
        <= parameters.max_shrink_ratio
    ):
        return None
    if (
        family.max_shrink_ratio > 0.0
        and shrink_ratio > family.max_shrink_ratio
    ):
        return None
    content = alignment.content_span
    if content is not None and content.valid():
        margin = clamp_int(
            float(original.height) * parameters.content_margin_ratio,
            parameters.content_margin_min,
            parameters.content_margin_max,
        )
        if (
            corrected.left > content.left - margin
            or corrected.right < content.right + margin
        ):
            return None
    if not correction_axes_allowed(family, original, corrected):
        return None
    return OuterCorrectionProposal(
        corrected_span=FilmSpan(corrected),
        family="long_axis_geometry",
        reason="separator_edges_explain_smaller_film_span",
    )


def _short_axis_geometry_proposal(
    geometry: CandidateGeometry,
    dimensions: FrameDimensionEvidence,
    physical_spec: FormatPhysicalSpec,
    policy: GeometryConsistencyCorrectionPolicy,
    canvas_height: int,
) -> OuterCorrectionProposal | None:
    family = policy.short_axis.family
    parameters = policy.short_axis.parameters
    original = geometry.film_span.box
    if family.mode == "off" or dimensions.maximum_dimension_error_ratio is None:
        return None
    if dimensions.maximum_dimension_error_ratio < parameters.min_error:
        return None
    measured_photo_width = (
        float(np.median(dimensions.photo_widths_px))
        if dimensions.photo_widths_px
        else float(geometry.pitch)
    )
    target_height = measured_photo_width / max(
        1e-6,
        float(physical_spec.horizontal_content_aspect),
    )
    if target_height <= float(original.height):
        return None
    margin = clamp_int(
        geometry.pitch * parameters.margin_ratio,
        parameters.margin_min,
        parameters.margin_max,
    )
    target_height = min(float(canvas_height), target_height + 2.0 * margin)
    center = 0.5 * float(original.top + original.bottom)
    top = int(round(center - 0.5 * target_height))
    bottom = int(round(center + 0.5 * target_height))
    if top < 0:
        bottom -= top
        top = 0
    if bottom > canvas_height:
        top -= bottom - canvas_height
        bottom = canvas_height
    corrected = Box(original.left, max(0, top), original.right, min(canvas_height, bottom))
    if not corrected.valid() or corrected.height <= original.height:
        return None
    expansion_ratio = float(corrected.height - original.height) / max(
        1.0,
        float(original.height),
    )
    if family.max_expand_ratio > 0.0 and expansion_ratio > family.max_expand_ratio:
        return None
    if not correction_axes_allowed(family, original, corrected):
        return None
    return OuterCorrectionProposal(
        corrected_span=FilmSpan(corrected),
        family="short_axis_geometry",
        reason="physical_frame_aspect_requires_short_axis_expansion",
    )


def geometry_consistency_correction_proposals(
    geometry: CandidateGeometry,
    dimensions: FrameDimensionEvidence,
    alignment: OuterAlignmentEvidence,
    physical_spec: FormatPhysicalSpec,
    policy: GeometryConsistencyCorrectionPolicy,
    *,
    canvas_width: int,
    canvas_height: int,
    eligible_families: frozenset[str],
) -> tuple[OuterCorrectionProposal, ...]:
    proposals: list[OuterCorrectionProposal] = []
    if "long_axis_geometry" in eligible_families:
        proposal = _long_axis_geometry_proposal(
            geometry,
            physical_spec,
            alignment,
            policy,
            canvas_width,
        )
        if proposal is not None:
            proposals.append(proposal)
    if "short_axis_geometry" in eligible_families:
        proposal = _short_axis_geometry_proposal(
            geometry,
            dimensions,
            physical_spec,
            policy,
            canvas_height,
        )
        if proposal is not None:
            proposals.append(proposal)
    return tuple(proposals)
