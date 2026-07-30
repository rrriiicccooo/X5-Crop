from __future__ import annotations

from dataclasses import fields, replace
from pathlib import Path
import tempfile
import unittest

import numpy as np

from tools.regression.safe_crop_acceptance import (
    AcceptancePreflightError,
    RESULT_FIELDS,
    RESULT_SCHEMA,
    SUMMARY_FIELDS,
    SUMMARY_SCHEMA,
    _validate_output_root,
    validate_acceptance_result_record,
    validate_acceptance_summary_record,
)
from x5crop.cache import MeasurementCache, MeasurementCacheKey
from x5crop.configuration.grid import frame_grid_search_prior
from x5crop.configuration.model import FrameCountMode
from x5crop.configuration.registry import get_detection_configuration
from x5crop.detection.candidate.assessment.candidate_gate import (
    candidate_gate_assessment,
)
from x5crop.detection.decision.decision_gate import apply_decision_gate
from x5crop.detection.decision.vocabulary import (
    FINAL_REASON_AUTOMATIC_COUNT_UNRESOLVED,
    FINAL_REASON_SLOT_OWNERSHIP_UNBOUNDED,
)
from x5crop.detection.grid.model import (
    G_MAX,
    K_MAX,
    O_MAX,
    P_MAX,
    DominanceDimensionRelation,
    DominanceRelation,
    FrameSlot,
    SafeCropEnvelope,
    SlotInteraction,
)
from x5crop.detection.grid.search import (
    _cross_count_selection_pool,
    _dominance,
    _interaction,
    _merge_count_component_proposals,
)
from x5crop.detection.pipeline import choose_detection
from x5crop.detection.protection import (
    apply_fixed_output_protection,
    output_protection_spec,
)
from x5crop.detection.workspace import prepare_detection_workspace
from x5crop.domain import Box, EvidenceState, FiniteInterval
from x5crop.io.model import ImageProfile, TiffMetadata


def _profile(shape: tuple[int, int]) -> ImageProfile:
    return ImageProfile(
        shape=shape,
        dtype="uint8",
        axes="YX",
        photometric="MINISBLACK",
        compression="NONE",
        sample_format=None,
        bits_per_sample=(8,),
        samples_per_pixel=1,
        planar_config=None,
        resolution=None,
        resolution_unit=None,
        icc_profile=None,
        metadata=TiffMetadata(None, None, None, ()),
    )


def _rectangles(
    *,
    count: int,
    start: int,
    width: int = 112,
    pitch: int = 118,
) -> np.ndarray:
    pixels = np.zeros((100, 720), dtype=np.uint8)
    for ordinal in range(count):
        left = start + ordinal * pitch
        pixels[:, left : left + width] = 180
    return pixels


def _candidate(
    pixels: np.ndarray,
    *,
    format_id: str = "135",
    strip_mode: str = "partial",
    requested_count: int | None = None,
    layout: str = "horizontal",
):
    configuration = get_detection_configuration(
        format_id,
        strip_mode,
        requested_count,
    )
    workspace = prepare_detection_workspace(
        pixels,
        _profile(tuple(int(value) for value in pixels.shape)),
        layout,
        configuration,
        None,
    )
    return workspace, configuration, choose_detection(
        workspace,
        configuration,
        None,
    )


