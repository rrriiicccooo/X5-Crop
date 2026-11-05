"""Bounded native-pixel endpoint measurements, independent of fits and gold.

A measured transition component is a signal fact.  It is not a photo identity,
an exposure ordinal, a physical terminal or a permission to crop.  In
particular, a component ending inside a query can also be weak or unresolved.
"""

from __future__ import annotations

from hashlib import sha256
import math

import cv2
import numpy as np

from x5crop.domain import FiniteInterval
from x5crop.image.gray import BaseGrayParameters, _luma_u16
from x5crop.detection.photo_geometry.line_observations import PhysicalLineRegion
from x5crop.detection.photo_geometry.model import PHOTO_BOUNDARY_MEASUREMENT_SPEC as SPEC
from x5crop.detection.photo_geometry.coarse_strip_support import NATIVE_COARSE_INTENSITY_QUANTUM
from x5crop.detection.photo_geometry.registered_transition_measurement import measure_trace_rows
from x5crop.detection.photo_geometry.template_measurement_plan_model import (
    MAX_PHASE_OBSERVATIONS, MAX_CROSS_FITTED_OBSERVATIONS,
)


NATIVE_CONNECTION_CONTRACT = "x5crop_native_endpoint_pixels_v2"
_ORIGINAL_TRANSITION_FIELDS = ("transitions", "cross_height_transitions", "broad_material_transitions")


def _original_peak_anchor_reservation(original_measurements, sequence_edges, side_lines):
    """Reserve before indexing any point or reading pixels.

    Q query headers, L frozen lines, P original transitions and R line raw-ID
    references cost at most 4096+128(Q+L)+256P+512R logical visits. Each raw
    reference is examined at most twice (the two endpoints), with bounded
    scalar context checks and one component lookup. The dictionary index
    keeps references to the frozen input, not copied measurement arrays.
    8192+1024(Q+L+P+2R) bytes cover the index, duplicate/missing-ID lists and
    both endpoints' small response dictionaries. Original ref payloads are
    retained as references, never recursively copied or reinterpreted.

    These are complete required reservations, including on a failed batch;
    they do not claim that failed preflight performed the indexed work.
    """
    if original_measurements is None:
        return {"original_peak_anchor_input_state": "not_provided",
                "original_peak_anchor_input_query_count": None,
                "original_peak_anchor_input_line_count": None,
                "original_peak_anchor_input_transition_count": None,
                "original_peak_anchor_line_transition_reference_count": None,
                "original_peak_anchor_value_work": 0, "original_peak_anchor_retained_bytes": 0}
    if not isinstance(original_measurements, (list, tuple)):
        raise ValueError("original measurements must be the complete query list or None")
    points = 0
    for measurement in original_measurements:
        if not isinstance(measurement, dict):
            raise ValueError("original measurement must be a query dictionary")
        for name in _ORIGINAL_TRANSITION_FIELDS:
            values = measurement.get(name, ())
            if not isinstance(values, (list, tuple)):
                raise ValueError("original transition batches must be arrays")
            points += len(values)
    lines = (*sequence_edges, *side_lines)
    references = 0
    for line in lines:
        identities = line.get("transition_ids", ())
        if not isinstance(identities, (list, tuple)):
            raise ValueError("original line transition IDs must be an array")
        references += len(identities)
    queries, line_count = len(original_measurements), len(lines)
    return {"original_peak_anchor_input_state": "provided",
            "original_peak_anchor_input_query_count": queries,
            "original_peak_anchor_input_line_count": line_count,
            "original_peak_anchor_input_transition_count": points,
            "original_peak_anchor_line_transition_reference_count": references,
            "original_peak_anchor_value_work": 4096+128*(queries+line_count)+256*points+512*references,
            "original_peak_anchor_retained_bytes": 8192+1024*(queries+line_count+points+2*references)}


