"""Geometry comparison for the user-confirmed golden cohort."""

from __future__ import annotations

import math
from typing import Sequence

from x5crop.detection.evidence.content_occupancy import (
    CONTENT_OCCUPANCY_MEASUREMENT_SPEC,
)
from x5crop.detection.photo_geometry.model import (
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
)
from x5crop.formats import OUTPUT_PROTECTION_SPEC, format_spec


def _contains_point(
    polygon: Sequence[Sequence[float]],
    point: Sequence[float],
    *,
    epsilon: float = 1.0e-6,
) -> bool:
    signs: list[bool] = []
    for left, right in zip(polygon, (*polygon[1:], polygon[0]), strict=True):
        cross = (
            (right[0] - left[0]) * (point[1] - left[1])
            - (right[1] - left[1]) * (point[0] - left[0])
        )
        if abs(cross) > epsilon:
            signs.append(cross > 0.0)
    return not signs or all(signs) or not any(signs)


def _contains_polygon(
    outer: Sequence[Sequence[float]],
    inner: Sequence[Sequence[float]],
) -> bool:
    return all(_contains_point(outer, point) for point in inner)


def _trimmed_edge_endpoints(
    polygon: Sequence[Sequence[float]],
    trim_depths_px: Sequence[float],
) -> tuple[tuple[float, float], ...]:
    points: list[tuple[float, float]] = []
    for left, right, depth in zip(
        polygon,
        (*polygon[1:], polygon[0]),
        trim_depths_px,
        strict=True,
    ):
        length = math.hypot(right[0] - left[0], right[1] - left[1])
        if length <= 0.0 or not 0.0 < depth < length / 2.0:
            raise ValueError("gold edge cannot establish a physical interior")
        fraction = depth / length
        points.extend(
            (
                (
                    left[0] + fraction * (right[0] - left[0]),
                    left[1] + fraction * (right[1] - left[1]),
                ),
                (
                    right[0] + fraction * (left[0] - right[0]),
                    right[1] + fraction * (left[1] - right[1]),
                ),
            )
        )
    return tuple(points)


def _unit_vector(x: float, y: float) -> tuple[float, float]:
    magnitude = math.hypot(x, y)
    if magnitude <= 0.0:
        raise ValueError("gold frame has a degenerate axis")
    return x / magnitude, y / magnitude


def _mean_edge_axis(
    polygon: Sequence[Sequence[float]],
    first: tuple[int, int],
    second: tuple[int, int],
) -> tuple[float, float]:
    return _unit_vector(
        (
            polygon[first[1]][0]
            - polygon[first[0]][0]
            + polygon[second[1]][0]
            - polygon[second[0]][0]
        )
        / 2.0,
        (
            polygon[first[1]][1]
            - polygon[first[0]][1]
            + polygon[second[1]][1]
            - polygon[second[0]][1]
        )
        / 2.0,
    )


def _projection_bounds(
    polygon: Sequence[Sequence[float]],
    axis: tuple[float, float],
) -> tuple[float, float]:
    values = tuple(point[0] * axis[0] + point[1] * axis[1] for point in polygon)
    return min(values), max(values)


def _assert_direct_use_budget(
    sample_id: str,
    frame_index: int,
    gold: Sequence[Sequence[float]],
    output: Sequence[Sequence[float]],
    strip_orientation: str,
    boundary_use: str,
) -> None:
    horizontal = strip_orientation == "horizontal"
    sequence_axis = _mean_edge_axis(
        gold,
        (0, 1) if horizontal else (0, 3),
        (3, 2) if horizontal else (1, 2),
    )
    cross_axis = _mean_edge_axis(
        gold,
        (0, 3) if horizontal else (0, 1),
        (1, 2) if horizontal else (3, 2),
    )
    gold_sequence = _projection_bounds(gold, sequence_axis)
    output_sequence = _projection_bounds(output, sequence_axis)
    gold_cross = _projection_bounds(gold, cross_axis)
    output_cross = _projection_bounds(output, cross_axis)
    sequence_span = gold_sequence[1] - gold_sequence[0]
    cross_span = gold_cross[1] - gold_cross[0]
    sequence_expansion = max(
        gold_sequence[0] - output_sequence[0],
        output_sequence[1] - gold_sequence[1],
    )
    cross_expansion = max(
        gold_cross[0] - output_cross[0],
        output_cross[1] - gold_cross[1],
    )
    pixel_allowance = (
        PHOTO_BOUNDARY_MEASUREMENT_SPEC
        .transition_coordinate_sampling_uncertainty_px
    )
    sequence_exceeded = (
        sequence_expansion
        > sequence_span * OUTPUT_PROTECTION_SPEC.maximum_expansion_ratio_per_side
        + pixel_allowance
    )
    if boundary_use == "enclosing_support_pair":
        output_cross_span = output_cross[1] - output_cross[0]
        cross_exceeded = (
            output_cross_span
            > cross_span
            * OUTPUT_PROTECTION_SPEC.maximum_enclosing_support_height_ratio
            + 2.0 * pixel_allowance
        )
    elif boundary_use == "aperture_pair":
        cross_exceeded = (
            cross_expansion
            > cross_span
            * OUTPUT_PROTECTION_SPEC.maximum_expansion_ratio_per_side
            + pixel_allowance
        )
    else:
        raise ValueError("gold output has an unknown cross-boundary use")
    if sequence_exceeded or cross_exceeded:
        raise ValueError(
            f"{sample_id} frame {frame_index} exceeds gold direct-use budget"
        )


