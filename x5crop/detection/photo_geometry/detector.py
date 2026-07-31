from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import math

import numpy as np

from ...configuration.model import DetectionConfiguration, FrameCountMode
from ...configuration.photo_geometry import (
    FrameSequencePhysicalConstraint,
    frame_sequence_physical_constraints,
)
from ...domain import Box, EvidenceState, FiniteInterval, PositiveInterval
from ..output_geometry import (
    OutputTransformAssessment,
    observed_output_transform_assessment,
)
from ..source_core import SourceContentComponent, SourceLaneEvidence
from .corridors import (
    FramePhysicalPixelIntervals,
    build_sequence_anchor_discovery_domain,
    build_top_bottom_search_corridors,
    frame_physical_pixel_intervals,
    registered_lane_measurement_queries,
    source_lane_box,
)
from .geometry_build import (
    FrameShortAxisCandidate,
    build_frame_photo_geometry,
    content_component_geometry_index,
    known_content_short_interval,
    select_frame_short_axis_candidates,
)
from .measurement import (
    fit_boundary_line_families,
    measure_registered_queries,
)
from .model import (
    AdjacencyKind,
    BoundaryAxis,
    BoundaryRole,
    FirstPhotoStartAssessment,
    FirstPhotoStartOutcome,
    FrameGeometryState,
    FrameSequenceGeometryConstraintSet,
    FrameSequenceGeometrySolution,
    GridInferredBlankOutputGeometry,
    GridSlotTranslationAssessment,
    GridSlotTranslationOutcome,
    OutputSlotIdentity,
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    PhotoBoundaryMeasurementField,
    PhotoBoundaryMeasurementSet,
    PhotoBoundaryObservation,
    PhotoSequenceExtentProposal,
    PhotoSequenceTranslationAssessment,
    PhotoSequenceTranslationOutcome,
    ResolvedOutputGeometry,
    ResolvedOutputSlots,
    SafeCropEnvelope,
    SequenceAnchorDiscoveryDomain,
    SequenceWorkReceipt,
    UndominatedFrameSequenceCandidate,
)
from .output import (
    grid_inferred_blank_output_geometry,
    safe_crop_envelope_from_photo_geometry,
)
from .protection import output_protection_spec
from .selection import (
    eliminate_transition_zone_dominated_lines,
    line_coordinate_at_trace,
    line_coordinate_interval_at_trace,
    positive_content_support_interval,
    outer_observed_assignments,
)
from .sequence import (
    LongAxisSequenceHypothesis,
    frame_long_boundaries,
    photo_translation_assessment,
    sequence_boundary_roles,
    solve_long_axis_sequence_hypotheses,
)

@dataclass(frozen=True)
class LabelSequenceReconstruction:
    constraint: FrameSequencePhysicalConstraint
    aperture_pixels: FramePhysicalPixelIntervals
    gutter_px: FiniteInterval
    raw_long_observations: tuple[PhotoBoundaryObservation, ...]
    physical_long_observations: tuple[PhotoBoundaryObservation, ...]
    hypotheses: tuple[LongAxisSequenceHypothesis, ...]
    content_support_interval_px: FiniteInterval | None
    expected_grid_translation_px: float | None
    outer_observed_assignments: tuple[tuple[str, int], ...]
    shared_scale_constraint_px_per_mm: PositiveInterval


@dataclass(frozen=True)
class LanePhotoGeometryReconstruction:
    lane_id: str
    anchor_domain: SequenceAnchorDiscoveryDomain
    extent_proposals: tuple[PhotoSequenceExtentProposal, ...]
    measurement_sets: tuple[PhotoBoundaryMeasurementSet, ...]
    label_reconstructions: tuple[LabelSequenceReconstruction, ...]
    sequence_choice_ranking: tuple[
        tuple[str, str, tuple[float, ...]], ...
    ]
    selected_label: str | None
    selected_long_hypothesis: LongAxisSequenceHypothesis | None
    constraint_set: FrameSequenceGeometryConstraintSet | None
    solution: FrameSequenceGeometrySolution | None
    all_undominated_states_by_ordinal: tuple[
        tuple[FrameGeometryState, ...], ...
    ]
    undominated_sequence_candidates: tuple[
        UndominatedFrameSequenceCandidate, ...
    ]
    resolved_output_geometries: tuple[ResolvedOutputGeometry, ...]
    selected_observations: tuple[PhotoBoundaryObservation, ...]
    unresolved_codes: tuple[str, ...]


@dataclass(frozen=True)
class PhotoGeometryDetectionResult:
    resolved_output_slots: ResolvedOutputSlots | None
    lane_reconstructions: tuple[LanePhotoGeometryReconstruction, ...]
    output_slot_identities: tuple[OutputSlotIdentity, ...]
    transform_assessment: OutputTransformAssessment
    unresolved_codes: tuple[str, ...]

    @property
    def resolved_output_geometries(
        self,
    ) -> tuple[ResolvedOutputGeometry, ...]:
        return tuple(
            geometry
            for lane in self.lane_reconstructions
            for geometry in lane.resolved_output_geometries
        )


@dataclass(frozen=True)
class _LongContentAssignmentScore:
    complete_assignment: float
    stable_ownership: float
    assignment_fraction: float
    assigned_content_containment_supported: float
    assigned_safe_containment_fraction: float
    safe_containment_fraction: float
    occupied_frame_count: int


MATERIAL_ASSIGNMENT_MINIMUM_FRACTION = 0.5
ASSIGNED_SAFE_CONTAINMENT_MINIMUM_FRACTION = 0.4
MATERIAL_ASSIGNMENT_RESIDUAL_RISK_MINIMUM = 0.90
MATERIAL_ASSIGNMENT_COMPLETE_FRACTION = 0.999
MATERIAL_ASSIGNMENT_EQUIVALENCE_FRACTION = 0.05


def _profile_capacity(
    configuration: DetectionConfiguration,
    lane: SourceLaneEvidence,
) -> int:
    profile = lane.scan_canvas.selected_profile
    if profile is None:
        return 0
    return next(
        (
            fit.maximum_frame_count
            for fit in profile.format_fits
            if fit.format_id == configuration.physical_spec.format_id
        ),
        0,
    )


