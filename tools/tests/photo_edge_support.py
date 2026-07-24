from __future__ import annotations

from hashlib import sha256

from x5crop.configuration.shared_short_axis import SharedShortAxisParameters
from x5crop.detection.evidence.photo_edges import (
    LocalTransitionState,
    NumericInterval,
    PhotoEdgeCoordinateSpace,
    PhotoEdgeFact,
    PhotoEdgeFragmentSummary,
    PhotoEdgeLineRegionCell,
    PhotoEdgeLineWitness,
    PhotoEdgeMeasurementSummary,
    PhotoEdgeObservation,
    PhotoEdgePairEvidence,
    PhotoEdgePairGeometry,
    PhotoEdgePairHypothesis,
    PhotoEdgePhysicalLabel,
    PhotoEdgePhysicalSelection,
    PhotoEdgeSideStatistics,
    fragment_constraint_hash,
)
from x5crop.detection.evidence.transform_geometry import (
    TransformGeometryEvidence,
    TransformOutcome,
)
from x5crop.detection.physical.short_axis import (
    SharedShortAxisPlan,
    shared_short_axis_from_photo_edge_pair,
)
from x5crop.domain import (
    BoundaryAxis,
    BoundaryKind,
    EvidenceState,
    FrameSequenceSearchScope,
    GrayBoundaryPathObservation,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
)
from x5crop.formats import FrameSizeMm
from x5crop.geometry.affine import AffineCoordinateTransform


SOURCE_SHA256 = sha256(b"typed-photo-edge-test-fixture").hexdigest()
SHARED_PARAMETERS = SharedShortAxisParameters(
    maximum_endpoint_uncertainty_photo_height_ratio=1.0,
    minimum_endpoint_uncertainty_px=100.0,
)
FRAME_SIZE = FrameSizeMm(36.0, 24.0)
SIDE_STATISTICS = PhotoEdgeSideStatistics(
    intensity_median_u8=64.0,
    intensity_mad_u8=1.0,
    texture_median_u8=4.0,
    gradient_median_u8=4.0,
)


def _path_line(path: GrayBoundaryPathObservation) -> tuple[float, float]:
    coordinates = tuple(
        sample.orthogonal_interval.midpoint for sample in path.samples
    )
    positions = tuple(sample.position.midpoint for sample in path.samples)
    coordinate_center = sum(coordinates) / float(len(coordinates))
    position_center = sum(positions) / float(len(positions))
    denominator = sum(
        (coordinate - coordinate_center) ** 2
        for coordinate in coordinates
    )
    slope = (
        0.0
        if denominator <= 0.0
        else sum(
            (coordinate - coordinate_center)
            * (position - position_center)
            for coordinate, position in zip(
                coordinates,
                positions,
                strict=True,
            )
        )
        / denominator
    )
    return slope, position_center - slope * coordinate_center


def _observations(
    path: GrayBoundaryPathObservation,
    prefix: str,
) -> tuple[PhotoEdgeObservation, ...]:
    slope, intercept = _path_line(path)
    extent = path.orthogonal_extent
    width = extent.maximum - extent.minimum
    if width <= 0.0:
        raise ValueError("photo-edge fixture path requires a positive domain")
    observations: list[PhotoEdgeObservation] = []
    for index in range(3):
        start = extent.minimum + width * float(index) / 3.0
        end = extent.minimum + width * float(index + 1) / 3.0
        midpoint = 0.5 * (start + end)
        position = slope * midpoint + intercept
        observation_id = ObservationId(f"{prefix}:observation:{index}")
        provenance = MeasurementProvenance(
            root_measurement=MeasurementIdentity.PHOTO_EDGES,
            observation_id=observation_id,
            dependencies=(MeasurementIdentity.GRAY_WORK,),
            description="typed current photo-edge test observation",
            boundary_anchors=(path.provenance.observation_id,),
        )
        observations.append(
            PhotoEdgeObservation(
                observation_id=observation_id,
                source_sha256=SOURCE_SHA256,
                long_axis_footprint=PixelInterval(start, end),
                short_axis_position_interval=PixelInterval.exact(position),
                negative_side_statistics=SIDE_STATISTICS,
                positive_side_statistics=SIDE_STATISTICS,
                absolute_intensity_effect=4.0,
                absolute_texture_effect=4.0,
                absolute_gradient_effect=4.0,
                local_noise_u8=1.0,
                multiscale_position_interval=PixelInterval.exact(position),
                state=LocalTransitionState.SUPPORTED,
                measurement_channels=("gradient", "intensity", "texture"),
                measurement_scales=(0.5, 1.0, 2.0),
                censored=False,
                provenance=provenance,
            )
        )
    return tuple(observations)


