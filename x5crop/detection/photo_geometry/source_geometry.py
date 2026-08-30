from __future__ import annotations

from dataclasses import dataclass

from ...domain import FiniteInterval, PositiveInterval
from ...formats import FramePhysicalSpec
from .joint_axis_geometry import JointAxisGeometry
from .physical_identity import physical_fact_id


def centered_short_axis_authority_px(
    visible_authority_px: FiniteInterval,
    scale_authority_px_per_mm: PositiveInterval,
) -> FiniteInterval:
    """Return the holder-centred film axis allowed by canvas authority.

    The scan-canvas scale interval already encodes the holder's physical extent
    tolerance.  Its relative half-width is therefore the only permitted
    uncertainty in where the nominal physical centre lands in the raster.  No
    second millimetre allowance or detector-specific centre threshold exists.
    """
    scale_sum = (
        scale_authority_px_per_mm.minimum
        + scale_authority_px_per_mm.maximum
    )
    extent_error_ratio = (
        scale_authority_px_per_mm.maximum
        - scale_authority_px_per_mm.minimum
    ) / scale_sum
    center_uncertainty_px = (
        visible_authority_px.width * extent_error_ratio / 2.0
    )
    return FiniteInterval(
        visible_authority_px.center - center_uncertainty_px,
        visible_authority_px.center + center_uncertainty_px,
    )
@dataclass(frozen=True)
class SourceScanGeometry:
    geometry_id: str
    frame_spec: FramePhysicalSpec
    width_state: JointAxisGeometry
    height_state: JointAxisGeometry

    @classmethod
    def create(
        cls,
        frame_spec: FramePhysicalSpec,
        *,
        width_scale_px_per_mm: PositiveInterval,
        height_scale_px_per_mm: PositiveInterval,
    ) -> "SourceScanGeometry":
        shared_scale_minimum = max(
            width_scale_px_per_mm.minimum,
            height_scale_px_per_mm.minimum,
        )
        shared_scale_maximum = min(
            width_scale_px_per_mm.maximum,
            height_scale_px_per_mm.maximum,
        )
        if shared_scale_maximum < shared_scale_minimum:
            raise ValueError("holder axes do not provide one source scan scale")
        shared_scale = PositiveInterval(
            shared_scale_minimum,
            shared_scale_maximum,
        )
        width = JointAxisGeometry.create(
            axis_name="width",
            design_extent_mm=frame_spec.frame_width_mm,
            scale_interval_px_per_mm=shared_scale,
            factor_interval=PositiveInterval(
                frame_spec.frame_width_factor_minimum,
                frame_spec.frame_width_factor_maximum,
            ),
        )
        height = JointAxisGeometry.create(
            axis_name="height",
            design_extent_mm=frame_spec.frame_height_mm,
            scale_interval_px_per_mm=shared_scale,
            factor_interval=PositiveInterval(
                frame_spec.frame_height_factor_minimum,
                frame_spec.frame_height_factor_maximum,
            ),
        )
        return cls(
            geometry_id=physical_fact_id(
                "source-scan-geometry",
                frame_spec.identity_fields,
                width_scale_px_per_mm,
                height_scale_px_per_mm,
            ),
            frame_spec=frame_spec,
            width_state=width,
            height_state=height,
        )

    def __post_init__(self) -> None:
        if (
            not self.geometry_id
            or self.width_state.axis_name != "width"
            or self.height_state.axis_name != "height"
            or self.width_state.design_extent_mm != self.frame_spec.frame_width_mm
            or self.height_state.design_extent_mm
            != self.frame_spec.frame_height_mm
            or self.width_state.scale_authority
            != self.height_state.scale_authority
        ):
            raise ValueError("source scan geometry is invalid")

    @classmethod
    def from_axis_states(
        cls,
        frame_spec: FramePhysicalSpec,
        width_state: JointAxisGeometry,
        height_state: JointAxisGeometry,
    ) -> "SourceScanGeometry":
        """Create one source owner for shared W_px and H_px feasibility.

        The holder establishes one nominal scan scale when ``create`` is
        called.  Once photograph edges are observed, a small camera-aperture
        difference and a small scan-scale difference are indistinguishable to
        this cropper.  Direct width evidence therefore narrows W_px and direct
        height evidence narrows H_px.  This constructor never turns one into
        evidence for the other; any future cross-axis inference must belong to
        a separately calibrated, typed aspect-ratio authority and remain
        correlated.  Both direct states are intersected across lanes below.
        """

        if (
            width_state.axis_name != "width"
            or height_state.axis_name != "height"
            or width_state.design_extent_mm != frame_spec.frame_width_mm
            or height_state.design_extent_mm != frame_spec.frame_height_mm
            or width_state.scale_authority != height_state.scale_authority
        ):
            raise ValueError("source W/H states do not share holder authority")
        return cls(
            geometry_id=physical_fact_id(
                "source-scan-geometry",
                frame_spec.identity_fields,
                width_state.vertices,
                height_state.vertices,
                width_state.observation_ids,
                height_state.observation_ids,
            ),
            frame_spec=frame_spec,
            width_state=width_state,
            height_state=height_state,
        )

    def intersect_source_state(
        self,
        other: "SourceScanGeometry",
    ) -> "SourceScanGeometry":
        if self.frame_spec != other.frame_spec:
            raise ValueError("source geometries use different frame specs")
        return SourceScanGeometry.from_axis_states(
            self.frame_spec,
            self.width_state.intersect_state(other.width_state),
            self.height_state.intersect_state(other.height_state),
        )
