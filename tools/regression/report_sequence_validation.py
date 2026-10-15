"""Validate current sequence topology, role and width evidence."""

from __future__ import annotations

from .report_value_validation import (
    _finite_number,
    _interval_contains,
    _valid_ids,
    _valid_interval,
)


_SOURCE_FRAME_WIDTH_AUTHORITY_FIELDS = {
    "authority_id",
    "state",
    "placement_scope",
    "placement_integer_slot_offset",
    "placement_phase_anchor_observation_ids",
    "supporting_role_observation_ids",
    "basis",
    "supporting_frame_ordinals",
    "supporting_constraint_ids",
    "width_px",
    "canonical_width_px",
    "observation_ids",
    "failure_kind",
    "reason",
}

_SOURCE_FRAME_WIDTH_FAILURE_KINDS = {
    "placement_hypothesis_unavailable",
    "direct_role_authority_unavailable",
    "source_width_closure_unavailable",
    "physical_width_conflict",
}


def _validate_adjacency_coverage(value: object, *, read_proof) -> None:
    from x5crop.detection.photo_geometry.template_adjacency_coverage import AdjacencyObservationCoverage

    if not isinstance(value, list):
        raise ValueError("adjacency coverage summary is invalid")
    coverage = tuple(read_proof(item, AdjacencyObservationCoverage) for item in value)
    if [item.relation_ordinal for item in coverage] != list(range(1, len(coverage) + 1)):
        raise ValueError("adjacency coverage ordinals are invalid")


def _validate_adjacency_continuity(value: object, *, read_proof) -> None:
    from x5crop.detection.photo_geometry.template_adjacency_topology import AdjacencyContinuityObservation

    if not isinstance(value, list):
        raise ValueError("adjacency continuity summary is invalid")
    observations = tuple(read_proof(item, AdjacencyContinuityObservation) for item in value)
    if len({item.observation_id for item in observations}) != len(observations):
        raise ValueError("adjacency continuity identities are not unique")
    for item in observations:
        if not all((*item.covering_query_ids, *item.separator_band_observation_ids)) or any(
            identity == "" for identity in (item.end_observation_id,
                item.next_start_observation_id, item.contact_observation_id, item.overlap_observation_id)
        ):
            raise ValueError("adjacency continuity identity is invalid")
    if [item.relation_ordinal for item in observations] != list(range(1, len(observations) + 1)):
        raise ValueError("adjacency continuity ordinals are invalid")


