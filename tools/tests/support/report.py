from __future__ import annotations

from pathlib import Path

from tools.tests.support.physical_gates import (
    detection_workspace_fixture,
    final_detection_fixture,
    selection_fixture,
)
from x5crop.configuration.registry import get_detection_configuration
from x5crop.domain import WorkspaceExtent
from x5crop.image.workspace import WorkspaceIdentity
from x5crop.io.model import ImageProfile, TiffMetadata
from x5crop.report.configuration import detection_configuration_read_model
from x5crop.report.read_models import typed_read_model
from x5crop.report.record import report_record_for_final_detection


def image_profile_fixture() -> ImageProfile:
    return ImageProfile(
        shape=(100, 310),
        dtype="uint8",
        axes="YX",
        photometric="MINISBLACK",
        compression="NONE",
        sample_format=None,
        bits_per_sample=8,
        samples_per_pixel=1,
        planar_config=None,
        resolution=None,
        resolution_unit=None,
        icc_profile=None,
        metadata=TiffMetadata(None, None, None, ()),
    )


def analysis_identity_fixture(
    format_id: str = "135",
    strip_mode: str = "partial",
    source_name: str = "input.tif",
    shape: tuple[int, int] = (100, 310),
    workspace_shape: tuple[int, int] | None = None,
    workspace_identity: WorkspaceIdentity | None = None,
) -> dict:
    workspace_shape = shape if workspace_shape is None else workspace_shape
    workspace_identity = workspace_identity or WorkspaceIdentity(
        WorkspaceExtent(workspace_shape[1], workspace_shape[0]),
        "0" * 64,
    )
    return {
        "script": "X5_Crop.py",
        "script_version": "4.9",
        "implementation_fingerprint": "0" * 64,
        "source": {
            "name": source_name,
            "size": 1,
            "mtime_ns": 1,
            "content_sha256": "0" * 64,
            "page": 0,
            "shape": list(shape),
            "dtype": "uint8",
            "axes": "YX",
            "photometric": "MINISBLACK",
        },
        "runtime_configuration": {
            "format_id": format_id,
            "layout": "horizontal",
            "strip_mode": strip_mode,
            "requested_count": None,
            "page": 0,
            "bleed_x": 20,
            "bleed_y": 10,
        },
        "detection_configuration_fingerprint": "0" * 64,
        "workspace_identity": typed_read_model(workspace_identity),
    }


def report_record_fixture(source: str = "input.tif") -> dict:
    workspace = detection_workspace_fixture()
    return report_record_for_final_detection(
        final_detection_fixture(),
        selection_fixture(),
        source=source,
        profile=typed_read_model(image_profile_fixture()),
        workspace=workspace,
        output_files=[],
        review_copy=None,
        warnings=[],
        configuration=detection_configuration_read_model(
            get_detection_configuration("135", "partial")
        ),
        analysis_identity=analysis_identity_fixture(
            source_name=Path(source).name,
            workspace_identity=workspace.identity,
        ),
    )
