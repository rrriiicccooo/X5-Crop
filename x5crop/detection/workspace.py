from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..cache import MeasurementCache
from ..cache.analysis import make_measurement_cache
from ..configuration.model import DetectionConfiguration
from ..domain import Box, EvidenceState
from ..geometry.layout import is_horizontal_layout, work_gray
from ..image.gray import make_base_gray_u8
from ..image.statistics import image_measurement_statistics
from ..image.workspace import WorkspaceIdentity, workspace_identity_for_gray
from ..io.model import ImageProfile
from .evidence.scan_canvas import ScanCanvasOutcome, observe_scan_canvas
from .source_core import (
    SourceCoreEvidence,
    SourceLaneEvidence,
    SourceStripValidationDomain,
    VisualDeskewOutcome,
    observe_source_content,
    output_protection_authority,
    unavailable_frame_grid,
    unavailable_photo_containment,
)


@dataclass(frozen=True)
class DetectionWorkspace:
    source_gray: np.ndarray
    measurement_cache: MeasurementCache
    source_core: SourceCoreEvidence
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
        object.__setattr__(
            self,
            "identity",
            workspace_identity_for_gray(self.source_gray),
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
    content = observe_source_content(
        gray_work,
        domain,
        configuration.content,
    )
    reasons = (
        ()
        if content.state == EvidenceState.SUPPORTED
        else ("source_content_measurement_unavailable",)
    )
    return (
        (
            SourceLaneEvidence(
                domain=domain,
                scan_canvas=scan_canvas,
                scales=scan_canvas.axis_scales,
                content=content,
            ),
        ),
        reasons,
    )


def _dual_lanes(
    gray_work: np.ndarray,
    layout: str,
    lane_configuration: DetectionConfiguration | None,
) -> tuple[tuple[SourceLaneEvidence, ...], tuple[str, ...]]:
    if lane_configuration is None or gray_work.shape[0] % 2:
        return (), ("dual_lane_center_partition_unavailable",)
    center = gray_work.shape[0] // 2
    lanes: list[SourceLaneEvidence] = []
    reasons: list[str] = []
    for lane_index, (top, bottom) in enumerate(
        ((0, center), (center, gray_work.shape[0]))
    ):
        if bottom <= top:
            return (), ("dual_lane_empty_lane",)
        scan_canvas = observe_scan_canvas(
            gray_work.shape[1],
            bottom - top,
            layout,
            lane_configuration.scan_canvas,
        )
        if (
            scan_canvas.outcome != ScanCanvasOutcome.SUPPORTED
            or scan_canvas.axis_scales is None
            or scan_canvas.selected_profile is None
        ):
            reasons.append(
                f"lane_{lane_index}_scan_canvas_{scan_canvas.outcome.value}"
            )
            continue
        domain = SourceStripValidationDomain(
            lane_id=f"lane:{lane_index}",
            work_box=Box(0, top, gray_work.shape[1], bottom),
            source_axis_long="x" if is_horizontal_layout(layout) else "y",
            authority_profile_id=scan_canvas.selected_profile.profile_id,
        )
        content = observe_source_content(
            gray_work,
            domain,
            lane_configuration.content,
        )
        if content.state != EvidenceState.SUPPORTED:
            reasons.append(f"lane_{lane_index}_source_content_unavailable")
        lanes.append(
            SourceLaneEvidence(
                domain=domain,
                scan_canvas=scan_canvas,
                scales=scan_canvas.axis_scales,
                content=content,
            )
        )
    if len(lanes) != 2:
        return (), tuple(dict.fromkeys(reasons))
    return tuple(lanes), tuple(dict.fromkeys(reasons))


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
    )
    gray_work = measurement_cache.gray_work
    if configuration.physical_spec.layout.kind == "dual_lane":
        lanes, incomplete_reasons = _dual_lanes(
            gray_work,
            layout,
            lane_configuration,
        )
    else:
        lanes, incomplete_reasons = _single_lane(
            gray_work,
            layout,
            configuration,
        )
    scan_canvas_state = (
        EvidenceState.SUPPORTED if lanes else EvidenceState.UNAVAILABLE
    )
    content_state = (
        EvidenceState.SUPPORTED
        if lanes
        and all(
            lane.content.state == EvidenceState.SUPPORTED
            for lane in lanes
        )
        else EvidenceState.UNAVAILABLE
    )
    source_core = SourceCoreEvidence(
        lanes=lanes,
        scan_canvas_state=scan_canvas_state,
        content_state=content_state,
        grid=unavailable_frame_grid(),
        containment=unavailable_photo_containment(),
        protection_authority=output_protection_authority(
            configuration.physical_spec
        ),
        visual_deskew_outcome=(
            VisualDeskewOutcome.NOT_APPLICABLE_CORE_UNAVAILABLE
        ),
        incomplete_reasons=incomplete_reasons,
    )
    return DetectionWorkspace(
        source_gray=source_gray,
        measurement_cache=measurement_cache,
        source_core=source_core,
    )