def _validate_adjacency_relations(
    value: object,
) -> dict[str, tuple[str, int]]:
    """Validate the serialized adjacency sum type and return topologies."""

    if not isinstance(value, list):
        raise ValueError("adjacency relation summary is invalid")
    ordinals: list[int] = []
    topologies: dict[str, tuple[str, int]] = {}
    separator_fields = {
        "relation_ordinal",
        "kind",
        "delta_interval_px",
        "canonical_delta_px",
        "separator_band_observation_id",
        "end_edge_observation_id",
        "next_start_edge_observation_id",
        "signed_gap_interval_px",
        "canonical_signed_gap_px",
    }
    contact_fields = {
        "relation_ordinal",
        "contact_observation_id",
        "physical_edge_id",
        "shared_edge_observation_id",
        "delta_interval_px",
        "canonical_delta_px",
        "supporting_observation_ids",
        "kind",
    }
    overlap_fields = {
        "relation_ordinal",
        "overlap_observation_id",
        "end_edge_observation_id",
        "next_start_edge_observation_id",
        "signed_gap_interval_px",
        "canonical_signed_gap_px",
        "delta_interval_px",
        "canonical_delta_px",
        "supporting_observation_ids",
        "kind",
    }
    for relation in value:
        if not isinstance(relation, dict):
            raise ValueError("adjacency relation is invalid")
        fields = set(relation)
        ordinal = relation.get("relation_ordinal")
        interval = relation.get("delta_interval_px")
        canonical = relation.get("canonical_delta_px")
        if (
            not isinstance(ordinal, int)
            or ordinal <= 0
            or not _valid_interval(interval)
            or not _interval_contains(interval, canonical)
        ):
            raise ValueError("adjacency relation geometry is invalid")
        ordinals.append(ordinal)
        if fields == separator_fields:
            kind = relation["kind"]
            direct_ids = (
                relation["separator_band_observation_id"],
                relation["end_edge_observation_id"],
                relation["next_start_edge_observation_id"],
            )
            signed_gap = relation["signed_gap_interval_px"]
            canonical_signed_gap = relation["canonical_signed_gap_px"]
            if (
                kind not in {"nominal", "normal", "wide", "narrow"}
                or (kind == "nominal")
                != (
                    interval == {"minimum": 0.0, "maximum": 0.0}
                    and float(canonical) == 0.0
                    and all(identity is None for identity in direct_ids)
                    and signed_gap is None
                    and canonical_signed_gap is None
                )
                or (
                    kind != "nominal"
                    and (
                        any(
                            not isinstance(identity, str) or not identity
                            for identity in direct_ids
                        )
                        or len(set(direct_ids)) != len(direct_ids)
                        or not _valid_interval(signed_gap)
                        or float(signed_gap["minimum"]) <= 0.0
                        or not _interval_contains(
                            signed_gap,
                            canonical_signed_gap,
                        )
                        or (
                            kind == "normal"
                            and abs(float(canonical)) > 1.0e-9
                        )
                        or (kind == "wide" and float(canonical) <= 0.0)
                        or (kind == "narrow" and float(canonical) >= 0.0)
                    )
                )
            ):
                raise ValueError("separator relation is invalid")
            continue
        if fields == contact_fields and relation["kind"] == "contact":
            contact_id = relation["contact_observation_id"]
            physical_id = relation["physical_edge_id"]
            shared_id = relation["shared_edge_observation_id"]
            supporting_ids = relation["supporting_observation_ids"]
            if (
                any(
                    not isinstance(identity, str) or not identity
                    for identity in (contact_id, physical_id, shared_id)
                )
                or physical_id != shared_id
                or not _valid_ids(supporting_ids, allow_empty=False)
                or supporting_ids != list(dict.fromkeys(supporting_ids))
                or physical_id not in supporting_ids
                or contact_id in topologies
            ):
                raise ValueError("contact relation is invalid")
            topologies[contact_id] = ("contact", ordinal)
            continue
        if fields != overlap_fields or relation["kind"] != "overlap":
            raise ValueError("adjacency relation sum type is invalid")
        overlap_id = relation["overlap_observation_id"]
        end_id = relation["end_edge_observation_id"]
        start_id = relation["next_start_edge_observation_id"]
        signed_gap = relation["signed_gap_interval_px"]
        canonical_signed_gap = relation["canonical_signed_gap_px"]
        supporting_ids = relation["supporting_observation_ids"]
        if (
            any(
                not isinstance(identity, str) or not identity
                for identity in (overlap_id, end_id, start_id)
            )
            or end_id == start_id
            or overlap_id in topologies
            or not _valid_interval(signed_gap)
            or float(signed_gap["maximum"]) >= 0.0
            or not _interval_contains(signed_gap, canonical_signed_gap)
            or supporting_ids != [end_id, start_id]
        ):
            raise ValueError("overlap relation is invalid")
        topologies[overlap_id] = ("overlap", ordinal)
    if ordinals != list(range(1, len(ordinals) + 1)):
        raise ValueError("adjacency relation ordinals are invalid")
    return topologies


def _validate_contact_edge_observations(value: object) -> dict[str, str]:
    """Validate role-free contact proposals without granting placement."""

    if not isinstance(value, list):
        raise ValueError("contact-edge observation summary is invalid")
    observations: dict[str, str] = {}
    fields = {
        "observation_id",
        "physical_edge_id",
        "shared_edge_observation_id",
        "authority_bases",
        "qualified_anchor_roles",
    }
    for observation in value:
        if not isinstance(observation, dict) or set(observation) != fields:
            raise ValueError("contact-edge observation is invalid")
        identity = observation["observation_id"]
        physical_id = observation["physical_edge_id"]
        shared_id = observation["shared_edge_observation_id"]
        bases = observation["authority_bases"]
        roles = observation["qualified_anchor_roles"]
        if (
            any(
                not isinstance(item, str) or not item
                for item in (identity, physical_id, shared_id)
            )
            or physical_id != shared_id
            or identity in observations
            or not isinstance(bases, list)
            or not bases
            or bases != list(dict.fromkeys(bases))
            or any(
                item not in {"source_wide_edge", "aggregate_union"}
                for item in bases
            )
            or not isinstance(roles, list)
            or not roles
            or roles != list(dict.fromkeys(roles))
            or any(item not in {"start", "end"} for item in roles)
        ):
            raise ValueError("contact-edge observation is invalid")
        observations[identity] = shared_id
    return observations


