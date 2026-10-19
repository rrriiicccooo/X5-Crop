"""Replay complete phase membership and conditional output from registered facts."""

from dataclasses import fields
from types import SimpleNamespace

from x5crop.report.read_models import typed_read_model
from x5crop.run_local_identity import source_identity_scope
from x5crop.detection.source_core import SourceLaneEvidence
from x5crop.detection.photo_geometry.axis_layout import axis_interval
from x5crop.detection.photo_geometry.model import BoundaryAxis, QueryPurpose
from x5crop.detection.photo_geometry.measurement_model import PhotoBoundaryMeasurementSet
from x5crop.detection.photo_geometry.observation_types import BasicAxisProfile
from x5crop.detection.photo_geometry.coarse_strip_support import CoarseStripSupport
from x5crop.detection.photo_geometry.source_geometry import SourceScanGeometry
from x5crop.detection.photo_geometry.template_cross_model import TemplateCrossInput, CrossRoleBinding
from x5crop.detection.photo_geometry.line_observations import PhotoBoundaryObservation
from x5crop.detection.photo_geometry.template_phase_model import PhaseFitResult, TemplatePhaseInput
from x5crop.detection.photo_geometry.template_phase_competition import fit_template_phase
from x5crop.detection.photo_geometry.template_phase_output import CompletePhaseOutputProof, build_complete_phase_output
from x5crop.detection.photo_geometry.template_registration import RegisteredCrossEvidence, register_cross_evidence


_ALLOCATED_PREFIXES = frozenset({
    "source-scan-geometry", "source-frame-width-authority", "adjacency-continuity",
    "aperture-aspect-ratio", "cross-longitudinal-projection", "calibrated-nominal-grid-evidence",
    "phase-member-output", "template-output-footprint", "joint-placement-projection",
    "common-phase-footprint", "enclosing-support-aperture", "enclosing-support-aperture-unavailable",
    "membership-proposal-run", "membership-proposal-family",
    "registered-cross-run", "constrained-cross-run",
})


def assert_replayed_facts(expected, actual, *, protected_native_ids=None) -> None:
    """Permit only bijective run-local renaming; preserve the physical identity graph."""
    forward, reverse = {}, {}

    def compare(left, right, path):
        if type(left) is dict and type(right) is dict and left.keys() == right.keys():
            for key in left:
                compare(left[key], right[key], f"{path}.{key}")
        elif type(left) is list and type(right) is list and len(left) == len(right):
            for ordinal, (a, b) in enumerate(zip(left, right, strict=True)):
                compare(a, b, f"{path}[{ordinal}]")
        elif isinstance(left, str) and isinstance(right, str):
            prefix, _, ordinal = left.rpartition(":")
            other, _, index = right.rpartition(":")
            conditional_native = (protected_native_ids is not None
                and prefix in {"format-role-bound-line", "constrained-family-line"}
                and left not in protected_native_ids and right not in protected_native_ids)
            allocated = ((prefix in _ALLOCATED_PREFIXES or conditional_native) and prefix == other
                         and ordinal.isdecimal() and index.isdecimal())
            if allocated:
                if forward.setdefault(left, right) == right and reverse.setdefault(right, left) == left:
                    return
            elif left == right:
                return
            if left != right or allocated:
                raise ValueError(f"complete phase physical facts changed at {path}: {left[:128]!r} != {right[:128]!r}")
        elif left != right:
            raise ValueError(f"complete phase physical facts changed at {path}")

    compare(expected, actual, "proof")


def _registered_replay_identity_context(lane, read_proof):
    names, keys = set(), []
    def collect(value):
        if isinstance(value, str):
            names.add(value)
        elif isinstance(value, dict):
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)
    # Reserve existing registered facts, never the new member proof's names.
    for field in ("base_cross_registration", "phase_input", "search", "source_scan_geometry", "observations", "cross_registration_work"):
        collect(lane[field])
    raw_lines = list(lane["observations"]["raw_top_bottom_lines"])
    raw_lines.extend(scope["fitted_observation"] for scope in lane["cross_registration_work"]["local_refinement_scopes"]
                     if scope["fitted_observation"] is not None)
    for raw in raw_lines:
        observation = read_proof(raw, PhotoBoundaryObservation)
        prefix, _, _ = str(observation.observation_id).rpartition(":")
        if prefix in {"format-role-bound-line", "constrained-family-line", "membership-proposal-line"}:
            keys.append((prefix, (observation.role.value, *map(str, sorted(observation.transition_ids, key=str))),
                         str(observation.observation_id)))
    for family in lane["base_cross_registration"]["family_resolutions"]:
        prefix, _, _ = family["family_id"].rpartition(":")
        members = tuple(family["member_observation_ids"])
        if prefix in {"cross-boundary-family", "constrained-cross-family"}:
            keys.append((prefix, (family["role"], family["use"], *members), family["family_id"]))
        elif prefix == "membership-proposal-family":
            keys.append((prefix, (family["role"], *members), family["family_id"]))
        for identity, transitions in zip(members, family["member_transition_groups"], strict=True):
            prefix, _, _ = identity.rpartition(":")
            if prefix in {"format-role-bound-line", "constrained-family-line", "membership-proposal-line"}:
                keys.append((prefix, (family["role"], *sorted(transitions)), identity))
    for raw in lane["observations"]["registered_top_bottom_bindings"]:
        binding = read_proof(raw, CrossRoleBinding)
        prefix, _, _ = binding.run_id.rpartition(":")
        if prefix in {"registered-cross-run", "constrained-cross-run", "membership-proposal-run"}:
            keys.append((prefix, (binding.role.value, binding.observation_id), binding.run_id))
        fact, track = binding.coarse_side_fact, binding.coarse_side_track
        if fact is not None and track is not None:
            keys.append(("coarse-enclosing-track", (fact.query.query_id, track.measurement_basis.value,
                track.side.value, *(str(item.transition_id) for item in fact.observations
                                   if item.trace_coordinate_px in track.trace_coordinates_px)),
                str(track.observation_id)))
    for run in lane["search"]["cross_profile"]["runs"]:
        _, _, region_id = run["run_id"].partition(":")
        if region_id.startswith("side-region:"):
            keys.append(("side-region", tuple(sorted(run["transition_ids"])), region_id))
    return source_identity_scope(reserved_ids=names, registered_keys=keys)


