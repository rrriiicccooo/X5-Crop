from __future__ import annotations

from dataclasses import dataclass

from ..domain import Box, PixelInterval


@dataclass(frozen=True)
class ContentRegionObservation:
    region: Box
    reliable_runs: tuple[tuple[int, int], ...]
    position_uncertainty_px: int
    guidance_runs: tuple[tuple[int, int], ...] = ()

    def __post_init__(self) -> None:
        if not self.region.valid():
            raise ValueError("content observation region must have positive extent")
        if self.position_uncertainty_px < 0:
            raise ValueError("content position uncertainty must be non-negative")
        for name, runs in (
            ("reliable", self.reliable_runs),
            ("guidance", self.guidance_runs),
        ):
            if any(
                not self.region.left <= start < end <= self.region.right
                for start, end in runs
            ):
                raise ValueError(
                    f"{name} content runs must fit their measurement region"
                )

    def uncovered_by(
        self,
        intervals: tuple[tuple[int, int], ...],
    ) -> tuple[tuple[int, int], ...]:
        return uncovered_content_runs(
            self.reliable_runs,
            intervals,
            position_uncertainty_px=self.position_uncertainty_px,
            bounds=(self.region.left, self.region.right),
        )

    def reliable_content_intersects(self, interval: PixelInterval) -> bool:
        uncertainty = self.position_uncertainty_px
        return any(
            float(start + uncertainty) < interval.maximum
            and float(end - uncertainty) > interval.minimum
            for start, end in self.reliable_runs
            if start + uncertainty < end - uncertainty
        )


def uncovered_content_runs(
    runs: tuple[tuple[int, int], ...],
    intervals: tuple[tuple[int, int], ...],
    *,
    position_uncertainty_px: int,
    bounds: tuple[int, int],
) -> tuple[tuple[int, int], ...]:
    coverage = _merged_coverage(
        intervals,
        position_uncertainty_px,
        bounds,
    )
    return tuple(
        segment
        for run in runs
        for segment in _interval_remainder(run, coverage)
    )


def _merged_coverage(
    intervals: tuple[tuple[int, int], ...],
    uncertainty_px: int,
    bounds: tuple[int, int],
) -> tuple[tuple[int, int], ...]:
    lower, upper = bounds
    merged: list[tuple[int, int]] = []
    for start, end in intervals:
        if not lower <= start < end <= upper:
            raise ValueError("content coverage intervals must fit the measured region")
        expanded = (
            max(lower, start - uncertainty_px),
            min(upper, end + uncertainty_px),
        )
        if merged and expanded[0] <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], expanded[1]))
        else:
            merged.append(expanded)
    return tuple(merged)


def _interval_remainder(
    interval: tuple[int, int],
    coverage: tuple[tuple[int, int], ...],
) -> tuple[tuple[int, int], ...]:
    start, end = interval
    cursor = start
    remainder: list[tuple[int, int]] = []
    for covered_start, covered_end in coverage:
        if covered_end <= cursor:
            continue
        if covered_start >= end:
            break
        if covered_start > cursor:
            remainder.append((cursor, min(end, covered_start)))
        cursor = max(cursor, covered_end)
        if cursor >= end:
            break
    if cursor < end:
        remainder.append((cursor, end))
    return tuple(remainder)
