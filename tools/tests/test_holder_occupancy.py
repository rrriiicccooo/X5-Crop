from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.physical_gate_support import candidate_evidence_fixture, candidate_fixture, separator_observation
from x5crop.detection.evidence.holder_occupancy import holder_occupancy_evidence
from x5crop.detection.evidence.partial_edge import partial_edge_safety_evidence
from x5crop.detection.evidence.state import EvidenceState
from x5crop.detection.physical.spans import FilmSpan, HolderSpan
from x5crop.domain import Box
from x5crop.formats import format_spec
from x5crop.units import ScanCalibration


class HolderOccupancyTests(unittest.TestCase):
    def _underfilled(self):
        candidate = candidate_fixture()
        holder = HolderSpan(Box(0, 0, 400, 120))
        film = FilmSpan(Box(30, 0, 360, 120))
        frames = (
            Box(30, 0, 130, 120),
            Box(140, 0, 240, 120),
            Box(250, 0, 350, 120),
        )
        geometry = replace(
            candidate.geometry,
            format_id="120-66",
            strip_mode="partial",
            count=3,
            holder_span=holder,
            film_span=film,
            work_frames=frames,
            image_frames=frames,
            separators=(
                separator_observation(1, 135.0, start=130.0, end=140.0),
                separator_observation(2, 245.0, start=240.0, end=250.0),
            ),
        )
        evidence = candidate_evidence_fixture()
        coverage = replace(
            evidence.frame_coverage,
            holder_interval=(0, 400),
            film_interval=(30, 360),
            frame_intervals=((30, 130), (140, 240), (250, 350)),
        )
        dimensions = replace(
            evidence.frame_dimensions,
            nominal_width_mm=56.0,
            nominal_height_mm=56.0,
            nominal_aspect=1.0,
            photo_widths_px=(100.0, 100.0, 100.0),
            photo_width_cv=0.0,
        )
        return geometry, coverage, dimensions, evidence

    def test_medium_square_partial_can_be_complete_underfilled(self) -> None:
        geometry, coverage, dimensions, _ = self._underfilled()
        occupancy = holder_occupancy_evidence(
            layout="horizontal",
            strip_mode="partial",
            count=geometry.count,
            holder_span=geometry.holder_span,
            film_span=geometry.film_span,
            work_frames=geometry.work_frames,
            separators=geometry.separators,
            physical_spec=format_spec("120-66"),
            content_support_available=True,
            frame_coverage=coverage,
            frame_dimensions=dimensions,
            calibration=ScanCalibration(None, None, "unavailable", False),
        )
        self.assertEqual(occupancy.occupancy_status, "underfilled")
        self.assertTrue(occupancy.complete_underfilled_strip)

    def test_underfilled_state_uses_normal_partial_edge_evidence(self) -> None:
        geometry, coverage, dimensions, evidence = self._underfilled()
        occupancy = holder_occupancy_evidence(
            layout="horizontal",
            strip_mode="partial",
            count=geometry.count,
            holder_span=geometry.holder_span,
            film_span=geometry.film_span,
            work_frames=geometry.work_frames,
            separators=geometry.separators,
            physical_spec=format_spec("120-66"),
            content_support_available=True,
            frame_coverage=coverage,
            frame_dimensions=dimensions,
            calibration=ScanCalibration(None, None, "unavailable", False),
        )
        partial = partial_edge_safety_evidence(
            geometry,
            coverage,
            dimensions,
            evidence.frame_content,
            occupancy,
        )
        self.assertEqual(partial.state, EvidenceState.SUPPORTED)
        self.assertTrue(partial.complete_underfilled_strip)

    def test_non_underfilled_format_does_not_gain_occupancy_exemption(self) -> None:
        geometry, coverage, dimensions, _ = self._underfilled()
        occupancy = holder_occupancy_evidence(
            layout="horizontal",
            strip_mode="partial",
            count=geometry.count,
            holder_span=geometry.holder_span,
            film_span=geometry.film_span,
            work_frames=geometry.work_frames,
            separators=geometry.separators,
            physical_spec=format_spec("135"),
            content_support_available=True,
            frame_coverage=coverage,
            frame_dimensions=dimensions,
            calibration=ScanCalibration(None, None, "unavailable", False),
        )
        self.assertFalse(occupancy.complete_underfilled_strip)

    def test_vertical_holder_slack_uses_source_y_calibration(self) -> None:
        geometry, coverage, dimensions, _ = self._underfilled()
        occupancy = holder_occupancy_evidence(
            layout="vertical",
            strip_mode="partial",
            count=geometry.count,
            holder_span=geometry.holder_span,
            film_span=geometry.film_span,
            work_frames=geometry.work_frames,
            separators=geometry.separators,
            physical_spec=format_spec("120-66"),
            content_support_available=True,
            frame_coverage=coverage,
            frame_dimensions=dimensions,
            calibration=ScanCalibration(10.0, 20.0, "tiff_resolution", True),
        )

        self.assertEqual(occupancy.leading_slack_mm, 1.5)
        self.assertEqual(occupancy.trailing_slack_mm, 2.0)


if __name__ == "__main__":
    unittest.main()
