"""Replay complete native Sequence connections and their geometry uses."""
from dataclasses import replace

from x5crop.domain import WorkspaceExtent
from x5crop.report.read_models import typed_read_model
from x5crop.detection.photo_geometry.observation_types import BoundaryEdgeObservation
from x5crop.detection.photo_geometry.sequence_connections import (
    SequenceConnectionEvidence,eligible_sequence_connection_parent,
    sequence_connection_persistent_input_bound,validate_sequence_connection_evidence,
)


def validate_sequence_connections(record, *, read_proof):
    extent = WorkspaceExtent(**record['measurement']['source_extent'])
    source_id = record['measurement']['source_id']
    development = {} if record['development'] is None else {l['lane_id']:l for l in record['development']['lanes']}
    for lane in record['photo_geometry']['lanes']:
        raw,raw_work = lane['sequence_connections'],lane['sequence_connection_work']
        constraints = {}
        if raw is None:
            if raw_work is not None:
                raise ValueError('Sequence connection lost its complete work')
        else:
            evidence = read_proof(raw,SequenceConnectionEvidence)
            budget = evidence.budget
            if (budget.maximum_value_visits > 128*extent.width*extent.height
                    or budget.maximum_temporary_bytes > 10*extent.width*extent.height+32*1024*1024):
                raise ValueError('Sequence connection exceeded the source-wide resource ceiling')
            if typed_read_model(evidence.work) != raw_work:
                raise ValueError('Sequence connection changed its ordinary source work')
            validate_sequence_connection_evidence(evidence,source_id=source_id,source_extent=extent,
                maximum_value_visits=budget.maximum_value_visits,
                maximum_temporary_bytes=budget.maximum_temporary_bytes,persistent_input_bytes=budget.persistent_input_bytes)
            constraints = {str(a.observation_id):typed_read_model(a.constraint) for a in evidence.assessments
                           if a.constraint is not None}

        def visit(value,path='lane'):
            if isinstance(value,dict):
                if 'sequence_connection_constraint' in value:
                    if value['sequence_connection_constraint'] != constraints.get(value['observation_id']):
                        raise ValueError(f'Sequence geometry lost its independent native connection: {path} / {value["observation_id"]}')
                for key,child in value.items():
                    if key != 'sequence_connections':
                        visit(child,path+'.'+key)
            elif isinstance(value,list):
                for index,child in enumerate(value):
                    visit(child,path+f'[{index}]')
        visit(lane)
        if lane['lane_id'] in development:
            detail = development[lane['lane_id']]
            if (detail['sequence_connections'] != raw
                    or detail['measurement_work']['sequence_connection_work'] != raw_work):
                raise ValueError('development Sequence connection changed production facts')
            visit(detail)


def validate_development_sequence_connections(lane, production, measurements, *, bounds, exterior, read_proof):
    edges = tuple(read_proof(p,BoundaryEdgeObservation) for p in lane['observations']['sequence_edges'])
    original = tuple(replace(p,sequence_connection_constraint=None) for p in edges)
    expected_parents = tuple(p for p in original if eligible_sequence_connection_parent(p))
    raw = production['sequence_connections']
    if raw is None:
        if expected_parents:
            raise ValueError('Sequence connection omitted its eligible parent set')
        return
    evidence = read_proof(raw,SequenceConnectionEvidence)
    if evidence.parents != expected_parents:
        raise ValueError('Sequence connection changed its complete native parent set')
    from x5crop.detection.photo_geometry.model import QueryPurpose
    expected_measurements = tuple(m for m in measurements if m.query.purpose in {
        QueryPurpose.SEQUENCE_BASELINE,QueryPurpose.SEQUENCE_ANCHOR_WINDOW})
    if evidence.planning_completed and evidence.measurements != expected_measurements:
        raise ValueError('Sequence connection changed its complete registered query inventory')
    pixels = exterior.work.pixel_query_count+sum(m.coverage.pixel_query_count for m in measurements)
    visits = sum(m.coverage.peak_source_value_visit_bound for m in measurements)
    persistent = sequence_connection_persistent_input_bound(measurements,len(original),exterior.query.work_box.height)
    budget = evidence.budget
    if (budget.maximum_value_visits != max(0,bounds.max_pixel_queries-pixels-visits)
            or budget.maximum_temporary_bytes != bounds.max_peak_temporary_bytes
            or budget.persistent_input_bytes != persistent):
        raise ValueError('Sequence connection changed its original shared-pool admission')
