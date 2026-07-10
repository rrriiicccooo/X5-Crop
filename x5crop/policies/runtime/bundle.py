from __future__ import annotations

from dataclasses import dataclass

from ..registry import get_detection_policy
from .policy import DetectionPolicy


@dataclass(frozen=True)
class DetectionPolicyBundle:
    initial_policy: DetectionPolicy
    resolved_policies: tuple[DetectionPolicy, ...]

    @classmethod
    def for_format_mode(cls, format_id: str, strip_mode: str) -> "DetectionPolicyBundle":
        initial_policy = get_detection_policy(format_id, strip_mode)
        initial_format = initial_policy.physical_spec
        policies = [initial_policy]
        if initial_format.physical_layout == "dual_lane":
            lane_format_id = initial_format.lane_format_id
            if lane_format_id is None:
                raise ValueError(
                    f"Dual-lane format {initial_format.format_id.value} has no lane format"
                )
            policies.append(get_detection_policy(lane_format_id.value, "full"))
        return cls(
            initial_policy=initial_policy,
            resolved_policies=tuple(policies),
        )

    def policy_for(self, format_id: str, strip_mode: str) -> DetectionPolicy:
        for policy in self.resolved_policies:
            if policy.physical_spec.format_id.value == format_id and policy.strip_mode == strip_mode:
                return policy
        raise KeyError(f"Unresolved detection policy: {format_id}/{strip_mode}")
