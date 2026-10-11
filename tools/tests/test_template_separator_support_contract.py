from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.template_test_support import (
    phase_edge as edge,
    phase_separator as separator,
    phase_sequence_measurement,
    phase_template,
    placement_sequence,
)
from x5crop.detection.photo_geometry.template_direct_role_authority import (
    DirectRoleAuthorityBasis,
    assess_direct_role_binding_authority,
)
from x5crop.detection.photo_geometry.template_separator_support import (
    SeparatorRoleAuthorityFailureKind,
    resolve_separator_support,
)
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.domain import EvidenceState, FiniteInterval


class TemplateSeparatorSupportContractTest(unittest.TestCase):
    def test_cancelled_pair_authority_keeps_complete_material_role_counterevidence(self) -> None:
        def selected_fit(selected):
            original = placement_sequence(phase_template(2))
            bindings = [None] * 4
            for index, observation in selected.items():
                bindings[index] = replace(
                    original.role_bindings[index],
                    observation_id=observation.observation_id,
                    evidence_group_id=observation.observation_id,
                    canonical_position_px=observation.canonical_position_px,
                    fit_position_interval_px=observation.fit_position_interval_px,
                    full_position_interval_px=observation.full_position_interval_px,
                )
            return replace(original, role_bindings=tuple(bindings),
                           phase_support_coverage=float(len({(i + 1) // 2 for i in selected})))

        a = replace(edge("fork:A", 100.0), qualified_anchor_roles=(BoundaryRole.START,))
        b = replace(edge("fork:B", 120.0), qualified_anchor_roles=(BoundaryRole.END,))
        c = replace(edge("fork:C", 140.0), qualified_anchor_roles=(BoundaryRole.START,),
                    trace_coordinates_px=(0, 10))
        u = edge("unrelated", 360.0)
        full = separator("full", a, b, FiniteInterval(19.8, 20.2))
        partial = separator("partial", b, c, FiniteInterval(19.8, 20.2), region_count=2)
        measurement = phase_sequence_measurement("fork", FiniteInterval(0.0, 500.0))
        for selected, expected in (
            ({1: b}, {1: (full.observation_id,)}),
            ({1: a, 2: b}, {1: (), 2: ()}),
            ({0: u}, {0: ()}),
        ):
            with self.subTest(selected=tuple(selected)):
                authority = assess_direct_role_binding_authority(
                    selected_fit(selected), (a, b, c, u), (full, partial), (measurement,),
                    authorized_source_frame_width_px=FiniteInterval.exact(100.0),
                )
                self.assertEqual({f.role_index: f.blocking_material_conflict_ids
                                  for f in authority.facts}, expected)
                if selected == {1: b}:
                    self.assertEqual(authority.state, EvidenceState.CONTRADICTED)
                    self.assertEqual(authority.facts[0].bases, (
                        DirectRoleAuthorityBasis.SOURCE_WIDE_EDGE,
                    ))
                elif selected == {1: a, 2: b}:
                    self.assertEqual(authority.state, EvidenceState.UNAVAILABLE)
                    self.assertTrue(all(not f.bases for f in authority.facts))

        # Two complete alternatives oppose the shared edge's two roles
        # separately; agreeing outer endpoints are not blanket-blocked.
        a = replace(a, qualified_anchor_roles=(BoundaryRole.END,))
        b = replace(b, qualified_anchor_roles=(BoundaryRole.START,))
        c = replace(c, trace_coordinates_px=(0, 10, 20))
        full2 = separator("full2", b, c, FiniteInterval(19.8, 20.2))
        for selected, expected in (
            ({2: b}, {2: (full2.observation_id,)}),
            ({1: b}, {1: (full.observation_id,)}),
            ({1: a, 2: c}, {1: (), 2: ()}),
        ):
            authority = assess_direct_role_binding_authority(
                selected_fit(selected), (a, b, c), (full, full2), (measurement,),
            )
            self.assertEqual({f.role_index: f.blocking_material_conflict_ids
                              for f in authority.facts}, expected)

        # Neither partial-only material nor an unambiguous complete pair
        # creates this fork counterevidence path.
        for bands in ((partial,), (full,)):
            authority = assess_direct_role_binding_authority(
                selected_fit({1: b}), (a, b, c), bands, (measurement,),
            )
            self.assertFalse(authority.facts[0].blocking_material_conflict_ids)

    def test_unique_source_wide_pair_owns_material_roles(self) -> None:
        left = edge("unique:left", 100.0)
        right = edge("unique:right", 120.0)
        band = separator(
            "unique:band",
            left,
            right,
            FiniteInterval(19.8, 20.2),
        )

        resolution = resolve_separator_support((left, right), (band,))

        self.assertEqual(len(resolution.components), 1)
        component = resolution.components[0]
        self.assertEqual(component.role_authority_state, EvidenceState.SUPPORTED)
        self.assertEqual(
            component.role_authority_pair_edge_observation_ids,
            (left.observation_id, right.observation_id),
        )
        self.assertIsNone(component.failure_kind)
        self.assertEqual(
            resolution.edge_component_ids,
            {
                left.observation_id: band.observation_id,
                right.observation_id: band.observation_id,
            },
        )

    def test_unique_partial_height_pair_retains_no_material_role_authority(
        self,
    ) -> None:
        left = edge("partial:left", 100.0)
        right = edge("partial:right", 120.0)
        band = separator(
            "partial:band",
            left,
            right,
            FiniteInterval(19.8, 20.2),
            region_count=2,
        )

        component = resolve_separator_support(
            (left, right),
            (band,),
        ).components[0]

        self.assertEqual(component.role_authority_state, EvidenceState.UNAVAILABLE)
        self.assertIsNone(component.role_authority_pair_edge_observation_ids)
        self.assertEqual(
            component.failure_kind,
            SeparatorRoleAuthorityFailureKind.INSUFFICIENT_SPATIAL_SUPPORT,
        )

    def test_unique_source_wide_pair_dominates_partial_height_alternative(
        self,
    ) -> None:
        earlier = replace(
            edge("dominant:earlier", 90.0),
            qualified_anchor_roles=(BoundaryRole.START,),
        )
        left = replace(
            edge("dominant:left", 100.0),
            qualified_anchor_roles=(),
        )
        right = replace(
            edge("dominant:right", 120.0),
            qualified_anchor_roles=(BoundaryRole.START,),
        )
        local = separator(
            "dominant:local",
            earlier,
            right,
            FiniteInterval(29.8, 30.2),
            region_count=2,
        )
        source_wide = separator(
            "dominant:source-wide",
            left,
            right,
            FiniteInterval(19.8, 20.2),
        )

        component = resolve_separator_support(
            (earlier, left, right),
            (local, source_wide),
        ).components[0]

        self.assertEqual(component.role_authority_state, EvidenceState.SUPPORTED)
        self.assertEqual(
            component.role_authority_pair_edge_observation_ids,
            (left.observation_id, right.observation_id),
        )
        self.assertEqual(len(component.pair_edge_observation_ids), 2)

    def test_connected_alternative_pairs_are_one_ambiguous_rank_group(
        self,
    ) -> None:
        left = edge("alternative:left", 100.0)
        middle = edge("alternative:middle", 120.0)
        right = edge("alternative:right", 140.0)
        first = separator(
            "alternative:band:1",
            left,
            middle,
            FiniteInterval(19.8, 20.2),
        )
        second = separator(
            "alternative:band:2",
            middle,
            right,
            FiniteInterval(19.8, 20.2),
        )

        resolution = resolve_separator_support(
            (left, middle, right),
            (first, second),
        )

        self.assertEqual(len(resolution.components), 1)
        component = resolution.components[0]
        self.assertEqual(
            component.role_authority_state,
            EvidenceState.CONTRADICTED,
        )
        self.assertEqual(
            component.failure_kind,
            SeparatorRoleAuthorityFailureKind.ALTERNATIVE_PAIR_INTERPRETATIONS,
        )
        self.assertIsNone(component.role_authority_pair_edge_observation_ids)
        self.assertEqual(len(set(resolution.edge_component_ids.values())), 1)

    def test_source_wide_pair_cannot_override_an_intrinsic_endpoint_role(
        self,
    ) -> None:
        earlier = replace(
            edge("conflict:earlier", 90.0),
            qualified_anchor_roles=(),
        )
        left = replace(
            edge("conflict:left", 100.0),
            qualified_anchor_roles=(BoundaryRole.START,),
        )
        right = replace(
            edge("conflict:right", 120.0),
            qualified_anchor_roles=(),
        )
        band = separator(
            "conflict:band",
            left,
            right,
            FiniteInterval(19.8, 20.2),
        )
        alternative = separator(
            "conflict:alternative",
            earlier,
            left,
            FiniteInterval(9.8, 10.2),
            region_count=2,
        )

        component = resolve_separator_support(
            (earlier, left, right),
            (alternative, band),
        ).components[0]

        self.assertEqual(
            component.role_authority_state,
            EvidenceState.CONTRADICTED,
        )
        self.assertEqual(
            component.failure_kind,
            SeparatorRoleAuthorityFailureKind.ENDPOINT_ROLE_CONFLICT,
        )
        self.assertEqual(
            component.conflicting_edge_observation_ids,
            (left.observation_id,),
        )

    def test_isolated_source_wide_pair_overrides_single_edge_role_hint(
        self,
    ) -> None:
        left = replace(
            edge("isolated:left", 100.0),
            qualified_anchor_roles=(BoundaryRole.START,),
        )
        right = replace(
            edge("isolated:right", 120.0),
            qualified_anchor_roles=(),
        )
        band = separator(
            "isolated:band",
            left,
            right,
            FiniteInterval(19.8, 20.2),
        )

        component = resolve_separator_support(
            (left, right),
            (band,),
        ).components[0]

        self.assertEqual(component.role_authority_state, EvidenceState.SUPPORTED)
        self.assertEqual(
            component.role_authority_pair_edge_observation_ids,
            (left.observation_id, right.observation_id),
        )
        self.assertEqual(component.conflicting_edge_observation_ids, ())

    def test_leaf_endpoint_hint_does_not_defeat_source_wide_material(
        self,
    ) -> None:
        earlier = replace(
            edge("leaf:earlier", 90.0),
            qualified_anchor_roles=(),
        )
        left = replace(
            edge("leaf:left", 100.0),
            qualified_anchor_roles=(),
        )
        right = replace(
            edge("leaf:right", 120.0),
            qualified_anchor_roles=(BoundaryRole.END,),
        )
        local = separator(
            "leaf:local",
            earlier,
            left,
            FiniteInterval(9.8, 10.2),
            region_count=2,
        )
        source_wide = separator(
            "leaf:source-wide",
            left,
            right,
            FiniteInterval(19.8, 20.2),
        )

        component = resolve_separator_support(
            (earlier, left, right),
            (local, source_wide),
        ).components[0]

        self.assertEqual(component.role_authority_state, EvidenceState.SUPPORTED)
        self.assertEqual(
            component.role_authority_pair_edge_observation_ids,
            (left.observation_id, right.observation_id),
        )
        self.assertEqual(component.conflicting_edge_observation_ids, ())


if __name__ == "__main__":
    unittest.main()