def _original_transition_index(original_measurements):
    """Index exact raw IDs; duplicates are unavailable rather than aliases."""
    by_id, ambiguous = {}, set()
    for measurement in original_measurements:
        for kind in _ORIGINAL_TRANSITION_FIELDS:
            for point in measurement.get(kind, ()):
                identity = point.get("transition_id") if isinstance(point, dict) else None
                if not isinstance(identity, str) or not identity:
                    continue
                if identity in by_id:
                    ambiguous.add(identity)
                else:
                    by_id[identity] = measurement, point, kind
    return by_id, ambiguous


def _unprovided_original_anchors():
    return {"original_peak_anchor_completeness": "not_provided",
            "original_peak_anchor_response_state": "unavailable",
            "original_peak_anchor_failure_kinds": ["original_measurements_not_provided"],
            "original_peak_anchor_missing_transition_ids": None,
            "original_peak_anchor_ambiguous_transition_ids": None,
            "original_peak_anchor_responses": []}


def _original_pixel_record(identity, measurement, point, kind, expected_axis):
    """Keep the original selected pixel, without asserting native16 identity."""
    query = measurement.get("query", {})
    if not isinstance(query, dict):
        query = {}
    coverage = measurement.get("coverage", {})
    reference = point.get("peak_source")
    sample = point.get("texture_sample_coordinate_px")
    coordinate = reference.get("source_coordinate_px") if isinstance(reference, dict) else sample
    trace, polarity = point.get("trace_coordinate_px"), point.get("polarity")
    record = {"transition_id": identity, "query_id": point.get("query_id"),
        "boundary_axis": query.get("boundary_axis"), "trace_coordinate_px": trace,
        "texture_sample_coordinate_px": sample, "source_coordinate_px": coordinate,
        "original_polarity": polarity, "peak_source": reference, "original_transition_kind": kind,
        "canonical_source_pixel_xy": None, "state": "unavailable", "failure_kind": None,
        "native_component_label": None, "native_component_reaches_query_edge": None,
        "response_basis": "native16_response_at_registered_original_pixel_only"}
    failure = None
    if (not isinstance(query.get("query_id"), str) or not query["query_id"]
            or point.get("query_id") != query["query_id"]):
        failure = "original_query_id_conflict"
    elif query.get("boundary_axis") != expected_axis:
        failure = "original_query_axis_mismatch"
    elif not isinstance(coverage, dict) or coverage.get("complete") is not True:
        failure = "original_query_incomplete"
    elif type(sample) is not int or sample < 0 or type(trace) is not int or trace < 0:
        failure = "original_pixel_unavailable"
    elif type(polarity) is not int or polarity not in (-1, 1):
        failure = "original_polarity_unavailable"
    elif reference is not None and (not isinstance(reference, dict)
            or not isinstance(reference.get("group_id"), str) or not reference["group_id"]
            or type(reference.get("candidate_ordinal")) is not int or reference["candidate_ordinal"] < 0
            or type(reference.get("source_coordinate_px")) is not int or coordinate != sample
            or type(reference.get("polarity")) is not int or reference["polarity"] != polarity):
        failure = "original_peak_source_conflict"
    else:
        ordinal = point.get("trace_ordinal")
        traces = query.get("trace_positions_px", ())
        searches = query.get("search_intervals_px", ())
        ownership = query.get("transition_ownership_intervals_px", ())
        if (any(not isinstance(values, (list, tuple)) for values in (traces, searches, ownership))
                or type(ordinal) is not int or ordinal < 0 or ordinal >= len(traces)
                or ordinal >= len(searches) or ordinal >= len(ownership) or traces[ordinal] != trace):
            failure = "original_query_trace_unavailable"
        else:
            for interval in (searches[ordinal], ownership[ordinal]):
                low, high = ((interval.get("minimum"), interval.get("maximum"))
                             if isinstance(interval, dict) else (None, None))
                if (type(low) not in (int, float) or type(high) not in (int, float)
                        or not math.isfinite(low) or not math.isfinite(high)
                        or not low <= coordinate <= high):
                    failure = "original_pixel_outside_query"
                    break
    if failure is None:
        record["canonical_source_pixel_xy"] = ([coordinate, trace] if expected_axis == "x" else [trace, coordinate])
    record["failure_kind"] = failure
    return record


