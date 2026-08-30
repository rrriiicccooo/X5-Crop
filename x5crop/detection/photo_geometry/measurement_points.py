"""Shared point contract for transition tracking and robust line fitting."""

from __future__ import annotations

from dataclasses import dataclass

from .measurement_model import SequenceTransitionObservation


@dataclass(frozen=True)
class TransitionPoint:
    transition: SequenceTransitionObservation
    trace: float
    coordinate: float
