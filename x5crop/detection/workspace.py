from __future__ import annotations

from dataclasses import dataclass, field
from math import atan, degrees
from statistics import median

import numpy as np

from ..cache import MeasurementCache, MeasurementCacheStatistics
from ..cache.analysis import make_measurement_cache
from ..configuration.model import DetectionConfiguration
from ..configuration.scan_canvas import ScanCanvasDetectionConfiguration
from ..configuration.transform import TransformDetectionParameters
from ..domain import (
    BoundaryMeasurementSet,
    BoundarySide,
    Box,
    ContainmentFallback,
    EvidenceState,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
)
from ..geometry.affine import AffineCoordinateTransform
from ..geometry.layout import HORIZONTAL, is_horizontal_layout, work_gray
from ..image.gray import make_base_gray_u8
from ..image.statistics import (
    ImageMeasurementStatistics,
    image_measurement_statistics,
)
from ..image.transforms import (
    BILINEAR_INTERPOLATION_POSITION_UNCERTAINTY_PX,
    photometric_background_value,
    rotate_array_expand,
)
from ..image.workspace import WorkspaceIdentity, workspace_identity_for_gray
from ..io.model import ImageProfile
from ..utils import clamp_float, spatial_shape
from .evidence.photo_edges import (
    POSITION_INTERVAL_SIDE_COUNT,
    PhotoEdgePathPairProposal,
    PhotoEdgePairEvidence,
    map_photo_edge_pair_evidence,
    observe_photo_edge_pairs,
    photo_edge_search_bands,
    photo_edge_inner_line,
    translate_photo_edge_pair_evidence,
)
from .evidence.scan_canvas import (
    ScanCanvasEvidence,
    observe_scan_canvas,
)
from .evidence.transform_geometry import (
    TransformGeometryEvidence,
    TransformOutcome,
)
from .physical.boundary_detection import (
    short_axis_boundary_paths,
    short_axis_boundary_path_pairs,
)
from .physical.lane_divider import LaneDividerEvidence, measure_lane_dividers
from .physical.short_axis import (
    SharedShortAxisPlan,
    shared_short_axis_from_photo_edge_pair,
)