class BoundedGridContractTest(unittest.TestCase):
    def test_count_one_has_no_internal_corridor_or_dp_work(self) -> None:
        _workspace, _configuration, candidate = _candidate(
            _rectangles(count=1, start=250),
            requested_count=1,
        )
        selection = candidate.lane_selections[0]
        proposal = selection.selected_proposal
        assert proposal is not None
        self.assertEqual(proposal.count, 1)
        self.assertEqual(proposal.corridor_candidates, ())
        self.assertEqual(proposal.anchor_class.value, "0")
        self.assertEqual(
            proposal.slots[0].previous_interaction,
            SlotInteraction.NOT_APPLICABLE,
        )
        self.assertEqual(
            proposal.slots[0].next_interaction,
            SlotInteraction.NOT_APPLICABLE,
        )
        self.assertTrue(
            all(
                item.dp_states == 0 and item.dp_transitions == 0
                for item in selection.work_by_count_component
            )
        )

        _workspace, _configuration, count_two = _candidate(
            _rectangles(count=2, start=250),
            requested_count=2,
        )
        proposal_two = count_two.lane_selections[0].selected_proposal
        assert proposal_two is not None
        assessment = _dominance(
            proposal,
            proposal_two,
            equality_interval_mm=0.05,
        )
        internal = next(
            item
            for item in assessment.dimensions
            if item.code == "internal_corridor_observed_support"
        )
        self.assertEqual(
            internal.relation,
            DominanceDimensionRelation.NOT_APPLICABLE,
        )
        self.assertFalse(internal.participates_in_dominance)

    def test_anchor_classes_and_arbitrary_partial_placements(self) -> None:
        expected_anchor = {1: "0", 2: "1", 4: "2+"}
        for count, anchor in expected_anchor.items():
            with self.subTest(count=count):
                _workspace, _configuration, candidate = _candidate(
                    _rectangles(count=count, start=120),
                    requested_count=count,
                )
                proposal = candidate.lane_selections[0].selected_proposal
                assert proposal is not None
                self.assertEqual(proposal.anchor_class.value, anchor)

        for placement, start in (
            ("leading", 10),
            ("center", 250),
            ("trailing", 480),
        ):
            with self.subTest(placement=placement):
                _workspace, _configuration, candidate = _candidate(
                    _rectangles(count=2, start=start),
                    requested_count=2,
                )
                proposal = candidate.lane_selections[0].selected_proposal
                assert proposal is not None
                self.assertEqual(len(proposal.safe_envelopes), 2)
                for ordinal, envelope in enumerate(
                    proposal.safe_envelopes
                ):
                    expected_left = start + ordinal * 118
                    expected_right = expected_left + 112
                    self.assertLessEqual(
                        envelope.work_box.left,
                        expected_left,
                    )
                    self.assertGreaterEqual(
                        envelope.work_box.right,
                        expected_right,
                    )

    def test_auto_count_unique_dominance_and_competition(self) -> None:
        _workspace, configuration, candidate = _candidate(
            _rectangles(count=4, start=120),
        )
        selection = candidate.lane_selections[0]
        self.assertEqual(selection.selection_reason, "unique_non_dominated_count")
        self.assertEqual(selection.selected_proposal.count, 4)

        _workspace, _configuration, count_two = _candidate(
            _rectangles(count=2, start=120),
            requested_count=2,
        )
        _workspace, _configuration, count_three = _candidate(
            _rectangles(count=3, start=120),
            requested_count=3,
        )
        proposal_two = count_two.lane_selections[0].selected_proposal
        proposal_three = count_three.lane_selections[0].selected_proposal
        assert proposal_two is not None and proposal_three is not None
        proposal_three = replace(
            proposal_three,
            proposal_id=proposal_three.proposal_id + ":competing",
            observed_boundary_count=4,
            model_only_boundary_count=2,
        )
        assessment = _dominance(
            proposal_two,
            proposal_three,
            equality_interval_mm=0.05,
        )
        self.assertEqual(
            assessment.relation,
            DominanceRelation.INCOMPARABLE,
        )
        gate = candidate_gate_assessment(
            scan_canvas_state=EvidenceState.SUPPORTED,
            source_content_state=EvidenceState.SUPPORTED,
            grid_search_coverage_state=EvidenceState.SUPPORTED,
            frame_count_state=EvidenceState.CONTRADICTED,
            slot_ordinal_state=EvidenceState.UNAVAILABLE,
            slot_ownership_state=EvidenceState.UNAVAILABLE,
            known_content_containment_state=EvidenceState.UNAVAILABLE,
            source_lane_geometry_state=EvidenceState.UNAVAILABLE,
            output_protection_state=EvidenceState.UNAVAILABLE,
            output_transform_state=EvidenceState.SUPPORTED,
        )
        decision = apply_decision_gate(
            gate,
            configuration.count_request.mode,
        )
        self.assertEqual(decision.status, "needs_review")
        self.assertIn(
            FINAL_REASON_AUTOMATIC_COUNT_UNRESOLVED,
            decision.final_review_reasons,
        )

    def test_hard_contradiction_does_not_compete_with_safe_auto_count(
        self,
    ) -> None:
        _workspace, _configuration, count_two = _candidate(
            _rectangles(count=2, start=120),
            requested_count=2,
        )
        _workspace, _configuration, count_three = _candidate(
            _rectangles(count=3, start=120),
            requested_count=3,
        )
        unsafe = replace(
            count_two.lane_selections[0].selected_proposal,
            proposal_id="unsafe-count-two",
            ownership_state=EvidenceState.CONTRADICTED,
        )
        safe = replace(
            count_three.lane_selections[0].selected_proposal,
            proposal_id="safe-count-three",
        )
        self.assertEqual(
            _cross_count_selection_pool((unsafe, safe)),
            (safe,),
        )
        self.assertEqual(
            _cross_count_selection_pool((unsafe,)),
            (unsafe,),
        )

    def test_work_limits_are_real_and_global_limit_is_per_lane(self) -> None:
        pixels = np.random.default_rng(8).integers(
            0,
            256,
            size=(100, 720),
            dtype=np.uint8,
        )
        _workspace, _configuration, candidate = _candidate(pixels)
        selection = candidate.lane_selections[0]
        self.assertLessEqual(len(selection.retained_global_proposals), G_MAX)
        self.assertGreater(len(selection.proposals_by_count), G_MAX)
        self.assertTrue(any(item.search_incomplete for item in selection.work_by_count_component))
        self.assertFalse(
            any(
                item.omitted_outcome_risk
                for item in selection.work_by_count_component
            )
        )
        self.assertEqual(
            selection.grid_search_coverage_state,
            EvidenceState.SUPPORTED,
        )
        for work in selection.work_by_count_component:
            self.assertLessEqual(work.seed_count, P_MAX)
            self.assertLessEqual(work.dp_states, work.state_upper)
            self.assertLessEqual(work.dp_transitions, work.transition_upper)
            self.assertFalse(work.budget_exhausted)
        for proposal in selection.proposals_by_count:
            for corridor in proposal.corridor_candidates:
                self.assertIn(
                    corridor.kind.value,
                    {
                        "observed_edge_pair",
                        "observed_one_sided",
                        "model_only",
                    },
                )
        self.assertEqual(O_MAX, 2)
        self.assertEqual(K_MAX, 3)

    def test_two_120_components_union_without_multiplying_global_limit(
        self,
    ) -> None:
        pixels = np.zeros((100, 377), dtype=np.uint8)
        _workspace, _configuration, candidate = _candidate(
            pixels,
            format_id="120-66",
            requested_count=3,
        )
        selection = candidate.lane_selections[0]
        proposal = selection.selected_proposal
        assert proposal is not None
        self.assertEqual(
            {item.component_id for item in selection.work_by_count_component},
            {"component:0:54x54", "component:1:56x56"},
        )
        self.assertTrue(proposal.component_id.startswith("union:"))
        self.assertEqual(len(selection.retained_global_proposals), 1)

    def test_blank_slots_overlap_and_protection_saturation_are_safe(self) -> None:
        workspace, configuration, candidate = _candidate(
            np.zeros((100, 720), dtype=np.uint8),
            requested_count=3,
        )
        selection = candidate.lane_selections[0]
        proposal = selection.selected_proposal
        assert proposal is not None
        self.assertEqual(len(proposal.slots), 3)
        self.assertTrue(
            all(
                slot.appearance_state == EvidenceState.UNAVAILABLE
                for slot in proposal.slots
            )
        )
        protected = candidate.protected_envelopes_by_lane[0]
        self.assertIn("left", protected[0].saturated_sides)
        self.assertTrue(
            all(
                {"top", "bottom"}.issubset(item.saturated_sides)
                for item in protected
            )
        )
        self.assertGreater(
            protected[0].protected_work_box.right,
            protected[1].protected_work_box.left,
        )
        self.assertTrue(candidate.gate.passed)
        self.assertEqual(
            configuration.count_request.mode,
            FrameCountMode.EXPLICIT,
        )
        self.assertIs(
            workspace.source_core.lanes[0].scan_canvas.axis_scales,
            workspace.source_core.lanes[0].axis_scale_intervals,
        )

    def test_interaction_equality_interval_handles_float_microdifferences(
        self,
    ) -> None:
        self.assertEqual(
            _interaction(
                FiniteInterval.exact(10.0),
                FiniteInterval.exact(10.0000001),
                0.001,
            ),
            SlotInteraction.CONTACT,
        )
        self.assertEqual(
            _interaction(
                FiniteInterval.exact(10.0),
                FiniteInterval.exact(9.0),
                0.001,
            ),
            SlotInteraction.OVERLAP,
        )
        self.assertEqual(
            _interaction(
                FiniteInterval.exact(10.0),
                FiniteInterval.exact(11.0),
                0.001,
            ),
            SlotInteraction.SEPARATED,
        )

    def test_safe_envelope_size_does_not_participate_in_count_dominance(
        self,
    ) -> None:
        _workspace, _configuration, candidate = _candidate(
            _rectangles(count=2, start=250),
            requested_count=2,
        )
        proposal = candidate.lane_selections[0].selected_proposal
        assert proposal is not None
        expanded = tuple(
            replace(
                envelope,
                work_box=Box(
                    max(0, envelope.work_box.left - 1),
                    envelope.work_box.top,
                    min(720, envelope.work_box.right + 1),
                    envelope.work_box.bottom,
                ),
            )
            for envelope in proposal.safe_envelopes
        )
        alternative = replace(
            proposal,
            proposal_id=proposal.proposal_id + ":expanded",
            safe_envelopes=expanded,
            residual_mm=proposal.residual_mm + 0.01,
        )
        assessment = _dominance(
            proposal,
            alternative,
            equality_interval_mm=0.05,
        )
        self.assertEqual(assessment.relation, DominanceRelation.EQUIVALENT)
        self.assertEqual(assessment.residual_relation, "equal_interval")

    def test_seed_alternatives_union_only_when_output_equivalent_or_blank(
        self,
    ) -> None:
        _workspace, _configuration, candidate = _candidate(
            _rectangles(count=2, start=120),
            requested_count=2,
        )
        proposal = candidate.lane_selections[0].selected_proposal
        assert proposal is not None

        def shifted(delta: int):
            return replace(
                proposal,
                proposal_id=f"{proposal.proposal_id}:shift:{delta}",
                seed=replace(
                    proposal.seed,
                    seed_id=f"{proposal.seed.seed_id}:shift:{delta}",
                    origin_px=FiniteInterval(
                        proposal.seed.origin_px.minimum + delta,
                        proposal.seed.origin_px.maximum + delta,
                    ),
                ),
                slots=tuple(
                    replace(
                        slot,
                        start_px=FiniteInterval(
                            slot.start_px.minimum + delta,
                            slot.start_px.maximum + delta,
                        ),
                        end_px=FiniteInterval(
                            slot.end_px.minimum + delta,
                            slot.end_px.maximum + delta,
                        ),
                    )
                    for slot in proposal.slots
                ),
                safe_envelopes=tuple(
                    replace(
                        envelope,
                        work_box=Box(
                            envelope.work_box.left + delta,
                            envelope.work_box.top,
                            envelope.work_box.right + delta,
                            envelope.work_box.bottom,
                        ),
                    )
                    for envelope in proposal.safe_envelopes
                ),
            )

        close = shifted(5)
        close_union = _merge_count_component_proposals(
            (proposal, close)
        )
        assert close_union is not None
        self.assertEqual(
            close_union.ownership_state,
            EvidenceState.SUPPORTED,
        )
        self.assertLessEqual(
            close_union.safe_envelopes[0].work_box.left,
            proposal.safe_envelopes[0].work_box.left,
        )
        self.assertGreaterEqual(
            close_union.safe_envelopes[0].work_box.right,
            close.safe_envelopes[0].work_box.right,
        )

        whole_pitch = shifted(150)
        competing = _merge_count_component_proposals(
            (proposal, whole_pitch)
        )
        assert competing is not None
        self.assertEqual(
            competing.ownership_state,
            EvidenceState.CONTRADICTED,
        )

        blank = tuple(
            replace(slot, appearance_state=EvidenceState.UNAVAILABLE)
            for slot in proposal.slots
        )
        blank_shifted = tuple(
            replace(slot, appearance_state=EvidenceState.UNAVAILABLE)
            for slot in whole_pitch.slots
        )
        blank_union = _merge_count_component_proposals(
            (
                replace(
                    proposal,
                    proposal_id=proposal.proposal_id + ":blank",
                    slots=blank,
                ),
                replace(
                    whole_pitch,
                    proposal_id=whole_pitch.proposal_id + ":blank",
                    slots=blank_shifted,
                ),
            )
        )
        assert blank_union is not None
        self.assertEqual(
            blank_union.ownership_state,
            EvidenceState.SUPPORTED,
        )

    def test_only_fixed_protection_may_saturate_lane_authority(self) -> None:
        workspace, _configuration, candidate = _candidate(
            np.zeros((100, 720), dtype=np.uint8),
            requested_count=1,
        )
        lane = workspace.source_core.lanes[0]
        with self.assertRaises(ValueError):
            apply_fixed_output_protection(
                lane,
                (
                    SafeCropEnvelope(
                        "lane:0",
                        1,
                        Box(-1, 0, 100, 100),
                        "model_outward_union",
                    ),
                ),
                output_protection_spec("135"),
            )
        protected = candidate.protected_envelopes_by_lane[0][0]
        self.assertTrue(protected.saturated_sides)
        self.assertIn("left", protected.saturated_sides)
        self.assertEqual(protected.protected_work_box.left, lane.domain.work_box.left)
        self.assertGreaterEqual(
            protected.protected_work_box.right,
            protected.safe_work_box.right,
        )
        self.assertLessEqual(
            protected.protected_work_box.right,
            lane.domain.work_box.right,
        )

    def test_hard_geometry_and_ownership_contradictions_are_typed(self) -> None:
        with self.assertRaises(ValueError):
            FrameSlot(
                lane_id="lane:0",
                lane_ordinal=1,
                start_px=FiniteInterval.exact(10.0),
                end_px=FiniteInterval.exact(10.0),
                appearance_state=EvidenceState.UNAVAILABLE,
                previous_interaction=SlotInteraction.NOT_APPLICABLE,
                next_interaction=SlotInteraction.NOT_APPLICABLE,
            )
        gate = candidate_gate_assessment(
            scan_canvas_state=EvidenceState.SUPPORTED,
            source_content_state=EvidenceState.SUPPORTED,
            grid_search_coverage_state=EvidenceState.SUPPORTED,
            frame_count_state=EvidenceState.SUPPORTED,
            slot_ordinal_state=EvidenceState.SUPPORTED,
            slot_ownership_state=EvidenceState.CONTRADICTED,
            known_content_containment_state=EvidenceState.UNAVAILABLE,
            source_lane_geometry_state=EvidenceState.SUPPORTED,
            output_protection_state=EvidenceState.SUPPORTED,
            output_transform_state=EvidenceState.SUPPORTED,
        )
        decision = apply_decision_gate(gate, FrameCountMode.EXPLICIT)
        self.assertEqual(decision.status, "needs_review")
        self.assertEqual(
            decision.final_review_reasons,
            (FINAL_REASON_SLOT_OWNERSHIP_UNBOUNDED,),
        )

    def test_vertical_work_layout_is_rotation_equivalent(self) -> None:
        horizontal = _rectangles(count=2, start=250)
        _workspace, _configuration, candidate = _candidate(
            horizontal.T,
            requested_count=2,
            layout="vertical",
        )
        proposal = candidate.lane_selections[0].selected_proposal
        assert proposal is not None
        self.assertEqual(proposal.count, 2)
        self.assertTrue(candidate.gate.passed)

    def test_measurement_cache_key_excludes_lifecycle_objects(self) -> None:
        workspace, _configuration, _candidate_value = _candidate(
            _rectangles(count=2, start=250),
            requested_count=2,
        )
        cache = workspace.measurement_cache
        self.assertEqual(
            tuple(item.name for item in fields(MeasurementCache)),
            ("key", "gray_work", "image_statistics"),
        )
        self.assertEqual(
            tuple(item.name for item in fields(MeasurementCacheKey)),
            (
                "workspace_identity",
                "layout",
                "base_gray_parameters",
                "statistics_parameters",
            ),
        )
        forbidden = {
            "seed",
            "candidate",
            "proposal",
            "gate",
            "decision",
            "reason",
            "output_box",
            "count",
            "offset",
        }
        self.assertTrue(
            forbidden.isdisjoint(
                {item.name for item in fields(MeasurementCache)}
                | {item.name for item in fields(MeasurementCacheKey)}
            )
        )
        self.assertFalse(cache.gray_work.flags.writeable)
        with self.assertRaises(Exception):
            cache.key = cache.key


