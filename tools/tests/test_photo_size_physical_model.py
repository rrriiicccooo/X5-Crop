from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.physical_gate_support import (
    candidate_fixture,
    separator_constraints,
    separator_observation,
)
from x5crop.detection.evidence.separator_continuity import (
    SeparatorContinuityEvidence,
    SeparatorContinuityRecord,
)
from x5crop.detection.physical.boundary import (
    HolderOcclusionEvidence,
    holder_occlusion_evidence,
)
from x5crop.detection.physical.photo_size import frame_dimension_evidence
from x5crop.detection.physical.model import PhotoInterval
from x5crop.detection.physical.separator.assignment import (
    assign_observation_to_boundary,
    frame_boundary_from_assignment,
)
from x5crop.domain import (
    BoundaryObservation,
    EvidenceState,
    MeasurementProvenance,
    PixelInterval,
)
from x5crop.formats import format_spec
from x5crop.units import ScanCalibration


def _geometry(second_start: float = 205.0):
    base = candidate_fixture().geometry
    observations = (
        separator_observation(102.5, start=100.0, end=105.0),
        separator_observation(
            0.5 * (second_start + second_start + 10.0),
            start=second_start,
            end=second_start + 10.0,
        ),
    )
    assignments = tuple(
        replace(
            assign_observation_to_boundary(
                index,
                observation,
                *separator_constraints(
                    index,
                    PixelInterval(
                        observation.start - 5.0,
                        observation.end + 5.0,
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
        "photo_edges",
        "test_fixture",
        ("separator_profile", "sequence_boundaries"),
    )
    return replace(
        base,
        count=3,
        visible_sequence_span=replace(base.visible_sequence_span, box=replace(base.visible_sequence_span.box, right=315)),
        crop_envelope=replace(base.crop_envelope, box=replace(base.crop_envelope.box, right=315)),
        separator_observations=observations,
        separator_assignments=assignments,
        frame_boundaries=boundaries,
        photo_intervals=(
            PhotoInterval(
                1,
                PixelInterval.exact(0.0),
                PixelInterval.exact(observations[0].start),
                photo_edge_provenance,
                photo_edge_provenance,
                True,
                True,
            ),
            PhotoInterval(
                2,
                PixelInterval.exact(observations[0].end),
                PixelInterval.exact(observations[1].start),
                photo_edge_provenance,
                photo_edge_provenance,
                True,
                True,
            ),
            PhotoInterval(
                3,
                PixelInterval.exact(observations[1].end),
                PixelInterval.exact(315.0),
                photo_edge_provenance,
                photo_edge_provenance,
                True,
                True,
            ),
        ),
        frames=(
            replace(base.frames[0], right=103),
            replace(base.frames[0], left=103, right=210),
            replace(base.frames[0], left=210, right=315),
        ),
    )


def _continuity(geometry) -> SeparatorContinuityEvidence:
    records = tuple(
        SeparatorContinuityRecord(
            item.start,
            item.end,
            EvidenceState.SUPPORTED,
            1.0,
            1.0,
            0,
            1.0,
            "supported",
        )
        for item in geometry.separator_observations
    )
    return SeparatorContinuityEvidence(
        EvidenceState.SUPPORTED,
        "supported",
        records,
        geometry.separator_observations,
    )


class PhotoSizePhysicalModelTest(unittest.TestCase):
    def test_physical_aspect_prior_does_not_become_dimension_evidence(self) -> None:
        base = candidate_fixture().geometry
        geometry = replace(
            base,
            count=2,
            separator_observations=(),
            separator_assignments=(),
            frame_boundaries=(),
            photo_intervals=(),
            frame_dimension_prior=replace(
                base.frame_dimension_prior,
                source="short_axis_aspect",
                provenance=MeasurementProvenance(
                    "physical_frame_aspect",
                    "frame_dimension_prior",
                    ("format_physical_spec", "short_axis_boundaries"),
                ),
            ),
        )
        result = frame_dimension_evidence(
            geometry,
            format_spec("135"),
            ScanCalibration(None, None, "unavailable", False),
            _continuity(geometry),
        )
        self.assertEqual(result.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(
            result.reason,
            "independent_photo_edge_measurements_unavailable",
        )

    def test_supported_edge_occlusion_does_not_self_prove_frame_dimensions(self) -> None:
        base = candidate_fixture().geometry
        geometry = replace(
            base,
            count=1,
            visible_sequence_span=replace(
                base.visible_sequence_span,
                box=replace(base.visible_sequence_span.box, right=94),
            ),
            frames=(replace(base.frames[0], right=94),),
            separator_observations=(),
            separator_assignments=(),
            frame_boundaries=(),
            photo_intervals=(),
        )
        boundary = BoundaryObservation(
            "leading",
            PixelInterval.exact(0.0),
            "white_holder_transition",
            MeasurementProvenance(
                "holder_boundary_profile",
                "white_holder_transition",
                ("gray_work",),
            ),
        )
        occlusion = holder_occlusion_evidence(
            leading_boundary=boundary,
            trailing_boundary=None,
            leading_visible_frame_width=PixelInterval.exact(94.0),
            trailing_visible_frame_width=None,
            frame_width_px=PixelInterval.exact(100.0),
        )
        result = frame_dimension_evidence(
            geometry,
            format_spec("135"),
            ScanCalibration(None, None, "unavailable", False),
            _continuity(geometry),
        )
        self.assertEqual(occlusion.leading.state, EvidenceState.SUPPORTED)
        self.assertEqual(result.photo_widths_px, ())
        self.assertEqual(result.state, EvidenceState.UNAVAILABLE)

    def test_separator_width_variation_does_not_contradict_photo_size(self) -> None:
        geometry = _geometry()
        result = frame_dimension_evidence(
            geometry,
            format_spec("135"),
            ScanCalibration(None, None, "unavailable", False),
            _continuity(geometry),
        )
        self.assertEqual(result.photo_widths_px, (100.0, 100.0, 100.0))
        self.assertGreater(result.separator_width_cv or 0.0, 0.0)
        self.assertEqual(result.state, EvidenceState.SUPPORTED)

    def test_photo_width_variation_is_a_physical_contradiction(self) -> None:
        geometry = _geometry(second_start=225.0)
        result = frame_dimension_evidence(
            geometry,
            format_spec("135"),
            ScanCalibration(None, None, "unavailable", False),
            _continuity(geometry),
        )
        self.assertEqual(result.state, EvidenceState.CONTRADICTED)
        self.assertEqual(result.reason, "physical_frame_dimensions_contradicted")


if __name__ == "__main__":
    unittest.main()
