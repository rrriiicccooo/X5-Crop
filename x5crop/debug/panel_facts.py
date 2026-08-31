"""Read-only report/runtime facts consumed by Debug Analysis panels."""

from __future__ import annotations

from PIL import Image

from ..detection.final.model import FinalDetection
from ..detection.photo_geometry.model import SPATIAL_SUPPORT_REGION_COUNT
from ..detection.photo_geometry.output_model import (
    FootprintSaturationKind,
    OutputFootprint,
)
from ..detection.photo_geometry.template_alignment_diagnostic import (
    template_alignment_diagnostic,
)
from ..detection.photo_geometry.template_placement import TemplateFrame
from ..detection.workspace import DetectionWorkspace
from .canvas import DebugRenderCache, cached_source_image
from .panel_layout import Projection


def _placement_geometry_by_identity(
    detection: FinalDetection,
    placement_ids: tuple[str, ...],
) -> tuple[tuple[int, TemplateFrame], ...]:
    global_ordinals = {
        (item.lane_id, item.lane_ordinal): item.global_output_ordinal
        for item in detection.output_slot_identities
    }
    values: list[tuple[int, TemplateFrame]] = []
    requested = set(placement_ids)
    for lane in detection.candidate.geometry.lane_reconstructions:
        for placement in lane.placement_competition.placements:
            if placement.placement_id not in requested:
                continue
            for geometry in placement.frames:
                ordinal = global_ordinals.get(
                    (placement.lane_id, geometry.lane_ordinal)
                )
                if ordinal is not None:
                    values.append((ordinal, geometry))
    return tuple(
        sorted(
            values,
            key=lambda item: (item[0], item[1].lane_ordinal),
        )
    )


def primary_geometry_by_identity(
    detection: FinalDetection,
) -> tuple[tuple[int, TemplateFrame], ...]:
    """Return one lane-local winner, or its best candidate when withheld."""

    placement_ids = tuple(
        lane.placement_competition.selected_placement_id
        or (
            lane.placement_competition.placements[0].placement_id
            if lane.placement_competition.placements
            else ""
        )
        for lane in detection.candidate.geometry.lane_reconstructions
    )
    return _placement_geometry_by_identity(
        detection,
        tuple(value for value in placement_ids if value),
    )


def runner_geometry_by_identity(
    detection: FinalDetection,
) -> tuple[tuple[int, TemplateFrame], ...]:
    placement_ids = tuple(
        lane.placement_competition.runner_up_placement_id
        for lane in detection.candidate.geometry.lane_reconstructions
        if lane.placement_competition.runner_up_placement_id is not None
    )
    return _placement_geometry_by_identity(detection, placement_ids)


def output_footprints(
    detection: FinalDetection,
) -> tuple[OutputFootprint, ...]:
    return detection.output_footprints


def selection_summary(detection: FinalDetection) -> str:
    lanes = detection.candidate.geometry.lane_reconstructions
    placements = sum(len(item.placement_competition.placements) for item in lanes)
    phase = sum(item.prepared.phase_competition.receipt.phase_hypothesis_count for item in lanes)
    authority_evaluations = sum(
        item.prepared.phase_competition.receipt
        .candidate_direct_role_authority_evaluation_count
        for item in lanes
    )
    authority_terminals = sum(
        item.prepared.phase_competition.receipt
        .candidate_direct_role_authority_terminal_count
        for item in lanes
    )
    projection_evaluations = sum(
        item.prepared.phase_competition.receipt
        .candidate_direct_role_projection_evaluation_count
        for item in lanes
    )
    projection_successes = sum(
        item.prepared.phase_competition.receipt
        .candidate_direct_role_projection_success_count
        for item in lanes
    )
    projected_bindings = sum(
        item.prepared.phase_competition.receipt
        .candidate_direct_role_projection_binding_count
        for item in lanes
    )
    vetoes = sum(len(item.content_veto_facts) for item in lanes)
    selected = sum(item.selected_placement is not None for item in lanes)
    bounded = any(item.work.bound_exceeded for item in lanes)
    return (
        f"PHASE {phase} · AUTH {authority_evaluations}/{authority_terminals} TERMINAL · "
        f"PROJECT {projection_evaluations}/{projection_successes} · "
        f"DROP {projected_bindings} · "
        f"PLACEMENTS {placements} · SELECTED {selected} · "
        f"VETO {vetoes} · BOUND {'EXCEEDED' if bounded else 'OK'}"
    )


