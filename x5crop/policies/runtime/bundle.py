from __future__ import annotations

from dataclasses import dataclass

from ..registry import get_detection_policy
from .policy import DetectionPolicy


@dataclass(frozen=True)
class DetectionPolicyBundle:
    initial_policy: DetectionPolicy

    @classmethod
    def for_format_mode(cls, format_id: str, strip_mode: str) -> "DetectionPolicyBundle":
        return cls(initial_policy=get_detection_policy(format_id, strip_mode))

    def policy_for(self, format_id: str, strip_mode: str) -> DetectionPolicy:
        return get_detection_policy(format_id, strip_mode)


__all__ = ["DetectionPolicyBundle"]
