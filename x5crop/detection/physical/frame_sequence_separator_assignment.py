from __future__ import annotations

from dataclasses import replace

from ...domain import (
    BoundarySide,
    EvidenceState,
    HolderBoundaryObservation,
    InterFrameBoundaryReference,
    InterFrameSpacing,
    InterFrameSpacingBasis,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
    SeparatorBandCrossAxisSupport,
)
from . import frame_sequence_candidates as sequence_candidates
from . import frame_sequence_measurements as measurement_facts
from .model import (
    BoundaryGeometryState,
    CommonFrameWidthResolution,
    FrameBoundarySource,
    FrameSlot,
    ResolvedFrameBoundary,
    SeparatorBandAssignment,
    boundary_role_is_independent_physical_measurement,
)


def separator_band_edge_constraint(
    support: SeparatorBandCrossAxisSupport,
    position: PixelInterval,
) -> measurement_facts.EdgeConstraint:
    observation = support.observation
    if position not in {observation.leading_edge, observation.trailing_edge}:
        raise ValueError("separator edge constraint must preserve one observed edge")
    return measurement_facts.EdgeConstraint(
        position=position,
        basis=FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION,
        state=EvidenceState.UNAVAILABLE,
        geometry_state=BoundaryGeometryState.RESOLVED,
        provenance=observation.provenance,
        separator=observation,
        separator_cross_axis=support.measurement,
    )

def observed_band_edges(
    support: SeparatorBandCrossAxisSupport,
) -> tuple[measurement_facts.EdgeConstraint, measurement_facts.EdgeConstraint]:
    observation = support.observation
    return (
        separator_band_edge_constraint(
            support,
            observation.leading_edge,
        ),
        separator_band_edge_constraint(
            support,
            observation.trailing_edge,
        ),
    )

def _separator_edge_with_supported_role(
    constraint: measurement_facts.EdgeConstraint,
) -> measurement_facts.EdgeConstraint:
    if (
        constraint.basis != FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION
        or constraint.separator is None
        or constraint.separator_cross_axis is None
        or not measurement_facts.separator_edge_path_is_supported(constraint)
    ):
        raise ValueError("separator role requires a supported raw band observation")
    return replace(constraint, state=EvidenceState.SUPPORTED)

def _separator_pair_fits_sequence(
    trailing: measurement_facts.EdgeConstraint,
    leading: measurement_facts.EdgeConstraint,
    frame_width: PixelInterval,
) -> bool:
    band = trailing.separator
    return bool(
        band is not None
        and band is leading.separator
        and trailing.separator_cross_axis is leading.separator_cross_axis
        and trailing.external_side is None
        and leading.external_side is None
        and trailing.separator_cross_axis is not None
        and trailing.separator_cross_axis.complete_separator_supported
        and trailing.position == band.leading_edge
        and leading.position == band.trailing_edge
        and band.width_px.minimum > 0.0
        and band.width_px.maximum < frame_width.minimum
    )

def candidate_specific_separator_edge_roles(
    constraints: tuple[measurement_facts.MeasuredFrameConstraint, ...],
) -> tuple[measurement_facts.MeasuredFrameConstraint, ...]:
    updated = list(constraints)
    for boundary_index in range(1, len(updated)):
        left = updated[boundary_index - 1]
        right = updated[boundary_index]
        if measurement_facts.separator_edge_path_is_supported(left.trailing):
            updated[boundary_index - 1] = replace(
                left,
                trailing=_separator_edge_with_supported_role(left.trailing),
            )
        if measurement_facts.separator_edge_path_is_supported(right.leading):
            updated[boundary_index] = replace(
                right,
                leading=_separator_edge_with_supported_role(right.leading),
            )
    return tuple(updated)

def candidate_specific_holder_band_roles(
    constraints: tuple[measurement_facts.MeasuredFrameConstraint, ...],
    frame_width: PixelInterval,
    holder_boundaries: dict[BoundarySide, HolderBoundaryObservation],
) -> tuple[measurement_facts.MeasuredFrameConstraint, ...]:
    updated = list(constraints)
    internal_sequence_complete = len(updated) > 1 and all(
        _separator_pair_fits_sequence(
            updated[boundary_index - 1].trailing,
            updated[boundary_index].leading,
            frame_width,
        )
        for boundary_index in range(1, len(updated))
    )
    if internal_sequence_complete:
        for slot_index, side in (
            (0, BoundarySide.LEADING),
            (len(updated) - 1, BoundarySide.TRAILING),
        ):
            boundary = (
                updated[slot_index].leading
                if side == BoundarySide.LEADING
                else updated[slot_index].trailing
            )
            band = boundary.separator
            holder_boundary = holder_boundaries.get(side)
            if (
                band is None
                or boundary.external_side != side
                or boundary.separator_cross_axis is None
                or not measurement_facts.separator_edge_path_is_supported(boundary)
                or holder_boundary is None
                or band.width_px.maximum >= frame_width.minimum
                or not PixelInterval(
                    band.leading_edge.minimum,
                    band.trailing_edge.maximum,
                ).intersects(holder_boundary.position)
            ):
                continue
            supported = _separator_edge_with_supported_role(boundary)
            if side == BoundarySide.LEADING:
                updated[slot_index] = replace(
                    updated[slot_index],
                    leading=supported,
                )
            else:
                updated[slot_index] = replace(
                    updated[slot_index],
                    trailing=supported,
                )
    return tuple(updated)

