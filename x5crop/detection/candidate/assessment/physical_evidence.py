from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ....formats import FormatPhysicalSpec
from ....geometry.detection_parameters import SeparatorContinuityParameters
from ....units import ScanCalibration
from ...evidence.frame_topology import FrameTopologyEvidence, frame_topology_evidence
from ...evidence.separator_continuity import (
    SeparatorContinuityEvidence,
    separator_cross_axis_continuity_evidence,
)
from ...physical.photo_size import FrameDimensionEvidence, frame_dimension_evidence
from ..model import BuiltCandidate


@dataclass(frozen=True)
class CorePhysicalEvidence:
    frame_topology: FrameTopologyEvidence
    separator_continuity: SeparatorContinuityEvidence
    frame_dimensions: FrameDimensionEvidence


def measure_core_physical_evidence(
    gray_work: np.ndarray,
    candidate: BuiltCandidate,
    physical_spec: FormatPhysicalSpec,
    calibration: ScanCalibration,
    separator_continuity_parameters: SeparatorContinuityParameters,
) -> CorePhysicalEvidence:
    geometry = candidate.geometry
    topology = frame_topology_evidence(geometry.frames, geometry.count)
    continuity = separator_cross_axis_continuity_evidence(
        gray_work,
        geometry,
        separator_continuity_parameters,
    )
    dimensions = frame_dimension_evidence(
        geometry,
        physical_spec,
        calibration,
        continuity,
    )
    return CorePhysicalEvidence(
        frame_topology=topology,
        separator_continuity=continuity,
        frame_dimensions=dimensions,
    )