class AcceptanceSchemaContractTest(unittest.TestCase):
    def test_frozen_result_and_summary_schemas(self) -> None:
        result = dict.fromkeys(RESULT_FIELDS)
        result.update(
            {
                "result_schema": RESULT_SCHEMA,
                "decision_status": "terminal_failure",
                "passed": False,
            }
        )
        validate_acceptance_result_record(result)
        summary = dict.fromkeys(SUMMARY_FIELDS)
        summary.update(
            {
                "summary_schema": SUMMARY_SCHEMA,
                "real_holdout": "unavailable",
                "passed": False,
            }
        )
        validate_acceptance_summary_record(summary)
        with self.assertRaises(ValueError):
            validate_acceptance_result_record(
                {**result, "legacy_alias": True}
            )

    def test_preflight_requires_an_empty_output_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "existing").write_text("occupied", encoding="utf-8")
            with self.assertRaises(AcceptancePreflightError):
                _validate_output_root(root)

    def test_xpan_and_120_645_priors_are_explicit_physical_rules(self) -> None:
        for format_id, aperture in (("xpan", 65.0), ("120-645", 42.0)):
            for mode in ("full", "partial"):
                prior = frame_grid_search_prior(
                    format_id,
                    mode,
                    aperture,
                )
                self.assertEqual(prior.provenance, "physical_rule")

    def test_uncovered_formats_have_synthetic_full_flow_contracts(self) -> None:
        cases = (
            ("xpan", np.zeros((100, 720), dtype=np.uint8), 3),
            ("120-645", np.zeros((100, 377), dtype=np.uint8), 4),
        )
        for format_id, pixels, expected_count in cases:
            with self.subTest(format_id=format_id):
                _workspace, configuration, candidate = _candidate(
                    pixels,
                    format_id=format_id,
                    strip_mode="full",
                )
                self.assertEqual(
                    configuration.count_request.mode,
                    FrameCountMode.FIXED_FULL,
                )
                self.assertEqual(candidate.selected_count, expected_count)
                self.assertTrue(candidate.gate.passed)


if __name__ == "__main__":
    unittest.main()
