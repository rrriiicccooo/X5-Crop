from __future__ import annotations

import unittest

from tools.tests.frame_slot_solver_support import path
from x5crop.detection.physical import frame_sequence_candidates as candidate_builds
from x5crop.detection.physical import (
    frame_sequence_candidate_resolution as candidate_resolution,
)
from x5crop.detection.physical import frame_sequence_result as sequence_result
from x5crop.detection.physical.model import (
    BoundaryAnchor,
    BoundaryGeometryState,
    BoundaryRoleAuthority,
    CommonFrameWidthResolution,
    FrameBoundarySource,
    FrameContentOccupancy,
    FrameSlot,
    FrameWidthMeasurementConstraint,
    ResolvedFrameBoundary,
)
from x5crop.domain import (
    BoundaryAxis,
    BoundarySide,
    EvidenceState,
    InterFrameSpacingBasis,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
)


def _measured_boundary(
    position: float,
    side: BoundarySide,
    label: str,
) -> ResolvedFrameBoundary:
    observation = path(BoundaryAxis.LONG, position, label)
    role_provenance = MeasurementProvenance(
        MeasurementIdentity.PHOTO_EDGES,
        ObservationId(f"{label}:role"),
        (observation.provenance.root_measurement,),
        "synthetic independently measured photo edge",
        (observation.provenance.observation_id,),
    )
    return ResolvedFrameBoundary(
        position=observation.position,
        source=FrameBoundarySource.GRAY_PATH_OBSERVATION,
        geometry_state=BoundaryGeometryState.RESOLVED,
        boundary_anchor=BoundaryAnchor(
            observation=observation,
            physical_role=side,
            role_state=EvidenceState.SUPPORTED,
            role_authority=BoundaryRoleAuthority.DIRECT_MEASUREMENT,
            role_provenance=role_provenance,
        ),
        inference_provenance=None,
    )


def _slot(
    index: int,
    leading: ResolvedFrameBoundary,
    trailing: ResolvedFrameBoundary,
) -> FrameSlot:
    return FrameSlot(
        index=index,
        visible_long_axis=PixelInterval(
            leading.position.minimum,
            trailing.position.maximum,
        ),
        leading=leading,
        trailing=trailing,
        content_occupancy=FrameContentOccupancy.UNAVAILABLE,
        edge_occlusion=None,
    )


def _common_width(
    contributors: tuple[FrameSlot, ...],
) -> CommonFrameWidthResolution:
    constraints = tuple(
        FrameWidthMeasurementConstraint(
            slot.index,
            slot.leading,
            slot.trailing,
        )
        for slot in contributors
    )
    width = PixelInterval(
        min(item.width_px.minimum for item in constraints),
        max(item.width_px.maximum for item in constraints),
    )
    anchors = tuple(
        boundary.measurement_provenance.observation_id
        for item in constraints
        for boundary in (item.leading, item.trailing)
    )
    return CommonFrameWidthResolution(
        width_px=width,
        constraints=constraints,
        physical_scale_constraint=None,
        state=EvidenceState.SUPPORTED,
        provenance=MeasurementProvenance(
            MeasurementIdentity.FRAME_DIMENSIONS,
            ObservationId(
                "synthetic_common_width:"
                + ":".join(str(item.frame_index) for item in constraints)
            ),
            (MeasurementIdentity.PHOTO_EDGES,),
            "synthetic common width from independent complete slots",
            anchors,
        ),
    )


def _dimension_trailing_boundary(
    frame_index: int,
    anchor: ResolvedFrameBoundary,
    common_width: CommonFrameWidthResolution,
) -> ResolvedFrameBoundary:
    assert common_width.width_px is not None
    return ResolvedFrameBoundary(
        position=anchor.position.plus(common_width.width_px),
        source=FrameBoundarySource.DIMENSION_CONSTRAINED,
        geometry_state=BoundaryGeometryState.RESOLVED,
        boundary_anchor=None,
        inference_provenance=candidate_resolution._common_width_dimension_provenance(
            frame_index,
            BoundarySide.TRAILING,
            anchor,
            common_width,
        ),
    )


def _inferred_boundary(
    position: float,
    label: str,
) -> ResolvedFrameBoundary:
    return ResolvedFrameBoundary(
        position=PixelInterval.exact(position),
        source=FrameBoundarySource.DIMENSION_CONSTRAINED,
        geometry_state=BoundaryGeometryState.RESOLVED,
        boundary_anchor=None,
        inference_provenance=MeasurementProvenance(
            MeasurementIdentity.FRAME_GEOMETRY,
            ObservationId(label),
            (MeasurementIdentity.FRAME_DIMENSIONS,),
            "synthetic dimension-constrained boundary",
        ),
    )


