from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.template_test_support import (
    cross_binding as binding,
    cross_template as template,
    phase_edge,
    phase_template,
)
from x5crop.domain import EvidenceState, FiniteInterval, ObservationId, PositiveInterval
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.source_geometry import SourceScanGeometry
from x5crop.detection.photo_geometry.template_aspect_ratio import (
    apply_inferred_aperture_height,
    consume_aperture_aspect_ratio_for_cross,
    derive_aperture_aspect_ratio_authority,
    reconcile_direct_aperture_height,
)
from x5crop.detection.photo_geometry.template_aspect_ratio_model import (
    ApertureAspectRatioFailureKind,
)
from x5crop.detection.photo_geometry.template_frame_width import (
    SourceFrameWidthAuthority,
    SourceFrameWidthAuthorityFailureKind,
)
from x5crop.detection.photo_geometry.template_model import (
    SourceFrameWidthAuthorityBasis,
)
from x5crop.detection.photo_geometry.template_cross import fit_template_cross
from x5crop.detection.photo_geometry.template_cross_model import (
    CrossEvidence,
    CrossFitStatus,
    TemplateCrossInput,
)
from x5crop.detection.photo_geometry.template_phase import fit_template_phase
from x5crop.detection.photo_geometry.template_selection import (
    select_lane_template_placement,
)
from x5crop.detection.gate_checks import GateGap, MinimumMissingFact
from x5crop.formats import ApertureAspectRatioSpec, FramePhysicalSpec


def _source(
    minimum_ratio: float,
    maximum_ratio: float,
    *,
    observed_width_px: FiniteInterval = FiniteInterval.exact(3600.0),
    design_height_mm: float = 24.0,
    width_observation_count: int = 4,
) -> SourceScanGeometry:
    frame = FramePhysicalSpec(
        36.0,
        design_height_mm,
        None,
        aperture_aspect_ratio=ApertureAspectRatioSpec(
            "test-gold-calibration",
            minimum_ratio,
            maximum_ratio,
            4,
            12,
        ),
    )
    source = SourceScanGeometry.create(
        frame,
        width_scale_px_per_mm=PositiveInterval.exact(100.0),
        height_scale_px_per_mm=PositiveInterval.exact(100.0),
    )
    width = source.width_state.intersect_observed_extent(
        observed_width_px,
        observation_ids=tuple(
            ObservationId(f"direct-width:{index}")
            for index in range(width_observation_count)
        ),
    )
    return SourceScanGeometry.from_axis_states(
        frame,
        width,
        source.height_state,
    )


def _source_width_authority(
    source: SourceScanGeometry,
    *,
    basis: SourceFrameWidthAuthorityBasis = (
        SourceFrameWidthAuthorityBasis.INDEPENDENT_COMPLETE_FRAMES
    ),
) -> SourceFrameWidthAuthority:
    observation_ids = source.width_state.observation_ids
    if not observation_ids:
        return SourceFrameWidthAuthority(
            authority_id="test-source-width-unavailable",
            state=EvidenceState.UNAVAILABLE,
            selected_integer_slot_offset=None,
            selected_phase_anchor_observation_ids=(),
            supporting_role_observation_ids=(),
            basis=None,
            supporting_frame_ordinals=(),
            supporting_constraint_ids=(),
            width_px=None,
            canonical_width_px=None,
            observation_ids=(),
            failure_kind=(
                SourceFrameWidthAuthorityFailureKind
                .SOURCE_WIDTH_CLOSURE_UNAVAILABLE
            ),
            reason="test source W is unavailable",
        )
    direct_lattice = (
        basis == SourceFrameWidthAuthorityBasis.DIRECT_LATTICE_CLOSURE
    )
    width = source.width_state.extent_projection_px()
    return SourceFrameWidthAuthority(
        authority_id=f"test-source-width:{basis.value}",
        state=EvidenceState.SUPPORTED,
        selected_integer_slot_offset=0,
        selected_phase_anchor_observation_ids=observation_ids,
        supporting_role_observation_ids=observation_ids,
        basis=basis,
        supporting_frame_ordinals=() if direct_lattice else (1, 2),
        supporting_constraint_ids=(
            tuple(f"constraint:{index}" for index in range(3))
            if direct_lattice
            else ()
        ),
        width_px=width,
        canonical_width_px=width.center,
        observation_ids=observation_ids,
        failure_kind=None,
        reason=None,
    )


