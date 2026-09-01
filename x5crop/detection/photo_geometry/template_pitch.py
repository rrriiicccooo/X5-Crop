"""Bounded source-pitch calibration from already bound template roles."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Sequence

from ...domain import FiniteInterval, ObservationId
from .interval_math import (
    intersect as _intersect,
    subtract as _subtract_interval,
)
from .model import BoundaryRole, SPATIAL_SUPPORT_REGION_COUNT
from .observation_types import BoundaryEdgeObservation, SeparatorBandObservation
from .template_model import (
    TemplateSpec,
    template_role_refinement_radius_px,
)
from .template_phase_model import PhaseFitResult, PhaseFitStatus


@dataclass(frozen=True)
class TemplatePitchCalibration:
    """One bounded source-pitch result and typed separator phase evidence."""

    template: TemplateSpec
    phase_authority_px: FiniteInterval | None
    phase_hypothesis_px: FiniteInterval | None
    direct_separator_ids: tuple[ObservationId, ...]
    pitch_observation_ids: tuple[ObservationId, ...]
    lattice_hypothesis_count: int
    bound_exceeded: bool

    def __post_init__(self) -> None:
        if not isinstance(self.template, TemplateSpec):
            raise TypeError("pitch calibration requires a template")
        if self.lattice_hypothesis_count < 0:
            raise ValueError("lattice hypothesis count cannot be negative")
        if len(set(self.direct_separator_ids)) != len(
            self.direct_separator_ids
        ):
            raise ValueError("separator calibration identities must be unique")
        if (
            len(set(self.pitch_observation_ids))
            != len(self.pitch_observation_ids)
            or any(
                not isinstance(identity, ObservationId)
                for identity in self.pitch_observation_ids
            )
        ):
            raise ValueError("pitch calibration identities must be unique and typed")
        for value, name in (
            (self.phase_authority_px, "phase authority"),
            (self.phase_hypothesis_px, "phase hypothesis"),
        ):
            if value is not None and not isinstance(value, FiniteInterval):
                raise TypeError(f"separator {name} must be a finite interval")
        if (
            self.phase_authority_px is not None
            and self.phase_hypothesis_px is not None
        ):
            raise ValueError("separator phase evidence must have one authority level")
        if self.phase_authority_px is not None and len(
            self.direct_separator_ids
        ) < 3:
            raise ValueError("separator phase authority needs three direct bands")
        if self.phase_hypothesis_px is not None and len(
            self.direct_separator_ids
        ) != 2:
            raise ValueError("separator phase hypothesis needs two direct bands")
        if (self.phase_authority_px is None and self.phase_hypothesis_px is None) != (
            not self.direct_separator_ids
        ):
            raise ValueError("separator phase identities require typed phase evidence")
        if self.bound_exceeded and (
            self.phase_authority_px is not None
            or self.phase_hypothesis_px is not None
            or self.direct_separator_ids
        ):
            raise ValueError("bounded-out pitch calibration cannot carry authority")


@dataclass(frozen=True)
class _SeparatorLatticeFit:
    pitch_px: FiniteInterval
    phase_px: FiniteInterval
    direct_separator_ids: tuple[ObservationId, ...]


def close_separator_phase_hypothesis(
    calibration: TemplatePitchCalibration,
    phase: PhaseFitResult,
) -> FiniteInterval | None:
    """Promote a two-band phase hypothesis only after independent closure.

    The two separator locations may own pitch, but their projected absolute
    phase is not self-authorizing.  It becomes authority only when a complete
    legal fit inside that interval binds another independent direct support.
    Three or more lattice locations already form their own closed authority.
    """

    if not isinstance(calibration, TemplatePitchCalibration):
        raise TypeError("separator phase closure requires pitch calibration")
    if not isinstance(phase, PhaseFitResult):
        raise TypeError("separator phase closure requires a phase fit")
    if calibration.phase_authority_px is not None:
        return calibration.phase_authority_px
    hypothesis = calibration.phase_hypothesis_px
    fit = phase.best
    if (
        hypothesis is None
        or phase.status != PhaseFitStatus.RESOLVED
        or fit is None
        or _intersect(
            hypothesis,
            fit.phase_lattice_fit.absolute_phase_interval_px,
        )
        is None
        or not set(fit.evidence_group_ids).difference(
            calibration.direct_separator_ids
        )
    ):
        return None
    return hypothesis


def _advance_interval(
    left: FiniteInterval,
    right: FiniteInterval,
    direction: int,
) -> FiniteInterval:
    if direction > 0:
        return FiniteInterval(
            right.minimum - left.maximum,
            right.maximum - left.minimum,
        )
    return FiniteInterval(
        left.minimum - right.maximum,
        left.maximum - right.minimum,
    )


def _separator_center_interval(
    band: SeparatorBandObservation,
    by_id: dict[ObservationId, BoundaryEdgeObservation],
) -> FiniteInterval:
    left = by_id.get(band.left_edge_observation_id)
    right = by_id.get(band.right_edge_observation_id)
    if left is None or right is None:
        raise ValueError("separator band references an unregistered edge")
    return FiniteInterval(
        (left.fit_position_interval_px.minimum + right.fit_position_interval_px.minimum)
        / 2.0,
        (left.fit_position_interval_px.maximum + right.fit_position_interval_px.maximum)
        / 2.0,
    )


def _axis_interval(interval: FiniteInterval, direction: int) -> FiniteInterval:
    if direction > 0:
        return interval
    return FiniteInterval(-interval.maximum, -interval.minimum)


def _scaled_interval(interval: FiniteInterval, factor: float) -> FiniteInterval:
    if factor < 0.0:
        raise ValueError("interval scale must be non-negative")
    return FiniteInterval(interval.minimum * factor, interval.maximum * factor)


def _independent_separator_centers(
    bands: Sequence[SeparatorBandObservation],
    by_id: dict[ObservationId, BoundaryEdgeObservation],
    *,
    maximum_normal_gap_px: float,
) -> tuple[tuple[ObservationId, FiniteInterval], ...]:
    """Collapse measurements of one material structure to one support fact.

    Bands that share either raw edge belong to the same physical structure.
    They may improve one location only when all measured center intervals
    intersect.  A contradictory component is not allowed to manufacture a
    broad center or several independent votes.
    """

    eligible = tuple(
        band
        for band in bands
        if (
            band.material_support_region_count
            >= SPATIAL_SUPPORT_REGION_COUNT
            and band.gap_interval_px.minimum <= maximum_normal_gap_px
        )
    )
    remaining = set(range(len(eligible)))
    result: list[tuple[ObservationId, FiniteInterval]] = []
    while remaining:
        component = {remaining.pop()}
        edge_ids = {
            eligible[index].left_edge_observation_id
            for index in component
        } | {
            eligible[index].right_edge_observation_id
            for index in component
        }
        changed = True
        while changed:
            changed = False
            for index in tuple(remaining):
                band = eligible[index]
                if not edge_ids.intersection(
                    (
                        band.left_edge_observation_id,
                        band.right_edge_observation_id,
                    )
                ):
                    continue
                remaining.remove(index)
                component.add(index)
                edge_ids.update(
                    (
                        band.left_edge_observation_id,
                        band.right_edge_observation_id,
                    )
                )
                changed = True
        ordered = tuple(sorted(component))
        center = _separator_center_interval(eligible[ordered[0]], by_id)
        for index in ordered[1:]:
            common = _intersect(
                center,
                _separator_center_interval(eligible[index], by_id),
            )
            if common is None:
                center = None
                break
            center = common
        if center is not None:
            result.append(
                (
                    min(
                        (eligible[index].observation_id for index in ordered),
                        key=str,
                    ),
                    center,
                )
            )
    return tuple(
        sorted(
            result,
            key=lambda item: (item[1].center, str(item[0])),
        )
    )


def _separator_lattice_pitch_interval(
    search_template: TemplateSpec,
    target_template: TemplateSpec,
    bands: Sequence[SeparatorBandObservation],
    by_id: dict[ObservationId, BoundaryEdgeObservation],
    holder_span_px: FiniteInterval | None,
    maximum_hypotheses: int,
) -> tuple[_SeparatorLatticeFit | None, int, bool]:
    """Measure one unlabelled separator lattice before final role binding.

    This is the release behavior expressed with V5 authority: direct material
    bands establish a bounded periodic lattice, the template supplies only the
    finite ordinal distances, and holder containment rejects impossible slot
    mappings.  Competing physical lattices remain unresolved; contrast,
    identity and the provisional placement cannot break the tie.
    """

    if target_template.count < 3 or len(bands) < 2:
        return None, 0, False
    search_pitch = (
        search_template.pitch_px.minimum + search_template.pitch_px.maximum
    ) / 2.0
    centers = _independent_separator_centers(
        bands,
        by_id,
        maximum_normal_gap_px=(
            search_template.gap_prior_px.maximum
            + template_role_refinement_radius_px(search_pitch)
        ),
    )
    if len(centers) < 2:
        return None, 0, False
    maximum_work = (
        len(centers)
        * max(0, len(centers) - 1)
        // 2
        * max(0, target_template.count - 1)
        * max(0, target_template.count - 2)
        // 2
    )
    if maximum_work > maximum_hypotheses:
        return None, maximum_work, True
    direction = target_template.direction
    holder_axis = (
        None if holder_span_px is None else _axis_interval(holder_span_px, direction)
    )
    width = FiniteInterval(
        target_template.frame_width_px.minimum,
        target_template.frame_width_px.maximum,
    )
    tolerance = width.maximum * 0.04
    pitch_search_radius = template_role_refinement_radius_px(
        search_pitch
    )
    hypotheses: list[
        tuple[FiniteInterval, FiniteInterval, tuple[ObservationId, ...]]
    ] = []
    for left_index, (left_id, left_center_px) in enumerate(centers[:-1]):
        source_left_center = _axis_interval(left_center_px, direction)
        for right_id, right_center_px in centers[left_index + 1 :]:
            source_right_center = _axis_interval(right_center_px, direction)
            left_center, right_center = sorted(
                (source_left_center, source_right_center),
                key=lambda interval: interval.center,
            )
            advance = _advance_interval(left_center, right_center, 1)
            for ordinal_advance in range(1, target_template.count - 1):
                measured = FiniteInterval(
                    advance.minimum / ordinal_advance,
                    advance.maximum / ordinal_advance,
                )
                if (
                    measured.minimum <= 0.0
                    or measured.maximum
                    < search_template.pitch_px.minimum - pitch_search_radius
                    or measured.minimum
                    > search_template.pitch_px.maximum + pitch_search_radius
                ):
                    continue
                pitch = measured
                for left_ordinal in range(
                    target_template.count - 1 - ordinal_advance
                ):
                    role_offset = _scaled_interval(
                        pitch,
                        left_ordinal + 0.5,
                    )
                    role_offset = FiniteInterval(
                        role_offset.minimum + width.minimum * 0.5,
                        role_offset.maximum + width.maximum * 0.5,
                    )
                    phase = _subtract_interval(left_center, role_offset)
                    if holder_axis is not None:
                        minimum_span = (
                            (target_template.count - 1) * pitch.minimum
                            + width.minimum
                        )
                        allowed_minimum = holder_axis.minimum - tolerance
                        allowed_maximum = (
                            holder_axis.maximum + tolerance - minimum_span
                        )
                        if allowed_maximum < allowed_minimum:
                            continue
                        allowed = FiniteInterval(
                            allowed_minimum,
                            allowed_maximum,
                        )
                        phase = _intersect(phase, allowed)
                        if phase is None:
                            continue
                    hypotheses.append(
                        (
                            pitch,
                            phase,
                            tuple(sorted((left_id, right_id), key=str)),
                        )
                    )
    if not hypotheses:
        return None, 0, False
    groups: list[
        tuple[FiniteInterval, FiniteInterval, tuple[ObservationId, ...]]
    ] = []
    for pitch, phase, support_ids in hypotheses:
        compatible = tuple(
            index
            for index, (group_pitch, group_phase, _ids) in enumerate(groups)
            if _intersect(pitch, group_pitch) is not None
            and _intersect(phase, group_phase) is not None
        )
        if len(compatible) > 1:
            return None, len(hypotheses), False
        if not compatible:
            groups.append((pitch, phase, support_ids))
            continue
        index = compatible[0]
        group_pitch, group_phase, group_ids = groups[index]
        common_pitch = _intersect(group_pitch, pitch)
        common_phase = _intersect(group_phase, phase)
        if common_pitch is None or common_phase is None:
            raise AssertionError("compatible lattice group lost its intersection")
        groups[index] = (
            common_pitch,
            common_phase,
            tuple(sorted(set(group_ids).union(support_ids), key=str)),
        )
    if len(groups) != 1:
        return None, len(hypotheses), False
    pitch, phase, support_ids = groups[0]
    return (
        _SeparatorLatticeFit(pitch, phase, support_ids),
        len(hypotheses),
        False,
    )


def _unique_supported_interval(
    values: Sequence[FiniteInterval],
) -> FiniteInterval | None:
    """Return the sole interval group supported at two physical adjacencies."""

    groups = {
        tuple(
            index
            for index, interval in enumerate(values)
            if interval.contains(point, epsilon=1.0e-9)
        )
        for interval in values
        for point in (interval.minimum, interval.maximum)
    }
    maximum_support = max(map(len, groups), default=0)
    winners = tuple(group for group in groups if len(group) == maximum_support)
    if maximum_support < 2 or len(winners) != 1:
        return None
    winner = winners[0]
    return FiniteInterval(
        max(values[index].minimum for index in winner),
        min(values[index].maximum for index in winner),
    )


def refine_placement_pitch_interval(
    bound_roles: Sequence[tuple[BoundaryRole, int, FiniteInterval]],
    *,
    canonical_pitch: float,
    pitch_authority: FiniteInterval,
    direction: int,
    prefixes: tuple[FiniteInterval, ...],
) -> FiniteInterval | None:
    """Narrow one placement's pitch uncertainty without changing its identity.

    Farthest START-to-START and END-to-END advances cancel fixed frame width.
    At most two relations are evaluated in one O(R) pass.  A relation that
    disagrees with the selected base pitch is left to bounded adjacency
    analysis instead of rejecting or recalibrating the placement here.
    """

    result = pitch_authority
    for boundary_role in (BoundaryRole.START, BoundaryRole.END):
        values = tuple(
            (slot_index, interval)
            for role, slot_index, interval in bound_roles
            if role == boundary_role
        )
        if len(values) < 2:
            continue
        left_slot, left = min(values, key=lambda item: item[0])
        right_slot, right = max(values, key=lambda item: item[0])
        slot_advance = right_slot - left_slot
        if slot_advance <= 0:
            continue
        observed = _advance_interval(left, right, direction)
        prefix_advance = _advance_interval(
            prefixes[left_slot],
            prefixes[right_slot],
            1,
        )
        candidate = FiniteInterval(
            (observed.minimum - prefix_advance.maximum) / slot_advance,
            (observed.maximum - prefix_advance.minimum) / slot_advance,
        )
        common = _intersect(pitch_authority, candidate)
        if common is None or not common.contains(
            canonical_pitch,
            epsilon=1.0e-7,
        ):
            continue
        common = _intersect(result, common)
        if common is None:
            return None
        result = common
    return result


def calibrate_template_source_pitch(
    template: TemplateSpec,
    phase: PhaseFitResult,
    observations: Sequence[BoundaryEdgeObservation],
    separator_bands: Sequence[SeparatorBandObservation] = (),
    *,
    holder_span_px: FiniteInterval | None = None,
    refine_from_bound_roles: bool = False,
    max_lattice_hypotheses: int = 16384,
) -> TemplatePitchCalibration:
    """Replace the format pitch prior only after two direct normal advances.

    Format gap remains the bounded search seed used by the provisional fit.
    Once two distinct adjacent slot relations support one source pitch, their
    common interval becomes the lane's measured pitch authority.  Each
    adjacency counts once even when both START and END observations exist.
    Discrete or conflicting groups leave the compiled template unchanged.
    """

    if (
        phase.template.count != template.count
        or phase.template.direction != template.direction
    ):
        raise ValueError("pitch calibration template identity disagrees")
    if max_lattice_hypotheses <= 0:
        raise ValueError("pitch lattice hypothesis bound must be positive")
    by_id = {item.observation_id: item for item in observations}
    separator_lattice, lattice_hypothesis_count, bound_exceeded = (
        _separator_lattice_pitch_interval(
            phase.template,
            template,
            separator_bands,
            by_id,
            holder_span_px,
            max_lattice_hypotheses,
        )
    )
    if bound_exceeded:
        return TemplatePitchCalibration(
            template=template,
            phase_authority_px=None,
            phase_hypothesis_px=None,
            direct_separator_ids=(),
            pitch_observation_ids=(),
            lattice_hypothesis_count=lattice_hypothesis_count,
            bound_exceeded=True,
        )
    band_pitch = (
        None if separator_lattice is None else separator_lattice.pitch_px
    )
    fit = phase.best
    if phase.status != PhaseFitStatus.RESOLVED or fit is None:
        role_pitch = None
    else:
        adjacency_intervals: list[FiniteInterval] = []
        for ordinal in range(template.count - 1):
            relations: list[FiniteInterval] = []
            for role_offset in (0, 1):
                left_id = fit.binding_observation_ids[2 * ordinal + role_offset]
                right_id = fit.binding_observation_ids[
                    2 * (ordinal + 1) + role_offset
                ]
                if left_id is None or right_id is None:
                    continue
                left = by_id.get(left_id)
                right = by_id.get(right_id)
                if left is None or right is None:
                    raise ValueError("bound pitch observation is not registered")
                measured = _advance_interval(
                    left.fit_position_interval_px,
                    right.fit_position_interval_px,
                    template.direction,
                )
                if measured.minimum <= 0.0:
                    continue
                relations.append(measured)
            if not relations:
                continue
            relation = relations[0]
            for other in relations[1:]:
                common = _intersect(relation, other)
                if common is None:
                    relation = None
                    break
                relation = common
            if relation is not None:
                adjacency_intervals.append(relation)
        role_pitch = _unique_supported_interval(adjacency_intervals)
    # A direct material lattice owns source pitch.  Role-based advances are a
    # secondary path only when no unique band lattice exists; a provisional
    # role assignment must not veto the material relation it was meant to
    # locate.
    if (
        refine_from_bound_roles
        and phase.status == PhaseFitStatus.RESOLVED
        and fit is not None
    ):
        measured_pitch = FiniteInterval(
            fit.pitch_fit.pitch_interval_px.minimum,
            fit.pitch_fit.pitch_interval_px.maximum,
        )
    elif band_pitch is not None:
        if (
            template.count <= 3
            or separator_lattice is not None
            and len(separator_lattice.direct_separator_ids) >= 3
        ):
            measured_pitch = band_pitch
        else:
            # Two locations in a longer strip establish phase but may straddle
            # one real local gap departure.  Keep the compiled pitch search
            # authority and let the now-correct global role binding refine it.
            measured_pitch = FiniteInterval(
                min(template.pitch_px.minimum, band_pitch.minimum),
                max(template.pitch_px.maximum, band_pitch.maximum),
            )
    else:
        measured_pitch = (
            None
            if lattice_hypothesis_count > 0
            else role_pitch
        )
    if measured_pitch is None:
        return TemplatePitchCalibration(
            template=template,
            phase_authority_px=None,
            phase_hypothesis_px=None,
            direct_separator_ids=(),
            pitch_observation_ids=(),
            lattice_hypothesis_count=lattice_hypothesis_count,
            bound_exceeded=False,
        )
    width = FiniteInterval(
        template.frame_width_px.minimum,
        template.frame_width_px.maximum,
    )
    gap = FiniteInterval(
        max(0.0, measured_pitch.minimum - width.maximum),
        max(0.0, measured_pitch.maximum - width.minimum),
    )
    if gap.maximum <= 0.0:
        return TemplatePitchCalibration(
            template=template,
            phase_authority_px=None,
            phase_hypothesis_px=None,
            direct_separator_ids=(),
            pitch_observation_ids=(),
            lattice_hypothesis_count=lattice_hypothesis_count,
            bound_exceeded=False,
        )
    calibrated = replace(
        template,
        pitch_px=measured_pitch,
        nominal_gap_px=gap,
        phase_lattice_authority=(
            template.phase_lattice_authority.with_period(measured_pitch)
        ),
    )
    # Two separator locations can own one bounded pitch lattice.  In a short
    # strip they also produce one finite phase hypothesis, but it remains
    # non-authoritative until another independent direct support closes a full
    # legal fit.  Three independent material locations form the first lattice
    # that may restrict absolute phase on its own.
    separator_owns_absolute_phase = (
        separator_lattice is not None
        and len(separator_lattice.direct_separator_ids) >= 3
    )
    separator_proposes_absolute_phase = (
        separator_lattice is not None
        and template.count <= 3
        and len(separator_lattice.direct_separator_ids) == 2
    )
    separator_phase = (
        None
        if separator_lattice is None
        else _axis_interval(separator_lattice.phase_px, template.direction)
    )
    separator_owns_pitch = (
        separator_lattice is not None
        and measured_pitch == band_pitch
    )
    return TemplatePitchCalibration(
        template=calibrated,
        phase_authority_px=(
            separator_phase if separator_owns_absolute_phase else None
        ),
        phase_hypothesis_px=(
            separator_phase if separator_proposes_absolute_phase else None
        ),
        direct_separator_ids=(
            ()
            if not (
                separator_owns_absolute_phase
                or separator_proposes_absolute_phase
            )
            else separator_lattice.direct_separator_ids
        ),
        pitch_observation_ids=(
            separator_lattice.direct_separator_ids
            if separator_owns_pitch
            else ()
        ),
        lattice_hypothesis_count=lattice_hypothesis_count,
        bound_exceeded=False,
    )
