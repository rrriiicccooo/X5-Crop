"""Replay native material-to-boundary provenance without choosing ordinals."""
from __future__ import annotations

from collections import Counter
import json
import re

from x5crop.detection.photo_geometry.aggregate_edge_support import (
    placement_sequence_edges_with_material_support, resolve_aggregate_separator_support,
)
from x5crop.detection.photo_geometry.observation_types import (
    AggregateEdgeResolution, AggregateEdgeResolutionKind, BoundaryEdgeMeasurementBasis,
    BasicAxisProfile, BoundaryEdgeObservation, OuterMaterialBoundaryObservation,
    SeparatorBandMeasurementBasis, SeparatorBandObservation,
)
from x5crop.detection.photo_geometry.outer_material import (
    observe_outer_material_boundaries, validate_material_band_sources,
)
from x5crop.detection.photo_geometry.template_direct_role_authority import intrinsic_direct_role_authority_bases
from x5crop.detection.photo_geometry.template_phase_model import TemplatePhaseInput
from x5crop.report.read_models import typed_read_model
from x5crop.domain import ObservationId


def _derived_physical_records(values, *, outer=False):
    records = []
    identities = set()
    for item in values:
        record = typed_read_model(item)
        identity = record["observation_id"]
        if identity in identities:
            raise ValueError("derived material identities must remain one-to-one")
        identities.add(identity)
        prefix = ("outer-material-boundary" if outer else "aggregate-separator-band"
                  if item.measurement_basis != SeparatorBandMeasurementBasis.DIRECT_TRACE else None)
        if prefix is not None and re.fullmatch(rf"{prefix}:[1-9][0-9]*", identity) is None:
            raise ValueError("derived material identity is not a registered run-local name")
        if outer:
            if record.pop("evidence_group_id") != record["observation_id"]:
                raise ValueError("outer material changed its correlated identity")
            record.pop("observation_id")
        elif item.measurement_basis != SeparatorBandMeasurementBasis.DIRECT_TRACE:
            record.pop("observation_id")
        records.append(json.dumps(record, sort_keys=True, separators=(",", ":")))
    return Counter(records)


def validate_registered_material_evidence(lane):
    # Decode through the same strict typed owner used by the other report
    # replays; importing locally avoids a validator module cycle.
    from .report_validation import _read_common_proof, _validate_separator_material_states
    observations = lane["observations"]
    raw = observations.get("raw_material_bands")
    if not isinstance(raw, list):
        raise ValueError("lane lost its original raw material-band ledger")
    _validate_separator_material_states(raw)
    read = lambda key, model: tuple(_read_common_proof(item, model) for item in observations[key])
    bands = read("raw_material_bands", SeparatorBandObservation)
    edges = read("sequence_edges", BoundaryEdgeObservation)
    cross = read("cross_height_edges", BoundaryEdgeObservation)
    broad = read("broad_material_edges", BoundaryEdgeObservation)
    cross_resolutions = read("cross_height_edge_resolutions", AggregateEdgeResolution)
    broad_resolutions = read("broad_material_edge_resolutions", AggregateEdgeResolution)
    resolutions = (*cross_resolutions, *broad_resolutions)
    outer = read("outer_material_boundaries", OuterMaterialBoundaryObservation)
    phase_input = _read_common_proof(lane["phase_input"], TemplatePhaseInput)
    transitions = {str(point.transition_id): point
                   for measurement in phase_input.sequence_measurement_sets
                   for point in (*measurement.transitions, *measurement.cross_height_transitions,
                                 *measurement.broad_material_transitions)}
    validate_material_band_sources(bands, edges, cross, broad, resolutions, outer,
        transition_by_id=transitions,
        profiles={basis: _read_common_proof(lane["search"][key], BasicAxisProfile)
                  for basis, key in (
                      (SeparatorBandMeasurementBasis.DIRECT_TRACE, "sequence_profile"),
                      (SeparatorBandMeasurementBasis.CROSS_HEIGHT_AGGREGATE, "cross_height_profile"),
                      (SeparatorBandMeasurementBasis.BROAD_MATERIAL_TRACE, "broad_material_profile"))},
        registered_region_transition_ids={basis: tuple(tuple(ObservationId(identity) for identity in region["transition_ids"])
                                                      for region in observations[key])
            for basis, key in (
                (SeparatorBandMeasurementBasis.DIRECT_TRACE, "side_transition_regions"),
                (SeparatorBandMeasurementBasis.CROSS_HEIGHT_AGGREGATE, "cross_height_transition_regions"),
                (SeparatorBandMeasurementBasis.BROAD_MATERIAL_TRACE, "broad_material_transition_regions"))})

    # Before placement filtering, every supported standalone aggregate was
    # still present. Rebuild that original input rather than using a fit or
    # the already filtered placement pool to manufacture an outermost pair.
    standalone = {item.support_observation_id for item in resolutions
                  if item.kind == AggregateEdgeResolutionKind.STANDALONE_EDGE}
    resolved = tuple(sorted((
        *(edge for edge in edges if edge.measurement_basis in (
            BoundaryEdgeMeasurementBasis.DIRECT_TRACE, BoundaryEdgeMeasurementBasis.DIRECT_WITH_AGGREGATE)),
        *(edge for edge in (*cross, *broad) if edge.observation_id in standalone),
    ), key=lambda edge: (edge.fit_position_interval_px.center, str(edge.observation_id))))
    direct = tuple(b for b in bands if b.measurement_basis == SeparatorBandMeasurementBasis.DIRECT_TRACE)
    projected_cross = resolve_aggregate_separator_support(
        tuple(b for b in bands if b.measurement_basis == SeparatorBandMeasurementBasis.CROSS_HEIGHT_AGGREGATE),
        cross_resolutions, resolved, direct,
        aggregate_basis=SeparatorBandMeasurementBasis.CROSS_HEIGHT_AGGREGATE)
    projected_broad = resolve_aggregate_separator_support(
        tuple(b for b in bands if b.measurement_basis == SeparatorBandMeasurementBasis.BROAD_MATERIAL_TRACE),
        broad_resolutions, resolved, (*direct, *projected_cross),
        aggregate_basis=SeparatorBandMeasurementBasis.BROAD_MATERIAL_TRACE)
    projected = (*direct, *projected_cross, *projected_broad)
    recorded = read("separator_bands", SeparatorBandObservation)
    if _derived_physical_records(projected) != _derived_physical_records(recorded):
        raise ValueError("registered separator material changed its original projection")
    observed = observe_outer_material_boundaries(bands, resolutions, resolved,
        direction=phase_input.template.direction,
        maximum_material_width_px=phase_input.template.gap_prior_px.maximum,
        intrinsic_authority_edge_ids=frozenset(intrinsic_direct_role_authority_bases(
            resolved, phase_input.sequence_measurement_sets)))
    expected_edges = placement_sequence_edges_with_material_support(
        resolved, (*projected_cross, *projected_broad), observed)
    expected_ids = {edge.observation_id for edge in expected_edges}
    expected_outer = tuple(item for item in observed if {
        item.boundary_edge_observation_id, item.exterior_edge_observation_id}.issubset(expected_ids))
    if (_derived_physical_records(expected_outer, outer=True) != _derived_physical_records(outer, outer=True)
            or expected_edges != edges):
        raise ValueError("outer material or placement edges changed their original registered evidence")
