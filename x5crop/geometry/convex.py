from __future__ import annotations

import math

from ..domain import Box


Point = tuple[float, float]
ConvexPolygon = tuple[Point, ...]


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


def _clip_half_plane(
    polygon: ConvexPolygon,
    *,
    inside,
    intersection,
) -> ConvexPolygon:
    if not polygon:
        return ()
    output: list[Point] = []
    previous = polygon[-1]
    previous_inside = inside(previous)
    for current in polygon:
        current_inside = inside(current)
        if current_inside:
            if not previous_inside:
                output.append(intersection(previous, current))
            output.append(current)
        elif previous_inside:
            output.append(intersection(previous, current))
        previous = current
        previous_inside = current_inside
    return tuple(output)


def clip_convex_polygon_to_box(
    polygon: ConvexPolygon,
    authority: Box,
) -> ConvexPolygon:
    """Clip source pixel-center geometry in left/top/right/bottom order."""

    if not authority.valid():
        raise ValueError("polygon clipping requires a valid authority box")
    left = float(authority.left)
    top = float(authority.top)
    right = float(authority.right - 1)
    bottom = float(authority.bottom - 1)

    def vertical(boundary: float):
        def intersect(start: Point, end: Point) -> Point:
            delta = end[0] - start[0]
            if delta == 0.0:
                return (boundary, start[1])
            factor = (boundary - start[0]) / delta
            return (boundary, start[1] + factor * (end[1] - start[1]))

        return intersect

    def horizontal(boundary: float):
        def intersect(start: Point, end: Point) -> Point:
            delta = end[1] - start[1]
            if delta == 0.0:
                return (start[0], boundary)
            factor = (boundary - start[1]) / delta
            return (start[0] + factor * (end[0] - start[0]), boundary)

        return intersect

    clipped = _clip_half_plane(
        polygon,
        inside=lambda point: point[0] >= left,
        intersection=vertical(left),
    )
    clipped = _clip_half_plane(
        clipped,
        inside=lambda point: point[1] >= top,
        intersection=horizontal(top),
    )
    clipped = _clip_half_plane(
        clipped,
        inside=lambda point: point[0] <= right,
        intersection=vertical(right),
    )
    clipped = _clip_half_plane(
        clipped,
        inside=lambda point: point[1] <= bottom,
        intersection=horizontal(bottom),
    )
    if len(clipped) < 3:
        raise ValueError("authority intersection is empty or degenerate")
    return convex_hull(clipped)


def mapped_half_open_box(
    polygon: ConvexPolygon,
    map_point,
) -> Box:
    mapped = tuple(map_point(x, y) for x, y in polygon)
    left = math.floor(min(point[0] for point in mapped))
    top = math.floor(min(point[1] for point in mapped))
    right = math.ceil(
        math.nextafter(max(point[0] for point in mapped), math.inf)
    )
    bottom = math.ceil(
        math.nextafter(max(point[1] for point in mapped), math.inf)
    )
    box = Box(left, top, right, bottom)
    if not box.valid():
        raise ValueError("mapped footprint is degenerate")
    return box
