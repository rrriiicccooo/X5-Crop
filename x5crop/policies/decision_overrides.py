from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .runtime_policy import DetectionPolicy


EVIDENCE_POLICY_OVERRIDES: dict[str, dict[str, Any]] = {
    "135": {
        "min_hard_separator_ratio": 0.35,
        "min_hard_separator_count": 2,
        "max_width_cv_ratio": 0.030,
        "max_model_gap_share": 0.70,
    },
    "135-dual": {
        "min_hard_separator_ratio": 0.50,
        "min_hard_separator_count": 2,
        "max_width_cv_ratio": 0.035,
    },
    "half": {
        "min_hard_separator_ratio": 0.55,
        "min_hard_separator_count": 2,
        "max_width_cv_ratio": 0.012,
        "allow_geometry_supported_separator": True,
        "geometry_supported_min_hard_ratio": 0.20,
        "geometry_supported_max_width_cv_ratio": 0.010,
        "max_outer_area_ratio": 0.990,
    },
    "xpan": {
        "min_hard_separator_ratio": 0.67,
        "min_hard_separator_count": 1,
        "max_width_cv_ratio": 0.035,
    },
    "120-645": {
        "min_hard_separator_ratio": 0.67,
        "min_hard_separator_count": 2,
        "max_width_cv_ratio": 0.035,
    },
    "120-66": {
        "min_hard_separator_ratio": 0.90,
        "min_hard_separator_count": 2,
        "max_width_cv_ratio": 0.040,
        "max_outer_area_ratio": 0.990,
    },
    "120-67": {
        "min_hard_separator_ratio": 0.75,
        "min_hard_separator_count": 2,
        "max_width_cv_ratio": 0.040,
    },
}


EVIDENCE_POLICY_MODE_OVERRIDES: dict[tuple[str, str], dict[str, Any]] = {}


def evidence_policy_values(
    format_id: str,
    strip_mode: str,
    defaults: Any,
    detection_policy: DetectionPolicy | None = None,
) -> dict[str, Any]:
    values = dict(EVIDENCE_POLICY_OVERRIDES.get(format_id, {}))
    if strip_mode == "partial":
        values.update(
            {
                "min_hard_separator_ratio": min(
                    float(values.get("min_hard_separator_ratio", defaults.min_hard_separator_ratio)),
                    0.35,
                ),
                "max_width_cv_ratio": max(
                    float(values.get("max_width_cv_ratio", defaults.max_width_cv_ratio)),
                    0.045,
                ),
                "max_outer_area_ratio": max(
                    float(values.get("max_outer_area_ratio", defaults.max_outer_area_ratio)),
                    0.990,
                ),
                "partial_requires_safe_edge": True,
            }
        )
    else:
        values["partial_requires_safe_edge"] = False
    values.update(EVIDENCE_POLICY_MODE_OVERRIDES.get((format_id, strip_mode), {}))
    if detection_policy is not None:
        values["allow_geometry_supported_separator"] = bool(detection_policy.separator.geometry_support_modes)
        values["partial_requires_safe_edge"] = detection_policy.strip_mode == "partial"
    return values


__all__ = [
    "EVIDENCE_POLICY_OVERRIDES",
    "EVIDENCE_POLICY_MODE_OVERRIDES",
    "evidence_policy_values",
]