def _original_anchor_metadata(queries, sequence_edges, side_lines, original_measurements, layout):
    if original_measurements is None:
        return {index: _unprovided_original_anchors() for index in range(len(queries))}
    by_id, ambiguous = _original_transition_index(original_measurements)
    lines = {(axis, line["observation_id"]): line for axis, values in
             (("long", sequence_edges), ("short", side_lines)) for line in values}
    result = {}
    for index, query in enumerate(queries):
        line = lines[query["axis"], query["observation_id"]]
        identities = line.get("transition_ids", ())
        missing = [identity for identity in identities if not isinstance(identity, str) or identity not in by_id]
        duplicates = [identity for identity in identities if isinstance(identity, str) and identity in ambiguous]
        failures, responses = [], []
        if not identities:
            failures.append("original_transition_ids_unavailable")
        if missing:
            failures.append("original_transition_ids_missing")
        if duplicates:
            failures.append("original_transition_ids_ambiguous")
        axis = "x" if (query["axis"] == "long") == (layout == "horizontal") else "y"
        for identity in identities:
            if not isinstance(identity, str) or identity not in by_id or identity in ambiguous:
                continue
            measurement, point, kind = by_id[identity]
            original = _original_pixel_record(identity, measurement, point, kind, axis)
            if original["failure_kind"] is not None and original["failure_kind"] not in failures:
                failures.append(original["failure_kind"])
            if point.get("trace_coordinate_px") == query.get("trace_px"):
                responses.append(original)
        if not responses:
            failures.append("original_endpoint_transition_unavailable")
        if failures:
            for response in responses:
                response["failure_kind"] = response["failure_kind"] or "original_transition_set_incomplete"
        result[index] = {"original_peak_anchor_completeness": "incomplete" if failures else "complete",
            "original_peak_anchor_response_state": "unavailable",
            "original_peak_anchor_failure_kinds": failures,
            "original_peak_anchor_missing_transition_ids": missing,
            "original_peak_anchor_ambiguous_transition_ids": duplicates,
            "original_peak_anchor_responses": responses}
    return result


def _region(raw):
    return None if raw is None else PhysicalLineRegion(
        raw["reference_trace_px"], tuple(map(tuple, raw["vertices"])))


def _endpoint_queries(sequence_edges, side_lines, scales):
    """Freeze axis-local (coordinate, trace) boxes before reading any pixel."""
    result = []
    for axis, lines in (("long", sequence_edges), ("short", side_lines)):
        coordinate_scale = scales["width_axis_px_per_mm" if axis == "long" else "height_axis_px_per_mm"]["maximum"]
        trace_scale = scales["height_axis_px_per_mm" if axis == "long" else "width_axis_px_per_mm"]["maximum"]
        halo = SPEC.measurement_halo_px(coordinate_scale)
        for line in lines:
            traces = line["trace_coordinates_px"]
            if not traces:
                result.append({"observation_id": line["observation_id"], "axis": axis,
                               "state": "native_trace_domain_unavailable"})
                continue
            region = _region(line["physical_line_region"])
            # The existing two-sided measurement kernel defines the local
            # field. It does not cover a whole gap between registered traces
            # or declare any continuation outside this neighborhood complete.
            radius = SPEC.measurement_halo_px(trace_scale)
            for end, trace in (("minimum_trace", min(traces)), ("maximum_trace", max(traces))):
                trace_low, trace_high = math.floor(trace - radius), math.ceil(trace + radius) + 1
                if region is not None:
                    bounds = (region.project(trace_low), region.project(trace_high - 1))
                    low, high = min(i.minimum for i in bounds), max(i.maximum for i in bounds)
                    anchor = region.project(trace)
                    basis = "joint_native_position_slope_region"
                elif axis == "long":
                    raw = line["full_position_interval_px"]
                    direction = line["full_direction_interval_degrees"]
                    slopes = ((-math.tan(math.radians(SPEC.maximum_measurable_line_angle_degrees)),
                               math.tan(math.radians(SPEC.maximum_measurable_line_angle_degrees)))
                              if direction is None else tuple(math.tan(math.radians(direction[k])) for k in ("minimum", "maximum")))
                    distance = tuple(t - line["reference_trace_px"] for t in (trace_low, trace_high - 1))
                    departures = tuple(s * d for s in slopes for d in distance)
                    low, high = raw["minimum"] + min(departures), raw["maximum"] + max(departures)
                    anchor_departures = tuple(s * (trace - line["reference_trace_px"]) for s in slopes)
                    anchor = FiniteInterval(raw["minimum"] + min(anchor_departures), raw["maximum"] + max(anchor_departures))
                    basis = "registered_full_interval_and_direction_search_bound"
                else:
                    intervals = [interval for t, interval in zip(traces, line["trace_position_intervals_px"], strict=True) if t == trace]
                    anchor = FiniteInterval(min(i["minimum"] for i in intervals), max(i["maximum"] for i in intervals))
                    departure = math.tan(math.radians(SPEC.maximum_measurable_line_angle_degrees)) * radius
                    low, high = anchor.minimum - departure, anchor.maximum + departure
                    basis = "original_raw_trace_interval_and_direction_search_bound"
                result.append({"observation_id": line["observation_id"], "axis": axis,
                    "endpoint": end, "trace_px": trace, "anchor_interval_px": (anchor.minimum, anchor.maximum),
                    "trace_radius_px": radius,
                    "coordinate_scale_px_per_mm": coordinate_scale, "query_basis": basis,
                    "requested_strip_box": (math.floor(low) - halo, trace_low, math.ceil(high) + halo + 1, trace_high),
                    "state": "registered"})
    return result


