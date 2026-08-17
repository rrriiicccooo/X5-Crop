from __future__ import annotations

from dataclasses import replace
import unittest

from x5crop.detection.photo_geometry.observation_types import (
    BoundaryEdgeObservation,
    SeparatorBandObservation,
    SeparatorMaterialRegionObservation,
)
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.template_model import (
    PhaseLatticeAuthority,
    TemplateSpec,
)
from x5crop.detection.photo_geometry.template_phase import fit_template_phase
from x5crop.detection.photo_geometry.template_pitch import (
    calibrate_template_source_pitch,
)
from x5crop.domain import FiniteInterval, ObservationId


def edge(name: str, coordinate: float) -> BoundaryEdgeObservation:
    interval = FiniteInterval(coordinate - 1.0, coordinate + 1.0)
    return BoundaryEdgeObservation(
        observation_id=ObservationId(name),
        run_id=f"run:{name}",
        discovery_interval_px=interval,
        reference_trace_px=10.0,
        canonical_position_px=coordinate,
        fit_position_interval_px=interval,
        full_position_interval_px=interval,
        transition_ids=(ObservationId(f"transition:{name}"),),
        trace_coordinates_px=(0, 10, 20),
        polarity=1,
        support_fraction=1.0,
        continuous_support_fraction=1.0,
        fit_residual_px=0.0,
        canonical_direction_degrees=None,
        fit_direction_interval_degrees=None,
        full_direction_interval_degrees=None,
        qualified_anchor_roles=(BoundaryRole.START,),
    )


def template() -> TemplateSpec:
    return TemplateSpec(
        template_id="pitch-template",
        frame_width_px=FiniteInterval(98.0, 102.0),
        pitch_px=FiniteInterval(118.0, 126.0),
        nominal_gap_px=FiniteInterval(18.0, 24.0),
        count=3,
        phase_lattice_authority=PhaseLatticeAuthority(
            period_px=FiniteInterval(118.0, 126.0),
            cycle_origin_px=0.0,
            minimum_slot_offset=-1,
            maximum_slot_offset=20,
        ),
    )


def separator(
    name: str,
    left: BoundaryEdgeObservation,
    right: BoundaryEdgeObservation,
) -> SeparatorBandObservation:
    material = tuple(
        SeparatorMaterialRegionObservation(
            region_index=index,
            sample_count=3,
            darkness_contrast_interval=FiniteInterval(1.0, 2.0),
            texture_contrast_interval=FiniteInterval(0.5, 1.0),
        )
        for index in range(3)
    )
    return SeparatorBandObservation(
        observation_id=ObservationId(name),
        left_edge_observation_id=left.observation_id,
        right_edge_observation_id=right.observation_id,
        left_run_id=left.run_id,
        right_run_id=right.run_id,
        gap_interval_px=FiniteInterval(
            right.fit_position_interval_px.minimum
            - left.fit_position_interval_px.maximum,
            right.fit_position_interval_px.maximum
            - left.fit_position_interval_px.minimum,
        ),
        transition_ids=(
            ObservationId(f"transition:{name}:left"),
            ObservationId(f"transition:{name}:right"),
        ),
        independent_support_region_count=3,
        continuous_support_fraction=1.0,
        darkness_contrast=1.5,
        darkness_contrast_interval=FiniteInterval(1.0, 2.0),
        texture_contrast=0.75,
        texture_contrast_interval=FiniteInterval(0.5, 1.0),
        material_regions=material,
    )