@dataclass(frozen=True)
class DetectionWorkspace:
    pixels: np.ndarray
    source_gray: np.ndarray
    gray: np.ndarray
    measurement_cache: MeasurementCache
    scan_canvas_evidence: ScanCanvasEvidence
    source_photo_edge_pairs: tuple[PhotoEdgePairEvidence, ...]
    mapped_photo_edge_pairs: tuple[PhotoEdgePairEvidence, ...]
    shared_short_axes: tuple[SharedShortAxisPlan, ...]
    source_lane_divider: LaneDividerEvidence | None
    lane_divider: LaneDividerEvidence | None
    transform_geometry: TransformGeometryEvidence
    identity: WorkspaceIdentity = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.pixels, np.ndarray):
            raise TypeError("detection workspace pixels must be an array")
        if (
            not isinstance(self.source_gray, np.ndarray)
            or self.source_gray.ndim != 2
            or not isinstance(self.gray, np.ndarray)
            or self.gray.ndim != 2
        ):
            raise ValueError("detection workspace gray images must be two-dimensional")
        transform = self.transform_geometry.coordinate_transform
        pixel_height, pixel_width = spatial_shape(self.pixels)
        if (pixel_width, pixel_height) != (
            transform.output_extent.width,
            transform.output_extent.height,
        ):
            raise ValueError("workspace pixels must match the transform output extent")
        if self.gray.shape != (
            transform.output_extent.height,
            transform.output_extent.width,
        ):
            raise ValueError("workspace gray must match the transform output extent")
        if self.source_gray.shape != (
            transform.source_extent.height,
            transform.source_extent.width,
        ):
            raise ValueError("source gray must match the transform source extent")
        if not (
            len(self.source_photo_edge_pairs)
            == len(self.mapped_photo_edge_pairs)
            == len(self.shared_short_axes)
        ):
            raise ValueError(
                "source, mapped, and shared short-axis evidence must correspond"
            )
        if (self.source_lane_divider is None) != (self.lane_divider is None):
            raise ValueError("source and workspace lane divider must correspond")
        source_work = work_gray(
            self.source_gray,
            self.measurement_cache.layout,
        )
        workspace_work = work_gray(
            self.gray,
            self.measurement_cache.layout,
        )
        if (
            self.scan_canvas_evidence.observed_long_axis_px
            != source_work.shape[1]
            or self.scan_canvas_evidence.observed_short_axis_px
            != source_work.shape[0]
        ):
            raise ValueError(
                "scan-canvas evidence must describe the source work domain"
            )
        for label, evidence_set, work in (
            ("source", self.source_photo_edge_pairs, source_work),
            ("workspace", self.mapped_photo_edge_pairs, workspace_work),
        ):
            for evidence in evidence_set:
                for candidate in evidence.candidates:
                    for sample in candidate.path.samples:
                        if (
                            sample.orthogonal_interval.minimum < 0.0
                            or sample.orthogonal_interval.maximum
                            > float(work.shape[1])
                            or sample.position.minimum < 0.0
                            or sample.position.maximum > float(work.shape[0])
                        ):
                            raise ValueError(
                                f"{label} photo-edge sample lies outside its coordinate domain"
                            )
        for plan, evidence in zip(
            self.shared_short_axes,
            self.mapped_photo_edge_pairs,
            strict=True,
        ):
            if plan.photo_edge_pair_id != evidence.observation_id:
                raise ValueError(
                    "shared short axis must reference mapped photo-edge evidence"
                )
            if plan.span is not None and (
                plan.top.minimum < 0.0
                or plan.bottom.maximum > float(workspace_work.shape[0])
            ):
                raise ValueError(
                    "workspace short-axis plan lies outside its coordinate domain"
                )
        for label, divider, work in (
            ("source", self.source_lane_divider, source_work),
            ("workspace", self.lane_divider, workspace_work),
        ):
            if divider is not None and not (
                0 <= divider.gutter.left < divider.gutter.right <= work.shape[1]
                and 0 <= divider.gutter.top < divider.gutter.bottom <= work.shape[0]
            ):
                raise ValueError(
                    f"{label} lane divider lies outside its coordinate domain"
                )
        if transform.is_identity:
            if not np.array_equal(self.source_gray, self.gray):
                raise ValueError("identity workspace must reuse source gray")
            if self.source_lane_divider != self.lane_divider:
                raise ValueError("identity workspace must reuse source lane divider")
        elif not self.source_photo_edge_pairs:
            raise ValueError(
                "applied transform requires source photo-edge evidence"
            )
        for source, mapped in zip(
            self.source_photo_edge_pairs,
            self.mapped_photo_edge_pairs,
            strict=True,
        ):
            if mapped.provenance.observation_id != ObservationId(
                f"workspace:{source.provenance.observation_id}"
            ):
                raise ValueError(
                    "mapped photo-edge evidence must preserve source identity"
                )
            if mapped.search_bands:
                raise ValueError(
                    "mapped photo-edge evidence cannot retain source-coordinate bands"
                )
            if mapped.physical_selection != source.physical_selection:
                raise ValueError(
                    "mapped photo-edge evidence must preserve physical selection"
                )
            if len(source.candidates) != len(mapped.candidates):
                raise ValueError(
                    "mapped photo-edge evidence must preserve every candidate"
                )
            for source_candidate, mapped_candidate in zip(
                source.candidates,
                mapped.candidates,
                strict=True,
            ):
                if (
                    mapped_candidate.path.provenance.observation_id
                    != ObservationId(
                        "workspace:"
                        f"{source_candidate.path.provenance.observation_id}"
                    )
                ):
                    raise ValueError(
                        "mapped photo-edge candidate must preserve raw path identity"
                    )
        if not transform.is_identity and self.source_lane_divider is not None:
            assert self.lane_divider is not None
            if self.lane_divider.provenance.observation_id != ObservationId(
                f"workspace:{self.source_lane_divider.provenance.observation_id}"
            ):
                raise ValueError(
                    "mapped lane divider must preserve source identity"
                )
        if not np.array_equal(
            self.measurement_cache.gray_work,
            work_gray(self.gray, self.measurement_cache.layout),
        ):
            raise ValueError("detection workspace cache must use canonical gray")
        object.__setattr__(self, "identity", workspace_identity_for_gray(self.gray))


