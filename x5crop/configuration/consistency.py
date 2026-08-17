from __future__ import annotations

from ..formats import FORMAT_CHOICES
from .registry import get_detection_configuration


def configuration_consistency_issues() -> tuple[str, ...]:
    issues: list[str] = []
    for format_id in FORMAT_CHOICES:
        try:
            configuration = get_detection_configuration(format_id)
        except ValueError:
            issues.append(f"{format_id}: configuration unavailable")
            continue
        spec = configuration.physical_spec
        if spec.format_id != format_id:
            issues.append(f"{format_id}: physical spec mismatch")
        if configuration.detector_kind != "v5_bounded_template_placement":
            issues.append(f"{format_id}: detector mismatch")
    return tuple(issues)


def main() -> int:
    issues = configuration_consistency_issues()
    if issues:
        print("Configuration consistency check failed:")
        for issue in issues:
            print(issue)
        return 1
    print(
        f"Configuration consistency check passed for "
        f"{len(FORMAT_CHOICES)} formats."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
