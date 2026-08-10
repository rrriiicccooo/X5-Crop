from __future__ import annotations

from types import SimpleNamespace
import inspect
import unittest
from unittest import mock

from x5crop.detection.evidence.content_occupancy import (
    ContentOccupancyObservation,
    ContentOccupancyObservationSet,
)
from x5crop.detection.photo_geometry.bounds import (
    MAX_BANDS_PER_CORRIDOR,
)
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.detector import _bounded_transition_regions
from x5crop.detection.photo_geometry.output import (
    direct_use_budget_assessment,
    safe_crop_envelope_from_placement,
)
from x5crop.detection.photo_geometry import solver
from x5crop.detection.photo_geometry.selection import (
    ChainEvidenceTier,
    ChainLedgerEntry,
    CompleteChainRecord,
    ContentVetoReason,
    PlacementCluster,
    ProducerBoundsReceipt,
    _compatible_source_geometry_clusters,
    cluster_sampling_equivalent_chains,
    cluster_strictly_dominates,
    content_veto_assessment,
)
from x5crop.detection.photo_geometry.source_geometry import SourceScanGeometry
from x5crop.formats import FramePhysicalSpec
from x5crop.detection.photo_geometry.chains import LocalAdvanceKind
from x5crop.domain import (
    Box,
    EvidenceState,
    FiniteInterval,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PositiveInterval,
)


def _chain(
    name: str,
    *,
    box: Box,
    interval: FiniteInterval,
    pair_count: int = 1,
    direct_count: int = 2,
    identities: tuple[str, ...] = ("a", "b"),
) -> CompleteChainRecord:
    observation_ids = tuple(ObservationId(value) for value in identities)
    return CompleteChainRecord(
        chain_id=f"chain:{name}",
        placement_id=f"placement:{name}",
        lane_id="lane:0",
        sampling_boxes=(box,),
        sampling_authority_boxes=(Box(0, 0, 20, 20),),
        authority_profile_ids=("holder:test",),
        boundary_intervals_px=(interval,) * 4,
        direction_id="direction:test",
        source_scan_geometry_id="source-geometry:test",
        direct_observation_count=direct_count,
        structural_pair_count=pair_count,
        direct_observation_ids=observation_ids,
        structural_observation_ids=observation_ids,
        normal_gap_supported=True,
        separator_material_quality=1.0,
        local_advance_authorized=True,
        ledger=(),
    )


def _placement(name: str, residual: float = 0.0):
    boundary = SimpleNamespace(
        full_position_interval_px=FiniteInterval.exact(1.0)
    )
    return SimpleNamespace(
        placement_id=f"placement:{name}",
        fixed_frames=SimpleNamespace(
            frames=(
                SimpleNamespace(
                    start=boundary,
                    end=boundary,
                    top=boundary,
                    bottom=boundary,
                ),
            )
        ),
        sequence=SimpleNamespace(
            observations=(SimpleNamespace(fit_residual_px=residual),)
        ),
        cross=SimpleNamespace(evidence=()),
    )


def _cluster(
    name: str,
    *,
    pair_count: int,
    direct_count: int,
    pair_ids: tuple[str, ...],
    direct_ids: tuple[str, ...],
) -> PlacementCluster:
    return PlacementCluster(
        cluster_id=f"cluster:{name}",
        chain_ids=(f"chain:{name}",),
        representative_placement_id=f"placement:{name}",
        sampling_boxes=(Box(0, 0, 10, 10),),
        boundary_intersections_px=(FiniteInterval.exact(1.0),) * 4,
        direct_observation_count=direct_count,
        structural_pair_count=pair_count,
        direct_observation_ids=tuple(
            ObservationId(value) for value in direct_ids
        ),
        structural_observation_ids=tuple(
            ObservationId(value) for value in pair_ids
        ),
        normal_gap_supported=True,
        separator_material_quality=1.0,
    )


def _observation(box: Box) -> ContentOccupancyObservationSet:
    identity = ObservationId(
        f"content:{box.left}:{box.top}:{box.right}:{box.bottom}"
    )
    observation = ContentOccupancyObservation(
        observation_id=identity,
        lane_id="lane:0",
        source_box=box,
        source_cells=(box,),
        reliability=0.95,
        provenance=MeasurementProvenance(
            root_measurement=MeasurementIdentity.CONTENT_OCCUPANCY,
            observation_id=identity,
            dependencies=(MeasurementIdentity.BASE_GRAY,),
            description="test content occupancy",
        ),
    )
    return ContentOccupancyObservationSet(
        lane_id="lane:0",
        observations=(observation,),
        long_sample_count=16,
        cross_sample_count=16,
        proposed_observation_count=1,
        proposed_cell_run_count=1,
        overflowed=False,
    )