def _measure_photo_edges(
    gray_work: np.ndarray,
    statistics: ImageMeasurementStatistics,
    configuration: DetectionConfiguration,
    *,
    observation_id: str,
    scan_canvas: ScanCanvasEvidence | None,
) -> PhotoEdgePairEvidence:
    if scan_canvas is None:
        paths = short_axis_boundary_paths(
            gray_work,
            statistics,
            configuration.photo_edges.path_sampling,
            minimum_path_samples=(
                configuration.photo_edges.minimum_candidate_sections
            ),
            observation_prefix=observation_id,
        )
        search_bands = ()
        path_pair_proposals = None
    else:
        search_bands = photo_edge_search_bands(
            scan_canvas,
            configuration.physical_spec.frame.frame_size_mm_options,
            configuration.photo_edges,
            configuration.transform.maximum_angle_degrees,
        )
        measured_pairs = (
            short_axis_boundary_path_pairs(
                gray_work,
                statistics,
                configuration.photo_edges.path_sampling,
                minimum_path_samples=(
                    configuration.photo_edges.minimum_candidate_sections
                ),
                matching_constraint_ids=(
                    lambda coordinate, top_position, bottom_position: tuple(
                        band.band_id
                        for band in search_bands
                        if band.allows_pair(
                            coordinate,
                            top_position,
                            bottom_position,
                        )
                    )
                ),
                observation_prefix=observation_id,
            )
            if search_bands
            else ()
        )
        paths_by_id = {
            path.provenance.observation_id: path
            for pair in measured_pairs
            for path in (pair.top_path, pair.bottom_path)
        }
        paths = tuple(
            paths_by_id[observation_id]
            for observation_id in sorted(paths_by_id, key=str)
        )
        path_pair_proposals = tuple(
            PhotoEdgePathPairProposal(
                pair.top_path.provenance.observation_id,
                pair.bottom_path.provenance.observation_id,
                pair.constraint_id,
            )
            for pair in measured_pairs
        )
    measured = BoundaryMeasurementSet(
        raw_paths=paths,
        holder_boundaries=(),
        containment_fallback=ContainmentFallback(
            Box(0, 0, gray_work.shape[1], gray_work.shape[0]),
            MeasurementProvenance(
                root_measurement=MeasurementIdentity.CANVAS,
                observation_id=ObservationId(
                    f"{observation_id}:canvas"
                ),
                dependencies=(MeasurementIdentity.GRAY_WORK,),
                description="photo-edge observation-domain containment",
            ),
        ),
    )
    return observe_photo_edge_pairs(
        gray_work,
        measured,
        configuration.photo_edges,
        observation_id=observation_id,
        search_bands=search_bands,
        path_pair_proposals=path_pair_proposals,
    )


def _source_photo_edge_pairs(
    source_cache: MeasurementCache,
    scan_canvas: ScanCanvasEvidence,
    configuration: DetectionConfiguration,
    lane_configuration: DetectionConfiguration | None,
) -> tuple[tuple[PhotoEdgePairEvidence, ...], LaneDividerEvidence | None]:
    if configuration.physical_spec.layout.kind != "dual_lane":
        return (
            (
                _measure_photo_edges(
                    source_cache.gray_work,
                    source_cache.image_statistics,
                    configuration,
                    observation_id="source_photo_edge_pair_evidence",
                    scan_canvas=scan_canvas,
                ),
            ),
            None,
        )
    if lane_configuration is None:
        return (), None
    divider_set = measure_lane_dividers(
        source_cache.content_evidence_float_work,
        configuration.candidate_plan.dual_lane_divider,
    )
    supported = tuple(
        divider
        for divider in divider_set.candidates
        if divider.state == EvidenceState.SUPPORTED
    )
    if len(supported) != 1:
        return (), None
    divider = supported[0]
    evidence_set: list[PhotoEdgePairEvidence] = []
    for lane_index, lane in enumerate(
        divider.lane_boxes(
            source_cache.gray_work.shape[1],
            source_cache.gray_work.shape[0],
        ),
        start=1,
    ):
        lane_gray = source_cache.gray_work[
            lane.top : lane.bottom,
            lane.left : lane.right,
        ]
        lane_statistics = image_measurement_statistics(
            lane_gray,
            lane_configuration.preprocess.image_statistics,
        )
        local = _measure_photo_edges(
            lane_gray,
            lane_statistics,
            lane_configuration,
            observation_id=f"source_lane_{lane_index}_photo_edge_pair_evidence",
            scan_canvas=None,
        )
        evidence_set.append(
            translate_photo_edge_pair_evidence(
                local,
                lane.top,
            )
        )
    return tuple(evidence_set), divider


