from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from ...configuration.scan_canvas import ScanCanvasDetectionConfiguration
from ...domain import (
    EvidenceState,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
)
from ...formats.scan_canvas import ScanCanvasPhysicalSpec
from ...geometry.layout import is_horizontal_layout


class ScanCanvasOutcome(str, Enum):
    SUPPORTED = "supported"
    NOT_APPLICABLE = "not_applicable"
    ASPECT_CONTRADICTED = "aspect_contradicted"
    COMPETING_PROFILES_UNRESOLVED = "competing_profiles_unresolved"


@dataclass(frozen=True)
class CanvasPixelScale:
    long_axis_px_per_mm: float
    short_axis_px_per_mm: float
    source_long_axis: str

    def __post_init__(self) -> None:
        if any(
            not math.isfinite(value) or value <= 0.0
            for value in (
                self.long_axis_px_per_mm,
                self.short_axis_px_per_mm,
            )
        ):
            raise ValueError("canvas pixel scale must be finite and positive")
        if self.source_long_axis not in {"x", "y"}:
            raise ValueError("source long axis must be x or y")


@dataclass(frozen=True)
class ScanCanvasProfileMatch:
    profile: ScanCanvasPhysicalSpec
    aspect_error_ratio: float

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.aspect_error_ratio)
            or self.aspect_error_ratio < 0.0
        ):
            raise ValueError(
                "scan-canvas aspect error must be finite and non-negative"
            )


@dataclass(frozen=True)
class ScanCanvasEvidence:
    outcome: ScanCanvasOutcome
    observed_long_axis_px: int
    observed_short_axis_px: int
    matches: tuple[ScanCanvasProfileMatch, ...]
    selected_profile: ScanCanvasPhysicalSpec | None
    pixel_scale: CanvasPixelScale | None
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, ScanCanvasOutcome):
            raise TypeError("scan-canvas evidence requires a typed outcome")
        if min(
            self.observed_long_axis_px,
            self.observed_short_axis_px,
        ) <= 0:
            raise ValueError("scan-canvas evidence requires positive extents")
        match_ids = tuple(
            match.profile.profile_id for match in self.matches
        )
        if len(set(match_ids)) != len(match_ids):
            raise ValueError("scan-canvas profile matches must be unique")
        if self.outcome == ScanCanvasOutcome.SUPPORTED:
            if (
                len(self.matches) != 1
                or self.selected_profile != self.matches[0].profile
                or self.pixel_scale is None
            ):
                raise ValueError(
                    "supported scan canvas requires one profile and scale"
                )
        elif self.selected_profile is not None or self.pixel_scale is not None:
            raise ValueError(
                "unresolved scan canvas cannot claim a profile or scale"
            )
        if (
            self.outcome == ScanCanvasOutcome.NOT_APPLICABLE
            and self.matches
        ):
            raise ValueError(
                "not-applicable scan canvas cannot carry profile matches"
            )
        if (
            self.outcome == ScanCanvasOutcome.ASPECT_CONTRADICTED
            and self.matches
        ):
            raise ValueError(
                "contradicted scan canvas cannot carry accepted matches"
            )
        if (
            self.outcome
            == ScanCanvasOutcome.COMPETING_PROFILES_UNRESOLVED
            and len(self.matches) <= 1
        ):
            raise ValueError(
                "competing scan canvas requires multiple profile matches"
            )
        if (
            self.provenance.root_measurement
            != MeasurementIdentity.SCAN_CANVAS_GEOMETRY
        ):
            raise ValueError(
                "scan-canvas evidence requires scan-canvas provenance"
            )

    @property
    def state(self) -> EvidenceState:
        if self.outcome == ScanCanvasOutcome.SUPPORTED:
            return EvidenceState.SUPPORTED
        if self.outcome == ScanCanvasOutcome.NOT_APPLICABLE:
            return EvidenceState.NOT_APPLICABLE
        if self.outcome == ScanCanvasOutcome.ASPECT_CONTRADICTED:
            return EvidenceState.CONTRADICTED
        return EvidenceState.UNAVAILABLE


def observe_scan_canvas(
    work_width_px: int,
    work_height_px: int,
    layout: str,
    configuration: ScanCanvasDetectionConfiguration,
) -> ScanCanvasEvidence:
    if min(work_width_px, work_height_px) <= 0:
        raise ValueError("scan-canvas observation requires positive extents")
    provenance = MeasurementProvenance(
        root_measurement=MeasurementIdentity.SCAN_CANVAS_GEOMETRY,
        observation_id=ObservationId("source_scan_canvas"),
        dependencies=(
            MeasurementIdentity.CANVAS,
            MeasurementIdentity.FORMAT_PHYSICAL_SPEC,
        ),
        description="source scan-canvas physical profile observation",
    )
    if not configuration.profiles:
        return ScanCanvasEvidence(
            outcome=ScanCanvasOutcome.NOT_APPLICABLE,
            observed_long_axis_px=work_width_px,
            observed_short_axis_px=work_height_px,
            matches=(),
            selected_profile=None,
            pixel_scale=None,
            provenance=provenance,
        )
    observed_aspect = float(work_width_px) / float(work_height_px)
    matches = tuple(
        ScanCanvasProfileMatch(
            profile,
            abs(observed_aspect - profile.aspect) / profile.aspect,
        )
        for profile in configuration.profiles
        if (
            abs(observed_aspect - profile.aspect) / profile.aspect
            <= configuration.maximum_aspect_error_ratio
        )
    )
    if not matches:
        return ScanCanvasEvidence(
            outcome=ScanCanvasOutcome.ASPECT_CONTRADICTED,
            observed_long_axis_px=work_width_px,
            observed_short_axis_px=work_height_px,
            matches=(),
            selected_profile=None,
            pixel_scale=None,
            provenance=provenance,
        )
    if len(matches) > 1:
        return ScanCanvasEvidence(
            outcome=ScanCanvasOutcome.COMPETING_PROFILES_UNRESOLVED,
            observed_long_axis_px=work_width_px,
            observed_short_axis_px=work_height_px,
            matches=matches,
            selected_profile=None,
            pixel_scale=None,
            provenance=provenance,
        )
    profile = matches[0].profile
    return ScanCanvasEvidence(
        outcome=ScanCanvasOutcome.SUPPORTED,
        observed_long_axis_px=work_width_px,
        observed_short_axis_px=work_height_px,
        matches=matches,
        selected_profile=profile,
        pixel_scale=CanvasPixelScale(
            long_axis_px_per_mm=(
                float(work_width_px) / profile.long_axis_mm
            ),
            short_axis_px_per_mm=(
                float(work_height_px) / profile.short_axis_mm
            ),
            source_long_axis="x" if is_horizontal_layout(layout) else "y",
        ),
        provenance=provenance,
    )