def _validate_overlap_edge_pair_observations(
    value: object,
) -> dict[str, tuple[str, str]]:
    """Validate ordinal-free overlap proposals without granting placement."""

    if not isinstance(value, list):
        raise ValueError("overlap edge-pair observation summary is invalid")
    observations: dict[str, tuple[str, str]] = {}
    fields = {
        "observation_id",
        "end_edge_observation_id",
        "next_start_edge_observation_id",
        "signed_gap_interval_px",
        "canonical_signed_gap_px",
        "end_authority_bases",
        "next_start_authority_bases",
    }
    for observation in value:
        if not isinstance(observation, dict) or set(observation) != fields:
            raise ValueError("overlap edge-pair observation is invalid")
        identity = observation["observation_id"]
        end_id = observation["end_edge_observation_id"]
        start_id = observation["next_start_edge_observation_id"]
        signed_gap = observation["signed_gap_interval_px"]
        canonical = observation["canonical_signed_gap_px"]
        bases = (
            observation["end_authority_bases"],
            observation["next_start_authority_bases"],
        )
        if (
            any(
                not isinstance(item, str) or not item
                for item in (identity, end_id, start_id)
            )
            or identity in observations
            or end_id == start_id
            or not _valid_interval(signed_gap)
            or float(signed_gap["maximum"]) >= -1.0e-7
            or not _finite_number(canonical)
            or not float(signed_gap["minimum"])
            <= float(canonical)
            <= float(signed_gap["maximum"])
            or any(
                not isinstance(items, list)
                or not items
                or items != list(dict.fromkeys(items))
                or any(
                    item not in {"source_wide_edge", "aggregate_union"}
                    for item in items
                )
                for items in bases
            )
        ):
            raise ValueError("overlap edge-pair observation is invalid")
        observations[identity] = (end_id, start_id)
    return observations


def _validate_outer_frame_observation_authority(value: object) -> None:
    if value is None:
        return
    if not isinstance(value, dict) or set(value) != {
        "state",
        "first_frame_ordinal",
        "last_frame_ordinal",
        "first_frame_observation_ids",
        "last_frame_observation_ids",
        "reason",
    }:
        raise ValueError("outer-frame observation authority summary is invalid")
    first = value["first_frame_observation_ids"]
    last = value["last_frame_observation_ids"]
    supported = value["state"] == "supported"
    if (
        value["state"] not in {"supported", "unavailable"}
        or value["first_frame_ordinal"] != 1
        or not isinstance(value["last_frame_ordinal"], int)
        or value["last_frame_ordinal"] < 1
        or not _valid_ids(first)
        or not _valid_ids(last)
        or supported != bool(first and last)
        or supported != (value["reason"] is None)
        or value["reason"] is not None
        and (not isinstance(value["reason"], str) or not value["reason"])
    ):
        raise ValueError("outer-frame observation authority summary is invalid")


