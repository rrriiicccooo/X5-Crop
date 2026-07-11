from __future__ import annotations

import numpy as np

from ....domain import MeasurementProvenance
from ....geometry.detection_parameters import OuterBoxDetectionParameters
from ..boundary import (
    BoundaryObservation,
    visible_sequence_and_crop_envelope,
)
from .common import unique_sequence_span_proposals
from .side_boundary import boundary_observation_groups
from .types import SequenceHypothesis


def _proposal_from_observations(
    name: str,
    observations: tuple[BoundaryObservation, ...],
    gray: np.ndarray,
    parameters: OuterBoxDetectionParameters,
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
    return tuple(
        (
            min(
                (item for group in measured for item in group if item.side == side),
                key=lambda item: item.position.minimum,
            )
            if side in {"leading", "top"}
            else max(
                (item for group in measured for item in group if item.side == side),
                key=lambda item: item.position.maximum,
            )
        )
        for side in ("leading", "trailing", "top", "bottom")
    )


def base_sequence_span_candidates(
    gray: np.ndarray,
    parameters: OuterBoxDetectionParameters,
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
    if mixed is not None:
        proposals.append(mixed)
    return unique_sequence_span_proposals(proposals)
