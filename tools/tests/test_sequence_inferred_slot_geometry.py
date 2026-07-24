from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.support.physical_gates import (
    boundary_path_fixture,
    candidate_fixture,
)
from x5crop.detection.physical import (
    sequence_completion as sequence_completion_module,
)
from x5crop.detection.physical.model import (
    SequenceSlotPosition,
    SequenceInferredSlotGeometry,
    BoundaryGeometryState,
    FrameContentOccupancy,
    FrameSlot,
    FrameBoundarySource,
    ResolvedFrameBoundary,
)
from x5crop.domain import (
    BoundarySide,
    BoundaryKind,
    Box,
    ContainmentFallback,
    EvidenceState,
    HolderBoundaryObservation,
    HolderSafetyEnvelope,
    InterFrameSpacing,
    InterFrameSpacingBasis,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
)
from x5crop.detection.physical.sequence_completion import infer_sequence_frame_slot


def _provenance(name: str) -> MeasurementProvenance:
    return MeasurementProvenance(
        root_measurement=MeasurementIdentity.FRAME_GEOMETRY,
        observation_id=ObservationId(name),
        dependencies=(MeasurementIdentity.FRAME_DIMENSIONS,),
        description=name,
    )


def _boundary(name: str, position: float) -> ResolvedFrameBoundary:
    return ResolvedFrameBoundary(
        position=PixelInterval.exact(position),
        source=FrameBoundarySource.SEQUENCE_INFERENCE,
        geometry_state=BoundaryGeometryState.RESOLVED,
        boundary_anchor=None,
        inference_provenance=_provenance(name),
    )


def _inference(
    frame_index: int,
    position: SequenceSlotPosition,
    start: float,
    end: float,
) -> SequenceInferredSlotGeometry:
    common_width = _provenance("common_width")
    neighbor = _provenance(f"neighbor_{frame_index}")
    return SequenceInferredSlotGeometry(
        frame_index=frame_index,
        position=position,
        nominal_interval=PixelInterval(start, end),
        safe_output_interval=PixelInterval(start - 5.0, end + 5.0),
        common_width_px=PixelInterval(end - start, end - start),
        inference_inputs=(common_width, neighbor),
        geometry_state=BoundaryGeometryState.RESOLVED,
        measurement_state=EvidenceState.UNAVAILABLE,
        provenance=_provenance(f"sequence_inferred_{position.value}"),
    )


def _sequence_inferred_slot(
    frame_index: int,
    position: SequenceSlotPosition,
) -> FrameSlot:
    start = float((frame_index - 1) * 110)
    end = start + 100.0
    return FrameSlot(
        index=frame_index,
        visible_long_axis=PixelInterval(start, end),
        leading=_boundary(f"leading_{frame_index}", start),
        trailing=_boundary(f"trailing_{frame_index}", end),
        content_occupancy=FrameContentOccupancy.UNAVAILABLE,
        edge_occlusion=None,
        sequence_inference=_inference(frame_index, position, start, end),
    )


