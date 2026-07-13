from __future__ import annotations

from dataclasses import replace
from inspect import signature
import unittest

from tools.tests.physical_gate_support import (
    candidate_evidence_fixture,
    candidate_fixture,
    separator_constraints,
    separator_observation,
    supported_calibration_fixture,
    unavailable_calibration_fixture,
)
from x5crop.detection.evidence.holder_occupancy import holder_occupancy_evidence
from x5crop.detection.evidence.partial_edge import partial_edge_safety_evidence
from x5crop.detection.physical.separator.assignment import (
    assign_observation_to_boundary,
    frame_boundary_from_assignment,
)
from x5crop.detection.physical.model import PhotoInterval
from x5crop.detection.physical.spacing import observed_spacing_evidence
from x5crop.domain import (
    EvidenceState,
    FrameBoundaryReference,
    MeasurementIdentity,
    MeasurementProvenance,
    PixelInterval,
)
from x5crop.domain import VisibleSequenceSpan, HolderSpan
from x5crop.domain import Box
from x5crop.formats import format_spec


class HolderOccupancyTests(unittest.TestCase):
    def test_occupancy_measurement_does_not_accept_user_strip_mode(self) -> None:
        self.assertNotIn(
            "strip_mode",
            signature(holder_occupancy_evidence).parameters,
        )

    def _underfilled(self):
        candidate = candidate_fixture()
        holder = HolderSpan(Box(0, 0, 400, 120))
        sequence = VisibleSequenceSpan(Box(30, 0, 360, 120))
        frames = (
            Box(30, 0, 135, 120),
            Box(135, 0, 245, 120),
            Box(245, 0, 360, 120),
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
        photo_edge_provenance = MeasurementProvenance(
            MeasurementIdentity.PHOTO_EDGES,
            "holder_occupancy_fixture",
            (MeasurementIdentity.GRAY_WORK,),
        )
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
            photo_intervals=tuple(
                PhotoInterval(
                    index,
                    PixelInterval.exact(start),
                    PixelInterval.exact(end),
                    photo_edge_provenance,
                    photo_edge_provenance,
                    True,
                    True,
                )
                for index, (start, end) in enumerate(
                    (
                        (30.0, observations[0].start),
                        (observations[0].end, observations[1].start),
                        (observations[1].end, 360.0),
                    ),
                    start=1,
                )
            ),
            separator_observations=observations,
            separator_assignments=assignments,
            frame_boundaries=boundaries,
            inter_frame_spacings=tuple(
                observed_spacing_evidence(
                    FrameBoundaryReference(None, index),
                    PixelInterval.exact(observation.width),
                    observation.provenance,
                )
                for index, observation in enumerate(observations, start=1)
            ),
        )
        evidence = candidate_evidence_fixture()
        coverage = replace(
            evidence.frame_coverage,
            holder_long_axis_interval=(0, 400),
            visible_sequence_interval=(30, 360),
            frame_intervals=((30, 360),),
            content_runs=((40, 350),),
        )
        dimensions = replace(
            evidence.frame_dimensions,
            frame_width_mm=56.0,
            frame_height_mm=56.0,
            frame_width_prior_px=PixelInterval.exact(100.0),
            photo_width_intervals_px=(
                PixelInterval.exact(100.0),
                PixelInterval.exact(100.0),
                PixelInterval.exact(100.0),
            ),
            observed_aspect=1.0,
            aspect_error_ratio=0.0,
        )
        return geometry, coverage, dimensions, evidence

    def test_medium_square_partial_can_be_complete_underfilled(self) -> None:
        geometry, coverage, dimensions, _ = self._underfilled()
        occupancy = holder_occupancy_evidence(
            layout="horizontal",
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
            calibration=unavailable_calibration_fixture(),
        )
        self.assertTrue(occupancy.underfilled)
        self.assertTrue(occupancy.complete_underfilled_strip)

    def test_underfilled_state_uses_normal_partial_edge_evidence(self) -> None:
        geometry, coverage, dimensions, evidence = self._underfilled()
        occupancy = holder_occupancy_evidence(
            layout="horizontal",
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
            calibration=unavailable_calibration_fixture(),
        )
        partial = partial_edge_safety_evidence(
            geometry,
            coverage,
            dimensions,
            evidence.frame_content,
        )
        self.assertTrue(occupancy.complete_underfilled_strip)
        self.assertEqual(partial.state, EvidenceState.SUPPORTED)

    def test_non_underfilled_format_does_not_gain_occupancy_exemption(self) -> None:
        geometry, coverage, dimensions, _ = self._underfilled()
        occupancy = holder_occupancy_evidence(
            layout="horizontal",
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
            calibration=unavailable_calibration_fixture(),
        )
        self.assertFalse(occupancy.complete_underfilled_strip)

    def test_vertical_holder_slack_uses_source_y_calibration(self) -> None:
        geometry, coverage, dimensions, _ = self._underfilled()
        occupancy = holder_occupancy_evidence(
            layout="vertical",
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
            calibration=supported_calibration_fixture(10.0, 20.0),
        )

        self.assertEqual(occupancy.leading_slack_mm, 1.5)
        self.assertEqual(occupancy.trailing_slack_mm, 2.0)

    def test_zero_holder_slack_is_physically_filled(self) -> None:
        geometry, coverage, dimensions, _ = self._underfilled()
        holder = HolderSpan(geometry.visible_sequence_span.box)
        occupancy = holder_occupancy_evidence(
            layout="horizontal",
            count=geometry.count,
            holder_span=holder,
            visible_sequence_span=geometry.visible_sequence_span,
            frames=geometry.frames,
            frame_boundaries=geometry.frame_boundaries,
            separator_assignments=geometry.separator_assignments,
            physical_spec=format_spec("120-66"),
            content_support_available=True,
            frame_coverage=coverage,
            frame_dimensions=dimensions,
            calibration=unavailable_calibration_fixture(),
        )
        self.assertFalse(occupancy.underfilled)


if __name__ == "__main__":
    unittest.main()
