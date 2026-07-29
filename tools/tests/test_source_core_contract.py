from __future__ import annotations

import unittest
from unittest import mock

import numpy as np

from x5crop.configuration.content import (
    ContentConfiguration,
    ContentEvidenceParameters,
)
from x5crop.configuration.scan_canvas import ScanCanvasDetectionConfiguration
from x5crop.detection.evidence.scan_canvas import (
    ScanCanvasOutcome,
    observe_scan_canvas,
)
from x5crop.detection.source_core import (
    SourceStripValidationDomain,
    _compact_components,
    _content_fields,
    observe_source_content,
    output_protection_authority,
)
from x5crop.domain import (
    Box,
    EvidenceState,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
)
from x5crop.formats import format_spec
from x5crop.formats.scan_canvas import ScanCanvasPhysicalSpec


def _content_provenance() -> MeasurementProvenance:
    return MeasurementProvenance(
        root_measurement=MeasurementIdentity.SOURCE_CONTENT,
        observation_id=ObservationId("test:content"),
        dependencies=(MeasurementIdentity.BASE_GRAY,),
        description="test content",
    )


class SourceCoreMeasurementContractTest(unittest.TestCase):
    def test_content_fields_use_edge_replicated_five_point_and_local_texture(
        self,
    ) -> None:
        gray = np.asarray(
            (
                (5, 10, 20, 25),
                (7, 14, 21, 28),
                (9, 18, 27, 36),
            ),
            dtype=np.uint8,
        )
        intensity, texture = _content_fields(gray)

        data = gray.astype(np.float32)
        padded = np.pad(data, 1, mode="edge")
        mean = (
            padded[1:-1, 1:-1]
            + padded[:-2, 1:-1]
            + padded[2:, 1:-1]
            + padded[1:-1, :-2]
            + padded[1:-1, 2:]
        ) / np.float32(5.0)
        expected_intensity = np.abs(data - mean) / np.float32(255.0)
        dx = np.zeros_like(data)
        dy = np.zeros_like(data)
        dx[:, 1:] = np.abs(data[:, 1:] - data[:, :-1])
        dy[1:, :] = np.abs(data[1:, :] - data[:-1, :])
        expected_texture = (dx + dy) / np.float32(510.0)

        np.testing.assert_allclose(intensity, expected_intensity, rtol=0, atol=1e-7)
        np.testing.assert_allclose(texture, expected_texture, rtol=0, atol=1e-7)
        self.assertTrue(np.all(texture[:, 0] >= 0.0))
        self.assertEqual(float(texture[0, 0]), 0.0)

    def test_strict_four_connectivity_and_immutable_compact_runs(self) -> None:
        domain = SourceStripValidationDomain(
            lane_id="lane:0",
            work_box=Box(10, 20, 18, 28),
            source_axis_long="x",
            authority_profile_id="test_canvas",
        )
        mask = np.zeros((8, 8), dtype=bool)
        mask[1:3, 1:3] = True
        mask[3:5, 3:5] = True
        components, table, raw_count, peak_bytes = _compact_components(
            mask,
            domain,
            minimum_active_pixels=4,
            provenance=_content_provenance(),
        )

        self.assertEqual(raw_count, 2)
        self.assertEqual(len(components), 2)
        self.assertEqual(
            tuple(component.footprint for component in components),
            (Box(11, 21, 13, 23), Box(13, 23, 15, 25)),
        )
        self.assertEqual(table.run_count, 4)
        self.assertGreater(peak_bytes, 0)
        for array in (
            table.rows,
            table.lefts,
            table.rights,
            table.component_indices,
        ):
            self.assertEqual(array.dtype, np.int32)
            self.assertFalse(array.flags.writeable)

    def test_positive_content_is_intersection_of_independent_channels(self) -> None:
        domain = SourceStripValidationDomain(
            lane_id="lane:0",
            work_box=Box(0, 0, 6, 6),
            source_axis_long="x",
            authority_profile_id="test_canvas",
        )
        intensity_mask = np.zeros((6, 6), dtype=bool)
        texture_mask = np.zeros((6, 6), dtype=bool)
        intensity_mask[1:4, 1:4] = True
        texture_mask[2:5, 2:5] = True
        parameters = ContentConfiguration(
            ContentEvidenceParameters(minimum_active_pixels=1)
        )

        with (
            mock.patch(
                "x5crop.detection.source_core.adaptive_activation_threshold",
                side_effect=(0.1, 0.2),
            ),
            mock.patch(
                "x5crop.detection.source_core.spatially_supported_activation_mask",
                side_effect=(intensity_mask, texture_mask),
            ),
        ):
            observation = observe_source_content(
                np.arange(36, dtype=np.uint8).reshape(6, 6),
                domain,
                parameters,
            )

        self.assertEqual(observation.state, EvidenceState.SUPPORTED)
        self.assertEqual(observation.statistics.intensity_active_cells, 9)
        self.assertEqual(observation.statistics.texture_active_cells, 9)
        self.assertEqual(observation.statistics.positive_cells, 4)
        self.assertEqual(observation.statistics.raw_component_count, 1)
        self.assertEqual(len(observation.components), 1)
        self.assertEqual(observation.components[0].footprint, Box(2, 2, 4, 4))


