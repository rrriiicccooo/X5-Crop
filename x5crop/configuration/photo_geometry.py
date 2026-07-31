from __future__ import annotations

from dataclasses import dataclass

from ..domain import FiniteInterval, PositiveInterval
from ..formats import FrameDesignApertureMm


@dataclass(frozen=True)
class FrameSequencePhysicalConstraint:
    """Format-owned aperture label and typed adjacency interval."""

    format_id: str
    aperture: FrameDesignApertureMm
    aperture_label: str
    gutter_mm: FiniteInterval
    provenance: str

    def __post_init__(self) -> None:
        if (
            not self.format_id
            or not self.aperture_label
            or self.provenance
            not in {"nominal_gold_calibrated", "physical_rule"}
        ):
            raise ValueError("frame-sequence physical constraint is incomplete")

    def gutter_px(
        self,
        long_axis_scale_px_per_mm: PositiveInterval,
    ) -> FiniteInterval:
        products = (
            self.gutter_mm.minimum
            * long_axis_scale_px_per_mm.minimum,
            self.gutter_mm.minimum
            * long_axis_scale_px_per_mm.maximum,
            self.gutter_mm.maximum
            * long_axis_scale_px_per_mm.minimum,
            self.gutter_mm.maximum
            * long_axis_scale_px_per_mm.maximum,
        )
        return FiniteInterval(min(products), max(products))


_GUTTER_MM_BY_FORMAT = {
    # The 135 holder's typed inter-aperture separator is narrower than the
    # full search allowance.  Keeping this as a physical interval prevents a
    # dark image-border transition farther inside a frame from masquerading
    # as the next aperture start.
    "135": FiniteInterval(1.0, 2.25),
    "135-dual": FiniteInterval(1.0, 2.25),
    "half": FiniteInterval(-0.5, 2.5),
    "xpan": FiniteInterval(1.0, 4.0),
    "120-645": FiniteInterval(4.0, 9.0),
    "120-66": None,
    "120-67": FiniteInterval(2.0, 8.0),
}


def frame_sequence_physical_constraints(
    format_id: str,
    apertures: tuple[FrameDesignApertureMm, ...],
) -> tuple[FrameSequencePhysicalConstraint, ...]:
    calibrated = format_id in {
        "135",
        "135-dual",
        "half",
        "120-66",
        "120-67",
    }
    constraints: list[FrameSequencePhysicalConstraint] = []
    for aperture in apertures:
        gutter = _GUTTER_MM_BY_FORMAT[format_id]
        if format_id == "120-66":
            # The 54/56 label belongs to the whole lane, so its matching
            # aperture and gutter interval are emitted as one sequence choice.
            gutter = (
                FiniteInterval(4.0, 11.0)
                if aperture.long_axis_mm == 54.0
                else FiniteInterval(2.0, 9.0)
            )
        assert gutter is not None
        label = (
            f"{aperture.long_axis_mm:g}x"
            f"{aperture.short_axis_mm:g}mm"
        )
        constraints.append(
            FrameSequencePhysicalConstraint(
                format_id=format_id,
                aperture=aperture,
                aperture_label=label,
                gutter_mm=gutter,
                provenance=(
                    "nominal_gold_calibrated"
                    if calibrated
                    else "physical_rule"
                ),
            )
        )
    return tuple(constraints)
