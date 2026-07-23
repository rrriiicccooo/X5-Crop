from __future__ import annotations

from dataclasses import replace

from x5crop.configuration.photo_edges import PhotoEdgeDetectionParameters
from x5crop.detection.evidence.photo_edges import (
    PhotoBandEvidence,
    PhotoEdgeCandidate,
    PhotoEdgeFact,
    PhotoEdgeLocalEvidence,
    PhotoEdgePairEvidence,
    PhotoEdgeWindowState,
    SlopeInterval,
    _hypothesis,
    _robust_fit,
)
from x5crop.detection.physical.short_axis import (
    SharedShortAxisPlan,
    shared_short_axis_from_photo_edge_pair,
)
from x5crop.domain import (
    BoundaryAxis,
    BoundaryKind,
    BoundaryPathSample,
    EvidenceState,
    FrameSequenceSearchScope,
    GrayBoundaryPathObservation,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
)


PARAMETERS = PhotoEdgeDetectionParameters()
FIXTURE_PARAMETERS = replace(
    PARAMETERS,
    maximum_shared_axis_uncertainty_ratio=1.0,
    shared_axis_uncertainty_floor_px=100.0,
)


def _distributed_path(
    path: GrayBoundaryPathObservation,
) -> GrayBoundaryPathObservation:
    if len(path.samples) >= FIXTURE_PARAMETERS.minimum_fit_inliers:
        return path
    extent = path.orthogonal_extent
    length = extent.maximum - extent.minimum
    if length <= 0.0:
        raise ValueError("photo-edge fixture path requires a non-empty domain")
    coordinates = tuple(
        sample.orthogonal_interval.midpoint for sample in path.samples
    )
    positions = tuple(sample.position.midpoint for sample in path.samples)
    coordinate_center = sum(coordinates) / float(len(coordinates))
    position_center = sum(positions) / float(len(positions))
    denominator = sum(
        (coordinate - coordinate_center) ** 2 for coordinate in coordinates
    )
    slope = (
        0.0
        if denominator <= 0.0
        else sum(
            (coordinate - coordinate_center) * (position - position_center)
            for coordinate, position in zip(coordinates, positions, strict=True)
        )
        / denominator
    )
    count = FIXTURE_PARAMETERS.minimum_fit_inliers
    samples = tuple(
        BoundaryPathSample(
            orthogonal_interval=type(extent)(
                extent.minimum + length * index / count,
                extent.minimum + length * (index + 1) / count,
            ),
            position=type(path.position).exact(
                position_center
                + slope
                * (
                    extent.minimum
                    + length * (index + 0.5) / count
                    - coordinate_center
                )
            ),
        )
        for index in range(count)
    )
    return replace(path, samples=samples)


def _candidate(path: GrayBoundaryPathObservation) -> PhotoEdgeCandidate:
    was_densified = len(path.samples) < FIXTURE_PARAMETERS.minimum_fit_inliers
    path = _distributed_path(path)
    fit = _robust_fit(path, FIXTURE_PARAMETERS)
    if was_densified:
        fit = replace(
            fit,
            slope_interval=SlopeInterval(fit.slope, fit.slope),
            position_uncertainty_px=0.0,
            residual_mad_px=0.0,
        )
    provenance = MeasurementProvenance(
        MeasurementIdentity.PHOTO_EDGES,
        ObservationId(f"fixture_candidate:{path.provenance.observation_id}"),
        (
            MeasurementIdentity.BOUNDARY_PATHS,
            MeasurementIdentity.GRAY_WORK,
        ),
        "typed photo-edge test fixture",
        (path.provenance.observation_id,),
    )
    return PhotoEdgeCandidate(
        path=path,
        fit=fit,
        local_evidence=tuple(
            PhotoEdgeLocalEvidence(
                sample_index=index,
                state=PhotoEdgeWindowState.SUPPORTED,
                intensity_effect=4.0,
                texture_effect=4.0,
                gradient_effect=4.0,
            )
            for index in range(len(path.samples))
        ),
        physical_band_ids=(),
        state=EvidenceState.SUPPORTED,
        facts=(),
        provenance=provenance,
    )


