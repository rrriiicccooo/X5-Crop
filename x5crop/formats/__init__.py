from __future__ import annotations

from dataclasses import dataclass

from ..utils import require_positive

@dataclass(frozen=True)
class FrameSizeMm:
    width_mm: float
    height_mm: float
    label: str = "nominal"

    def __post_init__(self) -> None:
        require_positive("frame width", self.width_mm)
        require_positive("frame height", self.height_mm)
        if not self.label:
            raise ValueError("frame size label must not be empty")

    @property
    def aspect(self) -> float:
        return float(self.width_mm) / float(self.height_mm)


@dataclass(frozen=True)
class FormatPhysicalSpec:
    format_id: str
    default_count: int
    allowed_counts: tuple[int, ...]
    family: str
    frame_size_mm_options: tuple[FrameSizeMm, ...]
    physical_layout: str = "single_strip"
    complete_strip_can_be_underfilled: bool = False
    lane_count: int = 1
    lane_format_id: str | None = None

    def __post_init__(self) -> None:
        if not self.format_id or not self.family:
            raise ValueError("format identity and family must not be empty")
        require_positive("default frame count", self.default_count)
        if (
            not self.allowed_counts
            or tuple(sorted(set(self.allowed_counts))) != self.allowed_counts
            or any(count <= 0 for count in self.allowed_counts)
        ):
            raise ValueError("allowed frame counts must be positive, unique, and ordered")
        if self.default_count not in self.allowed_counts:
            raise ValueError("default frame count must be allowed")
        if not self.frame_size_mm_options:
            raise ValueError("format requires at least one physical frame size")
        if self.physical_layout not in {"single_strip", "dual_lane"}:
            raise ValueError(f"unsupported physical layout: {self.physical_layout}")
        if self.physical_layout == "dual_lane":
            if self.lane_count <= 1 or self.default_count % self.lane_count:
                raise ValueError("dual-lane count must divide into multiple equal lanes")
            if not self.lane_format_id:
                raise ValueError("dual-lane format requires a lane format identity")
        elif self.lane_count != 1 or self.lane_format_id is not None:
            raise ValueError("single-strip format cannot declare lane geometry")

    @property
    def nominal_frame_size_mm(self) -> FrameSizeMm:
        return self.frame_size_mm_options[0]

    @property
    def horizontal_content_aspect(self) -> float:
        return self.nominal_frame_size_mm.aspect

    @property
    def expected_separator_count(self) -> int:
        return expected_separator_count(
            self.default_count,
            self.physical_layout,
            self.lane_count,
        )

def expected_separator_count(
    default_count: int,
    physical_layout: str,
    lane_count: int,
) -> int:
    if default_count <= 0:
        raise ValueError("default frame count must be positive")
    if physical_layout == "dual_lane":
        if lane_count <= 1 or default_count % lane_count:
            raise ValueError("dual-lane frame count must divide evenly")
        lane_frame_count = int(default_count) // int(lane_count)
        return int(lane_count) * (lane_frame_count - 1)
    if physical_layout != "single_strip" or lane_count != 1:
        raise ValueError("single-strip separator count requires one lane")
    return int(default_count) - 1


def _format_spec(
    format_id: str,
    default_count: int,
    allowed_counts: tuple[int, ...],
    family: str,
    nominal_frame_size_mm: FrameSizeMm,
    *,
    lane_count: int,
    frame_size_mm_options: tuple[FrameSizeMm, ...] = (),
    physical_layout: str = "single_strip",
    complete_strip_can_be_underfilled: bool = False,
    lane_format_id: str | None = None,
) -> FormatPhysicalSpec:
    frame_options = frame_size_mm_options or (nominal_frame_size_mm,)
    return FormatPhysicalSpec(
        format_id=format_id,
        default_count=default_count,
        allowed_counts=allowed_counts,
        family=family,
        frame_size_mm_options=frame_options,
        physical_layout=physical_layout,
        complete_strip_can_be_underfilled=complete_strip_can_be_underfilled,
        lane_count=lane_count,
        lane_format_id=lane_format_id,
    )


FORMATS: dict[str, FormatPhysicalSpec] = {
    "135": _format_spec(
        "135",
        6,
        tuple(range(1, 7)),
        "35mm",
        FrameSizeMm(36.0, 24.0),
        lane_count=1,
    ),
    "135-dual": _format_spec(
        "135-dual",
        12,
        (12,),
        "35mm",
        FrameSizeMm(36.0, 24.0),
        physical_layout="dual_lane",
        lane_count=2,
        lane_format_id="135",
    ),
    "half": _format_spec(
        "half",
        12,
        tuple(range(1, 13)),
        "35mm",
        FrameSizeMm(18.0, 24.0),
        lane_count=1,
    ),
    "xpan": _format_spec(
        "xpan",
        3,
        (1, 2, 3),
        "35mm",
        FrameSizeMm(65.0, 24.0),
        lane_count=1,
        complete_strip_can_be_underfilled=True,
    ),
    "120-645": _format_spec(
        "120-645",
        4,
        (1, 2, 3, 4),
        "120",
        FrameSizeMm(42.0, 56.0),
        lane_count=1,
    ),
    "120-66": _format_spec(
        "120-66",
        3,
        (1, 2, 3),
        "120",
        FrameSizeMm(56.0, 56.0),
        lane_count=1,
        frame_size_mm_options=(
            FrameSizeMm(56.0, 56.0),
            FrameSizeMm(54.0, 54.0, label="camera_variant"),
        ),
        complete_strip_can_be_underfilled=True,
    ),
    "120-67": _format_spec(
        "120-67",
        3,
        (1, 2, 3),
        "120",
        FrameSizeMm(70.0, 56.0),
        lane_count=1,
    ),
}

FORMAT_CHOICES = tuple(FORMATS.keys())


def format_spec(format_id: str) -> FormatPhysicalSpec:
    return FORMATS[format_id]
