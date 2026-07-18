from __future__ import annotations

from ..formats import FORMAT_CHOICES
from ..strip_modes import FULL, PARTIAL, STRIP_MODES
from .registry import get_detection_configuration


def configuration_consistency_issues() -> tuple[str, ...]:
    issues: list[str] = []
    for format_id in FORMAT_CHOICES:
        for strip_mode in STRIP_MODES:
            configuration = get_detection_configuration(format_id, strip_mode)
            spec = configuration.physical_spec
            if spec.format_id != format_id:
                issues.append(f"{format_id}/{strip_mode}: physical spec mismatch")
            expected_detector = (
                "dual_lane"
                if spec.layout.kind == "dual_lane" and strip_mode == FULL
                else "review_only"
                if spec.layout.kind == "dual_lane" and strip_mode == PARTIAL
                else "standard_strip"
            )
            if configuration.detector_kind != expected_detector:
                issues.append(f"{format_id}/{strip_mode}: detector mismatch")
    return tuple(issues)


def main() -> int:
    issues = configuration_consistency_issues()
    if issues:
        print("Configuration consistency check failed:")
        for issue in issues:
            print(issue)
        return 1
    total = len(FORMAT_CHOICES) * len(STRIP_MODES)
    print(f"Configuration consistency check passed for {total} format/mode pairs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
