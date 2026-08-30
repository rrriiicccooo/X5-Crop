from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from ..utils import require_positive


@dataclass(frozen=True, order=True)
class ApertureAxisGuardSpec:
    """One axis guard shared by every format through a mixed physical rule."""

    absolute_floor_mm: float
    relative_ratio: float

    def __post_init__(self) -> None:
        require_positive("aperture-axis absolute guard", self.absolute_floor_mm)
        if not 0.0 < self.relative_ratio < 1.0:
            raise ValueError(
                "aperture-axis relative guard must be between zero and one"
            )

    def guard_mm(self, nominal_axis_mm: float) -> float:
        require_positive("nominal aperture axis", nominal_axis_mm)
        return max(
            self.absolute_floor_mm,
            self.relative_ratio * nominal_axis_mm,
        )

    def relative_guard(self, nominal_axis_mm: float) -> float:
        return self.guard_mm(nominal_axis_mm) / nominal_axis_mm

    def factor_bounds(self, nominal_axis_mm: float) -> tuple[float, float]:
        guard = self.relative_guard(nominal_axis_mm)
        if guard >= 1.0:
            raise ValueError("aperture-axis guard exhausts its nominal extent")
        return 1.0 - guard, 1.0 + guard

    @property
    def identity_fields(self) -> tuple[str, ...]:
        return (
            self.absolute_floor_mm.hex(),
            self.relative_ratio.hex(),
        )


@dataclass(frozen=True, order=True)
class ApertureCompatibilitySpec:
    """Gold-calibrated W/H compatibility method shared by all formats."""

    calibration_id: str
    width: ApertureAxisGuardSpec
    height: ApertureAxisGuardSpec
    development_source_count: int
    development_frame_count: int
    source_center_deviation_quantile: float
    absolute_rounding_mm: float
    relative_rounding_ratio: float

    def __post_init__(self) -> None:
        if not self.calibration_id:
            raise ValueError("aperture compatibility calibration needs an identity")
        if (
            self.development_source_count <= 0
            or self.development_frame_count < self.development_source_count
            or not 0.0 < self.source_center_deviation_quantile < 1.0
        ):
            raise ValueError("aperture compatibility calibration is invalid")
        require_positive(
            "absolute guard calibration rounding",
            self.absolute_rounding_mm,
        )
        if not 0.0 < self.relative_rounding_ratio < 1.0:
            raise ValueError("relative guard calibration rounding is invalid")

    @property
    def identity_fields(self) -> tuple[str, ...]:
        return (
            self.calibration_id,
            *self.width.identity_fields,
            *self.height.identity_fields,
            str(self.development_source_count),
            str(self.development_frame_count),
            self.source_center_deviation_quantile.hex(),
            self.absolute_rounding_mm.hex(),
            self.relative_rounding_ratio.hex(),
        )


APERTURE_COMPATIBILITY_SPEC = ApertureCompatibilitySpec(
    calibration_id=(
        "x5crop_aperture_compatibility:development_gold_source_center_deviation_"
        "q95_mixed_guard_outward_0p05mm_0p001ratio_v1"
    ),
    width=ApertureAxisGuardSpec(absolute_floor_mm=0.95, relative_ratio=0.024),
    height=ApertureAxisGuardSpec(absolute_floor_mm=0.70, relative_ratio=0.018),
    development_source_count=105,
    development_frame_count=494,
    source_center_deviation_quantile=0.95,
    absolute_rounding_mm=0.05,
    relative_rounding_ratio=0.001,
)


@dataclass(frozen=True, order=True)
class ApertureAspectRatioSpec:
    """Source-centred raw aperture W/H interval for one frame format."""

    calibration_id: str
    raw_width_over_height_minimum: float
    raw_width_over_height_maximum: float
    development_source_count: int
    development_frame_count: int

    def __post_init__(self) -> None:
        if not self.calibration_id:
            raise ValueError("aperture aspect-ratio calibration needs an identity")
        require_positive(
            "raw aperture aspect-ratio minimum",
            self.raw_width_over_height_minimum,
        )
        if (
            self.raw_width_over_height_maximum
            < self.raw_width_over_height_minimum
            or self.development_source_count <= 0
            or self.development_frame_count < self.development_source_count
        ):
            raise ValueError("aperture aspect-ratio calibration is invalid")

    def guarded_bounds(
        self,
        *,
        nominal_width_mm: float,
        nominal_height_mm: float,
    ) -> tuple[float, float]:
        width_guard = APERTURE_COMPATIBILITY_SPEC.width.relative_guard(
            nominal_width_mm
        )
        height_guard = APERTURE_COMPATIBILITY_SPEC.height.relative_guard(
            nominal_height_mm
        )
        return (
            self.raw_width_over_height_minimum
            * (1.0 - width_guard)
            / (1.0 + height_guard),
            self.raw_width_over_height_maximum
            * (1.0 + width_guard)
            / (1.0 - height_guard),
        )

    @property
    def identity_fields(self) -> tuple[str, ...]:
        return (
            self.calibration_id,
            self.raw_width_over_height_minimum.hex(),
            self.raw_width_over_height_maximum.hex(),
            str(self.development_source_count),
            str(self.development_frame_count),
        )


