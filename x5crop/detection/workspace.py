from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..cache import MeasurementCache
from ..cache.analysis import make_measurement_cache
from ..configuration.model import DetectionConfiguration
from ..domain import Box
from ..geometry.layout import is_horizontal_layout, work_gray
from ..image.gray import make_base_gray_u8
from ..image.statistics import image_measurement_statistics
from ..image.workspace import WorkspaceIdentity
from ..io.model import ImageProfile
from .evidence.scan_canvas import ScanCanvasOutcome, observe_scan_canvas
from .photo_geometry.measurement import (
    make_photo_boundary_measurement_field,
)
from .photo_geometry.model import PhotoBoundaryMeasurementField
from .source_core import (
    SourceCoreEvidence,
    SourceLaneEvidence,
    SourceStripValidationDomain,
)


@dataclass(frozen=True)
class DetectionWorkspace:
    source_gray: np.ndarray
    measurement_cache: MeasurementCache
    source_core: SourceCoreEvidence
    boundary_measurement_field: PhotoBoundaryMeasurementField
    identity: WorkspaceIdentity = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.source_gray, np.ndarray) or self.source_gray.ndim != 2:
            raise ValueError("detection workspace requires source gray")
        canonical_work = work_gray(
            self.source_gray,
            self.measurement_cache.layout,
        )
        if not np.array_equal(self.measurement_cache.gray_work, canonical_work):
            raise ValueError("measurement cache must use canonical source gray")
        if self.boundary_measurement_field.source_gray is not self.source_gray:
            raise ValueError(
                "photo-boundary field must own the canonical source gray"
            )
        if self.boundary_measurement_field.layout != self.measurement_cache.layout:
            raise ValueError(
                "photo-boundary field must use the canonical work layout"
            )
        object.__setattr__(
            self,
            "identity",
            self.measurement_cache.key.workspace_identity,
        )


def _single_lane(
    gray_work: np.ndarray,
    layout: str,
    configuration: DetectionConfiguration,
) -> tuple[tuple[SourceLaneEvidence, ...], tuple[str, ...]]:
    scan_canvas = observe_scan_canvas(
        gray_work.shape[1],
        gray_work.shape[0],
        layout,
        configuration.scan_canvas,
    )
    if (
        scan_canvas.outcome != ScanCanvasOutcome.SUPPORTED
        or scan_canvas.axis_scales is None
        or scan_canvas.selected_profile is None
    ):
        return (), (f"scan_canvas_{scan_canvas.outcome.value}",)
    domain = SourceStripValidationDomain(
        lane_id="lane:0",
        work_box=Box(0, 0, gray_work.shape[1], gray_work.shape[0]),
        source_axis_long="x" if is_horizontal_layout(layout) else "y",
        authority_profile_id=scan_canvas.selected_profile.profile_id,
    )
    return (
        (
            SourceLaneEvidence(
                domain=domain,
                scan_canvas=scan_canvas,
            ),
        ),
        (),
    )


def _dual_lanes(
    gray_work: np.ndarray,
    layout: str,
    configuration: DetectionConfiguration,
    lane_configuration: DetectionConfiguration | None,
) -> tuple[tuple[SourceLaneEvidence, ...], tuple[str, ...]]:
    if lane_configuration is None or gray_work.shape[0] % 2:
        return (), ("dual_lane_center_partition_unavailable",)
    scan_canvas = observe_scan_canvas(
        gray_work.shape[1],
        gray_work.shape[0],
        layout,
        configuration.scan_canvas,
    )
    if (
        scan_canvas.outcome != ScanCanvasOutcome.SUPPORTED
        or scan_canvas.axis_scales is None
        or scan_canvas.selected_profile is None
    ):
        return (), (f"scan_canvas_{scan_canvas.outcome.value}",)
    center = gray_work.shape[0] // 2
    lanes: list[SourceLaneEvidence] = []
    for lane_index, (top, bottom) in enumerate(
        ((0, center), (center, gray_work.shape[0]))
    ):
        if bottom <= top:
            return (), ("dual_lane_empty_lane",)
        domain = SourceStripValidationDomain(
            lane_id=f"lane:{lane_index}",
            work_box=Box(0, top, gray_work.shape[1], bottom),
            source_axis_long="x" if is_horizontal_layout(layout) else "y",
            authority_profile_id=scan_canvas.selected_profile.profile_id,
        )
        lanes.append(
            SourceLaneEvidence(
                domain=domain,
                scan_canvas=scan_canvas,
            )
        )
    if len(lanes) != 2:
        return (), ("dual_lane_partition_unavailable",)
    return tuple(lanes), ()


def prepare_detection_workspace(
    arr: np.ndarray,
    profile: ImageProfile,
    layout: str,
    configuration: DetectionConfiguration,
    lane_configuration: DetectionConfiguration | None,
) -> DetectionWorkspace:
    source_gray = make_base_gray_u8(
        arr,
        profile.axes,
        profile.photometric,
        configuration.preprocess.base_gray,
    )
    statistics = image_measurement_statistics(
        source_gray,
        configuration.preprocess.image_statistics,
    )
    measurement_cache = make_measurement_cache(
        source_gray,
        layout,
        statistics,
        configuration.preprocess.base_gray,
        configuration.preprocess.image_statistics,
    )
    gray_work = measurement_cache.gray_work
    if configuration.physical_spec.layout.kind == "dual_lane":
        lanes, incomplete_reasons = _dual_lanes(
            gray_work,
            layout,
            configuration,
            lane_configuration,
        )
    else:
        lanes, incomplete_reasons = _single_lane(
            gray_work,
            layout,
            configuration,
        )
    source_core = SourceCoreEvidence(
        lanes=lanes,
        incomplete_reasons=incomplete_reasons,
    )
    boundary_measurement_field = make_photo_boundary_measurement_field(
        source_gray,
        layout,
    )
    return DetectionWorkspace(
        source_gray=source_gray,
        measurement_cache=measurement_cache,
        source_core=source_core,
        boundary_measurement_field=boundary_measurement_field,
    )
