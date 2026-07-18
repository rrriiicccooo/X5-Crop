from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from ..detection.final.model import FinalDetection
from ..detection.candidate.selection.model import SelectionResult
from ..detection.evidence.transform_geometry import TransformGeometryEvidence
from ..image.workspace import WorkspaceIdentity
from ..io.model import ImageProfile
from ..units import ResolutionMetadataObservation
from .model import ReportResult
from .read_models import typed_read_model
from .record import report_record_for_final_detection


def result_from_detection(
    input_file: Path,
    detection: FinalDetection,
    selection: SelectionResult,
    profile: ImageProfile,
    workspace_identity: WorkspaceIdentity,
    output_files: list[str],
    review_copy: Optional[str],
    warnings: list[str],
    *,
    configuration_detail: dict[str, Any],
    resolution_metadata: ResolutionMetadataObservation,
    transform_geometry: TransformGeometryEvidence,
    analysis_identity: dict[str, Any],
) -> ReportResult:
    record = report_record_for_final_detection(
        detection,
        selection,
        source=str(input_file),
        profile=typed_read_model(profile),
        workspace_identity=workspace_identity,
        output_files=output_files,
        review_copy=review_copy,
        warnings=warnings,
        configuration=configuration_detail,
        resolution_metadata=resolution_metadata,
        transform_geometry=transform_geometry,
        analysis_identity=analysis_identity,
    )
    return ReportResult(record=record)
