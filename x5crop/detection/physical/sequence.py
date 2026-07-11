from __future__ import annotations

from collections.abc import Iterable

import numpy as np

from ...domain import BoundaryObservation, MeasurementProvenance, SequenceHypothesis
from ...geometry.detection_parameters import BoundaryDetectionParameters
from .boundary import visible_sequence_and_crop_envelope
from .boundary_detection import boundary_observation_groups


def unique_sequence_hypotheses(
    candidates: Iterable[SequenceHypothesis],
) -> list[SequenceHypothesis]:
    seen: set[tuple[int, int, int, int, str, str]] = set()
    result: list[SequenceHypothesis] = []
    for candidate in candidates:
        box = candidate.crop_envelope.box
        key = (
            box.left,
            box.top,
            box.right,
            box.bottom,
            candidate.provenance.root_measurement,
            candidate.provenance.source,
        )
        if key in seen or not box.valid():
            continue
        seen.add(key)
        result.append(candidate)
    return result


def _proposal_from_observations(
    name: str,
    observations: tuple[BoundaryObservation, ...],
    gray: np.ndarray,
    parameters: BoundaryDetectionParameters,
) -> SequenceHypothesis | None:
    try:
        visible, envelope = visible_sequence_and_crop_envelope(
            observations,
            canvas_width=gray.shape[1],
            canvas_height=gray.shape[0],
        )
    except ValueError:
        return None
    box = envelope.box
    if (
        box.width < max(parameters.min_width_px, gray.shape[1] * parameters.min_width_ratio)
        or box.height
        < max(parameters.min_height_px, gray.shape[0] * parameters.min_height_ratio)
    ):
        return None
    roots = tuple(
        dict.fromkeys(
            observation.provenance.root_measurement
            for observation in observations
        )
    )
    return SequenceHypothesis(
        name=name,
        visible_sequence_span=visible,
        crop_envelope=envelope,
        strategy="boundary_led",
        provenance=MeasurementProvenance(
            root_measurement="boundary_observations",
            source=name,
            dependencies=roots,
            boundary_anchors=tuple(observation.side for observation in observations),
        ),
        boundary_observations=observations,
    )


def _mixed_safe_observations(
    groups: tuple[tuple[str, tuple[BoundaryObservation, ...]], ...],
) -> tuple[BoundaryObservation, ...]:
    measured = [
        observations for name, observations in groups if name != "full_canvas"
    ]
    canvas = {
        observation.side: observation
        for name, observations in groups
        if name == "full_canvas"
        for observation in observations
    }
    result: list[BoundaryObservation] = []
    for side in ("leading", "trailing", "top", "bottom"):
        candidates = tuple(
            observation
            for observations in measured
            for observation in observations
            if observation.side == side
        )
        if not candidates:
            result.append(canvas[side])
            continue
        if side in {"leading", "top"}:
            result.append(
                min(candidates, key=lambda item: item.position.minimum)
            )
        else:
            result.append(
                max(candidates, key=lambda item: item.position.maximum)
            )
    return tuple(result)


def base_sequence_span_candidates(
    gray: np.ndarray,
    parameters: BoundaryDetectionParameters,
) -> list[SequenceHypothesis]:
    groups = boundary_observation_groups(gray, parameters)
    proposals = [
        proposal
        for name, observations in groups
        if (
            proposal := _proposal_from_observations(
                name,
                observations,
                gray,
                parameters,
            )
        )
        is not None
    ]
    mixed = _proposal_from_observations(
        "mixed_safe_overcontain",
        _mixed_safe_observations(groups),
        gray,
        parameters,
    )
    if mixed is not None and any(
        observation.kind != "canvas_clip"
        for observation in mixed.boundary_observations
    ):
        proposals.append(mixed)
    return unique_sequence_hypotheses(proposals)