def validate_complete_phase_output(lane, production, measurement, *, layout, read_proof):
    phase = read_proof(lane["phase_competition"], PhaseFitResult)
    if production.get("phase_competition_scopes") != lane["phase_competition"]["competition_scopes"]:
        raise ValueError("complete phase producer scopes changed between reports")
    value = lane.get("complete_phase_output")
    if "complete_phase_output" not in lane or value != production.get("complete_phase_output"):
        raise ValueError("complete phase output changed between reports")
    # All producer scopes must replay, including unprojected history and the
    # third or lower-ranked member, whether or not output validation is needed.
    inputs = read_proof(lane["phase_input"], TemplatePhaseInput)
    source_rows = [item for item in measurement["source_lanes"] if item["domain"]["lane_id"] == lane["lane_id"]]
    if len(source_rows) != 1:
        raise ValueError("complete phase output lost its registered source lane")
    source_lane = read_proof({key: source_rows[0][key] for key in ("domain", "scan_canvas")}, SourceLaneEvidence)
    scales = source_lane.scan_canvas.axis_scales
    observations = lane["observations"]
    for field, registered in (("observations", "sequence_edges"), ("separator_bands", "separator_bands"),
                              ("outer_material_boundaries", "outer_material_boundaries"),
                              ("contact_edge_observations", "contact_edge_observations"),
                              ("overlap_edge_pair_observations", "overlap_edge_pair_observations")):
        if typed_read_model(getattr(inputs, field)) != observations[registered]:
            raise ValueError("complete phase output changed its registered phase facts")
    queries = tuple(read_proof({field.name: row[field.name] for field in fields(PhotoBoundaryMeasurementSet)},
                              PhotoBoundaryMeasurementSet)
                    for row in measurement["queries"] if row["query"]["lane_id"] == lane["lane_id"])
    sequence = tuple(item for item in queries if item.query.purpose == QueryPurpose.SEQUENCE_ANCHOR_WINDOW)
    if sequence != inputs.sequence_measurement_sets or inputs.scale_px_per_mm != scales.width_axis_px_per_mm:
        raise ValueError("complete phase output changed its registered sequence measurement domain")
    by_query = {item.query.query_id: item for item in sequence}
    for scope in phase.competition_scopes:
        context = scope.input_context
        if (context is None or context.scale_px_per_mm != scales.width_axis_px_per_mm
                or context.max_observations != inputs.max_observations):
            raise ValueError("complete phase producer lost its original inputs")
        if (scope.source_domain != inputs.source_domain or scope.holder_span_px != inputs.holder_span_px
                or any(identity not in by_query for identity in context.sequence_measurement_query_ids)
                or context.calibrated_nominal_grid_prior not in (None, inputs.calibrated_nominal_grid_prior)):
            raise ValueError("complete phase producer borrowed a foreign input domain")
        contact = tuple(item for item in inputs.contact_edge_observations if item.observation_id in context.contact_observation_ids)
        overlap = tuple(item for item in inputs.overlap_edge_pair_observations if item.observation_id in context.overlap_observation_ids)
        if (tuple(item.observation_id for item in contact) != context.contact_observation_ids
                or tuple(item.observation_id for item in overlap) != context.overlap_observation_ids):
            raise ValueError("complete phase producer lost registered topology inputs")
        with source_identity_scope():
            replay = fit_template_phase(inputs.observations, scope.template,
                separator_bands=inputs.separator_bands, outer_material_boundaries=inputs.outer_material_boundaries,
                scale_px_per_mm=context.scale_px_per_mm, holder_span_px=scope.holder_span_px,
                source_domain=scope.source_domain, phase_authority_px=scope.phase_authority_px,
                adjacency_relations=scope.adjacency_relations, contact_edge_observations=contact,
                overlap_edge_pair_observations=overlap,
                sequence_measurement_sets=tuple(by_query[identity] for identity in context.sequence_measurement_query_ids),
                calibrated_nominal_grid_prior=context.calibrated_nominal_grid_prior,
                phase_anchor_authority_ceiling=scope.phase_anchor_authority_ceiling,
                max_observations=context.max_observations)
        if replay.competition_scopes != (scope,):
            raise ValueError("complete phase producer membership or work is not reproducible")
    if value is None:
        if phase.runner_up is not None and phase.status.value != "resolved":
            raise ValueError("plural unresolved phase lost its complete output proof")
        return
    proof = read_proof(production["complete_phase_output"], CompletePhaseOutputProof)
    if proof.scopes != phase.competition_scopes:
        raise ValueError("complete phase output omitted a producer scope")
    cross_input = read_proof(lane["cross_input"], TemplateCrossInput)
    width_axis = BoundaryAxis.X if layout == "horizontal" else BoundaryAxis.Y
    height_axis = BoundaryAxis.Y if layout == "horizontal" else BoundaryAxis.X
    from x5crop.detection.photo_geometry.corridors import source_lane_box
    lane_box = source_lane_box(source_lane, layout)
    width_authority = axis_interval(lane_box, width_axis)
    height_authority = axis_interval(lane_box, height_axis)
    base = read_proof(lane["base_cross_registration"], RegisteredCrossEvidence)
    top = next(item for item in queries if item.query.purpose == QueryPurpose.TOP_CORRIDOR)
    bottom = next(item for item in queries if item.query.purpose == QueryPurpose.BOTTOM_CORRIDOR)
    from x5crop.detection.photo_geometry.lane_preparation import _physical_transition_regions
    from x5crop.detection.photo_geometry.profile_adapters import cross_profile_from_regions
    from x5crop.detection.photo_geometry.axis_layout import coordinate_count
    profile = read_proof(lane["search"]["cross_profile"], BasicAxisProfile)
    with _registered_replay_identity_context(lane, read_proof):
        regions = tuple(_physical_transition_regions((item,), reference_trace_px=width_authority.center,
            boundary_axis_scale_px_per_mm=scales.height_axis_px_per_mm,
            minimum_independent_support_regions=1) for item in (top, bottom))
        replay_profile = cross_profile_from_regions(*regions, coordinate_count=coordinate_count(height_authority),
            transition_by_id={str(transition.transition_id): transition for item in queries for transition in item.transitions})
        if replay_profile != profile:
            raise ValueError("member Cross profile changed its candidate-independent registered transitions")
        replay_base = register_cross_evidence(profile=profile,
            top_measurement=top, bottom_measurement=bottom, width_axis=width_axis, height_axis=height_axis,
            height_scale_px_per_mm=scales.height_axis_px_per_mm, lane_reference_trace_px=width_authority.center,
            maximum_runs_per_role=cross_input.maximum_registered_runs_per_role)
    assert_replayed_facts(typed_read_model(replay_base), typed_read_model(base))
    bounds = SimpleNamespace(**{name: getattr(cross_input, other) for name, other in (
        ("max_registered_runs_per_role", "maximum_registered_runs_per_role"),
        ("max_fitted_observations", "maximum_fitted_observations"),
        ("max_compatible_pairs", "maximum_compatible_pairs"),
        ("max_evaluated_fits", "maximum_evaluated_fits"))})
    prepared = SimpleNamespace(lane=source_lane, layout=layout, phase_input=inputs,
        phase_competition=phase, source_scan_geometry=read_proof(lane["source_scan_geometry"], SourceScanGeometry),
        base_cross_registration=base, measurement_sets=queries,
        coarse_support=read_proof(lane["search"]["coarse_strip_support"], CoarseStripSupport),
        width_axis=width_axis, height_axis=height_axis, width_authority_px=width_authority,
        height_authority_px=height_authority, measurement_plan=SimpleNamespace(cross_bounds=bounds))
    from x5crop.detection.photo_geometry.template_phase_review import IndependentPhaseReviewPortfolio
    independent = production["independent_phase_review"]
    retained = 0 if independent is None else read_proof(independent, IndependentPhaseReviewPortfolio).peak_temporary_bytes
    with _registered_replay_identity_context(lane, read_proof):
        expected = build_complete_phase_output(prepared, retained_review_bytes=retained)
    native_ids = {str(observation.observation_id) for observation in base.observations}
    native_ids.update(raw["observation_id"] for raw in lane["observations"]["raw_top_bottom_lines"])
    native_ids.update(scope["fitted_observation"]["observation_id"]
        for scope in lane["cross_registration_work"]["local_refinement_scopes"] if scope["fitted_observation"] is not None)
    assert_replayed_facts(typed_read_model(expected), value, protected_native_ids=native_ids)