def _fragment_summary(
    identity: ObservationId,
    observations: tuple[PhotoEdgeObservation, ...],
) -> PhotoEdgeFragmentSummary:
    return PhotoEdgeFragmentSummary(
        fragment_id=identity,
        long_axis_footprint=PixelInterval(
            min(
                observation.long_axis_footprint.minimum
                for observation in observations
            ),
            max(
                observation.long_axis_footprint.maximum
                for observation in observations
            ),
        ),
        short_axis_position_interval=PixelInterval(
            min(
                observation.short_axis_position_interval.minimum
                for observation in observations
            ),
            max(
                observation.short_axis_position_interval.maximum
                for observation in observations
            ),
        ),
        canonical_observation_count=len(observations),
        ordered_constraint_sha256=fragment_constraint_hash(observations),
        censored=False,
        active_observation_ids=tuple(
            observation.observation_id for observation in observations
        ),
        minimum_support_witness_ids=tuple(
            observation.observation_id for observation in observations
        ),
    )


def _identity_transform(
    width: int,
    height: int,
) -> TransformGeometryEvidence:
    return TransformGeometryEvidence(
        outcome=TransformOutcome.IDENTITY_WITHIN_TOLERANCE,
        estimated_angle_degrees=0.0,
        pixel_angle_interval_degrees=NumericInterval.exact(0.0),
        projected_edge_drift_px=0.0,
        identity_drift_threshold_px=1.0,
        position_uncertainty_px=0.0,
        coordinate_transform=AffineCoordinateTransform.identity(width, height),
    )


def photo_edge_pair_fixture(
    top: GrayBoundaryPathObservation,
    bottom: GrayBoundaryPathObservation,
    *,
    photo_band_support_depth_px: float = 1.0,
) -> PhotoEdgePairEvidence:
    del photo_band_support_depth_px
    if (
        top.axis != BoundaryAxis.SHORT
        or bottom.axis != BoundaryAxis.SHORT
        or top.kind == BoundaryKind.EDGE_ADJACENT_TRANSITION
        or bottom.kind == BoundaryKind.EDGE_ADJACENT_TRANSITION
    ):
        raise ValueError(
            "photo-edge fixture requires observed short-axis paths"
        )
    top_slope, top_intercept = _path_line(top)
    bottom_slope, bottom_intercept = _path_line(bottom)
    identity_prefix = (
        f"{top.provenance.observation_id}:"
        f"{bottom.provenance.observation_id}"
    )
    evidence_id = ObservationId(
        f"fixture_photo_edge_evidence:{identity_prefix}"
    )
    top_fragment_id = ObservationId(
        f"fixture_top_fragment:{top.provenance.observation_id}"
    )
    bottom_fragment_id = ObservationId(
        f"fixture_bottom_fragment:{bottom.provenance.observation_id}"
    )
    top_observations = _observations(top, str(top_fragment_id))
    bottom_observations = _observations(bottom, str(bottom_fragment_id))
    all_observations = (*top_observations, *bottom_observations)
    long_extent = max(
        1,
        int(
            round(
                max(
                    observation.long_axis_footprint.maximum
                    for observation in all_observations
                )
            )
        ),
    )
    short_extent = max(
        1,
        int(
            round(
                max(top.position.maximum, bottom.position.maximum) + 1.0
            )
        ),
    )
    label = PhotoEdgePhysicalLabel(None, None, FRAME_SIZE)
    compatible = bool(
        bottom_intercept > top_intercept
        and abs(top_slope - bottom_slope) <= 1e-9
    )
    hypothesis_id = ObservationId(
        f"fixture_photo_edge_hypothesis:{identity_prefix}"
    )
    if compatible:
        cell = PhotoEdgeLineRegionCell(
            source_cell_signature=sha256(
                identity_prefix.encode("utf-8")
            ).hexdigest(),
            pixel_slope=NumericInterval.exact(top_slope),
            top_intercept_px=NumericInterval.exact(top_intercept),
            bottom_intercept_px=NumericInterval.exact(bottom_intercept),
            possible_physical_labels=(label,),
            verified_witnesses=(
                PhotoEdgeLineWitness(
                    pixel_slope=top_slope,
                    top_intercept_px=top_intercept,
                    bottom_intercept_px=bottom_intercept,
                    top_intercept_feasible_px=NumericInterval.exact(
                        top_intercept
                    ),
                    bottom_intercept_feasible_px=NumericInterval.exact(
                        bottom_intercept
                    ),
                    physical_label=label,
                ),
            ),
            active_constraint_ids=tuple(
                observation.observation_id
                for observation in all_observations
            ),
        )
        geometry = PhotoEdgePairGeometry(
            cells=(cell,),
            normal_region=None,
            work_long_axis_extent_px=long_extent,
            work_short_axis_extent_px=short_extent,
            interpolation_position_uncertainty_px=0.0,
            coordinate_space=PhotoEdgeCoordinateSpace.SOURCE,
            numerically_indeterminate=False,
        )
        state = EvidenceState.SUPPORTED
        facts: tuple[PhotoEdgeFact, ...] = ()
        labels = (label,)
    else:
        geometry = None
        state = EvidenceState.CONTRADICTED
        facts = (PhotoEdgeFact.PAIR_GEOMETRY_CONTRADICTED,)
        labels = ()
    hypothesis = PhotoEdgePairHypothesis(
        observation_id=hypothesis_id,
        top_fragment_ids=(top_fragment_id,),
        bottom_fragment_ids=(bottom_fragment_id,),
        geometry=geometry,
        physical_labels=labels,
        state=state,
        facts=facts,
        provenance=MeasurementProvenance(
            root_measurement=MeasurementIdentity.PHOTO_EDGES,
            observation_id=hypothesis_id,
            dependencies=(MeasurementIdentity.GRAY_WORK,),
            description="typed current photo-edge pair hypothesis fixture",
            boundary_anchors=(top_fragment_id, bottom_fragment_id),
        ),
    )
    provenance = MeasurementProvenance(
        root_measurement=MeasurementIdentity.PHOTO_EDGES,
        observation_id=evidence_id,
        dependencies=(MeasurementIdentity.GRAY_WORK,),
        description="typed source-coordinate photo-edge pair fixture",
        boundary_anchors=tuple(
            observation.observation_id for observation in all_observations
        ),
    )
    return PhotoEdgePairEvidence(
        source_sha256=SOURCE_SHA256,
        search_corridors=(),
        measurement_summary=PhotoEdgeMeasurementSummary(
            raw_anchor_count=6,
            supported_transition_count=6,
            neutral_anchor_count=0,
            censored_component_count=0,
            merged_duplicate_count=0,
            fragment_count=2,
            canonical_observation_count=6,
            chunk_size_px=1024,
            peak_temporary_buffer_bytes=0,
        ),
        fragment_summaries=(
            _fragment_summary(top_fragment_id, top_observations),
            _fragment_summary(bottom_fragment_id, bottom_observations),
        ),
        audit_observations=all_observations,
        hypotheses=(hypothesis,),
        selected_pair_id=hypothesis_id if compatible else None,
        physical_selection=(
            PhotoEdgePhysicalSelection.from_label(label)
            if compatible
            else None
        ),
        state=state,
        facts=facts,
        coordinate_space=PhotoEdgeCoordinateSpace.SOURCE,
        provenance=provenance,
    )


