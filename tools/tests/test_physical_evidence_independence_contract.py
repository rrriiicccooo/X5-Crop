from __future__ import annotations

import ast
from dataclasses import fields, replace
from pathlib import Path
from types import SimpleNamespace
import unittest

from tools.tests.support.physical_gates import (
    _candidate_geometry,
    candidate_evidence_fixture,
    candidate_fixture,
)
from x5crop.detection.candidate.assessment.evidence_independence import (
    evidence_independence_evidence,
)
from x5crop.detection.candidate.model import sequence_proof_paths_for_geometry
from x5crop.detection.physical.model import (
    BoundaryAnchor,
    BoundaryRoleAuthority,
    CommonFrameWidthResolution,
    FrameSequenceSolution,
    GeometryIdentityError,
    FrameEdgeAssignment,
    FrameBoundarySource,
    FrameWidthMeasurementConstraint,
)
from x5crop.domain import (
    BoundarySide,
    EvidenceState,
    InterFrameSpacing,
    InterFrameSpacingBasis,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _measured_internal_edge_geometry(
    *,
    left_trailing_position: float | PixelInterval = 150.0,
    right_leading_position: float | PixelInterval = 160.0,
) -> FrameSequenceSolution:
    geometry = _candidate_geometry(boundary_proof_supported=False)
    template = geometry.long_axis_assignments[0].observation
    left_provenance = MeasurementProvenance(
        MeasurementIdentity.PHOTO_EDGES,
        ObservationId("measured_internal_trailing_edge"),
        (MeasurementIdentity.GRAY_WORK,),
        "measured internal trailing frame edge",
    )
    right_provenance = MeasurementProvenance(
        MeasurementIdentity.PHOTO_EDGES,
        ObservationId("measured_internal_leading_edge"),
        (MeasurementIdentity.GRAY_WORK,),
        "measured internal leading frame edge",
    )

    def measured_boundary(boundary, path, side, provenance):
        return replace(
            boundary,
            source=FrameBoundarySource.GRAY_PATH_OBSERVATION,
            boundary_anchor=BoundaryAnchor(
                path,
                side,
                EvidenceState.SUPPORTED,
                BoundaryRoleAuthority.DIRECT_MEASUREMENT,
                provenance,
            ),
            inference_provenance=None,
        )

    def measured_path(boundary, provenance):
        return replace(
            template,
            samples=tuple(
                replace(sample, position=boundary.position)
                for sample in template.samples
            ),
            lower_appearance=replace(
                template.lower_appearance,
                provenance=provenance,
            ),
            upper_appearance=replace(
                template.upper_appearance,
                provenance=provenance,
            ),
            provenance=provenance,
        )

    left_interval = (
        left_trailing_position
        if isinstance(left_trailing_position, PixelInterval)
        else PixelInterval.exact(left_trailing_position)
    )
    right_interval = (
        right_leading_position
        if isinstance(right_leading_position, PixelInterval)
        else PixelInterval.exact(right_leading_position)
    )
    left_template = replace(
        geometry.frame_slots[0].trailing,
        position=left_interval,
    )
    right_template = replace(
        geometry.frame_slots[1].leading,
        position=right_interval,
    )
    left_path = measured_path(left_template, left_provenance)
    right_path = measured_path(right_template, right_provenance)
    left = measured_boundary(
        left_template,
        left_path,
        BoundarySide.TRAILING,
        left_provenance,
    )
    right = measured_boundary(
        right_template,
        right_path,
        BoundarySide.LEADING,
        right_provenance,
    )
    slots = (
        replace(geometry.frame_slots[0], trailing=left),
        replace(geometry.frame_slots[1], leading=right),
    )
    constraints = tuple(
        FrameWidthMeasurementConstraint(
            slot.index,
            slot.leading,
            slot.trailing,
        )
        for slot in slots
    )
    common_width = PixelInterval.common_intersection(
        tuple(constraint.width_px for constraint in constraints)
    )
    assert common_width is not None
    return replace(
        geometry,
        frame_slots=slots,
        inter_frame_spacings=(
            InterFrameSpacing(
                geometry.inter_frame_spacings[0].boundary,
                right.position.minus(left.position),
                geometry.inter_frame_spacings[0].provenance,
                InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS,
            ),
        ),
        common_frame_width=CommonFrameWidthResolution(
            common_width,
            constraints,
            None,
            EvidenceState.SUPPORTED,
            MeasurementProvenance(
                MeasurementIdentity.FRAME_DIMENSIONS,
                ObservationId("measured_internal_common_width"),
                (MeasurementIdentity.PHOTO_EDGES,),
                "common width from measured internal frame edges",
            ),
        ),
        long_axis_assignments=(
            *geometry.long_axis_assignments,
            FrameEdgeAssignment(
                1,
                BoundarySide.TRAILING,
                left_path,
                left,
            ),
            FrameEdgeAssignment(
                2,
                BoundarySide.LEADING,
                right_path,
                right,
            ),
        ),
        raw_boundary_paths=(
            *geometry.raw_boundary_paths,
            left_path,
            right_path,
        ),
    )


class PhysicalEvidenceIndependenceContractTest(unittest.TestCase):
    def test_sequence_provenance_is_derived_from_geometry(self) -> None:
        provenance_field = next(
            item
            for item in fields(FrameSequenceSolution)
            if item.name == "sequence_provenance"
        )
        geometry = candidate_fixture().geometry

        self.assertFalse(provenance_field.init)
        self.assertEqual(
            geometry.sequence_provenance.root_measurement,
            MeasurementIdentity.FRAME_GEOMETRY,
        )
        self.assertIn(
            MeasurementIdentity.SEPARATOR_PROFILE,
            geometry.sequence_provenance.dependencies,
        )

    def test_measured_frame_edge_requires_its_assignment(self) -> None:
        geometry = candidate_fixture().geometry
        with self.assertRaises(GeometryIdentityError):
            replace(
                geometry,
                long_axis_assignments=geometry.long_axis_assignments[:-1],
            )

    def test_measurement_authority_uses_typed_identities(self) -> None:
        offenders: list[str] = []
        for path in (PROJECT_ROOT / "x5crop/detection").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Compare):
                    continue
                text = ast.unparse(node)
                if "root_measurement" not in text:
                    continue
                if any(
                    isinstance(child, ast.Constant)
                    and isinstance(child.value, str)
                    for comparator in node.comparators
                    for child in ast.walk(comparator)
                ):
                    offenders.append(
                        f"{path.relative_to(PROJECT_ROOT).as_posix()}:{node.lineno}"
                    )
        self.assertEqual(offenders, [])

    def test_geometry_dependent_boundary_role_is_rejected(self) -> None:
        geometry = candidate_fixture().geometry
        original = geometry.separator_assignments[0]
        provenance = replace(
            original.observation.provenance,
            dependencies=(MeasurementIdentity.FRAME_GEOMETRY,),
        )
        observation = replace(
            original.observation,
            appearance=replace(
                original.observation.appearance,
                provenance=provenance,
            ),
            provenance=provenance,
        )
        with self.assertRaises(ValueError):
            BoundaryAnchor(
                observation,
                BoundarySide.TRAILING,
                EvidenceState.SUPPORTED,
                BoundaryRoleAuthority.DIRECT_MEASUREMENT,
                provenance,
            )

    def test_independent_separator_measurement_can_support_geometry(self) -> None:
        geometry = candidate_fixture().geometry
        evidence = evidence_independence_evidence(geometry)

        self.assertEqual(evidence.state, EvidenceState.SUPPORTED)
        self.assertIn(
            MeasurementIdentity.SEPARATOR_PROFILE,
            evidence.supporting_measurement_roots,
        )

    def test_dimension_prior_is_not_independent_measurement_evidence(self) -> None:
        evidence = evidence_independence_evidence(candidate_fixture().geometry)
        self.assertNotIn(
            MeasurementIdentity.PHYSICAL_FRAME_ASPECT,
            evidence.supporting_measurement_roots,
        )
        self.assertNotIn(
            MeasurementIdentity.FORMAT_PHYSICAL_SPEC,
            evidence.supporting_measurement_roots,
        )

    def test_repeated_width_roles_are_not_independent_geometry_support(self) -> None:
        raw_measurement = MeasurementProvenance(
            MeasurementIdentity.BOUNDARY_PATHS,
            ObservationId("repeated_width_independence_raw_path"),
            (MeasurementIdentity.GRAY_WORK,),
            "raw gray boundary path",
        )
        repeated_width_role = MeasurementProvenance(
            MeasurementIdentity.PHOTO_EDGES,
            ObservationId("repeated_width_independence_role"),
            (
                MeasurementIdentity.BOUNDARY_PATHS,
                MeasurementIdentity.FRAME_WIDTH_PATTERN,
            ),
            "photo-edge role assigned by repeated-width geometry",
        )
        geometry = SimpleNamespace(
            long_axis_assignments=(
                SimpleNamespace(
                    observation=SimpleNamespace(provenance=raw_measurement),
                    resolution=SimpleNamespace(
                        independently_observed=True,
                        role_provenance=repeated_width_role,
                    ),
                ),
            ),
            separator_assignments=(),
            sequence_provenance=SimpleNamespace(
                root_measurement=MeasurementIdentity.FRAME_GEOMETRY,
            ),
        )

        evidence = evidence_independence_evidence(geometry)

        self.assertEqual(evidence.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(evidence.supporting_measurement_roots, ())

    def test_measured_internal_frame_edges_support_dimension_sequence(self) -> None:
        geometry = _measured_internal_edge_geometry()
        independence = evidence_independence_evidence(geometry)
        evidence = candidate_evidence_fixture(geometry=geometry)
        paths = sequence_proof_paths_for_geometry(geometry, evidence)
        dimension_path = next(
            path for path in paths if path.code == "dimension_sequence_led"
        )

        self.assertEqual(independence.state, EvidenceState.SUPPORTED)
        self.assertIn(
            MeasurementIdentity.PHOTO_EDGES,
            independence.supporting_measurement_roots,
        )
        self.assertEqual(dimension_path.state, EvidenceState.SUPPORTED)
        self.assertIn(
            "independent_internal_boundary_anchor_coverage",
            dimension_path.supporting_evidence,
        )

    def test_dimension_derived_roles_cannot_complete_their_own_proof(self) -> None:
        direct_role = MeasurementProvenance(
            MeasurementIdentity.PHOTO_EDGES,
            ObservationId("direct_internal_photo_edge"),
            (MeasurementIdentity.GRAY_WORK,),
            "direct internal photo edge",
        )
        dimension_role = MeasurementProvenance(
            MeasurementIdentity.PHOTO_EDGES,
            ObservationId("dimension_corroborated_outer_photo_edge"),
            (
                MeasurementIdentity.GRAY_WORK,
                MeasurementIdentity.FRAME_DIMENSIONS,
            ),
            "photo edge role corroborated by frame dimensions",
        )
        geometry = SimpleNamespace(
            count=2,
            strip_mode="full",
            shared_short_axis=SimpleNamespace(supports_safe_crop=True),
            frame_slots=(
                SimpleNamespace(
                    leading=SimpleNamespace(
                        independently_observed=True,
                        role_provenance=dimension_role,
                    ),
                    trailing=SimpleNamespace(
                        independently_observed=True,
                        role_provenance=direct_role,
                    ),
                ),
                SimpleNamespace(
                    leading=SimpleNamespace(
                        independently_observed=True,
                        role_provenance=direct_role,
                    ),
                    trailing=SimpleNamespace(
                        independently_observed=True,
                        role_provenance=dimension_role,
                    ),
                ),
            ),
            inter_frame_spacings=(),
            common_frame_width=SimpleNamespace(
                state=EvidenceState.UNAVAILABLE,
                physical_scale_constraint=None,
            ),
        )
        evidence = SimpleNamespace(
            frame_slot_topology=SimpleNamespace(state=EvidenceState.SUPPORTED),
            independence=SimpleNamespace(state=EvidenceState.SUPPORTED),
            separator_sequence=SimpleNamespace(
                state=EvidenceState.UNAVAILABLE,
                hard_count=1,
            ),
            frame_dimensions=SimpleNamespace(state=EvidenceState.SUPPORTED),
            content_preservation_state=EvidenceState.SUPPORTED,
            internal_frame_boundary_preservation=SimpleNamespace(observations=()),
            partial_edge_safety=SimpleNamespace(state=EvidenceState.UNAVAILABLE),
            holder_occupancy=SimpleNamespace(occupancy_state="unavailable"),
        )

        dimension_path = next(
            path
            for path in sequence_proof_paths_for_geometry(geometry, evidence)
            if path.code == "dimension_sequence_led"
        )

        self.assertEqual(dimension_path.state, EvidenceState.UNAVAILABLE)

    def test_repeated_width_roles_cannot_prove_single_frame_boundaries(self) -> None:
        repeated_width_role = MeasurementProvenance(
            MeasurementIdentity.PHOTO_EDGES,
            ObservationId("single_frame_repeated_width_role"),
            (
                MeasurementIdentity.GRAY_WORK,
                MeasurementIdentity.FRAME_WIDTH_PATTERN,
            ),
            "photo-edge role assigned by repeated-width geometry",
        )
        boundary = SimpleNamespace(
            independently_observed=True,
            role_provenance=repeated_width_role,
        )
        geometry = SimpleNamespace(
            count=1,
            strip_mode="full",
            shared_short_axis=SimpleNamespace(supports_safe_crop=True),
            frame_slots=(
                SimpleNamespace(leading=boundary, trailing=boundary),
            ),
            inter_frame_spacings=(),
            common_frame_width=SimpleNamespace(
                state=EvidenceState.UNAVAILABLE,
                physical_scale_constraint=None,
            ),
        )
        evidence = SimpleNamespace(
            frame_slot_topology=SimpleNamespace(state=EvidenceState.SUPPORTED),
            independence=SimpleNamespace(state=EvidenceState.SUPPORTED),
            separator_sequence=SimpleNamespace(
                state=EvidenceState.NOT_APPLICABLE,
                hard_count=0,
            ),
            frame_dimensions=SimpleNamespace(state=EvidenceState.UNAVAILABLE),
            content_preservation_state=EvidenceState.SUPPORTED,
            internal_frame_boundary_preservation=SimpleNamespace(observations=()),
            partial_edge_safety=SimpleNamespace(state=EvidenceState.NOT_APPLICABLE),
            holder_occupancy=SimpleNamespace(occupancy_state="unavailable"),
        )

        dimension_path = next(
            path
            for path in sequence_proof_paths_for_geometry(geometry, evidence)
            if path.code == "dimension_sequence_led"
        )

        self.assertEqual(dimension_path.state, EvidenceState.UNAVAILABLE)

    def test_independent_scale_and_internal_anchor_support_dimension_sequence(
        self,
    ) -> None:
        direct_role = MeasurementProvenance(
            MeasurementIdentity.PHOTO_EDGES,
            ObservationId("scale_route_direct_internal_edge"),
            (MeasurementIdentity.GRAY_WORK,),
            "direct internal photo edge",
        )
        dimension_role = MeasurementProvenance(
            MeasurementIdentity.PHOTO_EDGES,
            ObservationId("scale_route_dimension_edge"),
            (
                MeasurementIdentity.GRAY_WORK,
                MeasurementIdentity.FRAME_DIMENSIONS,
            ),
            "photo edge corroborated by independent frame scale",
        )
        geometry = SimpleNamespace(
            count=2,
            strip_mode="full",
            shared_short_axis=SimpleNamespace(supports_safe_crop=True),
            frame_slots=(
                SimpleNamespace(
                    leading=SimpleNamespace(
                        independently_observed=True,
                        role_provenance=dimension_role,
                    ),
                    trailing=SimpleNamespace(
                        independently_observed=True,
                        role_provenance=direct_role,
                    ),
                ),
                SimpleNamespace(
                    leading=SimpleNamespace(
                        independently_observed=True,
                        role_provenance=direct_role,
                    ),
                    trailing=SimpleNamespace(
                        independently_observed=True,
                        role_provenance=dimension_role,
                    ),
                ),
            ),
            inter_frame_spacings=(),
            common_frame_width=SimpleNamespace(
                state=EvidenceState.SUPPORTED,
                physical_scale_constraint=object(),
            ),
        )
        evidence = SimpleNamespace(
            frame_slot_topology=SimpleNamespace(state=EvidenceState.SUPPORTED),
            independence=SimpleNamespace(state=EvidenceState.SUPPORTED),
            separator_sequence=SimpleNamespace(
                state=EvidenceState.UNAVAILABLE,
                hard_count=1,
            ),
            frame_dimensions=SimpleNamespace(state=EvidenceState.SUPPORTED),
            content_preservation_state=EvidenceState.SUPPORTED,
            internal_frame_boundary_preservation=SimpleNamespace(observations=()),
            partial_edge_safety=SimpleNamespace(state=EvidenceState.UNAVAILABLE),
            holder_occupancy=SimpleNamespace(occupancy_state="unavailable"),
        )

        dimension_path = next(
            path
            for path in sequence_proof_paths_for_geometry(geometry, evidence)
            if path.code == "dimension_sequence_led"
        )

        self.assertEqual(dimension_path.state, EvidenceState.SUPPORTED)
        self.assertIn(
            "common_frame_width_resolution",
            dimension_path.supporting_evidence,
        )

    def test_common_width_and_one_independent_internal_anchor_support_sequence(
        self,
    ) -> None:
        direct_role = MeasurementProvenance(
            MeasurementIdentity.PHOTO_EDGES,
            ObservationId("single_repeated_sequence_anchor"),
            (MeasurementIdentity.GRAY_WORK,),
            "one direct internal photo edge pair",
        )
        dimension_role = MeasurementProvenance(
            MeasurementIdentity.PHOTO_EDGES,
            ObservationId("repeated_sequence_dimension_edge"),
            (
                MeasurementIdentity.GRAY_WORK,
                MeasurementIdentity.FRAME_DIMENSIONS,
            ),
            "photo edge corroborated by independent frame scale",
        )

        def boundary(*, independently_observed: bool, provenance):
            return SimpleNamespace(
                independently_observed=independently_observed,
                role_provenance=provenance,
            )

        geometry = SimpleNamespace(
            count=3,
            strip_mode="full",
            shared_short_axis=SimpleNamespace(supports_safe_crop=True),
            frame_slots=(
                SimpleNamespace(
                    leading=boundary(
                        independently_observed=True,
                        provenance=dimension_role,
                    ),
                    trailing=boundary(
                        independently_observed=True,
                        provenance=direct_role,
                    ),
                ),
                SimpleNamespace(
                    leading=boundary(
                        independently_observed=True,
                        provenance=direct_role,
                    ),
                    trailing=boundary(
                        independently_observed=False,
                        provenance=None,
                    ),
                ),
                SimpleNamespace(
                    leading=boundary(
                        independently_observed=False,
                        provenance=None,
                    ),
                    trailing=boundary(
                        independently_observed=True,
                        provenance=dimension_role,
                    ),
                ),
            ),
            inter_frame_spacings=(),
            common_frame_width=SimpleNamespace(
                state=EvidenceState.SUPPORTED,
                physical_scale_constraint=object(),
            ),
        )
        evidence = SimpleNamespace(
            frame_slot_topology=SimpleNamespace(state=EvidenceState.SUPPORTED),
            independence=SimpleNamespace(state=EvidenceState.SUPPORTED),
            separator_sequence=SimpleNamespace(
                state=EvidenceState.UNAVAILABLE,
                hard_count=1,
            ),
            frame_dimensions=SimpleNamespace(state=EvidenceState.SUPPORTED),
            content_preservation_state=EvidenceState.SUPPORTED,
            internal_frame_boundary_preservation=SimpleNamespace(observations=()),
            partial_edge_safety=SimpleNamespace(state=EvidenceState.UNAVAILABLE),
            holder_occupancy=SimpleNamespace(occupancy_state="unavailable"),
        )

        dimension_path = next(
            path
            for path in sequence_proof_paths_for_geometry(geometry, evidence)
            if path.code == "dimension_sequence_led"
        )

        self.assertEqual(dimension_path.state, EvidenceState.SUPPORTED)

        second_anchor = MeasurementProvenance(
            MeasurementIdentity.PHOTO_EDGES,
            ObservationId("second_repeated_sequence_anchor"),
            (MeasurementIdentity.GRAY_WORK,),
            "second direct internal photo edge pair",
        )
        repeated_geometry = SimpleNamespace(
            **{
                **geometry.__dict__,
                "frame_slots": (
                    geometry.frame_slots[0],
                    SimpleNamespace(
                        leading=geometry.frame_slots[1].leading,
                        trailing=boundary(
                            independently_observed=True,
                            provenance=second_anchor,
                        ),
                    ),
                    SimpleNamespace(
                        leading=boundary(
                            independently_observed=True,
                            provenance=second_anchor,
                        ),
                        trailing=geometry.frame_slots[2].trailing,
                    ),
                ),
            }
        )
        repeated_path = next(
            path
            for path in sequence_proof_paths_for_geometry(
                repeated_geometry,
                evidence,
            )
            if path.code == "dimension_sequence_led"
        )

        self.assertEqual(repeated_path.state, EvidenceState.SUPPORTED)

        width_pattern_anchor = replace(
            second_anchor,
            observation_id=ObservationId("repeated_width_pattern_anchor"),
            dependencies=(
                MeasurementIdentity.GRAY_WORK,
                MeasurementIdentity.FRAME_WIDTH_PATTERN,
            ),
            description="edge role corroborated by the repeated width pattern",
        )
        width_pattern_geometry = SimpleNamespace(
            **{
                **geometry.__dict__,
                "frame_slots": (
                    SimpleNamespace(
                        leading=geometry.frame_slots[0].leading,
                        trailing=boundary(
                            independently_observed=True,
                            provenance=width_pattern_anchor,
                        ),
                    ),
                    SimpleNamespace(
                        leading=boundary(
                            independently_observed=True,
                            provenance=width_pattern_anchor,
                        ),
                        trailing=boundary(
                            independently_observed=True,
                            provenance=width_pattern_anchor,
                        ),
                    ),
                    SimpleNamespace(
                        leading=boundary(
                            independently_observed=True,
                            provenance=width_pattern_anchor,
                        ),
                        trailing=geometry.frame_slots[2].trailing,
                    ),
                ),
            }
        )
        width_pattern_path = next(
            path
            for path in sequence_proof_paths_for_geometry(
                width_pattern_geometry,
                evidence,
            )
            if path.code == "dimension_sequence_led"
        )

        self.assertEqual(width_pattern_path.state, EvidenceState.UNAVAILABLE)

    def test_content_contradiction_cannot_support_dimension_sequence(self) -> None:
        geometry = _measured_internal_edge_geometry()
        evidence = candidate_evidence_fixture(
            geometry=geometry,
            content_preservation=EvidenceState.CONTRADICTED,
        )
        dimension_path = next(
            path
            for path in sequence_proof_paths_for_geometry(geometry, evidence)
            if path.code == "dimension_sequence_led"
        )

        self.assertEqual(
            evidence.content_preservation_state,
            EvidenceState.CONTRADICTED,
        )
        self.assertEqual(dimension_path.state, EvidenceState.UNAVAILABLE)

    def test_uncorroborated_overlap_cannot_support_dimension_sequence(self) -> None:
        geometry = _measured_internal_edge_geometry(
            left_trailing_position=160.0,
            right_leading_position=150.0,
        )
        evidence = candidate_evidence_fixture(geometry=geometry)
        dimension_path = next(
            path
            for path in sequence_proof_paths_for_geometry(geometry, evidence)
            if path.code == "dimension_sequence_led"
        )

        self.assertEqual(
            geometry.inter_frame_spacings[0].basis,
            InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS,
        )
        self.assertEqual(dimension_path.state, EvidenceState.UNAVAILABLE)

    def test_unresolved_geometry_spacing_can_remain_compatible(self) -> None:
        geometry = _measured_internal_edge_geometry()
        unresolved_spacing = replace(
            geometry.inter_frame_spacings[0],
            signed_width_px=PixelInterval(-10.0, 10.0),
            basis=InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS,
        )
        unresolved_geometry = SimpleNamespace(
            count=geometry.count,
            strip_mode=geometry.strip_mode,
            shared_short_axis=geometry.shared_short_axis,
            frame_slots=geometry.frame_slots,
            inter_frame_spacings=(unresolved_spacing,),
            common_frame_width=geometry.common_frame_width,
        )
        evidence = candidate_evidence_fixture(geometry=geometry)

        dimension_path = next(
            path
            for path in sequence_proof_paths_for_geometry(
                unresolved_geometry,
                evidence,
            )
            if path.code == "dimension_sequence_led"
        )

        self.assertEqual(unresolved_spacing.state, EvidenceState.UNAVAILABLE)
        self.assertFalse(unresolved_spacing.supports_output_protection)
        self.assertEqual(dimension_path.state, EvidenceState.SUPPORTED)

    def test_observed_uncertain_spacing_can_support_dimension_sequence(self) -> None:
        geometry = _measured_internal_edge_geometry(
            left_trailing_position=PixelInterval(150.0, 155.0),
            right_leading_position=PixelInterval(145.0, 160.0),
        )
        observed_spacing = replace(
            geometry.inter_frame_spacings[0],
            basis=InterFrameSpacingBasis.OBSERVED,
        )
        observed_geometry = replace(
            geometry,
            inter_frame_spacings=(observed_spacing,),
        )
        evidence = candidate_evidence_fixture(geometry=observed_geometry)

        dimension_path = next(
            path
            for path in sequence_proof_paths_for_geometry(
                observed_geometry,
                evidence,
            )
            if path.code == "dimension_sequence_led"
        )

        self.assertEqual(observed_spacing.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(dimension_path.state, EvidenceState.SUPPORTED)

    def test_separator_width_variation_is_not_gate_language(self) -> None:
        source = "\n".join(
            path.read_text()
            for path in (
                PROJECT_ROOT / "x5crop/detection/candidate/assessment"
            ).rglob("*.py")
        )
        self.assertNotIn("separator_width_unstable", source)
        self.assertNotIn("separator_width_cv >", source)


if __name__ == "__main__":
    unittest.main()
