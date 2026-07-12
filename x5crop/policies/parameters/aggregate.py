from __future__ import annotations

from dataclasses import dataclass, field

from ...geometry.detection_parameters import (
    SeparatorProfileParameters,
)
from ...image.deskew_parameters import DeskewParameters
from .candidate import CandidatePlanParameters
from .content import (
    ContentEvidenceParameters,
    ContentProfileParameters,
)
from .diagnostics import SeparatorOverlayParameters
from .separator import (
    SeparatorObservationParameters,
)


@dataclass(frozen=True)
class PreprocessParameters:
    deskew: DeskewParameters = field(default_factory=DeskewParameters)


@dataclass(frozen=True)
class ContentParameters:
    content_evidence: ContentEvidenceParameters = field(default_factory=ContentEvidenceParameters)
    content_profile: ContentProfileParameters = field(default_factory=ContentProfileParameters)


@dataclass(frozen=True)
class SeparatorParameters:
    separator_observation: SeparatorObservationParameters = field(
        default_factory=SeparatorObservationParameters
    )
    separator_profile: SeparatorProfileParameters = field(default_factory=SeparatorProfileParameters)


@dataclass(frozen=True)
class CandidateParameters:
    candidate_plan: CandidatePlanParameters = field(default_factory=CandidatePlanParameters)


@dataclass(frozen=True)
class DiagnosticsParameters:
    separator_overlay: SeparatorOverlayParameters = field(default_factory=SeparatorOverlayParameters)


@dataclass(frozen=True)
class FormatParameters:
    preprocess: PreprocessParameters = field(default_factory=PreprocessParameters)
    content: ContentParameters = field(default_factory=ContentParameters)
    separator: SeparatorParameters = field(default_factory=SeparatorParameters)
    candidate: CandidateParameters = field(default_factory=CandidateParameters)
    diagnostics: DiagnosticsParameters = field(default_factory=DiagnosticsParameters)
