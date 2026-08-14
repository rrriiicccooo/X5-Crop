"""Adapt measured transition regions into role-free axis profiles."""

from __future__ import annotations

from .model import (
    BoundaryRole,
    MINIMUM_INDEPENDENT_SUPPORT_REGIONS,
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
)
from .measurement_model import PhotoBoundaryTransition
from .line_observations import SideTransitionRegion
from .observation_types import BasicAxisProfile, ProfileRun


def _is_strict_majority(fraction: float) -> bool:
    return fraction > 1.0 - fraction


def _region_anchor_qualified(
    region: SideTransitionRegion,
    role: BoundaryRole,
) -> bool:
    if role not in {BoundaryRole.START, BoundaryRole.END}:
        return False
    spec = PHOTO_BOUNDARY_MEASUREMENT_SPEC
    role_preference = (
        region.left_background_preference_fraction
        if role == BoundaryRole.START
        else region.right_background_preference_fraction
    )
    return (
        not region.ambiguous
        and region.independent_support_region_count
        >= MINIMUM_INDEPENDENT_SUPPORT_REGIONS
        and region.mean_gradient_z >= spec.gradient_z_minimum
        and region.mean_tone_or_texture_z >= spec.tone_or_texture_z_minimum
        and _is_strict_majority(role_preference)
    )


def sequence_profile_from_regions(
    regions: tuple[SideTransitionRegion, ...],
    *,
    coordinate_count: int,
    transition_by_id: dict[str, PhotoBoundaryTransition],
) -> BasicAxisProfile:
    spec = PHOTO_BOUNDARY_MEASUREMENT_SPEC
    runs = tuple(
        sorted(
            (
                ProfileRun(
                    run_id=region.region_id,
                    coordinate_interval_px=region.position_interval_px,
                    transition_ids=region.transition_ids,
                    trace_coordinates_px=tuple(
                        sorted(
                            {
                                transition_by_id[
                                    str(identity)
                                ].trace_coordinate_px
                                for identity in region.transition_ids
                            }
                        )
                    ),
                    role_hint=None,
                    qualified_anchor_roles=tuple(
                        role
                        for role in (BoundaryRole.START, BoundaryRole.END)
                        if _region_anchor_qualified(region, role)
                    ),
                    support_fraction=(
                        region.trace_support_count / region.queried_trace_count
                    ),
                    continuous_support_fraction=region.continuous_support_fraction,
                    fit_residual_px=region.fit_residual_px,
                    evidence_strength=(
                        region.mean_gradient_z + region.mean_tone_or_texture_z
                    ),
                    pair_qualified=(
                        not region.ambiguous
                        and region.independent_support_region_count
                        >= MINIMUM_INDEPENDENT_SUPPORT_REGIONS
                        and region.mean_gradient_z >= spec.gradient_z_minimum
                        and region.mean_tone_or_texture_z
                        >= spec.tone_or_texture_z_minimum
                    ),
                )
                for region in regions
            ),
            key=lambda item: (item.coordinate_interval_px.center, item.run_id),
        )
    )
    traces = tuple(
        sorted({trace for run in runs for trace in run.trace_coordinates_px})
    )
    return BasicAxisProfile("sequence", coordinate_count, traces, runs)


def cross_profile_from_regions(
    top_regions: tuple[SideTransitionRegion, ...],
    bottom_regions: tuple[SideTransitionRegion, ...],
    *,
    coordinate_count: int,
    transition_by_id: dict[str, PhotoBoundaryTransition],
) -> BasicAxisProfile:
    values: list[ProfileRun] = []
    spec = PHOTO_BOUNDARY_MEASUREMENT_SPEC
    for role, regions in (
        (BoundaryRole.TOP, top_regions),
        (BoundaryRole.BOTTOM, bottom_regions),
    ):
        for region in regions:
            traces = tuple(
                sorted(
                    {
                        transition_by_id[str(identity)].trace_coordinate_px
                        for identity in region.transition_ids
                    }
                )
            )
            role_preference = (
                region.left_background_preference_fraction
                if role == BoundaryRole.TOP
                else region.right_background_preference_fraction
            )
            values.append(
                ProfileRun(
                    run_id=f"{role.value}:{region.region_id}",
                    coordinate_interval_px=region.position_interval_px,
                    transition_ids=region.transition_ids,
                    trace_coordinates_px=traces,
                    role_hint=role,
                    qualified_anchor_roles=(
                        (role,)
                        if (
                            not region.ambiguous
                            and region.independent_support_region_count
                            >= MINIMUM_INDEPENDENT_SUPPORT_REGIONS
                            and region.mean_gradient_z >= spec.gradient_z_minimum
                            and region.mean_tone_or_texture_z
                            >= spec.tone_or_texture_z_minimum
                            and _is_strict_majority(role_preference)
                        )
                        else ()
                    ),
                    support_fraction=(
                        region.trace_support_count / region.queried_trace_count
                    ),
                    continuous_support_fraction=region.continuous_support_fraction,
                    fit_residual_px=region.fit_residual_px,
                    evidence_strength=(
                        region.mean_gradient_z + region.mean_tone_or_texture_z
                    ),
                    pair_qualified=(
                        not region.ambiguous
                        and region.mean_gradient_z >= spec.gradient_z_minimum
                        and region.mean_tone_or_texture_z
                        >= spec.tone_or_texture_z_minimum
                    ),
                )
            )
    runs = tuple(
        sorted(
            values,
            key=lambda item: (item.coordinate_interval_px.center, item.run_id),
        )
    )
    traces = tuple(
        sorted({trace for run in runs for trace in run.trace_coordinates_px})
    )
    return BasicAxisProfile("cross", coordinate_count, traces, runs)
