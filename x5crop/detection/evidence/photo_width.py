from __future__ import annotations

from typing import Any


PHOTO_WIDTH_SOURCE = "photo_edges"


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def width_cv_source(detail: dict[str, Any]) -> str:
    return str(detail.get("width_cv_source") or "unknown")


def photo_width_cv_from_detail(detail: dict[str, Any]) -> float | None:
    if width_cv_source(detail) != PHOTO_WIDTH_SOURCE:
        return None
    photo_width_cv = _optional_float(detail.get("photo_width_cv"))
    if photo_width_cv is not None:
        return photo_width_cv
    return _optional_float(detail.get("width_cv"))


def photo_width_stability_detail(
    detail: dict[str, Any],
    max_photo_width_cv: float,
    *,
    used_role: str,
    unavailable_role: str = "diagnostic_until_photo_edges",
) -> dict[str, Any]:
    photo_width_cv = photo_width_cv_from_detail(detail)
    source = width_cv_source(detail)
    width_cv = _optional_float(detail.get("width_cv"))
    if photo_width_cv is None:
        return {
            "used": False,
            "role": unavailable_role,
            "reason": "width_source_not_photo_edges",
            "width_cv": width_cv,
            "photo_width_cv": None,
            "width_cv_source": source,
            "max_photo_width_cv": float(max_photo_width_cv),
            "ok": True,
            "unstable": False,
        }
    ok = photo_width_cv <= float(max_photo_width_cv)
    return {
        "used": True,
        "role": used_role,
        "reason": "ok" if ok else "photo_width_unstable",
        "width_cv": float(width_cv if width_cv is not None else photo_width_cv),
        "photo_width_cv": float(photo_width_cv),
        "width_cv_source": PHOTO_WIDTH_SOURCE,
        "max_photo_width_cv": float(max_photo_width_cv),
        "ok": bool(ok),
        "unstable": not bool(ok),
    }


def photo_width_within_limit(
    detail: dict[str, Any],
    max_photo_width_cv: float,
    *,
    unavailable_ok: bool,
) -> bool:
    photo_width_cv = photo_width_cv_from_detail(detail)
    if photo_width_cv is None:
        return bool(unavailable_ok)
    return photo_width_cv <= float(max_photo_width_cv)


__all__ = [
    "PHOTO_WIDTH_SOURCE",
    "photo_width_cv_from_detail",
    "photo_width_stability_detail",
    "photo_width_within_limit",
    "width_cv_source",
]
