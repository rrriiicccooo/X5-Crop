"""Read-only report/runtime facts consumed by Debug Analysis panels."""

from __future__ import annotations

from PIL import Image

from ..detection.final.model import FinalDetection
from ..detection.photo_geometry.output_model import OutputFootprint
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
    vetoes = sum(len(item.content_veto_facts) for item in lanes)
    selected = sum(item.selected_placement is not None for item in lanes)
    bounded = any(item.work.bound_exceeded for item in lanes)
    return (
        f"PHASE {phase} · PLACEMENTS {placements} · SELECTED {selected} · "
        f"VETO {vetoes} · BOUND {'EXCEEDED' if bounded else 'OK'}"
    )


def competition_summary(detection: FinalDetection) -> str:
    """Explain which physical fit differs without inventing a combined score."""

    lanes = detection.candidate.geometry.lane_reconstructions
    differences: set[str] = set()
    phase_bases: set[str] = set()
    cross_bases: set[str] = set()
    for lane in lanes:
        competition = lane.placement_competition
        phase_basis = lane.prepared.phase_competition.winner_basis
        if phase_basis is not None:
            phase_bases.add(phase_basis.value.upper().replace("_", " "))
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
    return f"{subject} · {basis} · RUNNER DIFF {runner}"


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
        if diagnostic.pattern.value == "unresolved":
            values.append(f"{lane.lane_id} {label}")
            continue
        pitch_delta = float(
            diagnostic.pitch_delta_from_compiled_center_px or 0.0
        )
        residual = diagnostic.maximum_absolute_role_residual_px
        values.append(
            f"{lane.lane_id} {label} · PITCH Δ {pitch_delta:+.2f}px · "
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
    return (
        f"SELECTED OUTPUT SAFETY · {uses} · JOINT {measurement:.1f}px · "
        f"RESIDUAL {residual:.1f}px · BLEED S{sequence_bleed:.1f}/"
        f"C{cross_bleed:.1f}px · MAX 5% BUDGET USE {maximum}"
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
    cross_status = "/".join(
        sorted(
            {
                lane.prepared.cross_competition.status.value.upper()
                for lane in lanes
            }
        )
    )
    phase_runners = sum(
        lane.prepared.phase_competition.runner_up is not None
        for lane in lanes
    )
    cross_runners = sum(
        lane.prepared.cross_competition.runner_up is not None
        for lane in lanes
    )
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
            f"RUNNER {cross_runners}",
            f"SEQUENCE FIT · {phase_status} · COARSE {coarse_long} · "
            f"RUNNER {phase_runners}",
            f"SOURCE FIT · {competitors} PLACEMENTS · {detail}",
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
        + f" · DIRECT {direct_cross} · INFERRED {inferred_cross}",
        f"SEQUENCE FIT · {phase_status} · COARSE {coarse_long} → "
        f"DIRECT {direct_sequence} · INFERRED {inferred_sequence}",
        f"SOURCE FIT · LANES {len(lanes)} · RUNNERS {runners} · GATE SUPPORTED",
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