def _validate_frame_width_inference(value: object) -> None:
    if value is None:
        return
    if not isinstance(value, dict) or set(value) != {
        "state",
        "inferred_role_indices",
        "supporting_frame_ordinals",
        "width_px",
        "canonical_width_px",
        "observation_ids",
        "authority_id",
        "authority_basis",
        "failure_kind",
        "validation_only_role_indices",
        "validation_observation_ids",
    }:
        raise ValueError("Frame width inference summary is invalid")
    inferred = value["inferred_role_indices"]
    supporting = value["supporting_frame_ordinals"]
    observation_ids = value["observation_ids"]
    validation_only = value["validation_only_role_indices"]
    validation_ids = value["validation_observation_ids"]
    supported = value["state"] == "supported"
    authority_basis = value["authority_basis"]
    if (
        value["state"] not in {"supported", "unavailable"}
        or not isinstance(inferred, list)
        or inferred != sorted(set(inferred))
        or not inferred
        or any(not isinstance(index, int) or index < 0 for index in inferred)
        or not isinstance(supporting, list)
        or supporting != sorted(set(supporting))
        or any(
            not isinstance(ordinal, int) or ordinal <= 0
            for ordinal in supporting
        )
        or not _valid_ids(observation_ids)
        or not isinstance(validation_only, list)
        or validation_only != sorted(set(validation_only))
        or any(
            not isinstance(index, int) or index < 0
            for index in validation_only
        )
        or any(index not in inferred for index in validation_only)
        or not _valid_ids(validation_ids)
        or len(validation_only) != len(validation_ids)
        or not set(validation_ids).isdisjoint(observation_ids)
    ):
        raise ValueError("Frame width inference ledger is invalid")
    if supported:
        width = value["width_px"]
        canonical = value["canonical_width_px"]
        if (
            not isinstance(value["authority_id"], str)
            or not value["authority_id"]
            or authority_basis
            not in {
                "independent_complete_frames",
                "direct_lattice_closure",
                "reconciled_direct_constraints",
            }
            or (
                authority_basis == "independent_complete_frames"
                and (len(supporting) < 2 or len(observation_ids) < 4)
            )
            or (
                authority_basis == "reconciled_direct_constraints"
                and (len(supporting) < 2 or len(observation_ids) < 4)
            )
            or (
                authority_basis == "direct_lattice_closure"
                and len(observation_ids) < 3
            )
            or not _valid_interval(width)
            or not _finite_number(canonical)
            or float(canonical) < float(width["minimum"]) - 1.0e-9
            or float(canonical) > float(width["maximum"]) + 1.0e-9
            or value["failure_kind"] is not None
        ):
            raise ValueError("supported Frame width inference is invalid")
    elif (
        supporting
        or observation_ids
        or validation_only
        or validation_ids
        or value["width_px"] is not None
        or value["canonical_width_px"] is not None
        or value["authority_id"] is not None
        or authority_basis is not None
        or value["failure_kind"]
        not in {
            "source_width_placement_conflict",
            "common_width_authority_unavailable",
            "direct_lattice_counterevidence",
        }
    ):
        raise ValueError("unavailable Frame width inference is invalid")