def _unapplied_transform_evidence(
    outcome: TransformOutcome,
    transform: AffineCoordinateTransform,
    *,
    estimated_angle_degrees: float | None = None,
    projected_edge_drift_px: float | None = None,
    identity_drift_threshold_px: float | None = None,
) -> TransformGeometryEvidence:
    return TransformGeometryEvidence(
        outcome=outcome,
        estimated_angle_degrees=estimated_angle_degrees,
        projected_edge_drift_px=projected_edge_drift_px,
        identity_drift_threshold_px=identity_drift_threshold_px,
        position_uncertainty_px=0.0,
        coordinate_transform=transform,
    )


def _transform_geometry(
    evidence_set: tuple[PhotoEdgePairEvidence, ...],
    source_work_width: int,
    source_width: int,
    source_height: int,
    layout: str,
    parameters: TransformDetectionParameters,
) -> TransformGeometryEvidence:
    identity = AffineCoordinateTransform.identity(source_width, source_height)
    if not evidence_set or any(
        evidence.state != EvidenceState.SUPPORTED
        or evidence.selected_candidates is None
        for evidence in evidence_set
    ):
        return _unapplied_transform_evidence(
            TransformOutcome.PHOTO_EDGE_PAIR_UNAVAILABLE,
            identity,
        )
    pair_lines = tuple(
        (
            photo_edge_inner_line(top, BoundarySide.TOP),
            photo_edge_inner_line(bottom, BoundarySide.BOTTOM),
            evidence.selected_pair,
        )
        for evidence in evidence_set
        for selected in (evidence.selected_candidates,)
        if selected is not None
        for top, bottom in (selected,)
    )
    lane_slopes = tuple(
        float(median((top.slope, bottom.slope)))
        for top, bottom, _ in pair_lines
    )
    if (
        len(lane_slopes) > 1
        and max(lane_slopes) - min(lane_slopes)
        > parameters.maximum_lane_slope_delta
    ):
        return _unapplied_transform_evidence(
            TransformOutcome.EDGE_SLOPES_DISAGREE,
            identity,
        )
    projected_uncertainties = []
    for top, bottom, hypothesis in pair_lines:
        assert hypothesis is not None
        assert hypothesis.photo_height_px is not None
        projected_uncertainty = max(
            (
                line.slope_interval.maximum
                - line.slope_interval.minimum
            )
            * float(source_work_width)
            + POSITION_INTERVAL_SIDE_COUNT * line.position_uncertainty_px
            for line in (top, bottom)
        )
        projected_uncertainties.append(projected_uncertainty)
        if projected_uncertainty > (
            hypothesis.photo_height_px.midpoint
            * parameters.maximum_projected_uncertainty_height_ratio
        ):
            return _unapplied_transform_evidence(
                TransformOutcome.ANGLE_ESTIMATION_UNAVAILABLE,
                identity,
            )
    slopes = tuple(
        line.slope
        for top, bottom, _ in pair_lines
        for line in (top, bottom)
    )
    work_slope = float(median(slopes))
    work_angle = degrees(atan(work_slope))
    estimated_angle = work_angle if is_horizontal_layout(layout) else -work_angle
    projected_drift = abs(work_slope * float(source_work_width))
    identity_drift_threshold = clamp_float(
        source_work_width * parameters.identity_span_ratio,
        parameters.identity_span_min_px,
        parameters.identity_span_max_px,
    )
    if abs(estimated_angle) > parameters.maximum_angle_degrees:
        return _unapplied_transform_evidence(
            TransformOutcome.ANGLE_OUT_OF_RANGE,
            identity,
        )
    if projected_drift <= identity_drift_threshold:
        return _unapplied_transform_evidence(
            TransformOutcome.IDENTITY_WITHIN_TOLERANCE,
            identity,
            estimated_angle_degrees=estimated_angle,
            projected_edge_drift_px=projected_drift,
            identity_drift_threshold_px=identity_drift_threshold,
        )
    line_uncertainty = max(
        line.position_uncertainty_px
        for top, bottom, _ in pair_lines
        for line in (top, bottom)
    )
    return TransformGeometryEvidence(
        outcome=TransformOutcome.DESKEW_APPLIED,
        estimated_angle_degrees=estimated_angle,
        projected_edge_drift_px=projected_drift,
        identity_drift_threshold_px=identity_drift_threshold,
        position_uncertainty_px=(
            BILINEAR_INTERPOLATION_POSITION_UNCERTAINTY_PX
            + line_uncertainty
        ),
        coordinate_transform=AffineCoordinateTransform.expanded_rotation(
            source_width,
            source_height,
            -estimated_angle,
        ),
    )