def competition_summary(detection: FinalDetection) -> str:
    """Explain which physical fit differs without inventing a combined score."""

    def projection_label(fit: object, projection: object) -> str:
        if fit is None or projection is None:
            return "NONE"
        reason = "NONE" if projection.reason is None else projection.reason
        return (
            f"OFFSET {fit.phase_lattice_fit.integer_slot_offset} / "
            f"{projection.outcome.value.upper()} / "
            f"RANK {projection.retained_direct_constraint_rank} / "
            f"DROP {len(projection.projected_out_bindings)} / "
            f"FAILURE {reason}"
        )

    lanes = detection.candidate.geometry.lane_reconstructions
    differences: set[str] = set()
    phase_bases: set[str] = set()
    cross_bases: set[str] = set()
    phase_projection_states: set[str] = set()
    for lane in lanes:
        competition = lane.placement_competition
        phase_competition = lane.prepared.phase_competition
        phase_basis = phase_competition.winner_basis
        if phase_basis is not None:
            phase_bases.add(phase_basis.value.upper().replace("_", " "))
        best_projection = (
            phase_competition.best_phase_candidate_authority_projection
        )
        runner_projection = (
            phase_competition.runner_phase_candidate_authority_projection
        )
        if best_projection is not None:
            phase_projection_states.add(
                "BEST "
                + projection_label(phase_competition.best, best_projection)
                + " / RUNNER "
                + projection_label(
                    phase_competition.runner_up,
                    runner_projection,
                )
            )
        cross_basis = lane.prepared.cross_competition.winner_basis
        if cross_basis is not None:
            cross_bases.add(cross_basis.value.upper().replace("_", " "))
        if lane.prepared.phase_competition.runner_up is not None:
            differences.add("PHASE")
        if lane.prepared.cross_competition.runner_up is not None:
            differences.add("CROSS")
        if not competition.placements:
            continue
        primary_id = competition.selected_placement_id or competition.placements[0].placement_id
        primary = next(
            item for item in competition.placements if item.placement_id == primary_id
        )
        runner = next(
            (
                item
                for item in competition.placements
                if item.placement_id == competition.runner_up_placement_id
            ),
            None,
        )
        if runner is None:
            continue
        if runner.sequence_fit != primary.sequence_fit:
            differences.add("PHASE")
        if runner.cross_fit != primary.cross_fit:
            differences.add("CROSS")
    selection = detection.candidate.geometry.source_placement_selection
    if selection.state.value == "supported":
        phase_basis = (
            "/".join(sorted(phase_bases)) if phase_bases else "UNAVAILABLE"
        )
        cross_basis = (
            "/".join(sorted(cross_bases)) if cross_bases else "UNAVAILABLE"
        )
        basis = (
            f"PHASE {phase_basis} + CROSS {cross_basis} + "
            "CONTENT SAFE + SHARED SOURCE"
        )
        subject = "WINNER BASIS"
    else:
        basis = "NO UNIQUE SAFE SOURCE PLACEMENT"
        subject = "BEST CANDIDATE ONLY"
    runner = "NONE" if not differences else "/".join(sorted(differences))
    authority = (
        "UNAVAILABLE"
        if not phase_projection_states
        else " + ".join(sorted(phase_projection_states))
    )
    return (
        f"{subject} · {basis} · PHASE PROJECT {authority} · "
        f"RUNNER DIFF {runner}"
    )


