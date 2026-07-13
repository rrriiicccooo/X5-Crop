from __future__ import annotations

from dataclasses import replace
from dataclasses import fields
import unittest

from tools.tests.physical_gate_support import (
    boundary_path_fixture,
    candidate_fixture,
    separator_constraints,
    separator_observation,
    supported_calibration_fixture,
    unavailable_calibration_fixture,
)
from x5crop.detection.physical.boundary import (
    canvas_boundary_paths,
    holder_occlusion_evidence,
)
from x5crop.detection.physical.photo_size import (
    frame_dimension_evidence,
    frame_dimension_priors,
)
from x5crop.detection.physical.model import (
    PhotoInterval,
    photo_intervals_for_sequence,
)
from x5crop.detection.physical.spacing import (
    observed_spacing_evidence,
    spacing_hypothesis,
)
from x5crop.detection.physical.separator.assignment import (
    assign_observation_to_boundary,
    dimension_constrained_boundary,
    frame_boundary_from_assignment,
)
from x5crop.domain import (
    BoundaryKind,
    BoundarySide,
    EvidenceState,
    FrameBoundaryReference,
    FrameDimensionPriorSource,
    MeasurementIdentity,
    MeasurementProvenance,
    PixelInterval,
)
from x5crop.formats import format_spec


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
    first_cut = int(round(observations[0].center))
    second_cut = int(round(observations[1].center))
    photo_edge_provenance = MeasurementProvenance(
        MeasurementIdentity.PHOTO_EDGES,
        "test_fixture",
        (
            MeasurementIdentity.SEPARATOR_PROFILE,
            MeasurementIdentity.SEQUENCE_BOUNDARIES,
        ),
    )
    return replace(
        base,
        format_id="120-66",
        count=3,
        visible_sequence_span=replace(base.visible_sequence_span, box=replace(base.visible_sequence_span.box, right=315)),
        crop_envelope=replace(base.crop_envelope, box=replace(base.crop_envelope.box, right=315)),
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
            replace(base.frames[0], right=first_cut),
            replace(base.frames[0], left=first_cut, right=second_cut),
            replace(base.frames[0], left=second_cut, right=315),
        ),
        frame_dimension_prior=replace(
            base.frame_dimension_prior,
            width_px=PixelInterval.exact(100.0),
            height_px=PixelInterval.exact(100.0),
            frame_size_mm=(56.0, 56.0),
        ),
    )