def unavailable_photo_edge_pair_fixture(
    name: str = "fixture_unavailable_photo_edge_evidence",
) -> PhotoEdgePairEvidence:
    observation_id = ObservationId(name)
    return PhotoEdgePairEvidence(
        source_sha256=SOURCE_SHA256,
        search_corridors=(),
        measurement_summary=PhotoEdgeMeasurementSummary(
            raw_anchor_count=0,
            supported_transition_count=0,
            neutral_anchor_count=0,
            censored_component_count=0,
            merged_duplicate_count=0,
            fragment_count=0,
            canonical_observation_count=0,
            chunk_size_px=1024,
            peak_temporary_buffer_bytes=0,
        ),
        fragment_summaries=(),
        audit_observations=(),
        hypotheses=(),
        selected_pair_id=None,
        physical_selection=None,
        state=EvidenceState.UNAVAILABLE,
        facts=(PhotoEdgeFact.OBSERVATIONS_UNAVAILABLE,),
        coordinate_space=PhotoEdgeCoordinateSpace.SOURCE,
        provenance=MeasurementProvenance(
            root_measurement=MeasurementIdentity.PHOTO_EDGES,
            observation_id=observation_id,
            dependencies=(MeasurementIdentity.GRAY_WORK,),
            description="typed unavailable photo-edge test fixture",
        ),
    )


def shared_short_axis_fixture_from_edges(
    top: GrayBoundaryPathObservation,
    bottom: GrayBoundaryPathObservation,
) -> SharedShortAxisPlan:
    evidence = photo_edge_pair_fixture(top, bottom)
    common = top.orthogonal_extent.intersection(bottom.orthogonal_extent)
    long_extent = int(round(common.maximum)) if common is not None else 1
    short_extent = max(
        1,
        int(round(max(top.position.maximum, bottom.position.maximum) + 1.0)),
    )
    return shared_short_axis_from_photo_edge_pair(
        evidence,
        _identity_transform(max(1, long_extent), short_extent),
        max(1, long_extent),
        SHARED_PARAMETERS,
    )


def shared_short_axis_fixture(
    search_scope: FrameSequenceSearchScope,
) -> SharedShortAxisPlan:
    paths = tuple(
        path
        for path in search_scope.raw_boundary_paths
        if path.axis == BoundaryAxis.SHORT
        and path.kind != BoundaryKind.EDGE_ADJACENT_TRANSITION
    )
    ordered = tuple(
        sorted(
            paths,
            key=lambda path: (
                path.position.midpoint,
                str(path.provenance.observation_id),
            ),
        )
    )
    pairs = tuple(
        (top, bottom)
        for index, top in enumerate(ordered)
        for bottom in ordered[index + 1 :]
        if bottom.position.minimum > top.position.maximum
    )
    equivalent = bool(
        pairs
        and all(
            left[0].position.intersection(right[0].position) is not None
            and left[1].position.intersection(right[1].position) is not None
            for index, left in enumerate(pairs)
            for right in pairs[index + 1 :]
        )
    )
    if len(pairs) == 1 or equivalent:
        return shared_short_axis_fixture_from_edges(*pairs[0])
    evidence = unavailable_photo_edge_pair_fixture()
    return shared_short_axis_from_photo_edge_pair(
        evidence,
        _identity_transform(1, 1),
        1,
        SHARED_PARAMETERS,
    )
