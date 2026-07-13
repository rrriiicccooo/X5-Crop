from __future__ import annotations

import unittest

import numpy as np

from x5crop.detection.guidance.content_crop_envelope import (
    expand_crop_envelopes_for_content,
)
from x5crop.detection.physical.boundary_detection import boundary_path_groups
from x5crop.detection.physical.sequence import base_sequence_span_candidates
from x5crop.domain import (
    Box,
    CropEnvelope,
    MeasurementIdentity,
    MeasurementProvenance,
    SequenceHypothesis,
    VisibleSequenceSpan,
)
from x5crop.image.statistics import ImageMeasurementStatisticsParameters, image_measurement_statistics
from x5crop.configuration.content import ContentEvidenceParameters
from x5crop.configuration.boundary import BoundaryPathParameters


BOUNDARY_PARAMETERS = BoundaryPathParameters()


def _statistics(gray: np.ndarray):
    return image_measurement_statistics(gray, ImageMeasurementStatisticsParameters())


def _base_candidates(gray: np.ndarray):
    statistics = _statistics(gray)
    groups = boundary_path_groups(gray, statistics, BOUNDARY_PARAMETERS)
    return base_sequence_span_candidates(gray, groups)


def _groups_by_source(gray: np.ndarray):
    return {
        group.source.value: group.paths
        for group in boundary_path_groups(
            gray,
            _statistics(gray),
            BOUNDARY_PARAMETERS,
        )
    }


class BoundaryDetectionTests(unittest.TestCase):
    def test_gray_material_tonal_texture_and_canvas_paths_are_measured(self) -> None:
        gray = np.full((120, 240), 255, dtype=np.uint8)
        gray[20:100, 40:200] = 120
        gray[20:24, 40:200] = 0
        results = boundary_path_groups(
            gray,
            _statistics(gray),
            BOUNDARY_PARAMETERS,
        )
        self.assertEqual(
            tuple(group.source.value for group in results),
            (
                "holder_boundary",
                "tonal",
                "texture",
                "full_canvas",
            ),
        )
        self.assertTrue(all(len(group.paths) == 4 for group in results))

    def test_each_side_has_an_explicit_boundary_model(self) -> None:
        gray = np.full((120, 240), 255, dtype=np.uint8)
        gray[20:100, 40:200] = 120
        group = boundary_path_groups(
            gray,
            _statistics(gray),
            BOUNDARY_PARAMETERS,
        )[0]
        self.assertEqual(
            {observation.side for observation in group.paths},
            {"leading", "trailing", "top", "bottom"},
        )
        self.assertTrue(all(observation.kind for observation in group.paths))

    def test_every_measured_path_keeps_outer_and_inner_gray_material(self) -> None:
        gray = np.full((120, 240), 255, dtype=np.uint8)
        gray[20:100, 40:200] = 120
        groups = _groups_by_source(gray)
        measured = tuple(
            path
            for name, paths in groups.items()
            if name != "full_canvas"
            for path in paths
        )
        self.assertTrue(measured)
        self.assertTrue(all(path.outer_appearance is not None for path in measured))
        self.assertTrue(all(path.inner_appearance is not None for path in measured))

    def test_mixed_light_and_dark_holder_edges_share_one_material_family(self) -> None:
        gray = np.full((120, 240), 120, dtype=np.uint8)
        gray[:, :30] = 255
        gray[:, 210:] = 0
        gray[:20, :] = 255
        gray[100:, :] = 0

        groups = _groups_by_source(gray)

        self.assertEqual(
            {observation.side for observation in groups["holder_boundary"]},
            {"leading", "trailing", "top", "bottom"},
        )

    def test_holder_gradient_does_not_move_the_aperture_into_holder_boundary(self) -> None:
        gray = np.full((120, 240), 120, dtype=np.uint8)
        gray[:, :40] = np.linspace(240, 250, 40, dtype=np.uint8)
        gray[:, 200:] = np.linspace(250, 240, 40, dtype=np.uint8)
        gray[:20, :] = 245
        gray[100:, :] = 245

        groups = _groups_by_source(gray)
        paths = {path.side: path for path in groups["holder_boundary"]}

        self.assertEqual(paths["leading"].position.midpoint, 40.0)
        self.assertEqual(paths["trailing"].position.midpoint, 201.0)
        self.assertEqual(paths["top"].position.midpoint, 20.0)
        self.assertEqual(paths["bottom"].position.midpoint, 101.0)

    def test_sequence_hypothesis_carries_four_side_boundary_provenance(self) -> None:
        gray = np.full((120, 240), 255, dtype=np.uint8)
        gray[20:100, 40:200] = 120
        proposals = _base_candidates(gray)
        measured = [
            proposal
            for proposal in proposals
            if proposal.provenance.boundary_anchors
        ]
        self.assertTrue(measured)
        self.assertTrue(
            all(
                set(proposal.provenance.boundary_anchors)
                == {"leading", "trailing", "top", "bottom"}
                for proposal in measured
            )
        )

    def test_full_canvas_is_preserved_as_safe_overcontain_proposal(self) -> None:
        gray = np.full((120, 240), 255, dtype=np.uint8)
        proposals = _base_candidates(gray)
        full_canvas = next(
            item
            for item in proposals
            if item.provenance.source == "full_canvas"
        )
        self.assertEqual(
            (
                full_canvas.crop_envelope.box.left,
                full_canvas.crop_envelope.box.top,
                full_canvas.crop_envelope.box.right,
                full_canvas.crop_envelope.box.bottom,
            ),
            (0, 0, 240, 120),
        )

    def test_uniform_edge_does_not_invent_holder_boundary_transition(self) -> None:
        gray = np.full((120, 240), 80, dtype=np.uint8)
        groups = _groups_by_source(gray)
        self.assertEqual(groups["holder_boundary"], ())

    def test_uniform_canvas_has_no_invented_pixel_transition(self) -> None:
        for value in (0, 255):
            with self.subTest(value=value):
                gray = np.full((120, 240), value, dtype=np.uint8)
                groups = _groups_by_source(gray)
                self.assertEqual(groups["tonal"], ())
                self.assertEqual(groups["texture"], ())
                proposals = _base_candidates(gray)
                self.assertEqual(
                    [item.provenance.source for item in proposals],
                    ["full_canvas"],
                )

    def test_content_expands_crop_envelope_without_changing_sequence_geometry(self) -> None:
        gray = np.full((100, 200), 255, dtype=np.uint8)
        gray[10:90, 10:190] = 80
        content_evidence = np.zeros((100, 200), dtype=np.float32)
        content_evidence[10:90, 10:190] = 1.0
        physical_box = Box(20, 20, 180, 80)
        physical = SequenceHypothesis(
            visible_sequence_span=VisibleSequenceSpan(physical_box),
            crop_envelope=CropEnvelope(physical_box),
            provenance=MeasurementProvenance(
                MeasurementIdentity.HOLDER_BOUNDARY_PROFILE,
                "synthetic",
                (MeasurementIdentity.GRAY_WORK,),
            ),
            boundary_paths=(),
        )
        expanded = expand_crop_envelopes_for_content(
            content_evidence,
            [physical],
            ContentEvidenceParameters(),
        )[0]
        self.assertEqual(expanded.visible_sequence_span, physical.visible_sequence_span)
        self.assertEqual(expanded.crop_envelope.box, Box(10, 10, 190, 90))
        self.assertEqual(expanded.provenance, physical.provenance)


if __name__ == "__main__":
    unittest.main()
