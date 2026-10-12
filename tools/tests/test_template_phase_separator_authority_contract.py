from __future__ import annotations

from dataclasses import replace
import unittest

from x5crop.detection.photo_geometry import template_phase_observations as phase_observations
from tools.tests.template_test_support import (
    phase_edge as edge,
    phase_sequence_measurement,
    phase_separator as separator,
    phase_template as template,
)
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.line_observations import PhysicalLineRegion
from x5crop.detection.photo_geometry.observation_types import (
    BoundaryEdgeMeasurementBasis,
    SeparatorMaterialPolarity,
)
from x5crop.detection.photo_geometry.template_direct_role_authority import (
    DirectRoleAuthorityBasis,
    assess_direct_role_binding_authority,
)
from x5crop.detection.photo_geometry.template_phase_competition import fit_template_phase
from x5crop.detection.photo_geometry.template_phase_fitting import _match_roles
from x5crop.detection.photo_geometry.template_phase_observations import (
    _facts,
    _with_separator_role_authority,
    _separator_role_authority,
)
from x5crop.detection.photo_geometry.template_phase_model import PhaseFitStatus
from x5crop.domain import EvidenceState, FiniteInterval, ObservationId


class TemplatePhaseSeparatorAuthorityContractTest(unittest.TestCase):
    def test_physical_line_seed_requires_complete_direct_family(
        self,
    ) -> None:
        compiled = template(1)
        for closed, spanning, basis in (
            (False, True, BoundaryEdgeMeasurementBasis.DIRECT_TRACE),
            (True, True, BoundaryEdgeMeasurementBasis.DIRECT_TRACE),
            (True, False, BoundaryEdgeMeasurementBasis.DIRECT_TRACE),
            (True, True, BoundaryEdgeMeasurementBasis.BROAD_MATERIAL_TRACE),
        ):
            for required in (False, True):
                with self.subTest(
                    closed=closed, spanning=spanning, basis=basis,
                    required=required,
                ):
                    observation = replace(
                        edge("rough:start", 100.0),
                        qualified_anchor_roles=(BoundaryRole.START,),
                        fit_residual_px=12.0,
                        canonical_direction_degrees=0.0,
                        fit_direction_interval_degrees=FiniteInterval.exact(0.0),
                        full_direction_interval_degrees=FiniteInterval.exact(0.0),
                        trace_coordinates_px=(
                            tuple(range(21)) if spanning else (0, 10, 20)
                        ),
                        measurement_basis=basis,
                        physical_line_region=(
                            PhysicalLineRegion(10.0, ((100.0, 0.0),))
                            if closed else None
                        ),
                    )
                    matches = _match_roles(
                        _facts(
                            (observation,),
                            registered_trace_positions_px=tuple(range(21)),
                        ),
                        compiled.roles,
                        (),
                        phase=100.0,
                        width=100.0,
                        pitch=120.0,
                        direction=1,
                        prefixes=(0.0,),
                        frame_width=compiled.frame_width_px,
                        fit_residual_limit_px=7.5,
                        required_bindings=(
                            ((0, observation.observation_id),) if required else ()
                        ),
                    )
                    accepted = (
                        closed and spanning and required
                        and basis == BoundaryEdgeMeasurementBasis.DIRECT_TRACE
                    )
                    self.assertEqual(bool(matches), accepted)
                    if accepted:
                        self.assertEqual(
                            matches[0][1].line_evidence.physical_line_region,
                            observation.physical_line_region,
                        )
                        self.assertEqual(matches[0][1].fit_residual_px, 12.0)

    def test_material_role_hypothesis_requires_the_exact_seed_pair(self) -> None:
        left = replace(
            edge("hypothesis:left", 110.0),
            qualified_anchor_roles=(BoundaryRole.START,),
        )
        right = replace(
            edge("hypothesis:right", 130.0),
            qualified_anchor_roles=(BoundaryRole.END,),
        )
        band = separator(
            "hypothesis:material", left, right,
            FiniteInterval(19.8, 20.2), region_count=2,
        )
        spec = template(2)
        facts = _facts((left, right))
        pairs = phase_observations._separator_pair_facts(
            (band,), facts, maximum_material_gap_px=20.0,
        )
        seeds = phase_observations._separator_phase_seeds(
            (band,), facts, spec.roles, spec,
            width=100.0, pitch=120.0, prefixes=(0.0, 0.0),
        )
        required = ((1, left.observation_id), (2, right.observation_id))
        self.assertTrue(seeds)
        self.assertTrue(all(seed.required_bindings == required for seed in seeds))
        for bindings in ((), required[:1], required):
            with self.subTest(bindings=bindings):
                matches = _match_roles(
                    facts, spec.roles, pairs,
                    phase=10.0, width=100.0, pitch=120.0, direction=1,
                    prefixes=(0.0, 0.0), frame_width=spec.frame_width_px,
                    fit_residual_limit_px=None, required_bindings=bindings,
                )
                self.assertEqual(
                    tuple((role.role_index, fact.observation_id)
                          for role, fact in matches),
                    required if bindings == required else (),
                )
        self.assertEqual(left.qualified_anchor_roles, (BoundaryRole.START,))
        self.assertEqual(right.qualified_anchor_roles, (BoundaryRole.END,))

    def test_material_hypothesis_does_not_reserve_an_opposite_qualified_role(
        self,
    ) -> None:
        left = replace(
            edge("material-hypothesis:left", 210.0),
            qualified_anchor_roles=(BoundaryRole.START,),
        )
        right = replace(
            edge("material-hypothesis:right", 230.0),
            qualified_anchor_roles=(BoundaryRole.END,),
        )
        facts = _facts((left, right))
        by_id = {fact.observation_id: fact for fact in facts}
        spec = template(2)
        matches = _match_roles(
            facts, spec.roles,
            ((by_id[left.observation_id], by_id[right.observation_id]),),
            phase=10.0, width=100.0, pitch=120.0, direction=1,
            prefixes=(0.0, 0.0), frame_width=spec.frame_width_px,
            fit_residual_limit_px=None,
        )
        self.assertEqual(
            tuple((role.role_index, fact.observation_id)
                  for role, fact in matches),
            ((3, right.observation_id),),
        )

    def test_material_role_hypothesis_cannot_borrow_intrinsic_role_authority(
        self,
    ) -> None:
        original = tuple(
            replace(edge(f"hypothesis:{index}", coordinate),
                    qualified_anchor_roles=(role,))
            for index, coordinate, role in (
                (0, 10.0, BoundaryRole.START),
                (1, 110.0, BoundaryRole.END),
                (2, 130.0, BoundaryRole.START),
                (3, 230.0, BoundaryRole.END),
            )
        )
        fit = fit_template_phase(original, template(2)).best
        assert fit is not None
        for donor in (False, True, None):
            with self.subTest(donor=donor):
                observations = list(original)
                observations[1] = replace(
                    original[1], qualified_anchor_roles=(
                        () if donor is None else (
                            BoundaryRole.END if donor else BoundaryRole.START,
                        )
                    ),
                )
                observations[2] = replace(
                    original[2], qualified_anchor_roles=(BoundaryRole.END,),
                )
                band = separator(
                    "hypothesis:partial-transfer", observations[1], observations[2],
                    FiniteInterval(19.8, 20.2), region_count=2,
                )
                authority = assess_direct_role_binding_authority(
                    fit, tuple(observations), (band,),
                    (phase_sequence_measurement(
                        "hypothesis:registered", FiniteInterval(0.0, 260.0),
                    ),),
                )
                facts = {fact.role_index: fact for fact in authority.facts}
                self.assertEqual(
                    facts[2].bases,
                    (DirectRoleAuthorityBasis.PARTIAL_HEIGHT_SEPARATOR_PAIR,)
                    if donor is not False else (),
                )
                if donor is False:
                    self.assertEqual(facts[1].bases, ())

    def test_separator_roles_cannot_form_an_unobserved_mixed_pair(self) -> None:
        observations = (
            replace(
                edge("outer:start", 30.0),
                qualified_anchor_roles=(BoundaryRole.START,),
            ),
            replace(
                edge("band:a:end", 110.0),
                qualified_anchor_roles=(BoundaryRole.END,),
            ),
            replace(
                edge("band:b:end", 130.0),
                qualified_anchor_roles=(BoundaryRole.END,),
            ),
            replace(
                edge("band:a:start", 150.0),
                qualified_anchor_roles=(BoundaryRole.START,),
            ),
            replace(
                edge("band:b:start", 170.0),
                qualified_anchor_roles=(BoundaryRole.START,),
            ),
            replace(
                edge("outer:end", 250.0),
                qualified_anchor_roles=(BoundaryRole.END,),
            ),
        )
        facts = _facts(observations)
        by_id = {item.observation_id: item for item in facts}
        separator_pairs = (
            (
                by_id[ObservationId("band:a:end")],
                by_id[ObservationId("band:a:start")],
            ),
            (
                by_id[ObservationId("band:b:end")],
                by_id[ObservationId("band:b:start")],
            ),
        )
        compiled = template(2)

        matches = _match_roles(
            facts,
            compiled.roles,
            separator_pairs,
            phase=30.0,
            width=100.0,
            pitch=120.0,
            direction=1,
            prefixes=(0.0, 0.0),
            frame_width=compiled.frame_width_px,
            fit_residual_limit_px=None,
        )

        self.assertEqual(
            tuple((role.role_index, fact.observation_id) for role, fact in matches),
            (
                (0, ObservationId("outer:start")),
                (3, ObservationId("outer:end")),
            ),
        )

    def test_unique_source_wide_band_grants_separator_roles(self) -> None:
        observations = tuple(
            edge(f"edge:unique-source-wide:{index}", coordinate)
            for index, coordinate in enumerate((110.0, 130.0))
        )
        authority = _separator_role_authority(
            observations,
            (
                separator(
                    "separator:unique-source-wide",
                    observations[0],
                    observations[1],
                    FiniteInterval(19.8, 20.2),
                ),
            )
        )

        self.assertEqual(
            authority,
            {
                observations[0].observation_id: frozenset(
                    (BoundaryRole.END,)
                ),
                observations[1].observation_id: frozenset(
                    (BoundaryRole.START,)
                ),
            },
        )

    def test_material_role_keeps_existing_pixel_interpretation(self) -> None:
        left = replace(
            edge("material:left", 108.0),
            qualified_anchor_roles=(BoundaryRole.END,),
        )
        right = replace(
            edge("material:right", 110.0),
            qualified_anchor_roles=(BoundaryRole.END,),
            polarity=-1,
        )
        band = separator(
            "material:bright-strip",
            left,
            right,
            FiniteInterval(1.8, 2.2),
            material_polarity=SeparatorMaterialPolarity.LIGHT,
        )

        augmented = _with_separator_role_authority(
            (left, right),
            (band,),
            maximum_material_gap_px=20.0,
        )

        self.assertEqual(augmented[0].qualified_anchor_roles, (BoundaryRole.END,))
        self.assertEqual(
            augmented[1].qualified_anchor_roles,
            (BoundaryRole.START, BoundaryRole.END),
        )
        self.assertEqual(
            replace(
                augmented[1],
                qualified_anchor_roles=right.qualified_anchor_roles,
            ),
            right,
        )
        facts = _facts(
            augmented,
            separator_support_ids={
                left.observation_id: band.observation_id,
                right.observation_id: band.observation_id,
            },
        )
        self.assertEqual(len(facts), 2)
        self.assertEqual(
            {fact.evidence_group_id for fact in facts},
            {band.observation_id},
        )

    def test_material_alternative_keeps_one_vote_and_uses_independent_lattice(
        self,
    ) -> None:
        spec = template(4)
        spec = replace(
            spec,
            pitch_px=110.0,
            nominal_gap_px=10.0,
            phase_lattice_authority=replace(
                spec.phase_lattice_authority,
                period_px=110.0,
            ),
        )
        for material_polarity in SeparatorMaterialPolarity:
            for inside_frame in (False, True):
                with self.subTest(
                    material_polarity=material_polarity,
                    inside_frame=inside_frame,
                ):
                    coordinates = (
                        (108.0, 110.0) if inside_frame else (110.0, 120.0)
                    )
                    observed = (
                        (coordinates[0], BoundaryRole.END),
                        (coordinates[1], BoundaryRole.END),
                        (230.0, BoundaryRole.START),
                        (330.0, BoundaryRole.END),
                        (340.0, BoundaryRole.START),
                        (440.0, BoundaryRole.END),
                    )
                    material_left_polarity = (
                        1 if material_polarity == SeparatorMaterialPolarity.LIGHT else -1
                    )
                    observations = tuple(
                        replace(
                            edge(f"edge:material-alternative:{index}", coordinate),
                            qualified_anchor_roles=(role,),
                            polarity=(
                                material_left_polarity * (1 if index == 0 else -1)
                                if index < 2
                                else 1 if role == BoundaryRole.START else -1
                            ),
                        )
                        for index, (coordinate, role) in enumerate(observed)
                    )
                    gap = coordinates[1] - coordinates[0]
                    band = separator(
                        "material:alternative",
                        observations[0],
                        observations[1],
                        FiniteInterval(gap - 0.2, gap + 0.2),
                        material_polarity=material_polarity,
                    )

                    result = fit_template_phase(
                        observations,
                        spec,
                        separator_bands=(band,),
                        holder_span_px=FiniteInterval(0.0, 455.0),
                    )

                    self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
                    assert result.best is not None
                    self.assertEqual(result.best.phase_support_count, 4)
                    self.assertAlmostEqual(
                        result.best.phase_lattice_fit.canonical_absolute_phase_px,
                        10.0,
                    )
                    self.assertEqual(
                        result.best.binding_observation_ids[1],
                        observations[1 if inside_frame else 0].observation_id,
                    )
                    self.assertEqual(
                        result.best.binding_observation_ids[2],
                        None if inside_frame else observations[1].observation_id,
                    )

    def test_retained_pixel_role_cannot_borrow_opposite_material_authority(
        self,
    ) -> None:
        start = replace(
            edge("material-role:start", 100.0),
            qualified_anchor_roles=(BoundaryRole.START,),
        )
        left = replace(
            edge("material-role:left", 198.0),
            qualified_anchor_roles=(BoundaryRole.END,),
            polarity=-1,
        )
        right = replace(
            edge("material-role:right", 200.0, support_fraction=2.0 / 3.0),
            qualified_anchor_roles=(BoundaryRole.END,),
            trace_coordinates_px=(0, 10),
        )
        band = separator(
            "material:role-authority",
            left,
            right,
            FiniteInterval(1.8, 2.2),
        )
        augmented = _with_separator_role_authority(
            (start, left, right),
            (band,),
            maximum_material_gap_px=20.0,
        )
        fit = fit_template_phase((start, right), template(1)).best
        assert fit is not None

        authority = assess_direct_role_binding_authority(
            fit,
            augmented,
            (band,),
            (phase_sequence_measurement("material-role", FiniteInterval(0, 250)),),
        )

        retained = next(
            fact for fact in authority.facts
            if fact.observation_id == right.observation_id
        )
        self.assertEqual(retained.role, BoundaryRole.END)
        self.assertEqual(retained.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(retained.bases, ())

    def test_unique_source_wide_pair_retains_roles_across_leaf_alternative(
        self,
    ) -> None:
        observations = list(
            edge(f"edge:source-wide:{index}", coordinate)
            for index, coordinate in enumerate((10.0, 110.0, 130.0, 150.0, 250.0))
        )
        observations[1] = replace(
            observations[1],
            polarity=-1,
            qualified_anchor_roles=(BoundaryRole.END,),
        )
        observations[2] = replace(
            observations[2],
            polarity=1,
            qualified_anchor_roles=(BoundaryRole.END,),
        )
        observations[3] = replace(
            observations[3],
            polarity=1,
            qualified_anchor_roles=(BoundaryRole.END,),
        )
        authority = _separator_role_authority(
            tuple(observations),
            (
                separator(
                    "separator:local-alternative",
                    observations[1],
                    observations[3],
                    FiniteInterval(39.8, 40.2),
                    region_count=2,
                ),
                separator(
                    "separator:source-wide",
                    observations[1],
                    observations[2],
                    FiniteInterval(19.8, 20.2),
                ),
            ),
        )
        self.assertEqual(
            authority,
            {
                observations[1].observation_id: frozenset(
                    (BoundaryRole.END,)
                ),
                observations[2].observation_id: frozenset(
                    (BoundaryRole.START,)
                ),
            },
        )

    def test_local_separator_center_protects_only_its_weak_edge(self) -> None:
        observations = (
            replace(
                edge("material:outer-start", 10.0),
                qualified_anchor_roles=(BoundaryRole.START,),
            ),
            replace(
                edge("material:strong-end", 110.0),
                polarity=-1,
                qualified_anchor_roles=(BoundaryRole.END,),
            ),
            replace(
                edge("material:weak-start", 130.0, support_fraction=0.4),
                polarity=1,
                qualified_anchor_roles=(BoundaryRole.START,),
            ),
            replace(
                edge("material:outer-end", 230.0),
                polarity=-1,
                qualified_anchor_roles=(BoundaryRole.END,),
            ),
        )
        result = fit_template_phase(
            observations,
            template(2),
            separator_bands=(
                separator(
                    "material:local-band",
                    observations[1],
                    observations[2],
                    FiniteInterval(19.8, 20.0),
                    region_count=2,
                ),
            ),
        )

        self.assertEqual(result.status, PhaseFitStatus.RESOLVED)
        assert result.best is not None
        self.assertEqual(
            result.best.model_full_role_intervals_px[1],
            observations[1].full_position_interval_px,
        )
        self.assertLess(
            result.best.model_full_role_intervals_px[2].minimum,
            observations[2].full_position_interval_px.minimum,
        )


if __name__ == "__main__":
    unittest.main()