def _pattern_boundary(
    position: float,
    side: BoundarySide,
    label: str,
) -> ResolvedFrameBoundary:
    observation = path(BoundaryAxis.LONG, position, label)
    role_provenance = MeasurementProvenance(
        MeasurementIdentity.PHOTO_EDGES,
        ObservationId(f"{label}:pattern-role"),
        (
            observation.provenance.root_measurement,
            MeasurementIdentity.FRAME_WIDTH_PATTERN,
        ),
        "synthetic role assigned by repeated frame width",
        (observation.provenance.observation_id,),
    )
    return ResolvedFrameBoundary(
        position=observation.position,
        source=FrameBoundarySource.GRAY_PATH_OBSERVATION,
        geometry_state=BoundaryGeometryState.RESOLVED,
        boundary_anchor=BoundaryAnchor(
            observation=observation,
            physical_role=side,
            role_state=EvidenceState.SUPPORTED,
            role_authority=BoundaryRoleAuthority.MEASUREMENT_CORROBORATED,
            role_provenance=role_provenance,
        ),
        inference_provenance=None,
    )


class SequenceConstraintOverlapContractTest(unittest.TestCase):
    def _sequence(
        self,
        *,
        width_contributor_indexes: tuple[int, int],
    ) -> tuple[tuple[FrameSlot, ...], CommonFrameWidthResolution]:
        first_leading = _measured_boundary(
            0.0,
            BoundarySide.LEADING,
            "first-leading",
        )
        second = _slot(
            2,
            _measured_boundary(80.0, BoundarySide.LEADING, "second-leading"),
            _measured_boundary(180.0, BoundarySide.TRAILING, "second-trailing"),
        )
        third = _slot(
            3,
            _measured_boundary(220.0, BoundarySide.LEADING, "third-leading"),
            _measured_boundary(320.0, BoundarySide.TRAILING, "third-trailing"),
        )
        fourth = _slot(
            4,
            _measured_boundary(340.0, BoundarySide.LEADING, "fourth-leading"),
            _measured_boundary(440.0, BoundarySide.TRAILING, "fourth-trailing"),
        )
        measured = {2: second, 3: third, 4: fourth}
        common_width = _common_width(
            tuple(measured[index] for index in width_contributor_indexes)
        )
        first = _slot(
            1,
            first_leading,
            _dimension_trailing_boundary(1, first_leading, common_width),
        )
        return (first, second, third, fourth), common_width

    def test_target_independent_common_width_corroborates_overlap(self) -> None:
        slots, common_width = self._sequence(
            width_contributor_indexes=(3, 4),
        )

        spacings = sequence_result.final_inter_frame_spacings(
            slots,
            (),
            common_width,
        )

        self.assertEqual(
            spacings[0].basis,
            InterFrameSpacingBasis.CORROBORATED_OVERLAP,
        )
        self.assertTrue(spacings[0].supports_output_protection)

    def test_target_dependent_common_width_cannot_corroborate_overlap(self) -> None:
        slots, common_width = self._sequence(
            width_contributor_indexes=(2, 3),
        )

        spacings = sequence_result.final_inter_frame_spacings(
            slots,
            (),
            common_width,
        )

        self.assertEqual(
            spacings[0].basis,
            InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS,
        )
        self.assertFalse(spacings[0].supports_output_protection)

    def test_width_pattern_role_cannot_dominate_physical_alternative(self) -> None:
        first_leading = _inferred_boundary(0.0, "first-leading-inference")
        first_trailing = _measured_boundary(
            100.0,
            BoundarySide.TRAILING,
            "first-trailing",
        )
        second_leading = _measured_boundary(
            110.0,
            BoundarySide.LEADING,
            "second-leading",
        )
        second_trailing = _inferred_boundary(
            210.0,
            "second-trailing-inference",
        )
        third_leading = _inferred_boundary(
            220.0,
            "third-leading-inference",
        )
        third_trailing = _inferred_boundary(
            320.0,
            "third-trailing-inference",
        )
        subset_slots = (
            _slot(1, first_leading, first_trailing),
            _slot(2, second_leading, second_trailing),
            _slot(3, third_leading, third_trailing),
        )
        pattern_slots = (
            subset_slots[0],
            _slot(
                2,
                second_leading,
                _pattern_boundary(
                    210.0,
                    BoundarySide.TRAILING,
                    "second-trailing-pattern",
                ),
            ),
            _slot(
                3,
                _pattern_boundary(
                    220.0,
                    BoundarySide.LEADING,
                    "third-leading-pattern",
                ),
                third_trailing,
            ),
        )
        objectives = candidate_builds.SequenceBuildObjectives(
            uncorroborated_overlap_extent_px=0.0,
            unexplained_spacing_extent_px=10.0,
            supported_separator_count=1,
            internal_boundary_measurement_quality=2.0,
            dimension_residual=0.0,
            external_boundary_measurement_quality=0.0,
            boundary_uncertainty_ratio=0.0,
            inferred_boundary_count=2,
        )
        subset = type("SyntheticBuild", (), {})()
        subset.slots = subset_slots
        subset.objectives = objectives
        pattern = type("SyntheticBuild", (), {})()
        pattern.slots = pattern_slots
        pattern.objectives = objectives

        preferred = candidate_builds.physically_preferred_builds(
            (subset, pattern)
        )

        self.assertEqual(preferred, (subset, pattern))


if __name__ == "__main__":
    unittest.main()
