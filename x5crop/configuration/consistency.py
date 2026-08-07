from __future__ import annotations

from ..formats import FORMAT_CHOICES, format_spec
from ..strip_modes import PARTIAL, STRIP_MODES
from .registry import get_detection_configuration


def configuration_consistency_issues() -> tuple[str, ...]:
    issues: list[str] = []
    for format_id in FORMAT_CHOICES:
        for strip_mode in STRIP_MODES:
            try:
                configuration = get_detection_configuration(
                    format_id,
                    strip_mode,
                )
            except ValueError:
                if (
                    strip_mode == PARTIAL
                    and not format_spec(format_id).strip.partial_mode_supported
                ):
                    continue
                issues.append(
                    f"{format_id}/{strip_mode}: configuration unavailable"
                )
                continue
            spec = configuration.physical_spec
            if spec.format_id != format_id:
                issues.append(f"{format_id}/{strip_mode}: physical spec mismatch")
            if (
                configuration.detector_kind
                != "v5_template_first_format_placement"
            ):
                issues.append(f"{format_id}/{strip_mode}: detector mismatch")
    return tuple(issues)


def main() -> int:
    issues = configuration_consistency_issues()
    if issues:
        print("Configuration consistency check failed:")
        for issue in issues:
            print(issue)
        return 1
    total = sum(
        1
        for format_id in FORMAT_CHOICES
        for strip_mode in STRIP_MODES
        if not (
            strip_mode == PARTIAL
            and not format_spec(format_id).strip.partial_mode_supported
        )
    )
    print(f"Configuration consistency check passed for {total} format/mode pairs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
