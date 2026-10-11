from __future__ import annotations

from dataclasses import replace
import unittest
from unittest.mock import patch

import numpy as np

from tools.tests.template_test_support import (
    calibrated_nominal_grid_prior,
    phase_sequence_measurement,
)

from x5crop.detection.photo_geometry.observation_types import (
    BoundaryEdgeMeasurementBasis,
    BoundaryEdgeObservation,
    SeparatorBandObservation,
    SeparatorBandMeasurementBasis,
    SeparatorMaterialPolarity,
    SeparatorMaterialRegionObservation,
    SeparatorMaterialRegionState,
)
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.template_model import (
    PhaseLatticeAuthority,
    TemplateSpec,
)
from x5crop.detection.photo_geometry.template_phase import fit_template_phase
from x5crop.detection.photo_geometry.template_pitch import (
    calibrate_template_source_pitch,
    close_separator_phase_hypothesis,
    resolve_separator_pitch_hypothesis,
    TemplatePitchCalibration,
)
from x5crop.detection.photo_geometry.template_phase_model import (
    PhaseFailureKind,
    PhaseFitStatus,
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
        measurement_basis=BoundaryEdgeMeasurementBasis.DIRECT_TRACE,
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
            material_contrast_interval=FiniteInterval(2.0, 3.0),
            core_texture_interval=FiniteInterval(0.5, 0.75),
            state=SeparatorMaterialRegionState.SUPPORTED,
        )
        for index in range(3)
    )
    return SeparatorBandObservation(
        observation_id=ObservationId(name),
        left_edge_observation_id=left.observation_id,
        right_edge_observation_id=right.observation_id,
        left_run_id=left.run_id,
        right_run_id=right.run_id,
        measurement_basis=SeparatorBandMeasurementBasis.DIRECT_TRACE,
        material_polarity=SeparatorMaterialPolarity.DARK,
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
        material_support_region_count=3,
        continuous_support_fraction=1.0,
        material_contrast=2.5,
        material_contrast_interval=FiniteInterval(2.0, 3.0),
        core_texture=0.625,
        core_texture_interval=FiniteInterval(0.5, 0.75),
        material_regions=material,
    )