def alignment_summary(detection: FinalDetection) -> str:
    """Summarize actual-versus-template deviation without a score."""

    values: list[str] = []
    for lane in detection.candidate.geometry.lane_reconstructions:
        diagnostic = template_alignment_diagnostic(
            lane.prepared.phase_competition,
            lane.prepared.sequence_edges,
            lane.prepared.separator_bands,
        )
        label = diagnostic.pattern.value.upper().replace("_", " ")
        authority = diagnostic.global_lattice_authority
        rank = 0 if authority is None else authority.joint_constraint_rank
        nominal = diagnostic.calibrated_nominal_grid_evidence
        nominal_frames = (
            "-"
            if nominal is None or not nominal.unobserved_frame_ordinals
            else ",".join(map(str, nominal.unobserved_frame_ordinals))
        )
        nominal_failure = (
            ""
            if nominal is None or nominal.failure_kind is None
            else f"{nominal.failure_kind.value.upper()} "
        )
        nominal_proof = (
            "N/A"
            if nominal is None
            else (
                f"{nominal.state.value.upper()} {nominal_failure}"
                f"A{len(nominal.phase_anchor_role_indices)} "
                f"G{len(nominal.inferred_adjacency_ordinals)} "
                f"F{nominal_frames}"
            )
        )
        inferred_coverage = tuple(
            item
            for item in diagnostic.adjacency_observation_coverage
            if item.normal_inference_required
        )
        complete_coverage = sum(
            item.state.value == "complete" for item in inferred_coverage
        )
        continuity_counts = {
            kind: sum(
                item.kind.value == kind
                for item in diagnostic.adjacency_continuity_observations
            )
            for kind in (
                "separator_material",
                "no_counterevidence_observed",
                "normal_separator_counterevidence",
                "separator_material_unresolved",
                "unresolved",
                "coverage_incomplete",
            )
        }
        direct = diagnostic.direct_role_binding_authority
        direct_supported = (
            0
            if direct is None
            else len(direct.facts) - len(direct.unsupported_role_indices)
        )
        direct_total = 0 if direct is None else len(direct.facts)
        direct_evidence_group_count = (
            0
            if direct is None
            else len({item.evidence_group_id for item in direct.facts})
        )
        direct_aperture_required = (
            0
            if direct is None
            else len(direct.direct_aperture_required_role_indices)
        )
        outer = diagnostic.outer_frame_observation_authority
        outer_count = (
            0
            if outer is None
            else int(bool(outer.first_frame_observation_ids))
            + int(bool(outer.last_frame_observation_ids))
        )
        width_inference = diagnostic.frame_width_inference
        width_proof = (
            "N/A"
            if width_inference is None
            else (
                f"{len(width_inference.supporting_frame_ordinals)}F/"
                f"{len(width_inference.inferred_role_indices)}R/"
                f"{len(width_inference.validation_only_role_indices)}V"
                if width_inference.state.value == "supported"
                else width_inference.failure_kind.value.upper()
            )
        )
        source_width = lane.prepared.source_frame_width_authority
        source_width_proof = (
            f"{len(source_width.supporting_frame_ordinals)}F"
            if source_width.state.value == "supported"
            else source_width.failure_kind.value.upper()
        )
        separator_counts = {
            polarity: (
                sum(
                    item.material_support_region_count
                    == SPATIAL_SUPPORT_REGION_COUNT
                    for item in lane.prepared.separator_bands
                    if item.material_polarity.value == polarity
                ),
                sum(
                    item.material_polarity.value == polarity
                    for item in lane.prepared.separator_bands
                ),
                sum(
                    item.material_polarity.value == polarity
                    and item.evidence_state.value == "contradiction"
                    for item in lane.prepared.separator_bands
                ),
            )
            for polarity in ("dark", "light")
        }
        joint_total = len(lane.prepared.cross_height_edge_resolutions)
        joint_authority = sum(
            item.kind.value == "bound_direct_edge"
            for item in lane.prepared.cross_height_edge_resolutions
        )
        joint_standalone = sum(
            item.kind.value == "standalone_edge"
            for item in lane.prepared.cross_height_edge_resolutions
        )
        joint_ambiguous = sum(
            item.state.value == "contradicted"
            for item in lane.prepared.cross_height_edge_resolutions
        )
        joint_unavailable = sum(
            item.state.value == "unavailable"
            for item in lane.prepared.cross_height_edge_resolutions
        )
        joint_separator = sum(
            item.measurement_basis.value == "cross_height_aggregate"
            for item in lane.prepared.separator_bands
        )
        proof = (
            f"GLOBAL {rank}/3 · NOMINAL {nominal_proof} · ADJ "
            f"{complete_coverage}/{len(inferred_coverage)} · CONT "
            f"S{continuity_counts['separator_material']} "
            f"N{continuity_counts['no_counterevidence_observed']} "
            f"X{continuity_counts['normal_separator_counterevidence']} "
            f"M{continuity_counts['separator_material_unresolved']} "
            f"U{continuity_counts['unresolved']} "
            f"I{continuity_counts['coverage_incomplete']} · DIRECT "
            f"{direct_supported}/{direct_total} G{direct_evidence_group_count} · "
            f"APERTURE DOMAIN "
            f"{direct_aperture_required} · OUTER "
            f"{outer_count}/2 · SOURCE W {source_width_proof} · "
            f"W INFER {width_proof} · SEP "
            f"D {separator_counts['dark'][0]}/{separator_counts['dark'][1]}"
            f" C{separator_counts['dark'][2]} "
            f"L {separator_counts['light'][0]}/{separator_counts['light'][1]}"
            f" C{separator_counts['light'][2]} · JOINT "
            f"B{joint_authority} S{joint_standalone}/{joint_total} "
            f"A{joint_ambiguous} "
            f"U{joint_unavailable} P{joint_separator}"
        )
        if diagnostic.pattern.value == "unresolved":
            values.append(f"{lane.lane_id} {label} · {proof}")
            continue
        pitch_delta = float(
            diagnostic.pitch_delta_from_compiled_center_px or 0.0
        )
        residual = diagnostic.maximum_absolute_role_residual_px
        values.append(
            f"{lane.lane_id} {label} · {proof} · "
            f"PITCH Δ {pitch_delta:+.2f}px · "
            f"ROLE RESIDUAL {'N/A' if residual is None else f'{residual:.2f}px'}"
        )
    return "ALIGNMENT · " + " | ".join(values)