class PhysicalAuthorityContractTest(unittest.TestCase):
    def test_design_components_remain_discrete(self) -> None:
        expected = {
            "135": ((36.0, 24.0),),
            "135-dual": ((36.0, 24.0),),
            "half": ((18.0, 24.0),),
            "xpan": ((65.0, 24.0),),
            "120-645": ((42.0, 54.0), (42.0, 56.0)),
            "120-66": ((54.0, 54.0), (56.0, 56.0)),
            "120-67": ((70.0, 54.0), (70.0, 56.0)),
        }
        for format_id, components in expected.items():
            with self.subTest(format_id=format_id):
                spec = format_spec(format_id)
                self.assertEqual(
                    tuple(
                        (item.long_axis_mm, item.short_axis_mm)
                        for item in spec.aperture_components
                    ),
                    components,
                )

    def test_axis_scales_are_independent_point_intervals(self) -> None:
        profile = ScanCanvasPhysicalSpec(
            "only",
            short_axis_mm=10.0,
            long_axis_mm=50.0,
            format_ids=("135",),
        )
        evidence = observe_scan_canvas(
            500,
            100,
            "horizontal",
            ScanCanvasDetectionConfiguration((profile,)),
        )
        self.assertEqual(evidence.outcome, ScanCanvasOutcome.SUPPORTED)
        assert evidence.axis_scales is not None
        self.assertEqual(
            (
                evidence.axis_scales.long_axis_px_per_mm.minimum,
                evidence.axis_scales.long_axis_px_per_mm.maximum,
            ),
            (10.0, 10.0),
        )
        self.assertEqual(
            (
                evidence.axis_scales.short_axis_px_per_mm.minimum,
                evidence.axis_scales.short_axis_px_per_mm.maximum,
            ),
            (10.0, 10.0),
        )

    def test_multiple_canvas_profiles_remain_unavailable(self) -> None:
        profiles = (
            ScanCanvasPhysicalSpec(
                "a",
                short_axis_mm=10.0,
                long_axis_mm=50.0,
                format_ids=("135",),
            ),
            ScanCanvasPhysicalSpec(
                "b",
                short_axis_mm=20.0,
                long_axis_mm=100.0,
                format_ids=("135",),
            ),
        )
        evidence = observe_scan_canvas(
            500,
            100,
            "horizontal",
            ScanCanvasDetectionConfiguration(profiles),
        )
        self.assertEqual(
            evidence.outcome,
            ScanCanvasOutcome.COMPETING_PROFILES_UNRESOLVED,
        )
        self.assertIsNone(evidence.axis_scales)

    def test_millimetre_protection_has_one_format_owner(self) -> None:
        expected = {
            "half": (0.15, 0.25),
            "135": (0.25, 0.25),
            "135-dual": (0.25, 0.25),
            "120-645": (0.30, 0.25),
            "120-66": (0.40, 0.25),
            "xpan": (0.45, 0.25),
            "120-67": (0.50, 0.25),
        }
        for format_id, values in expected.items():
            with self.subTest(format_id=format_id):
                authority = output_protection_authority(format_spec(format_id))
                self.assertEqual(
                    (authority.long_axis_mm, authority.short_axis_mm),
                    values,
                )
                self.assertFalse(authority.applied)


if __name__ == "__main__":
    unittest.main()
