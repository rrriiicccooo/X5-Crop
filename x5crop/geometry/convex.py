from __future__ import annotations

import math

from ..domain import Box


Point = tuple[float, float]
ConvexPolygon = tuple[Point, ...]
ContinuousBox = tuple[float, float, float, float]


def signed_area(polygon: ConvexPolygon) -> float:
    return 0.5 * sum(
        left[0] * right[1] - right[0] * left[1]
        for left, right in zip(
            polygon,
            polygon[1:] + polygon[:1],
            strict=True,
        )
    )


def convex_hull(points: tuple[Point, ...]) -> ConvexPolygon:
    """Return the counter-clockwise Andrew monotone-chain hull."""

    ordered = sorted(set(points))
    if len(ordered) < 3 or any(
        not math.isfinite(value)
        for point in ordered
        for value in point
    ):
        raise ValueError("convex hull requires at least three finite points")

    def cross(origin: Point, left: Point, right: Point) -> float:
        return (
            (left[0] - origin[0]) * (right[1] - origin[1])
            - (left[1] - origin[1]) * (right[0] - origin[0])
        )

    lower: list[Point] = []
    for point in ordered:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0.0:
            lower.pop()
        lower.append(point)
    upper: list[Point] = []
    for point in reversed(ordered):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0.0:
            upper.pop()
        upper.append(point)
    hull = tuple(lower[:-1] + upper[:-1])
    if len(hull) < 3 or signed_area(hull) <= 0.0:
        raise ValueError("convex hull is degenerate")
    return hull


def clip_convex_polygon_to_bounds(
    polygon: ConvexPolygon,
    bounds: ContinuousBox,
) -> ConvexPolygon:
    """Intersect one convex polygon with continuous left/top/right/bottom bounds."""

    left, top, right, bottom = bounds
    if (
        any(not math.isfinite(value) for value in bounds)
        or right <= left
        or bottom <= top
    ):
        raise ValueError("polygon clipping requires valid continuous bounds")
    if len(polygon) < 3 or signed_area(polygon) <= 0.0:
        raise ValueError("polygon clipping requires a non-degenerate CCW polygon")

    boundaries = (
        (0, left, True),
        (0, right, False),
        (1, top, True),
        (1, bottom, False),
    )
    points = list(polygon)
    for axis, limit, keep_greater in boundaries:
        if not points:
            break
        clipped: list[Point] = []
        previous = points[-1]
        previous_inside = (
            previous[axis] >= limit
            if keep_greater
            else previous[axis] <= limit
        )
        for current in points:
            current_inside = (
                current[axis] >= limit
                if keep_greater
                else current[axis] <= limit
            )
            if current_inside != previous_inside:
                delta = current[axis] - previous[axis]
                if delta == 0.0:
                    raise ValueError("polygon clipping intersection is undefined")
                fraction = (limit - previous[axis]) / delta
                other_axis = 1 - axis
                other = (
                    previous[other_axis]
                    + fraction * (current[other_axis] - previous[other_axis])
                )
                intersection = (
                    (limit, other) if axis == 0 else (other, limit)
                )
                clipped.append(intersection)
            if current_inside:
                clipped.append(current)
            previous = current
            previous_inside = current_inside
        points = clipped
    if len(points) < 3:
        raise ValueError("polygon clipping removed the complete footprint")
    return convex_hull(tuple(points))


def mapped_half_open_box(
    polygon: ConvexPolygon,
    map_point,
) -> Box:
    """Cover a mapped physical polygon with output raster sample cells.

    Integer coordinates are sample centers; index i owns [i-.5, i+.5].
    This changes representation only, never the physical crop authority.
    """

    mapped = tuple(map_point(x, y) for x, y in polygon)
    left = math.floor(min(point[0] for point in mapped) + 0.5)
    top = math.floor(min(point[1] for point in mapped) + 0.5)
    right = math.ceil(max(point[0] for point in mapped) + 0.5)
    bottom = math.ceil(max(point[1] for point in mapped) + 0.5)
    box = Box(left, top, right, bottom)
    if not box.valid():
        raise ValueError("mapped footprint is degenerate")
    return box