class SequenceInferredSlotGeometryContractTest(unittest.TestCase):
    def test_no_content_does_not_create_a_sequence_inferred_slot(self) -> None:
        slot = FrameSlot(
            index=1,
            visible_long_axis=PixelInterval(0.0, 100.0),
            leading=ResolvedFrameBoundary(
                position=PixelInterval.exact(0.0),
                source=FrameBoundarySource.DIMENSION_CONSTRAINED,
                geometry_state=BoundaryGeometryState.RESOLVED,
                boundary_anchor=None,
                inference_provenance=_provenance("leading"),
            ),
            trailing=ResolvedFrameBoundary(
                position=PixelInterval.exact(100.0),
                source=FrameBoundarySource.DIMENSION_CONSTRAINED,
                geometry_state=BoundaryGeometryState.RESOLVED,
                boundary_anchor=None,
                inference_provenance=_provenance("trailing"),
            ),
            content_occupancy=FrameContentOccupancy.UNAVAILABLE,
            edge_occlusion=None,
            sequence_inference=None,
        )

        self.assertFalse(slot.sequence_inferred)

    def test_sequence_inferred_is_geometry_resolved_and_measurement_unavailable(self) -> None:
        slot = _sequence_inferred_slot(2, SequenceSlotPosition.INTERIOR)

        self.assertTrue(slot.sequence_inferred)
        assert slot.sequence_inference is not None
        self.assertEqual(
            slot.sequence_inference.geometry_state,
            BoundaryGeometryState.RESOLVED,
        )
        self.assertEqual(
            slot.sequence_inference.measurement_state,
            EvidenceState.UNAVAILABLE,
        )
        self.assertFalse(slot.leading.independently_observed)
        self.assertFalse(slot.trailing.independently_observed)

    def test_sequence_inference_does_not_claim_content_occupancy(self) -> None:
        slot = replace(
            _sequence_inferred_slot(2, SequenceSlotPosition.INTERIOR),
            content_occupancy=FrameContentOccupancy.CONTENT_OBSERVED,
        )

        self.assertTrue(slot.sequence_inferred)
        self.assertEqual(
            slot.content_occupancy,
            FrameContentOccupancy.CONTENT_OBSERVED,
        )

    def test_sequence_inferred_position_can_be_leading_interior_or_trailing(self) -> None:
        cases = (
            (1, SequenceSlotPosition.LEADING),
            (2, SequenceSlotPosition.INTERIOR),
            (3, SequenceSlotPosition.TRAILING),
        )

        for frame_index, position in cases:
            with self.subTest(position=position):
                slot = _sequence_inferred_slot(frame_index, position)
                assert slot.sequence_inference is not None
                self.assertEqual(slot.sequence_inference.position, position)

    def test_sequence_inferred_measurement_cannot_be_supported(self) -> None:
        with self.assertRaises(ValueError):
            SequenceInferredSlotGeometry(
                frame_index=2,
                position=SequenceSlotPosition.INTERIOR,
                nominal_interval=PixelInterval(110.0, 210.0),
                safe_output_interval=PixelInterval(105.0, 215.0),
                common_width_px=PixelInterval.exact(100.0),
                inference_inputs=(_provenance("common_width"),),
                geometry_state=BoundaryGeometryState.RESOLVED,
                measurement_state=EvidenceState.SUPPORTED,
                provenance=_provenance("invalid_sequence_inferred"),
            )

    def test_two_sequence_inferred_slots_cannot_form_sequence_geometry(self) -> None:
        geometry = candidate_fixture().geometry

        with self.assertRaisesRegex(ValueError, "at most one inferred frame slot"):
            replace(
                geometry,
                frame_slots=(
                    _sequence_inferred_slot(1, SequenceSlotPosition.LEADING),
                    _sequence_inferred_slot(2, SequenceSlotPosition.TRAILING),
                ),
            )

    def test_uncorroborated_real_frame_overlap_cannot_support_sequence_inference(
        self,
    ) -> None:
        geometry = candidate_fixture().geometry
        reference_spacing = geometry.inter_frame_spacings[0]
        uncorroborated_overlap = InterFrameSpacing(
            boundary=reference_spacing.boundary,
            signed_width_px=PixelInterval(-20.0, -10.0),
            provenance=_provenance("uncorroborated_real_frame_overlap"),
            basis=InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS,
        )

        self.assertFalse(
            sequence_completion_module.measured_sequence_supports_slot_inference(
                geometry.frame_slots,
                (uncorroborated_overlap,),
                geometry.common_frame_width,
            )
        )

    def test_one_frame_sized_gap_can_support_interior_sequence_inference(
        self,
    ) -> None:
        geometry = candidate_fixture().geometry
        reference_spacing = geometry.inter_frame_spacings[0]
        common_width = geometry.common_frame_width.width_px
        assert common_width is not None
        frame_sized_gap = InterFrameSpacing(
            boundary=reference_spacing.boundary,
            signed_width_px=PixelInterval(
                common_width.minimum,
                common_width.maximum + 20.0,
            ),
            provenance=_provenance("single_sequence_inferred_sized_gap"),
            basis=InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS,
        )

        self.assertTrue(
            sequence_completion_module.measured_sequence_supports_slot_inference(
                geometry.frame_slots,
                (frame_sized_gap,),
                geometry.common_frame_width,
            )
        )

    def test_edge_sequence_inferred_nominal_geometry_uses_common_width_not_holder_slack(
        self,
    ) -> None:
        geometry = candidate_fixture().geometry
        real_slots = geometry.frame_slots
        holder_path_provenance = _provenance("leading_holder_path")
        holder_path = boundary_path_fixture(
            BoundarySide.LEADING,
            PixelInterval.exact(0.0),
            BoundaryKind.EDGE_ADJACENT_TRANSITION,
            holder_path_provenance,
        )
        holder_boundary = HolderBoundaryObservation(
            BoundarySide.LEADING,
            PixelInterval.exact(0.0),
            (holder_path,),
        )
        holder = HolderSafetyEnvelope(
            (holder_boundary,),
            ContainmentFallback(
                Box(0, 0, 1000, 200),
                _provenance("holder_containment"),
            ),
        )
        shifted_slots = tuple(
            replace(
                slot,
                index=index,
                visible_long_axis=PixelInterval(
                    slot.visible_long_axis.minimum + 500.0,
                    slot.visible_long_axis.maximum + 500.0,
                ),
                leading=replace(
                    slot.leading,
                    position=PixelInterval(
                        slot.leading.position.minimum + 500.0,
                        slot.leading.position.maximum + 500.0,
                    ),
                ),
                trailing=replace(
                    slot.trailing,
                    position=PixelInterval(
                        slot.trailing.position.minimum + 500.0,
                        slot.trailing.position.maximum + 500.0,
                    ),
                ),
            )
            for index, slot in enumerate(real_slots, start=1)
        )
        common_width = replace(
            geometry.common_frame_width,
            constraints=tuple(
                replace(
                    constraint,
                    frame_index=index,
                    leading=shifted_slots[index - 1].leading,
                    trailing=shifted_slots[index - 1].trailing,
                )
                for index, constraint in enumerate(
                    geometry.common_frame_width.constraints,
                    start=1,
                )
            ),
        )

        inferred_slot = infer_sequence_frame_slot(
            shifted_slots,
            insertion_index=1,
            common_width=common_width,
            holder_safety=holder,
        )

        self.assertIsNotNone(inferred_slot)
        assert (
            inferred_slot is not None
            and inferred_slot.sequence_inference is not None
        )
        nominal = inferred_slot.sequence_inference.nominal_interval
        width = nominal.maximum - nominal.minimum
        expected = common_width.width_px
        assert expected is not None
        self.assertGreaterEqual(width, expected.minimum)
        self.assertLessEqual(width, expected.maximum)
        self.assertGreater(
            inferred_slot.sequence_inference.safe_output_interval.maximum
            - inferred_slot.sequence_inference.safe_output_interval.minimum,
            width,
        )
        self.assertEqual(
            inferred_slot.trailing.position,
            shifted_slots[0].leading.position,
        )


if __name__ == "__main__":
    unittest.main()