class TemplatePitchContractTest(unittest.TestCase):
    def test_two_adjacent_same_role_advances_authorize_source_pitch(self) -> None:
        observations = (edge("start:1", 40.0), edge("start:2", 160.0), edge("start:3", 280.0))
        phase = fit_template_phase(observations, template())
        calibrated = calibrate_template_source_pitch(
            template(),
            phase,
            observations,
        )
        self.assertEqual(calibrated.template.pitch_px.minimum, 118.0)
        self.assertEqual(calibrated.template.pitch_px.maximum, 122.0)
        self.assertEqual(
            calibrated.template.phase_lattice_authority.period_px,
            calibrated.template.pitch_px,
        )
        self.assertEqual(
            calibrated.template.gap_prior_px,
            FiniteInterval(16.0, 24.0),
        )

    def test_one_advance_or_discrete_advances_do_not_rewrite_prior(self) -> None:
        compiled = template()
        two = (edge("two:1", 40.0), edge("two:2", 160.0))
        phase = fit_template_phase(two, compiled)
        self.assertIs(
            calibrate_template_source_pitch(compiled, phase, two).template,
            compiled,
        )

    def test_two_direct_separator_locations_calibrate_missing_later_roles(self) -> None:
        compiled = template()
        phase_edges = (edge("phase:1", 40.0), edge("phase:2", 160.0))
        phase = fit_template_phase(phase_edges, compiled)
        band_edges = (
            edge("band:1:left", 144.0),
            edge("band:1:right", 156.0),
            edge("band:2:left", 260.0),
            edge("band:2:right", 272.0),
        )
        bands = (
            separator("separator:1", band_edges[0], band_edges[1]),
            separator("separator:2", band_edges[2], band_edges[3]),
        )
        calibrated = calibrate_template_source_pitch(
            compiled,
            phase,
            (*phase_edges, *band_edges),
            bands,
        )
        self.assertEqual(calibrated.template.pitch_px.minimum, 114.0)
        self.assertEqual(calibrated.template.pitch_px.maximum, 118.0)
        self.assertEqual(
            calibrated.template.gap_prior_px,
            FiniteInterval(12.0, 20.0),
        )
        self.assertIsNotNone(calibrated.phase_authority_px)
        self.assertEqual(
            calibrated.direct_separator_ids,
            (ObservationId("separator:1"), ObservationId("separator:2")),
        )

    def test_separator_pitch_ignores_off_corridor_material(self) -> None:
        compiled = template()
        phase_edges = (edge("phase:near:1", 40.0), edge("phase:near:2", 160.0))
        phase = fit_template_phase(phase_edges, compiled)
        band_edges = (
            edge("near:1:left", 144.0),
            edge("near:1:right", 156.0),
            edge("near:2:left", 260.0),
            edge("near:2:right", 272.0),
            edge("far:left", 998.0),
            edge("far:right", 1010.0),
        )
        bands = (
            separator("separator:near:1", band_edges[0], band_edges[1]),
            separator("separator:near:2", band_edges[2], band_edges[3]),
            separator("separator:far", band_edges[4], band_edges[5]),
        )
        calibrated = calibrate_template_source_pitch(
            compiled,
            phase,
            (*phase_edges, *band_edges),
            bands,
        )
        self.assertEqual(calibrated.template.pitch_px.minimum, 114.0)
        self.assertEqual(calibrated.template.pitch_px.maximum, 118.0)

    def test_holder_containment_selects_one_unlabelled_separator_lattice(
        self,
    ) -> None:
        compiled = TemplateSpec(
            template_id="holder-lattice",
            frame_width_px=FiniteInterval(98.0, 102.0),
            pitch_px=FiniteInterval(118.0, 132.0),
            nominal_gap_px=FiniteInterval(16.0, 34.0),
            count=3,
            phase_lattice_authority=PhaseLatticeAuthority(
                period_px=FiniteInterval(118.0, 132.0),
                cycle_origin_px=0.0,
                minimum_slot_offset=-1,
                maximum_slot_offset=3,
            ),
        )
        phase_edges = (edge("holder:phase:1", 40.0), edge("holder:phase:2", 160.0))
        phase = fit_template_phase(phase_edges, compiled)
        band_edges = (
            edge("holder:false:left", 15.0),
            edge("holder:false:right", 25.0),
            edge("holder:true:1:left", 144.0),
            edge("holder:true:1:right", 156.0),
            edge("holder:true:2:left", 264.0),
            edge("holder:true:2:right", 276.0),
        )
        bands = (
            separator("separator:holder:false", band_edges[0], band_edges[1]),
            separator("separator:holder:true:1", band_edges[2], band_edges[3]),
            separator("separator:holder:true:2", band_edges[4], band_edges[5]),
        )

        ambiguous = calibrate_template_source_pitch(
            compiled,
            phase,
            (*phase_edges, *band_edges),
            bands,
        )
        self.assertIs(ambiguous.template, compiled)
        self.assertIsNone(ambiguous.phase_authority_px)

        calibrated = calibrate_template_source_pitch(
            compiled,
            phase,
            (*phase_edges, *band_edges),
            bands,
            holder_span_px=FiniteInterval(0.0, 400.0),
        )
        self.assertEqual(calibrated.template.pitch_px.minimum, 118.0)
        self.assertEqual(calibrated.template.pitch_px.maximum, 122.0)
        self.assertIsNotNone(calibrated.phase_authority_px)
        assert calibrated.phase_authority_px is not None
        self.assertTrue(calibrated.phase_authority_px.contains(40.0))
        self.assertEqual(
            calibrated.direct_separator_ids,
            (
                ObservationId("separator:holder:true:1"),
                ObservationId("separator:holder:true:2"),
            ),
        )

    def test_one_or_discretely_ambiguous_separator_does_not_calibrate(self) -> None:
        compiled = template()
        phase_edges = (edge("phase:ambiguous:1", 40.0), edge("phase:ambiguous:2", 160.0))
        phase = fit_template_phase(phase_edges, compiled)
        one_edges = (edge("one:left", 144.0), edge("one:right", 156.0))
        one_band = (separator("separator:one", *one_edges),)
        self.assertIs(
            calibrate_template_source_pitch(
                compiled,
                phase,
                (*phase_edges, *one_edges),
                one_band,
            ).template,
            compiled,
        )

        ambiguous_edges = (
            edge("ambiguous:left:1", 139.0),
            edge("ambiguous:right:1", 149.0),
            edge("ambiguous:left:2", 151.0),
            edge("ambiguous:right:2", 161.0),
            edge("ambiguous:second:left", 264.0),
            edge("ambiguous:second:right", 276.0),
        )
        ambiguous_bands = (
            separator("separator:ambiguous:1", ambiguous_edges[0], ambiguous_edges[1]),
            separator("separator:ambiguous:2", ambiguous_edges[2], ambiguous_edges[3]),
            separator("separator:ambiguous:second", ambiguous_edges[4], ambiguous_edges[5]),
        )
        self.assertIs(
            calibrate_template_source_pitch(
                compiled,
                phase,
                (*phase_edges, *ambiguous_edges),
                ambiguous_bands,
            ).template,
            compiled,
        )

    def test_separator_lattice_bound_overflow_is_explicit(self) -> None:
        compiled = replace(template(), count=4)
        phase_edges = (
            edge("bound:phase:1", 40.0),
            edge("bound:phase:2", 160.0),
        )
        phase = fit_template_phase(phase_edges, compiled)
        band_edges = tuple(
            edge(f"bound:band:{index}", coordinate)
            for index, coordinate in enumerate(
                (144.0, 156.0, 264.0, 276.0, 384.0, 396.0)
            )
        )
        bands = tuple(
            separator(
                f"separator:bound:{index}",
                band_edges[2 * index],
                band_edges[2 * index + 1],
            )
            for index in range(3)
        )
        calibration = calibrate_template_source_pitch(
            compiled,
            phase,
            (*phase_edges, *band_edges),
            bands,
            max_lattice_hypotheses=1,
        )
        self.assertTrue(calibration.bound_exceeded)
        self.assertIs(calibration.template, compiled)
        self.assertIsNone(calibration.phase_authority_px)
        self.assertEqual(calibration.direct_separator_ids, ())
        self.assertGreater(calibration.lattice_hypothesis_count, 1)

    def test_impossible_holder_mapping_stays_unresolved_without_bad_interval(self) -> None:
        compiled = template()
        phase_edges = (
            edge("small-holder:phase:1", 40.0),
            edge("small-holder:phase:2", 160.0),
        )
        phase = fit_template_phase(phase_edges, compiled)
        band_edges = (
            edge("small-holder:band:1:left", 144.0),
            edge("small-holder:band:1:right", 156.0),
            edge("small-holder:band:2:left", 264.0),
            edge("small-holder:band:2:right", 276.0),
        )
        bands = (
            separator("small-holder:separator:1", *band_edges[:2]),
            separator("small-holder:separator:2", *band_edges[2:]),
        )
        calibration = calibrate_template_source_pitch(
            compiled,
            phase,
            (*phase_edges, *band_edges),
            bands,
            holder_span_px=FiniteInterval(0.0, 100.0),
        )
        self.assertFalse(calibration.bound_exceeded)
        self.assertIs(calibration.template, compiled)
        self.assertIsNone(calibration.phase_authority_px)


if __name__ == "__main__":
    unittest.main()