def _frame(start: float, end: float):
    return SimpleNamespace(
        start=SimpleNamespace(full_position_interval_px=FiniteInterval.exact(start)),
        end=SimpleNamespace(full_position_interval_px=FiniteInterval.exact(end)),
        top=SimpleNamespace(full_position_interval_px=FiniteInterval.exact(10.0)),
        bottom=SimpleNamespace(full_position_interval_px=FiniteInterval.exact(20.0)),
    )


def _content_placement(
    frames: tuple[object, ...],
    relations: tuple[LocalAdvanceKind, ...],
):
    return SimpleNamespace(
        placement_id="placement:content",
        fixed_frames=SimpleNamespace(frames=frames),
        sequence=SimpleNamespace(
            lane_gap_model=SimpleNamespace(
                state=EvidenceState.SUPPORTED,
                gap_interval_px=FiniteInterval.exact(4.0),
            ),
            local_advance_relations=tuple(
                SimpleNamespace(kind=value) for value in relations
            ),
        ),
    )


class ChainSelectionContractTest(unittest.TestCase):
    def test_dual_lane_joint_solver_queries_only_scale_compatible_chains(
        self,
    ) -> None:
        frame = FramePhysicalSpec(36.0, 24.0, 2.0)

        def geometry(minimum: float, maximum: float) -> SourceScanGeometry:
            return SourceScanGeometry.create(
                frame,
                width_scale_px_per_mm=PositiveInterval(minimum, maximum),
                height_scale_px_per_mm=PositiveInterval(minimum, maximum),
            )

        compatible = _cluster(
            "compatible",
            pair_count=1,
            direct_count=1,
            pair_ids=("a",),
            direct_ids=("a",),
        )
        incompatible = _cluster(
            "incompatible",
            pair_count=1,
            direct_count=1,
            pair_ids=("b",),
            direct_ids=("b",),
        )
        right = {
            compatible.representative_placement_id: SimpleNamespace(
                frame_spec=frame,
                source_scan_geometry=geometry(9.5, 10.5),
            ),
            incompatible.representative_placement_id: SimpleNamespace(
                frame_spec=frame,
                source_scan_geometry=geometry(11.0, 12.0),
            ),
        }
        matches = _compatible_source_geometry_clusters(
            (compatible, incompatible),
            right,
            SimpleNamespace(
                frame_spec=frame,
                source_scan_geometry=geometry(9.0, 10.0),
            ),
        )
        self.assertEqual(
            tuple(item.cluster_id for item, _shared in matches),
            (compatible.cluster_id,),
        )
        self.assertEqual(
            matches[0][1].width_state.feasible_scale_interval(),
            PositiveInterval(9.5, 10.0),
        )

    def test_only_raw_corridor_observations_have_a_fixed_cap(self) -> None:
        self.assertEqual(MAX_BANDS_PER_CORRIDOR, 4)
        source = inspect.getsource(solver.materialize_lane_placements)
        self.assertNotIn("proposed[:", source)
        self.assertNotIn("ordered[:", source)

    def test_overflowing_corridor_materializes_no_ranked_subset(self) -> None:
        regions = tuple(
            SimpleNamespace(
                ambiguous=False,
                trace_support_count=8,
                proposal_position_interval_px=FiniteInterval.exact(float(index)),
                region_id=f"region:{index}",
            )
            for index in range(5)
        )
        measurement = SimpleNamespace(query=SimpleNamespace(query_id="corridor:0"))
        with mock.patch(
            "x5crop.detection.photo_geometry.detector."
            "track_side_transition_regions",
            return_value=regions,
        ):
            retained, counts, exceeded = _bounded_transition_regions(
                (measurement,),
                reference_trace_px=10.0,
                boundary_axis_scale_px_per_mm=SimpleNamespace(),
            )
        self.assertEqual(retained, ())
        self.assertEqual(counts[0].proposed_count, 5)
        self.assertEqual(counts[0].materialized_count, 0)
        self.assertTrue(exceeded)

    def test_chain_ledger_preserves_every_unique_entry(self) -> None:
        entries = tuple(
            ChainLedgerEntry(
                entry_id=f"entry:{ordinal}",
                chain_id="chain:overflow",
                ordinal=ordinal,
                evidence_tier=ChainEvidenceTier.WEAK_PRIOR,
                observation_ids=(),
                physical_interval_px=None,
            )
            for ordinal in range(1, 66)
        )
        record = CompleteChainRecord(
            chain_id="chain:overflow",
            placement_id="placement:overflow",
            lane_id="lane:0",
            sampling_boxes=(Box(0, 0, 10, 10),),
            sampling_authority_boxes=(Box(0, 0, 20, 20),),
            authority_profile_ids=("holder:test",),
            boundary_intervals_px=(FiniteInterval.exact(1.0),) * 4,
            direction_id="direction:test",
            source_scan_geometry_id="source-geometry:test",
            direct_observation_count=0,
            structural_pair_count=0,
            direct_observation_ids=(),
            structural_observation_ids=(),
            normal_gap_supported=False,
            separator_material_quality=0.0,
            local_advance_authorized=True,
            ledger=entries,
        )
        self.assertEqual(len(record.ledger), 65)

    def test_safe_envelope_and_budget_accept_one_selected_placement(self) -> None:
        self.assertIn(
            "placement",
            inspect.signature(safe_crop_envelope_from_placement).parameters,
        )
        self.assertNotIn(
            "placements",
            inspect.signature(safe_crop_envelope_from_placement).parameters,
        )
        self.assertIn(
            "placement",
            inspect.signature(direct_use_budget_assessment).parameters,
        )
        self.assertNotIn(
            "placements",
            inspect.signature(direct_use_budget_assessment).parameters,
        )
        self.assertNotIn(
            "minimum_guard",
            inspect.getsource(safe_crop_envelope_from_placement),
        )

    def test_sampling_cluster_requires_exact_boxes_and_common_intervals(
        self,
    ) -> None:
        first = _chain(
            "first",
            box=Box(0, 0, 10, 10),
            interval=FiniteInterval(1.0, 2.0),
        )
        equivalent = _chain(
            "equivalent",
            box=Box(0, 0, 10, 10),
            interval=FiniteInterval(1.5, 2.5),
        )
        displaced = _chain(
            "displaced",
            box=Box(1, 0, 11, 10),
            interval=FiniteInterval(1.5, 2.5),
        )
        disjoint = _chain(
            "disjoint",
            box=Box(0, 0, 10, 10),
            interval=FiniteInterval(3.0, 4.0),
        )
        placements = {
            item.placement_id: _placement(item.placement_id.split(":", 1)[1])
            for item in (first, equivalent, displaced, disjoint)
        }
        clusters = cluster_sampling_equivalent_chains(
            (first, equivalent, displaced, disjoint),
            placements,
        )
        self.assertEqual(sorted(len(item.chain_ids) for item in clusters), [1, 1, 2])
        self.assertEqual(
            clusters,
            cluster_sampling_equivalent_chains(
                (disjoint, displaced, equivalent, first),
                placements,
            ),
        )

    def test_tiered_dominance_rejects_unexplained_same_tier_evidence(self) -> None:
        authority = _cluster(
            "authority",
            pair_count=2,
            direct_count=4,
            pair_ids=("a", "b", "c"),
            direct_ids=("a", "b", "c", "d"),
        )
        explained = _cluster(
            "explained",
            pair_count=1,
            direct_count=3,
            pair_ids=("a", "b"),
            direct_ids=("a", "b", "d"),
        )
        unexplained = _cluster(
            "unexplained",
            pair_count=1,
            direct_count=3,
            pair_ids=("a", "x"),
            direct_ids=("a", "x", "d"),
        )
        self.assertTrue(cluster_strictly_dominates(authority, explained))
        self.assertFalse(cluster_strictly_dominates(authority, unexplained))

    def test_start_end_and_contact_content_are_neutral(self) -> None:
        outside = content_veto_assessment(
            _content_placement((_frame(10.0, 20.0),), ()),
            _observation(Box(0, 12, 5, 16)),
            layout="horizontal",
        )
        contact = content_veto_assessment(
            _content_placement(
                (_frame(10.0, 20.0), _frame(20.0, 30.0)),
                (LocalAdvanceKind.CONTACT,),
            ),
            _observation(Box(18, 12, 22, 16)),
            layout="horizontal",
        )
        overlap = content_veto_assessment(
            _content_placement(
                (_frame(10.0, 21.0), _frame(19.0, 30.0)),
                (LocalAdvanceKind.OVERLAP,),
            ),
            _observation(Box(18, 12, 22, 16)),
            layout="horizontal",
        )
        self.assertFalse(outside.vetoed)
        self.assertFalse(contact.vetoed)
        self.assertFalse(overlap.vetoed)

    def test_only_slot_crop_or_normal_separator_crossing_vetoes(self) -> None:
        slot = content_veto_assessment(
            _content_placement((_frame(10.0, 20.0),), ()),
            _observation(Box(12, 8, 16, 13)),
            layout="horizontal",
        )
        separator = content_veto_assessment(
            _content_placement(
                (_frame(10.0, 18.0), _frame(22.0, 30.0)),
                (LocalAdvanceKind.NOMINAL,),
            ),
            _observation(Box(16, 12, 24, 16)),
            layout="horizontal",
        )
        self.assertEqual(
            {item.reason for item in slot.facts},
            {ContentVetoReason.SLOT_CONTENT_CROPPED_IN},
        )
        self.assertEqual(
            {item.reason for item in separator.facts},
            {ContentVetoReason.SEPARATOR_CORE_CONTENT_CROSSING},
        )


if __name__ == "__main__":
    unittest.main()