def selected_output_safety_summary(detection: FinalDetection) -> str:
    """Name boundary ownership and the largest final per-side budget use."""

    geometry = detection.candidate.geometry
    outputs = detection.output_footprints
    budgets = geometry.direct_use_budget_assessments
    if not outputs or not budgets:
        return "SELECTED OUTPUT SAFETY · NOT EVALUATED"
    uses = "/".join(
        sorted(
            {
                output.envelope.boundary_use.value.upper().replace("_", " ")
                for output in outputs
            }
        )
    )
    ratios = tuple(
        edge.expansion_mm / edge.limit_mm
        for budget in budgets
        for edge in budget.edge_assessments
        if edge.limit_applies and edge.limit_mm > 0.0
    ) + tuple(
        float(budget.maximum_same_state_cross_alignment_padding_mm)
        / min(
            edge.limit_mm
            for edge in budget.edge_assessments
            if edge.role.value in {"top", "bottom"}
        )
        for budget in budgets
        if budget.maximum_same_state_cross_alignment_padding_mm is not None
    )
    protections = tuple(
        protection
        for output in outputs
        for protection in output.boundary_protections
    )
    measurement = max(
        (item.measurement_expansion_px for item in protections),
        default=0.0,
    )
    residual = max(
        (item.local_boundary_residual_px for item in protections),
        default=0.0,
    )
    sequence_bleed = max(
        (
            item.bleed_px
            for item in protections
            if item.role.value in {"start", "end"}
        ),
        default=0.0,
    )
    cross_bleed = max(
        (
            item.bleed_px
            for item in protections
            if item.role.value in {"top", "bottom"}
        ),
        default=0.0,
    )
    maximum = "N/A" if not ratios else f"{100.0 * max(ratios):.1f}%"
    source_saturations = tuple(
        fact
        for output in outputs
        for fact in output.saturation_facts
        if fact.source_boundary
    )
    optional_count = sum(
        fact.kind == FootprintSaturationKind.SOURCE_BOUNDARY_OPTIONAL_BLEED
        for fact in source_saturations
    )
    joint_count = len(source_saturations) - optional_count
    maximum_overflow = max(
        (fact.requested_overflow_px for fact in source_saturations),
        default=0.0,
    )
    saturation = (
        ""
        if not source_saturations
        else (
            f" · SOURCE EDGE B{optional_count}/J{joint_count} · "
            f"MAX {maximum_overflow:.1f}px"
        )
    )
    return (
        f"SELECTED OUTPUT SAFETY · {uses} · JOINT {measurement:.1f}px · "
        f"RESIDUAL {residual:.1f}px · BLEED S{sequence_bleed:.1f}/"
        f"C{cross_bleed:.1f}px · MAX 5% BUDGET USE {maximum}{saturation}"
    )


def root_gate_summary(detection: FinalDetection) -> str:
    blocking = detection.decision.blocking_checks
    if not blocking:
        return "ROOT GATE · ALL REQUIRED CHECKS SUPPORTED"
    check = blocking[0]
    failure = check.failure
    if failure is None:
        return f"ROOT GATE · {check.code.upper()}"
    return (
        f"ROOT GATE · {check.code.upper()} → {failure.gap.value.upper()} · "
        f"NEED {failure.minimum_missing_fact.value.upper()} · "
        f"ACTION {failure.recommended_action.value.upper()}"
    )


