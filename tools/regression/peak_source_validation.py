"""Replay source-bound coarse/native links and their ordinary report uses."""

from x5crop.report.read_models import typed_read_model
from x5crop.detection.photo_geometry.coarse_native_association import associate_coarse_native_lines, native_line_alternatives
from x5crop.detection.photo_geometry.coarse_native_association_model import CoarseNativeLineAssociation
from x5crop.detection.photo_geometry.coarse_strip_support import CoarseStripSupport
from x5crop.detection.photo_geometry.template_registration import RegisteredCrossEvidence
from x5crop.detection.photo_geometry.template_cross_model import CrossEvidence
from x5crop.detection.photo_geometry.transition_peak_validation import validate_peak_source_measurements


def validate_ordinary_peak_associations(record, *, read_proof, source_extent):
    source_id = record["measurement"].get("source_id")
    if not isinstance(source_id, str) or not source_id:
        raise ValueError("report lost its original peak source identity")
    constraints = {}
    for lane in record["photo_geometry"]["lanes"]:
        proofs = tuple(read_proof(value, CoarseNativeLineAssociation) for value in lane["coarse_native_associations"])
        if len(proofs) > 2 or len({proof.coarse_track.side for proof in proofs}) != len(proofs):
            raise ValueError("coarse/native association changed its two original sides")
        raw_base = lane["coarse_native_base_registration"]
        if bool(proofs) != (raw_base is not None):
            raise ValueError("native association lost its candidate-independent base registration")
        base = None if raw_base is None else read_proof(raw_base, RegisteredCrossEvidence)
        alternatives = None if base is None else native_line_alternatives(base)
        for proof in proofs:
            mapped = frozenset(link.native_transition.transition_id for link in proof.correspondences)
            candidates = tuple(binding for binding in (*base.top_bindings, *base.bottom_bindings)
                if binding.role == proof.native_observation.role and binding.role_authorized
                and binding.evidence == CrossEvidence.DIRECT and not binding.conditional_family_ids
                and mapped.issubset(next(item.transition_ids for item in base.observations
                                       if item.observation_id == binding.observation_id)))
            if (base.local_refinement_scope_count or base.local_refinement_scopes
                    or alternatives is None or proof.alternatives != alternatives
                    or len(candidates) != 1 or candidates[0].observation_id != proof.native_observation.observation_id
                    or proof.native_observation not in base.observations):
                raise ValueError("native association changed its complete independent continuation universe")
            if (proof.native_query.lane_id != lane["lane_id"] or any(
                    group.source.source_id != source_id or group.source.source_extent != source_extent
                    for link in proof.correspondences for group in (link.coarse_group, link.native_group))):
                raise ValueError("coarse/native association changed its source or registered lane")
            constraints[str(proof.coarse_track.observation_id)] = typed_read_model(proof.constraint)

    def visit(value):
        if isinstance(value, dict):
            if "coarse_native_constraint" in value:
                expected = constraints.get(value["observation_id"])
                if value["coarse_native_constraint"] != expected:
                    raise ValueError("output binding changed its independent native support constraint")
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(record["photo_geometry"])
    if record["development"] is not None:
        visit(record["development"]["lanes"])


def validate_development_peak_associations(lane, production_lane, measurements, *,
                                         source_id, source_extent, bounds, read_proof):
    coarse = read_proof(lane["search"]["coarse_strip_support"], CoarseStripSupport)
    validate_peak_source_measurements(measurements, source_id=source_id,
                                      source_extent=source_extent, coarse_support=coarse)
    base = read_proof(lane["base_cross_registration"], RegisteredCrossEvidence)
    if production_lane["coarse_native_base_registration"] != (
            lane["base_cross_registration"] if production_lane["coarse_native_associations"] else None):
        raise ValueError("ordinary native association changed its original base registration")
    work = lane["measurement_work"]
    base_visits = sum(item.coverage.peak_source_value_visit_bound for item in measurements)
    base_peak = max(work["exterior_work"]["peak_temporary_bytes"],
                    *(item.coverage.peak_temporary_bytes for item in measurements))
    proofs, association_work = associate_coarse_native_lines(coarse, measurements, base,
        maximum_value_visits=max(0, bounds.max_pixel_queries - work["pixel_query_count"] - base_visits),
        maximum_temporary_bytes=max(0, bounds.max_peak_temporary_bytes - base_peak))
    if (typed_read_model(proofs) != production_lane["coarse_native_associations"]
            or typed_read_model(association_work) != work["coarse_native_association_work"]
            or typed_read_model(association_work) != production_lane["coarse_native_association_work"]):
        raise ValueError("coarse/native association changed its complete base universe, source links or work")
