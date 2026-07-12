from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.physical_gate_support import (
    candidate_evidence_fixture,
    candidate_fixture,
    separator_constraints,
    separator_observation,
)
from x5crop.detection.evidence.holder_occupancy import holder_occupancy_evidence
from x5crop.detection.evidence.partial_edge import partial_edge_safety_evidence
from x5crop.detection.physical.separator.assignment import (
    assign_observation_to_boundary,
    frame_boundary_from_assignment,
)
from x5crop.domain import EvidenceState, PixelInterval
from x5crop.domain import VisibleSequenceSpan, HolderSpan
from x5crop.domain import Box
from x5crop.formats import format_spec
from x5crop.units import ScanCalibration


class HolderOccupancyTests(unittest.TestCase):
    def _underfilled(self):
        candidate = candidate_fixture()
        holder = HolderSpan(Box(0, 0, 400, 120))
        sequence = VisibleSequenceSpan(Box(30, 0, 360, 120))
        frames = (
            Box(30, 0, 130, 120),
            Box(140, 0, 240, 120),
            Box(250, 0, 350, 120),
        )
        observations = (
            separator_observation(135.0, start=130.0, end=140.0),
            separator_observation(245.0, start=240.0, end=250.0),
        )
        assignments = tuple(
            replace(
                assign_observation_to_boundary(
                    index,
                    observation,
                    *separator_constraints(
                        index,
                        PixelInterval(
                            observation.start - 10.0,
                            observation.end + 10.0,
                        ),
                        PixelInterval(0.0, 20.0),
                    ),
                ),
                used_for_boundary=True,
            )
            for index, observation in enumerate(observations, start=1)
        )
        boundaries = tuple(frame_boundary_from_assignment(item) for item in assignments)
        geometry = replace(
            candidate.geometry,
            format_id="120-66",
            strip_mode="partial",
            count=3,
            holder_span=holder,
            visible_sequence_span=sequence,
            crop_envelope=replace(
                candidate.geometry.crop_envelope,
                box=sequence.box,
            ),
            frames=frames,
            separator_observations=observations,
            separator_assignments=assignments,
            frame_boundaries=boundaries,
        )
        evidence = candidate_evidence_fixture()
        coverage = replace(
            evidence.frame_coverage,
            holder_long_axis_interval=(0, 400),
            visible_sequence_interval=(30, 360),
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
            visible_sequence_span=geometry.visible_sequence_span,
            frames=geometry.frames,
            frame_boundaries=geometry.frame_boundaries,
            separator_assignments=geometry.separator_assignments,
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
            visible_sequence_span=geometry.visible_sequence_span,
            frames=geometry.frames,
            frame_boundaries=geometry.frame_boundaries,
            separator_assignments=geometry.separator_assignments,
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
            visible_sequence_span=geometry.visible_sequence_span,
            frames=geometry.frames,
            frame_boundaries=geometry.frame_boundaries,
            separator_assignments=geometry.separator_assignments,
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
            visible_sequence_span=geometry.visible_sequence_span,
            frames=geometry.frames,
            frame_boundaries=geometry.frame_boundaries,
            separator_assignments=geometry.separator_assignments,
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