def _derive(
    source: SourceScanGeometry,
    *,
    basis: SourceFrameWidthAuthorityBasis = (
        SourceFrameWidthAuthorityBasis.INDEPENDENT_COMPLETE_FRAMES
    ),
):
    return derive_aperture_aspect_ratio_authority(
        source,
        _source_width_authority(source, basis=basis),
    )


class TemplateAspectRatioContractTest(unittest.TestCase):
    def test_direct_width_derives_correlated_height_without_rank(self) -> None:
        source = _source(1.48, 1.52)

        authority = _derive(source)

        self.assertEqual(authority.state, EvidenceState.SUPPORTED)
        self.assertEqual(authority.scale_height_over_width, PositiveInterval.exact(1.0))
        self.assertEqual(authority.independent_constraint_rank, 0)
        self.assertEqual(len(authority.width_observation_ids), 4)
        raw = PositiveInterval(1.48, 1.52)
        self.assertEqual(authority.raw_width_over_height, raw)
        guarded = PositiveInterval(
            raw.minimum * (1.0 - 0.95 / 36.0) / (1.0 + 0.70 / 24.0),
            raw.maximum * (1.0 + 0.95 / 36.0) / (1.0 - 0.70 / 24.0),
        )
        self.assertEqual(authority.guarded_width_over_height, guarded)
        self.assertEqual(
            authority.inferred_height_px,
            FiniteInterval(
                3600.0 / guarded.maximum,
                3600.0 / guarded.minimum,
            ),
        )
        self.assertEqual(
            authority.effective_height_px,
            FiniteInterval(2330.0, 2470.0),
        )

        consumed = consume_aperture_aspect_ratio_for_cross(authority)
        narrowed = apply_inferred_aperture_height(source, consumed)
        self.assertEqual(
            narrowed.height_state.extent_projection_px(),
            authority.effective_height_px,
        )
        self.assertEqual(narrowed.height_state.observation_ids, ())

    def test_direct_lattice_width_derives_the_same_rank_zero_height(self) -> None:
        source = _source(
            1.48,
            1.52,
            width_observation_count=3,
        )

        authority = _derive(
            source,
            basis=SourceFrameWidthAuthorityBasis.DIRECT_LATTICE_CLOSURE,
        )

        self.assertEqual(authority.state, EvidenceState.SUPPORTED)
        self.assertEqual(len(authority.width_observation_ids), 3)
        self.assertEqual(authority.independent_constraint_rank, 0)
        self.assertEqual(
            authority.source_width_px,
            source.width_state.extent_projection_px(),
        )

    def test_missing_calibration_or_direct_width_is_typed_unavailable(self) -> None:
        frame = FramePhysicalSpec(20.0, 10.0, None)
        uncalibrated = SourceScanGeometry.create(
            frame,
            width_scale_px_per_mm=PositiveInterval.exact(100.0),
            height_scale_px_per_mm=PositiveInterval.exact(100.0),
        )
        without_width = SourceScanGeometry.create(
            _source(1.48, 1.52).frame_spec,
            width_scale_px_per_mm=PositiveInterval.exact(100.0),
            height_scale_px_per_mm=PositiveInterval.exact(100.0),
        )

        for source in (uncalibrated, without_width):
            authority = _derive(source)
            self.assertEqual(authority.state, EvidenceState.UNAVAILABLE)
            self.assertEqual(
                authority.failure_kind,
                ApertureAspectRatioFailureKind.AUTHORITY_UNAVAILABLE,
            )

    def test_ratio_uncertainty_that_spends_five_percent_is_typed(self) -> None:
        authority = _derive(
            _source(4.0, 5.0, design_height_mm=8.0)
        )

        self.assertEqual(authority.state, EvidenceState.CONTRADICTED)
        self.assertEqual(
            authority.failure_kind,
            ApertureAspectRatioFailureKind.BUDGET_EXHAUSTED,
        )
        self.assertGreater(
            authority.minimum_output_expansion_mm,
            authority.output_expansion_limit_mm,
        )
        direct = reconcile_direct_aperture_height(
            authority,
            FiniteInterval(790.0, 810.0),
        )
        self.assertEqual(direct.direct_height_px, FiniteInterval(790.0, 810.0))
        self.assertFalse(direct.blocks_cross_resolution)

    def test_ratio_that_misses_height_prior_has_its_own_typed_failure(self) -> None:
        authority = _derive(
            _source(10.0, 12.0)
        )

        self.assertEqual(authority.state, EvidenceState.CONTRADICTED)
        self.assertEqual(
            authority.failure_kind,
            ApertureAspectRatioFailureKind.PHYSICAL_PRIOR_CONFLICT,
        )
        self.assertIsNone(authority.effective_height_px)

    def test_direct_height_keeps_native_authority_or_reports_conflict(self) -> None:
        authority = _derive(_source(1.48, 1.52))
        compatible = reconcile_direct_aperture_height(
            authority,
            FiniteInterval(2398.0, 2402.0),
        )
        conflict = reconcile_direct_aperture_height(
            authority,
            FiniteInterval(2600.0, 2610.0),
        )

        self.assertEqual(compatible.state, EvidenceState.SUPPORTED)
        self.assertEqual(
            compatible.direct_height_px,
            FiniteInterval(2398.0, 2402.0),
        )
        self.assertFalse(compatible.consumed_for_cross_inference)
        self.assertEqual(conflict.state, EvidenceState.CONTRADICTED)
        self.assertEqual(
            conflict.failure_kind,
            ApertureAspectRatioFailureKind.DIRECT_CONFLICT,
        )
        self.assertTrue(conflict.blocks_cross_resolution)

    def test_cross_truth_table_preserves_direct_h_and_requires_ratio_for_inference(
        self,
    ) -> None:
        unavailable = _derive(
            SourceScanGeometry.create(
                FramePhysicalSpec(20.0, 10.0, None),
                width_scale_px_per_mm=PositiveInterval.exact(100.0),
                height_scale_px_per_mm=PositiveInterval.exact(100.0),
            )
        )
        direct = fit_template_cross(
            TemplateCrossInput(
                template=template(),
                fixed_height_px=FiniteInterval(238.0, 242.0),
                top_bindings=(binding(BoundaryRole.TOP, "direct-top", 100.0),),
                bottom_bindings=(
                    binding(BoundaryRole.BOTTOM, "direct-bottom", 340.0),
                ),
                aperture_aspect_ratio_authority=unavailable,
            )
        )
        missing = fit_template_cross(
            TemplateCrossInput(
                template=template(),
                fixed_height_px=FiniteInterval(238.0, 242.0),
                top_bindings=(binding(BoundaryRole.TOP, "single-top", 100.0),),
                aperture_aspect_ratio_authority=unavailable,
            )
        )

        self.assertEqual(direct.status, CrossFitStatus.RESOLVED)
        self.assertTrue(direct.best.direct_pair)
        self.assertEqual(missing.status, CrossFitStatus.UNRESOLVED)
        self.assertTrue(
            missing.aperture_aspect_ratio_authority.blocks_cross_resolution
        )

    def test_one_side_consumes_full_ratio_height_interval(self) -> None:
        authority = _derive(_source(1.48, 1.52))
        scaled = replace(
            authority,
            inferred_height_px=FiniteInterval(238.0, 242.0),
            effective_height_px=FiniteInterval(238.0, 242.0),
            canonical_height_px=240.0,
        )
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(),
                fixed_height_px=FiniteInterval(230.0, 250.0),
                canonical_fixed_height_px=240.0,
                top_bindings=(binding(BoundaryRole.TOP, "ratio-top", 100.0),),
                aperture_aspect_ratio_authority=scaled,
            )
        )

        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        self.assertTrue(
            result.aperture_aspect_ratio_authority.consumed_for_cross_inference
        )
        self.assertEqual(
            result.best.inferred_bindings[0].evidence,
            CrossEvidence.ASPECT_RATIO_HEIGHT_INFERRED,
        )
        self.assertEqual(
            result.best.bottom_full_interval_px,
            FiniteInterval(338.0, 342.0),
        )

    def test_unique_direct_h_conflict_with_ratio_refuses_resolution(self) -> None:
        authority = _derive(_source(1.48, 1.52))
        scaled = replace(
            authority,
            inferred_height_px=FiniteInterval(238.0, 242.0),
            effective_height_px=FiniteInterval(238.0, 242.0),
            canonical_height_px=240.0,
        )
        result = fit_template_cross(
            TemplateCrossInput(
                template=template(),
                fixed_height_px=FiniteInterval(240.0, 260.0),
                canonical_fixed_height_px=250.0,
                top_bindings=(binding(BoundaryRole.TOP, "conflict-top", 100.0),),
                bottom_bindings=(
                    binding(BoundaryRole.BOTTOM, "conflict-bottom", 350.0),
                ),
                aperture_aspect_ratio_authority=scaled,
            )
        )

        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertEqual(
            result.aperture_aspect_ratio_authority.failure_kind,
            ApertureAspectRatioFailureKind.DIRECT_CONFLICT,
        )
        self.assertTrue(
            result.aperture_aspect_ratio_authority.blocks_cross_resolution
        )
        phase = fit_template_phase(
            (
                phase_edge("direct-conflict-start", 40.0),
                phase_edge("direct-conflict-end", 140.0),
            ),
            phase_template(1),
        )
        competition = select_lane_template_placement(
            lane_id="lane:0",
            best=None,
            runner_up=None,
            phase=phase,
            cross=result,
            content_assessment=None,
        )
        self.assertEqual(
            competition.failure.gap,
            GateGap.APERTURE_ASPECT_RATIO_DIRECT_CONFLICT,
        )

    def test_required_missing_ratio_reaches_the_typed_gate_failure(self) -> None:
        unavailable = _derive(
            SourceScanGeometry.create(
                FramePhysicalSpec(20.0, 10.0, None),
                width_scale_px_per_mm=PositiveInterval.exact(100.0),
                height_scale_px_per_mm=PositiveInterval.exact(100.0),
            )
        )
        cross = fit_template_cross(
            TemplateCrossInput(
                template=template(),
                fixed_height_px=FiniteInterval(238.0, 242.0),
                top_bindings=(binding(BoundaryRole.TOP, "missing-ratio", 100.0),),
                aperture_aspect_ratio_authority=unavailable,
            )
        )
        phase = fit_template_phase(
            (
                phase_edge("gate-start", 40.0),
                phase_edge("gate-end", 140.0),
            ),
            phase_template(1),
        )
        competition = select_lane_template_placement(
            lane_id="lane:0",
            best=None,
            runner_up=None,
            phase=phase,
            cross=cross,
            content_assessment=None,
        )

        self.assertEqual(
            competition.failure.gap,
            GateGap.APERTURE_ASPECT_RATIO_AUTHORITY_UNAVAILABLE,
        )
        self.assertEqual(
            competition.failure.minimum_missing_fact,
            MinimumMissingFact.APERTURE_ASPECT_RATIO_AUTHORITY,
        )

    def test_required_ratio_failures_keep_distinct_gate_roots(self) -> None:
        phase = fit_template_phase(
            (
                phase_edge("typed-gate-start", 40.0),
                phase_edge("typed-gate-end", 140.0),
            ),
            phase_template(1),
        )
        cases = (
            (
                _derive(_source(10.0, 12.0)),
                GateGap.APERTURE_ASPECT_RATIO_PHYSICAL_PRIOR_CONFLICT,
            ),
            (
                _derive(
                    _source(4.0, 5.0, design_height_mm=8.0)
                ),
                GateGap.APERTURE_ASPECT_RATIO_BUDGET_EXHAUSTED,
            ),
        )

        for authority, expected_gap in cases:
            with self.subTest(expected_gap=expected_gap):
                cross = fit_template_cross(
                    TemplateCrossInput(
                        template=template(),
                        fixed_height_px=FiniteInterval(238.0, 242.0),
                        top_bindings=(
                            binding(BoundaryRole.TOP, "typed-gate", 100.0),
                        ),
                        aperture_aspect_ratio_authority=authority,
                    )
                )
                competition = select_lane_template_placement(
                    lane_id="lane:0",
                    best=None,
                    runner_up=None,
                    phase=phase,
                    cross=cross,
                    content_assessment=None,
                )

                self.assertEqual(competition.failure.gap, expected_gap)


if __name__ == "__main__":
    unittest.main()
