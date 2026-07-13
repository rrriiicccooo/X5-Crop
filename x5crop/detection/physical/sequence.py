from __future__ import annotations

from collections.abc import Iterable

import numpy as np
from ...domain import (
    BoundaryKind,
    BoundaryPathGroup,
    BoundaryPathObservation,
    BoundaryPathSource,
    BoundarySide,
    MeasurementIdentity,
    MeasurementProvenance,
    SequenceHypothesis,
)
from .boundary import visible_sequence_and_crop_envelope


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


def _proposal_from_paths(
    source: str,
    paths: tuple[BoundaryPathObservation, ...],
    gray: np.ndarray,
) -> SequenceHypothesis | None:
    try:
        visible, envelope = visible_sequence_and_crop_envelope(
            paths,
            canvas_width=gray.shape[1],
            canvas_height=gray.shape[0],
        )
    except ValueError:
        return None
    roots = tuple(
        dict.fromkeys(
            path.provenance.root_measurement
            for path in paths
        )
    )
    return SequenceHypothesis(
        visible_sequence_span=visible,
        crop_envelope=envelope,
        provenance=MeasurementProvenance(
            root_measurement=MeasurementIdentity.BOUNDARY_PATHS,
            source=source,
            dependencies=roots,
            boundary_anchors=tuple(path.side for path in paths),
        ),
        boundary_paths=paths,
    )


def _mixed_safe_paths(
    groups: tuple[BoundaryPathGroup, ...],
) -> tuple[BoundaryPathObservation, ...]:
    measured = [
        group.paths
        for group in groups
        if group.source != BoundaryPathSource.FULL_CANVAS
    ]
    canvas = {
        path.side: path
        for group in groups
        if group.source == BoundaryPathSource.FULL_CANVAS
        for path in group.paths
    }
    result: list[BoundaryPathObservation] = []
    for side in BoundarySide:
        candidates = tuple(
            path
            for paths in measured
            for path in paths
            if path.side == side
        )
        if not candidates:
            result.append(canvas[side])
            continue
        if side in {BoundarySide.LEADING, BoundarySide.TOP}:
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
    groups: tuple[BoundaryPathGroup, ...],
) -> list[SequenceHypothesis]:
    proposals = [
        proposal
        for group in groups
        if (
            proposal := _proposal_from_paths(
                group.source.value,
                group.paths,
                gray,
            )
        )
        is not None
    ]
    mixed = _proposal_from_paths(
        "mixed_safe_overcontain",
        _mixed_safe_paths(groups),
        gray,
    )
    if mixed is not None and any(
        observation.kind != BoundaryKind.CANVAS_CLIP
        for observation in mixed.boundary_paths
    ):
        proposals.append(mixed)
    return unique_sequence_hypotheses(proposals)
