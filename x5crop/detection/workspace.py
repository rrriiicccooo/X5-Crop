from __future__ import annotations

from dataclasses import dataclass, field, replace
from math import atan, degrees
from statistics import median

import numpy as np

from ..cache import MeasurementCache, MeasurementCacheStatistics
from ..cache.analysis import make_measurement_cache
from ..configuration.model import DetectionConfiguration
from ..configuration.transform import DeskewDetectionParameters
from ..domain import (
    BoundaryAxis,
    BoundaryKind,
    BoundaryMeasurementSet,
    BoundaryPathFit,
    BoundaryPathSample,
    BoundarySide,
    Box,
    EvidenceState,
    FrameSequenceSearchScope,
    GrayBoundaryPathObservation,
    HolderSafetyEnvelope,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PhysicalSearchFact,
    PhysicalSearchOutcome,
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
from .evidence.transform_geometry import (
    TransformGeometryEvidence,
    TransformOutcome,
)
from .physical.boundary_detection import boundary_measurements
from .physical.lane_divider import LaneDividerEvidence, measure_lane_dividers
from .physical.short_axis import (
    SharedShortAxisPlan,
    photo_edge_is_independent,
    shared_short_axis_from_photo_edges,
    shared_short_axis_plan,
)


@dataclass(frozen=True)
class DetectionWorkspace:
    pixels: np.ndarray
    source_gray: np.ndarray
    gray: np.ndarray
    measurement_cache: MeasurementCache
    source_shared_short_axes: tuple[SharedShortAxisPlan, ...]
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
        if len(self.source_shared_short_axes) != len(self.shared_short_axes):
            raise ValueError("source and workspace short-axis plans must correspond")
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
        for label, plans, work in (
            ("source", self.source_shared_short_axes, source_work),
            ("workspace", self.shared_short_axes, workspace_work),
        ):
            for plan in plans:
                if plan.span is not None and (
                    plan.top.minimum < 0.0
                    or plan.bottom.maximum > float(work.shape[0])
                ):
                    raise ValueError(
                        f"{label} short-axis plan lies outside its coordinate domain"
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
            if self.source_shared_short_axes != self.shared_short_axes:
                raise ValueError("identity workspace must reuse source short-axis plans")
            if self.source_lane_divider != self.lane_divider:
                raise ValueError("identity workspace must reuse the source lane divider")
        else:
            if not self.source_shared_short_axes:
                raise ValueError(
                    "applied transform requires source short-axis plans"
                )
            for source_plan, mapped_plan in zip(
                self.source_shared_short_axes,
                self.shared_short_axes,
                strict=True,
            ):
                if (
                    source_plan.top_photo_edge is None
                    or source_plan.bottom_photo_edge is None
                    or mapped_plan.top_photo_edge is None
                    or mapped_plan.bottom_photo_edge is None
                ):
                    raise ValueError(
                        "applied transform requires corresponding mapped photo edges"
                    )
                for source_edge, mapped_edge in (
                    (source_plan.top_photo_edge, mapped_plan.top_photo_edge),
                    (source_plan.bottom_photo_edge, mapped_plan.bottom_photo_edge),
                ):
                    if mapped_edge.provenance.observation_id != ObservationId(
                        f"workspace:{source_edge.provenance.observation_id}"
                    ):
                        raise ValueError(
                            "mapped photo edge must preserve its source observation identity"
                        )
            if self.source_lane_divider is not None:
                assert self.lane_divider is not None
                if self.lane_divider.provenance.observation_id != ObservationId(
                    f"workspace:{self.source_lane_divider.provenance.observation_id}"
                ):
                    raise ValueError(
                        "mapped lane divider must preserve its source observation identity"
                    )
        if not np.array_equal(
            self.measurement_cache.gray_work,
            work_gray(self.gray, self.measurement_cache.layout),
        ):
            raise ValueError("detection workspace cache must use its canonical gray")
        object.__setattr__(self, "identity", workspace_identity_for_gray(self.gray))


def _short_axis_scope(
    measured: BoundaryMeasurementSet,
    qualified_photo_edges: tuple[GrayBoundaryPathObservation, ...],
) -> FrameSequenceSearchScope:
    holder_safety = HolderSafetyEnvelope(
        measured.holder_boundaries,
        measured.containment_fallback,
    )
    holder_paths = tuple(
        path
        for boundary in measured.holder_boundaries
        for path in boundary.supporting_paths
    )
    return FrameSequenceSearchScope(
        holder_safety=holder_safety,
        raw_boundary_paths=tuple(
            dict.fromkeys((*qualified_photo_edges, *holder_paths))
        ),
        provenance=MeasurementProvenance(
            root_measurement=MeasurementIdentity.BOUNDARY_PATHS,
            observation_id=ObservationId("source_shared_short_axis_scope"),
            dependencies=(
                MeasurementIdentity.GRAY_WORK,
                MeasurementIdentity.IMAGE_MEASUREMENT_STATISTICS,
            ),
            description="source-coordinate short-axis photo-edge search scope",
            boundary_anchors=tuple(
                boundary.provenance.observation_id
                for boundary in measured.holder_boundaries
            ),
        ),
    )


def _measure_short_axis(
    gray_work: np.ndarray,
    statistics: ImageMeasurementStatistics,
    configuration: DetectionConfiguration,
) -> SharedShortAxisPlan:
    measured = boundary_measurements(
        gray_work,
        statistics,
        configuration.boundary_path,
        axes=(BoundaryAxis.SHORT,),
        transform_position_uncertainty_px=0.0,
    )
    intensity_range = max(
        0.0,
        statistics.intensity_high - statistics.intensity_low,
    )
    minimum_intensity_contrast = (
        intensity_range
        * configuration.deskew.minimum_photo_edge_intensity_range_ratio
    )
    minimum_holder_gap = (
        float(gray_work.shape[0])
        * configuration.deskew.minimum_holder_photo_gap_ratio
    )
    holder_by_side = {
        boundary.side: boundary for boundary in measured.holder_boundaries
    }
    qualified_photo_edges = tuple(
        path
        for path in measured.raw_paths
        if path.axis == BoundaryAxis.SHORT
        and path.kind != BoundaryKind.EDGE_ADJACENT_TRANSITION
        and any(
            photo_edge_is_independent(
                path,
                side,
                holder_by_side.get(side),
                minimum_intensity_contrast=minimum_intensity_contrast,
                minimum_holder_gap=minimum_holder_gap,
            )
            for side in (BoundarySide.TOP, BoundarySide.BOTTOM)
        )
    )
    return shared_short_axis_plan(
        _short_axis_scope(measured, qualified_photo_edges)
    )


def _path_provenance(
    path: GrayBoundaryPathObservation,
    prefix: str,
    dependency: MeasurementIdentity,
) -> MeasurementProvenance:
    return MeasurementProvenance(
        root_measurement=MeasurementIdentity.BOUNDARY_PATHS,
        observation_id=ObservationId(
            f"{prefix}:{path.provenance.observation_id}"
        ),
        dependencies=tuple(
            dict.fromkeys(
                (
                    *path.provenance.dependencies,
                    dependency,
                )
            )
        ),
        description="coordinate-mapped photo boundary path",
        boundary_anchors=(path.provenance.observation_id,),
    )


def _translate_path_to_parent(
    path: GrayBoundaryPathObservation,
    y_offset: int,
) -> GrayBoundaryPathObservation:
    provenance = _path_provenance(
        path,
        f"parent_lane_{y_offset}",
        MeasurementIdentity.CANVAS,
    )
    return GrayBoundaryPathObservation(
        axis=path.axis,
        kind=path.kind,
        samples=tuple(
            BoundaryPathSample(
                sample.orthogonal_interval,
                sample.position.plus(PixelInterval.exact(float(y_offset))),
            )
            for sample in path.samples
        ),
        lower_appearance=replace(path.lower_appearance, provenance=provenance),
        upper_appearance=replace(path.upper_appearance, provenance=provenance),
        provenance=provenance,
    )


def _translate_plan_to_parent(
    plan: SharedShortAxisPlan,
    y_offset: int,
) -> SharedShortAxisPlan:
    if plan.top_photo_edge is None or plan.bottom_photo_edge is None:
        return plan
    top = _translate_path_to_parent(plan.top_photo_edge, y_offset)
    bottom = _translate_path_to_parent(plan.bottom_photo_edge, y_offset)
    return shared_short_axis_from_photo_edges(
        top,
        bottom,
    )


def _source_short_axes(
    source_cache: MeasurementCache,
    configuration: DetectionConfiguration,
    lane_configuration: DetectionConfiguration | None,
) -> tuple[tuple[SharedShortAxisPlan, ...], LaneDividerEvidence | None]:
    if configuration.physical_spec.layout.kind != "dual_lane":
        return (
            (
                _measure_short_axis(
                    source_cache.gray_work,
                    source_cache.image_statistics,
                    configuration,
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
    plans: list[SharedShortAxisPlan] = []
    for lane in divider.lane_boxes(
        source_cache.gray_work.shape[1],
        source_cache.gray_work.shape[0],
    ):
        lane_gray = source_cache.gray_work[
            lane.top : lane.bottom,
            lane.left : lane.right,
        ]
        lane_statistics = image_measurement_statistics(
            lane_gray,
            lane_configuration.preprocess.image_statistics,
        )
        plans.append(
            _translate_plan_to_parent(
                _measure_short_axis(
                    lane_gray,
                    lane_statistics,
                    lane_configuration,
                ),
                lane.top,
            )
        )
    return tuple(plans), divider


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


def _deskew_geometry(
    plans: tuple[SharedShortAxisPlan, ...],
    source_work_width: int,
    source_work_height: int,
    source_width: int,
    source_height: int,
    layout: str,
    parameters: DeskewDetectionParameters,
) -> TransformGeometryEvidence:
    identity = AffineCoordinateTransform.identity(source_width, source_height)
    if not plans or any(
        plan.top_photo_edge is None or plan.bottom_photo_edge is None
        for plan in plans
    ):
        return _unapplied_transform_evidence(
            TransformOutcome.PHOTO_EDGES_UNAVAILABLE,
            identity,
        )
    if any(not plan.supports_safe_crop for plan in plans):
        return _unapplied_transform_evidence(
            TransformOutcome.INSUFFICIENT_COMMON_SUPPORT,
            identity,
        )
    fits = tuple(
        (
            BoundaryPathFit(plan.top_photo_edge),
            BoundaryPathFit(plan.bottom_photo_edge),
        )
        for plan in plans
        if plan.top_photo_edge is not None and plan.bottom_photo_edge is not None
    )
    common_extents = tuple(
        top.orthogonal_extent.intersection(bottom.orthogonal_extent)
        for top, bottom in fits
    )
    if any(
        extent is None
        or extent.maximum - extent.minimum
        < source_work_width * parameters.minimum_common_support_ratio
        for extent in common_extents
    ) or any(
        len(plan.top_photo_edge.samples) < parameters.minimum_path_samples
        or len(plan.bottom_photo_edge.samples) < parameters.minimum_path_samples
        for plan in plans
        if plan.top_photo_edge is not None and plan.bottom_photo_edge is not None
    ):
        return _unapplied_transform_evidence(
            TransformOutcome.INSUFFICIENT_COMMON_SUPPORT,
            identity,
        )
    inner_lines = tuple(
        line
        for top, bottom in fits
        for line in (top.maximum_line, bottom.minimum_line)
    )
    residual_limit = max(
        parameters.residual_floor_px,
        source_work_height * parameters.residual_height_ratio,
    )
    if any(line.residual > residual_limit for line in inner_lines):
        return _unapplied_transform_evidence(
            TransformOutcome.EDGE_FIT_HIGH_RESIDUAL,
            identity,
        )
    slopes = tuple(line.slope for line in inner_lines)
    if max(slopes) - min(slopes) > parameters.maximum_slope_delta:
        return _unapplied_transform_evidence(
            TransformOutcome.EDGE_SLOPES_DISAGREE,
            identity,
        )
    work_angle = degrees(atan(float(median(slopes))))
    estimated_angle = work_angle if is_horizontal_layout(layout) else -work_angle
    projected_drift = abs(float(median(slopes)) * float(source_work_width))
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
    return TransformGeometryEvidence(
        outcome=TransformOutcome.DESKEW_APPLIED,
        estimated_angle_degrees=estimated_angle,
        projected_edge_drift_px=projected_drift,
        identity_drift_threshold_px=identity_drift_threshold,
        position_uncertainty_px=(
            BILINEAR_INTERPOLATION_POSITION_UNCERTAINTY_PX
            + max(line.residual for line in inner_lines)
        ),
        coordinate_transform=AffineCoordinateTransform.expanded_rotation(
            source_width,
            source_height,
            -estimated_angle,
        ),
    )


def _transform_qualified_short_axes(
    plans: tuple[SharedShortAxisPlan, ...],
    evidence: TransformGeometryEvidence,
) -> tuple[SharedShortAxisPlan, ...]:
    if evidence.outcome not in {
        TransformOutcome.INSUFFICIENT_COMMON_SUPPORT,
        TransformOutcome.EDGE_SLOPES_DISAGREE,
        TransformOutcome.EDGE_FIT_HIGH_RESIDUAL,
    }:
        return plans
    fact = (
        PhysicalSearchFact.MEASUREMENTS_UNAVAILABLE
        if evidence.outcome == TransformOutcome.INSUFFICIENT_COMMON_SUPPORT
        else PhysicalSearchFact.CONSTRAINTS_CONTRADICTED
    )
    return tuple(
        replace(
            plan,
            span=None,
            search_outcome=PhysicalSearchOutcome((fact,)),
        )
        for plan in plans
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


def _mapped_path(
    path: GrayBoundaryPathObservation,
    transform: AffineCoordinateTransform,
    layout: str,
    position_uncertainty_px: float,
) -> GrayBoundaryPathObservation:
    provenance = _path_provenance(
        path,
        "workspace",
        MeasurementIdentity.WORKSPACE_TRANSFORM,
    )
    samples = []
    work_width = (
        transform.output_extent.width
        if is_horizontal_layout(layout)
        else transform.output_extent.height
    )
    work_height = (
        transform.output_extent.height
        if is_horizontal_layout(layout)
        else transform.output_extent.width
    )
    orthogonal_domain = PixelInterval(0.0, float(work_width))
    position_domain = PixelInterval(0.0, float(work_height))
    for sample in path.samples:
        orthogonal, position = _map_work_intervals(
            transform,
            layout,
            sample.orthogonal_interval,
            sample.position,
        )
        orthogonal = orthogonal.intersection(orthogonal_domain)
        position = position.expanded(position_uncertainty_px).intersection(
            position_domain
        )
        if orthogonal is None or position is None:
            raise ValueError("mapped photo-edge sample lies outside the workspace")
        samples.append(
            BoundaryPathSample(
                orthogonal,
                position,
            )
        )
    return GrayBoundaryPathObservation(
        axis=path.axis,
        kind=path.kind,
        samples=tuple(
            sorted(samples, key=lambda sample: sample.orthogonal_interval.midpoint)
        ),
        lower_appearance=replace(path.lower_appearance, provenance=provenance),
        upper_appearance=replace(path.upper_appearance, provenance=provenance),
        provenance=provenance,
    )


def _mapped_plan(
    plan: SharedShortAxisPlan,
    evidence: TransformGeometryEvidence,
    layout: str,
) -> SharedShortAxisPlan:
    if not evidence.applied or not plan.supports_safe_crop:
        return plan
    assert plan.top_photo_edge is not None
    assert plan.bottom_photo_edge is not None
    top = _mapped_path(
        plan.top_photo_edge,
        evidence.coordinate_transform,
        layout,
        evidence.position_uncertainty_px,
    )
    bottom = _mapped_path(
        plan.bottom_photo_edge,
        evidence.coordinate_transform,
        layout,
        evidence.position_uncertainty_px,
    )
    return shared_short_axis_from_photo_edges(
        top,
        bottom,
    )


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
    center = max(gutter.top, min(gutter.bottom - 1, round(center_position.midpoint)))
    provenance = MeasurementProvenance(
        root_measurement=MeasurementIdentity.LANE_DIVIDER_PROFILE,
        observation_id=ObservationId(
            f"workspace:{divider.provenance.observation_id}"
        ),
        dependencies=tuple(
            dict.fromkeys(
                (*divider.provenance.dependencies, MeasurementIdentity.WORKSPACE_TRANSFORM)
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
    source_plans, source_divider = _source_short_axes(
        source_cache,
        configuration,
        lane_configuration,
    )
    source_height, source_width = spatial_shape(pixels)
    evidence = _deskew_geometry(
        source_plans,
        source_cache.gray_work.shape[1],
        source_cache.gray_work.shape[0],
        source_width,
        source_height,
        layout,
        configuration.deskew,
    )
    source_plans = _transform_qualified_short_axes(source_plans, evidence)
    if evidence.applied:
        assert evidence.applied_angle_degrees is not None
        transformed_pixels, transform = rotate_array_expand(
            pixels,
            evidence.applied_angle_degrees,
            profile.axes,
            background_value=photometric_background_value(
                pixels,
                profile.photometric,
            ),
        )
        if transform != evidence.coordinate_transform:
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
            evidence.position_uncertainty_px,
            lookup_statistics,
        )
    else:
        transformed_pixels = pixels
        gray = source_gray
        cache = source_cache
    plans = tuple(_mapped_plan(plan, evidence, layout) for plan in source_plans)
    divider = _mapped_lane_divider(
        source_divider,
        evidence,
        layout,
        cache.gray_work.shape[1],
        cache.gray_work.shape[0],
    )
    return DetectionWorkspace(
        pixels=transformed_pixels,
        source_gray=source_gray,
        gray=gray,
        measurement_cache=cache,
        source_shared_short_axes=source_plans,
        shared_short_axes=plans,
        source_lane_divider=source_divider,
        lane_divider=divider,
        transform_geometry=evidence,
    )


def detection_workspace_region(
    workspace: DetectionWorkspace,
    region: Box,
    shared_short_axis: SharedShortAxisPlan,
    configuration: DetectionConfiguration,
) -> DetectionWorkspace:
    gray = workspace.measurement_cache.gray_work[
        region.top : region.bottom,
        region.left : region.right,
    ]
    local_plan = _translate_plan_to_parent(shared_short_axis, -region.top)
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
    local_transform = TransformGeometryEvidence(
        outcome=TransformOutcome.IDENTITY_WITHIN_TOLERANCE,
        estimated_angle_degrees=0.0,
        projected_edge_drift_px=0.0,
        identity_drift_threshold_px=1.0,
        position_uncertainty_px=0.0,
        coordinate_transform=identity,
    )
    return DetectionWorkspace(
        pixels=gray,
        source_gray=gray,
        gray=gray,
        measurement_cache=cache,
        source_shared_short_axes=(local_plan,),
        shared_short_axes=(local_plan,),
        source_lane_divider=None,
        lane_divider=None,
        transform_geometry=local_transform,
    )
