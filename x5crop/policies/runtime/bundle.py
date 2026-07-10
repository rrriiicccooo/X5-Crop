from __future__ import annotations

from dataclasses import dataclass

from ...formats import FormatSpec, format_spec
from ..registry import get_detection_policy
from .policy import DetectionPolicy


@dataclass(frozen=True)
class DetectionPolicyBundle:
    initial_policy: DetectionPolicy
    resolved_policies: tuple[DetectionPolicy, ...]
    resolved_formats: tuple[FormatSpec, ...]

    @classmethod
    def for_format_mode(cls, format_id: str, strip_mode: str) -> "DetectionPolicyBundle":
        initial_format = format_spec(format_id)
        initial_policy = get_detection_policy(initial_format.name, strip_mode)
        policies = [initial_policy]
        formats = [initial_format]
        if initial_format.physical_layout == "dual_lane":
            lane_format_id = initial_format.lane_format_id
            if lane_format_id is None:
                raise ValueError(f"Dual-lane format {initial_format.name} has no lane format")
            lane_format = format_spec(lane_format_id)
            formats.append(lane_format)
            policies.append(get_detection_policy(lane_format.name, "full"))
        return cls(
            initial_policy=initial_policy,
            resolved_policies=tuple(policies),
            resolved_formats=tuple(formats),
        )

    def policy_for(self, format_id: str, strip_mode: str) -> DetectionPolicy:
        for policy in self.resolved_policies:
            if policy.format_id == format_id and policy.strip_mode == strip_mode:
                return policy
        raise KeyError(f"Unresolved detection policy: {format_id}/{strip_mode}")

    def format_for(self, format_id: str) -> FormatSpec:
        for spec in self.resolved_formats:
            if spec.name == format_id:
                return spec
        raise KeyError(f"Unresolved format spec: {format_id}")


__all__ = ["DetectionPolicyBundle"]
