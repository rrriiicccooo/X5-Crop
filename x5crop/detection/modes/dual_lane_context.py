from __future__ import annotations

from dataclasses import dataclass

from ...formats import FORMATS, FormatSpec
from ...runtime.policy_context import RuntimePolicyContext
from ...policies.runtime.policy import DetectionPolicy


@dataclass(frozen=True)
class DualLaneDetectionContext:
    format_id: str
    format_spec: FormatSpec
    lane_format_id: str
    lane_format_spec: FormatSpec
    lane_policy: DetectionPolicy
    lane_count: int
    total_count: int


def build_dual_lane_context(
    policy: DetectionPolicy,
    policy_context: RuntimePolicyContext,
) -> DualLaneDetectionContext:
    lane_format_id = policy.detector.dual_lane.lane_format
    format_spec = FORMATS[policy.format_id]
    lane_format_spec = FORMATS[lane_format_id]
    return DualLaneDetectionContext(
        format_id=policy.format_id,
        format_spec=format_spec,
        lane_format_id=lane_format_id,
        lane_format_spec=lane_format_spec,
        lane_policy=policy_context.policy_for(lane_format_id, "full"),
        lane_count=policy.detector.dual_lane.lane_count,
        total_count=format_spec.default_count,
    )


__all__ = [
    "DualLaneDetectionContext",
    "build_dual_lane_context",
]
