from __future__ import annotations

import ast
from dataclasses import replace
import inspect
from pathlib import Path
import unittest

from x5crop.domain import (
    Box,
    EvidenceState,
    FiniteInterval,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PositiveInterval,
)
from x5crop.formats import DIRECT_USE_BUDGET_SPEC
from x5crop.formats.scan_canvas import ScanCanvasPhysicalSpec
from x5crop.geometry.affine import AffineCoordinateTransform
from x5crop.detection.evidence.scan_canvas import (
    CanvasAxisScaleIntervals,
    ScanCanvasEvidence,
    ScanCanvasOutcome,
    ScanCanvasProfileMatch,
)
from x5crop.detection.photo_geometry.model import AuthoritySide, BoundaryRole
from x5crop.detection.photo_geometry.template_output import (
    safe_crop_envelope_from_template_placement,
    template_direct_use_budget_assessment,
)
from x5crop.detection.source_core import (
    SourceLaneEvidence,
    SourceStripValidationDomain,
)
from tools.tests.test_template_placement_contract import (
    _compose,
    _cross,
    _direction,
    _sequence,
    _template,
)


def _placement():
    template = _template(1)
    direction = _direction()
    return _compose(
        template,
        _sequence(template),
        _cross(template, direction=direction),
    )


def _lane(lane_id: str = "lane:test") -> SourceLaneEvidence:
    profile = ScanCanvasPhysicalSpec(
        profile_id="template-output-holder",
        short_axis_mm=40.0,
        long_axis_mm=50.0,
    )
    shared_scale = PositiveInterval.exact(10.0)
    scales = CanvasAxisScaleIntervals(
        holder_profile_id=profile.profile_id,
        width_axis_px_per_mm=shared_scale,
        height_axis_px_per_mm=shared_scale,
        source_width_axis="x",
        source_height_axis="y",
    )
    scan_canvas = ScanCanvasEvidence(
        outcome=ScanCanvasOutcome.SUPPORTED,
        observed_long_axis_px=500,
        observed_short_axis_px=400,
        matches=(
            ScanCanvasProfileMatch(
                profile=profile,
                aspect_error_ratio=0.0,
                shared_scale_px_per_mm=shared_scale,
            ),
        ),
        selected_profile=profile,
        axis_scales=scales,
        provenance=MeasurementProvenance(
            root_measurement=MeasurementIdentity.SCAN_CANVAS_GEOMETRY,
            observation_id=ObservationId("template-output:canvas"),
            dependencies=(),
            description="template output test canvas",
        ),
    )
    return SourceLaneEvidence(
        domain=SourceStripValidationDomain(
            lane_id=lane_id,
            work_box=Box(0, 0, 500, 400),
            source_axis_long="x",
            authority_profile_id=profile.profile_id,
        ),
        scan_canvas=scan_canvas,
    )