def ordered_gold_mapping(
    gold_frames: Sequence[dict[str, object]],
    output_geometries: Sequence[dict[str, object]],
    strip_orientation: str,
    format_id: str,
) -> tuple[int, ...]:
    if len(gold_frames) != len(output_geometries):
        return ()
    horizontal = strip_orientation == "horizontal"

    def safely_covers(
        gold: Sequence[Sequence[float]],
        output: Sequence[Sequence[float]],
    ) -> bool:
        if _contains_polygon(output, gold):
            return True
        sequence_axis = _mean_edge_axis(
            gold,
            (0, 1) if horizontal else (0, 3),
            (3, 2) if horizontal else (1, 2),
        )
        cross_axis = _mean_edge_axis(
            gold,
            (0, 3) if horizontal else (0, 1),
            (1, 2) if horizontal else (3, 2),
        )
        frame = format_spec(format_id).frame
        edge_lengths = tuple(
            math.hypot(right[0] - left[0], right[1] - left[1])
            for left, right in zip(gold, (*gold[1:], gold[0]), strict=True)
        )
        sequence_scale = (edge_lengths[0] + edge_lengths[2]) / (
            2.0 * frame.frame_width_mm
        )
        cross_scale = (edge_lengths[1] + edge_lengths[3]) / (
            2.0 * frame.frame_height_mm
        )
        # A user-confirmed direct-use frame may graze content only at the
        # intersection of two adjacent boundaries.  Remove one already-owned
        # content-measurement support depth from both ends of every edge and
        # require the remaining edge interiors to be covered.  This is the
        # same topological rule as the runtime content veto: it is expressed
        # in physical units and does not permit an arbitrary number of lost
        # pixels at a corner.
        sequence_depth = (
            CONTENT_OCCUPANCY_MEASUREMENT_SPEC.cell_extent_mm
            * sequence_scale
        )
        cross_depth = (
            CONTENT_OCCUPANCY_MEASUREMENT_SPEC.cell_extent_mm
            * cross_scale
        )
        return all(
            _contains_point(output, point)
            for point in _trimmed_edge_endpoints(
                gold,
                (sequence_depth, cross_depth) * 2,
            )
        )

    mapping: list[int] = []
    next_output = 0
    for frame in gold_frames:
        polygon = frame["polygon_source_pixel_center_coordinates"]
        matches = tuple(
            index
            for index in range(next_output, len(output_geometries))
            if safely_covers(
                polygon,
                output_geometries[index]["required_source_footprint"],
            )
        )
        if not matches:
            return ()
        selected = matches[0]
        mapping.append(selected)
        next_output = selected + 1
    return tuple(mapping)


def validate_selected_candidate_coverage(
    record: dict[str, object],
    report: dict[str, object],
) -> bool:
    """Check selected pre-decision geometry without requiring official output."""

    outputs = tuple(
        output
        for lane in report["photo_geometry"]["lanes"]
        for output in lane["output_footprints"]
    )
    if not outputs:
        return False
    sample_id = str(record["sample_id"])
    gold = record["confirmed_geometry"]
    frames = gold["frames"]
    mapping = ordered_gold_mapping(
        frames,
        outputs,
        str(gold["strip_orientation"]),
        str(record["format_id"]),
    )
    if len(mapping) != len(frames):
        raise ValueError(f"{sample_id} candidate cuts confirmed content")
    return True


def validate_approved_geometry(
    record: dict[str, object],
    report: dict[str, object],
) -> None:
    sample_id = str(record["sample_id"])
    gold = record["confirmed_geometry"]
    frames = gold["frames"]
    outputs = report["output"]["finalization"]["output_footprints"]
    mapping = ordered_gold_mapping(
        frames,
        outputs,
        str(gold["strip_orientation"]),
        str(record["format_id"]),
    )
    if len(mapping) != len(frames):
        raise ValueError(f"{sample_id} approved output cuts confirmed content")
    for frame, output_index in zip(frames, mapping, strict=True):
        polygon = frame["polygon_source_pixel_center_coordinates"]
        output_polygon = outputs[output_index]["required_source_footprint"]
        _assert_direct_use_budget(
            sample_id,
            int(frame["frame_index"]),
            polygon,
            output_polygon,
            str(gold["strip_orientation"]),
            str(outputs[output_index]["envelope"]["boundary_use"]),
        )
    transform = report["output"]["finalization"][
        "source_transform_assessment"
    ]
    observed_angle = transform["observed_angle_interval_degrees"]
    gold_angles = tuple(
        math.degrees(math.atan(float(edge["slope"])))
        for edge in gold["shared_edges"]
    )
    if not all(
        observed_angle["minimum"] - 1.0e-9
        <= angle
        <= observed_angle["maximum"] + 1.0e-9
        for angle in gold_angles
    ):
        raise ValueError(f"{sample_id} deskew interval excludes confirmed edges")
