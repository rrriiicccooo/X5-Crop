from __future__ import annotations

from dataclasses import fields
import unittest

import numpy as np

from x5crop.configuration.grid import (
    CALIBRATION_RECEIPT_ID,
    GRID_CALIBRATION_RECEIPT,
    frame_grid_search_prior,
)
from x5crop.configuration.model import FrameCountMode
from x5crop.configuration.registry import get_detection_configuration
from x5crop.configuration.scan_canvas import ScanCanvasDetectionConfiguration
from x5crop.detection.evidence.scan_canvas import (
    ScanCanvasOutcome,
    observe_scan_canvas,
)
from x5crop.detection.evidence.separator import (
    observe_long_axis_separator_field,
    separator_corridor_observations,
)
from x5crop.detection.grid.model import FrameGridWorkStatistics
from x5crop.detection.source_core import (
    SourceLaneEvidence,
    SourceStripValidationDomain,
    _compact_components,
    _content_fields,
)
from x5crop.domain import (
    Box,
    FiniteInterval,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
)
from x5crop.formats import format_spec
from x5crop.formats.scan_canvas import (
    SCAN_CANVAS_PHYSICAL_SPECS,
    ScanCanvasFormatFit,
    ScanCanvasPhysicalSpec,
    scan_canvas_specs_for_format,
)


def _content_provenance() -> MeasurementProvenance:
    return MeasurementProvenance(
        root_measurement=MeasurementIdentity.SOURCE_CONTENT,
        observation_id=ObservationId("test:content"),
        dependencies=(MeasurementIdentity.BASE_GRAY,),
        description="test content",
    )


