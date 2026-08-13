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
    PositiveInterval,
)
from ...formats.scan_canvas import ScanCanvasPhysicalSpec
from ...formats import FormatSpec
from ...geometry.layout import is_horizontal_layout


class ScanCanvasOutcome(str, Enum):
    SUPPORTED = "supported"
    NOT_APPLICABLE = "not_applicable"
    ASPECT_CONTRADICTED = "aspect_contradicted"
    COMPETING_PROFILES_UNRESOLVED = "competing_profiles_unresolved"


@dataclass(frozen=True)
class CanvasAxisScaleIntervals:
    holder_profile_id: str
    width_axis_px_per_mm: PositiveInterval
    height_axis_px_per_mm: PositiveInterval
    source_width_axis: str
    source_height_axis: str

    def __post_init__(self) -> None:
        if not self.holder_profile_id:
            raise ValueError("canvas scale requires a holder-profile identity")
        if (
            self.source_width_axis not in {"x", "y"}
            or self.source_height_axis not in {"x", "y"}
            or self.source_width_axis == self.source_height_axis
        ):
            raise ValueError("photo width/height axes must map to distinct source axes")


@dataclass(frozen=True)
class ScanCanvasProfileMatch:
    profile: ScanCanvasPhysicalSpec
    aspect_error_ratio: float
    shared_scale_px_per_mm: PositiveInterval

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.aspect_error_ratio)
            or self.aspect_error_ratio < 0.0
        ):
            raise ValueError(
                "scan-canvas aspect error must be finite and non-negative"
            )


@dataclass(frozen=True)
class MatchedHolder:
    profile: ScanCanvasPhysicalSpec
    full_count: int
    aspect_error_ratio: float
    axis_scales: CanvasAxisScaleIntervals

    def __post_init__(self) -> None:
        if self.full_count <= 0:
            raise ValueError("matched holder requires positive full count")
        if self.axis_scales.holder_profile_id != self.profile.profile_id:
            raise ValueError("matched-holder scale authority disagrees")
        if not math.isfinite(self.aspect_error_ratio) or self.aspect_error_ratio < 0:
            raise ValueError("matched-holder aspect error is invalid")


@dataclass(frozen=True)
class ScanCanvasEvidence:
    outcome: ScanCanvasOutcome
    observed_long_axis_px: int
    observed_short_axis_px: int
    matches: tuple[ScanCanvasProfileMatch, ...]
    selected_profile: ScanCanvasPhysicalSpec | None
    axis_scales: CanvasAxisScaleIntervals | None
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
                not self.matches
                or self.selected_profile not in tuple(
                    match.profile for match in self.matches
                )
                or self.axis_scales is None
            ):
                raise ValueError(
                    "supported scan canvas requires a selected profile and scale"
                )
        elif self.selected_profile is not None or self.axis_scales is not None:
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
        dependencies=(),
        description="source scan-canvas physical profile observation",
    )
    if not configuration.profiles:
        return ScanCanvasEvidence(
            outcome=ScanCanvasOutcome.NOT_APPLICABLE,
            observed_long_axis_px=work_width_px,
            observed_short_axis_px=work_height_px,
            matches=(),
            selected_profile=None,
            axis_scales=None,
            provenance=provenance,
        )
    observed_aspect = float(work_width_px) / float(work_height_px)
    physical_tolerance = configuration.physical_extent_tolerance_ratio

    def _scale_interval(
        observed_px: int,
        nominal_mm: float,
    ) -> PositiveInterval:
        return PositiveInterval(
            float(observed_px)
            / (nominal_mm * (1.0 + physical_tolerance)),
            float(observed_px)
            / (nominal_mm * (1.0 - physical_tolerance)),
        )

    def _profile_match(
        profile: ScanCanvasPhysicalSpec,
    ) -> ScanCanvasProfileMatch | None:
        long_scale = _scale_interval(
            work_width_px,
            profile.long_axis_mm,
        )
        short_scale = _scale_interval(
            work_height_px,
            profile.short_axis_mm,
        )
        minimum = max(long_scale.minimum, short_scale.minimum)
        maximum = min(long_scale.maximum, short_scale.maximum)
        if minimum > maximum:
            return None
        return ScanCanvasProfileMatch(
            profile=profile,
            aspect_error_ratio=(
                abs(observed_aspect - profile.aspect) / profile.aspect
            ),
            shared_scale_px_per_mm=PositiveInterval(minimum, maximum),
        )

    matches = tuple(
        match
        for profile in configuration.profiles
        if (match := _profile_match(profile)) is not None
    )
    if not matches:
        return ScanCanvasEvidence(
            outcome=ScanCanvasOutcome.ASPECT_CONTRADICTED,
            observed_long_axis_px=work_width_px,
            observed_short_axis_px=work_height_px,
            matches=(),
            selected_profile=None,
            axis_scales=None,
            provenance=provenance,
        )
    ordered_matches = tuple(
        sorted(
            matches,
            key=lambda item: (
                item.aspect_error_ratio,
                item.profile.profile_id,
            ),
        )
    )
    selected = ordered_matches[0]
    if (
        len(ordered_matches) > 1
        and math.isclose(
            selected.aspect_error_ratio,
            ordered_matches[1].aspect_error_ratio,
            rel_tol=0.0,
            abs_tol=1.0e-12,
        )
    ):
        return ScanCanvasEvidence(
            outcome=ScanCanvasOutcome.COMPETING_PROFILES_UNRESOLVED,
            observed_long_axis_px=work_width_px,
            observed_short_axis_px=work_height_px,
            matches=matches,
            selected_profile=None,
            axis_scales=None,
            provenance=provenance,
        )
    profile = selected.profile
    return ScanCanvasEvidence(
        outcome=ScanCanvasOutcome.SUPPORTED,
        observed_long_axis_px=work_width_px,
        observed_short_axis_px=work_height_px,
        matches=matches,
        selected_profile=profile,
        axis_scales=CanvasAxisScaleIntervals(
            holder_profile_id=profile.profile_id,
            width_axis_px_per_mm=selected.shared_scale_px_per_mm,
            height_axis_px_per_mm=selected.shared_scale_px_per_mm,
            source_width_axis="x" if is_horizontal_layout(layout) else "y",
            source_height_axis="y" if is_horizontal_layout(layout) else "x",
        ),
        provenance=provenance,
    )


def matched_holder_from_evidence(
    evidence: ScanCanvasEvidence,
    format_spec: FormatSpec,
) -> MatchedHolder | None:
    if (
        evidence.outcome != ScanCanvasOutcome.SUPPORTED
        or evidence.selected_profile is None
        or evidence.axis_scales is None
    ):
        return None
    selected_match = next(
        (
            match
            for match in evidence.matches
            if match.profile == evidence.selected_profile
        ),
        None,
    )
    if selected_match is None:
        return None
    full_count = format_spec.holder_full_count(
        evidence.selected_profile.profile_id
    )
    if full_count is None:
        return None
    return MatchedHolder(
        profile=evidence.selected_profile,
        full_count=full_count,
        aspect_error_ratio=selected_match.aspect_error_ratio,
        axis_scales=evidence.axis_scales,
    )