class TemplateOutputContractTest(unittest.TestCase):
    def test_selected_placement_produces_supported_safe_output(self) -> None:
        placement = _placement()
        transform = AffineCoordinateTransform.identity(500, 400)
        envelope = safe_crop_envelope_from_template_placement(
            placement,
            lane=_lane(),
            lane_ordinal=1,
            layout="horizontal",
            transform=transform,
        )
        self.assertEqual(
            envelope.placement_source_footprint,
            placement.frames[0].canonical_source_polygon,
        )
        self.assertEqual(envelope.saturation_facts, ())
        assessment = template_direct_use_budget_assessment(
            placement,
            envelope,
            transform,
        )
        self.assertEqual(assessment.state, EvidenceState.SUPPORTED)
        self.assertEqual(
            tuple(item.role for item in assessment.edge_assessments),
            (
                BoundaryRole.START,
                BoundaryRole.END,
                BoundaryRole.TOP,
                BoundaryRole.BOTTOM,
            ),
        )
        self.assertEqual(
            assessment.placement_solution_ids,
            (placement.placement_id,),
        )
        self.assertTrue(
            all(
                item.worst_placement_solution_id == placement.placement_id
                for item in assessment.edge_assessments
            )
        )

    def test_lane_clipping_is_explicit_and_budget_can_contradict(self) -> None:
        placement = _placement()
        frame = placement.frames[0]
        unsafe_top = replace(
            frame.top,
            full_position_interval_px=FiniteInterval(-20.0, 10.0),
        )
        placement = replace(
            placement,
            frames=(replace(frame, top=unsafe_top),),
        )
        transform = AffineCoordinateTransform.identity(500, 400)
        envelope = safe_crop_envelope_from_template_placement(
            placement,
            lane=_lane(),
            lane_ordinal=1,
            layout="horizontal",
            transform=transform,
        )
        self.assertIn(
            AuthoritySide.TOP,
            tuple(item.authority_side for item in envelope.saturation_facts),
        )
        self.assertGreaterEqual(
            min(point[1] for point in envelope.constrained_source_footprint),
            0.0,
        )
        assessment = template_direct_use_budget_assessment(
            placement,
            envelope,
            transform,
        )
        self.assertEqual(assessment.state, EvidenceState.CONTRADICTED)
        top = next(
            item
            for item in assessment.edge_assessments
            if item.role == BoundaryRole.TOP
        )
        self.assertFalse(top.within_limit)

    def test_mismatched_lane_and_nonselected_geometry_are_rejected(self) -> None:
        placement = _placement()
        transform = AffineCoordinateTransform.identity(500, 400)
        with self.assertRaises(ValueError):
            safe_crop_envelope_from_template_placement(
                placement,
                lane=_lane("lane:other"),
                lane_ordinal=1,
                layout="horizontal",
                transform=transform,
            )
        envelope = safe_crop_envelope_from_template_placement(
            placement,
            lane=_lane(),
            lane_ordinal=1,
            layout="horizontal",
            transform=transform,
        )
        tampered = replace(
            envelope,
            required_source_footprint=envelope.placement_source_footprint,
        )
        with self.assertRaises(ValueError):
            template_direct_use_budget_assessment(
                placement,
                tampered,
                transform,
            )

    def test_invalid_ordinal_and_output_extent_fail_without_fallback(self) -> None:
        placement = _placement()
        with self.assertRaises(ValueError):
            safe_crop_envelope_from_template_placement(
                placement,
                lane=_lane(),
                lane_ordinal=0,
                layout="horizontal",
                transform=AffineCoordinateTransform.identity(500, 400),
            )
        with self.assertRaises(ValueError):
            safe_crop_envelope_from_template_placement(
                placement,
                lane=_lane(),
                lane_ordinal=1,
                layout="horizontal",
                transform=AffineCoordinateTransform.identity(150, 150),
            )

    def test_api_is_current_only_and_ratios_are_frozen(self) -> None:
        self.assertEqual(
            tuple(
                inspect.signature(
                    safe_crop_envelope_from_template_placement
                ).parameters
            ),
            ("placement", "lane", "lane_ordinal", "layout", "transform"),
        )
        self.assertEqual(
            tuple(
                inspect.signature(
                    template_direct_use_budget_assessment
                ).parameters
            ),
            ("placement", "envelope", "transform"),
        )
        self.assertEqual(DIRECT_USE_BUDGET_SPEC.sequence_ratio_per_side, 0.05)
        self.assertEqual(DIRECT_USE_BUDGET_SPEC.cross_ratio_per_side, 0.03)
        path = (
            Path(__file__).parents[2]
            / "x5crop/detection/photo_geometry/template_output.py"
        )
        source = path.read_text()
        tree = ast.parse(source)
        modules = tuple(
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        )
        forbidden = (
            "chains",
            "fixed_frame_geometry",
            "candidate_sampling",
            "materialization",
            "selection",
            "cache",
            "frame_footprints",
            "corridors",
        )
        self.assertFalse(
            any(token in module for token in forbidden for module in modules)
        )
        self.assertNotIn("UNAVAILABLE", source)


if __name__ == "__main__":
    unittest.main()