def _map_work_intervals(
    transform: AffineCoordinateTransform,
    layout: str,
    orthogonal: PixelInterval,
    position: PixelInterval,
) -> tuple[PixelInterval, PixelInterval]:
    if is_horizontal_layout(layout):
        return transform.map_intervals(orthogonal, position)
    mapped_source_x, mapped_source_y = transform.map_intervals(
        position,
        orthogonal,
    )
    return mapped_source_y, mapped_source_x


def _mapped_lane_divider(
    divider: LaneDividerEvidence | None,
    evidence: TransformGeometryEvidence,
    layout: str,
    output_work_width: int,
    output_work_height: int,
) -> LaneDividerEvidence | None:
    if divider is None or not evidence.applied:
        return divider
    source_work_width = (
        evidence.coordinate_transform.source_extent.width
        if is_horizontal_layout(layout)
        else evidence.coordinate_transform.source_extent.height
    )
    _, center_position = _map_work_intervals(
        evidence.coordinate_transform,
        layout,
        PixelInterval(0.0, float(source_work_width)),
        PixelInterval.exact(float(divider.center)),
    )
    source_gutter = (
        divider.gutter
        if is_horizontal_layout(layout)
        else Box(
            divider.gutter.top,
            divider.gutter.left,
            divider.gutter.bottom,
            divider.gutter.right,
        )
    )
    mapped_source_gutter = evidence.coordinate_transform.map_box(source_gutter)
    mapped_work_gutter = (
        mapped_source_gutter
        if is_horizontal_layout(layout)
        else Box(
            mapped_source_gutter.top,
            mapped_source_gutter.left,
            mapped_source_gutter.bottom,
            mapped_source_gutter.right,
        )
    )
    gutter = Box(
        max(0, mapped_work_gutter.left),
        max(0, mapped_work_gutter.top),
        min(output_work_width, mapped_work_gutter.right),
        min(output_work_height, mapped_work_gutter.bottom),
    )
    center = max(
        gutter.top,
        min(gutter.bottom - 1, round(center_position.midpoint)),
    )
    provenance = MeasurementProvenance(
        root_measurement=MeasurementIdentity.LANE_DIVIDER_PROFILE,
        observation_id=ObservationId(
            f"workspace:{divider.provenance.observation_id}"
        ),
        dependencies=tuple(
            dict.fromkeys(
                (
                    *divider.provenance.dependencies,
                    MeasurementIdentity.WORKSPACE_TRANSFORM,
                )
            )
        ),
        description="coordinate-mapped lane divider",
        boundary_anchors=(divider.provenance.observation_id,),
    )
    return LaneDividerEvidence(
        center=center,
        gutter=gutter,
        normalized_gutter_residual=divider.normalized_gutter_residual,
        normalized_lane_residuals=divider.normalized_lane_residuals,
        provenance=provenance,
    )


