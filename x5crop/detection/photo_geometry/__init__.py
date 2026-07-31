"""Source-coordinate photo-boundary reconstruction.

Pixel observations, physical constraints, search proposals, selection and
output geometry are deliberately represented by different types.  The package
contains no DecisionGate authority.
"""

from .model import (
    BoundaryAxis,
    BoundaryRole,
    FirstPhotoStartAssessment,
    FirstPhotoStartOutcome,
    FrameGeometryState,
    FramePhotoGeometry,
    FrameSequenceGeometryConstraintSet,
    FrameSequenceGeometrySolution,
    GridInferredBlankOutputGeometry,
    GridSlotTranslationAssessment,
    GridSlotTranslationOutcome,
    PhotoBoundaryMeasurementField,
    PhotoBoundaryMeasurementQuery,
    PhotoBoundaryMeasurementSet,
    PhotoBoundaryMeasurementSpec,
    PhotoBoundaryObservation,
    PhotoEdgeSearchCorridor,
    PhotoSequenceExtentProposal,
    PhotoSequenceTranslationAssessment,
    PhotoSequenceTranslationOutcome,
    SafeCropEnvelope,
    SequenceAnchorDiscoveryDomain,
    UndominatedFrameSequenceCandidate,
)

__all__ = (
    "BoundaryAxis",
    "BoundaryRole",
    "FirstPhotoStartAssessment",
    "FirstPhotoStartOutcome",
    "FrameGeometryState",
    "FramePhotoGeometry",
    "FrameSequenceGeometryConstraintSet",
    "FrameSequenceGeometrySolution",
    "GridInferredBlankOutputGeometry",
    "GridSlotTranslationAssessment",
    "GridSlotTranslationOutcome",
    "PhotoBoundaryMeasurementField",
    "PhotoBoundaryMeasurementQuery",
    "PhotoBoundaryMeasurementSet",
    "PhotoBoundaryMeasurementSpec",
    "PhotoBoundaryObservation",
    "PhotoEdgeSearchCorridor",
    "PhotoSequenceExtentProposal",
    "PhotoSequenceTranslationAssessment",
    "PhotoSequenceTranslationOutcome",
    "SafeCropEnvelope",
    "SequenceAnchorDiscoveryDomain",
    "UndominatedFrameSequenceCandidate",
)