def resolve_output_slots(
    configuration: DetectionConfiguration,
    lanes: tuple[SourceLaneEvidence, ...],
) -> ResolvedOutputSlots | None:
    if not lanes:
        return None
    request = configuration.count_request
    if configuration.physical_spec.layout.kind == "dual_lane":
        capacity = _profile_capacity(configuration, lanes[0])
        requested = request.authoritative_count
        if (
            requested is None
            or requested != capacity
            or requested % len(lanes)
        ):
            return None
        return ResolvedOutputSlots(
            tuple(requested // len(lanes) for _lane in lanes)
        )
    capacity = _profile_capacity(configuration, lanes[0])
    requested = (
        capacity
        if request.mode == FrameCountMode.AUTO
        else request.authoritative_count
    )
    if requested is None or requested <= 0 or requested > capacity:
        return None
    return ResolvedOutputSlots((requested,))


def _source_axes(layout: str) -> tuple[BoundaryAxis, BoundaryAxis]:
    if layout == "horizontal":
        return BoundaryAxis.X, BoundaryAxis.Y
    if layout == "vertical":
        return BoundaryAxis.Y, BoundaryAxis.X
    raise ValueError(f"unsupported source layout: {layout}")


def _axis_interval(box: Box, axis: BoundaryAxis) -> FiniteInterval:
    return (
        FiniteInterval(float(box.left), float(box.right - 1))
        if axis == BoundaryAxis.X
        else FiniteInterval(float(box.top), float(box.bottom - 1))
    )


def _axis_extent(box: Box, axis: BoundaryAxis) -> int:
    return box.width if axis == BoundaryAxis.X else box.height


def _union_aperture_pixels(
    values: tuple[FramePhysicalPixelIntervals, ...],
) -> FramePhysicalPixelIntervals:
    if not values:
        raise ValueError("combined photo measurement requires aperture labels")
    return FramePhysicalPixelIntervals(
        aperture=values[0].aperture,
        long_axis_px=PositiveInterval(
            min(item.long_axis_px.minimum for item in values),
            max(item.long_axis_px.maximum for item in values),
        ),
        short_axis_px=PositiveInterval(
            min(item.short_axis_px.minimum for item in values),
            max(item.short_axis_px.maximum for item in values),
        ),
    )


def _union_interval(values: tuple[FiniteInterval, ...]) -> FiniteInterval:
    return FiniteInterval(
        min(item.minimum for item in values),
        max(item.maximum for item in values),
    )


def _expected_grid_translation(
    sequence_length: int,
    aperture_width_px: PositiveInterval,
    gutter_px: FiniteInterval,
    long_extent_px: int,
) -> float:
    width_center = (
        aperture_width_px.minimum + aperture_width_px.maximum
    ) / 2.0
    total = (
        sequence_length * width_center
        + (sequence_length - 1) * gutter_px.center
    )
    return max(0.0, (long_extent_px - total) / 2.0)


def _predeclared_support_span(
    anchor_domain: SequenceAnchorDiscoveryDomain,
    start_interval: FiniteInterval,
    end_interval: FiniteInterval,
) -> FiniteInterval:
    tiles = tuple(
        tile
        for tile in anchor_domain.tiles
        if (
            tile.core_px.maximum >= start_interval.minimum
            and tile.core_px.minimum <= end_interval.maximum
        )
    )
    if not tiles:
        raise ValueError("resolved frame escaped pre-registered anchor tiles")
    return FiniteInterval(
        min(item.core_px.minimum for item in tiles),
        max(item.core_px.maximum for item in tiles),
    )


def _point_in_polygon(
    polygon: tuple[tuple[float, float], ...],
    point: tuple[float, float],
) -> bool:
    signs = tuple(
        (right[0] - left[0]) * (point[1] - left[1])
        - (right[1] - left[1]) * (point[0] - left[0])
        for left, right in zip(
            polygon,
            polygon[1:] + polygon[:1],
            strict=True,
        )
    )
    return all(value >= -1.0e-6 for value in signs) or all(
        value <= 1.0e-6 for value in signs
    )


def _component_source_center(
    component: SourceContentComponent,
    layout: str,
) -> tuple[float, float]:
    work_x = (component.footprint.left + component.footprint.right) / 2.0
    work_y = (component.footprint.top + component.footprint.bottom) / 2.0
    return (
        (work_x, work_y)
        if layout == "horizontal"
        else (work_y, work_x)
    )


def _content_ids_for_geometry(
    geometry,
    lane: SourceLaneEvidence,
    layout: str,
    *,
    minimum_component_cells: int,
    maximum_long_span_px: float,
    maximum_short_span_px: float,
) -> tuple[str, ...]:
    components = tuple(
        component
        for component in lane.content.components
        if (
            component.positive_cells >= minimum_component_cells
            and component.footprint.width <= maximum_long_span_px
            and component.footprint.height <= maximum_short_span_px
        )
    )
    if not components:
        return ()
    centers = tuple(
        _component_source_center(component, layout)
        for component in components
    )
    x = np.asarray([point[0] for point in centers], dtype=np.float64)
    y = np.asarray([point[1] for point in centers], dtype=np.float64)
    polygon = geometry.source_polygon
    cross = np.vstack(
        tuple(
            (right[0] - left[0]) * (y - left[1])
            - (right[1] - left[1]) * (x - left[0])
            for left, right in zip(
                polygon,
                polygon[1:] + polygon[:1],
                strict=True,
            )
        )
    )
    inside = np.all(cross >= -1.0e-6, axis=0) | np.all(
        cross <= 1.0e-6,
        axis=0,
    )
    return tuple(
        component.component_id
        for component, keep in zip(components, inside, strict=True)
        if bool(keep)
    )


def _adjacency_kind(interval: FiniteInterval) -> AdjacencyKind:
    if interval.maximum < 0.0:
        return AdjacencyKind.OVERLAP
    if interval.minimum <= 0.0 <= interval.maximum:
        return AdjacencyKind.CONTACT
    return AdjacencyKind.EDGE_PAIR


def _model_state(
    lane_id: str,
    lane_ordinal: int,
    aperture_label: str,
) -> FrameGeometryState:
    return FrameGeometryState(
        state_id=f"model-state:{lane_id}:{lane_ordinal}:{aperture_label}",
        lane_id=lane_id,
        lane_ordinal=lane_ordinal,
        photo_geometry=None,
        aperture_label=aperture_label,
        rotation_class_id="model_only_no_rotation_evidence",
        ownership="unassigned",
        interaction_before=None,
        interaction_after=None,
        model_only=True,
        physical_residual_px=0.0,
        measurement_uncertainty_px=0.0,
    )


def _state_id(*parts: object) -> str:
    payload = "\x1f".join(str(item) for item in parts).encode("utf-8")
    return "frame-state:" + sha256(payload).hexdigest()[:24]


def _box_contains(outer: Box, inner: Box) -> bool:
    return (
        outer.left <= inner.left
        and outer.top <= inner.top
        and outer.right >= inner.right
        and outer.bottom >= inner.bottom
    )


def _protection_absorbing_state_index(
    states: tuple[FrameGeometryState, ...],
    lane: SourceLaneEvidence,
    *,
    layout: str,
    configuration: DetectionConfiguration,
) -> int | None:
    photo_states = tuple(
        (index, state)
        for index, state in enumerate(states)
        if state.photo_geometry is not None
    )
    if len(photo_states) != len(states) or not photo_states:
        return 0 if len(states) == 1 else None
    envelopes = tuple(
        (
            index,
            safe_crop_envelope_from_photo_geometry(
                state.photo_geometry,
                lane,
                layout=layout,
                protection=output_protection_spec(
                    configuration.physical_spec.format_id
                ),
            ),
        )
        for index, state in photo_states
    )
    for index, candidate in envelopes:
        if all(
            _box_contains(
                candidate.source_protected_box,
                alternative.source_safe_box,
            )
            for _other_index, alternative in envelopes
        ):
            return index
    return None


def _selected_label_hypotheses(
    reconstructions: tuple[LabelSequenceReconstruction, ...],
) -> tuple[tuple[LabelSequenceReconstruction, LongAxisSequenceHypothesis], ...]:
    def geometry_equivalent(
        left: LongAxisSequenceHypothesis,
        right: LongAxisSequenceHypothesis,
        *,
        equivalence_px: float,
    ) -> bool:
        return all(
            abs(left_interval.center - right_interval.center)
            <= equivalence_px
            for left_interval, right_interval in zip(
                left.position_intervals_px,
                right.position_intervals_px,
                strict=True,
            )
        )

    def quality(
        item: LongAxisSequenceHypothesis,
    ) -> tuple[int, int, int, int, int, float, float, str]:
        return (
            item.observed_aperture_pair_count,
            item.observed_frame_count,
            item.observed_role_count,
            int(item.known_content_contained),
            int(item.lane_geometry_contained),
            -item.scalar_residual_px,
            -item.physical_uncertainty_px,
            item.hypothesis_id,
        )

    retained: list[
        tuple[LabelSequenceReconstruction, LongAxisSequenceHypothesis]
    ] = []
    for reconstruction in reconstructions:
        equivalence_px = max(
            1.0,
            0.05
            * reconstruction
            .shared_scale_constraint_px_per_mm.maximum,
        )
        deduplicated: list[LongAxisSequenceHypothesis] = []
        for hypothesis in sorted(
            reconstruction.hypotheses,
            key=quality,
            reverse=True,
        ):
            equivalent_index = next(
                (
                    index
                    for index, existing in enumerate(deduplicated)
                    if geometry_equivalent(
                        existing,
                        hypothesis,
                        equivalence_px=equivalence_px,
                    )
                ),
                None,
            )
            if equivalent_index is None:
                deduplicated.append(hypothesis)
            elif quality(hypothesis) > quality(
                deduplicated[equivalent_index]
            ):
                deduplicated[equivalent_index] = hypothesis
        retained.extend(
            (reconstruction, hypothesis)
            for hypothesis in deduplicated
        )
    candidates = tuple(retained)
    if not candidates:
        return ()
    return tuple(
        sorted(
            candidates,
            key=lambda item: (
                -item[1].role_oriented_observed_role_count,
                -(
                    item[1].background_side_support_fraction
                    * item[1].role_oriented_observed_role_count
                ),
                -(
                    item[1].role_oriented_background_support_fraction
                    * item[1].role_oriented_observed_role_count
                ),
                -item[1].observed_role_count,
                item[1].scalar_residual_px,
                item[1].physical_uncertainty_px,
                item[0].constraint.aperture_label,
                item[1].hypothesis_id,
            ),
        )
    )


def _rotation_coherent_short_candidates(
    candidate_rows: tuple[tuple[FrameShortAxisCandidate, ...], ...],
) -> tuple[
    tuple[tuple[FrameShortAxisCandidate, ...], ...],
    float,
]:
    """Retain rows whose selected frame states share an exact angle interval."""

    supported = FiniteInterval(-2.0, 2.0)
    filtered = tuple(
        tuple(
            candidate
            for candidate in row
            if (
                candidate.angle_interval_degrees.minimum
                <= supported.maximum
                and supported.minimum
                <= candidate.angle_interval_degrees.maximum
            )
        )
        for row in candidate_rows
    )
    if not filtered or any(not row for row in filtered):
        return filtered, 0.0
    event_points = {
        0.0,
        supported.minimum,
        supported.maximum,
    }
    for row in filtered:
        for candidate in row:
            interval = candidate.angle_interval_degrees
            event_points.update(
                (
                    max(supported.minimum, interval.minimum),
                    min(supported.maximum, interval.maximum),
                    min(
                        supported.maximum,
                        max(supported.minimum, interval.center),
                    ),
                )
            )
    feasible: list[
        tuple[
            tuple[int, ...],
            float,
            tuple[FrameShortAxisCandidate, ...],
        ]
    ] = []
    for point in sorted(event_points):
        selected: list[FrameShortAxisCandidate] = []
        indices: list[int] = []
        for row in filtered:
            match = next(
                (
                    (index, candidate)
                    for index, candidate in enumerate(row)
                    if candidate.angle_interval_degrees.contains(
                        point,
                        epsilon=1.0e-12,
                    )
                ),
                None,
            )
            if match is None:
                break
            index, candidate = match
            indices.append(index)
            selected.append(candidate)
        if len(selected) == len(filtered):
            feasible.append((tuple(indices), point, tuple(selected)))
    if not feasible:
        return tuple(() for _row in filtered), math.inf
    _indices, canonical_angle, selected = min(
        feasible,
        key=lambda item: (
            item[0],
            abs(item[1]),
            item[1],
        ),
    )
    selected_centers = tuple(
        candidate.angle_interval_degrees.center
        for candidate in selected
    )
    if not selected_centers:
        return filtered, 0.0
    median = float(np.median(np.asarray(selected_centers)))
    coherent = tuple(
        tuple(
            candidate
            for candidate in row
            if candidate.angle_interval_degrees.contains(
                canonical_angle,
                epsilon=1.0e-12,
            )
        )
        for row in filtered
    )
    return (
        coherent,
        sum(abs(value - median) for value in selected_centers),
    )


def _material_content_components(
    lane: SourceLaneEvidence,
    *,
    layout: str,
    aperture_long_extent_px: float,
    aperture_short_extent_px: float,
) -> tuple[SourceContentComponent, ...]:
    minimum_component_cells = max(
        64,
        int(
            math.ceil(
                0.002
                * aperture_long_extent_px
                * aperture_short_extent_px
            )
        ),
    )
    return tuple(
        component
        for component in lane.content.components
        if (
            component.positive_cells >= minimum_component_cells
            # Source-content components live in canonical work coordinates:
            # work-x is always the strip long axis and work-y is always the
            # short axis, including a vertical source TIFF.
            and component.footprint.width
            <= aperture_long_extent_px * 1.25
            and component.footprint.height
            <= aperture_short_extent_px * 1.25
        )
    )


def _long_content_assignment_score(
    hypothesis: LongAxisSequenceHypothesis,
    components: tuple[SourceContentComponent, ...],
    *,
    layout: str,
    safe_padding_px: float,
) -> _LongContentAssignmentScore:
    """Assess material content without creating photo-edge evidence."""

    intervals = tuple(
        FiniteInterval(start.minimum, end.maximum)
        for start, end in zip(
            hypothesis.position_intervals_px[::2],
            hypothesis.position_intervals_px[1::2],
            strict=True,
        )
    )
    assigned_component_weight = 0.0
    ambiguous_component_weight = 0.0
    safely_contained_weight = 0.0
    occupied_indices: set[int] = set()
    for component in components:
        long_minimum = component.footprint.left
        long_maximum = component.footprint.right
        center = (long_minimum + long_maximum) / 2.0
        owner_indices = tuple(
            index
            for index, interval in enumerate(intervals)
            if interval.contains(center, epsilon=0.5)
        )
        if len(owner_indices) == 1:
            assigned_component_weight += component.positive_cells
            occupied_indices.add(owner_indices[0])
        elif (
            len(owner_indices) == 2
            and owner_indices[1] == owner_indices[0] + 1
        ):
            # Adjacent contact/overlap is intentionally duplicated into both
            # safe outputs.  A component inside that shared interval has
            # bounded ownership and is not an ordinal ambiguity.
            assigned_component_weight += component.positive_cells
            occupied_indices.update(owner_indices)
        elif len(owner_indices) > 1:
            ambiguous_component_weight += component.positive_cells
        if owner_indices and any(
            intervals[index].minimum - safe_padding_px
            <= long_minimum
            and intervals[index].maximum + safe_padding_px
            >= long_maximum
            for index in owner_indices
        ):
            safely_contained_weight += component.positive_cells
    total_component_weight = float(
        sum(component.positive_cells for component in components)
    )
    assignment_fraction = (
        1.0
        if total_component_weight <= 0.0
        else assigned_component_weight / total_component_weight
    )
    ambiguous_fraction = (
        0.0
        if total_component_weight <= 0.0
        else ambiguous_component_weight / total_component_weight
    )
    safe_containment_fraction = (
        1.0
        if total_component_weight <= 0.0
        else safely_contained_weight / total_component_weight
    )
    assigned_safe_containment_fraction = (
        1.0
        if assigned_component_weight <= 0.0
        else safely_contained_weight / assigned_component_weight
    )
    assigned_content_containment_supported = (
        assignment_fraction < MATERIAL_ASSIGNMENT_MINIMUM_FRACTION
        or assigned_safe_containment_fraction
        >= ASSIGNED_SAFE_CONTAINMENT_MINIMUM_FRACTION
    )
    return _LongContentAssignmentScore(
        complete_assignment=float(assignment_fraction >= 0.999),
        stable_ownership=float(ambiguous_component_weight == 0.0),
        assignment_fraction=assignment_fraction - ambiguous_fraction,
        assigned_content_containment_supported=float(
            assigned_content_containment_supported
        ),
        assigned_safe_containment_fraction=(
            assigned_safe_containment_fraction
        ),
        safe_containment_fraction=safe_containment_fraction,
        occupied_frame_count=len(occupied_indices),
    )


def _material_content_ordinals(
    hypothesis: LongAxisSequenceHypothesis,
    components: tuple[SourceContentComponent, ...],
) -> frozenset[int]:
    intervals = tuple(
        FiniteInterval(start.minimum, end.maximum)
        for start, end in zip(
            hypothesis.position_intervals_px[::2],
            hypothesis.position_intervals_px[1::2],
            strict=True,
        )
    )
    return frozenset(
        index
        for component in components
        for index, interval in enumerate(intervals, 1)
        if interval.contains(
            (
                component.footprint.left + component.footprint.right
            )
            / 2.0,
            epsilon=0.5,
        )
    )


def _grid_translation(
    hypothesis: LongAxisSequenceHypothesis | None,
    expected_translation_px: float,
    *,
    profile_bounded: bool,
    no_known_content: bool,
) -> GridSlotTranslationAssessment:
    if profile_bounded:
        return GridSlotTranslationAssessment(
            outcome=GridSlotTranslationOutcome.SCAN_CANVAS_PROFILE_BOUNDED,
            interval_px=FiniteInterval.exact(expected_translation_px),
            protected_footprint_equivalence_class_id=None,
            competing_class_ids=(),
        )
    if hypothesis is not None:
        return GridSlotTranslationAssessment(
            outcome=GridSlotTranslationOutcome.OBSERVED_GRID_ANCHOR,
            interval_px=hypothesis.translation_interval_px,
            protected_footprint_equivalence_class_id=None,
            competing_class_ids=(),
        )
    if no_known_content:
        return GridSlotTranslationAssessment(
            outcome=GridSlotTranslationOutcome.SCAN_CANVAS_PROFILE_BOUNDED,
            interval_px=FiniteInterval.exact(expected_translation_px),
            protected_footprint_equivalence_class_id=None,
            competing_class_ids=(),
        )
    return GridSlotTranslationAssessment(
        outcome=GridSlotTranslationOutcome.UNRESOLVED,
        interval_px=None,
        protected_footprint_equivalence_class_id=None,
        competing_class_ids=("grid_slot_translation_unresolved",),
    )


def _empty_photo_translation() -> PhotoSequenceTranslationAssessment:
    return PhotoSequenceTranslationAssessment(
        outcome=PhotoSequenceTranslationOutcome.UNRESOLVED,
        interval_px=None,
        observation_ids=(),
        competing_class_ids=("sequence_translation_unresolved",),
    )


def _reconstruct_lane(
    field: PhotoBoundaryMeasurementField,
    lane: SourceLaneEvidence,
    *,
    layout: str,
    sequence_length: int,
    configuration: DetectionConfiguration,
) -> LanePhotoGeometryReconstruction:
    long_axis, short_axis = _source_axes(layout)
    lane_box = source_lane_box(lane, layout)
    lane_long_interval = _axis_interval(lane_box, long_axis)
    lane_short_interval = _axis_interval(lane_box, short_axis)
    constraints = frame_sequence_physical_constraints(
        configuration.physical_spec.format_id,
        configuration.physical_spec.aperture_components,
    )
    aperture_pixels_by_label = tuple(
        (
            constraint,
            frame_physical_pixel_intervals(
                constraint.aperture,
                configuration.physical_spec.aperture_tolerance,
                lane.axis_scale_intervals.long_axis_px_per_mm,
                lane.axis_scale_intervals.short_axis_px_per_mm,
            ),
        )
        for constraint in constraints
    )
    combined_pixels = _union_aperture_pixels(
        tuple(item[1] for item in aperture_pixels_by_label)
    )
    gutter_by_label = tuple(
        (
            constraint,
            constraint.gutter_px(
                lane.axis_scale_intervals.long_axis_px_per_mm
            ),
        )
        for constraint in constraints
    )
    combined_gutter = _union_interval(
        tuple(item[1] for item in gutter_by_label)
    )
    top_corridor, bottom_corridor = build_top_bottom_search_corridors(
        lane,
        layout=layout,
        aperture_pixels=combined_pixels,
    )
    combined_expected = _expected_grid_translation(
        sequence_length,
        combined_pixels.long_axis_px,
        combined_gutter,
        _axis_extent(lane_box, long_axis),
    )
    long_extent = _axis_extent(lane_box, long_axis)
    coarse_content_support = positive_content_support_interval(
        lane,
        (
            combined_pixels.long_axis_px.minimum
            + combined_pixels.long_axis_px.maximum
        )
        / 2.0,
    )
    extent_proposals = [
        PhotoSequenceExtentProposal(
            proposal_id=(
                "sequence-extent:grid:"
                + sha256(
                    (
                        f"{lane.domain.lane_id}:"
                        f"{combined_expected:.9f}"
                    ).encode("utf-8")
                ).hexdigest()[:24]
            ),
            lane_id=lane.domain.lane_id,
            source="grid_search_order",
            long_axis_interval_px=FiniteInterval(
                combined_expected,
                max(
                    combined_expected,
                    float(long_extent) - combined_expected,
                ),
            ),
        )
    ]
    if coarse_content_support is not None:
        extent_proposals.append(
            PhotoSequenceExtentProposal(
                proposal_id=(
                    "sequence-extent:content:"
                    + sha256(
                        (
                            f"{lane.domain.lane_id}:"
                            f"{coarse_content_support.minimum:.9f}:"
                            f"{coarse_content_support.maximum:.9f}"
                        ).encode("utf-8")
                    ).hexdigest()[:24]
                ),
                lane_id=lane.domain.lane_id,
                source="outer_content",
                long_axis_interval_px=coarse_content_support,
            )
        )
    anchor_domain = build_sequence_anchor_discovery_domain(
        lane,
        layout=layout,
        authoritative_sequence_length=sequence_length,
        aperture_pixels=combined_pixels,
        typed_gutter_interval_px=combined_gutter,
        grid_nominal_translation_px=combined_expected,
        outer_proposal_centers_px=tuple(
            proposal.long_axis_interval_px.center
            for proposal in extent_proposals
        ),
    )
    queries = registered_lane_measurement_queries(
        lane,
        layout=layout,
        aperture_pixels=combined_pixels,
        top_corridor=top_corridor,
        bottom_corridor=bottom_corridor,
        anchor_domain=anchor_domain,
    )
    measurement_sets = measure_registered_queries(field, queries)
    unavailable_measurement = any(
        item.state != EvidenceState.SUPPORTED
        for item in measurement_sets
    )
    anchor_sets = measurement_sets[2:]
    anchor_trace_positions = (
        ()
        if not anchor_sets
        else anchor_sets[0].query.trace_positions_px
    )
    reference_short = lane_short_interval.center
    long_support_interval = (
        lane_short_interval
        if not anchor_trace_positions
        else FiniteInterval(
            float(min(anchor_trace_positions)),
            float(max(anchor_trace_positions)),
        )
    )
    shared_raw_long = fit_boundary_line_families(
        anchor_sets,
        role=BoundaryRole.LONG_BOUNDARY,
        source_axis_long=long_axis,
        support_interval_px=long_support_interval,
        boundary_axis_scale_px_per_mm=(
            lane.axis_scale_intervals.long_axis_px_per_mm
        ),
        trace_axis_scale_px_per_mm=(
            lane.axis_scale_intervals.short_axis_px_per_mm
        ),
    )
    shared_physical_long = eliminate_transition_zone_dominated_lines(
        shared_raw_long,
        boundary_axis=long_axis,
        reference_trace_px=reference_short,
        boundary_axis_scale_px_per_mm=(
            lane.axis_scale_intervals.long_axis_px_per_mm
        ),
    )
    label_reconstructions: list[LabelSequenceReconstruction] = []
    for constraint, aperture_pixels in aperture_pixels_by_label:
        gutter_px = next(
            value
            for item, value in gutter_by_label
            if item is constraint
        )
        raw_long = shared_raw_long
        physical_long = shared_physical_long
        width_center = (
            aperture_pixels.long_axis_px.minimum
            + aperture_pixels.long_axis_px.maximum
        ) / 2.0
        content_support = positive_content_support_interval(
            lane,
            width_center,
        )
        expected = _expected_grid_translation(
            sequence_length,
            aperture_pixels.long_axis_px,
            gutter_px,
            _axis_extent(lane_box, long_axis),
        )
        expected_for_selection = (
            expected
            if configuration.count_request.mode
            in {FrameCountMode.FIXED_FULL, FrameCountMode.AUTO}
            else None
        )
        shared_scale_constraint = (
            lane.axis_scale_intervals.long_axis_px_per_mm
        )
        full_search_radius = (
            3.0
            * lane.axis_scale_intervals.long_axis_px_per_mm.maximum
            + 0.5
            * lane_short_interval.width
            * math.tan(math.radians(4.0))
        )
        outer_assignments = outer_observed_assignments(
            physical_long,
            boundary_axis=long_axis,
            reference_trace_px=reference_short,
            authoritative_sequence_length=sequence_length,
            strip_mode=configuration.strip_mode,
            known_content_interval_px=content_support,
            expected_grid_translation_px=expected_for_selection,
            full_search_radius_px=full_search_radius,
            lane_long_extent_px=_axis_extent(lane_box, long_axis),
        )
        complete_hypotheses = (
            ()
            if unavailable_measurement
            else solve_long_axis_sequence_hypotheses(
                physical_long,
                authoritative_sequence_length=sequence_length,
                aperture_width_px=aperture_pixels.long_axis_px,
                aperture_width_mm=PositiveInterval(
                    constraint.aperture.long_axis_mm
                    - configuration.physical_spec.aperture_tolerance
                    .long_axis_tolerance_mm,
                    constraint.aperture.long_axis_mm
                    + configuration.physical_spec.aperture_tolerance
                    .long_axis_tolerance_mm,
                ),
                shared_scale_px_per_mm=(
                    shared_scale_constraint
                ),
                gutter_px=gutter_px,
                boundary_axis=long_axis,
                reference_trace_px=reference_short,
                lane_long_extent_px=_axis_extent(lane_box, long_axis),
                expected_grid_translation_px=expected_for_selection,
                known_content_interval_px=content_support,
                preferred_outer_assignments=outer_assignments,
                allow_blank_slots=False,
            )
        )
        capacity_fully_observed = any(
            hypothesis.observed_frame_count == sequence_length
            and hypothesis.observed_aperture_pair_count
            == sequence_length
            for hypothesis in complete_hypotheses
        )
        hypotheses = (
            solve_long_axis_sequence_hypotheses(
                physical_long,
                authoritative_sequence_length=sequence_length,
                aperture_width_px=aperture_pixels.long_axis_px,
                aperture_width_mm=PositiveInterval(
                    constraint.aperture.long_axis_mm
                    - configuration.physical_spec.aperture_tolerance
                    .long_axis_tolerance_mm,
                    constraint.aperture.long_axis_mm
                    + configuration.physical_spec.aperture_tolerance
                    .long_axis_tolerance_mm,
                ),
                shared_scale_px_per_mm=shared_scale_constraint,
                gutter_px=gutter_px,
                boundary_axis=long_axis,
                reference_trace_px=reference_short,
                lane_long_extent_px=_axis_extent(
                    lane_box,
                    long_axis,
                ),
                expected_grid_translation_px=(
                    expected_for_selection
                ),
                known_content_interval_px=content_support,
                preferred_outer_assignments=outer_assignments,
                allow_blank_slots=True,
            )
            if (
                not unavailable_measurement
                and configuration.count_request.mode
                == FrameCountMode.AUTO
                and not capacity_fully_observed
            )
            else complete_hypotheses
        )
        label_reconstructions.append(
            LabelSequenceReconstruction(
                constraint=constraint,
                aperture_pixels=aperture_pixels,
                gutter_px=gutter_px,
                raw_long_observations=raw_long,
                physical_long_observations=physical_long,
                hypotheses=hypotheses,
                content_support_interval_px=content_support,
                expected_grid_translation_px=expected,
                outer_observed_assignments=outer_assignments,
                shared_scale_constraint_px_per_mm=(
                    shared_scale_constraint
                ),
            )
        )

    long_axis_choices = _selected_label_hypotheses(
        tuple(label_reconstructions)
    )
    protection = output_protection_spec(
        configuration.physical_spec.format_id
    )
    content_geometry_index = content_component_geometry_index(lane)
    short_fit_cache: dict[
        tuple[float, float],
        tuple[
            tuple[PhotoBoundaryObservation, ...],
            tuple[PhotoBoundaryObservation, ...],
        ],
    ] = {}
    content_short_cache: dict[
        tuple[float, float, float, int],
        FiniteInterval | None,
    ] = {}
    short_frame_cache: dict[
        tuple[str, str, int],
        tuple[
            FiniteInterval,
            float,
            tuple[PhotoBoundaryObservation, ...],
            tuple[PhotoBoundaryObservation, ...],
            FiniteInterval | None,
            tuple[FrameShortAxisCandidate, ...],
        ],
    ] = {}

    def short_axis_evidence(
        reconstruction: LabelSequenceReconstruction,
        hypothesis: LongAxisSequenceHypothesis,
        ordinal: int,
    ) -> tuple[
        FiniteInterval,
        float,
        tuple[PhotoBoundaryObservation, ...],
        tuple[PhotoBoundaryObservation, ...],
        FiniteInterval | None,
        tuple[FrameShortAxisCandidate, ...],
    ]:
        cache_key = (
            reconstruction.constraint.aperture_label,
            hypothesis.hypothesis_id,
            ordinal,
        )
        existing = short_frame_cache.get(cache_key)
        if existing is not None:
            return existing
        start_interval = hypothesis.position_intervals_px[
            (ordinal - 1) * 2
        ]
        end_interval = hypothesis.position_intervals_px[
            (ordinal - 1) * 2 + 1
        ]
        support_span = _predeclared_support_span(
            anchor_domain,
            start_interval,
            end_interval,
        )
        frame_reference_long = (
            start_interval.center + end_interval.center
        ) / 2.0
        fit_key = (
            round(support_span.minimum, 6),
            round(support_span.maximum, 6),
        )
        raw_pair = short_fit_cache.get(fit_key)
        if raw_pair is None:
            raw_pair = (
                fit_boundary_line_families(
                    (measurement_sets[0],),
                    role=BoundaryRole.TOP,
                    source_axis_long=long_axis,
                    support_interval_px=support_span,
                    boundary_axis_scale_px_per_mm=(
                        lane.axis_scale_intervals.short_axis_px_per_mm
                    ),
                    trace_axis_scale_px_per_mm=(
                        lane.axis_scale_intervals.long_axis_px_per_mm
                    ),
                ),
                fit_boundary_line_families(
                    (measurement_sets[1],),
                    role=BoundaryRole.BOTTOM,
                    source_axis_long=long_axis,
                    support_interval_px=support_span,
                    boundary_axis_scale_px_per_mm=(
                        lane.axis_scale_intervals.short_axis_px_per_mm
                    ),
                    trace_axis_scale_px_per_mm=(
                        lane.axis_scale_intervals.long_axis_px_per_mm
                    ),
                ),
            )
            short_fit_cache[fit_key] = raw_pair
        top_observations = eliminate_transition_zone_dominated_lines(
            raw_pair[0],
            boundary_axis=short_axis,
            reference_trace_px=frame_reference_long,
            boundary_axis_scale_px_per_mm=(
                lane.axis_scale_intervals.short_axis_px_per_mm
            ),
        )
        bottom_observations = eliminate_transition_zone_dominated_lines(
            raw_pair[1],
            boundary_axis=short_axis,
            reference_trace_px=frame_reference_long,
            boundary_axis_scale_px_per_mm=(
                lane.axis_scale_intervals.short_axis_px_per_mm
            ),
        )
        content_interval = FiniteInterval(
            start_interval.minimum,
            end_interval.maximum,
        )
        expected_short_extent = (
            reconstruction.aperture_pixels.short_axis_px.maximum
        )
        smoothing = max(
            1,
            int(
                round(
                    0.25
                    * lane.axis_scale_intervals
                    .short_axis_px_per_mm.maximum
                )
            ),
        )
        content_cache_key = (
            round(content_interval.minimum, 6),
            round(content_interval.maximum, 6),
            round(expected_short_extent, 6),
            smoothing,
        )
        if content_cache_key in content_short_cache:
            content_short = content_short_cache[content_cache_key]
        else:
            content_short = known_content_short_interval(
                lane,
                component_index=content_geometry_index,
                long_axis_interval_px=content_interval,
                expected_short_extent_px=expected_short_extent,
                smoothing_px=smoothing,
            )
            content_short_cache[content_cache_key] = content_short
        candidates = select_frame_short_axis_candidates(
            top_observations,
            bottom_observations,
            short_axis=short_axis,
            reference_long_px=frame_reference_long,
            height_px=reconstruction.aperture_pixels.short_axis_px,
            support_projection_px=support_span,
            lane_short_interval_px=lane_short_interval,
            known_content_interval_px=content_short,
            interpolation_allowance_px=1.0,
            protection_px=(
                protection.short_axis_mm_per_side
                * lane.axis_scale_intervals
                .short_axis_px_per_mm.maximum
            ),
            scanner_border_exclusion_px=(
                0.5
                * lane.axis_scale_intervals
                .short_axis_px_per_mm.maximum
            ),
        )
        result = (
            support_span,
            frame_reference_long,
            top_observations,
            bottom_observations,
            content_short,
            candidates,
        )
        short_frame_cache[cache_key] = result
        return result

    def complete_sequence_candidate(
        reconstruction: LabelSequenceReconstruction,
        hypothesis: LongAxisSequenceHypothesis,
        coherent_rows: tuple[
            tuple[FrameShortAxisCandidate, ...], ...
        ],
        rank: tuple[float, ...],
    ) -> UndominatedFrameSequenceCandidate | None:
        photo_count = len(hypothesis.position_intervals_px) // 2
        if (
            photo_count <= 0
            or len(coherent_rows) != photo_count
            or any(not row for row in coherent_rows)
        ):
            return None
        states: list[FrameGeometryState] = []
        outputs: list[SafeCropEnvelope] = []
        minimum_component_cells = max(
            64,
            int(
                math.ceil(
                    0.0001
                    * (
                        reconstruction.aperture_pixels
                        .long_axis_px.minimum
                        + reconstruction.aperture_pixels
                        .long_axis_px.maximum
                    )
                    / 2.0
                    * (
                        reconstruction.aperture_pixels
                        .short_axis_px.minimum
                        + reconstruction.aperture_pixels
                        .short_axis_px.maximum
                    )
                    / 2.0
                )
            ),
        )
        for ordinal, candidates in enumerate(coherent_rows, 1):
            short_candidate = candidates[0]
            start, end = frame_long_boundaries(
                hypothesis,
                lane_ordinal=ordinal,
                boundary_axis=long_axis,
                reference_trace_px=reference_short,
                support_projection_px=lane_short_interval,
            )
            provisional = build_frame_photo_geometry(
                lane_id=lane.domain.lane_id,
                lane_ordinal=ordinal,
                start=start,
                end=end,
                short_candidate=short_candidate,
                content_component_ids=(),
                ownership="unassigned",
            )
            content_ids = _content_ids_for_geometry(
                provisional,
                lane,
                layout,
                minimum_component_cells=minimum_component_cells,
                maximum_long_span_px=(
                    reconstruction.aperture_pixels
                    .long_axis_px.maximum
                    * 1.25
                ),
                maximum_short_span_px=(
                    reconstruction.aperture_pixels
                    .short_axis_px.maximum
                    * 1.25
                ),
            )
            geometry = replace(
                provisional,
                content_component_ids=content_ids,
                ownership=(
                    "assigned_content"
                    if content_ids
                    else "observed_empty"
                ),
            )
            start_interval = hypothesis.position_intervals_px[
                (ordinal - 1) * 2
            ]
            end_interval = hypothesis.position_intervals_px[
                (ordinal - 1) * 2 + 1
            ]
            previous_gap = (
                None
                if ordinal == 1
                else FiniteInterval(
                    start_interval.minimum
                    - hypothesis.position_intervals_px[
                        (ordinal - 2) * 2 + 1
                    ].maximum,
                    start_interval.maximum
                    - hypothesis.position_intervals_px[
                        (ordinal - 2) * 2 + 1
                    ].minimum,
                )
            )
            next_gap = (
                None
                if ordinal == photo_count
                else FiniteInterval(
                    hypothesis.position_intervals_px[
                        ordinal * 2
                    ].minimum
                    - end_interval.maximum,
                    hypothesis.position_intervals_px[
                        ordinal * 2
                    ].maximum
                    - end_interval.minimum,
                )
            )
            state = FrameGeometryState(
                state_id=_state_id(
                    "candidate",
                    hypothesis.hypothesis_id,
                    geometry.geometry_id,
                ),
                lane_id=lane.domain.lane_id,
                lane_ordinal=ordinal,
                photo_geometry=geometry,
                aperture_label=(
                    reconstruction.constraint.aperture_label
                ),
                rotation_class_id="observed_lane_rotation",
                ownership=geometry.ownership,
                interaction_before=(
                    None
                    if previous_gap is None
                    else _adjacency_kind(previous_gap)
                ),
                interaction_after=(
                    None
                    if next_gap is None
                    else _adjacency_kind(next_gap)
                ),
                model_only=False,
                physical_residual_px=(
                    short_candidate.residual_px
                    + hypothesis.scalar_residual_px
                ),
                measurement_uncertainty_px=(
                    short_candidate.uncertainty_px
                    + start.outward_uncertainty_px
                    + end.outward_uncertainty_px
                ),
            )
            states.append(state)
            outputs.append(
                safe_crop_envelope_from_photo_geometry(
                    geometry,
                    lane,
                    layout=layout,
                    protection=protection,
                )
            )
        equivalence_payload = "\x1f".join(
            f"{box.left:.6f},{box.top:.6f},"
            f"{box.right:.6f},{box.bottom:.6f}"
            for box in (
                output.source_protected_box for output in outputs
            )
        )
        equivalence_id = (
            "sequence-output-class:"
            + sha256(equivalence_payload.encode("utf-8")).hexdigest()[:24]
        )
        candidate_id = (
            "sequence-candidate:"
            + sha256(
                (
                    hypothesis.hypothesis_id
                    + "\x1f"
                    + equivalence_id
                ).encode("utf-8")
            ).hexdigest()[:24]
        )
        return UndominatedFrameSequenceCandidate(
            candidate_id=candidate_id,
            lane_id=lane.domain.lane_id,
            aperture_label=(
                reconstruction.constraint.aperture_label
            ),
            hypothesis_id=hypothesis.hypothesis_id,
            photo_states=tuple(states),
            output_geometries=tuple(outputs),
            output_equivalence_class_id=equivalence_id,
            selection_rank=rank,
        )

    assessed_choices: list[
        tuple[
            tuple[float, ...],
            LabelSequenceReconstruction,
            LongAxisSequenceHypothesis,
        ]
    ] = []
    coherent_rows_by_choice: dict[
        tuple[str, str],
        tuple[tuple[FrameShortAxisCandidate, ...], ...],
    ] = {}
    material_content_by_label: dict[
        str,
        tuple[SourceContentComponent, ...],
    ] = {}
    content_score_by_choice: dict[
        tuple[str, str],
        _LongContentAssignmentScore,
    ] = {}
    best_content_class = (0.0, 0.0, 0.0)
    for reconstruction, hypothesis in long_axis_choices:
        label = reconstruction.constraint.aperture_label
        material_content = material_content_by_label.get(label)
        if material_content is None:
            material_content = _material_content_components(
                lane,
                layout=layout,
                aperture_long_extent_px=(
                    reconstruction.aperture_pixels.long_axis_px.maximum
                ),
                aperture_short_extent_px=(
                    reconstruction.aperture_pixels.short_axis_px.maximum
                ),
            )
            material_content_by_label[label] = material_content
        content_score_by_choice[(label, hypothesis.hypothesis_id)] = (
            _long_content_assignment_score(
                hypothesis,
                material_content,
                layout=layout,
                safe_padding_px=(
                    PHOTO_BOUNDARY_MEASUREMENT_SPEC
                    .interpolation_allowance_source_px
                    + protection.long_axis_mm_per_side
                    * lane.axis_scale_intervals
                    .long_axis_px_per_mm.maximum
                ),
            )
        )
    if long_axis_choices:
        best_content_class = max(
            (
                score.assigned_content_containment_supported,
                score.complete_assignment,
                score.stable_ownership,
            )
            for score in content_score_by_choice.values()
        )
        long_axis_choices = tuple(
            (reconstruction, hypothesis)
            for reconstruction, hypothesis in long_axis_choices
            if (
                lambda score: (
                    score.assigned_content_containment_supported,
                    score.complete_assignment,
                    score.stable_ownership,
                )
            )(
                content_score_by_choice[
                    (
                        reconstruction.constraint.aperture_label,
                        hypothesis.hypothesis_id,
                    )
                ]
            )
            == best_content_class
        )
    for reconstruction, hypothesis in long_axis_choices:
        complete_pair_ordinals = frozenset(
            ordinal
            for ordinal in range(1, sequence_length + 1)
            if all(
                hypothesis.observations_by_role[index] is not None
                for index in (
                    (ordinal - 1) * 2,
                    (ordinal - 1) * 2 + 1,
                )
            )
        )
        one_sided_ordinals = frozenset(
            ordinal
            for ordinal in range(1, sequence_length + 1)
            if ordinal not in complete_pair_ordinals
            and any(
                hypothesis.observations_by_role[index] is not None
                for index in (
                    (ordinal - 1) * 2,
                    (ordinal - 1) * 2 + 1,
                )
            )
        )
        material_ordinals = _material_content_ordinals(
            hypothesis,
            material_content_by_label[
                reconstruction.constraint.aperture_label
            ],
        )
        required_short_ordinals = (
            (
                complete_pair_ordinals
                | (one_sided_ordinals & material_ordinals)
            )
            if configuration.count_request.mode == FrameCountMode.AUTO
            else frozenset(range(1, sequence_length + 1))
        )
        if not required_short_ordinals:
            continue
        rows = tuple(
            (
                short_axis_evidence(
                    reconstruction,
                    hypothesis,
                    ordinal,
                )
                if ordinal in required_short_ordinals
                else None
            )
            for ordinal in range(1, sequence_length + 1)
        )
        coherent_rows, angle_residual = (
            _rotation_coherent_short_candidates(
                tuple(
                    ()
                    if row is None
                    else row[5]
                    for row in rows
                )
            )
        )
        coherent_rows_by_choice[
            (
                reconstruction.constraint.aperture_label,
                hypothesis.hypothesis_id,
            )
        ] = coherent_rows
        selected_short = tuple(
            row[0]
            for ordinal, row in enumerate(coherent_rows, 1)
            if ordinal in required_short_ordinals and row
        )
        if len(selected_short) != len(required_short_ordinals):
            continue
        content_score = content_score_by_choice[
            (
                reconstruction.constraint.aperture_label,
                hypothesis.hypothesis_id,
            )
        ]
        combined_uncertainty_px = (
            hypothesis.physical_uncertainty_px
            + sum(item.uncertainty_px for item in selected_short)
        )
        combined_residual_px = (
            hypothesis.scalar_residual_px
            + sum(item.residual_px for item in selected_short)
        )
        effective_short_support = sum(
            item.support_count * item.continuous_support_fraction
            for item in selected_short
        )
        isolated_background_support = tuple(
            observation.background_side_support_fraction
            for ordinal in sorted(required_short_ordinals)
            for role_index, neighboring_ordinal in (
                ((ordinal - 1) * 2, ordinal - 1),
                ((ordinal - 1) * 2 + 1, ordinal + 1),
            )
            if neighboring_ordinal not in required_short_ordinals
            for observation in (
                hypothesis.observations_by_role[role_index],
            )
            if observation is not None
        )
        isolated_background_supported_count = sum(
            value
            >= PHOTO_BOUNDARY_MEASUREMENT_SPEC
            .directional_background_support_minimum
            for value in isolated_background_support
        )
        rank = (
            float(len(selected_short)),
            float(hypothesis.observed_aperture_pair_count),
            content_score.assigned_content_containment_supported,
            content_score.complete_assignment,
            content_score.stable_ownership,
            float(isolated_background_supported_count),
            (
                min(isolated_background_support)
                if isolated_background_support
                else 0.0
            ),
            float(
                sum(
                    item.known_content_contained
                    for item in selected_short
                )
            ),
            float(
                sum(
                    item.observed_edge_count
                    for item in selected_short
                )
            ),
            float(hypothesis.observed_role_count),
            # This is polarity-independent pixel evidence that one side of
            # each fitted line behaves like background/separator.  It
            # distinguishes a true photo edge from a stronger interior image
            # transition without imposing one global light/dark direction.
            hypothesis.background_side_support_fraction,
            -combined_residual_px,
            -combined_uncertainty_px,
            float(effective_short_support),
            float(
                sum(item.support_count for item in selected_short)
            ),
            float(
                sum(
                    item.continuous_support_fraction
                    for item in selected_short
                )
            ),
            -float(
                sum(item.uncertainty_px for item in selected_short)
            ),
            -float(
                sum(item.residual_px for item in selected_short)
            ),
            -angle_residual,
            content_score.safe_containment_fraction,
            float(content_score.occupied_frame_count),
            content_score.assignment_fraction,
            float(
                hypothesis.role_oriented_observed_role_count
            ),
            (
                hypothesis.background_side_support_fraction
                * hypothesis.role_oriented_observed_role_count
            ),
            (
                hypothesis.role_oriented_background_support_fraction
                * hypothesis.role_oriented_observed_role_count
            ),
            hypothesis.background_side_support_fraction,
            hypothesis.role_oriented_background_support_fraction,
            -abs(
                hypothesis.translation_interval_px.center
                - (
                    reconstruction.expected_grid_translation_px
                    if reconstruction.expected_grid_translation_px
                    is not None
                    else hypothesis.translation_interval_px.center
                )
            ),
        )
        assessed_choices.append((rank, reconstruction, hypothesis))
    label_choices: tuple[
        tuple[LabelSequenceReconstruction, LongAxisSequenceHypothesis],
        ...,
    ]
    if not assessed_choices:
        label_choices = ()
    else:
        best_primary_rank = max(
            item[0][:5] for item in assessed_choices
        )
        primary_choices = [
            item
            for item in assessed_choices
            if item[0][:5] == best_primary_rank
        ]
        best_rank = max(item[0] for item in primary_choices)
        label_choices = tuple(
            (reconstruction, hypothesis)
            for rank, reconstruction, hypothesis in primary_choices
            if rank == best_rank
        )

    best_assignment_fraction = max(
        (
            score.assignment_fraction
            for score in content_score_by_choice.values()
        ),
        default=1.0,
    )
    material_content_residual_risk = (
        MATERIAL_ASSIGNMENT_RESIDUAL_RISK_MINIMUM
        <= best_assignment_fraction
        < MATERIAL_ASSIGNMENT_COMPLETE_FRACTION
    )
    sequence_candidate_records: list[
        tuple[
            tuple[float, float, float],
            UndominatedFrameSequenceCandidate,
        ]
    ] = []
    candidate_source_choices = (
        tuple(
            item
            for item in assessed_choices
            if (
                content_score_by_choice[
                    (
                        item[1].constraint.aperture_label,
                        item[2].hypothesis_id,
                    )
                ].assignment_fraction
                >= (
                    best_assignment_fraction
                    - MATERIAL_ASSIGNMENT_EQUIVALENCE_FRACTION
                )
            )
        )
        if material_content_residual_risk
        else tuple(
            item
            for item in assessed_choices
            if (item[1], item[2]) in label_choices
        )
    )
    for rank, reconstruction, hypothesis in candidate_source_choices:
        key = (
            reconstruction.constraint.aperture_label,
            hypothesis.hypothesis_id,
        )
        coherent_rows = coherent_rows_by_choice.get(key)
        if coherent_rows is None:
            continue
        candidate = complete_sequence_candidate(
            reconstruction,
            hypothesis,
            coherent_rows,
            rank,
        )
        if candidate is None:
            continue
        score = content_score_by_choice[key]
        sequence_candidate_records.append(
            (
                (
                    score.assigned_content_containment_supported,
                    score.complete_assignment,
                    score.stable_ownership,
                ),
                candidate,
            )
        )

    # Capacity-auto owns the fixed number of output slots, not the number of
    # visible photos.  When capacity placement cannot safely contain known
    # content, build one bounded observed-photo-chain proposal from pixel
    # evidence.  The proposal does not change output capacity or authorize
    # export; it preserves the complete competing source geometry for review.
    if configuration.count_request.mode == FrameCountMode.AUTO:
        selected_capacity_labels = {
            selected_reconstruction.constraint.aperture_label
            for selected_reconstruction, _hypothesis in label_choices
        }
        for reconstruction in label_reconstructions:
            label = reconstruction.constraint.aperture_label
            if label not in selected_capacity_labels:
                continue
            proposed_photo_count = max(
                (
                    score.occupied_frame_count
                    for (choice_label, _hypothesis_id), score
                    in content_score_by_choice.items()
                    if choice_label == label
                ),
                default=0,
            )
            selected_capacity_pair_count = max(
                (
                    hypothesis.observed_aperture_pair_count
                    for selected_reconstruction, hypothesis
                    in label_choices
                    if (
                        selected_reconstruction.constraint
                        .aperture_label
                        == label
                    )
                ),
                default=0,
            )
            if (
                not 0 < proposed_photo_count < sequence_length
                or proposed_photo_count
                <= selected_capacity_pair_count
            ):
                continue
            aperture_width_mm = PositiveInterval(
                reconstruction.constraint.aperture.long_axis_mm
                - configuration.physical_spec.aperture_tolerance
                .long_axis_tolerance_mm,
                reconstruction.constraint.aperture.long_axis_mm
                + configuration.physical_spec.aperture_tolerance
                .long_axis_tolerance_mm,
            )
            chain_hypotheses = solve_long_axis_sequence_hypotheses(
                reconstruction.physical_long_observations,
                authoritative_sequence_length=proposed_photo_count,
                aperture_width_px=(
                    reconstruction.aperture_pixels.long_axis_px
                ),
                aperture_width_mm=aperture_width_mm,
                shared_scale_px_per_mm=(
                    reconstruction.shared_scale_constraint_px_per_mm
                ),
                gutter_px=reconstruction.gutter_px,
                boundary_axis=long_axis,
                reference_trace_px=reference_short,
                lane_long_extent_px=_axis_extent(
                    lane_box,
                    long_axis,
                ),
                expected_grid_translation_px=None,
                known_content_interval_px=(
                    reconstruction.content_support_interval_px
                ),
                preferred_outer_assignments=(),
                allow_blank_slots=False,
            )
            material_content = material_content_by_label[label]
            chain_records: list[
                tuple[
                    tuple[float, float, float],
                    UndominatedFrameSequenceCandidate,
                ]
            ] = []
            for hypothesis in chain_hypotheses:
                content_score = _long_content_assignment_score(
                    hypothesis,
                    material_content,
                    layout=layout,
                    safe_padding_px=(
                        PHOTO_BOUNDARY_MEASUREMENT_SPEC
                        .interpolation_allowance_source_px
                        + protection.long_axis_mm_per_side
                        * lane.axis_scale_intervals
                        .long_axis_px_per_mm.maximum
                    ),
                )
                raw_rows = tuple(
                    short_axis_evidence(
                        reconstruction,
                        hypothesis,
                        ordinal,
                    )[5]
                    for ordinal in range(
                        1,
                        proposed_photo_count + 1,
                    )
                )
                coherent_rows, angle_residual = (
                    _rotation_coherent_short_candidates(raw_rows)
                )
                if any(not row for row in coherent_rows):
                    continue
                selected_short = tuple(
                    row[0] for row in coherent_rows
                )
                rank = (
                    float(len(selected_short)),
                    float(hypothesis.observed_aperture_pair_count),
                    content_score.assigned_content_containment_supported,
                    content_score.complete_assignment,
                    content_score.stable_ownership,
                    float(hypothesis.observed_role_count),
                    hypothesis.background_side_support_fraction,
                    -(
                        hypothesis.scalar_residual_px
                        + sum(
                            item.residual_px
                            for item in selected_short
                        )
                    ),
                    -(
                        hypothesis.physical_uncertainty_px
                        + sum(
                            item.uncertainty_px
                            for item in selected_short
                        )
                    ),
                    -angle_residual,
                )
                candidate = complete_sequence_candidate(
                    reconstruction,
                    hypothesis,
                    coherent_rows,
                    rank,
                )
                if candidate is None:
                    continue
                chain_records.append(
                    (
                        (
                            content_score.assigned_content_containment_supported,
                            content_score.complete_assignment,
                            content_score.stable_ownership,
                        ),
                        candidate,
                    )
                )
            if chain_records:
                best_chain_content_class = max(
                    item[0] for item in chain_records
                )
                sequence_candidate_records.extend(
                    item
                    for item in chain_records
                    if item[0] == best_chain_content_class
                )

    output_equivalence_px = max(
        1.0,
        0.05
        * lane.axis_scale_intervals
        .long_axis_px_per_mm.maximum,
    )

    def candidate_outputs_equivalent(
        left: UndominatedFrameSequenceCandidate,
        right: UndominatedFrameSequenceCandidate,
    ) -> bool:
        if len(left.output_geometries) != len(
            right.output_geometries
        ):
            return False
        return all(
            all(
                abs(left_value - right_value)
                <= output_equivalence_px
                for left_value, right_value in zip(
                    (
                        left_geometry.source_protected_box.left,
                        left_geometry.source_protected_box.top,
                        left_geometry.source_protected_box.right,
                        left_geometry.source_protected_box.bottom,
                    ),
                    (
                        right_geometry.source_protected_box.left,
                        right_geometry.source_protected_box.top,
                        right_geometry.source_protected_box.right,
                        right_geometry.source_protected_box.bottom,
                    ),
                    strict=True,
                )
            )
            for left_geometry, right_geometry in zip(
                left.output_geometries,
                right.output_geometries,
                strict=True,
            )
        )

    undominated_sequence_candidates_list: list[
        UndominatedFrameSequenceCandidate
    ] = []
    for content_class, candidate in sorted(
        sequence_candidate_records,
        key=lambda item: (
            item[0],
            item[1].selection_rank,
            item[1].candidate_id,
        ),
        reverse=True,
    ):
        del content_class
        equivalent_index = next(
            (
                index
                for index, existing in enumerate(
                    undominated_sequence_candidates_list
                )
                if candidate_outputs_equivalent(existing, candidate)
            ),
            None,
        )
        if equivalent_index is None:
            undominated_sequence_candidates_list.append(candidate)
            continue
        existing = undominated_sequence_candidates_list[
            equivalent_index
        ]
        if candidate.selection_rank > existing.selection_rank:
            undominated_sequence_candidates_list[
                equivalent_index
            ] = candidate
    undominated_sequence_candidates = tuple(
        sorted(
            undominated_sequence_candidates_list,
            key=lambda item: item.candidate_id,
        )
    )

    no_known_photo_content = all(
        reconstruction.content_support_interval_px is None
        for reconstruction in label_reconstructions
    )
    blank_model_candidate = not label_choices and no_known_photo_content
    blank_model_candidate = (
        blank_model_candidate
        and configuration.count_request.mode == FrameCountMode.AUTO
    )

    unresolved: list[str] = []
    if unavailable_measurement:
        unresolved.append("photo_boundary_measurement_unavailable")
    if (
        any(material_content_by_label.values())
        and (
            best_content_class[0] < 1.0
            or material_content_residual_risk
        )
    ):
        unresolved.append("known_content_containment_unresolved")
    if len(undominated_sequence_candidates) > 2:
        unresolved.append(
            "complete_sequence_state_count_exceeds_two"
        )
    elif len(undominated_sequence_candidates) > 1:
        unresolved.append(
            "sequence_geometry_competition_unresolved"
        )
    if not label_choices:
        if not blank_model_candidate:
            unresolved.append("sequence_translation_unresolved")
        selected_reconstruction = label_reconstructions[0]
        selected_hypothesis = None
    else:
        selected_reconstruction, selected_hypothesis = label_choices[0]
        if len(label_choices) > 2:
            unresolved.append(
                "complete_sequence_state_count_exceeds_two"
            )
        elif len(label_choices) > 1:
            unresolved.append("sequence_aperture_or_phase_unresolved")
        selected_coherent_rows = coherent_rows_by_choice[
            (
                selected_reconstruction.constraint.aperture_label,
                selected_hypothesis.hypothesis_id,
            )
        ]
        for ordinal, candidates in enumerate(
            selected_coherent_rows,
            1,
        ):
            key = (
                selected_reconstruction.constraint.aperture_label,
                selected_hypothesis.hypothesis_id,
                ordinal,
            )
            if key not in short_frame_cache:
                continue
            cached = short_frame_cache[key]
            short_frame_cache[key] = (*cached[:5], candidates)

    expected_translation = (
        selected_reconstruction.expected_grid_translation_px
        if selected_reconstruction.expected_grid_translation_px is not None
        else combined_expected
    )
    grid_translation = _grid_translation(
        selected_hypothesis,
        expected_translation,
        profile_bounded=(
            configuration.count_request.mode == FrameCountMode.AUTO
        ),
        no_known_content=(
            selected_reconstruction.content_support_interval_px is None
        ),
    )
    if grid_translation.outcome == GridSlotTranslationOutcome.UNRESOLVED:
        unresolved.append("grid_slot_translation_unresolved")

    states_by_ordinal: list[tuple[FrameGeometryState, ...]] = []
    all_states_by_ordinal: list[tuple[FrameGeometryState, ...]] = []
    selected_observations: dict[str, PhotoBoundaryObservation] = {}
    used_observation_ids: set[str] = set()
    resolved_outputs: list[ResolvedOutputGeometry] = []
    top_by_ordinal: list[tuple[PhotoBoundaryObservation, ...]] = []
    bottom_by_ordinal: list[tuple[PhotoBoundaryObservation, ...]] = []
    constraint_set = None
    solution = None

    if selected_hypothesis is not None:
        selected_material_ordinals = _material_content_ordinals(
            selected_hypothesis,
            material_content_by_label.get(
                selected_reconstruction.constraint.aperture_label,
                (),
            ),
        )
        for observation in selected_hypothesis.observations_by_role:
            if observation is not None:
                selected_observations[str(observation.observation_id)] = (
                    observation
                )
        for ordinal in range(1, sequence_length + 1):
            start_interval = selected_hypothesis.position_intervals_px[
                (ordinal - 1) * 2
            ]
            end_interval = selected_hypothesis.position_intervals_px[
                (ordinal - 1) * 2 + 1
            ]
            observed_long_pair = all(
                selected_hypothesis.observations_by_role[index]
                is not None
                for index in (
                    (ordinal - 1) * 2,
                    (ordinal - 1) * 2 + 1,
                )
            )
            if (
                configuration.count_request.mode == FrameCountMode.AUTO
                and not (
                    observed_long_pair
                    or (
                        ordinal in selected_material_ordinals
                        and any(
                            selected_hypothesis
                            .observations_by_role[index]
                            is not None
                            for index in (
                                (ordinal - 1) * 2,
                                (ordinal - 1) * 2 + 1,
                            )
                        )
                    )
                )
            ):
                top_by_ordinal.append(())
                bottom_by_ordinal.append(())
                blank = _model_state(
                    lane.domain.lane_id,
                    ordinal,
                    selected_reconstruction.constraint.aperture_label,
                )
                states_by_ordinal.append((blank,))
                all_states_by_ordinal.append((blank,))
                continue
            (
                support_span,
                frame_reference_long,
                top_observations,
                bottom_observations,
                content_short,
                short_candidates,
            ) = short_axis_evidence(
                selected_reconstruction,
                selected_hypothesis,
                ordinal,
            )
            top_by_ordinal.append(top_observations)
            bottom_by_ordinal.append(bottom_observations)
            for observation in (*top_observations, *bottom_observations):
                selected_observations[str(observation.observation_id)] = (
                    observation
                )
            states: list[FrameGeometryState] = []
            for short_candidate in short_candidates:
                start, end = frame_long_boundaries(
                    selected_hypothesis,
                    lane_ordinal=ordinal,
                    boundary_axis=long_axis,
                    reference_trace_px=reference_short,
                    support_projection_px=lane_short_interval,
                )
                provisional = build_frame_photo_geometry(
                    lane_id=lane.domain.lane_id,
                    lane_ordinal=ordinal,
                    start=start,
                    end=end,
                    short_candidate=short_candidate,
                    content_component_ids=(),
                    ownership="unassigned",
                )
                content_ids = _content_ids_for_geometry(
                    provisional,
                    lane,
                    layout,
                    minimum_component_cells=max(
                        64,
                        int(
                            math.ceil(
                                0.0001
                                * (
                                    selected_reconstruction.aperture_pixels
                                    .long_axis_px.minimum
                                    + selected_reconstruction.aperture_pixels
                                    .long_axis_px.maximum
                                )
                                / 2.0
                                * (
                                    selected_reconstruction.aperture_pixels
                                    .short_axis_px.minimum
                                    + selected_reconstruction.aperture_pixels
                                    .short_axis_px.maximum
                                )
                                / 2.0
                            )
                        ),
                    ),
                    maximum_long_span_px=(
                        selected_reconstruction.aperture_pixels
                        .long_axis_px.maximum
                        * 1.25
                    ),
                    maximum_short_span_px=(
                        selected_reconstruction.aperture_pixels
                        .short_axis_px.maximum
                        * 1.25
                    ),
                )
                geometry = replace(
                    provisional,
                    content_component_ids=content_ids,
                    ownership=(
                        "assigned_content"
                        if content_ids
                        else "observed_empty"
                    ),
                )
                previous_gap = (
                    None
                    if ordinal == 1
                    else FiniteInterval(
                        start_interval.minimum
                        - selected_hypothesis.position_intervals_px[
                            (ordinal - 2) * 2 + 1
                        ].maximum,
                        start_interval.maximum
                        - selected_hypothesis.position_intervals_px[
                            (ordinal - 2) * 2 + 1
                        ].minimum,
                    )
                )
                next_gap = (
                    None
                    if ordinal == sequence_length
                    else FiniteInterval(
                        selected_hypothesis.position_intervals_px[
                            ordinal * 2
                        ].minimum
                        - end_interval.maximum,
                        selected_hypothesis.position_intervals_px[
                            ordinal * 2
                        ].maximum
                        - end_interval.minimum,
                    )
                )
                state = FrameGeometryState(
                    state_id=_state_id(
                        selected_hypothesis.hypothesis_id,
                        geometry.geometry_id,
                    ),
                    lane_id=lane.domain.lane_id,
                    lane_ordinal=ordinal,
                    photo_geometry=geometry,
                    aperture_label=(
                        selected_reconstruction.constraint.aperture_label
                    ),
                    rotation_class_id="observed_lane_rotation",
                    ownership=geometry.ownership,
                    interaction_before=(
                        None
                        if previous_gap is None
                        else _adjacency_kind(previous_gap)
                    ),
                    interaction_after=(
                        None
                        if next_gap is None
                        else _adjacency_kind(next_gap)
                    ),
                    model_only=False,
                    physical_residual_px=(
                        short_candidate.residual_px
                        + selected_hypothesis.scalar_residual_px
                    ),
                    measurement_uncertainty_px=(
                        short_candidate.uncertainty_px
                        + start.outward_uncertainty_px
                        + end.outward_uncertainty_px
                    ),
                )
                states.append(state)

            actual_photo_required = (
                configuration.count_request.mode != FrameCountMode.AUTO
            )
            if len(states) > 1:
                component_weight = {
                    component.component_id: component.positive_cells
                    for component in lane.content.components
                }
                ownership_support = tuple(
                    sum(
                        component_weight[component_id]
                        for component_id in (
                            state.photo_geometry.content_component_ids
                            if state.photo_geometry is not None
                            else ()
                        )
                    )
                    for state in states
                )
                maximum_ownership_support = max(ownership_support)
                if maximum_ownership_support > 0:
                    states = [
                        state
                        for state, support in zip(
                            states,
                            ownership_support,
                            strict=True,
                        )
                        if support == maximum_ownership_support
                    ]
            if not states:
                if actual_photo_required or content_short is not None:
                    unresolved.append(
                        f"lane_{lane.domain.lane_id}_ordinal_{ordinal}_"
                        "photo_geometry_unavailable"
                    )
                states = [
                    _model_state(
                        lane.domain.lane_id,
                        ordinal,
                        selected_reconstruction.constraint.aperture_label,
                    )
                ]
            all_states = tuple(states)
            absorber_index = _protection_absorbing_state_index(
                all_states,
                lane,
                layout=layout,
                configuration=configuration,
            )
            if absorber_index not in {None, 0}:
                all_states = (
                    all_states[absorber_index],
                    *(
                        state
                        for index, state in enumerate(all_states)
                        if index != absorber_index
                    ),
                )
            observed_state_count = sum(
                not state.model_only for state in all_states
            )
            if observed_state_count > 2:
                unresolved.append(
                    f"lane_{lane.domain.lane_id}_ordinal_{ordinal}_"
                    "observed_non_dominated_count_exceeds_two"
                )
            all_states_by_ordinal.append(all_states)
            states_by_ordinal.append(
                all_states
                if len(all_states) <= 3
                else (all_states[0],)
            )

        if configuration.count_request.mode == FrameCountMode.AUTO:
            for index, states in enumerate(states_by_ordinal):
                observed_states = tuple(
                    state
                    for state in states
                    if (
                        state.photo_geometry is not None
                        and any(
                            edge.source.value == "observed"
                            for edge in (
                                state.photo_geometry.start,
                                state.photo_geometry.end,
                            )
                        )
                    )
                )
                if observed_states:
                    states_by_ordinal[index] = observed_states
                    all_states_by_ordinal[index] = observed_states
                    continue
                blank = _model_state(
                    lane.domain.lane_id,
                    index + 1,
                    selected_reconstruction.constraint.aperture_label,
                )
                states_by_ordinal[index] = (blank,)
                all_states_by_ordinal[index] = (blank,)

        constraint_set = FrameSequenceGeometryConstraintSet(
            constraint_set_id=(
                "constraint-set:"
                + selected_hypothesis.hypothesis_id
            ),
            lane_id=lane.domain.lane_id,
            output_slot_count=sequence_length,
            authoritative_photo_count=(
                None
                if configuration.count_request.mode
                == FrameCountMode.AUTO
                else sequence_length
            ),
            aperture=selected_reconstruction.constraint.aperture,
            aperture_label=(
                selected_reconstruction.constraint.aperture_label
            ),
            width_interval_px=(
                selected_reconstruction.aperture_pixels.long_axis_px
            ),
            height_interval_px=(
                selected_reconstruction.aperture_pixels.short_axis_px
            ),
            typed_gutter_interval_px=selected_reconstruction.gutter_px,
            long_boundary_observations=(
                selected_reconstruction.physical_long_observations
            ),
            top_observations_by_ordinal=tuple(top_by_ordinal),
            bottom_observations_by_ordinal=tuple(bottom_by_ordinal),
            adjacency_constraints=(),
        )
        selected_states: list[FrameGeometryState] = []
        for ordinal, states in enumerate(states_by_ordinal, 1):
            if len(states) > 1:
                if (
                    _protection_absorbing_state_index(
                        states,
                        lane,
                        layout=layout,
                        configuration=configuration,
                    )
                    is None
                ):
                    unresolved.append(
                        f"lane_{lane.domain.lane_id}_ordinal_{ordinal}_"
                        "frame_geometry_competition_unresolved"
                    )
            selected_states.append(states[0])

        photo_translation = photo_translation_assessment(
            tuple(item[1] for item in label_choices)
            if label_choices
            else ()
        )
        if (
            photo_translation.outcome
            == PhotoSequenceTranslationOutcome.UNRESOLVED
        ):
            unresolved.append("sequence_translation_unresolved")
        first_photo_ordinal = next(
            (
                state.lane_ordinal
                for state in selected_states
                if state.photo_geometry is not None
            ),
            None,
        )
        if first_photo_ordinal is None:
            first_start = FirstPhotoStartAssessment(
                outcome=FirstPhotoStartOutcome.NOT_APPLICABLE,
                lane_ordinal=None,
                interval_px=None,
                observation_ids=(),
            )
        else:
            role_index = (first_photo_ordinal - 1) * 2
            observation = selected_hypothesis.observations_by_role[
                role_index
            ]
            first_start = FirstPhotoStartAssessment(
                outcome=(
                    FirstPhotoStartOutcome.OBSERVED_LEADING
                    if observation is not None
                    else FirstPhotoStartOutcome.SEQUENCE_INFERRED
                ),
                lane_ordinal=first_photo_ordinal,
                interval_px=selected_hypothesis.position_intervals_px[
                    role_index
                ],
                observation_ids=(
                    ()
                    if observation is None
                    else (observation.observation_id,)
                ),
            )
        raw_transition_count = sum(
            len(item.transitions) for item in measurement_sets
        )
        line_family_count = sum(
            len(item.raw_long_observations)
            for item in label_reconstructions
        ) + sum(len(item) for item in top_by_ordinal) + sum(
            len(item) for item in bottom_by_ordinal
        )
        work = SequenceWorkReceipt(
            raw_transition_count=raw_transition_count,
            line_family_count=line_family_count,
            physical_geometry_count=sum(
                len(item) for item in all_states_by_ordinal
            ),
            pre_join_state_count=sum(
                len(item) for item in all_states_by_ordinal
            ),
            post_join_state_count=sum(
                len(item) for item in states_by_ordinal
            ),
            deduplicated_state_count=sum(
                len(item) for item in states_by_ordinal
            ),
            sequence_phase_class_count=len(label_choices),
            dp_state_count=sum(
                len(item) for item in states_by_ordinal
            ),
            dp_transition_count=sum(
                len(left) * len(right)
                for left, right in zip(
                    states_by_ordinal,
                    states_by_ordinal[1:],
                )
            ),
            pixel_query_count=sum(
                item.coverage.pixel_query_count
                for item in measurement_sets
            ),
            shared_measurement_reuse_count=max(
                0,
                len(constraints) - 1,
            )
            * len(measurement_sets),
            peak_temporary_memory_bytes=max(
                (
                    content_geometry_index.temporary_bytes,
                    *(
                        item.coverage.peak_temporary_bytes
                        for item in measurement_sets
                    ),
                ),
            ),
        )
        solution = FrameSequenceGeometrySolution(
            solution_id=(
                "sequence-solution:"
                + selected_hypothesis.hypothesis_id
            ),
            lane_id=lane.domain.lane_id,
            aperture_label=(
                selected_reconstruction.constraint.aperture_label
            ),
            selected_states=tuple(selected_states),
            undominated_states_by_ordinal=tuple(states_by_ordinal),
            photo_translation=photo_translation,
            grid_translation=grid_translation,
            first_photo_start=first_start,
            work=work,
            unresolved_codes=tuple(dict.fromkeys(unresolved)),
        )

        grid_roles = sequence_boundary_roles(
            sequence_length,
            selected_reconstruction.aperture_pixels.long_axis_px,
            selected_reconstruction.gutter_px,
        )
        if grid_translation.interval_px is None:
            grid_positions: tuple[FiniteInterval, ...] = ()
        else:
            grid_positions = tuple(
                FiniteInterval(
                    grid_translation.interval_px.minimum
                    + role.relative_interval_px.minimum,
                    grid_translation.interval_px.maximum
                    + role.relative_interval_px.maximum,
                )
                for role in grid_roles
            )
        for state in selected_states:
            if state.photo_geometry is not None:
                for edge in (
                    state.photo_geometry.top,
                    state.photo_geometry.bottom,
                    state.photo_geometry.start,
                    state.photo_geometry.end,
                ):
                    if edge.source.value == "observed":
                        used_observation_ids.update(
                            str(item) for item in edge.observation_ids
                        )
                resolved_outputs.append(
                    safe_crop_envelope_from_photo_geometry(
                        state.photo_geometry,
                        lane,
                        layout=layout,
                        protection=output_protection_spec(
                            configuration.physical_spec.format_id
                        ),
                    )
                )
            else:
                if not grid_positions:
                    unresolved.append(
                        "grid_slot_translation_unresolved"
                    )
                    continue
                role_index = (state.lane_ordinal - 1) * 2
                start_interval = grid_positions[role_index]
                end_interval = grid_positions[role_index + 1]
                center_short = lane_short_interval.center
                half_height = (
                    selected_reconstruction
                    .aperture_pixels.short_axis_px.maximum
                    / 2.0
                )
                resolved_outputs.append(
                    grid_inferred_blank_output_geometry(
                        lane=lane,
                        layout=layout,
                        lane_ordinal=state.lane_ordinal,
                        long_axis_interval_px=FiniteInterval(
                            start_interval.minimum,
                            end_interval.maximum,
                        ),
                        short_axis_interval_px=FiniteInterval(
                            center_short - half_height,
                            center_short + half_height,
                        ),
                        grid_translation=grid_translation,
                        protection=output_protection_spec(
                            configuration.physical_spec.format_id
                        ),
                    )
                )
    elif blank_model_candidate:
        blank_candidates: list[
            tuple[
                LabelSequenceReconstruction,
                GridSlotTranslationAssessment,
                tuple[GridInferredBlankOutputGeometry, ...],
            ]
        ] = []
        for reconstruction in label_reconstructions:
            candidate_translation_px = (
                reconstruction.expected_grid_translation_px
                if reconstruction.expected_grid_translation_px is not None
                else _expected_grid_translation(
                    sequence_length,
                    reconstruction.aperture_pixels.long_axis_px,
                    reconstruction.gutter_px,
                    _axis_extent(lane_box, long_axis),
                )
            )
            candidate_grid_translation = GridSlotTranslationAssessment(
                outcome=(
                    GridSlotTranslationOutcome
                    .SCAN_CANVAS_PROFILE_BOUNDED
                ),
                interval_px=FiniteInterval.exact(
                    candidate_translation_px
                ),
                protected_footprint_equivalence_class_id=None,
                competing_class_ids=(),
            )
            roles = sequence_boundary_roles(
                sequence_length,
                reconstruction.aperture_pixels.long_axis_px,
                reconstruction.gutter_px,
            )
            positions = tuple(
                FiniteInterval(
                    candidate_translation_px
                    + role.relative_interval_px.minimum,
                    candidate_translation_px
                    + role.relative_interval_px.maximum,
                )
                for role in roles
            )
            center_short = lane_short_interval.center
            half_height = (
                reconstruction.aperture_pixels.short_axis_px.maximum
                / 2.0
            )
            outputs = tuple(
                grid_inferred_blank_output_geometry(
                    lane=lane,
                    layout=layout,
                    lane_ordinal=ordinal,
                    long_axis_interval_px=FiniteInterval(
                        positions[(ordinal - 1) * 2].minimum,
                        positions[(ordinal - 1) * 2 + 1].maximum,
                    ),
                    short_axis_interval_px=FiniteInterval(
                        center_short - half_height,
                        center_short + half_height,
                    ),
                    grid_translation=candidate_grid_translation,
                    protection=output_protection_spec(
                        configuration.physical_spec.format_id
                    ),
                )
                for ordinal in range(1, sequence_length + 1)
            )
            blank_candidates.append(
                (
                    reconstruction,
                    candidate_grid_translation,
                    outputs,
                )
            )

        footprint_classes: dict[
            tuple[tuple[int, int, int, int], ...],
            list[
                tuple[
                    LabelSequenceReconstruction,
                    GridSlotTranslationAssessment,
                    tuple[GridInferredBlankOutputGeometry, ...],
                ]
            ],
        ] = {}
        for candidate in blank_candidates:
            footprint_key = tuple(
                (
                    geometry.source_protected_box.left,
                    geometry.source_protected_box.top,
                    geometry.source_protected_box.right,
                    geometry.source_protected_box.bottom,
                )
                for geometry in candidate[2]
            )
            footprint_classes.setdefault(footprint_key, []).append(candidate)

        if len(footprint_classes) == 1:
            selected_reconstruction, _, selected_outputs = (
                blank_candidates[0]
            )
            footprint_key = next(iter(footprint_classes))
            footprint_payload = repr(footprint_key).encode("utf-8")
            equivalence_class_id = (
                "blank-output-equivalence:"
                + sha256(footprint_payload).hexdigest()[:24]
            )
            grid_translation = GridSlotTranslationAssessment(
                outcome=(
                    GridSlotTranslationOutcome
                    .MODEL_BOUNDED_OUTPUT_EQUIVALENT
                ),
                interval_px=FiniteInterval.exact(
                    selected_reconstruction
                    .expected_grid_translation_px
                    if selected_reconstruction
                    .expected_grid_translation_px is not None
                    else combined_expected
                ),
                protected_footprint_equivalence_class_id=(
                    equivalence_class_id
                ),
                competing_class_ids=(),
            )
            resolved_outputs.extend(
                replace(
                    geometry,
                    grid_translation=grid_translation,
                )
                for geometry in selected_outputs
            )
            states_by_ordinal = [
                (
                    _model_state(
                        lane.domain.lane_id,
                        ordinal,
                        selected_reconstruction
                        .constraint.aperture_label,
                    ),
                )
                for ordinal in range(1, sequence_length + 1)
            ]
            all_states_by_ordinal = list(states_by_ordinal)
            work = SequenceWorkReceipt(
                raw_transition_count=sum(
                    len(item.transitions) for item in measurement_sets
                ),
                line_family_count=sum(
                    len(item.raw_long_observations)
                    for item in label_reconstructions
                ),
                physical_geometry_count=sequence_length,
                pre_join_state_count=sequence_length,
                post_join_state_count=sequence_length,
                deduplicated_state_count=sequence_length,
                sequence_phase_class_count=1,
                dp_state_count=sequence_length,
                dp_transition_count=max(0, sequence_length - 1),
                pixel_query_count=sum(
                    item.coverage.pixel_query_count
                    for item in measurement_sets
                ),
                shared_measurement_reuse_count=max(
                    0,
                    len(constraints) - 1,
                )
                * len(measurement_sets),
                peak_temporary_memory_bytes=max(
                    (
                        content_geometry_index.temporary_bytes,
                        *(
                            item.coverage.peak_temporary_bytes
                            for item in measurement_sets
                        ),
                    ),
                ),
            )
            solution = FrameSequenceGeometrySolution(
                solution_id=(
                    "blank-sequence-solution:"
                    + equivalence_class_id.rsplit(":", 1)[-1]
                ),
                lane_id=lane.domain.lane_id,
                aperture_label=(
                    selected_reconstruction.constraint.aperture_label
                ),
                selected_states=tuple(
                    states[0] for states in states_by_ordinal
                ),
                undominated_states_by_ordinal=tuple(
                    states_by_ordinal
                ),
                photo_translation=PhotoSequenceTranslationAssessment(
                    outcome=(
                        PhotoSequenceTranslationOutcome
                        .NOT_APPLICABLE_NO_PHOTO_GEOMETRY
                    ),
                    interval_px=None,
                    observation_ids=(),
                    competing_class_ids=(),
                ),
                grid_translation=grid_translation,
                first_photo_start=FirstPhotoStartAssessment(
                    outcome=FirstPhotoStartOutcome.NOT_APPLICABLE,
                    lane_ordinal=None,
                    interval_px=None,
                    observation_ids=(),
                ),
                work=work,
                unresolved_codes=tuple(dict.fromkeys(unresolved)),
            )
        else:
            class_ids = tuple(
                "blank-output-class:"
                + sha256(repr(key).encode("utf-8")).hexdigest()[:24]
                for key in sorted(footprint_classes)
            )
            grid_translation = GridSlotTranslationAssessment(
                outcome=GridSlotTranslationOutcome.UNRESOLVED,
                interval_px=None,
                protected_footprint_equivalence_class_id=None,
                competing_class_ids=class_ids,
            )
            unresolved.append("grid_slot_translation_unresolved")

    return LanePhotoGeometryReconstruction(
        lane_id=lane.domain.lane_id,
        anchor_domain=anchor_domain,
        extent_proposals=tuple(extent_proposals),
        measurement_sets=measurement_sets,
        label_reconstructions=tuple(label_reconstructions),
        sequence_choice_ranking=tuple(
            (
                reconstruction.constraint.aperture_label,
                hypothesis.hypothesis_id,
                rank,
            )
            for rank, reconstruction, hypothesis in sorted(
                assessed_choices,
                key=lambda item: (
                    item[1].constraint.aperture_label,
                    item[2].hypothesis_id,
                ),
            )
        ),
        selected_label=(
            (
                selected_reconstruction.constraint.aperture_label
                if solution is not None
                else None
            )
        ),
        selected_long_hypothesis=selected_hypothesis,
        constraint_set=constraint_set,
        solution=solution,
        all_undominated_states_by_ordinal=tuple(
            all_states_by_ordinal
        ),
        undominated_sequence_candidates=(
            undominated_sequence_candidates
        ),
        resolved_output_geometries=tuple(resolved_outputs),
        selected_observations=tuple(
            selected_observations[key]
            for key in sorted(used_observation_ids)
            if key in selected_observations
        ),
        unresolved_codes=tuple(dict.fromkeys(unresolved)),
    )


def reconstruct_photo_geometry(
    field: PhotoBoundaryMeasurementField,
    lanes: tuple[SourceLaneEvidence, ...],
    *,
    layout: str,
    configuration: DetectionConfiguration,
    lane_configuration: DetectionConfiguration | None,
) -> PhotoGeometryDetectionResult:
    resolved_slots = resolve_output_slots(configuration, lanes)
    if resolved_slots is None:
        return PhotoGeometryDetectionResult(
            resolved_output_slots=None,
            lane_reconstructions=(),
            output_slot_identities=(),
            transform_assessment=(
                observed_output_transform_assessment(
                    (),
                    layout=layout,
                    source_width=field.source_extent.width,
                    source_height=field.source_extent.height,
                )
            ),
            unresolved_codes=("output_slot_count_unresolved",),
        )
    effective_configuration = lane_configuration or configuration
    lane_reconstructions = tuple(
        _reconstruct_lane(
            field,
            lane,
            layout=layout,
            sequence_length=lane_count,
            configuration=effective_configuration,
        )
        for lane, lane_count in zip(
            lanes,
            resolved_slots.lane_output_slot_counts,
            strict=True,
        )
    )
    selected_observations = tuple(
        observation
        for lane in lane_reconstructions
        for observation in lane.selected_observations
    )
    transform = observed_output_transform_assessment(
        selected_observations,
        layout=layout,
        source_width=field.source_extent.width,
        source_height=field.source_extent.height,
        allow_grid_blank_identity=(
            bool(lane_reconstructions)
            and all(
                lane.resolved_output_geometries
                and all(
                    isinstance(
                        geometry,
                        GridInferredBlankOutputGeometry,
                    )
                    for geometry in lane.resolved_output_geometries
                )
                for lane in lane_reconstructions
            )
        ),
    )
    identities: list[OutputSlotIdentity] = []
    global_ordinal = 1
    for lane, lane_count in zip(
        lanes,
        resolved_slots.lane_output_slot_counts,
        strict=True,
    ):
        for lane_ordinal in range(1, lane_count + 1):
            identities.append(
                OutputSlotIdentity(
                    global_output_ordinal=global_ordinal,
                    lane_id=lane.domain.lane_id,
                    lane_ordinal=lane_ordinal,
                )
            )
            global_ordinal += 1
    unresolved = tuple(
        dict.fromkeys(
            (
                *(
                    code
                    for lane in lane_reconstructions
                    for code in lane.unresolved_codes
                ),
                *(
                    ()
                    if transform.state == EvidenceState.SUPPORTED
                    else ("output_transform_unavailable",)
                ),
            )
        )
    )
    return PhotoGeometryDetectionResult(
        resolved_output_slots=resolved_slots,
        lane_reconstructions=lane_reconstructions,
        output_slot_identities=tuple(identities),
        transform_assessment=transform,
        unresolved_codes=unresolved,
    )