class PhotoSizePhysicalModelTest(unittest.TestCase):
    def test_discrete_frame_sizes_produce_discrete_dimension_priors(self) -> None:
        base = candidate_fixture().geometry
        priors = frame_dimension_priors(
            base.visible_sequence_span,
            format_spec("120-66"),
            supported_calibration_fixture(10.0, 10.0),
            layout="horizontal",
        )
        self.assertEqual(
            tuple(prior.frame_size_mm for prior in priors),
            ((56.0, 56.0), (54.0, 54.0)),
        )
        self.assertEqual(
            tuple(prior.width_px for prior in priors),
            (PixelInterval.exact(560.0), PixelInterval.exact(540.0)),
        )
        self.assertNotIn(
            PixelInterval.exact(550.0),
            tuple(prior.width_px for prior in priors),
        )
        uncalibrated = frame_dimension_priors(
            base.visible_sequence_span,
            format_spec("120-66"),
            unavailable_calibration_fixture(),
            layout="horizontal",
        )
        self.assertEqual(len(uncalibrated), 1)
        self.assertEqual(uncalibrated[0].frame_size_mm, (56.0, 56.0))

    def test_dimension_evidence_names_the_selected_physical_size(self) -> None:
        from x5crop.detection.physical.photo_size import FrameDimensionEvidence

        names = {field.name for field in fields(FrameDimensionEvidence)}
        self.assertTrue(
            {"frame_width_mm", "frame_height_mm", "frame_aspect"} <= names
        )
        self.assertFalse(any(name.startswith("nominal_") for name in names))

    def test_physical_aspect_prior_does_not_become_dimension_evidence(self) -> None:
        base = candidate_fixture().geometry
        provenance = base.frame_dimension_prior.provenance
        boundary = dimension_constrained_boundary(
            1,
            PixelInterval.exact(100.0),
            provenance,
        )
        boundary_paths = canvas_boundary_paths(200, 100)
        geometry = replace(
            base,
            separator_observations=(),
            separator_assignments=(),
            frame_boundaries=(boundary,),
            inter_frame_spacings=(
                spacing_hypothesis(
                    FrameBoundaryReference(None, 1),
                    PixelInterval.zero(),
                    provenance,
                ),
            ),
            boundary_paths=boundary_paths,
            photo_intervals=photo_intervals_for_sequence(
                (boundary,),
                base.frames,
                boundary_paths,
            ),
            frame_dimension_prior=replace(
                base.frame_dimension_prior,
                source=FrameDimensionPriorSource.SHORT_AXIS_ASPECT,
                provenance=MeasurementProvenance(
                    MeasurementIdentity.PHYSICAL_FRAME_ASPECT,
                    "frame_dimension_prior",
                    (
                        MeasurementIdentity.FORMAT_PHYSICAL_SPEC,
                        MeasurementIdentity.SHORT_AXIS_BOUNDARIES,
                    ),
                ),
            ),
        )
        result = frame_dimension_evidence(
            geometry,
            unavailable_calibration_fixture(),
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
            inter_frame_spacings=(),
            photo_intervals=(
                PhotoInterval(
                    1,
                    PixelInterval.exact(0.0),
                    PixelInterval.exact(94.0),
                    base.frame_dimension_prior.provenance,
                    base.frame_dimension_prior.provenance,
                    False,
                    False,
                ),
            ),
        )
        boundary = boundary_path_fixture(
            BoundarySide.LEADING,
            PixelInterval.exact(0.0),
            BoundaryKind.HOLDER_BOUNDARY_TRANSITION,
            MeasurementProvenance(
                MeasurementIdentity.HOLDER_BOUNDARY_PROFILE,
                "holder_boundary_transition",
                (MeasurementIdentity.GRAY_WORK,),
            ),
        )
        occlusion = holder_occlusion_evidence(
            leading_boundary=boundary,
            trailing_boundary=None,
            leading_visible_frame_width=PixelInterval.exact(94.0),
            trailing_visible_frame_width=None,
            frame_width_px=PixelInterval.exact(100.0),
            edge_texture_limit=1.0,
        )
        photo_edges = MeasurementProvenance(
            MeasurementIdentity.PHOTO_EDGES,
            "test_fixture",
            (MeasurementIdentity.HOLDER_BOUNDARY_PROFILE,),
        )
        geometry = replace(
            geometry,
            holder_occlusion=occlusion,
            photo_intervals=(
                replace(
                    geometry.photo_intervals[0],
                    start_provenance=photo_edges,
                    end_provenance=photo_edges,
                    start_independently_observed=True,
                    end_independently_observed=True,
                ),
            ),
        )
        result = frame_dimension_evidence(
            geometry,
            unavailable_calibration_fixture(),
        )
        self.assertEqual(occlusion.leading.state, EvidenceState.SUPPORTED)
        self.assertEqual(result.photo_widths_px, ())
        self.assertEqual(result.state, EvidenceState.UNAVAILABLE)

    def test_separator_width_variation_does_not_contradict_photo_size(self) -> None:
        geometry = _geometry()
        result = frame_dimension_evidence(
            geometry,
            unavailable_calibration_fixture(),
        )
        self.assertEqual(result.photo_widths_px, (100.0, 100.0, 100.0))
        self.assertGreater(result.separator_width_cv or 0.0, 0.0)
        self.assertEqual(result.state, EvidenceState.SUPPORTED)

    def test_supported_holder_occlusion_excludes_edge_frames_from_dimension_checks(
        self,
    ) -> None:
        geometry = _geometry()
        provenance = geometry.photo_intervals[0].start_provenance
        leading = boundary_path_fixture(
            BoundarySide.LEADING,
            PixelInterval.exact(0.0),
            BoundaryKind.HOLDER_BOUNDARY_TRANSITION,
            provenance,
        )
        trailing = boundary_path_fixture(
            BoundarySide.TRAILING,
            PixelInterval.exact(315.0),
            BoundaryKind.HOLDER_BOUNDARY_TRANSITION,
            provenance,
        )
        occlusion = holder_occlusion_evidence(
            leading_boundary=leading,
            trailing_boundary=trailing,
            leading_visible_frame_width=PixelInterval.exact(90.0),
            trailing_visible_frame_width=PixelInterval.exact(90.0),
            frame_width_px=PixelInterval.exact(100.0),
            edge_texture_limit=1.0,
        )
        geometry = replace(
            geometry,
            holder_occlusion=occlusion,
            photo_intervals=(
                replace(
                    geometry.photo_intervals[0],
                    end=PixelInterval.exact(90.0),
                ),
                geometry.photo_intervals[1],
                replace(
                    geometry.photo_intervals[2],
                    start=PixelInterval.exact(225.0),
                ),
            ),
        )

        result = frame_dimension_evidence(
            geometry,
            unavailable_calibration_fixture(),
        )

        self.assertEqual(result.photo_widths_px, (100.0,))
        self.assertEqual(result.state, EvidenceState.SUPPORTED)

    def test_photo_width_variation_is_a_physical_contradiction(self) -> None:
        geometry = _geometry(second_start=225.0)
        result = frame_dimension_evidence(
            geometry,
            unavailable_calibration_fixture(),
        )
        self.assertEqual(result.state, EvidenceState.CONTRADICTED)
        self.assertEqual(result.reason, "physical_frame_dimensions_contradicted")


if __name__ == "__main__":
    unittest.main()
