from __future__ import annotations

import ast
from dataclasses import fields
import unittest

from tools.tests.support.architecture import PROJECT_ROOT
from x5crop.detection.physical import model
from x5crop.detection.physical import short_axis


class FrameSlotArchitectureContractTest(unittest.TestCase):
    def test_short_axis_plan_has_one_canonical_owner(self) -> None:
        owners: dict[str, list[str]] = {
            "SharedShortAxisPlan": [],
            "shared_short_axis_from_photo_edge_pair": [],
        }
        physical_root = PROJECT_ROOT / "x5crop/detection/physical"
        for path in physical_root.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in tree.body:
                if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
                    if node.name in owners:
                        owners[node.name].append(path.name)

        self.assertEqual(owners["SharedShortAxisPlan"], ["short_axis.py"])
        self.assertEqual(
            owners["shared_short_axis_from_photo_edge_pair"],
            ["short_axis.py"],
        )

    def test_frame_width_constraint_families_have_distinct_canonical_types(
        self,
    ) -> None:
        import x5crop.detection.physical.model as model

        for type_name in (
            "HolderSpanScaleHint",
            "ContentExtentConstraint",
            "IndexedAnchorDistanceConstraint",
            "FrameWidthMeasurementConstraint",
        ):
            with self.subTest(type_name=type_name):
                self.assertTrue(hasattr(model, type_name))

    def test_search_and_geometry_constraints_do_not_claim_evidence_state(
        self,
    ) -> None:
        for constraint_type in (
            model.HolderSpanScaleHint,
            model.ContentExtentConstraint,
            model.IndexedAnchorDistanceConstraint,
            short_axis.FrameWidthSearchHint,
        ):
            with self.subTest(constraint_type=constraint_type.__name__):
                self.assertNotIn(
                    "state",
                    {field.name for field in fields(constraint_type)},
                )

    def test_canonical_frame_sequence_types_exist(self) -> None:
        expected = {
            "ResolvedFrameBoundary",
            "FrameSlot",
            "FrameWidthMeasurementConstraint",
            "FrameWidthPhysicalScaleConstraint",
            "CommonFrameWidthResolution",
            "SequenceInferredSlotGeometry",
            "SeparatorBandAssignment",
            "FrameSequenceSolution",
            "DualLaneFrameSolution",
            "ReviewOnlyContainment",
        }

        self.assertTrue(expected.issubset(vars(model)))

    def test_frame_sequence_owns_one_shared_short_axis_and_ordered_slots(self) -> None:
        solution_fields = {field.name for field in fields(model.FrameSequenceSolution)}

        self.assertIn("shared_short_axis", solution_fields)
        self.assertIn("frame_slots", solution_fields)
        self.assertIn("inter_frame_spacings", solution_fields)
        self.assertIn("common_frame_width", solution_fields)
        self.assertTrue(
            {
                "holder_span_scale_hint",
                "content_extent_constraint",
                "indexed_anchor_distance_constraints",
                "frame_width_search_hint",
            }.issubset(solution_fields)
        )
        self.assertNotIn("photo_apertures", solution_fields)
        self.assertNotIn("cross_axis_hypotheses", solution_fields)
        self.assertNotIn("crop_envelope", solution_fields)

    def test_frame_slot_has_no_independent_short_axis_geometry(self) -> None:
        slot_fields = {field.name for field in fields(model.FrameSlot)}

        self.assertEqual(
            slot_fields,
            {
                "index",
                "visible_long_axis",
                "leading",
                "trailing",
                "content_occupancy",
                "edge_occlusion",
                "sequence_inference",
            },
        )
        self.assertNotIn("top", slot_fields)
        self.assertNotIn("bottom", slot_fields)

    def test_short_axis_has_no_holder_resolved_basis(self) -> None:
        self.assertFalse(hasattr(model, "SharedShortAxisBasis"))
        self.assertFalse(hasattr(model, "SharedShortAxisSafetySpan"))
        self.assertEqual(
            set(short_axis.SharedShortAxisPlan.__dataclass_fields__),
            {
                "photo_edge_pair_id",
                "span",
                "outcome",
                "position_uncertainty_px",
                "provenance",
            },
        )

    def test_common_width_owns_measurement_constraints_not_index_copies(self) -> None:
        resolution_fields = {
            field.name for field in fields(model.CommonFrameWidthResolution)
        }

        self.assertEqual(
            resolution_fields,
            {
                "width_px",
                "constraints",
                "physical_scale_constraint",
                "state",
                "provenance",
            },
        )

    def test_sequence_inference_is_geometry_not_content_identity(self) -> None:
        inference_fields = {
            field.name for field in fields(model.SequenceInferredSlotGeometry)
        }

        self.assertEqual(
            inference_fields,
            {
                "frame_index",
                "position",
                "nominal_interval",
                "safe_output_interval",
                "common_width_px",
                "inference_inputs",
                "geometry_state",
                "measurement_state",
                "provenance",
            },
        )

    def test_sequence_inference_never_owns_gate_or_proof_authority(self) -> None:
        candidate_gate = (
            PROJECT_ROOT / "x5crop/detection/candidate/assessment/candidate_gate.py"
        ).read_text(encoding="utf-8")
        decision_gate = (
            PROJECT_ROOT / "x5crop/detection/decision/decision_gate.py"
        ).read_text(encoding="utf-8")
        proof_model = (
            PROJECT_ROOT / "x5crop/detection/candidate/assessment/model.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("blank", candidate_gate.lower())
        self.assertNotIn("blank", decision_gate.lower())
        self.assertNotIn("blank", proof_model.lower())

    def test_runtime_does_not_name_sequence_geometry_as_blank_content(self) -> None:
        physical = PROJECT_ROOT / "x5crop/detection/physical"
        source = "\n".join(
            path.read_text(encoding="utf-8") for path in physical.rglob("*.py")
        )

        for removed in (
            "Blank" + "FrameSlotInference",
            "Blank" + "FramePosition",
            "blank" + "_inference",
            "BLANK" + "_SLOT_INFERENCE",
        ):
            with self.subTest(removed=removed):
                self.assertNotIn(removed, source)

    def test_active_runtime_has_no_superseded_aperture_sequence_model(self) -> None:
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (PROJECT_ROOT / "x5crop").rglob("*.py")
        )
        for removed in (
            "Photo" + "Aperture",
            "Photo" + "SequenceSolution",
            "Inter" + "PhotoSpacing",
            "photo_" + "apertures",
        ):
            with self.subTest(removed=removed):
                self.assertNotIn(removed, source)


if __name__ == "__main__":
    unittest.main()
