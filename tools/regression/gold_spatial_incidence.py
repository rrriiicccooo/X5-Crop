"""Candidate/reference-independent necessary bounds on native cross-axis links.

Intersecting fitted lines is not an observed pixel junction. Even overlapping
raw trace hulls are only a necessary condition: they can hide unsampled space,
disconnected fragments or an internal image line. This probe deliberately
grants no same-photo, terminal, ordinal or output authority.
"""

from __future__ import annotations

from x5crop.detection.photo_geometry.template_measurement_plan_model import (
    MAX_CROSS_FITTED_OBSERVATIONS, MAX_PHASE_OBSERVATIONS,
)

SPATIAL_INCIDENCE_CONTRACT = "x5crop_native_spatial_incidence_probe_v1"
MAX_INCIDENCE_PAIRS = MAX_PHASE_OBSERVATIONS * MAX_CROSS_FITTED_OBSERVATIONS


def _support_box(observation):
    traces = observation["trace_coordinates_px"]
    region = observation["physical_line_region"]
    if not traces or region is None:
        return None
    low, high = min(traces), max(traces)
    projected = [position + slope * (trace - region["reference_trace_px"])
                 for position, slope in region["vertices"] for trace in (low, high)]
    return (low, high), (min(projected), max(projected))


def _interval_gap(left, right):
    return max(0., left[0] - right[1], right[0] - left[1])


def native_spatial_incidence_probe(sequence_edges, side_lines):
    """Measure all native support-box separations without a candidate or gold.

    Joint physical position/slope vertices are projected at both raw trace
    endpoints. Their bounding box is conservative; overlap never certifies
    a complete physical connection. No interpolation adds observed traces.
    """
    result = {"contract": SPATIAL_INCIDENCE_CONTRACT,
        "candidate_or_reference_consumed": False,
        "same_photo_pair_authority": "unavailable",
        "terminal_authority": "unavailable",
        "ordinal_authority": "unavailable"}
    count = len(sequence_edges) * len(side_lines)
    if count > MAX_INCIDENCE_PAIRS:
        return {**result, "state": "work_bound_exceeded", "pair_check_count": 0,
                "required_pair_count": count, "measurements": []}
    sequence = [(edge["observation_id"], _support_box(edge)) for edge in sequence_edges]
    sides = [(line["observation_id"], _support_box(line)) for line in side_lines]
    measurements = []
    unavailable = overlap = disjoint = 0
    for edge_id, edge in sequence:
        for side_id, side in sides:
            if edge is None or side is None:
                unavailable += 1
                measurements.append([edge_id, side_id, None, None])
                continue
            # An edge searches long at a short trace; a side searches short at
            # a long trace. Compare in the same strip coordinate system.
            long_gap = _interval_gap(edge[1], side[0])
            short_gap = _interval_gap(edge[0], side[1])
            overlap += int(long_gap == 0. and short_gap == 0.)
            disjoint += int(long_gap > 0. or short_gap > 0.)
            measurements.append([edge_id, side_id, long_gap, short_gap])
    return {**result, "state": "measured_necessary_domains_only", "pair_check_count": count,
        "required_pair_count": count, "unavailable_domain_pair_count": unavailable,
        "overlapping_domain_pair_count": overlap, "disjoint_domain_pair_count": disjoint,
        "measurement_columns": ["sequence_observation_id", "side_observation_id",
                                "long_axis_domain_gap_px", "short_axis_domain_gap_px"],
        "measurements": measurements}
