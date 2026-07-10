from __future__ import annotations

from dataclasses import dataclass

from ...policies.runtime.bundle import DetectionPolicyBundle
from ...policies.runtime.policy import DetectionPolicy


@dataclass(frozen=True)
class DualLaneDetectionContext:
    policy: DetectionPolicy
    lane_policy: DetectionPolicy


def build_dual_lane_context(
    policy: DetectionPolicy,
    policy_bundle: DetectionPolicyBundle,
) -> DualLaneDetectionContext:
    format_spec = policy.physical_spec
    lane_format = format_spec.lane_format_id
    if lane_format is None:
        raise ValueError(f"Dual-lane format {format_spec.format_id} has no lane format")
    lane_format_id = lane_format
    lane_policy = policy_bundle.policy_for(lane_format_id, "full")
    return DualLaneDetectionContext(
        policy=policy,
        lane_policy=lane_policy,
    )