@dataclass(frozen=True, order=True)
class FramePhysicalSpec:
    """One format's design aperture and bounded cross-camera prior."""

    frame_width_mm: float
    frame_height_mm: float
    format_gap_prior_mm: float | None
    aperture_aspect_ratio: ApertureAspectRatioSpec | None = None

    def __post_init__(self) -> None:
        require_positive("frame design width", self.frame_width_mm)
        require_positive("frame design height", self.frame_height_mm)
        if self.format_gap_prior_mm is not None:
            require_positive("format gap search prior", self.format_gap_prior_mm)

    @property
    def width_factor_bounds(self) -> tuple[float, float]:
        return APERTURE_COMPATIBILITY_SPEC.width.factor_bounds(
            self.frame_width_mm
        )

    @property
    def height_factor_bounds(self) -> tuple[float, float]:
        return APERTURE_COMPATIBILITY_SPEC.height.factor_bounds(
            self.frame_height_mm
        )

    @property
    def identity_fields(self) -> tuple[str, ...]:
        return (
            self.frame_width_mm.hex(),
            self.frame_height_mm.hex(),
            "none"
            if self.format_gap_prior_mm is None
            else self.format_gap_prior_mm.hex(),
            *APERTURE_COMPATIBILITY_SPEC.identity_fields,
            *(
                ("aspect-ratio-unavailable",)
                if self.aperture_aspect_ratio is None
                else self.aperture_aspect_ratio.identity_fields
            ),
        )

    @property
    def frame_spec_id(self) -> str:
        return "frame-spec:" + ":".join(self.identity_fields)


@dataclass(frozen=True, order=True)
class OutputProtectionSpec:
    """One product policy for bleed and automatic-output limits.

    Bleed is deterministic output geometry.  It is not measurement evidence
    and never helps select a placement.  The five-percent limit is applied to
    the complete selected-output requirement on each aperture side.  A
    directly observed enclosing support pair has its own total-height limit
    and receives no additional cross-axis bleed.
    """

    sequence_bleed_minimum_mm: float = 0.15
    sequence_bleed_frame_ratio: float = 0.007
    cross_bleed_mm: float = 0.25
    maximum_expansion_ratio_per_side: float = 0.05
    maximum_enclosing_support_height_ratio: float = 1.10

    def __post_init__(self) -> None:
        for name, value in (
            ("sequence minimum bleed", self.sequence_bleed_minimum_mm),
            ("cross bleed", self.cross_bleed_mm),
        ):
            require_positive(name, value)
        for name, value in (
            ("sequence bleed ratio", self.sequence_bleed_frame_ratio),
            ("maximum per-side expansion", self.maximum_expansion_ratio_per_side),
        ):
            if not 0.0 < value < 1.0:
                raise ValueError(f"{name} must be between zero and one")
        if not 1.0 < self.maximum_enclosing_support_height_ratio < 2.0:
            raise ValueError("enclosing-support height ratio must be between one and two")

    def sequence_bleed_mm(self, frame_width_mm: float) -> float:
        require_positive("frame width", frame_width_mm)
        return max(
            self.sequence_bleed_minimum_mm,
            self.sequence_bleed_frame_ratio * frame_width_mm,
        )


OUTPUT_PROTECTION_SPEC = OutputProtectionSpec()


@dataclass(frozen=True)
class ScanLayoutSpec:
    kind: str = "single_strip"
    lane_count: int = 1
    lane_format_id: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in {"single_strip", "dual_lane"}:
            raise ValueError(f"unsupported scan layout: {self.kind}")
        if self.kind == "dual_lane":
            if self.lane_count != 2 or not self.lane_format_id:
                raise ValueError(
                    "dual-lane authority requires exactly two identified lanes"
                )
        elif self.lane_count != 1 or self.lane_format_id is not None:
            raise ValueError("single-strip layout cannot declare lane geometry")


@dataclass(frozen=True, order=True)
class ScanCanvasFit:
    """Format-owned applicability and full count for one physical holder."""

    profile_id: str
    full_count: int

    def __post_init__(self) -> None:
        if not self.profile_id:
            raise ValueError("scan-canvas fit requires a profile identity")
        require_positive("scan-canvas full count", self.full_count)


