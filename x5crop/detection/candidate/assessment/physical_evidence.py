from __future__ import annotations

from dataclasses import dataclass

from ....formats import FormatPhysicalSpec
from ....units import ScanCalibration
from ...evidence.frame_topology import FrameTopologyEvidence, frame_topology_evidence
from ...physical.photo_size import FrameDimensionEvidence, frame_dimension_evidence
from ..model import BuiltCandidate


@dataclass(frozen=True)
class CorePhysicalEvidence:
    frame_topology: FrameTopologyEvidence
    frame_dimensions: FrameDimensionEvidence


def measure_core_physical_evidence(
    candidate: BuiltCandidate,
    physical_spec: FormatPhysicalSpec,
    calibration: ScanCalibration,
) -> CorePhysicalEvidence:
    geometry = candidate.geometry
    topology = frame_topology_evidence(geometry.frames, geometry.count)
    dimensions = frame_dimension_evidence(
        geometry,
        physical_spec,
        calibration,
    )
    return CorePhysicalEvidence(
        frame_topology=topology,
        frame_dimensions=dimensions,
    )