class SourceMeasurementContractTest(unittest.TestCase):
    def test_content_fields_use_edge_replicated_five_point_and_local_texture(
        self,
    ) -> None:
        gray = np.asarray(
            ((5, 10, 20, 25), (7, 14, 21, 28), (9, 18, 27, 36)),
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
        np.testing.assert_allclose(
            intensity,
            expected_intensity,
            rtol=0,
            atol=1e-7,
        )
        np.testing.assert_allclose(
            texture,
            (dx + dy) / np.float32(510.0),
            rtol=0,
            atol=1e-7,
        )

    def test_content_components_are_strict_four_connected_and_immutable(
        self,
    ) -> None:
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
        self.assertGreater(peak_bytes, 0)
        for array in (
            table.rows,
            table.lefts,
            table.rights,
            table.component_indices,
        ):
            self.assertFalse(array.flags.writeable)

    def test_separator_field_has_independent_owner_and_immutable_arrays(
        self,
    ) -> None:
        gray = np.zeros((40, 220), dtype=np.uint8)
        gray[:, 50:90] = 180
        gray[:, 96:136] = 220
        gray[:, 142:182] = 160
        field = observe_long_axis_separator_field(gray, "lane:0")
        self.assertEqual(
            field.provenance.root_measurement,
            MeasurementIdentity.SEPARATOR_FIELD,
        )
        self.assertNotIn(
            MeasurementIdentity.SOURCE_CONTENT,
            field.provenance.dependencies,
        )
        self.assertFalse(field.difference_support.flags.writeable)
        self.assertFalse(field.mean_absolute_difference.flags.writeable)
        coordinates = tuple(round(line.boundary_px) for line in field.lines)
        self.assertIn(50, coordinates)
        self.assertIn(90, coordinates)
        self.assertIn(96, coordinates)
        self.assertIn(136, coordinates)
        observation_set = separator_corridor_observations(
            field,
            FiniteInterval(4.0, 8.0),
            equality_interval_px=1.0,
        )
        self.assertTrue(
            any(
                item.kind == "edge_pair"
                for item in observation_set.corridors
            )
        )
        self.assertTrue(observation_set.bands)
        self.assertIsNotNone(observation_set.learned_gutter_px)
        self.assertTrue(
            any(
                item.kind == "one_sided"
                for item in observation_set.corridors
            )
        )
        self.assertTrue(
            all(
                item.learned_gutter_px
                == observation_set.learned_gutter_px
                for item in observation_set.corridors
                if item.kind == "one_sided"
            )
        )
        self.assertEqual(
            observation_set.work.pair_query_count,
            len(field.lines),
        )


class PhysicalAuthorityContractTest(unittest.TestCase):
    def test_design_components_and_strip_contract_are_current(self) -> None:
        expected = {
            "135": ((36.0, 24.0), 6, True),
            "135-dual": ((36.0, 24.0), 12, False),
            "half": ((18.0, 24.0), 12, True),
            "xpan": ((65.0, 24.0), 3, True),
            "120-645": ((42.0, 54.0), (42.0, 56.0), 4, True),
            "120-66": ((54.0, 54.0), (56.0, 56.0), 3, True),
            "120-67": ((70.0, 54.0), (70.0, 56.0), 3, True),
        }
        for format_id, values in expected.items():
            spec = format_spec(format_id)
            components = values[:-2]
            self.assertEqual(
                tuple(
                    (item.long_axis_mm, item.short_axis_mm)
                    for item in spec.aperture_components
                ),
                components,
            )
            self.assertEqual(spec.strip.default_count, values[-2])
            self.assertEqual(spec.strip.partial_mode_supported, values[-1])

    def test_scan_canvas_catalog_preserves_capacity_authority(self) -> None:
        self.assertEqual(len(SCAN_CANVAS_PHYSICAL_SPECS), 7)
        self.assertNotIn(
            "120_wide_188_5",
            tuple(
                item.profile_id
                for item in scan_canvas_specs_for_format("120-67", 3)
            ),
        )
        auto = get_detection_configuration("120-67", "partial", None)
        explicit = get_detection_configuration("120-67", "partial", 2)
        self.assertEqual(auto.count_request.mode, FrameCountMode.AUTO)
        self.assertIsNone(auto.count_request.authoritative_count)
        self.assertIn(
            "120_wide_188_5",
            tuple(item.profile_id for item in auto.scan_canvas.profiles),
        )
        self.assertEqual(explicit.count_request.mode, FrameCountMode.EXPLICIT)
        self.assertEqual(explicit.count_request.authoritative_count, 2)
        self.assertIn(
            "120_wide_188_5",
            tuple(item.profile_id for item in explicit.scan_canvas.profiles),
        )

    def test_scan_canvas_is_the_only_scale_owner(self) -> None:
        profile = ScanCanvasPhysicalSpec(
            "only",
            short_axis_mm=10.0,
            long_axis_mm=50.0,
            format_fits=(ScanCanvasFormatFit("135", 6),),
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
            evidence.axis_scales.long_axis_px_per_mm.minimum,
            10.0,
        )
        self.assertEqual(
            tuple(item.name for item in fields(SourceLaneEvidence)),
            ("domain", "scan_canvas", "content"),
        )


class PriorAndWorkContractTest(unittest.TestCase):
    def test_calibration_receipt_is_reproducible_and_does_not_claim_grid(
        self,
    ) -> None:
        receipt = GRID_CALIBRATION_RECEIPT
        self.assertEqual(receipt.calibration_receipt_id, CALIBRATION_RECEIPT_ID)
        self.assertEqual(receipt.provenance, "user_confirmed_geometry")
        self.assertEqual(
            receipt.schema,
            "x5crop_grid_calibration_receipt_v2",
        )
        self.assertEqual(
            receipt.algorithm_revision,
            "bounded_ordered_capacity_grid_v5",
        )
        self.assertEqual(
            receipt.search_contract.slot_count_policy,
            "single_resolved_output_slot_count",
        )
        self.assertEqual(
            receipt.search_contract.proposal_resolution,
            "output_equivalence_outward_union_only",
        )
        self.assertEqual(
            receipt.search_contract.omission_resolution,
            "proven_equivalent_and_union_absorbed_only",
        )
        self.assertEqual(len(receipt.cells), 8)
        self.assertNotIn("S098", tuple(cell.sample_id for cell in receipt.cells))
        self.assertEqual(len(receipt.source_sha256_set), 8)
        prior = frame_grid_search_prior("135", "partial", 36.0)
        self.assertEqual(prior.calibration_receipt_id, CALIBRATION_RECEIPT_ID)
        self.assertEqual(prior.provenance, "user_confirmed_geometry")
        for format_id, aperture in (("xpan", 65.0), ("120-645", 42.0)):
            self.assertEqual(
                frame_grid_search_prior(
                    format_id,
                    "partial",
                    aperture,
                ).provenance,
                "physical_rule",
            )

    def test_structural_work_limits_match_frozen_topology(self) -> None:
        self.assertEqual(FrameGridWorkStatistics.state_limit(1), 0)
        self.assertEqual(FrameGridWorkStatistics.transition_limit(1), 0)
        self.assertEqual(FrameGridWorkStatistics.state_limit(12), 198)
        self.assertEqual(FrameGridWorkStatistics.transition_limit(12), 558)


if __name__ == "__main__":
    unittest.main()
