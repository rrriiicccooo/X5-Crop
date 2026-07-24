from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
import unittest

from tools.tests.support.frame_sequence import path
from x5crop.detection.physical import frame_sequence_consensus as sequence_consensus
from x5crop.detection.physical.model import (
    AssignmentConsensusOutcome,
    BoundaryAnchor,
    BoundaryGeometryState,
    BoundaryRoleAuthority,
    FrameBoundarySource,
    ResolvedFrameBoundary,
)
from x5crop.domain import (
    BoundaryAxis,
    BoundarySide,
    EvidenceState,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
)


class FrameSequenceConsensusContractTest(unittest.TestCase):
    def test_blank_placement_disagreement_counts_all_alternative_builds(
        self,
    ) -> None:
        preferred_builds = (
            SimpleNamespace(
                slots=(SimpleNamespace(index=1, sequence_inferred=True),),
            ),
            SimpleNamespace(
                slots=(SimpleNamespace(index=6, sequence_inferred=True),),
            ),
        )

        consensus = sequence_consensus.sequence_assignment_consensus(
            preferred_builds,
        )

        self.assertEqual(consensus.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(consensus.solution_count, 2)
        self.assertEqual(consensus.conflicting_frame_indexes, (1, 6))

    def test_same_inferred_slot_position_does_not_create_frame_disagreement(
        self,
    ) -> None:
        def boundary(start: float, end: float):
            return SimpleNamespace(position=PixelInterval(start, end))

        real_slot = SimpleNamespace(
            index=1,
            sequence_inferred=False,
            leading=boundary(0.0, 2.0),
            trailing=boundary(98.0, 100.0),
        )
        alternatives = (
            SimpleNamespace(
                slots=(
                    real_slot,
                    SimpleNamespace(
                        index=2,
                        sequence_inferred=True,
                        leading=boundary(110.0, 112.0),
                        trailing=boundary(208.0, 210.0),
                    ),
                ),
            ),
            SimpleNamespace(
                slots=(
                    real_slot,
                    SimpleNamespace(
                        index=2,
                        sequence_inferred=True,
                        leading=boundary(230.0, 232.0),
                        trailing=boundary(328.0, 330.0),
                    ),
                ),
            ),
        )

        consensus = sequence_consensus.sequence_assignment_consensus(alternatives)

        self.assertEqual(consensus.state, EvidenceState.SUPPORTED)
        self.assertEqual(consensus.conflicting_frame_indexes, ())

    def test_measured_and_inferred_slot_identity_is_assignment_disagreement(
        self,
    ) -> None:
        def boundary(position: float):
            return SimpleNamespace(position=PixelInterval.exact(position))

        def build(second_slot_inferred: bool):
            return SimpleNamespace(
                slots=(
                    SimpleNamespace(
                        index=1,
                        sequence_inferred=False,
                        leading=boundary(0.0),
                        trailing=boundary(100.0),
                    ),
                    SimpleNamespace(
                        index=2,
                        sequence_inferred=second_slot_inferred,
                        leading=boundary(110.0),
                        trailing=boundary(210.0),
                    ),
                ),
            )

        consensus = sequence_consensus.sequence_assignment_consensus(
            (build(False), build(True))
        )

        self.assertEqual(consensus.outcome, AssignmentConsensusOutcome.DISAGREED)
        self.assertEqual(consensus.conflicting_frame_indexes, (2,))

    def test_external_safety_uncertainty_is_not_internal_assignment_disagreement(
        self,
    ) -> None:
        def boundary(start: float, end: float | None = None):
            return SimpleNamespace(
                position=PixelInterval(
                    start,
                    start if end is None else end,
                ),
                source=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                independently_observed=True,
            )

        def build(
            leading: tuple[float, float],
            internal: tuple[float, float],
            trailing: tuple[float, float],
        ):
            return SimpleNamespace(
                slots=(
                    SimpleNamespace(
                        index=1,
                        sequence_inferred=False,
                        leading=boundary(*leading),
                        trailing=boundary(*internal),
                    ),
                    SimpleNamespace(
                        index=2,
                        sequence_inferred=False,
                        leading=boundary(110.0, 112.0),
                        trailing=boundary(*trailing),
                    ),
                )
            )

        endpoint_alternatives = (
            build((0.0, 2.0), (98.0, 100.0), (208.0, 210.0)),
            build((8.0, 10.0), (98.0, 100.0), (218.0, 220.0)),
        )
        internal_alternatives = (
            build((0.0, 2.0), (98.0, 100.0), (208.0, 210.0)),
            build((0.0, 2.0), (103.0, 105.0), (208.0, 210.0)),
        )

        endpoint_consensus = sequence_consensus.sequence_assignment_consensus(
            endpoint_alternatives,
        )
        internal_consensus = sequence_consensus.sequence_assignment_consensus(
            internal_alternatives,
        )

        self.assertEqual(endpoint_consensus.state, EvidenceState.SUPPORTED)
        self.assertEqual(endpoint_consensus.conflicting_frame_indexes, ())
        self.assertEqual(internal_consensus.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(internal_consensus.conflicting_frame_indexes, (1,))

        observations = tuple(
            path(BoundaryAxis.LONG, position, f"external_endpoint:{position}")
            for position in (2.0, 8.0)
        )
        boundaries = tuple(
            ResolvedFrameBoundary(
                position=observation.position,
                source=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                geometry_state=BoundaryGeometryState.RESOLVED,
                boundary_anchor=BoundaryAnchor(
                    observation=observation,
                    physical_role=BoundarySide.LEADING,
                    role_state=EvidenceState.SUPPORTED,
                    role_authority=BoundaryRoleAuthority.DIRECT_MEASUREMENT,
                    role_provenance=observation.provenance,
                ),
                inference_provenance=None,
            )
            for observation in observations
        )

        safe_boundary = sequence_consensus.external_safety_boundary(
            BoundarySide.LEADING,
            boundaries,
            PixelInterval(0.0, 20.0),
        )
        self.assertEqual(
            safe_boundary.source,
            FrameBoundarySource.EXTERNAL_SAFETY_ENVELOPE,
        )
        self.assertEqual(safe_boundary.position, PixelInterval(2.0, 8.0))
        self.assertEqual(safe_boundary.role_state, EvidenceState.UNAVAILABLE)
        self.assertTrue(safe_boundary.geometry_resolved)

    def test_external_safety_boundary_is_clamped_to_holder_safety(self) -> None:
        observations = tuple(
            path(BoundaryAxis.LONG, position, f"clamped_endpoint:{position}")
            for position in (198.0, 207.0)
        )
        boundaries = tuple(
            ResolvedFrameBoundary(
                position=observation.position,
                source=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                geometry_state=BoundaryGeometryState.RESOLVED,
                boundary_anchor=BoundaryAnchor(
                    observation=observation,
                    physical_role=BoundarySide.TRAILING,
                    role_state=EvidenceState.SUPPORTED,
                    role_authority=BoundaryRoleAuthority.DIRECT_MEASUREMENT,
                    role_provenance=observation.provenance,
                ),
                inference_provenance=None,
            )
            for observation in observations
        )

        safe_boundary = sequence_consensus.external_safety_boundary(
            BoundarySide.TRAILING,
            boundaries,
            PixelInterval(0.0, 200.0),
        )

        self.assertEqual(safe_boundary.position, PixelInterval(198.0, 200.0))

    def test_distinct_observations_with_one_shared_interval_form_consensus(
        self,
    ) -> None:
        def observed_boundary(
            position: PixelInterval,
            source: str,
            side: BoundarySide,
        ) -> ResolvedFrameBoundary:
            observation = path(BoundaryAxis.LONG, position.midpoint, source)
            observation = replace(
                observation,
                samples=(
                    replace(
                        observation.samples[0],
                        position=position,
                    ),
                ),
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
                    role_provenance=observation.provenance,
                ),
                inference_provenance=None,
            )

        fixed_leading = observed_boundary(
            PixelInterval.exact(0.0),
            "fixed_leading",
            BoundarySide.LEADING,
        )
        alternatives = tuple(
            SimpleNamespace(
                slots=(
                    SimpleNamespace(
                        index=1,
                        sequence_inferred=False,
                        leading=fixed_leading,
                        trailing=observed_boundary(
                            position,
                            source,
                            BoundarySide.TRAILING,
                        ),
                    ),
                ),
            )
            for position, source in (
                (PixelInterval(98.0, 106.0), "first_trailing_path"),
                (PixelInterval(102.0, 110.0), "second_trailing_path"),
            )
        )

        consensus = sequence_consensus.sequence_assignment_consensus(alternatives)

        self.assertEqual(
            consensus.outcome,
            AssignmentConsensusOutcome.AGREED,
        )
        self.assertEqual(consensus.conflicting_frame_indexes, ())

    def test_broad_uncertainty_cannot_bridge_disjoint_placements(self) -> None:
        fixed = SimpleNamespace(
            position=PixelInterval.exact(0.0),
            source=FrameBoundarySource.GRAY_PATH_OBSERVATION,
            independently_observed=True,
        )
        alternatives = tuple(
            SimpleNamespace(
                slots=(
                    SimpleNamespace(
                        index=1,
                        sequence_inferred=False,
                        leading=fixed,
                        trailing=SimpleNamespace(
                            position=position,
                            source=FrameBoundarySource.GRAY_PATH_OBSERVATION,
                            independently_observed=True,
                        ),
                    ),
                ),
            )
            for position in (
                PixelInterval(98.0, 100.0),
                PixelInterval(98.0, 110.0),
                PixelInterval(108.0, 110.0),
            )
        )

        consensus = sequence_consensus.sequence_assignment_consensus(alternatives)

        self.assertEqual(
            consensus.outcome,
            AssignmentConsensusOutcome.DISAGREED,
        )
        self.assertEqual(consensus.conflicting_frame_indexes, (1,))

    def test_dimension_only_alternatives_form_one_geometry_uncertainty(self) -> None:
        def boundary(position: PixelInterval, label: str) -> ResolvedFrameBoundary:
            return ResolvedFrameBoundary(
                position=position,
                source=FrameBoundarySource.DIMENSION_CONSTRAINED,
                geometry_state=BoundaryGeometryState.RESOLVED,
                boundary_anchor=None,
                inference_provenance=MeasurementProvenance(
                    MeasurementIdentity.FRAME_GEOMETRY,
                    ObservationId(label),
                    (MeasurementIdentity.FRAME_DIMENSIONS,),
                    "synthetic dimension-only boundary",
                ),
            )

        alternatives = tuple(
            SimpleNamespace(
                slots=(
                    SimpleNamespace(
                        index=1,
                        sequence_inferred=False,
                        leading=boundary(
                            PixelInterval.exact(0.0),
                            f"fixed_leading:{offset}",
                        ),
                        trailing=boundary(
                            PixelInterval(offset, offset + 10.0),
                            f"dimension_trailing:{offset}",
                        ),
                    ),
                ),
            )
            for offset in (90.0, 120.0)
        )

        consensus = sequence_consensus.sequence_assignment_consensus(alternatives)
        envelope = sequence_consensus.internal_geometry_uncertainty_boundary(
            BoundarySide.TRAILING,
            tuple(build.slots[0].trailing for build in alternatives),
        )

        self.assertEqual(consensus.state, EvidenceState.SUPPORTED)
        self.assertEqual(envelope.position, PixelInterval(90.0, 130.0))
        self.assertEqual(
            envelope.source,
            FrameBoundarySource.DIMENSION_CONSTRAINED,
        )
        self.assertFalse(envelope.independently_observed)


if __name__ == "__main__":
    unittest.main()