def _merged_ranges(intervals):
    merged = []
    for low, high in sorted(intervals):
        if merged and low <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(high, merged[-1][1]))
        else:
            merged.append((low, high))
    return tuple(merged)


def _normalization_plan(source, queries):
    plans = []
    for axis in ("long", "short"):
        field = source if axis == "long" else source.transpose(1, 0, 2)
        selected = [q for q in queries if q["state"] == "registered" and q["axis"] == axis]
        if not selected:
            continue
        scale = selected[0]["coordinate_scale_px_per_mm"]
        if any(q["coordinate_scale_px_per_mm"] != scale for q in selected):
            raise ValueError("native normalization cannot mix source scales")
        intervals = _merged_ranges((q["sampled_strip_box"][1], q["sampled_strip_box"][3])for q in selected)
        rows = sum(high - low for low, high in intervals)
        halo = SPEC.measurement_halo_px(scale)
        coordinates = max(0, field.shape[1] - 2 * halo) * rows
        plans.append({"axis": axis, "trace_intervals_px": intervals,
            "coordinate_interval_px": (0, field.shape[1]), "coordinate_scale_px_per_mm": scale,
            "pixel_work_bound": 3 * field.shape[1] * rows + coordinates * (2 * halo + 2)})
    return plans


def _measure_profiles(source, queries, plans, memory_limit):
    masks = {index: (np.zeros((q["sampled_strip_box"][3] - q["sampled_strip_box"][1],
                             q["sampled_strip_box"][2] - q["sampled_strip_box"][0]), dtype=np.uint8),
                     np.zeros((q["sampled_strip_box"][3] - q["sampled_strip_box"][1],
                               q["sampled_strip_box"][2] - q["sampled_strip_box"][0]), dtype=np.uint8))
             for index, q in enumerate(queries) if q["state"] == "registered"}
    retained = sum(mask.nbytes for pair in masks.values()for mask in pair)
    peak = retained
    for plan in plans:
        field = source if plan["axis"] == "long" else source.transpose(1, 0, 2)
        selected = [(index, q)for index, q in enumerate(queries)if index in masks and q["axis"] == plan["axis"]]
        width = field.shape[1]
        batch_rows = min(SPEC.maximum_streaming_block_pixels // width,
                         (memory_limit - retained) // (320 * width))
        if batch_rows < 1:
            raise ValueError("native profile batch was not reserved")
        for low, high in plan["trace_intervals_px"]:
            for start in range(low, high, batch_rows):
                block = field[start:min(high, start + batch_rows)]
                luma = np.empty(block.shape[:2], dtype=np.float32)
                scratch = np.empty_like(luma)
                _luma_u16(block, luma, scratch, BaseGrayParameters())
                measured = measure_trace_rows(luma, FiniteInterval(0., width - 1.),
                    plan["coordinate_scale_px_per_mm"], SPEC, intensity_quantum=NATIVE_COARSE_INTENSITY_QUANTUM)
                supported = ((measured.gradient_z >= SPEC.gradient_z_minimum)
                    & (np.maximum(measured.tone_z, measured.texture_z) >= SPEC.tone_or_texture_z_minimum))
                # Eight retained float64 responses, plus maximum/comparison/
                # polarity masks. The row helper's construction peak and the
                # subsequent derived-mask peak are alternative live phases.
                response_peak = (measured.coordinates.nbytes + 8 * measured.gradient_z.nbytes
                                 + 16 * measured.gradient_z.size)
                peak = max(peak, retained + max(measured.temporary_bytes, response_peak)
                           + luma.nbytes + scratch.nbytes)
                first = int(measured.coordinates[0]) if measured.coordinates.size else width
                stop = int(measured.coordinates[-1]) + 1 if measured.coordinates.size else width
                for index, query in selected:
                    left, top, right, bottom = query["sampled_strip_box"]
                    y0, y1 = max(top, start), min(bottom, start + block.shape[0])
                    x0, x1 = max(left, first), min(right, stop)
                    if y1 <= y0 or x1 <= x0:
                        continue
                    rows = slice(y0 - start, y1 - start)
                    columns = slice(x0 - first, x1 - first)
                    for mask, polarity in zip(masks[index], (1, -1), strict=True):
                        mask[y0 - top:y1 - top, x0 - left:x1 - left] = (
                            supported[rows, columns] & (polarity * measured.signed_gradient[rows, columns] > 0.))
                del measured, luma, scratch, supported
    return masks, peak


def _measure_query(source, query, memory_limit, *, masks, retained_profile_bytes=0,
                   original_anchor_metadata=None):
    left, top, right, bottom = query["sampled_strip_box"]
    rgb = source[top:bottom, left:right]
    rows, columns = rgb.shape[:2]
    scale = query["coordinate_scale_px_per_mm"]
    halo = SPEC.measurement_halo_px(scale)
    measured_coordinates = rows * max(0, min(right, source.shape[1] - halo) - max(left, halo))
    peak = retained_profile_bytes + 96 * rows * columns
    if peak > memory_limit:
        raise ValueError("native endpoint masks exceeded their reserved source memory")
    anchor_row = min(rows - 1, max(0, round(query["trace_px"]) - top))
    low, high = query["anchor_interval_px"]
    anchor_low = max(0, math.ceil(low) - left)
    anchor_high = min(columns, math.floor(high) - left + 1)
    original = (_unprovided_original_anchors() if original_anchor_metadata is None else original_anchor_metadata)
    for response in original["original_peak_anchor_responses"]:
        if response["failure_kind"] is not None:
            continue
        row = response["trace_coordinate_px"]-top
        column = response["source_coordinate_px"]-left
        if not 0 <= row < rows or not 0 <= column < columns:
            response["failure_kind"] = "native_query_pixel_unobserved"
        elif not halo <= response["source_coordinate_px"] < source.shape[1]-halo:
            response["failure_kind"] = "native_kernel_unobservable"
    directions = []
    for mask, polarity in zip(masks, (1, -1), strict=True):
        count, labels = cv2.connectedComponents(mask, connectivity=4, ltype=cv2.CV_32S)
        anchor = set(np.unique(labels[anchor_row, anchor_low:anchor_high])) - {0}
        outer = set(np.unique(labels[0 if query["endpoint"] == "minimum_trace" else -1])) - {0}
        directions.append({"polarity": polarity, "component_count": count - 1,
            "anchor_component_count": len(anchor), "anchor_components_reaching_query_edge_count": len(anchor & outer)})
        for response in original["original_peak_anchor_responses"]:
            if response["failure_kind"] is not None or response["original_polarity"] != polarity:
                continue
            component = int(labels[response["trace_coordinate_px"]-top, response["source_coordinate_px"]-left])
            response["native_component_label"] = component
            response["native_component_reaches_query_edge"] = bool(component and component in outer)
            response["state"] = "supported" if component else "unavailable"
            response["failure_kind"] = None if component else "native_signal_unavailable"
    if (original["original_peak_anchor_completeness"] == "complete"
            and all(response["state"] == "supported" for response in original["original_peak_anchor_responses"])):
        original["original_peak_anchor_response_state"] = "supported"
    return {"query": query, "state": "measured_local_signal_only",
        "native_rgb_sha256": sha256(rgb.tobytes(order="C")).hexdigest(),
        "pixel_count": rows * columns, "measured_profile_coordinate_count": measured_coordinates,
        "profile_state": "source_trace_baseline_measured",
        "kernel_unobserved_coordinate_columns": columns - measured_coordinates // rows,
        "step_components": directions, **original,
        "peak_temporary_bytes": peak}


def native_local_connection_diagnostic(source_rgb, *, layout, sequence_edges, side_lines, scales,
                                       existing_pixel_work=0, original_measurements=None):
    """Read all frozen endpoint neighborhoods, never a candidate or reference.

    Raw native luma uses the same Rec.709 owner and 1-code native quantum as
    the registered coarse-short measurement. There is no percentile clipping,
    favorable patch selection, morphology, gap closing or material classifier.
    """
    if (source_rgb.dtype != np.uint16 or source_rgb.ndim != 3 or source_rgb.shape[2] != 3
            or layout not in {"horizontal", "vertical"}):
        raise ValueError("native connection measurement requires canonical uint16 RGB and layout")
    if isinstance(existing_pixel_work, bool) or not isinstance(existing_pixel_work, int) or existing_pixel_work < 0:
        raise ValueError("existing native pixel work must be a non-negative integer")
    result = {"contract": NATIVE_CONNECTION_CONTRACT, "candidate_or_reference_consumed": False,
        "query_scope": "registered_trace_endpoint_measurement_kernel_neighborhoods",
        "intensity_basis": "native_rgb_rec709_luma", "intensity_quantum": NATIVE_COARSE_INTENSITY_QUANTUM,
        "same_photo_pair_authority": "unavailable", "terminal_authority": "unavailable", "ordinal_authority": "unavailable",
        "boundary_identity_authority": "unavailable",
        "original_peak_anchor_context": "native16_and_registered_gray8_contexts_differ",
        "original_peak_anchor_input_state": "not_provided" if original_measurements is None else "provided",
        "original_peak_anchor_processing_state": "not_started"}
    if len(sequence_edges) > MAX_PHASE_OBSERVATIONS or len(side_lines) > MAX_CROSS_FITTED_OBSERVATIONS:
        return {**result, "state": "work_bound_exceeded", "bound_failures": ["observation_count"], "queries": []}
    source = source_rgb if layout == "horizontal" else source_rgb.transpose(1, 0, 2)
    reservation = _original_peak_anchor_reservation(original_measurements, sequence_edges, side_lines)
    result.update(reservation)
    original_work = reservation["original_peak_anchor_value_work"]
    original_bytes = reservation["original_peak_anchor_retained_bytes"]
    queries = _endpoint_queries(sequence_edges, side_lines, scales)
    source_pixels = source.shape[0] * source.shape[1]
    work = 0
    mask_work = 0
    memory_limit = 10 * source_pixels + 32 * 1024 * 1024
    for query in queries:
        if query["state"] != "registered":
            continue
        left, top, right, bottom = query["requested_strip_box"]
        field = source if query["axis"] == "long" else source.transpose(1, 0, 2)
        sampled = (max(0, left), max(0, top), min(field.shape[1], right), min(field.shape[0], bottom))
        query["source_clipped"] = sampled != (left, top, right, bottom)
        query["sampled_strip_box"] = sampled
        width, height = max(0, sampled[2] - sampled[0]), max(0, sampled[3] - sampled[1])
        if not width or not height:
            query["state"] = "outside_source"
            continue
        # Source reads for the three-channel patch identity. Profile source
        # reads are reserved once per merged full-row normalization query.
        # Component labeling reads derived masks, not additional source pixels.
        query["pixel_work_bound"] = 3 * width * height
        query["mask_site_work_bound"] = 10 * width * height + 4 * width
        work += query["pixel_work_bound"]
        mask_work += query["mask_site_work_bound"]
    normalization = _normalization_plan(source, queries)
    work += sum(plan["pixel_work_bound"]for plan in normalization)
    retained_profiles = 2 * sum((q["sampled_strip_box"][2] - q["sampled_strip_box"][0])
        * (q["sampled_strip_box"][3] - q["sampled_strip_box"][1])
        for q in queries if q["state"] == "registered")
    memory_exceeded = original_bytes > memory_limit or any(original_bytes + retained_profiles + 320 * plan["coordinate_interval_px"][1] > memory_limit
                          for plan in normalization)
    memory_exceeded |= any(original_bytes + retained_profiles + 96 * (q["sampled_strip_box"][2] - q["sampled_strip_box"][0])
        * (q["sampled_strip_box"][3] - q["sampled_strip_box"][1]) > memory_limit for q in queries if q["state"] == "registered")
    if work + existing_pixel_work + original_work > 128 * source_pixels or memory_exceeded:
        return {**result, "state": "work_bound_exceeded", "registered_query_count": len(queries),
            "bound_failures": [reason for reason, exceeded in (
                ("pixel_work", work + existing_pixel_work + original_work > 128 * source_pixels), ("temporary_memory", memory_exceeded)) if exceeded],
            "registered_pixel_work": work, "existing_pixel_work": existing_pixel_work,
            "mask_site_work_bound": mask_work, "pixel_work_limit": 128 * source_pixels, "queries": []}
    originals = _original_anchor_metadata(queries, sequence_edges, side_lines, original_measurements, layout)
    masks, profile_peak = _measure_profiles(source, queries, normalization, memory_limit-original_bytes)
    measured = []
    for index, query in enumerate(queries):
        if query["state"] != "registered":
            original = originals[index]
            for response in original["original_peak_anchor_responses"]:
                response["failure_kind"] = response["failure_kind"] or "native_query_unavailable"
            measured.append({"query": query, "state": query["state"], **original})
            continue
        if query["axis"] == "long":
            measured.append(_measure_query(source, query, memory_limit, masks=masks[index],
                retained_profile_bytes=retained_profiles+original_bytes, original_anchor_metadata=originals[index]))
        else:
            measured.append(_measure_query(source.transpose(1, 0, 2), query, memory_limit, masks=masks[index],
                retained_profile_bytes=retained_profiles+original_bytes, original_anchor_metadata=originals[index]))
    return {**result, "state": "measured_native_endpoint_neighborhoods", "registered_query_count": len(queries),
        "completed_query_count": sum(item["state"] == "measured_local_signal_only" for item in measured),
        "source_clipped_query_count": sum(q.get("source_clipped", False) for q in queries),
        "anchor_signal_query_count": sum(any(c["anchor_component_count"] for c in item.get("step_components", ())) for item in measured),
        "continuing_signal_query_count": sum(any(c["anchor_components_reaching_query_edge_count"] for c in item.get("step_components", ())) for item in measured),
        "registered_pixel_work": work, "existing_pixel_work": existing_pixel_work,
        "pixel_work_limit": 128 * source_pixels,
        "mask_site_work_bound": mask_work, "normalization_queries": normalization,
        "original_peak_anchor_processing_state": "not_provided" if original_measurements is None else "completed",
        "peak_temporary_bytes": max(profile_peak+original_bytes, max((m.get("peak_temporary_bytes", 0)for m in measured),default=0)),
        "queries": measured}
