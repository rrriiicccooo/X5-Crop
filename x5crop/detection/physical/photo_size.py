from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from ...domain import Gap
from ...geometry.gap_geometry import (
    photo_widths_from_gap_edges,
    separator_widths,
    width_cv,
)
from ...geometry.separator_band import SeparatorBand


@dataclass(frozen=True)
class PhotoSizeConsistency:
    used: bool
    reason: str
    photo_widths: tuple[float, ...] = ()
    separator_widths: tuple[float, ...] = ()
    target_photo_width: float | None = None
    photo_width_cv: float | None = None
    separator_width_cv: float | None = None
    mean_photo_width_error_ratio: float | None = None
    max_photo_width_error_ratio: float | None = None

    def detail(self) -> dict[str, Any]:
        return {
            "used": bool(self.used),
            "reason": self.reason,
            "physical_rule": "photo_size_consistent_separator_width_variable",
            "photo_widths": [float(width) for width in self.photo_widths],
            "separator_widths": [float(width) for width in self.separator_widths],
            "target_photo_width": (
                None if self.target_photo_width is None else float(self.target_photo_width)
            ),
            "photo_width_cv": (
                None if self.photo_width_cv is None else float(self.photo_width_cv)
            ),
            "separator_width_cv": (
                None if self.separator_width_cv is None else float(self.separator_width_cv)
            ),
            "mean_photo_width_error_ratio": (
                None
                if self.mean_photo_width_error_ratio is None
                else float(self.mean_photo_width_error_ratio)
            ),
            "max_photo_width_error_ratio": (
                None
                if self.max_photo_width_error_ratio is None
                else float(self.max_photo_width_error_ratio)
            ),
            "separator_width_role": "observed_detail_not_stability_penalty",
        }

def _photo_width_error_ratios(
    widths: Sequence[float],
    target_photo_width: float | None,
) -> tuple[float | None, float | None]:
    if not widths or target_photo_width is None or target_photo_width <= 1.0:
        return None, None
    ratios = [
        abs(float(width) - float(target_photo_width)) / max(1.0, float(target_photo_width))
        for width in widths
    ]
    return float(sum(ratios) / len(ratios)), float(max(ratios))


def photo_size_consistency_from_gap_edges(
    gaps: list[Gap],
    origin: float,
    pitch: float,
    count: int,
    *,
    target_photo_width: float | None = None,
) -> PhotoSizeConsistency:
    if count <= 0 or pitch <= 0.0:
        return PhotoSizeConsistency(False, "invalid_count_or_pitch")
    photo_widths = photo_widths_from_gap_edges(gaps, origin, pitch, count)
    if photo_widths is None:
        return PhotoSizeConsistency(
            False,
            "incomplete_separator_edges",
            separator_widths=tuple(separator_widths(gaps)),
            target_photo_width=target_photo_width,
            separator_width_cv=width_cv(separator_widths(gaps)),
        )
    separator_values = tuple(separator_widths(gaps))
    mean_error, max_error = _photo_width_error_ratios(photo_widths, target_photo_width)
    return PhotoSizeConsistency(
        True,
        "ok",
        photo_widths=tuple(float(width) for width in photo_widths),
        separator_widths=separator_values,
        target_photo_width=target_photo_width,
        photo_width_cv=width_cv(photo_widths),
        separator_width_cv=width_cv(separator_values),
        mean_photo_width_error_ratio=mean_error,
        max_photo_width_error_ratio=max_error,
    )


def photo_size_consistency_from_separator_bands(
    bands: Sequence[SeparatorBand],
    *,
    target_photo_width: float,
) -> PhotoSizeConsistency:
    if len(bands) < 2:
        return PhotoSizeConsistency(
            False,
            "too_few_separator_bands",
            target_photo_width=target_photo_width,
            separator_widths=tuple(float(band.width) for band in bands),
        )
    photo_widths: list[float] = []
    previous = bands[0]
    for band in bands[1:]:
        width = float(band.start) - float(previous.end)
        if width <= 1.0:
            return PhotoSizeConsistency(
                False,
                "non_positive_photo_interval",
                target_photo_width=target_photo_width,
                separator_widths=tuple(float(item.width) for item in bands),
            )
        photo_widths.append(width)
        previous = band
    separator_values = tuple(float(band.width) for band in bands)
    mean_error, max_error = _photo_width_error_ratios(photo_widths, target_photo_width)
    return PhotoSizeConsistency(
        True,
        "ok",
        photo_widths=tuple(photo_widths),
        separator_widths=separator_values,
        target_photo_width=target_photo_width,
        photo_width_cv=width_cv(photo_widths),
        separator_width_cv=width_cv(separator_values),
        mean_photo_width_error_ratio=mean_error,
        max_photo_width_error_ratio=max_error,
    )
