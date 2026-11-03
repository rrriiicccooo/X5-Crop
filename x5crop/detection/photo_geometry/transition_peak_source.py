"""Immutable identity records for registered transition-peak sources.

The records in this module describe the physical source of a transition peak
and the deterministic grouping that was derived from it.  They deliberately
do not read pixels, perform measurements, or grant any role/output authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
import hashlib
import math
import re

from ...domain import WorkspaceExtent
from .model import BoundaryAxis


TRANSITION_PEAK_SOURCE_BASIS = "registered-u8-peak-source-v1"

_NATIVE_PEAK_GROUP_ID = re.compile(r"^native-peak-group:[0-9a-f]{64}$")


def _require_plain_string(value: object, name: str) -> None:
    if type(value) is not str:
        raise TypeError(f"{name} must be a string")


def _require_plain_int(value: object, name: str) -> None:
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")


def _require_plain_bool(value: object, name: str) -> None:
    if type(value) is not bool:
        raise TypeError(f"{name} must be a bool")


def _require_closed_domain(value: object, name: str) -> tuple[int, int]:
    if type(value) is not tuple or len(value) != 2:
        raise TypeError(f"{name} must be a two-item tuple")
    minimum, maximum = value
    _require_plain_int(minimum, f"{name} minimum")
    _require_plain_int(maximum, f"{name} maximum")
    if minimum > maximum:
        raise ValueError(f"{name} bounds are reversed")
    return minimum, maximum


def _source_and_trace_lengths(
    source_extent: WorkspaceExtent,
    boundary_axis: BoundaryAxis,
) -> tuple[int, int]:
    if boundary_axis == BoundaryAxis.X:
        return source_extent.width, source_extent.height
    return source_extent.height, source_extent.width


@dataclass(frozen=True)
class TransitionPeakTraceSource:
    """The immutable, source-local identity of one measured trace."""

    source_id: str
    source_extent: WorkspaceExtent
    boundary_axis: BoundaryAxis
    trace_coordinate_px: int
    normalization_domain_px: tuple[int, int]
    window_px: int
    gap_px: int
    gradient_z_minimum: float
    tone_or_texture_z_minimum: float
    signal_sha256: str
    basis: str = TRANSITION_PEAK_SOURCE_BASIS

    def __post_init__(self) -> None:
        _require_plain_string(self.source_id, "source_id")
        if not self.source_id:
            raise ValueError("source_id must be non-empty")
        if not isinstance(self.source_extent, WorkspaceExtent):
            raise TypeError("source_extent must be a WorkspaceExtent")
        if any(
            type(value) is not int
            for value in (self.source_extent.width, self.source_extent.height)
        ):
            raise TypeError("source extent dimensions must be integers")
        if not isinstance(self.boundary_axis, BoundaryAxis):
            raise TypeError("boundary_axis must be a BoundaryAxis")

        _require_plain_int(self.trace_coordinate_px, "trace_coordinate_px")
        normalization_domain = _require_closed_domain(
            self.normalization_domain_px,
            "normalization_domain_px",
        )
        _require_plain_int(self.window_px, "window_px")
        _require_plain_int(self.gap_px, "gap_px")
        if self.window_px <= 0 or self.gap_px <= 0:
            raise ValueError("registered peak kernels must be positive")

        for value, name in (
            (self.gradient_z_minimum, "gradient_z_minimum"),
            (self.tone_or_texture_z_minimum, "tone_or_texture_z_minimum"),
        ):
            if type(value) is not float:
                raise TypeError(f"{name} must be a float")
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")

        _require_plain_string(self.signal_sha256, "signal_sha256")
        if not re.fullmatch(r"[0-9a-f]{64}", self.signal_sha256):
            raise ValueError("signal_sha256 must be 64 lowercase hexadecimal characters")
        _require_plain_string(self.basis, "basis")
        if self.basis != TRANSITION_PEAK_SOURCE_BASIS:
            raise ValueError("transition peak source basis is not registered")

        source_length, trace_length = _source_and_trace_lengths(
            self.source_extent,
            self.boundary_axis,
        )
        if not 0 <= self.trace_coordinate_px < trace_length:
            raise ValueError("trace coordinate leaves the source trace axis")

        minimum, maximum = normalization_domain
        if minimum < 0 or maximum >= source_length:
            raise ValueError("normalization domain leaves the source axis")
        kernel_radius = self.window_px + self.gap_px
        # The registered trace uses a half-open ``arange`` upper bound.  Its
        # last real coordinate is therefore one before the right kernel stop,
        # even though the stop itself may equal the source length.
        if minimum < kernel_radius or maximum > source_length - kernel_radius - 1:
            raise ValueError(
                "normalization domain leaves the registered kernel observable range"
            )

    @cached_property
    def primitive_key(self) -> tuple[object, ...]:
        """All source identity fields as immutable primitive values."""

        return (
            self.source_id,
            self.source_extent.width,
            self.source_extent.height,
            self.boundary_axis.value,
            self.trace_coordinate_px,
            self.normalization_domain_px,
            self.window_px,
            self.gap_px,
            self.gradient_z_minimum,
            self.tone_or_texture_z_minimum,
            self.signal_sha256,
            self.basis,
        )

    @property
    def normalization_coordinate_count(self) -> int:
        minimum, maximum = self.normalization_domain_px
        return maximum - minimum + 1

    @property
    def retained_bytes(self) -> int:
        return 1024

    @property
    def signal_value_visit_count(self) -> int:
        return 5 * self.normalization_coordinate_count


def _validate_runs(
    value: object,
    group_domain: tuple[int, int],
) -> tuple[tuple[int, tuple[int, ...]], ...]:
    if type(value) is not tuple:
        raise TypeError("reliable_gradient_partitions must be a tuple")
    previous_sign: int | None = None
    previous_last: int | None = None
    validated: list[tuple[int, tuple[int, ...]]] = []
    for index, item in enumerate(value):
        if type(item) is not tuple or len(item) != 2:
            raise TypeError(f"gradient run {index} must be a sign and coordinates tuple")
        sign, coordinates = item
        _require_plain_int(sign, f"gradient run {index} sign")
        if sign not in {-1, 1}:
            raise ValueError("gradient run signs must be -1 or 1")
        if type(coordinates) is not tuple or not coordinates:
            raise ValueError("gradient runs must contain coordinates")
        if any(type(coordinate) is not int for coordinate in coordinates):
            raise TypeError("gradient run coordinates must be integers")
        if any(right <= left for left, right in zip(coordinates, coordinates[1:])):
            raise ValueError("gradient run coordinates must be strictly increasing")
        if coordinates[0] < group_domain[0] or coordinates[-1] > group_domain[1]:
            raise ValueError("gradient run leaves the credible group domain")
        if previous_sign is not None and sign == previous_sign:
            raise ValueError("adjacent gradient runs must have opposite signs")
        if previous_last is not None and coordinates[0] <= previous_last:
            raise ValueError("gradient runs must be ordered in source coordinates")
        previous_sign = sign
        previous_last = coordinates[-1]
        validated.append((sign, coordinates))
    return tuple(validated)


@dataclass(frozen=True)
class TransitionPeakGroupSource:
    """A deterministic group of candidate peaks from one trace source."""

    source: TransitionPeakTraceSource
    measurement_domain_px: tuple[int, int]
    credible_group_domain_px: tuple[int, int]
    reliable_gradient_partitions: tuple[tuple[int, tuple[int, ...]], ...]
    candidate_peak_coordinates_px: tuple[int, ...]
    selection_basis: str
    split_gradient_reversals: bool

    def __post_init__(self) -> None:
        if not isinstance(self.source, TransitionPeakTraceSource):
            raise TypeError("group source must be a TransitionPeakTraceSource")
        measurement_domain = _require_closed_domain(
            self.measurement_domain_px,
            "measurement_domain_px",
        )
        group_domain = _require_closed_domain(
            self.credible_group_domain_px,
            "credible_group_domain_px",
        )
        source_domain = self.source.normalization_domain_px
        if (
            measurement_domain[0] < source_domain[0]
            or measurement_domain[1] > source_domain[1]
        ):
            raise ValueError("measurement domain leaves the source normalization domain")
        if (
            group_domain[0] < measurement_domain[0]
            or group_domain[1] > measurement_domain[1]
        ):
            raise ValueError("credible group domain leaves the measurement domain")

        _require_plain_string(self.selection_basis, "selection_basis")
        if self.selection_basis not in {"gradient", "secondary"}:
            raise ValueError("selection_basis must be gradient or secondary")
        _require_plain_bool(
            self.split_gradient_reversals,
            "split_gradient_reversals",
        )
        runs = _validate_runs(
            self.reliable_gradient_partitions,
            group_domain,
        )

        if type(self.candidate_peak_coordinates_px) is not tuple:
            raise TypeError("candidate peak coordinates must be a tuple")
        candidates = self.candidate_peak_coordinates_px
        if not candidates:
            raise ValueError("a peak group requires at least one candidate")
        if any(type(coordinate) is not int for coordinate in candidates):
            raise TypeError("candidate peak coordinates must be integers")
        if any(right <= left for left, right in zip(candidates, candidates[1:])):
            raise ValueError("candidate peak coordinates must be strictly increasing")
        if candidates[0] < group_domain[0] or candidates[-1] > group_domain[1]:
            raise ValueError("candidate peak leaves the credible group domain")

        if self.selection_basis == "gradient":
            if not runs:
                raise ValueError("gradient selection requires reliable gradient runs")
            if self.split_gradient_reversals:
                if len(candidates) != len(runs):
                    raise ValueError(
                        "split gradient selection requires one candidate per run"
                    )
                if any(
                    candidate not in coordinates
                    for candidate, (_, coordinates) in zip(
                        candidates,
                        runs,
                        strict=True,
                    )
                ):
                    raise ValueError(
                        "split gradient selection requires one candidate in each run"
                    )
            elif len(candidates) != 1 or not any(
                candidates[0] in coordinates for _, coordinates in runs
            ):
                raise ValueError(
                    "unsplit gradient selection requires one reliable candidate"
                )
        else:
            if runs:
                raise ValueError("secondary selection cannot carry gradient runs")
            if len(candidates) != 1:
                raise ValueError("secondary selection requires one candidate")

    @property
    def complete(self) -> bool:
        view_minimum, view_maximum = self.measurement_domain_px
        group_minimum, group_maximum = self.credible_group_domain_px
        return group_minimum > view_minimum and group_maximum < view_maximum

    @cached_property
    def primitive_key(self) -> tuple[object, ...]:
        return (
            self.source.primitive_key,
            self.credible_group_domain_px,
            self.reliable_gradient_partitions,
            self.candidate_peak_coordinates_px,
            self.selection_basis,
            self.split_gradient_reversals,
        )

    @cached_property
    def primitive_id(self) -> str:
        digest = hashlib.sha256(repr(self.primitive_key).encode()).hexdigest()
        return f"native-peak-group:{digest}"

    @property
    def retained_bytes(self) -> int:
        run_coordinate_count = sum(
            len(coordinates) for _, coordinates in self.reliable_gradient_partitions
        )
        return 2048 + 256 * (
            run_coordinate_count + len(self.candidate_peak_coordinates_px)
        )

    @property
    def logical_value_visit_count(self) -> int:
        group_minimum, group_maximum = self.credible_group_domain_px
        group_coordinate_count = group_maximum - group_minimum + 1
        run_coordinate_count = sum(
            len(coordinates) for _, coordinates in self.reliable_gradient_partitions
        )
        return 32 + 8 * (
            group_coordinate_count
            + run_coordinate_count
            + len(self.candidate_peak_coordinates_px)
        )


@dataclass(frozen=True)
class TransitionPeakReference:
    """A reference to a candidate by its absolute source coordinate."""

    group_id: str
    candidate_ordinal: int
    source_coordinate_px: int
    polarity: int

    def __post_init__(self) -> None:
        _require_plain_string(self.group_id, "group_id")
        if _NATIVE_PEAK_GROUP_ID.fullmatch(self.group_id) is None:
            raise ValueError("group_id is not a native peak group identity")
        _require_plain_int(self.candidate_ordinal, "candidate_ordinal")
        _require_plain_int(self.source_coordinate_px, "source_coordinate_px")
        _require_plain_int(self.polarity, "polarity")
        if self.candidate_ordinal < 0:
            raise ValueError("candidate ordinal must be nonnegative")
        if self.source_coordinate_px < 0:
            raise ValueError("source coordinate must be nonnegative")
        if self.polarity not in {-1, 0, 1}:
            raise ValueError("peak polarity must be -1, 0, or 1")

    def validate_group(self, group: TransitionPeakGroupSource) -> None:
        """Validate this reference against its full immutable group record."""

        if not isinstance(group, TransitionPeakGroupSource):
            raise ValueError("peak reference requires a typed group source")
        if self.group_id != group.primitive_id:
            raise ValueError("peak reference group identity does not match")
        candidates = group.candidate_peak_coordinates_px
        if not 0 <= self.candidate_ordinal < len(candidates):
            raise ValueError("peak reference candidate ordinal leaves the group")
        if self.source_coordinate_px != candidates[self.candidate_ordinal]:
            raise ValueError("peak reference coordinate does not match its candidate")

        if group.selection_basis == "gradient":
            if group.split_gradient_reversals:
                sign, coordinates = group.reliable_gradient_partitions[
                    self.candidate_ordinal
                ]
                if (
                    self.source_coordinate_px not in coordinates
                    or self.polarity != sign
                ):
                    raise ValueError(
                        "gradient peak reference polarity is not supported"
                    )
                return
            matching_signs = {
                sign
                for sign, coordinates in group.reliable_gradient_partitions
                if self.source_coordinate_px in coordinates
            }
            if len(matching_signs) != 1 or self.polarity not in matching_signs:
                raise ValueError("gradient peak reference polarity is not supported")
        elif self.polarity != 0:
            raise ValueError("secondary peak reference cannot invent a gradient sign")

    @property
    def retained_bytes(self) -> int:
        return 512


def same_transition_peak(
    left_ref: TransitionPeakReference,
    left_group: TransitionPeakGroupSource,
    right_ref: TransitionPeakReference,
    right_group: TransitionPeakGroupSource,
) -> bool:
    """Return whether two complete records name one original source peak."""

    if not isinstance(left_ref, TransitionPeakReference):
        raise ValueError("left peak reference is not typed")
    if not isinstance(right_ref, TransitionPeakReference):
        raise ValueError("right peak reference is not typed")
    left_ref.validate_group(left_group)
    right_ref.validate_group(right_group)
    return (
        left_group.complete
        and right_group.complete
        and left_group.primitive_key == right_group.primitive_key
        and left_ref.source_coordinate_px == right_ref.source_coordinate_px
        and left_ref.candidate_ordinal == right_ref.candidate_ordinal
        and left_ref.polarity == right_ref.polarity
    )


__all__ = [
    "TRANSITION_PEAK_SOURCE_BASIS",
    "TransitionPeakTraceSource",
    "TransitionPeakGroupSource",
    "TransitionPeakReference",
    "same_transition_peak",
]