def _validate_source_frame_width_authority(value: object) -> None:
    if (
        not isinstance(value, dict)
        or set(value) != _SOURCE_FRAME_WIDTH_AUTHORITY_FIELDS
        or not isinstance(value["authority_id"], str)
        or not value["authority_id"]
    ):
        raise ValueError("source Frame-width authority summary is invalid")
    state = value["state"]
    phase_anchor_ids = value["placement_phase_anchor_observation_ids"]
    supporting_role_ids = value["supporting_role_observation_ids"]
    basis = value["basis"]
    supporting = value["supporting_frame_ordinals"]
    constraint_ids = value["supporting_constraint_ids"]
    observation_ids = value["observation_ids"]
    if (
        state not in {"supported", "unavailable", "contradicted"}
        or not isinstance(phase_anchor_ids, list)
        or not isinstance(supporting_role_ids, list)
        or len(supporting_role_ids) != len(phase_anchor_ids)
        or any(
            identity is not None
            and (not isinstance(identity, str) or not identity)
            for identity in (*phase_anchor_ids, *supporting_role_ids)
        )
        or not isinstance(supporting, list)
        or supporting != sorted(set(supporting))
        or any(
            not isinstance(ordinal, int) or ordinal <= 0
            for ordinal in supporting
        )
        or not isinstance(constraint_ids, list)
        or constraint_ids != sorted(set(constraint_ids))
        or any(
            not isinstance(identity, str) or not identity
            for identity in constraint_ids
        )
        or not _valid_ids(observation_ids)
        or observation_ids != sorted(observation_ids)
    ):
        raise ValueError("source Frame-width authority ledger is invalid")
    supported = state == "supported"
    width = value["width_px"]
    canonical = value["canonical_width_px"]
    if supported:
        if (
            value["placement_scope"]
            not in {
                "resolved_placement",
                "retained_ambiguous_proposal",
                "retained_unresolved_proposal",
            }
            or not isinstance(value["placement_integer_slot_offset"], int)
            or not phase_anchor_ids
            or not any(phase_anchor_ids)
            or not any(supporting_role_ids)
            or {
                identity
                for identity in supporting_role_ids
                if identity is not None
            }
            != set(observation_ids)
            or basis
            not in {
                "independent_complete_frames",
                "direct_lattice_closure",
                "reconciled_direct_constraints",
            }
            or (
                basis == "independent_complete_frames"
                and (
                    len(supporting) < 2
                    or constraint_ids
                    or len(observation_ids) < 4
                )
            )
            or (
                basis == "reconciled_direct_constraints"
                and (
                    len(supporting) < 2
                    or len(constraint_ids) < 3
                    or len(observation_ids) < 4
                )
            )
            or (
                basis == "direct_lattice_closure"
                and (
                    supporting
                    or len(constraint_ids) < 3
                    or len(observation_ids) < 3
                )
            )
            or not _valid_interval(width)
            or float(width["minimum"]) <= 0.0
            or not _finite_number(canonical)
            or float(canonical) < float(width["minimum"]) - 1.0e-9
            or float(canonical) > float(width["maximum"]) + 1.0e-9
            or value["failure_kind"] is not None
            or value["reason"] is not None
        ):
            raise ValueError("supported source Frame-width authority is invalid")
        return
    if (
        value["placement_scope"] is not None
        or value["placement_integer_slot_offset"] is not None
        or phase_anchor_ids
        or supporting_role_ids
        or basis is not None
        or supporting
        or constraint_ids
        or width is not None
        or canonical is not None
        or observation_ids
        or value["failure_kind"] not in _SOURCE_FRAME_WIDTH_FAILURE_KINDS
        or not isinstance(value["reason"], str)
        or not value["reason"]
    ):
        raise ValueError("failed source Frame-width authority is invalid")


def _validate_source_frame_width_topology_assessment(value: object) -> None:
    if value is None:
        return
    if not isinstance(value, dict) or set(value) != {
        "source_frame_width_authority_id",
        "state",
        "facts",
        "failure_kind",
        "reason",
    }:
        raise ValueError("source-W topology assessment schema is invalid")
    authority_id = value["source_frame_width_authority_id"]
    facts = value["facts"]
    if (
        not isinstance(authority_id, str)
        or not authority_id
        or not isinstance(facts, list)
    ):
        raise ValueError("source-W topology assessment ledger is invalid")
    states: list[str] = []
    ordinals: list[int] = []
    for fact in facts:
        if not isinstance(fact, dict) or set(fact) != {
            "relation_ordinal",
            "inferred_role_indices",
            "signed_gap_interval_px",
            "canonical_signed_gap_px",
            "state",
        }:
            raise ValueError("source-W topology fact schema is invalid")
        ordinal = fact["relation_ordinal"]
        inferred = fact["inferred_role_indices"]
        interval = fact["signed_gap_interval_px"]
        canonical = fact["canonical_signed_gap_px"]
        if (
            not isinstance(ordinal, int)
            or isinstance(ordinal, bool)
            or ordinal <= 0
            or not isinstance(inferred, list)
            or not inferred
            or inferred != sorted(set(inferred))
            or any(
                not isinstance(index, int)
                or isinstance(index, bool)
                or index not in {2 * ordinal - 1, 2 * ordinal}
                for index in inferred
            )
            or not _valid_interval(interval)
            or not _finite_number(canonical)
            or float(canonical) < float(interval["minimum"]) - 1.0e-9
            or float(canonical) > float(interval["maximum"]) + 1.0e-9
        ):
            raise ValueError("source-W topology fact geometry is invalid")
        expected_state = (
            "supported"
            if float(interval["minimum"]) >= -1.0e-9
            else "contradicted"
            if float(interval["maximum"]) < -1.0e-9
            else "unavailable"
        )
        if fact["state"] != expected_state:
            raise ValueError("source-W topology fact state is invalid")
        ordinals.append(ordinal)
        states.append(expected_state)
    if ordinals != sorted(set(ordinals)):
        raise ValueError("source-W topology facts are not canonical")
    expected_state = (
        "contradicted"
        if "contradicted" in states
        else "unavailable"
        if "unavailable" in states
        else "supported"
    )
    expected_failure = (
        "normal_adjacency_contradicted"
        if expected_state == "contradicted"
        else "normal_adjacency_unresolved"
        if expected_state == "unavailable"
        else None
    )
    if (
        value["state"] != expected_state
        or value["failure_kind"] != expected_failure
        or (expected_state == "supported") != (value["reason"] is None)
        or value["reason"] is not None
        and (
            not isinstance(value["reason"], str)
            or not value["reason"]
        )
    ):
        raise ValueError("source-W topology assessment state is invalid")


