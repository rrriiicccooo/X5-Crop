"""Gold-only audit of native signal, conditioned pairs and ordinal ambiguity.

The reference labels are independent evaluation data. They never enter the
detector. A raw-line match is a diagnostic, not a terminal, same-photo or
ordinal certificate; in particular, an input fit cannot certify its own pair.
"""

from __future__ import annotations

from collections import defaultdict

from x5crop.domain import ObservationId
from x5crop.detection.photo_geometry.measurement_model import PhotoBoundaryMeasurementSet
from x5crop.detection.photo_geometry.observation_types import BoundaryEdgeObservation
from x5crop.detection.photo_geometry.model import independent_spatial_support_count
from x5crop.detection.photo_geometry.template_direct_role_authority import intrinsic_direct_role_authority_bases


NATIVE_ASSOCIATION_CONTRACT = "x5crop_gold_native_association_diagnostic_v1"
_EDGE_POOLS = ("sequence_edges", "cross_height_edges", "broad_material_edges")
_TRANSITION_POOLS = ("transitions", "cross_height_transitions", "broad_material_transitions")
_DIRECT_REFERENCE_BASES = frozenset({"directly_visible", "visible_content_limit"})
_EPSILON_PX = 1.0e-7


def _contains(interval, value):
    return interval["minimum"] - _EPSILON_PX <= value <= interval["maximum"] + _EPSILON_PX


def _key(member):
    return member["scope_id"], member["record_ordinal"]


def _assignments(values, qualified):
    return [{"ordinal": ordinal, "member_keys": [list(key) for key in sorted(keys)],
             "qualified_member_keys": (None if qualified is None else [list(key) for key in sorted(keys & qualified)])}
            for ordinal, keys in sorted(values.items())]