def axis_authority_summaries(
    detection: FinalDetection,
) -> tuple[str, str, str]:
    lanes = detection.candidate.geometry.lane_reconstructions
    selection = detection.candidate.geometry.source_placement_selection
    coarse_long = "/".join(
        sorted(
            {
                lane.prepared.coarse_support.long_axis.authority.value
                .upper()
                .replace("_", " ")
                for lane in lanes
            }
        )
    )
    coarse_short = "/".join(
        sorted(
            {
                lane.prepared.coarse_support.short_axis.authority.value
                .upper()
                .replace("_", " ")
                for lane in lanes
            }
        )
    )
    direction_values = tuple(
        lane.prepared.coarse_support.shared_direction
        for lane in lanes
        if lane.prepared.coarse_support.shared_direction is not None
    )
    direction = (
        "UNAVAILABLE"
        if not direction_values
        else "/".join(
            sorted(
                {
                    f"{value.canonical_direction_degrees:+.3f}deg"
                    for value in direction_values
                }
            )
        )
    )
    enclosing = sum(
        lane.prepared.coarse_support.enclosing_support is not None
        for lane in lanes
    )
    phase_status = "/".join(
        sorted(
            {
                lane.prepared.phase_competition.status.value.upper()
                for lane in lanes
            }
        )
    )
    lattice_fit_bases = "/".join(
        sorted(
            {
                lane.prepared.phase_competition.best
                .lattice_parameter_fit_basis.value.upper()
                for lane in lanes
                if lane.prepared.phase_competition.best is not None
            }
        )
    )
    lattice_fit_suffix = (
        "" if not lattice_fit_bases else f" · PARAM {lattice_fit_bases}"
    )
    cross_status = "/".join(
        sorted(
            {
                lane.prepared.cross_competition.status.value.upper()
                for lane in lanes
            }
        )
    )
    cross_failures = "/".join(
        sorted(
            {
                lane.prepared.cross_competition.failure_kind.value.upper()
                for lane in lanes
                if lane.prepared.cross_competition.failure_kind is not None
            }
        )
    )
    cross_pair_modes = "/".join(
        sorted(
            {
                lane.prepared.cross_competition.best.pair_support_mode.value
                .upper()
                for lane in lanes
                if lane.prepared.cross_competition.best is not None
                and lane.prepared.cross_competition.best.pair_support_mode
                is not None
            }
        )
    )
    cross_failure_suffix = (
        "" if not cross_failures else f" · FAILURE {cross_failures}"
    )
    cross_pair_mode_suffix = (
        "" if not cross_pair_modes else f" · PAIR {cross_pair_modes}"
    )
    phase_runners = sum(
        lane.prepared.phase_competition.runner_up is not None
        for lane in lanes
    )
    cross_runners = sum(
        lane.prepared.cross_competition.runner_up is not None
        for lane in lanes
    )
    width_calibrated = sum(
        bool(lane.prepared.source_scan_geometry.width_state.observation_ids)
        for lane in lanes
    )
    height_calibrated = sum(
        bool(lane.prepared.source_scan_geometry.height_state.observation_ids)
        for lane in lanes
    )
    aspect_labels: set[str] = set()
    for lane in lanes:
        authority = (
            lane.prepared.cross_competition.aperture_aspect_ratio_authority
        )
        if authority.state.value == "supported":
            raw_ratio = authority.raw_width_over_height
            ratio = authority.guarded_width_over_height
            height = authority.effective_height_px
            assert raw_ratio is not None and ratio is not None and height is not None
            use = (
                "USED"
                if authority.consumed_for_cross_inference
                else "DIRECT"
                if authority.direct_height_px is not None
                else "READY"
            )
            aspect_labels.add(
                f"{use} Rraw{raw_ratio.minimum:.3f}-{raw_ratio.maximum:.3f} "
                f"Rguard{ratio.minimum:.3f}-{ratio.maximum:.3f} "
                f"gW{authority.width_guard_ratio:.3%} "
                f"gH{authority.height_guard_ratio:.3%} "
                f"H{height.minimum:.1f}-{height.maximum:.1f}px"
            )
        else:
            failure = authority.failure_kind
            label = (
                "DIRECT RATIO-NOT-USED"
                if authority.direct_height_px is not None
                else "UNAVAILABLE"
                if failure is None
                else failure.value.upper()
            )
            raw_ratio = authority.raw_width_over_height
            ratio = authority.guarded_width_over_height
            height = authority.effective_height_px
            if raw_ratio is not None:
                label += (
                    f" Rraw{raw_ratio.minimum:.3f}-{raw_ratio.maximum:.3f}"
                )
            if ratio is not None:
                label += (
                    f" Rguard{ratio.minimum:.3f}-{ratio.maximum:.3f}"
                    f" gW{authority.width_guard_ratio:.3%}"
                    f" gH{authority.height_guard_ratio:.3%}"
                )
            if height is not None:
                label += f" H{height.minimum:.1f}-{height.maximum:.1f}px"
            if authority.blocks_cross_resolution:
                label += " BLOCK"
            aspect_labels.add(label)
    aspect_summary = "/".join(sorted(aspect_labels))
    if selection.state.value != "supported":
        competitors = sum(
            len(item.placement_competition.placements) for item in lanes
        )
        failure = selection.failure
        detail = (
            "PLACEMENT UNRESOLVED"
            if failure is None
            else failure.detail.replace("_", " ").upper()
        )
        return (
            f"CROSS FIT · {cross_status} · COARSE {coarse_short} · "
            f"COARSE ORIENTATION {direction} · ENCLOSING {enclosing} · "
            f"RUNNER {cross_runners}{cross_failure_suffix}",
            f"SEQUENCE FIT · {phase_status} · COARSE {coarse_long} · "
            f"RUNNER {phase_runners}{lattice_fit_suffix}",
            f"SOURCE FIT · {competitors} PLACEMENTS · APERTURE "
            f"W {width_calibrated}/{len(lanes)} H "
            f"{height_calibrated}/{len(lanes)} · RATIO {aspect_summary} · "
            f"{detail}",
        )
    direct_sequence = sum(
        len(item.prepared.phase_competition.best.bound_observation_ids)
        for item in lanes
        if item.prepared.phase_competition.best is not None
    )
    inferred_sequence = sum(
        len(item.prepared.phase_competition.best.unbound_role_indices)
        for item in lanes
        if item.prepared.phase_competition.best is not None
    )
    direct_cross = sum(
        len(item.prepared.cross_competition.best.direct_bindings)
        for item in lanes
        if item.prepared.cross_competition.best is not None
    )
    inferred_cross = sum(
        len(item.prepared.cross_competition.best.inferred_bindings)
        for item in lanes
        if item.prepared.cross_competition.best is not None
    )
    runners = sum(
        item.placement_competition.runner_up_placement_id is not None
        for item in lanes
    )
    return (
        f"CROSS FIT · {cross_status} · COARSE {coarse_short} · "
        f"COARSE ORIENTATION {direction} · ENCLOSING {enclosing} → "
        + "/".join(
            sorted(
                {
                    lane.prepared.cross_competition.best.boundary_use.value
                    .upper()
                    .replace("_", " ")
                    for lane in lanes
                    if lane.prepared.cross_competition.best is not None
                }
            )
        )
        + f" · DIRECT {direct_cross} · INFERRED {inferred_cross}"
        + cross_pair_mode_suffix,
        f"SEQUENCE FIT · {phase_status} · COARSE {coarse_long} → "
        f"DIRECT {direct_sequence} · INFERRED {inferred_sequence}"
        f"{lattice_fit_suffix}",
        f"SOURCE FIT · LANES {len(lanes)} · APERTURE W "
        f"{width_calibrated}/{len(lanes)} H {height_calibrated}/{len(lanes)} · "
        f"RATIO {aspect_summary} · RUNNERS {runners} · GATE SUPPORTED",
    )


def source_projection(workspace: DetectionWorkspace) -> Projection:
    height, width = workspace.source_gray.shape
    return Projection(
        source_width=width,
        source_height=height,
        rotate_clockwise=workspace.layout == "vertical",
    )


def source_image(
    workspace: DetectionWorkspace,
    render_cache: DebugRenderCache,
) -> tuple[Image.Image, Projection]:
    projection = source_projection(workspace)
    return (
        cached_source_image(
            render_cache,
            workspace.source_gray,
            rotate_clockwise=projection.rotate_clockwise,
        ),
        projection,
    )
