"""Register the finite template inputs for one already measured lane."""

from __future__ import annotations

from dataclasses import dataclass

from ...configuration.model import HolderLayoutAuthority
from ...domain import FiniteInterval, PositiveInterval
from ...formats import FramePhysicalSpec
from .boundary_fitting import fit_format_bound_boundary_observation
from .measurement_model import PhotoBoundaryMeasurementSet
from .model import BoundaryAxis, BoundaryRole
from .observation_types import BasicAxisProfile
from .line_observations import PhotoBoundaryObservation
from .source_geometry import SourceScanGeometry, centered_short_axis_authority_px
from .template_cross import CrossRoleBinding
from .template_model import PhaseAuthority, TemplateSpec


def _add(left: FiniteInterval, right: FiniteInterval) -> FiniteInterval:
    return FiniteInterval(
        left.minimum + right.minimum,
        left.maximum + right.maximum,
    )


def template_spec_from_physical_authority(
    *,
    frame_spec: FramePhysicalSpec,
    source_geometry: SourceScanGeometry,
    width_scale_px_per_mm: PositiveInterval,
    count: int,
    holder_layout_authority: HolderLayoutAuthority,
) -> TemplateSpec:
    """Scale the user's fixed format once; observations only refine it."""

    width = source_geometry.width_state.extent_projection_px()
    height = source_geometry.height_state.extent_projection_px()
    if frame_spec.format_gap_prior_mm is None:
        gap = FiniteInterval(width.minimum * 0.02, width.maximum * 0.20)
    else:
        gap = FiniteInterval(
            frame_spec.format_gap_prior_mm * width_scale_px_per_mm.minimum,
            frame_spec.format_gap_prior_mm * width_scale_px_per_mm.maximum,
        )
    authority = (
        PhaseAuthority.FULL_CENTERED
        if holder_layout_authority
        == HolderLayoutAuthority.USER_CONFIRMED_FILLED_HOLDER_LAYOUT
        else PhaseAuthority.PARTIAL_FREE
    )
    return TemplateSpec(
        template_id=(
            f"template:{frame_spec.frame_spec_id}:{authority.value}:{count}"
        ),
        frame_width_px=width,
        frame_height_px=height,
        pitch_px=_add(width, gap),
        nominal_gap_px=gap,
        count=count,
        phase_authority=authority,
    )


@dataclass(frozen=True)
class RegisteredCrossEvidence:
    top_bindings: tuple[CrossRoleBinding, ...]
    bottom_bindings: tuple[CrossRoleBinding, ...]
    observations: tuple[PhotoBoundaryObservation, ...]

    def __post_init__(self) -> None:
        identities = tuple(item.observation_id for item in self.observations)
        if len(set(identities)) != len(identities):
            raise ValueError("cross observations must be registered once")


def register_cross_evidence(
    *,
    profile: BasicAxisProfile,
    top_measurement: PhotoBoundaryMeasurementSet,
    bottom_measurement: PhotoBoundaryMeasurementSet,
    width_axis: BoundaryAxis,
    height_axis: BoundaryAxis,
    height_scale_px_per_mm: PositiveInterval,
    lane_reference_trace_px: float,
    maximum_runs: int = 256,
) -> RegisteredCrossEvidence:
    """Fit every registered top/bottom run once, without placement queries."""

    if maximum_runs <= 0:
        raise ValueError("cross registration bound must be positive")
    qualified = tuple(
        run
        for run in profile.runs
        if run.role_hint in {BoundaryRole.TOP, BoundaryRole.BOTTOM}
        and (run.pair_qualified or run.anchor_qualified_for(run.role_hint))
    )
    if len(qualified) > maximum_runs:
        raise ValueError("cross registration bound exceeded")
    registered: dict[str, tuple[CrossRoleBinding, PhotoBoundaryObservation]] = {}
    for run in qualified:
        measurement = (
            top_measurement
            if run.role_hint == BoundaryRole.TOP
            else bottom_measurement
        )
        observation = fit_format_bound_boundary_observation(
            measurement,
            transition_ids=run.transition_ids,
            role=run.role_hint,
            source_axis_long=width_axis,
            boundary_axis_scale_px_per_mm=height_scale_px_per_mm,
            minimum_independent_support_regions=1,
        )
        if observation is None:
            continue
        binding = CrossRoleBinding.from_measurement(
            run,
            observation,
            lane_reference_trace_px=lane_reference_trace_px,
            boundary_axis=height_axis,
        )
        key = str(observation.observation_id)
        previous = registered.get(key)
        if previous is None or (
            binding.support_fraction,
            binding.continuous_support_fraction,
            -binding.fit_residual_px,
            binding.run_id,
        ) > (
            previous[0].support_fraction,
            previous[0].continuous_support_fraction,
            -previous[0].fit_residual_px,
            previous[0].run_id,
        ):
            registered[key] = (binding, observation)
    ordered = tuple(
        registered[key]
        for key in sorted(
            registered,
            key=lambda identity: (
                registered[identity][0].coordinate_interval_px.center,
                identity,
            ),
        )
    )
    return RegisteredCrossEvidence(
        top_bindings=tuple(
            binding
            for binding, _observation in ordered
            if binding.role == BoundaryRole.TOP
        ),
        bottom_bindings=tuple(
            binding
            for binding, _observation in ordered
            if binding.role == BoundaryRole.BOTTOM
        ),
        observations=tuple(observation for _binding, observation in ordered),
    )


def short_axis_center_authority(
    visible_authority_px: FiniteInterval,
    scale_authority_px_per_mm: PositiveInterval,
) -> FiniteInterval:
    return centered_short_axis_authority_px(
        visible_authority_px,
        scale_authority_px_per_mm,
    )


__all__ = [
    "RegisteredCrossEvidence",
    "register_cross_evidence",
    "short_axis_center_authority",
    "template_spec_from_physical_authority",
]