def photo_edge_pair_fixture(
    top: GrayBoundaryPathObservation,
    bottom: GrayBoundaryPathObservation,
    *,
    photo_band_support_depth_px: float = 1.0,
) -> PhotoEdgePairEvidence:
    if (
        top.axis != BoundaryAxis.SHORT
        or bottom.axis != BoundaryAxis.SHORT
        or top.kind == BoundaryKind.EDGE_ADJACENT_TRANSITION
        or bottom.kind == BoundaryKind.EDGE_ADJACENT_TRANSITION
    ):
        raise ValueError(
            "photo-edge fixture requires independently observed short-axis paths"
        )
    top_candidate = _candidate(top)
    bottom_candidate = _candidate(bottom)
    hypothesis = _hypothesis(
        top_candidate,
        bottom_candidate,
        (),
        FIXTURE_PARAMETERS,
        photo_band_support_depth_px,
        PhotoBandEvidence(
            top_supported_window_count=(
                FIXTURE_PARAMETERS.minimum_supported_windows
            ),
            top_support_distribution_bins=(
                FIXTURE_PARAMETERS.minimum_support_distribution_bins
            ),
            bottom_supported_window_count=(
                FIXTURE_PARAMETERS.minimum_supported_windows
            ),
            bottom_support_distribution_bins=(
                FIXTURE_PARAMETERS.minimum_support_distribution_bins
            ),
            state=EvidenceState.SUPPORTED,
        ),
    )
    provenance = MeasurementProvenance(
        MeasurementIdentity.PHOTO_EDGES,
        ObservationId(
            "fixture_photo_edge_evidence:"
            f"{top.provenance.observation_id}:"
            f"{bottom.provenance.observation_id}"
        ),
        (
            MeasurementIdentity.BOUNDARY_PATHS,
            MeasurementIdentity.GRAY_WORK,
        ),
        "typed source-coordinate photo-edge pair fixture",
        (
            top.provenance.observation_id,
            bottom.provenance.observation_id,
        ),
    )
    supported = hypothesis.state == EvidenceState.SUPPORTED
    return PhotoEdgePairEvidence(
        candidates=(top_candidate, bottom_candidate),
        candidate_summaries=(),
        search_bands=(),
        hypotheses=(hypothesis,),
        selected_pair_id=hypothesis.observation_id if supported else None,
        physical_selection=None,
        state=hypothesis.state,
        facts=(
            ()
            if supported
            else hypothesis.facts
            or (PhotoEdgeFact.PAIR_GEOMETRY_CONTRADICTED,)
        ),
        provenance=provenance,
    )


def unavailable_photo_edge_pair_fixture(
    name: str = "fixture_unavailable_photo_edge_evidence",
) -> PhotoEdgePairEvidence:
    return PhotoEdgePairEvidence(
        candidates=(),
        candidate_summaries=(),
        search_bands=(),
        hypotheses=(),
        selected_pair_id=None,
        physical_selection=None,
        state=EvidenceState.UNAVAILABLE,
        facts=(PhotoEdgeFact.PATHS_UNAVAILABLE,),
        provenance=MeasurementProvenance(
            MeasurementIdentity.PHOTO_EDGES,
            ObservationId(name),
            (
                MeasurementIdentity.BOUNDARY_PATHS,
                MeasurementIdentity.GRAY_WORK,
            ),
            "typed unavailable photo-edge test fixture",
        ),
    )


def shared_short_axis_fixture_from_edges(
    top: GrayBoundaryPathObservation,
    bottom: GrayBoundaryPathObservation,
) -> SharedShortAxisPlan:
    evidence = photo_edge_pair_fixture(top, bottom)
    common = top.orthogonal_extent.intersection(bottom.orthogonal_extent)
    long_extent = int(round(common.maximum)) if common is not None else 1
    return shared_short_axis_from_photo_edge_pair(
        evidence,
        max(1, long_extent),
        FIXTURE_PARAMETERS,
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
        1,
        FIXTURE_PARAMETERS,
    )
