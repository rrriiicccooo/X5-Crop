from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.template_test_support import (
    phase_edge,
    phase_separator,
    phase_sequence_measurement,
)
from x5crop.domain import FiniteInterval, ObservationId
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.template_model import (
    OverlapRelation,
    adjacency_topology_required_bindings,
    realize_topology_relations_at_role_positions,
)
from x5crop.detection.photo_geometry.template_overlap import (
    observe_overlap_edge_pairs,
)


def _edge(name: str, coordinate: float, role: BoundaryRole):
    return replace(
        phase_edge(name, coordinate),
        qualified_anchor_roles=(role,),
    )


def _measurement(maximum: float = 500.0):
    return phase_sequence_measurement(
        "overlap-contract",
        FiniteInterval(0.0, maximum),
    )


class TemplateOverlapContractTest(unittest.TestCase):
    def test_calibrated_state_realizes_overlap_inside_measured_interval(
        self,
    ) -> None:
        relation = OverlapRelation(
            relation_ordinal=1,
            overlap_observation_id=ObservationId("overlap:calibrated"),
            end_edge_observation_id=ObservationId("edge:end"),
            next_start_edge_observation_id=ObservationId("edge:start"),
            signed_gap_interval_px=FiniteInterval(-10.0, -4.0),
            canonical_signed_gap_px=-7.0,
            delta_interval_px=FiniteInterval(-30.0, -24.0),
            canonical_delta_px=-27.0,
            supporting_observation_ids=(
                ObservationId("edge:end"),
                ObservationId("edge:start"),
            ),
        )

        (realized,) = realize_topology_relations_at_role_positions(
            (relation,),
            model_role_positions_px=(0.0, 100.0, 94.0, 194.0),
            direction=1,
            frame_width_px=100.0,
            pitch_px=120.0,
        )

        self.assertEqual(realized.canonical_signed_gap_px, -6.0)
        self.assertEqual(realized.canonical_delta_px, -26.0)
        self.assertEqual(
            adjacency_topology_required_bindings((realized,)),
            (
                (1, ObservationId("edge:end")),
                (2, ObservationId("edge:start")),
            ),
        )

    def test_spatially_adjacent_independent_reversed_edges_form_one_pair(
        self,
    ) -> None:
        edges = (
            _edge("frame-1:start", 100.0, BoundaryRole.START),
            _edge("frame-2:start", 195.0, BoundaryRole.START),
            _edge("frame-1:end", 200.0, BoundaryRole.END),
            _edge("frame-2:end", 295.0, BoundaryRole.END),
        )

        (observation,) = observe_overlap_edge_pairs(
            edges,
            (),
            (_measurement(),),
            direction=1,
            maximum_overlap_px=12.0,
        )

        self.assertEqual(
            observation.supporting_observation_ids,
            (edges[2].observation_id, edges[1].observation_id),
        )
        self.assertEqual(observation.canonical_signed_gap_px, -5.0)
        self.assertLess(observation.signed_gap_interval_px.maximum, 0.0)

    def test_positive_separator_material_cannot_become_overlap(self) -> None:
        start = _edge("next:start", 195.0, BoundaryRole.START)
        end = _edge("current:end", 200.0, BoundaryRole.END)
        band = phase_separator(
            "competing-material",
            start,
            end,
            FiniteInterval(4.8, 5.2),
        )

        result = observe_overlap_edge_pairs(
            (start, end),
            (band,),
            (_measurement(),),
            direction=1,
            maximum_overlap_px=12.0,
        )

        self.assertEqual(result, ())

    def test_overlapping_edge_identities_do_not_create_a_pair(self) -> None:
        first = _edge("start:a", 195.0, BoundaryRole.START)
        second = _edge("start:b", 195.1, BoundaryRole.START)
        end = _edge("end", 200.0, BoundaryRole.END)

        result = observe_overlap_edge_pairs(
            (first, second, end),
            (),
            (_measurement(),),
            direction=1,
            maximum_overlap_px=12.0,
        )

        self.assertEqual(result, ())

    def test_pair_registration_is_linear_and_bounded_by_local_corridor(
        self,
    ) -> None:
        edges = tuple(
            _edge(f"edge:{index}", coordinate, role)
            for index, (coordinate, role) in enumerate(
                (
                    (100.0, BoundaryRole.START),
                    (180.0, BoundaryRole.START),
                    (200.0, BoundaryRole.END),
                    (280.0, BoundaryRole.END),
                    (300.0, BoundaryRole.START),
                    (400.0, BoundaryRole.END),
                )
            )
        )

        result = observe_overlap_edge_pairs(
            edges,
            (),
            (_measurement(),),
            direction=1,
            maximum_overlap_px=12.0,
        )

        self.assertEqual(result, ())
        self.assertLessEqual(len(result), len(edges) - 1)


if __name__ == "__main__":
    unittest.main()