@dataclass(frozen=True)
class FormatSpec:
    format_id: str
    frame: FramePhysicalSpec
    layout: ScanLayoutSpec
    scan_canvas_fits: tuple[ScanCanvasFit, ...]

    def __post_init__(self) -> None:
        if not self.format_id:
            raise ValueError("format identity must not be empty")
        profile_ids = tuple(item.profile_id for item in self.scan_canvas_fits)
        if not profile_ids or len(set(profile_ids)) != len(profile_ids):
            raise ValueError("format scan-canvas fits must be non-empty and unique")

    def holder_full_count(self, profile_id: str) -> int | None:
        return next(
            (
                item.full_count
                for item in self.scan_canvas_fits
                if item.profile_id == profile_id
            ),
            None,
        )

    @property
    def maximum_full_count(self) -> int:
        return max(item.full_count for item in self.scan_canvas_fits)

ASPECT_RATIO_CALIBRATION_METHOD = (
    "development_gold_source_median_direct_frame_and_design_hull_v1"
)


def _aspect_ratio_spec(
    format_id: str,
    minimum: float,
    maximum: float,
    *,
    source_count: int,
    frame_count: int,
) -> ApertureAspectRatioSpec:
    return ApertureAspectRatioSpec(
        calibration_id=(
            f"x5crop_aperture_aspect_ratio:{format_id}:"
            f"{ASPECT_RATIO_CALIBRATION_METHOD}"
        ),
        raw_width_over_height_minimum=minimum,
        raw_width_over_height_maximum=maximum,
        development_source_count=source_count,
        development_frame_count=frame_count,
    )


FRAME_135 = FramePhysicalSpec(
    36.0,
    24.0,
    2.0,
    aperture_aspect_ratio=_aspect_ratio_spec(
        "135",
        1.4644888926698973,
        1.5075456582394127,
        source_count=57,
        frame_count=289,
    ),
)


FORMAT_CATALOG_REVISION = "x5crop_format_catalog_v5"


_FORMAT_SPECS: dict[str, FormatSpec] = {
    "135": FormatSpec(
        "135",
        FRAME_135,
        ScanLayoutSpec(),
        (
            ScanCanvasFit("135_standard", 6),
            ScanCanvasFit("135_narrow", 6),
        ),
    ),
    "135-dual": FormatSpec(
        "135-dual",
        FRAME_135,
        ScanLayoutSpec("dual_lane", 2, "135"),
        (ScanCanvasFit("135_dual", 12),),
    ),
    "half": FormatSpec(
        "half",
        FramePhysicalSpec(
            18.0,
            24.0,
            1.0,
            aperture_aspect_ratio=_aspect_ratio_spec(
                "half",
                0.6987076104149175,
                0.75,
                source_count=14,
                frame_count=108,
            ),
        ),
        ScanLayoutSpec(),
        (
            ScanCanvasFit("135_standard", 12),
            ScanCanvasFit("135_narrow", 12),
        ),
    ),
    "xpan": FormatSpec(
        "xpan",
        FramePhysicalSpec(65.0, 24.0, 2.0),
        ScanLayoutSpec(),
        (
            ScanCanvasFit("135_standard", 3),
            ScanCanvasFit("135_narrow", 3),
        ),
    ),
    "120-645": FormatSpec(
        "120-645",
        FramePhysicalSpec(42.0, 56.0, None),
        ScanLayoutSpec(),
        (
            ScanCanvasFit("120_standard", 4),
            ScanCanvasFit("120_wide_224_5", 4),
            ScanCanvasFit("120_wide_223", 4),
            ScanCanvasFit("120_wide_188_5", 4),
        ),
    ),
    "120-66": FormatSpec(
        "120-66",
        FramePhysicalSpec(
            56.0,
            56.0,
            None,
            aperture_aspect_ratio=_aspect_ratio_spec(
                "120-66",
                0.9922863201007389,
                1.0081672375873374,
                source_count=31,
                frame_count=88,
            ),
        ),
        ScanLayoutSpec(),
        (
            ScanCanvasFit("120_standard", 3),
            ScanCanvasFit("120_wide_224_5", 3),
            ScanCanvasFit("120_wide_223", 3),
            ScanCanvasFit("120_wide_188_5", 3),
        ),
    ),
    "120-67": FormatSpec(
        "120-67",
        FramePhysicalSpec(
            70.0,
            56.0,
            None,
            aperture_aspect_ratio=_aspect_ratio_spec(
                "120-67",
                1.2211302564012225,
                1.25,
                source_count=3,
                frame_count=9,
            ),
        ),
        ScanLayoutSpec(),
        (
            ScanCanvasFit("120_standard", 3),
            ScanCanvasFit("120_wide_224_5", 3),
            ScanCanvasFit("120_wide_223", 3),
            ScanCanvasFit("120_wide_188_5", 2),
        ),
    ),
}

FORMATS = MappingProxyType(_FORMAT_SPECS)
FORMAT_CHOICES = tuple(FORMATS)


def format_spec(format_id: str) -> FormatSpec:
    return FORMATS[format_id]
