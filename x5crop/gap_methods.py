from __future__ import annotations

from .constants import (
    GAP_CONTENT,
    GAP_DETECTED,
    GAP_EDGE_PAIR,
    GAP_EQUAL,
    GAP_GRID,
    HARD_GAP_METHODS,
    MODEL_GAP_METHODS,
)

DIRECT_HARD_GAP_METHODS = frozenset({GAP_DETECTED, GAP_EDGE_PAIR})
GEOMETRY_MODEL_GAP_METHODS = frozenset({GAP_GRID, GAP_EQUAL})
SEPARATOR_SUPPORT_GAP_METHODS = frozenset(set(HARD_GAP_METHODS) | {GAP_GRID})


def is_direct_hard_gap_method(method: str) -> bool:
    return method in DIRECT_HARD_GAP_METHODS


def is_detected_gap_method(method: str) -> bool:
    return method == GAP_DETECTED


def is_edge_pair_gap_method(method: str) -> bool:
    return method == GAP_EDGE_PAIR


def is_hard_gap_method(method: str) -> bool:
    return method in HARD_GAP_METHODS


def is_model_gap_method(method: str) -> bool:
    return method in MODEL_GAP_METHODS


def is_geometry_model_gap_method(method: str) -> bool:
    return method in GEOMETRY_MODEL_GAP_METHODS


def is_grid_model_gap_method(method: str) -> bool:
    return method == GAP_GRID


def is_equal_model_gap_method(method: str) -> bool:
    return method == GAP_EQUAL


def is_content_model_gap_method(method: str) -> bool:
    return method == GAP_CONTENT


def is_separator_support_gap_method(method: str) -> bool:
    return method in SEPARATOR_SUPPORT_GAP_METHODS


def gap_method_role(method: str) -> str:
    if is_direct_hard_gap_method(method):
        return "separator_evidence"
    if is_geometry_model_gap_method(method):
        return "geometry_model"
    if is_content_model_gap_method(method):
        return "content_model"
    return "unknown"


def gap_method_roles() -> dict[str, str]:
    return {
        GAP_DETECTED: gap_method_role(GAP_DETECTED),
        GAP_EDGE_PAIR: gap_method_role(GAP_EDGE_PAIR),
        GAP_GRID: gap_method_role(GAP_GRID),
        GAP_EQUAL: gap_method_role(GAP_EQUAL),
        GAP_CONTENT: gap_method_role(GAP_CONTENT),
    }


__all__ = [
    "DIRECT_HARD_GAP_METHODS",
    "GEOMETRY_MODEL_GAP_METHODS",
    "SEPARATOR_SUPPORT_GAP_METHODS",
    "gap_method_role",
    "gap_method_roles",
    "is_content_model_gap_method",
    "is_detected_gap_method",
    "is_direct_hard_gap_method",
    "is_edge_pair_gap_method",
    "is_equal_model_gap_method",
    "is_geometry_model_gap_method",
    "is_grid_model_gap_method",
    "is_hard_gap_method",
    "is_model_gap_method",
    "is_separator_support_gap_method",
]