def native_association_diagnostic(lane, references, *, count, read_proof):
    """Audit every registered pool and original member, without a pixel query.

    Call only after canonical report validation. References are canonical
    sequence lines, expressed as position at trace zero plus slope. Matching
    uses every retained transition of an edge, rather than its marginal hull
    or a favorable subset. Raw aggregate alternatives stay separate.
    """
    observations = lane["observations"]
    queries = lane["phase_input"]["sequence_measurement_sets"]
    transitions = {}
    points_by_basis = defaultdict(list)
    for query in queries:
        for field in _TRANSITION_POOLS:
            for point in query[field]:
                identity = point["transition_id"]
                if identity in transitions:
                    raise ValueError("native association audit requires unique registered transitions")
                transitions[identity] = point
                points_by_basis[field].append(point)
    intrinsic = intrinsic_direct_role_authority_bases(
        tuple(read_proof(edge, BoundaryEdgeObservation) for edge in observations["sequence_edges"]),
        tuple(read_proof(query, PhotoBoundaryMeasurementSet) for query in queries),
    )
    complete = lane["complete_phase_output"]
    proofs = {} if complete is None else {_key(member): member for member in complete["members"]}
    original = {(scope["scope_id"], member["record_ordinal"]): member
                for scope in lane["phase_competition"]["competition_scopes"] for member in scope["members"]}
    if complete is not None and proofs.keys() != original.keys():
        raise ValueError("native association audit lost complete historical membership")
    qualified = None if complete is None else {key for key, member in proofs.items() if not member["gaps"]}
    edge_ordinals = defaultdict(lambda: defaultdict(set))
    pair_ordinals = defaultdict(lambda: defaultdict(set))
    shared_contact_uses = []
    for key, member in original.items():
        bindings = member["input_fit"]["role_bindings"]
        for index, binding in enumerate(bindings):
            if binding is not None:
                role = "start" if index % 2 == 0 else "end"
                edge_ordinals[(binding["observation_id"], role)][index // 2 + 1].add(key)
        for index, (start, end) in enumerate(zip(bindings[::2], bindings[1::2], strict=True), 1):
            if start is not None and end is not None:
                pair_ordinals[(start["observation_id"], end["observation_id"])][index].add(key)
        for index in range(1, len(bindings) - 1, 2):
            end, start = bindings[index:index + 2]
            if end is not None and start is not None and end["observation_id"] == start["observation_id"]:
                shared_contact_uses.append({"member_key": list(key), "relation_ordinal": (index + 1) // 2,
                    "observation_id": end["observation_id"]})

    boundaries = []
    for reference in references:
        matches = []
        for pool in _EDGE_POOLS:
            for edge in observations[pool]:
                position = reference["position_at_trace_zero_px"] + reference["slope"] * edge["reference_trace_px"]
                marginal = _contains(edge["full_position_interval_px"], position)
                failures = []
                for identity in edge["transition_ids"]:
                    point = transitions[identity]
                    expected = reference["position_at_trace_zero_px"] + reference["slope"] * point["trace_coordinate_px"]
                    if not _contains(point["physical_position_interval_px"], expected):
                        failures.append(identity)
                if not marginal and failures:
                    continue
                matches.append({
                    "pool": pool, "observation_id": edge["observation_id"],
                    "measurement_basis": edge["measurement_basis"],
                    "native_interval_match": marginal, "complete_raw_transition_match": not failures,
                    "role_qualified": reference["role"] in edge["qualified_anchor_roles"],
                    "intrinsic_coordinate_bases": ([basis.value for basis in intrinsic.get(
                        ObservationId(edge["observation_id"]), ())] if pool == "sequence_edges" else []),
                    "transition_count": len(edge["transition_ids"]),
                    "incompatible_transition_ids": failures,
                    "conditioned_input_ordinals": _assignments(edge_ordinals.get((edge["observation_id"], reference["role"]), {}), qualified),
                })
        raw_candidates = []
        for basis, points in points_by_basis.items():
            candidates = []
            for point in points:
                expected = reference["position_at_trace_zero_px"] + reference["slope"] * point["trace_coordinate_px"]
                if _contains(point["physical_position_interval_px"], expected):
                    candidates.append({key: point[key] for key in ("transition_id", "query_id", "trace_coordinate_px",
                        "physical_position_interval_px", "localization_interval_px", "polarity")}
                        | {"localization_match": _contains(point["localization_interval_px"], expected)})
            traces = tuple(sorted({point["trace_coordinate_px"] for point in candidates}))
            query_support = []
            for query in queries:
                identity = query["query"]["query_id"]
                local_traces = tuple(sorted({point["trace_coordinate_px"] for point in candidates if point["query_id"] == identity}))
                query_support.append({"query_id": identity, "trace_coordinates_px": list(local_traces),
                    "spatial_support_region_count": independent_spatial_support_count(
                        tuple(query["query"]["trace_positions_px"]), local_traces)})
            raw_candidates.append({"basis": basis, "points": candidates, "trace_coordinates_px": list(traces),
                "query_support": query_support, "union_spatial_support_region_count": independent_spatial_support_count(
                    tuple(queries[0]["query"]["trace_positions_px"]) if queries else (), traces)})
        compatible = [item for item in matches if item["native_interval_match"] and item["complete_raw_transition_match"]]
        registered = [item for item in compatible if item["pool"] == "sequence_edges"]
        if reference["review_basis"] not in _DIRECT_REFERENCE_BASES:
            signal_class = "reference_not_direct"
        elif any(item["role_qualified"] and item["intrinsic_coordinate_bases"] for item in registered):
            signal_class = "intrinsic_coordinate_observed"
        elif any(item["role_qualified"] for item in registered):
            signal_class = "registered_role_without_intrinsic_coordinate"
        elif registered:
            signal_class = "registered_coordinate_role_unqualified"
        elif any(item["role_qualified"] for item in compatible):
            signal_class = "aggregate_raw_only"
        elif matches:
            signal_class = "interval_or_raw_constraint_match_only"
        else:
            signal_class = "no_registered_edge_match"
        boundaries.append({**reference, "signal_class": signal_class, "matches": matches,
            "raw_reference_point_candidates": raw_candidates,
            "terminal_reference": (reference["ordinal"] == 1 and reference["role"] == "start"
                or reference["ordinal"] == count and reference["role"] == "end")})

    by_role = {(item["ordinal"], item["role"]): item for item in boundaries}
    pairs = []
    for ordinal in range(1, count + 1):
        start, end = by_role.get((ordinal, "start")), by_role.get((ordinal, "end"))
        if start is None or end is None:
            continue  # A structural blank has no reference pair to match.
        start_ids, end_ids = ({item["observation_id"] for item in side["matches"]
            if item["pool"] == "sequence_edges" and item["native_interval_match"]
            and item["complete_raw_transition_match"] and item["role_qualified"]} for side in (start, end))
        conditioned = [{"start_observation_id": a, "end_observation_id": b,
                        "assignments": _assignments(values, qualified)}
                       for (a, b), values in sorted(pair_ordinals.items()) if a in start_ids and b in end_ids]
        pairs.append({"reference_ordinal": ordinal, "start_line_id": start["line_id"], "end_line_id": end["line_id"],
            "start_signal_class": start["signal_class"], "end_signal_class": end["signal_class"],
            "pair_identity_origin": "user_reference_only", "conditioned_input_pairs": conditioned})

    coordinate, mixed, holder = [], [], []
    for key, member in sorted(proofs.items()):
        association = member["native_grid_association"]
        base = {"member_key": list(key), "gaps": member["gaps"]}
        if association is not None:
            if association["grid_authority_failure"] in {"nominal_grid_state_missing", "adjacency_observation_coverage_incomplete"}:
                coordinate.append({**base, "grid_failure_kind": association["grid_authority_failure"],
                    "uncompiled_anchor_role_indices": association["uncompiled_grid_anchor_role_indices"],
                    "unqualified_anchor_role_indices": association["unqualified_grid_anchor_role_indices"]})
            crossing = [fact for fact in association["facts"] if fact["signed_gap_interval_px"] is not None
                        and fact["signed_gap_interval_px"]["minimum"] < 0 < fact["signed_gap_interval_px"]["maximum"]]
            if crossing:
                mixed.append({**base, "relations": crossing})
        admission = member["admission"]
        if admission is not None and not admission["current_holder_admitted"]:
            violations = admission["current_holder_violations"]
            if violations and all(item["observation_id"] is None and item["role_index"] in (0, 2 * count - 1)
                                  for item in violations):
                holder.append({**base, "violations": violations})
    return {
        "contract": NATIVE_ASSOCIATION_CONTRACT, "evidence_scope": "gold_only_not_runtime_authority",
        "member_count": len(original), "qualified_member_count": None if qualified is None else len(qualified),
        "member_output_evaluation_state": "not_evaluated" if complete is None else "evaluated",
        "reference_boundaries": boundaries, "reference_pairs": pairs,
        "ordinal_assignment_basis": "conditioned_original_input_fit",
        "conditioned_ordinal_conflicts": [{"observation_id": identity, "role": role, "assignments": _assignments(values, qualified)}
            for (identity, role), values in sorted(edge_ordinals.items()) if len(values) > 1],
        "shared_contact_uses": shared_contact_uses,
        "member_gap_groups_may_overlap": True, "coordinate_or_coverage_members": coordinate,
        "mixed_sign_members": mixed, "unbound_holder_terminal_members": holder,
        "complete_output_state": None if complete is None else complete["state"],
        "complete_common_output_count": None if complete is None else len(complete["common_outputs"]),
    }