class TemplatePitchContractTest(unittest.TestCase):
    def test_lane_preserves_phase_producer_bounds_without_retry(self) -> None:
        from tools.tests.photo_geometry_support import make_native_test_field
        from tools.tests.template_runtime_test_support import runtime_lane
        from x5crop.configuration.registry import get_detection_configuration
        from x5crop.detection.photo_geometry.lane_preparation import prepare_template_lane

        owner = "x5crop.detection.photo_geometry.lane_preparation."
        fits = []

        def measured_fit(observations, compiled, **kwargs):
            phase = fit_template_phase(observations, compiled, **kwargs)
            if len(fits) + 1 == bound_pass:
                phase = replace(
                    phase, status=PhaseFitStatus.BOUND_EXCEEDED,
                    best=None, runner_up=None, winner_basis=None,
                    failure_kind=PhaseFailureKind.HYPOTHESIS_BOUND_EXCEEDED,
                    ambiguity_reason=f"phase pass {bound_pass} producer bound exceeded",
                    best_phase_candidate_authority_projection=None,
                    runner_phase_candidate_authority_projection=None,
                )
            fits.append(phase)
            return phase

        def proposed_pitch(compiled, *args, **kwargs):
            return TemplatePitchCalibration(
                compiled, None, FiniteInterval(40.0, 41.0),
                (ObservationId("separator:1"), ObservationId("separator:2")),
                (), 1, False,
            )

        for bound_pass in (1, 2, 3):
            with self.subTest(bound_pass=bound_pass):
                fits.clear()
                with (
                    patch(owner + "fit_template_phase", side_effect=measured_fit) as fit,
                    patch(owner + "calibrate_template_source_pitch", side_effect=proposed_pitch) as calibrate,
                    patch(owner + "fit_template_phase_candidate_with_adjacency_relations") as retry,
                ):
                    prepared = prepare_template_lane(
                        make_native_test_field(np.zeros((322, 2320), dtype=np.uint8), "horizontal"),
                        runtime_lane(), layout="horizontal", output_slot_count=3,
                        measurement_slot_count=6, configuration=get_detection_configuration("135"),
                    )
                self.assertEqual(fit.call_count, bound_pass)
                if bound_pass == 1:
                    calibrate.assert_not_called()
                retry.assert_not_called()
                phase = prepared.phase_competition
                self.assertEqual(phase.status, PhaseFitStatus.BOUND_EXCEEDED)
                self.assertEqual(phase.failure_kind, PhaseFailureKind.HYPOTHESIS_BOUND_EXCEEDED)
                self.assertEqual(phase.ambiguity_reason, fits[-1].ambiguity_reason)
                self.assertIsNone(phase.best)
                self.assertIsNone(phase.runner_up)
                self.assertIsNone(phase.winner_basis)
                self.assertEqual(phase.receipt.phase_hypothesis_count,
                    sum(item.receipt.phase_hypothesis_count for item in fits))
                self.assertEqual(phase.receipt.fit_pass_count,
                    sum(item.receipt.fit_pass_count for item in fits))

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

    def test_two_separator_locations_narrow_pitch_without_owning_phase(self) -> None:
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
        self.assertIsNone(calibrated.phase_authority_px)
        self.assertIsNotNone(calibrated.phase_hypothesis_px)
        self.assertEqual(
            calibrated.direct_separator_ids,
            (ObservationId("separator:1"), ObservationId("separator:2")),
        )
        assert calibrated.phase_hypothesis_px is not None
        raw_independent = fit_template_phase(
            (phase_edges[0], *band_edges),
            calibrated.template,
            separator_bands=bands,
            phase_authority_px=calibrated.phase_hypothesis_px,
        )
        self.assertEqual(raw_independent.status, PhaseFitStatus.RESOLVED)
        self.assertIsNone(close_separator_phase_hypothesis(calibrated, raw_independent))
        measurements = (
            phase_sequence_measurement("pitch-closure", FiniteInterval(0.0, 400.0)),
        )
        prior = calibrated_nominal_grid_prior(calibrated.template)
        independently_closed = fit_template_phase(
            (phase_edges[0], *band_edges),
            calibrated.template,
            separator_bands=bands,
            phase_authority_px=calibrated.phase_hypothesis_px,
            sequence_measurement_sets=measurements,
            calibrated_nominal_grid_prior=prior,
        )
        self.assertEqual(
            close_separator_phase_hypothesis(
                calibrated,
                independently_closed,
            ),
            calibrated.phase_hypothesis_px,
        )
        weak_independent = fit_template_phase(
            (
                replace(
                    phase_edges[0],
                    trace_coordinates_px=(0, 10),
                    support_fraction=2.0 / 3.0,
                    continuous_support_fraction=2.0 / 3.0,
                ),
                *band_edges,
            ),
            calibrated.template,
            separator_bands=bands,
            phase_authority_px=calibrated.phase_hypothesis_px,
            sequence_measurement_sets=measurements,
            calibrated_nominal_grid_prior=prior,
        )
        self.assertIsNone(close_separator_phase_hypothesis(calibrated, weak_independent))
        weak_withheld = resolve_separator_pitch_hypothesis(
            calibrated, weak_independent, original_template=compiled
        )
        self.assertTrue(weak_withheld.pitch_hypothesis_withheld)
        self.assertIs(weak_withheld.template, compiled)
        lattice_self_fit = fit_template_phase(
            band_edges,
            calibrated.template,
            separator_bands=bands,
            phase_authority_px=calibrated.phase_hypothesis_px,
            sequence_measurement_sets=measurements,
            calibrated_nominal_grid_prior=prior,
        )
        self.assertEqual(lattice_self_fit.status, PhaseFitStatus.RESOLVED)
        self.assertIsNone(
            close_separator_phase_hypothesis(calibrated, lattice_self_fit)
        )
        withheld = resolve_separator_pitch_hypothesis(
            calibrated, lattice_self_fit, original_template=compiled)
        self.assertIs(withheld.template, compiled)
        self.assertTrue(withheld.pitch_hypothesis_withheld)
        self.assertEqual(withheld.pitch_observation_ids, ())
        self.assertEqual(withheld.direct_separator_ids, calibrated.direct_separator_ids)
        self.assertEqual(withheld.phase_hypothesis_px, calibrated.phase_hypothesis_px)
        self.assertIsNone(close_separator_phase_hypothesis(withheld, independently_closed))
        self.assertIs(resolve_separator_pitch_hypothesis(
            calibrated, independently_closed, original_template=compiled), calibrated)
        bounded = replace(lattice_self_fit, status=PhaseFitStatus.BOUND_EXCEEDED,
            best=None, runner_up=None, winner_basis=None,
            failure_kind=PhaseFailureKind.HYPOTHESIS_BOUND_EXCEEDED,
            ambiguity_reason="producer bound exceeded",
            best_phase_candidate_authority_projection=None,
            runner_phase_candidate_authority_projection=None)
        self.assertIs(resolve_separator_pitch_hypothesis(
            calibrated, bounded, original_template=compiled), calibrated)
        with self.assertRaisesRegex(ValueError, "template identity"):
            resolve_separator_pitch_hypothesis(calibrated, lattice_self_fit,
                original_template=replace(compiled, template_id="another-template"))
        incompatible = replace(
            calibrated,
            phase_hypothesis_px=FiniteInterval(1_000.0, 1_010.0),
        )
        independently_resolved = fit_template_phase(
            (phase_edges[0], *band_edges),
            calibrated.template,
            separator_bands=bands,
        )
        self.assertIsNone(
            close_separator_phase_hypothesis(
                incompatible,
                independently_resolved,
            )
        )

    def test_three_separator_locations_close_absolute_phase(self) -> None:
        compiled = replace(template(), count=4)
        phase_edges = (edge("phase:1", 40.0), edge("phase:2", 160.0))
        phase = fit_template_phase(phase_edges, compiled)
        band_edges = (
            edge("band:1:left", 144.0),
            edge("band:1:right", 156.0),
            edge("band:2:left", 264.0),
            edge("band:2:right", 276.0),
            edge("band:3:left", 384.0),
            edge("band:3:right", 396.0),
        )
        bands = (
            separator("separator:1", band_edges[0], band_edges[1]),
            separator("separator:2", band_edges[2], band_edges[3]),
            separator("separator:3", band_edges[4], band_edges[5]),
        )

        calibrated = calibrate_template_source_pitch(
            compiled,
            phase,
            (*phase_edges, *band_edges),
            bands,
            holder_span_px=FiniteInterval(0.0, 520.0),
        )

        self.assertIsNotNone(calibrated.phase_authority_px)
        self.assertIsNone(calibrated.phase_hypothesis_px)
        self.assertEqual(
            calibrated.direct_separator_ids,
            (
                ObservationId("separator:1"),
                ObservationId("separator:2"),
                ObservationId("separator:3"),
            ),
        )

    def test_two_distant_separators_in_long_strip_do_not_own_absolute_phase(
        self,
    ) -> None:
        compiled = replace(template(), count=6)
        phase_edges = (
            edge("long:phase:start", 40.0),
            edge("long:phase:end", 640.0),
        )
        phase = fit_template_phase(phase_edges, compiled)
        band_edges = (
            edge("long:band:1:left", 144.0),
            edge("long:band:1:right", 156.0),
            edge("long:band:4:left", 510.0),
            edge("long:band:4:right", 522.0),
        )
        bands = (
            separator("long:separator:1", band_edges[0], band_edges[1]),
            separator("long:separator:4", band_edges[2], band_edges[3]),
        )

        calibrated = calibrate_template_source_pitch(
            compiled,
            phase,
            (*phase_edges, *band_edges),
            bands,
            holder_span_px=FiniteInterval(0.0, 800.0),
        )

        self.assertFalse(calibrated.bound_exceeded)
        self.assertIsNone(calibrated.phase_authority_px)
        self.assertIsNone(calibrated.phase_hypothesis_px)
        self.assertEqual(calibrated.direct_separator_ids, ())
        self.assertGreater(calibrated.lattice_hypothesis_count, 0)

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
        self.assertIsNone(ambiguous.phase_hypothesis_px)

        calibrated = calibrate_template_source_pitch(
            compiled,
            phase,
            (*phase_edges, *band_edges),
            bands,
            holder_span_px=FiniteInterval(0.0, 400.0),
        )
        self.assertEqual(calibrated.template.pitch_px.minimum, 118.0)
        self.assertEqual(calibrated.template.pitch_px.maximum, 122.0)
        self.assertIsNone(calibrated.phase_authority_px)
        self.assertIsNotNone(calibrated.phase_hypothesis_px)
        self.assertEqual(
            calibrated.direct_separator_ids,
            (
                ObservationId("separator:holder:true:1"),
                ObservationId("separator:holder:true:2"),
            ),
        )
        rebound = fit_template_phase(
            (*phase_edges, *band_edges),
            calibrated.template,
            separator_bands=bands,
            holder_span_px=FiniteInterval(0.0, 400.0),
        )
        self.assertIsNotNone(rebound.best)

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