def spacing_for_band(
    boundary_index: int,
    support: SeparatorBandCrossAxisSupport,
    trailing: ResolvedFrameBoundary,
    leading: ResolvedFrameBoundary,
) -> tuple[InterFrameSpacing, sequence_candidates.SeparatorBandBinding | None]:
    band = support.observation
    measurement = support.measurement
    supported = bool(
        measurement.complete_separator_supported
        and band.width_px.minimum > 0.0
        and trailing.role_state == EvidenceState.SUPPORTED
        and leading.role_state == EvidenceState.SUPPORTED
        and trailing.source == FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION
        and leading.source == FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION
    )
    assignment = (
        sequence_candidates.SeparatorBandBinding(
            boundary_index,
            band,
            measurement,
            trailing,
            leading,
        )
        if supported
        else None
    )
    if assignment is not None:
        provenance = band.provenance
        basis = InterFrameSpacingBasis.OBSERVED
    elif (
        trailing.source == FrameBoundarySource.GRAY_PATH_OBSERVATION
        and leading.source == FrameBoundarySource.GRAY_PATH_OBSERVATION
    ):
        return (
            sequence_candidates.spacing_from_frame_edges(
                boundary_index,
                trailing,
                leading,
            ),
            None,
        )
    else:
        provenance = MeasurementProvenance(
            root_measurement=MeasurementIdentity.FRAME_GEOMETRY,
            observation_id=ObservationId(
                f"dimension_spacing:{boundary_index}:"
                f"{trailing.measurement_provenance.observation_id}:"
                f"{leading.measurement_provenance.observation_id}"
            ),
            dependencies=tuple(
                dict.fromkeys(
                    (
                        MeasurementIdentity.FRAME_DIMENSIONS,
                        band.provenance.root_measurement,
                    )
                )
            ),
            description="dimension-constrained inter-frame spacing",
            boundary_anchors=tuple(
                dict.fromkeys(
                    (
                        trailing.measurement_provenance.observation_id,
                        leading.measurement_provenance.observation_id,
                    )
                )
            ),
        )
        basis = InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS
    return (
        InterFrameSpacing(
            boundary=InterFrameBoundaryReference(None, boundary_index),
            signed_width_px=leading.position.minus(trailing.position),
            provenance=provenance,
            basis=basis,
        ),
        assignment,
    )

def separator_observation_assignment(
    build: sequence_candidates.SequenceBuild,
    boundary_index: int,
    support: SeparatorBandCrossAxisSupport,
    common_width: CommonFrameWidthResolution,
) -> tuple[tuple[FrameSlot, ...], sequence_candidates.SeparatorBandBinding] | None:
    if (
        common_width.state != EvidenceState.SUPPORTED
        or common_width.width_px is None
        or not support.measurement.complete_separator_supported
        or support.observation.width_px.minimum <= 0.0
        or support.observation.width_px.maximum >= common_width.width_px.minimum
        or not 1 <= boundary_index < len(build.slots)
    ):
        return None
    left = build.slots[boundary_index - 1]
    right = build.slots[boundary_index]
    if left.sequence_inferred or right.sequence_inferred:
        return None
    replaceable_sources = {
        FrameBoundarySource.DIMENSION_CONSTRAINED,
        FrameBoundarySource.GRAY_PATH_OBSERVATION,
    }
    if (
        left.trailing.source not in replaceable_sources
        or right.leading.source not in replaceable_sources
        or (
            left.trailing.role_state == EvidenceState.SUPPORTED
            and boundary_role_is_independent_physical_measurement(left.trailing)
        )
        or (
            right.leading.role_state == EvidenceState.SUPPORTED
            and boundary_role_is_independent_physical_measurement(right.leading)
        )
    ):
        return None
    observed_trailing, observed_leading = tuple(
        _separator_edge_with_supported_role(edge)
        for edge in observed_band_edges(support)
    )
    trailing, _ = sequence_candidates.resolve_edge_constraint(
        left.index,
        BoundarySide.TRAILING,
        observed_trailing,
    )
    leading, _ = sequence_candidates.resolve_edge_constraint(
        right.index,
        BoundarySide.LEADING,
        observed_leading,
    )
    left_width = trailing.position.minus(left.leading.position)
    right_width = right.trailing.position.minus(leading.position)
    if (
        measurement_facts.positive_interval(left_width) is None
        or measurement_facts.positive_interval(right_width) is None
        or not measurement_facts.measurement_intervals_are_compatible(
            left_width,
            common_width.width_px,
        )
        or not measurement_facts.measurement_intervals_are_compatible(
            right_width,
            common_width.width_px,
        )
    ):
        return None
    slots = list(build.slots)
    slots[boundary_index - 1] = replace(
        left,
        trailing=trailing,
        visible_long_axis=PixelInterval(
            left.leading.position.minimum,
            trailing.position.maximum,
        ),
    )
    slots[boundary_index] = replace(
        right,
        leading=leading,
        visible_long_axis=PixelInterval(
            leading.position.minimum,
            right.trailing.position.maximum,
        ),
    )
    resolved_slots = tuple(slots)
    if not sequence_candidates.frame_slots_are_strictly_monotonic(resolved_slots):
        return None
    return (
        resolved_slots,
        sequence_candidates.SeparatorBandBinding(
            boundary_index=boundary_index,
            observation=support.observation,
            cross_axis_measurement=support.measurement,
            preceding_trailing_edge=trailing,
            following_leading_edge=leading,
        ),
    )

