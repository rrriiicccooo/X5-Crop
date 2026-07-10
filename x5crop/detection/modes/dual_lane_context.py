from __future__ import annotations

from dataclasses import dataclass

from ...formats import FormatPhysicalSpec
from ...policies.runtime.bundle import DetectionPolicyBundle
from ...policies.runtime.policy import DetectionPolicy


@dataclass(frozen=True)
class DualLaneDetectionContext:
    format_id: str
    format_spec: FormatPhysicalSpec
    lane_format_id: str
    lane_format_spec: FormatPhysicalSpec
    lane_policy: DetectionPolicy
    lane_count: int
    total_count: int


def build_dual_lane_context(
    policy: DetectionPolicy,
    policy_bundle: DetectionPolicyBundle,
) -> DualLaneDetectionContext:
    format_spec = policy_bundle.format_for(policy.format_id)
    lane_format = format_spec.lane_format_id
    if lane_format is None:
        raise ValueError(f"Dual-lane format {format_spec.name} has no lane format")
    lane_format_id = lane_format.value
    lane_format_spec = policy_bundle.format_for(lane_format_id)
    return DualLaneDetectionContext(
        format_id=policy.format_id,
        format_spec=format_spec,
        lane_format_id=lane_format_id,
        lane_format_spec=lane_format_spec,
        lane_policy=policy_bundle.policy_for(lane_format_id, "full"),
        lane_count=format_spec.lane_count,
        total_count=format_spec.default_count,
    )


__all__ = [
    "DualLaneDetectionContext",
    "build_dual_lane_context",
]
