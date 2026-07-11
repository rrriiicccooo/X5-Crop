from __future__ import annotations

from .constants import (
    GAP_DETECTED,
    GAP_EQUAL,
    HARD_GAP_METHODS,
    MODEL_GAP_METHODS,
)

GEOMETRY_MODEL_GAP_METHODS = frozenset({GAP_EQUAL})


def is_detected_gap_method(method: str) -> bool:
    return method == GAP_DETECTED


def is_hard_gap_method(method: str) -> bool:
    return method in HARD_GAP_METHODS


def is_model_gap_method(method: str) -> bool:
    return method in MODEL_GAP_METHODS


def is_geometry_model_gap_method(method: str) -> bool:
    return method in GEOMETRY_MODEL_GAP_METHODS


def gap_method_role(method: str) -> str:
    if is_hard_gap_method(method):
        return "separator_evidence"
    if is_geometry_model_gap_method(method):
        return "geometry_model"
    return "unknown"