def assign_unique_separator_observations(
    build: sequence_candidates.SequenceBuild,
    common_width: CommonFrameWidthResolution,
    supports: tuple[SeparatorBandCrossAxisSupport, ...],
) -> sequence_candidates.SequenceBuild:
    resolved = build
    remaining = tuple(
        support
        for support in supports
        if support.observation.provenance.observation_id
        not in {
            binding.observation.provenance.observation_id
            for binding in build.separator_bindings
        }
    )
    while remaining:
        candidates: dict[
            int,
            list[
                tuple[
                    SeparatorBandCrossAxisSupport,
                    tuple[FrameSlot, ...],
                    sequence_candidates.SeparatorBandBinding,
                ]
            ],
        ] = {}
        support_boundaries: dict[ObservationId, list[int]] = {}
        for boundary_index in range(1, len(resolved.slots)):
            if any(
                binding.boundary_index == boundary_index
                for binding in resolved.separator_bindings
            ):
                continue
            for support in remaining:
                assignment = separator_observation_assignment(
                    resolved,
                    boundary_index,
                    support,
                    common_width,
                )
                if assignment is None:
                    continue
                slots, binding = assignment
                candidates.setdefault(boundary_index, []).append(
                    (support, slots, binding)
                )
                support_boundaries.setdefault(
                    support.observation.provenance.observation_id,
                    [],
                ).append(boundary_index)
        unique = tuple(
            items[0]
            for boundary_index, items in sorted(candidates.items())
            if len(items) == 1
            and len(
                support_boundaries[
                    items[0][0].observation.provenance.observation_id
                ]
            )
            == 1
        )
        if not unique:
            break
        support, slots, binding = unique[0]
        resolved = sequence_candidates.rebuild_sequence_build(
            replace(
                resolved,
                separator_bindings=(
                    *resolved.separator_bindings,
                    binding,
                ),
            ),
            slots,
        )
        assigned_id = support.observation.provenance.observation_id
        remaining = tuple(
            item
            for item in remaining
            if item.observation.provenance.observation_id != assigned_id
        )
    return resolved

def separator_assignments_from_bindings(
    bindings: tuple[sequence_candidates.SeparatorBandBinding, ...],
    slots: tuple[FrameSlot, ...],
    common_width: CommonFrameWidthResolution,
) -> tuple[SeparatorBandAssignment, ...]:
    if common_width.state != EvidenceState.SUPPORTED:
        return ()
    assert common_width.width_px is not None
    assignments: list[SeparatorBandAssignment] = []
    for binding in bindings:
        if (
            binding.observation.width_px.minimum <= 0.0
            or binding.observation.width_px.maximum
            >= common_width.width_px.minimum
        ):
            continue
        trailing = slots[binding.boundary_index - 1].trailing
        leading = slots[binding.boundary_index].leading
        if (
            trailing.position != binding.observation.leading_edge
            or leading.position != binding.observation.trailing_edge
        ):
            continue
        assignments.append(
            SeparatorBandAssignment(
                boundary_index=binding.boundary_index,
                observation=binding.observation,
                cross_axis_measurement=binding.cross_axis_measurement,
                frame_width_px=common_width.width_px,
                preceding_trailing_edge=trailing,
                following_leading_edge=leading,
            )
        )
    return tuple(
        sorted(assignments, key=lambda assignment: assignment.boundary_index)
    )
