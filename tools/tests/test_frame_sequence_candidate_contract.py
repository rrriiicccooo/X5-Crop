from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
import unittest

from tools.tests.frame_slot_solver_support import path
from tools.tests.physical_gate_support import candidate_fixture
from x5crop.detection.physical import frame_sequence_candidates as candidate_builds
from x5crop.detection.physical import model as physical_model
from x5crop.detection.physical.model import (
    BoundaryAnchor,
    BoundaryGeometryState,
    BoundaryRoleAuthority,
    FrameBoundarySource,
    FrameContentOccupancy,
    FrameSlot,
    ResolvedFrameBoundary,
)
from x5crop.domain import (
    BoundaryAxis,
    BoundarySide,
    EvidenceState,
    InterFrameSpacingBasis,
    InterFrameSpacingKind,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
)


class FrameSequenceCandidateContractTest(unittest.TestCase):
    def test_physical_pareto_prefers_stronger_physical_measurement_support(
        self,
    ) -> None:
        stronger_separator = SimpleNamespace(
            slots=(),
            objectives=candidate_builds.SequenceBuildObjectives(
                uncorroborated_overlap_extent_px=0.0,
                unexplained_spacing_extent_px=0.0,
                supported_separator_count=3,
                internal_boundary_measurement_quality=2.0,
                dimension_residual=0.1,
                external_boundary_measurement_quality=1.0,
                boundary_uncertainty_ratio=0.2,
            )
        )
        tighter_boundary = SimpleNamespace(
            slots=(),
            objectives=candidate_builds.SequenceBuildObjectives(
                uncorroborated_overlap_extent_px=0.0,
                unexplained_spacing_extent_px=0.0,
                supported_separator_count=2,
                internal_boundary_measurement_quality=2.0,
                dimension_residual=0.1,
                external_boundary_measurement_quality=1.0,
                boundary_uncertainty_ratio=0.1,
            )
        )
        dominated = SimpleNamespace(
            slots=(),
            objectives=candidate_builds.SequenceBuildObjectives(
                uncorroborated_overlap_extent_px=1.0,
                unexplained_spacing_extent_px=1.0,
                supported_separator_count=2,
                internal_boundary_measurement_quality=1.0,
                dimension_residual=0.2,
                external_boundary_measurement_quality=0.5,
                boundary_uncertainty_ratio=0.3,
            )
        )

        retained = candidate_builds.physically_preferred_builds(
            (stronger_separator, tighter_boundary, dominated)
        )

        self.assertEqual(
            {id(item) for item in retained},
            {id(stronger_separator)},
        )

    def test_strictly_larger_unexplained_spacing_is_dominated(self) -> None:
        edge = SimpleNamespace(position=PixelInterval.exact(0.0))
        slots = (SimpleNamespace(leading=edge, trailing=edge),)
        compact = SimpleNamespace(
            slots=slots,
            objectives=candidate_builds.SequenceBuildObjectives(
                uncorroborated_overlap_extent_px=0.0,
                unexplained_spacing_extent_px=10.0,
                supported_separator_count=1,
                internal_boundary_measurement_quality=1.0,
                dimension_residual=0.0,
                external_boundary_measurement_quality=1.0,
                boundary_uncertainty_ratio=0.0,
            )
        )
        fragmented = SimpleNamespace(
            slots=slots,
            objectives=candidate_builds.SequenceBuildObjectives(
                uncorroborated_overlap_extent_px=0.0,
                unexplained_spacing_extent_px=100.0,
                supported_separator_count=1,
                internal_boundary_measurement_quality=1.0,
                dimension_residual=0.0,
                external_boundary_measurement_quality=1.0,
                boundary_uncertainty_ratio=0.0,
            )
        )

        self.assertEqual(
            candidate_builds.physically_preferred_builds((fragmented, compact)),
            (compact,),
        )
        self.assertIs(
            candidate_builds.representative_build((fragmented, compact)),
            compact,
        )

    def test_strictly_larger_dimension_residual_is_dominated(
        self,
    ) -> None:
        def build(position: float, residual: float):
            edge = SimpleNamespace(position=PixelInterval.exact(position))
            return SimpleNamespace(
                slots=(SimpleNamespace(leading=edge, trailing=edge),),
                objectives=candidate_builds.SequenceBuildObjectives(
                    uncorroborated_overlap_extent_px=0.0,
                    unexplained_spacing_extent_px=0.0,
                    supported_separator_count=1,
                    internal_boundary_measurement_quality=2.0,
                    dimension_residual=residual,
                    external_boundary_measurement_quality=0.0,
                    boundary_uncertainty_ratio=0.0,
                    inferred_boundary_count=1,
                ),
            )

        lower_residual = build(100.0, 0.01)
        higher_residual = build(200.0, 0.02)

        self.assertEqual(
            candidate_builds.physically_preferred_builds((higher_residual, lower_residual)),
            (lower_residual,),
        )
        self.assertIs(
            candidate_builds.representative_build(
                (higher_residual, lower_residual)
            ),
            lower_residual,
        )

    def test_physical_residual_tradeoff_remains_a_geometry_alternative(
        self,
    ) -> None:
        edge = SimpleNamespace(position=PixelInterval.exact(0.0))

        def build(unexplained: float, dimension_residual: float):
            return SimpleNamespace(
                slots=(SimpleNamespace(leading=edge, trailing=edge),),
                objectives=candidate_builds.SequenceBuildObjectives(
                    uncorroborated_overlap_extent_px=0.0,
                    unexplained_spacing_extent_px=unexplained,
                    supported_separator_count=1,
                    internal_boundary_measurement_quality=1.0,
                    dimension_residual=dimension_residual,
                    external_boundary_measurement_quality=1.0,
                    boundary_uncertainty_ratio=0.0,
                ),
            )

        compact = build(10.0, 0.02)
        dimension_consistent = build(20.0, 0.01)

        self.assertEqual(
            candidate_builds.physically_preferred_builds((compact, dimension_consistent)),
            (compact, dimension_consistent),
        )

    def test_inferred_boundary_count_orders_without_erasing_alternative(
        self,
    ) -> None:
        def build(position: float, inferred_boundary_count: int):
            edge = SimpleNamespace(position=PixelInterval.exact(position))
            return SimpleNamespace(
                slots=(SimpleNamespace(leading=edge, trailing=edge),),
                objectives=candidate_builds.SequenceBuildObjectives(
                    uncorroborated_overlap_extent_px=0.0,
                    unexplained_spacing_extent_px=0.0,
                    supported_separator_count=1,
                    internal_boundary_measurement_quality=2.0,
                    dimension_residual=0.01,
                    external_boundary_measurement_quality=0.0,
                    boundary_uncertainty_ratio=0.0,
                    inferred_boundary_count=inferred_boundary_count,
                ),
            )

        more_measured = build(100.0, 1)
        more_inferred = build(200.0, 2)

        self.assertEqual(
            candidate_builds.physically_preferred_builds((more_inferred, more_measured)),
            (more_inferred, more_measured),
        )
        self.assertIs(
            candidate_builds.representative_build((more_inferred, more_measured)),
            more_measured,
        )

    def test_boundary_measurement_count_does_not_erase_geometry_alternative(
        self,
    ) -> None:
        def build(position: float, internal_quality: float):
            edge = SimpleNamespace(position=PixelInterval.exact(position))
            return SimpleNamespace(
                slots=(SimpleNamespace(leading=edge, trailing=edge),),
                objectives=candidate_builds.SequenceBuildObjectives(
                    uncorroborated_overlap_extent_px=0.0,
                    unexplained_spacing_extent_px=0.0,
                    supported_separator_count=1,
                    internal_boundary_measurement_quality=internal_quality,
                    dimension_residual=0.01,
                    external_boundary_measurement_quality=0.0,
                    boundary_uncertainty_ratio=0.0,
                    inferred_boundary_count=1,
                ),
            )

        more_roles = build(100.0, 3.0)
        fewer_roles = build(200.0, 2.0)

        self.assertEqual(
            candidate_builds.physically_preferred_builds((fewer_roles, more_roles)),
            (fewer_roles, more_roles),
        )
        self.assertIs(
            candidate_builds.representative_build((fewer_roles, more_roles)),
            more_roles,
        )

    def test_same_topology_with_strict_boundary_role_superset_dominates(
        self,
    ) -> None:
        def boundary(
            position: float,
            observation_id: str | None,
        ) -> SimpleNamespace:
            return SimpleNamespace(
                position=PixelInterval.exact(position),
                independently_observed=observation_id is not None,
                role_provenance=(
                    None
                    if observation_id is None
                    else SimpleNamespace(
                        root_measurement=MeasurementIdentity.PHOTO_EDGES,
                        dependencies=(),
                    )
                ),
                measurement_provenance=(
                    None
                    if observation_id is None
                    else SimpleNamespace(
                        observation_id=ObservationId(observation_id)
                    )
                ),
            )

        def build(*, second_anchor: bool) -> SimpleNamespace:
            first_anchor = "first_internal_anchor"
            second = "second_internal_anchor" if second_anchor else None
            return SimpleNamespace(
                slots=(
                    SimpleNamespace(
                        index=1,
                        sequence_inferred=False,
                        leading=boundary(0.0, None),
                        trailing=boundary(100.0, first_anchor),
                    ),
                    SimpleNamespace(
                        index=2,
                        sequence_inferred=False,
                        leading=boundary(110.0, first_anchor),
                        trailing=boundary(210.0, second),
                    ),
                    SimpleNamespace(
                        index=3,
                        sequence_inferred=False,
                        leading=boundary(220.0, second),
                        trailing=boundary(320.0, None),
                    ),
                ),
                objectives=candidate_builds.SequenceBuildObjectives(
                    uncorroborated_overlap_extent_px=0.0,
                    unexplained_spacing_extent_px=0.0,
                    supported_separator_count=1,
                    internal_boundary_measurement_quality=2.0,
                    dimension_residual=0.0,
                    external_boundary_measurement_quality=0.0,
                    boundary_uncertainty_ratio=0.0,
                ),
            )

        subset = build(second_anchor=False)
        superset = build(second_anchor=True)

        self.assertEqual(
            candidate_builds.physically_preferred_builds((subset, superset)),
            (superset,),
        )

    def test_independent_separator_sequence_precedes_small_unexplained_spacing(
        self,
    ) -> None:
        def build(unexplained: float, separator_count: int):
            edge = SimpleNamespace(position=PixelInterval.exact(0.0))
            return SimpleNamespace(
                slots=(SimpleNamespace(leading=edge, trailing=edge),),
                objectives=candidate_builds.SequenceBuildObjectives(
                    uncorroborated_overlap_extent_px=0.0,
                    unexplained_spacing_extent_px=unexplained,
                    supported_separator_count=separator_count,
                    internal_boundary_measurement_quality=float(separator_count),
                    dimension_residual=0.0,
                    external_boundary_measurement_quality=1.0,
                    boundary_uncertainty_ratio=0.0,
                ),
            )

        model_fitted = build(0.0, 2)
        measured_sequence = build(141.0, 4)

        self.assertEqual(
            candidate_builds.physically_preferred_builds((model_fitted, measured_sequence)),
            (measured_sequence,),
        )
        self.assertIs(
            candidate_builds.representative_build(
                (model_fitted, measured_sequence)
            ),
            measured_sequence,
        )

    def test_search_hint_residual_does_not_prevent_physical_dominance(self) -> None:
        actual_frame_scale = candidate_builds.SequenceBuildObjectives(
            uncorroborated_overlap_extent_px=0.0,
            unexplained_spacing_extent_px=0.0,
            supported_separator_count=0,
            internal_boundary_measurement_quality=0.0,
            dimension_residual=0.0,
            external_boundary_measurement_quality=0.0,
            boundary_uncertainty_ratio=0.006,
            frame_width_hint_residual=0.0,
        )
        whole_holder_span = candidate_builds.SequenceBuildObjectives(
            uncorroborated_overlap_extent_px=0.0,
            unexplained_spacing_extent_px=0.0,
            supported_separator_count=0,
            internal_boundary_measurement_quality=0.0,
            dimension_residual=0.0,
            external_boundary_measurement_quality=0.0,
            boundary_uncertainty_ratio=0.004,
            frame_width_hint_residual=11.0,
        )

        self.assertTrue(whole_holder_span.dominates(actual_frame_scale))
        self.assertFalse(actual_frame_scale.dominates(whole_holder_span))

    def test_representative_uses_physical_objectives_before_coordinates(self) -> None:
        def build(position: float, separator_count: int):
            edge = SimpleNamespace(position=PixelInterval.exact(position))
            return SimpleNamespace(
                slots=(SimpleNamespace(leading=edge, trailing=edge),),
                objectives=candidate_builds.SequenceBuildObjectives(
                    uncorroborated_overlap_extent_px=0.0,
                    unexplained_spacing_extent_px=10.0,
                    supported_separator_count=separator_count,
                    internal_boundary_measurement_quality=float(separator_count),
                    dimension_residual=0.0,
                    external_boundary_measurement_quality=1.0,
                    boundary_uncertainty_ratio=0.0,
                ),
            )

        weak_leftmost = build(0.0, 1)
        supported_sequence = build(100.0, 5)

        self.assertIs(
            candidate_builds.representative_build(
                (weak_leftmost, supported_sequence)
            ),
            supported_sequence,
        )

    def test_uncorroborated_overlap_is_not_bought_with_extra_separator_evidence(
        self,
    ) -> None:
        def build(overlap: float, unexplained: float, separator_count: int):
            edge = SimpleNamespace(position=PixelInterval.exact(0.0))
            return SimpleNamespace(
                slots=(SimpleNamespace(leading=edge, trailing=edge),),
                objectives=candidate_builds.SequenceBuildObjectives(
                    uncorroborated_overlap_extent_px=overlap,
                    unexplained_spacing_extent_px=unexplained,
                    supported_separator_count=separator_count,
                    internal_boundary_measurement_quality=1.0,
                    dimension_residual=0.0,
                    external_boundary_measurement_quality=1.0,
                    boundary_uncertainty_ratio=0.0,
                ),
            )

        zero_overlap_large_gap = build(0.0, 100.0, 1)
        overlapping_extra_separator = build(10.0, 20.0, 2)

        self.assertIs(
            candidate_builds.representative_build(
                (zero_overlap_large_gap, overlapping_extra_separator)
            ),
            zero_overlap_large_gap,
        )
        self.assertEqual(
            candidate_builds.physically_preferred_builds(
                (zero_overlap_large_gap, overlapping_extra_separator)
            ),
            (zero_overlap_large_gap,),
        )

    def test_sequence_conservation_precedes_extra_separator_support(self) -> None:
        def build(unresolved: float, separator_count: int):
            edge = SimpleNamespace(position=PixelInterval.exact(0.0))
            return SimpleNamespace(
                slots=(SimpleNamespace(leading=edge, trailing=edge),),
                objectives=candidate_builds.SequenceBuildObjectives(
                    uncorroborated_overlap_extent_px=unresolved,
                    unexplained_spacing_extent_px=0.0,
                    supported_separator_count=separator_count,
                    internal_boundary_measurement_quality=float(separator_count),
                    dimension_residual=0.0,
                    external_boundary_measurement_quality=1.0,
                    boundary_uncertainty_ratio=0.0,
                ),
            )

        conserved = build(20.0, 4)
        extra_separator_with_broken_conservation = build(200.0, 5)

        self.assertIs(
            candidate_builds.representative_build(
                (extra_separator_with_broken_conservation, conserved)
            ),
            conserved,
        )
        self.assertEqual(
            candidate_builds.physically_preferred_builds(
                (extra_separator_with_broken_conservation, conserved)
            ),
            (conserved,),
        )


    def test_spacing_interval_crossing_zero_is_uncertainty_not_physical_residual(
        self,
    ) -> None:
        spacing = SimpleNamespace(
            basis=InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS,
            signed_width_px=PixelInterval(-100.0, 5.0),
        )

        self.assertEqual(candidate_builds.uncorroborated_overlap_extent((spacing,)), 0.0)
        self.assertEqual(candidate_builds.unexplained_spacing_extent((spacing,)), 0.0)

    def test_spacing_residuals_only_count_unavoidable_overlap_or_gap(self) -> None:
        overlap = SimpleNamespace(
            basis=InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS,
            signed_width_px=PixelInterval(-100.0, -20.0),
        )
        gap = SimpleNamespace(
            basis=InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS,
            signed_width_px=PixelInterval(5.0, 40.0),
        )

        self.assertEqual(candidate_builds.uncorroborated_overlap_extent((overlap, gap)), 20.0)
        self.assertEqual(candidate_builds.unexplained_spacing_extent((overlap, gap)), 5.0)

    def test_dimension_replacement_removes_superseded_path_assignment(
        self,
    ) -> None:
        geometry_model = candidate_fixture().geometry
        replaced_boundary = ResolvedFrameBoundary(
            position=geometry_model.frame_slots[0].leading.position,
            source=FrameBoundarySource.DIMENSION_CONSTRAINED,
            geometry_state=BoundaryGeometryState.RESOLVED,
            boundary_anchor=None,
            inference_provenance=MeasurementProvenance(
                MeasurementIdentity.FRAME_GEOMETRY,
                ObservationId("dimension-replaced-leading-edge"),
                (MeasurementIdentity.FRAME_DIMENSIONS,),
                "dimension replacement",
            ),
        )
        slots = (
            replace(
                geometry_model.frame_slots[0],
                leading=replaced_boundary,
            ),
            *geometry_model.frame_slots[1:],
        )

        assignments = candidate_builds.long_axis_assignments_for_slots(
            geometry_model.long_axis_assignments,
            slots,
        )

        self.assertNotIn(
            (1, BoundarySide.LEADING),
            {(item.frame_index, item.side) for item in assignments},
        )

    def test_distinct_supported_photo_edges_measure_their_distance(
        self,
    ) -> None:
        def boundary(
            position: float,
            side: BoundarySide,
            label: str,
        ) -> ResolvedFrameBoundary:
            observation = path(BoundaryAxis.LONG, position, label)
            role_provenance = MeasurementProvenance(
                MeasurementIdentity.PHOTO_EDGES,
                ObservationId(f"{label}:role"),
                (observation.provenance.root_measurement,),
                "synthetic independently supported photo-edge role",
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

        spacing = candidate_builds.spacing_from_frame_edges(
            1,
            boundary(100.0, BoundarySide.TRAILING, "unrelated-trailing"),
            boundary(5_000.0, BoundarySide.LEADING, "unrelated-leading"),
        )

        self.assertEqual(
            spacing.basis,
            InterFrameSpacingBasis.OBSERVED,
        )
        self.assertEqual(spacing.state, EvidenceState.SUPPORTED)
        self.assertEqual(
            spacing.provenance.root_measurement,
            MeasurementIdentity.PHOTO_EDGES,
        )

    def test_distinct_supported_photo_edges_measure_uncertain_spacing(self) -> None:
        def boundary(
            interval: PixelInterval,
            side: BoundarySide,
            label: str,
        ) -> ResolvedFrameBoundary:
            observation = path(BoundaryAxis.LONG, interval.midpoint, label)
            observation = replace(
                observation,
                samples=tuple(
                    replace(sample, position=interval)
                    for sample in observation.samples
                ),
            )
            role_provenance = MeasurementProvenance(
                MeasurementIdentity.PHOTO_EDGES,
                ObservationId(f"{label}:role"),
                (observation.provenance.root_measurement,),
                "synthetic independently supported photo-edge role",
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

        spacing = candidate_builds.spacing_from_frame_edges(
            1,
            boundary(
                PixelInterval(100.0, 105.0),
                BoundarySide.TRAILING,
                "measured-trailing",
            ),
            boundary(
                PixelInterval(99.0, 110.0),
                BoundarySide.LEADING,
                "measured-leading",
            ),
        )

        self.assertEqual(spacing.basis, InterFrameSpacingBasis.OBSERVED)
        self.assertEqual(spacing.kind, InterFrameSpacingKind.UNRESOLVED)
        self.assertEqual(spacing.state, EvidenceState.UNAVAILABLE)
        self.assertFalse(spacing.supports_output_protection)

    def test_separator_spacing_identity_includes_candidate_measurement_authority(
        self,
    ) -> None:
        geometry = candidate_fixture().geometry
        trailing = geometry.frame_slots[0].trailing
        leading = geometry.frame_slots[1].leading

        observed = candidate_builds.spacing_from_frame_edges(
            1,
            trailing,
            leading,
            separator_observation_supported=True,
        )
        hypothetical = candidate_builds.spacing_from_frame_edges(
            1,
            trailing,
            leading,
            separator_observation_supported=False,
        )

        self.assertEqual(observed.basis, InterFrameSpacingBasis.OBSERVED)
        self.assertEqual(
            hypothetical.basis,
            InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS,
        )
        self.assertNotEqual(
            observed.provenance.observation_id,
            hypothetical.provenance.observation_id,
        )

    def test_repeated_width_role_does_not_measure_inter_frame_overlap(
        self,
    ) -> None:
        def boundary(
            position: float,
            side: BoundarySide,
            label: str,
        ) -> ResolvedFrameBoundary:
            observation = path(BoundaryAxis.LONG, position, label)
            role_provenance = MeasurementProvenance(
                MeasurementIdentity.PHOTO_EDGES,
                ObservationId(f"{label}:repeated-width-role"),
                (
                    observation.provenance.root_measurement,
                    MeasurementIdentity.FRAME_WIDTH_PATTERN,
                ),
                "synthetic role corroborated by repeated frame width",
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
                    role_authority=(
                        BoundaryRoleAuthority.MEASUREMENT_CORROBORATED
                    ),
                    role_provenance=role_provenance,
                ),
                inference_provenance=None,
            )

        spacing = candidate_builds.spacing_from_frame_edges(
            1,
            boundary(200.0, BoundarySide.TRAILING, "pattern-trailing"),
            boundary(100.0, BoundarySide.LEADING, "pattern-leading"),
        )

        self.assertEqual(
            spacing.basis,
            InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS,
        )
        self.assertEqual(spacing.state, EvidenceState.UNAVAILABLE)
        self.assertFalse(spacing.supports_output_protection)

    def test_shared_supported_photo_edge_is_exact_measured_contact(self) -> None:
        observation = path(BoundaryAxis.LONG, 100.0, "shared-contact")
        uncertain_position = PixelInterval(90.0, 110.0)
        observation = replace(
            observation,
            samples=tuple(
                replace(sample, position=uncertain_position)
                for sample in observation.samples
            ),
        )
        role_provenance = MeasurementProvenance(
            MeasurementIdentity.PHOTO_EDGES,
            ObservationId("shared-contact:role"),
            (observation.provenance.root_measurement,),
            "synthetic independently supported shared photo edge",
            (observation.provenance.observation_id,),
        )

        def boundary(side: BoundarySide) -> ResolvedFrameBoundary:
            boundary_observation = (
                observation
                if side == BoundarySide.TRAILING
                else replace(observation)
            )
            return ResolvedFrameBoundary(
                position=boundary_observation.position,
                source=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                geometry_state=BoundaryGeometryState.RESOLVED,
                boundary_anchor=BoundaryAnchor(
                    observation=boundary_observation,
                    physical_role=side,
                    role_state=EvidenceState.SUPPORTED,
                    role_authority=BoundaryRoleAuthority.DIRECT_MEASUREMENT,
                    role_provenance=role_provenance,
                ),
                inference_provenance=None,
            )

        spacing = candidate_builds.spacing_from_frame_edges(
            1,
            boundary(BoundarySide.TRAILING),
            boundary(BoundarySide.LEADING),
        )

        self.assertEqual(spacing.basis, InterFrameSpacingBasis.OBSERVED)
        self.assertEqual(spacing.signed_width_px, PixelInterval.exact(0.0))
        self.assertEqual(spacing.kind, InterFrameSpacingKind.CONTACT)
        self.assertEqual(spacing.state, EvidenceState.SUPPORTED)
        self.assertFalse(spacing.supports_output_protection)

        def inferred_boundary(position: float) -> ResolvedFrameBoundary:
            return ResolvedFrameBoundary(
                position=PixelInterval.exact(position),
                source=FrameBoundarySource.DIMENSION_CONSTRAINED,
                geometry_state=BoundaryGeometryState.RESOLVED,
                boundary_anchor=None,
                inference_provenance=MeasurementProvenance(
                    MeasurementIdentity.FRAME_GEOMETRY,
                    ObservationId(f"contact-endpoint:{position}"),
                    (),
                    "synthetic contact endpoint",
                ),
            )

        left = FrameSlot(
            1,
            PixelInterval(0.0, 110.0),
            inferred_boundary(0.0),
            boundary(BoundarySide.TRAILING),
            FrameContentOccupancy.UNAVAILABLE,
            None,
        )
        right = FrameSlot(
            2,
            PixelInterval(90.0, 200.0),
            boundary(BoundarySide.LEADING),
            inferred_boundary(200.0),
            FrameContentOccupancy.UNAVAILABLE,
            None,
        )
        self.assertTrue(
            physical_model._spacing_matches_frame_slots(spacing, left, right)
        )


if __name__ == "__main__":
    unittest.main()
