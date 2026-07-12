from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ...cache import MeasurementCache
from ...domain import Box
from ...policies.parameters.sequence import SequenceContentAlignmentParameters
from ...utils import bbox_from_mask, clamp_int
from x5crop.domain import EvidenceState

if TYPE_CHECKING:
    from ..physical.model import SequenceSolution


@dataclass(frozen=True)
class SequenceContentAlignmentEvidence:
    state: EvidenceState
    reason: str
    visible_sequence_span: Box
    content_span: Box | None
    content_measurement_sources: tuple[str, ...]
    confirmed_undercrop_sides: tuple[str, ...]
    unconfirmed_undercrop_sides: tuple[str, ...]
    overcontains_long_axis: bool
    overcontains_short_axis: bool
    leading_slack_px: int
    trailing_slack_px: int
    top_slack_px: int
    bottom_slack_px: int
    border_tonal_fraction: tuple[tuple[str, float], ...]

def sequence_content_alignment_evidence(
    geometry: SequenceSolution,
    cache: MeasurementCache,
    parameters: SequenceContentAlignmentParameters,
) -> SequenceContentAlignmentEvidence:
    if cache.layout != geometry.layout:
        raise ValueError("sequence alignment requires matching measurement cache")
    work_height, work_width = cache.gray_work.shape
    sequence_box = geometry.visible_sequence_span.box.clamp(work_width, work_height)
    if not sequence_box.valid():
        return SequenceContentAlignmentEvidence(
            EvidenceState.UNAVAILABLE,
            "invalid_visible_sequence_span",
            sequence_box,
            None,
            (),
            (),
            (),
            False,
            False,
            0,
            0,
            0,
            0,
            (),
        )

    measured: list[tuple[str, Box]] = []
    for threshold in parameters.content_bbox_thresholds:
        box = bbox_from_mask(
            cache.gray_work < int(threshold),
            min_row_fraction=float(parameters.content_bbox_min_row_fraction),
            min_col_fraction=float(parameters.content_bbox_min_col_fraction),
        )
        if box is not None and box.valid():
            measured.append((f"gray_lt_{threshold}", box))
    if not measured:
        return SequenceContentAlignmentEvidence(
            EvidenceState.UNAVAILABLE,
            "content_span_unavailable",
            sequence_box,
            None,
            (),
            (),
            (),
            False,
            False,
            0,
            0,
            0,
            0,
            (),
        )

    content = measured[0][1]
    pitch = float(sequence_box.width) / float(max(1, geometry.count))
    long_threshold = clamp_int(
        pitch * parameters.long_threshold_ratio,
        parameters.long_threshold_min,
        parameters.long_threshold_max,
    )
    short_threshold = clamp_int(
        float(sequence_box.height) * parameters.short_threshold_ratio,
        parameters.short_threshold_min,
        parameters.short_threshold_max,
    )
    counts = {
        "left": sum(
            max(0, sequence_box.left - box.left) >= long_threshold
            for _source, box in measured
        ),
        "right": sum(
            max(0, box.right - sequence_box.right) >= long_threshold
            for _source, box in measured
        ),
        "top": sum(
            max(0, sequence_box.top - box.top) >= short_threshold
            for _source, box in measured
        ),
        "bottom": sum(
            max(0, box.bottom - sequence_box.bottom) >= short_threshold
            for _source, box in measured
        ),
    }
    minimum = int(parameters.undercrop_confirmation_min_measurements)
    confirmed = tuple(side for side, count in counts.items() if count >= minimum)
    unconfirmed = tuple(
        side for side, count in counts.items() if 0 < count < minimum
    )

    leading_slack = max(0, content.left - sequence_box.left)
    trailing_slack = max(0, sequence_box.right - content.right)
    top_slack = max(0, content.top - sequence_box.top)
    bottom_slack = max(0, sequence_box.bottom - content.bottom)
    max_long_slack = max(leading_slack, trailing_slack)
    max_short_slack = max(top_slack, bottom_slack)
    long_slack_ratio = float(max_long_slack) / max(1.0, pitch)
    short_slack_ratio = float(max_short_slack) / max(1.0, float(sequence_box.height))

    crop = cache.gray_work[sequence_box.top : sequence_box.bottom, sequence_box.left : sequence_box.right]
    edge_band = max(
        int(parameters.border_band_min_px),
        min(
            int(parameters.border_band_max_px),
            int(round(min(sequence_box.width, sequence_box.height) * parameters.border_band_ratio)),
        ),
    )
    if crop.size:
        samples = {
            "left": crop[:, : min(edge_band, crop.shape[1])],
            "right": crop[:, max(0, crop.shape[1] - edge_band) :],
            "top": crop[: min(edge_band, crop.shape[0]), :],
            "bottom": crop[max(0, crop.shape[0] - edge_band) :, :],
        }
        tonal = tuple(
            (
                side,
                float((sample < parameters.border_dark_threshold).mean())
                if sample.size
                else 0.0,
            )
            for side, sample in samples.items()
        )
    else:
        tonal = ()

    hard_boundary_indexes = {
        boundary.boundary_index
        for boundary in geometry.frame_boundaries
        if boundary.hard_separator
    }
    edge_hard_anchors = bool(
        geometry.strip_mode == "full"
        and geometry.count > 2
        and {1, geometry.count - 1}.issubset(hard_boundary_indexes)
    )
    content_width_ratio = float(content.width) / max(1.0, float(sequence_box.width))
    white_edge_threshold = clamp_int(
        pitch * parameters.white_edge_long_ratio,
        parameters.white_edge_long_min,
        parameters.white_edge_long_max,
    )
    tonal_by_side = dict(tonal)
    white_holder_slack = bool(
        edge_hard_anchors
        and content_width_ratio >= parameters.content_width_min
        and max_short_slack
        <= max(
            int(parameters.edge_short_min_px),
            int(round(float(sequence_box.height) * parameters.edge_short_ratio)),
        )
        and (
            leading_slack >= white_edge_threshold
            and tonal_by_side.get("left", 1.0) <= parameters.edge_dark_max
            or trailing_slack >= white_edge_threshold
            and tonal_by_side.get("right", 1.0) <= parameters.edge_dark_max
        )
    )
    overcontains_long = bool(
        long_slack_ratio > parameters.long_excess_ratio
        or (
            max_long_slack >= long_threshold
            and long_slack_ratio > parameters.long_excess_threshold_ratio
        )
        or white_holder_slack
    )
    short_semantic = bool(
        (not parameters.short_requires_hard_anchors or edge_hard_anchors)
        and (
            parameters.short_content_height_max >= 1.0
            or float(content.height) / max(1.0, float(sequence_box.height))
            <= parameters.short_content_height_max
        )
    )
    overcontains_short = bool(
        short_semantic
        and short_slack_ratio > parameters.short_excess_ratio
        and max_short_slack >= short_threshold
    )

    if confirmed:
        state = EvidenceState.CONTRADICTED
        reason = "content_outside_visible_sequence_confirmed"
    elif unconfirmed:
        state = EvidenceState.UNAVAILABLE
        reason = "content_span_measurements_disagree"
    else:
        state = EvidenceState.SUPPORTED
        reason = "content_inside_visible_sequence"
    return SequenceContentAlignmentEvidence(
        state=state,
        reason=reason,
        visible_sequence_span=sequence_box,
        content_span=content,
        content_measurement_sources=tuple(source for source, _box in measured),
        confirmed_undercrop_sides=confirmed,
        unconfirmed_undercrop_sides=unconfirmed,
        overcontains_long_axis=overcontains_long,
        overcontains_short_axis=overcontains_short,
        leading_slack_px=int(leading_slack),
        trailing_slack_px=int(trailing_slack),
        top_slack_px=int(top_slack),
        bottom_slack_px=int(bottom_slack),
        border_tonal_fraction=tonal,
    )
