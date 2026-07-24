from __future__ import annotations

from dataclasses import replace
import unittest

import numpy as np

from x5crop.cache import MeasurementCacheStatistics
from x5crop.configuration.registry import get_detection_configuration
from x5crop.configuration.scan_canvas import ScanCanvasDetectionConfiguration
from x5crop.detection.evidence.scan_canvas import (
    CanvasPixelScale,
    ScanCanvasOutcome,
    observe_scan_canvas,
)
from x5crop.detection.evidence.photo_edges import PhotoEdgeFact
from x5crop.detection.workspace import prepare_detection_workspace
from x5crop.domain import EvidenceState
from x5crop.formats.scan_canvas import (
    SCAN_CANVAS_PHYSICAL_SPECS,
    ScanCanvasPhysicalSpec,
    scan_canvas_specs_for_format,
)
from x5crop.io.model import ImageProfile, TiffMetadata
from x5crop.report.read_models import scan_canvas_evidence_read_model


class ScanCanvasPhysicalModelTests(unittest.TestCase):
    def test_catalog_has_one_canonical_set_of_known_profiles(self) -> None:
        self.assertEqual(
            {
                spec.profile_id: (
                    spec.short_axis_mm,
                    spec.long_axis_mm,
                    spec.format_ids,
                )
                for spec in SCAN_CANVAS_PHYSICAL_SPECS
            },
            {
                "135_standard": (
                    32.22,
                    232.0,
                    ("135", "half", "xpan"),
                ),
                "135_narrow": (
                    25.4,
                    232.0,
                    ("135", "half", "xpan"),
                ),
                "120_standard": (
                    60.0,
                    226.0,
                    ("120-645", "120-66", "120-67"),
                ),
                "120_wide": (
                    63.44,
                    224.5,
                    ("120-645", "120-66", "120-67"),
                ),
                "120_66_three_frame": (
                    63.44,
                    188.5,
                    ("120-66",),
                ),
            },
        )

    def test_frame_and_scan_canvas_physical_facts_remain_separate(self) -> None:
        from x5crop.formats import FramePhysicalSpec

        self.assertNotIn(
            "scan_canvas",
            FramePhysicalSpec.__dataclass_fields__,
        )
        self.assertEqual(
            set(ScanCanvasPhysicalSpec.__dataclass_fields__),
            {
                "profile_id",
                "short_axis_mm",
                "long_axis_mm",
                "format_ids",
            },
        )

    def test_all_single_strip_configurations_receive_explicit_profiles(
        self,
    ) -> None:
        for format_id in (
            "135",
            "half",
            "xpan",
            "120-645",
            "120-66",
            "120-67",
        ):
            with self.subTest(format_id=format_id):
                configuration = get_detection_configuration(
                    format_id,
                    "full",
                )
                self.assertEqual(
                    configuration.scan_canvas.profiles,
                    scan_canvas_specs_for_format(format_id),
                )

        dual = get_detection_configuration("135-dual", "full")
        self.assertEqual(dual.scan_canvas.profiles, ())

    def test_known_pixel_extents_select_unique_profiles(self) -> None:
        cases = (
            ("135", 20140, 2797, "135_standard"),
            ("135", 18268, 1998, "135_narrow"),
            ("120-67", 15055, 3997, "120_standard"),
            ("120-66", 9899, 2797, "120_wide"),
            ("120-66", 14142, 3996, "120_wide"),
        )
        for format_id, width, height, expected in cases:
            with self.subTest(format_id=format_id, extent=(width, height)):
                configuration = get_detection_configuration(
                    format_id,
                    "full",
                )
                evidence = observe_scan_canvas(
                    width,
                    height,
                    "horizontal",
                    configuration.scan_canvas,
                )
                self.assertEqual(evidence.outcome, ScanCanvasOutcome.SUPPORTED)
                assert evidence.selected_profile is not None
                self.assertEqual(evidence.selected_profile.profile_id, expected)
                self.assertIsInstance(evidence.pixel_scale, CanvasPixelScale)

    def test_effective_scale_is_derived_from_canvas_not_tiff_metadata(
        self,
    ) -> None:
        evidence = observe_scan_canvas(
            20140,
            2797,
            "horizontal",
            get_detection_configuration("135", "full").scan_canvas,
        )
        assert evidence.pixel_scale is not None
        self.assertAlmostEqual(
            evidence.pixel_scale.long_axis_px_per_mm,
            20140.0 / 232.0,
        )
        self.assertAlmostEqual(
            evidence.pixel_scale.short_axis_px_per_mm,
            2797.0 / 32.22,
        )
        self.assertEqual(evidence.pixel_scale.source_long_axis, "x")

        vertical = observe_scan_canvas(
            20140,
            2797,
            "vertical",
            get_detection_configuration("135", "full").scan_canvas,
        )
        assert vertical.pixel_scale is not None
        self.assertEqual(vertical.pixel_scale.source_long_axis, "y")

        read_model = scan_canvas_evidence_read_model(evidence)
        self.assertAlmostEqual(
            read_model["effective_ppi"]["long_axis"],
            evidence.pixel_scale.long_axis_px_per_mm * 25.4,
        )
        self.assertAlmostEqual(
            read_model["effective_ppi"]["short_axis"],
            evidence.pixel_scale.short_axis_px_per_mm * 25.4,
        )

    def test_unmatched_competing_and_dual_outcomes_are_typed(self) -> None:
        standard = get_detection_configuration("135", "full").scan_canvas
        unmatched = observe_scan_canvas(
            1000,
            1000,
            "horizontal",
            standard,
        )
        self.assertEqual(
            unmatched.outcome,
            ScanCanvasOutcome.ASPECT_CONTRADICTED,
        )
        self.assertIsNone(unmatched.pixel_scale)

        duplicate_geometry = ScanCanvasPhysicalSpec(
            "duplicate",
            short_axis_mm=32.22,
            long_axis_mm=232.0,
            format_ids=("135",),
        )
        competing_configuration = replace(
            standard,
            profiles=(*standard.profiles, duplicate_geometry),
        )
        competing = observe_scan_canvas(
            20140,
            2797,
            "horizontal",
            competing_configuration,
        )
        self.assertEqual(
            competing.outcome,
            ScanCanvasOutcome.COMPETING_PROFILES_UNRESOLVED,
        )
        self.assertIsNone(competing.selected_profile)

        dual = observe_scan_canvas(
            2000,
            1000,
            "horizontal",
            ScanCanvasDetectionConfiguration(()),
        )
        self.assertEqual(dual.outcome, ScanCanvasOutcome.NOT_APPLICABLE)
        self.assertIsNone(dual.pixel_scale)

    def test_aspect_limit_is_exactly_half_a_percent(self) -> None:
        configuration = get_detection_configuration(
            "135",
            "full",
        ).scan_canvas
        self.assertEqual(configuration.maximum_aspect_error_ratio, 0.005)

    def test_equivalent_measurement_tracks_form_one_physical_pair(self) -> None:
        pixels = np.full((322, 2320), 230, dtype=np.uint8)
        photo_texture = (
            70
            + 4
            * (
                np.arange(pixels.shape[1], dtype=np.uint16)
                % 7
            )
        ).astype(np.uint8)
        pixels[41:281, :] = photo_texture
        profile = ImageProfile(
            shape=pixels.shape,
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

        workspace = prepare_detection_workspace(
            pixels,
            profile,
            "horizontal",
            get_detection_configuration("135", "full"),
            None,
            MeasurementCacheStatistics(),
            "0" * 64,
        )
        evidence = workspace.source_photo_edge_pairs[0]

        self.assertEqual(evidence.state, EvidenceState.SUPPORTED)
        self.assertEqual(len(evidence.fragment_summaries), 2)
        self.assertEqual(len(evidence.hypotheses), 1)
        self.assertEqual(
            tuple(
                label.identity
                for label in evidence.hypotheses[0].physical_labels
            ),
            ("135_standard:36x24",),
        )
        self.assertIsNotNone(evidence.selected_pair_id)
        assert evidence.physical_selection is not None
        self.assertEqual(
            evidence.physical_selection.scan_canvas_profile_id,
            "135_standard",
        )
        self.assertEqual(
            (
                evidence.physical_selection.frame_size_mm.width_mm,
                evidence.physical_selection.frame_size_mm.height_mm,
            ),
            (36.0, 24.0),
        )
        mapped = workspace.mapped_photo_edge_pairs[0]
        self.assertEqual(mapped.search_corridors, ())
        self.assertEqual(
            mapped.physical_selection,
            evidence.physical_selection,
        )
        self.assertEqual(len(mapped.fragment_summaries), 2)
        self.assertEqual(
            workspace.shared_short_axes[0].photo_edge_pair_id,
            mapped.observation_id,
        )

    def test_overlapping_120_height_options_remain_explicitly_unresolved(
        self,
    ) -> None:
        pixels = np.full((600, 2260), 230, dtype=np.uint8)
        x = np.arange(pixels.shape[1], dtype=np.uint16)
        outer_photo_texture = (30 + 2 * (x % 3)).astype(np.uint8)
        inner_photo_texture = (70 + 6 * (x % 5)).astype(np.uint8)
        pixels[20:30, :] = outer_photo_texture
        pixels[30:570, :] = inner_photo_texture
        pixels[570:580, :] = outer_photo_texture
        profile = ImageProfile(
            shape=pixels.shape,
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

        workspace = prepare_detection_workspace(
            pixels,
            profile,
            "horizontal",
            get_detection_configuration("120-67", "full"),
            None,
            MeasurementCacheStatistics(),
            "0" * 64,
        )
        evidence = workspace.source_photo_edge_pairs[0]

        self.assertEqual(evidence.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(
            evidence.facts,
            (PhotoEdgeFact.COMPETING_PAIRS_UNRESOLVED,),
        )
        self.assertEqual(len(evidence.fragment_summaries), 4)
        self.assertEqual(len(evidence.hypotheses), 4)
        self.assertEqual(
            {
                hypothesis.physical_labels[0].identity
                for hypothesis in evidence.hypotheses
                if hypothesis.state == EvidenceState.SUPPORTED
            },
            {
                "120_standard:70x54",
                "120_standard:70x56",
            },
        )

    def test_material_agnostic_transitions_remain_competing(
        self,
    ) -> None:
        pixels = np.full((322, 2320), 230, dtype=np.uint8)
        x = np.arange(pixels.shape[1], dtype=np.uint16)
        pixels[41:281, :] = (70 + 4 * (x % 7)).astype(np.uint8)
        pixels[281:289, :] = 20
        profile = ImageProfile(
            shape=pixels.shape,
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

        workspace = prepare_detection_workspace(
            pixels,
            profile,
            "horizontal",
            get_detection_configuration("135", "full"),
            None,
            MeasurementCacheStatistics(),
            "0" * 64,
        )
        evidence = workspace.source_photo_edge_pairs[0]

        self.assertEqual(evidence.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(
            evidence.facts,
            (PhotoEdgeFact.COMPETING_PAIRS_UNRESOLVED,),
        )
        self.assertGreaterEqual(
            sum(
                hypothesis.state != EvidenceState.CONTRADICTED
                for hypothesis in evidence.hypotheses
            ),
            2,
        )
        self.assertIsNone(evidence.selected_pair_id)


if __name__ == "__main__":
    unittest.main()