def prepare_detection_workspace(
    pixels: np.ndarray,
    profile: ImageProfile,
    layout: str,
    configuration: DetectionConfiguration,
    lane_configuration: DetectionConfiguration | None,
    lookup_statistics: MeasurementCacheStatistics,
) -> DetectionWorkspace:
    source_gray = make_base_gray_u8(
        pixels,
        profile.axes,
        profile.photometric,
        configuration.preprocess.base_gray,
    )
    source_statistics = image_measurement_statistics(
        work_gray(source_gray, layout),
        configuration.preprocess.image_statistics,
    )
    source_cache = make_measurement_cache(
        source_gray,
        layout,
        source_statistics,
        0.0,
        lookup_statistics,
    )
    scan_canvas_evidence = observe_scan_canvas(
        source_cache.gray_work.shape[1],
        source_cache.gray_work.shape[0],
        layout,
        configuration.scan_canvas,
    )
    source_photo_edges, source_divider = _source_photo_edge_pairs(
        source_cache,
        scan_canvas_evidence,
        configuration,
        lane_configuration,
    )
    source_height, source_width = spatial_shape(pixels)
    transform_geometry = _transform_geometry(
        source_photo_edges,
        source_cache.gray_work.shape[1],
        source_width,
        source_height,
        layout,
        configuration.transform,
    )
    if transform_geometry.applied:
        assert transform_geometry.applied_angle_degrees is not None
        transformed_pixels, transform = rotate_array_expand(
            pixels,
            transform_geometry.applied_angle_degrees,
            profile.axes,
            background_value=photometric_background_value(
                pixels,
                profile.photometric,
            ),
        )
        if transform != transform_geometry.coordinate_transform:
            raise ValueError("pixel rotation and coordinate mapping must be identical")
        gray = make_base_gray_u8(
            transformed_pixels,
            profile.axes,
            profile.photometric,
            configuration.preprocess.base_gray,
        )
        statistics = image_measurement_statistics(
            work_gray(gray, layout),
            configuration.preprocess.image_statistics,
        )
        cache = make_measurement_cache(
            gray,
            layout,
            statistics,
            transform_geometry.position_uncertainty_px,
            lookup_statistics,
        )
    else:
        transformed_pixels = pixels
        gray = source_gray
        cache = source_cache
    mapped_photo_edges = tuple(
        map_photo_edge_pair_evidence(
            evidence,
            transform_geometry.coordinate_transform,
            layout,
            transform_geometry.position_uncertainty_px,
        )
        for evidence in source_photo_edges
    )
    shared_short_axes = tuple(
        shared_short_axis_from_photo_edge_pair(
            evidence,
            cache.gray_work.shape[1],
            (
                lane_configuration.photo_edges
                if lane_configuration is not None
                and configuration.physical_spec.layout.kind == "dual_lane"
                else configuration.photo_edges
            ),
        )
        for evidence in mapped_photo_edges
    )
    divider = _mapped_lane_divider(
        source_divider,
        transform_geometry,
        layout,
        cache.gray_work.shape[1],
        cache.gray_work.shape[0],
    )
    return DetectionWorkspace(
        pixels=transformed_pixels,
        source_gray=source_gray,
        gray=gray,
        measurement_cache=cache,
        scan_canvas_evidence=scan_canvas_evidence,
        source_photo_edge_pairs=source_photo_edges,
        mapped_photo_edge_pairs=mapped_photo_edges,
        shared_short_axes=shared_short_axes,
        source_lane_divider=source_divider,
        lane_divider=divider,
        transform_geometry=transform_geometry,
    )


def detection_workspace_region(
    workspace: DetectionWorkspace,
    region: Box,
    shared_short_axis: SharedShortAxisPlan,
    configuration: DetectionConfiguration,
) -> DetectionWorkspace:
    try:
        index = workspace.shared_short_axes.index(shared_short_axis)
    except ValueError as exc:
        raise ValueError(
            "regional workspace requires an owned shared short axis"
        ) from exc
    gray = workspace.measurement_cache.gray_work[
        region.top : region.bottom,
        region.left : region.right,
    ]
    local_source_evidence = translate_photo_edge_pair_evidence(
        workspace.mapped_photo_edge_pairs[index],
        -region.top,
    )
    statistics = image_measurement_statistics(
        gray,
        configuration.preprocess.image_statistics,
    )
    cache = make_measurement_cache(
        gray,
        HORIZONTAL,
        statistics,
        workspace.transform_geometry.position_uncertainty_px,
        workspace.measurement_cache.lookup_statistics,
    )
    identity = AffineCoordinateTransform.identity(region.width, region.height)
    local_mapped_evidence = map_photo_edge_pair_evidence(
        local_source_evidence,
        identity,
        HORIZONTAL,
        0.0,
    )
    local_plan = shared_short_axis_from_photo_edge_pair(
        local_mapped_evidence,
        region.width,
        configuration.photo_edges,
    )
    local_transform = TransformGeometryEvidence(
        outcome=TransformOutcome.IDENTITY_WITHIN_TOLERANCE,
        estimated_angle_degrees=0.0,
        projected_edge_drift_px=0.0,
        identity_drift_threshold_px=1.0,
        position_uncertainty_px=0.0,
        coordinate_transform=identity,
    )
    local_scan_canvas = observe_scan_canvas(
        region.width,
        region.height,
        HORIZONTAL,
        ScanCanvasDetectionConfiguration(()),
    )
    return DetectionWorkspace(
        pixels=gray,
        source_gray=gray,
        gray=gray,
        measurement_cache=cache,
        scan_canvas_evidence=local_scan_canvas,
        source_photo_edge_pairs=(local_source_evidence,),
        mapped_photo_edge_pairs=(local_mapped_evidence,),
        shared_short_axes=(local_plan,),
        source_lane_divider=None,
        lane_divider=None,
        transform_geometry=local_transform,
    )
