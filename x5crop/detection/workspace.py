from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from ..configuration.model import (
    DetectionConfiguration,
    ResolvedSlotCount,
    SlotCountAuthority,
)
from ..domain import Box
from ..geometry.layout import is_horizontal_layout, work_gray
from ..image.gray import make_base_gray_u8
from ..io.model import ImageProfile
from .evidence.scan_canvas import (
    MatchedHolder,
    ScanCanvasEvidence,
    ScanCanvasOutcome,
    matched_holder_from_evidence,
    observe_scan_canvas,
)
from .evidence.content_occupancy import observe_content_occupancy
from .evidence.content_occupancy_model import (
    CONTENT_OCCUPANCY_MEASUREMENT_SPEC,
)
from .photo_geometry.registered_measurement import (
    make_photo_boundary_measurement_field,
)
from .photo_geometry.measurement_model import PhotoBoundaryMeasurementField
from .source_core import (
    SourceCoreEvidence,
    SourceLaneEvidence,
    SourceStripValidationDomain,
)


@dataclass(frozen=True)
class DetectionWorkspace:
    source_gray: np.ndarray
    layout: str
    source_core: SourceCoreEvidence
    boundary_measurement_field: PhotoBoundaryMeasurementField

    def __post_init__(self) -> None:
        if not isinstance(self.source_gray, np.ndarray) or self.source_gray.ndim != 2:
            raise ValueError("detection workspace requires source gray")
        if self.boundary_measurement_field.source_gray is not self.source_gray:
            raise ValueError(
                "photo-boundary field must own the canonical source gray"
            )
        if self.boundary_measurement_field.layout != self.layout:
            raise ValueError(
                "photo-boundary field must use the canonical work layout"
            )


class SourceInputContractError(ValueError):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


def resolve_slot_count(
    configuration: DetectionConfiguration,
    matched_holder: MatchedHolder,
) -> ResolvedSlotCount:
    request = configuration.count_request
    if request.strip_mode == "full":
        return ResolvedSlotCount(
            matched_holder.profile.profile_id,
            matched_holder.full_count,
            matched_holder.full_count,
            SlotCountAuthority.MATCHED_HOLDER_FULL_COUNT,
            request.holder_layout_authority,
        )
    assert request.user_count is not None
    if request.user_count > matched_holder.full_count:
        raise SourceInputContractError(
            "partial_count_exceeds_matched_full_count",
            f"partial count {request.user_count} must not exceed matched "
            f"holder full count {matched_holder.full_count} "
            f"({matched_holder.profile.profile_id})",
        )
    return ResolvedSlotCount(
        matched_holder.profile.profile_id,
        matched_holder.full_count,
        request.user_count,
        SlotCountAuthority.USER_EXPLICIT_PARTIAL_COUNT,
        request.holder_layout_authority,
    )


def _single_lane(
    gray_work: np.ndarray,
    layout: str,
    scan_canvas: ScanCanvasEvidence,
) -> tuple[tuple[SourceLaneEvidence, ...], tuple[str, ...]]:
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
    scan_canvas: ScanCanvasEvidence,
    lane_configuration: DetectionConfiguration | None,
) -> tuple[tuple[SourceLaneEvidence, ...], tuple[str, ...]]:
    if lane_configuration is None or gray_work.shape[0] % 2:
        return (), ("dual_lane_center_partition_unavailable",)
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
    gray_work = work_gray(source_gray, layout)
    gray_work.flags.writeable = False
    scan_canvas = observe_scan_canvas(
        gray_work.shape[1],
        gray_work.shape[0],
        layout,
        configuration.scan_canvas,
    )
    matched_holder = matched_holder_from_evidence(
        scan_canvas,
        configuration.physical_spec,
    )
    resolved_slot_count = (
        None
        if matched_holder is None
        else resolve_slot_count(configuration, matched_holder)
    )
    if configuration.physical_spec.layout.kind == "dual_lane":
        lanes, incomplete_reasons = _dual_lanes(
            gray_work,
            layout,
            scan_canvas,
            lane_configuration,
        )
    else:
        lanes, incomplete_reasons = _single_lane(
            gray_work,
            layout,
            scan_canvas,
        )
    if matched_holder is None:
        candidate_full_counts = {
            configuration.physical_spec.holder_full_count(
                match.profile.profile_id
            )
            for match in scan_canvas.matches
        }
        candidate_full_counts.discard(None)
        if len(candidate_full_counts) > 1:
            incomplete_reasons = (
                *incomplete_reasons,
                "holder_full_count_unresolved",
            )
        elif len(scan_canvas.matches) > 1:
            incomplete_reasons = (
                *incomplete_reasons,
                "holder_identity_unresolved",
            )
    source_core = SourceCoreEvidence(
        scan_canvas=scan_canvas,
        matched_holder=matched_holder,
        resolved_slot_count=resolved_slot_count,
        content_occupancy=tuple(
            observe_content_occupancy(
                gray_work,
                lane_id=lane.domain.lane_id,
                lane_work_box=lane.domain.work_box,
                layout=layout,
                long_step_px=(
                    None
                    if matched_holder is None
                    else max(
                        CONTENT_OCCUPANCY_MEASUREMENT_SPEC.internal_subcells_per_axis,
                        math.floor(
                            matched_holder.axis_scales.width_axis_px_per_mm.minimum
                            * CONTENT_OCCUPANCY_MEASUREMENT_SPEC.cell_extent_mm
                        ),
                    )
                ),
                cross_step_px=(
                    None
                    if matched_holder is None
                    else max(
                        CONTENT_OCCUPANCY_MEASUREMENT_SPEC.internal_subcells_per_axis,
                        math.floor(
                            matched_holder.axis_scales.height_axis_px_per_mm.minimum
                            * CONTENT_OCCUPANCY_MEASUREMENT_SPEC.cell_extent_mm
                        ),
                    )
                ),
                spec=CONTENT_OCCUPANCY_MEASUREMENT_SPEC,
            )
            for lane in lanes
        ),
        lanes=lanes,
        incomplete_reasons=incomplete_reasons,
    )
    boundary_measurement_field = make_photo_boundary_measurement_field(
        source_gray,
        layout,
    )
    return DetectionWorkspace(
        source_gray=source_gray,
        layout=layout,
        source_core=source_core,
        boundary_measurement_field=boundary_measurement_field,
    )
