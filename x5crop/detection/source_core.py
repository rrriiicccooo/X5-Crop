from __future__ import annotations

from dataclasses import dataclass

from ..domain import Box, EvidenceState
from .evidence.scan_canvas import ScanCanvasEvidence, ScanCanvasOutcome


@dataclass(frozen=True)
class SourceStripValidationDomain:
    lane_id: str
    work_box: Box
    source_axis_long: str
    authority_profile_id: str

    def __post_init__(self) -> None:
        if not self.lane_id or not self.work_box.valid():
            raise ValueError("source strip domain requires one non-empty lane")
        if self.source_axis_long not in {"x", "y"}:
            raise ValueError("source strip domain requires a source long axis")
        if not self.authority_profile_id:
            raise ValueError("source strip domain requires profile authority")


@dataclass(frozen=True)
class SourceLaneEvidence:
    domain: SourceStripValidationDomain
    scan_canvas: ScanCanvasEvidence

    def __post_init__(self) -> None:
        if self.scan_canvas.outcome != ScanCanvasOutcome.SUPPORTED:
            raise ValueError("source lane requires unique scan-canvas authority")
        if self.scan_canvas.axis_scales is None:
            raise ValueError("source lane requires scan-canvas scale intervals")


@dataclass(frozen=True)
class SourceCoreEvidence:
    lanes: tuple[SourceLaneEvidence, ...]
    incomplete_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if len(set(lane.domain.lane_id for lane in self.lanes)) != len(self.lanes):
            raise ValueError("source-core lane identities must be unique")
        if len(set(self.incomplete_reasons)) != len(self.incomplete_reasons):
            raise ValueError("source-core incomplete reasons must be unique")

    @property
    def scan_canvas_state(self) -> EvidenceState:
        return (
            EvidenceState.SUPPORTED
            if self.lanes
            else EvidenceState.UNAVAILABLE
        )