def _validate_direct_role_binding_authority(value: object) -> None:
    if value is None:
        return
    if not isinstance(value, dict) or set(value) != {
        "state",
        "facts",
        "unsupported_role_indices",
        "reason",
    }:
        raise ValueError("direct-role binding authority summary is invalid")
    facts = value["facts"]
    unsupported = value["unsupported_role_indices"]
    if not isinstance(facts, list) or not isinstance(unsupported, list):
        raise ValueError("direct-role binding authority ledger is invalid")
    indices: list[int] = []
    blocked: list[int] = []
    contradicted = False
    allowed_bases = {
        "source_wide_edge",
        "aggregate_union",
        "separator_pair",
        "partial_height_separator_pair",
        "outer_material_boundary",
    }
    for fact in facts:
        if not isinstance(fact, dict) or set(fact) != {
            "role_index",
            "lane_ordinal",
            "role",
            "observation_id",
            "evidence_group_id",
            "independent_support_region_count",
            "bases",
            "blocking_material_conflict_ids",
            "state",
            "trace_coordinates_px",
            "supporting_outer_material_observation_ids",
        }:
            raise ValueError("direct-role authority fact is invalid")
        index = fact["role_index"]
        bases = fact["bases"]
        conflicts = fact["blocking_material_conflict_ids"]
        traces = fact["trace_coordinates_px"]
        outer_material = fact[
            "supporting_outer_material_observation_ids"
        ]
        supported = fact["state"] == "supported"
        conflict = fact["state"] == "contradicted"
        if (
            not isinstance(index, int)
            or index < 0
            or fact["lane_ordinal"] != index // 2 + 1
            or fact["role"] != ("start" if index % 2 == 0 else "end")
            or not isinstance(fact["observation_id"], str)
            or not fact["observation_id"]
            or not isinstance(fact["evidence_group_id"], str)
            or not fact["evidence_group_id"]
            or fact["independent_support_region_count"] not in {1, 2, 3}
            or not isinstance(bases, list)
            or bases != list(dict.fromkeys(bases))
            or any(item not in allowed_bases for item in bases)
            or (
                "partial_height_separator_pair" in bases
                and (
                    bases != ["partial_height_separator_pair"]
                    or fact["independent_support_region_count"] not in {2, 3}
                )
            )
            or not isinstance(conflicts, list)
            or conflicts != sorted(set(conflicts))
            or any(not isinstance(item, str) or not item for item in conflicts)
            or fact["state"]
            not in {"supported", "contradicted", "unavailable"}
            or not isinstance(traces, list)
            or traces != sorted(set(traces))
            or any(not isinstance(item, int) for item in traces)
            or not isinstance(outer_material, list)
            or outer_material != sorted(set(outer_material))
            or any(
                not isinstance(item, str) or not item
                for item in outer_material
            )
            or (
                "outer_material_boundary" in bases
            )
            != bool(outer_material)
            or (
                "partial_height_separator_pair" in bases
                and not traces
            )
            or conflict != bool(conflicts)
            or supported != (bool(bases) and not conflicts)
            or (fact["state"] == "unavailable")
            != (not bases and not conflicts)
        ):
            raise ValueError("direct-role authority fact is invalid")
        indices.append(index)
        if not supported:
            blocked.append(index)
        contradicted = contradicted or conflict
    expected_state = (
        "contradicted" if contradicted else "unavailable" if blocked else "supported"
    )
    if (
        indices != sorted(set(indices))
        or unsupported != blocked
        or value["state"] != expected_state
        or (expected_state == "supported") != (value["reason"] is None)
        or value["reason"] is not None
        and (not isinstance(value["reason"], str) or not value["reason"])
    ):
        raise ValueError("direct-role binding authority summary is invalid")


