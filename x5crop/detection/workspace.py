from __future__ import annotations

from dataclasses import dataclass, field
from math import atan, degrees

import numpy as np

from ..cache import MeasurementCache, MeasurementCacheStatistics
from ..cache.analysis import make_measurement_cache
from ..configuration.model import DetectionConfiguration
from ..configuration.scan_canvas import ScanCanvasDetectionConfiguration
from ..configuration.transform import TransformDetectionParameters
from ..domain import (
    Box,
    EvidenceState,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
)
from ..geometry.affine import AffineCoordinateTransform
from ..geometry.layout import HORIZONTAL, is_horizontal_layout, work_gray
from ..image.gray import make_base_gray_u8
from ..image.statistics import image_measurement_statistics
from ..image.transforms import (
    BILINEAR_INTERPOLATION_POSITION_UNCERTAINTY_PX,
    photometric_background_value,
    rotate_array_expand,
)
from ..image.workspace import WorkspaceIdentity, workspace_identity_for_gray
from ..io.model import ImageProfile
from ..utils import clamp_float, spatial_shape
from .evidence.photo_edges import (
    DualLanePhotoEdgeJointRegion,
    NumericInterval,
    PhotoEdgeCoordinateSpace,
    PhotoEdgePairEvidence,
    map_photo_edge_pair_evidence,
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
from .physical.lane_divider import LaneDividerEvidence, measure_lane_dividers
from .physical.photo_edge_detection import (
    observe_fixed_canvas_photo_edges,
    observe_image_only_lane_photo_edges,
)
from .physical.photo_edge_geometry import join_dual_lane_hypotheses
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
    dual_lane_photo_edge_geometry: DualLanePhotoEdgeJointRegion | None
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
        if self.dual_lane_photo_edge_geometry is not None:
            joint = self.dual_lane_photo_edge_geometry
            if len(self.source_photo_edge_pairs) != 2:
                raise ValueError(
                    "dual-lane joint geometry requires exactly two lane pairs"
                )
            if joint.state == EvidenceState.SUPPORTED:
                assert joint.selected_pair_ids is not None
                selected = tuple(
                    evidence.selected_pair_id
                    for evidence in self.source_photo_edge_pairs
                )
                if selected != joint.selected_pair_ids:
                    raise ValueError(
                        "dual-lane joint geometry must select the lane pairs"
                    )
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
                for observation in evidence.audit_observations:
                    if (
                        observation.long_axis_footprint.minimum < 0.0
                        or observation.long_axis_footprint.maximum
                        > float(work.shape[1])
                        or observation.short_axis_position_interval.minimum
                        < 0.0
                        or observation.short_axis_position_interval.maximum
                        > float(work.shape[0])
                    ):
                        raise ValueError(
                            f"{label} photo-edge observation lies outside "
                            "its coordinate domain"
                        )
                expected_space = (
                    PhotoEdgeCoordinateSpace.SOURCE
                    if label == "source"
                    else PhotoEdgeCoordinateSpace.MAPPED
                )
                if evidence.coordinate_space != expected_space:
                    raise ValueError(
                        f"{label} photo-edge evidence has the wrong coordinate space"
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
            if mapped.search_corridors:
                raise ValueError(
                    "mapped photo-edge evidence cannot retain source corridors"
                )
            if mapped.physical_selection != source.physical_selection:
                raise ValueError(
                    "mapped photo-edge evidence must preserve physical selection"
                )
            if len(source.hypotheses) != len(mapped.hypotheses):
                raise ValueError(
                    "mapped photo-edge evidence must preserve every hypothesis"
                )
            for source_hypothesis, mapped_hypothesis in zip(
                source.hypotheses,
                mapped.hypotheses,
                strict=True,
            ):
                if (
                    mapped_hypothesis.provenance.observation_id
                    != ObservationId(
                        "workspace:"
                        f"{source_hypothesis.provenance.observation_id}"
                    )
                ):
                    raise ValueError(
                        "mapped photo-edge hypothesis must preserve source identity"
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


def _source_photo_edge_pairs(
    source_cache: MeasurementCache,
    scan_canvas: ScanCanvasEvidence,
    configuration: DetectionConfiguration,
    lane_configuration: DetectionConfiguration | None,
    source_sha256: str,
) -> tuple[
    tuple[PhotoEdgePairEvidence, ...],
    LaneDividerEvidence | None,
    DualLanePhotoEdgeJointRegion | None,
]:
    if configuration.physical_spec.layout.kind != "dual_lane":
        return (
            (
                observe_fixed_canvas_photo_edges(
                    source_cache.gray_work,
                    scan_canvas,
                    configuration.physical_spec.frame.frame_size_mm_options,
                    configuration.photo_edges,
                    source_sha256=source_sha256,
                    observation_id="source_photo_edge_pair_evidence",
                ),
            ),
            None,
            None,
        )
    if lane_configuration is None:
        return (), None, None
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
        return (), None, None
    divider = supported[0]
    frame_sizes = (
        lane_configuration.physical_spec.frame.frame_size_mm_options
    )
    if len(frame_sizes) != 1:
        raise ValueError(
            "dual-lane image-only geometry requires one lane frame size"
        )
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
        local = observe_image_only_lane_photo_edges(
            lane_gray,
            frame_sizes[0],
            lane_configuration.photo_edges,
            source_sha256=source_sha256,
            observation_id=f"source_lane_{lane_index}_photo_edge_pair_evidence",
        )
        evidence_set.append(
            translate_photo_edge_pair_evidence(
                local,
                lane.top,
                PhotoEdgeCoordinateSpace.SOURCE,
            )
        )
    joint = join_dual_lane_hypotheses(
        evidence_set[0].hypotheses,
        evidence_set[1].hypotheses,
    )
    return tuple(evidence_set), divider, joint


def _unapplied_transform_evidence(
    outcome: TransformOutcome,
    transform: AffineCoordinateTransform,
    *,
    estimated_angle_degrees: float | None = None,
    pixel_angle_interval_degrees: NumericInterval | None = None,
    projected_edge_drift_px: float | None = None,
    identity_drift_threshold_px: float | None = None,
) -> TransformGeometryEvidence:
    return TransformGeometryEvidence(
        outcome=outcome,
        estimated_angle_degrees=estimated_angle_degrees,
        pixel_angle_interval_degrees=pixel_angle_interval_degrees,
        projected_edge_drift_px=projected_edge_drift_px,
        identity_drift_threshold_px=identity_drift_threshold_px,
        position_uncertainty_px=0.0,
        coordinate_transform=transform,
    )


def _transform_geometry(
    evidence_set: tuple[PhotoEdgePairEvidence, ...],
    dual_lane_geometry: DualLanePhotoEdgeJointRegion | None,
    source_work_width: int,
    source_width: int,
    source_height: int,
    layout: str,
    parameters: TransformDetectionParameters,
) -> TransformGeometryEvidence:
    identity = AffineCoordinateTransform.identity(source_width, source_height)
    if (
        dual_lane_geometry is not None
        and dual_lane_geometry.state != EvidenceState.SUPPORTED
    ):
        return _unapplied_transform_evidence(
            TransformOutcome.PHOTO_EDGE_PAIR_UNAVAILABLE,
            identity,
        )
    if not evidence_set or any(
        evidence.state != EvidenceState.SUPPORTED
        or evidence.selected_geometry is None
        for evidence in evidence_set
    ):
        return _unapplied_transform_evidence(
            TransformOutcome.PHOTO_EDGE_PAIR_UNAVAILABLE,
            identity,
        )
    geometries = tuple(evidence.selected_geometry for evidence in evidence_set)
    assert all(geometry is not None for geometry in geometries)
    typed_geometries = tuple(
        geometry for geometry in geometries if geometry is not None
    )
    if dual_lane_geometry is None:
        minimum_slope = max(
            geometry.pixel_slope_interval.minimum
            for geometry in typed_geometries
        )
        maximum_slope = min(
            geometry.pixel_slope_interval.maximum
            for geometry in typed_geometries
        )
    else:
        minimum_slope = min(
            cell.pixel_slope.minimum
            for cell in dual_lane_geometry.cells
        )
        maximum_slope = max(
            cell.pixel_slope.maximum
            for cell in dual_lane_geometry.cells
        )
    if maximum_slope < minimum_slope:
        return _unapplied_transform_evidence(
            TransformOutcome.ANGLE_ESTIMATION_UNAVAILABLE,
            identity,
        )
    slope_interval = NumericInterval(minimum_slope, maximum_slope)
    projected_uncertainty = (
        slope_interval.width * float(max(0, source_work_width - 1))
    )
    minimum_photo_height_px = (
        min(
            geometry.photo_height_px.minimum
            for geometry in typed_geometries
        )
        if dual_lane_geometry is None
        else min(
            cell.perpendicular_height_px.minimum
            for cell in dual_lane_geometry.cells
        )
    )
    allowed_projected_uncertainty = (
        minimum_photo_height_px
        * parameters.maximum_projected_uncertainty_photo_height_ratio
    )
    if projected_uncertainty > allowed_projected_uncertainty:
        return _unapplied_transform_evidence(
            TransformOutcome.ANGLE_ESTIMATION_UNAVAILABLE,
            identity,
        )
    work_slope = slope_interval.midpoint
    work_angle = degrees(atan(work_slope))
    estimated_angle = work_angle if is_horizontal_layout(layout) else -work_angle
    work_angle_interval = NumericInterval(
        degrees(atan(slope_interval.minimum)),
        degrees(atan(slope_interval.maximum)),
    )
    angle_interval = (
        work_angle_interval
        if is_horizontal_layout(layout)
        else NumericInterval(
            -work_angle_interval.maximum,
            -work_angle_interval.minimum,
        )
    )
    projected_drift = abs(
        work_slope * float(max(0, source_work_width - 1))
    )
    identity_drift_threshold = clamp_float(
        source_work_width * parameters.identity_span_ratio,
        parameters.identity_span_min_px,
        parameters.identity_span_max_px,
    )
    if (
        angle_interval.minimum < -parameters.maximum_angle_degrees
        or angle_interval.maximum > parameters.maximum_angle_degrees
    ):
        return _unapplied_transform_evidence(
            TransformOutcome.ANGLE_OUT_OF_RANGE,
            identity,
        )
    maximum_projected_drift = max(
        abs(slope_interval.minimum),
        abs(slope_interval.maximum),
    ) * float(max(0, source_work_width - 1))
    if maximum_projected_drift <= identity_drift_threshold:
        return _unapplied_transform_evidence(
            TransformOutcome.IDENTITY_WITHIN_TOLERANCE,
            identity,
            estimated_angle_degrees=estimated_angle,
            pixel_angle_interval_degrees=angle_interval,
            projected_edge_drift_px=projected_drift,
            identity_drift_threshold_px=identity_drift_threshold,
        )
    return TransformGeometryEvidence(
        outcome=TransformOutcome.DESKEW_APPLIED,
        estimated_angle_degrees=estimated_angle,
        pixel_angle_interval_degrees=angle_interval,
        projected_edge_drift_px=projected_drift,
        identity_drift_threshold_px=identity_drift_threshold,
        position_uncertainty_px=(
            BILINEAR_INTERPOLATION_POSITION_UNCERTAINTY_PX
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
    source_sha256: str,
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
    (
        source_photo_edges,
        source_divider,
        dual_lane_photo_edge_geometry,
    ) = _source_photo_edge_pairs(
        source_cache,
        scan_canvas_evidence,
        configuration,
        lane_configuration,
        source_sha256,
    )
    source_height, source_width = spatial_shape(pixels)
    transform_geometry = _transform_geometry(
        source_photo_edges,
        dual_lane_photo_edge_geometry,
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
            transform_geometry,
            cache.gray_work.shape[1],
            (
                lane_configuration.shared_short_axis
                if lane_configuration is not None
                and configuration.physical_spec.layout.kind == "dual_lane"
                else configuration.shared_short_axis
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
        dual_lane_photo_edge_geometry=dual_lane_photo_edge_geometry,
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
        PhotoEdgeCoordinateSpace.SOURCE,
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
    local_transform = TransformGeometryEvidence(
        outcome=TransformOutcome.IDENTITY_WITHIN_TOLERANCE,
        estimated_angle_degrees=0.0,
        pixel_angle_interval_degrees=NumericInterval.exact(0.0),
        projected_edge_drift_px=0.0,
        identity_drift_threshold_px=1.0,
        position_uncertainty_px=0.0,
        coordinate_transform=identity,
    )
    local_plan = shared_short_axis_from_photo_edge_pair(
        local_mapped_evidence,
        local_transform,
        region.width,
        configuration.shared_short_axis,
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
        dual_lane_photo_edge_geometry=None,
        mapped_photo_edge_pairs=(local_mapped_evidence,),
        shared_short_axes=(local_plan,),
        source_lane_divider=None,
        lane_divider=None,
        transform_geometry=local_transform,
    )
