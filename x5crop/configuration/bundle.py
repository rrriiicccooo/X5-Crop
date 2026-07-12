from __future__ import annotations

from dataclasses import dataclass

from .model import DetectionConfiguration
from .registry import get_detection_configuration


@dataclass(frozen=True)
class DetectionConfigurationBundle:
    initial_configuration: DetectionConfiguration
    resolved_configurations: tuple[DetectionConfiguration, ...]

    def __post_init__(self) -> None:
        if (
            not self.resolved_configurations
            or self.resolved_configurations[0] != self.initial_configuration
        ):
            raise ValueError(
                "configuration bundle must start with its initial configuration"
            )
        identities = tuple(
            configuration.configuration_id
            for configuration in self.resolved_configurations
        )
        if len(set(identities)) != len(identities):
            raise ValueError("configuration bundle identities must be unique")

    @classmethod
    def for_format_mode(
        cls,
        format_id: str,
        strip_mode: str,
    ) -> "DetectionConfigurationBundle":
        initial = get_detection_configuration(format_id, strip_mode)
        configurations = [initial]
        if initial.physical_spec.physical_layout == "dual_lane":
            lane_format_id = initial.physical_spec.lane_format_id
            if lane_format_id is None:
                raise ValueError(
                    f"Dual-lane format {format_id} has no lane format"
                )
            configurations.append(
                get_detection_configuration(lane_format_id, "full")
            )
        return cls(initial, tuple(configurations))

    def configuration_for(
        self,
        format_id: str,
        strip_mode: str,
    ) -> DetectionConfiguration:
        for configuration in self.resolved_configurations:
            if (
                configuration.physical_spec.format_id == format_id
                and configuration.strip_mode == strip_mode
            ):
                return configuration
        raise KeyError(
            f"Unresolved detection configuration: {format_id}/{strip_mode}"
        )