def _validate_direct_role_aperture_domain_authority(value: object) -> None:
    if value is None:
        return
    if not isinstance(value, dict) or set(value) != {
        "state",
        "facts",
        "unsupported_role_indices",
        "reason",
    }:
        raise ValueError("direct-role aperture-domain authority is invalid")
    facts = value["facts"]
    unsupported = value["unsupported_role_indices"]
    if not isinstance(facts, list) or not facts or not isinstance(unsupported, list):
        raise ValueError("direct-role aperture-domain ledger is invalid")
    indices: list[int] = []
    blocked: list[int] = []
    contradicted = False
    for fact in facts:
        if not isinstance(fact, dict) or set(fact) != {
            "role_index",
            "observation_id",
            "role_position_interval_px",
            "support_trace_interval_px",
            "guaranteed_aperture_interval_px",
            "basis",
            "cross_observation_ids",
            "state",
            "failure_kind",
        }:
            raise ValueError("direct-role aperture-domain fact is invalid")
        index = fact["role_index"]
        state = fact["state"]
        basis = fact["basis"]
        failure = fact["failure_kind"]
        domain = fact["guaranteed_aperture_interval_px"]
        trace = fact["support_trace_interval_px"]
        cross_ids = fact["cross_observation_ids"]
        contained = (
            _valid_interval(domain)
            and _valid_interval(trace)
            and float(domain["minimum"]) <= float(trace["minimum"])
            and float(trace["maximum"]) <= float(domain["maximum"])
        )
        has_cross_domain = basis is not None and _valid_ids(
            cross_ids,
            allow_empty=False,
        )
        collapsed = failure == "aperture_domain_collapsed"
        outside = failure == "support_outside_aperture_domain"
        if (
            not isinstance(index, int)
            or index < 0
            or not isinstance(fact["observation_id"], str)
            or not fact["observation_id"]
            or not _valid_interval(fact["role_position_interval_px"])
            or not _valid_interval(trace)
            or domain is not None and not _valid_interval(domain)
            or basis not in {
                None,
                "direct_aperture_pair",
                "enclosing_support_aperture",
            }
            or not _valid_ids(cross_ids)
            or state not in {"supported", "contradicted", "unavailable"}
            or failure
            not in {
                None,
                "two_sided_cross_domain_unavailable",
                "aperture_domain_collapsed",
                "support_outside_aperture_domain",
            }
            or (state == "supported")
            != (
                has_cross_domain
                and failure is None
                and contained
            )
            or (state == "contradicted")
            != (
                has_cross_domain
                and (
                    (collapsed and domain is None)
                    or (
                        outside
                        and domain is not None
                        and not contained
                    )
                )
            )
            or (state == "unavailable")
            != (
                basis is None
                and domain is None
                and failure == "two_sided_cross_domain_unavailable"
            )
        ):
            raise ValueError("direct-role aperture-domain fact is invalid")
        indices.append(index)
        if state != "supported":
            blocked.append(index)
        contradicted = contradicted or state == "contradicted"
    expected = (
        "contradicted" if contradicted else "unavailable" if blocked else "supported"
    )
    if (
        indices != sorted(set(indices))
        or unsupported != blocked
        or value["state"] != expected
        or (expected == "supported") != (value["reason"] is None)
        or value["reason"] is not None
        and (not isinstance(value["reason"], str) or not value["reason"])
    ):
        raise ValueError("direct-role aperture-domain authority is invalid")
