from __future__ import annotations

import ast
from pathlib import Path
import unittest

from x5crop.configuration.model import HolderLayoutAuthority
from x5crop.domain import PositiveInterval
from x5crop.formats import FramePhysicalSpec
from x5crop.detection.photo_geometry.source_geometry import SourceScanGeometry
from x5crop.detection.photo_geometry.template_model import PhaseAuthority
from x5crop.detection.photo_geometry.template_registration import (
    template_spec_from_physical_authority,
)


def _source(frame: FramePhysicalSpec) -> SourceScanGeometry:
    return SourceScanGeometry.create(
        frame,
        width_scale_px_per_mm=PositiveInterval.exact(10.0),
        height_scale_px_per_mm=PositiveInterval.exact(10.0),
    )


class TemplateRegistrationContractTest(unittest.TestCase):
    def test_full_layout_owns_centered_phase_and_format_gap(self) -> None:
        frame = FramePhysicalSpec(36.0, 24.0, 2.0)
        template = template_spec_from_physical_authority(
            frame_spec=frame,
            source_geometry=_source(frame),
            width_scale_px_per_mm=PositiveInterval.exact(10.0),
            count=6,
            holder_layout_authority=(
                HolderLayoutAuthority.USER_CONFIRMED_FILLED_HOLDER_LAYOUT
            ),
        )
        self.assertEqual(template.phase_authority, PhaseAuthority.FULL_CENTERED)
        self.assertEqual(template.count, 6)
        self.assertEqual(template.nominal_gap_px.minimum, 20.0)
        self.assertEqual(template.nominal_gap_px.maximum, 20.0)

    def test_partial_equal_to_full_count_remains_free_phase(self) -> None:
        frame = FramePhysicalSpec(36.0, 24.0, 2.0)
        template = template_spec_from_physical_authority(
            frame_spec=frame,
            source_geometry=_source(frame),
            width_scale_px_per_mm=PositiveInterval.exact(10.0),
            count=6,
            holder_layout_authority=(
                HolderLayoutAuthority.USER_CONFIRMED_NONFILLING_LAYOUT
            ),
        )
        self.assertEqual(template.phase_authority, PhaseAuthority.PARTIAL_FREE)
        self.assertEqual(template.count, 6)

    def test_registration_does_not_import_retired_candidate_modules(self) -> None:
        path = (
            Path(__file__).parents[2]
            / "x5crop/detection/photo_geometry/template_registration.py"
        )
        tree = ast.parse(path.read_text())
        imports = [
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in getattr(node, "names", ())
        ]
        self.assertFalse(
            any(
                token in name
                for name in imports
                for token in ("proposal", "materialization", "chain", "cache")
            )
        )


if __name__ == "__main__":
    unittest.main()
