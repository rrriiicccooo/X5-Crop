from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from tools.tests.physical_gate_support import (
    candidate_evidence_fixture,
    candidate_fixture,
    separator_observation,
)
from x5crop.cache import MeasurementCache
from x5crop.detection.candidate.assessment.candidate import _boundary_proof_paths
from x5crop.detection.candidate.assessment.separator_support import (
    separator_sequence_evidence,
)
from x5crop.detection.candidate.build.separator_sources import (
    select_geometry_equal_model_gaps,
)
from x5crop.detection.candidate.model import BuiltCandidate
from x5crop.detection.evidence.content.preservation import content_preservation_evidence
from x5crop.detection.evidence.frame_coverage import frame_coverage_evidence
from x5crop.detection.evidence.state import EvidenceState
from x5crop.detection.evidence.separator_continuity import (
    SeparatorContinuityEvidence,
    SeparatorContinuityRecord,
)
from x5crop.detection.physical.photo_size import (
    frame_dimension_evidence,
    photo_size_consistency_from_gap_edges,
)
from x5crop.detection.physical.separator.hints import (
    SeparatorGapHint,
    SeparatorGapHintSet,
)
from x5crop.detection.physical.separator.proposal import propose_separator_gaps
from x5crop.domain import Box, MeasurementProvenance
from x5crop.formats import format_spec
from x5crop.geometry.detection_parameters import (
    EdgePairParameters,
    NearbySeparatorRefinementParameters,
)
from x5crop.geometry.edge_pairs import refine_gaps_with_edge_profiles
from x5crop.geometry.frame_fit import frame_boxes_from_gaps
from x5crop.geometry.gap_search import GapSearchResult
from x5crop.geometry.nearby_separator import apply_nearby_separator_refinement
from x5crop.policies.registry import get_detection_policy
from x5crop.units import ScanCalibration


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _cache() -> MeasurementCache:
    gray = np.zeros((100, 600), dtype=np.uint8)
    return MeasurementCache(
        layout="horizontal",
        gray_work=gray,
        content_evidence_work=gray,
        content_evidence_float_work=gray.astype(np.float32),
    )


class PhysicalDetectionResolutionContractTest(unittest.TestCase):
    def test_more_content_regions_than_frames_contradicts_coverage(self) -> None:
        candidate = candidate_fixture()
        with patch(
            "x5crop.detection.evidence.frame_coverage.content_region_runs",
            return_value=((10, 50), (80, 120), (150, 190)),
        ):
            evidence = frame_coverage_evidence(
                candidate.geometry.holder_span,
                candidate.geometry.film_span,
                candidate.geometry.work_frames,
                format_spec("135"),
                _cache(),
                get_detection_policy("135", "full").content,
            )
        self.assertEqual(evidence.state, EvidenceState.CONTRADICTED)
        self.assertEqual(evidence.unexplained_content_region_count, 1)

    def test_extra_empty_frame_is_legal(self) -> None:
        candidate = candidate_fixture()
        with patch(
            "x5crop.detection.evidence.frame_coverage.content_region_runs",
            return_value=((10, 90),),
        ):
            evidence = frame_coverage_evidence(
                candidate.geometry.holder_span,
                candidate.geometry.film_span,
                candidate.geometry.work_frames,
                format_spec("135"),
                _cache(),
                get_detection_policy("135", "full").content,
            )
        self.assertEqual(evidence.state, EvidenceState.SUPPORTED)

    def test_single_frame_needs_calibration_or_two_boundary_anchors(self) -> None:
        assessed = candidate_fixture()
        geometry = replace(
            assessed.geometry,
            count=1,
            work_frames=(assessed.geometry.work_frames[0],),
            image_frames=(assessed.geometry.image_frames[0],),
            separators=(),
            outer_provenance=replace(
                assessed.geometry.outer_provenance,
                boundary_anchors=(),
            ),
        )
        built = BuiltCandidate(geometry, assessed.count_hypothesis, ())
        evidence = replace(
            candidate_evidence_fixture(),
            frame_dimensions=replace(
                candidate_evidence_fixture().frame_dimensions,
                calibration_used=False,
            ),
        )
        paths = _boundary_proof_paths(built, evidence)
        self.assertFalse(
            any(path.state == EvidenceState.SUPPORTED for path in paths)
        )

    def test_complete_underfilled_does_not_suppress_undercrop(self) -> None:
        evidence = candidate_evidence_fixture()
        coverage = replace(
            evidence.frame_coverage,
            state=EvidenceState.CONTRADICTED,
            uncovered_content=((190, 210),),
        )
        partial = replace(
            evidence.partial_edge_safety,
            state=EvidenceState.SUPPORTED,
            complete_underfilled_strip=True,
        )
        result = content_preservation_evidence(
            evidence.frame_content,
            evidence.outer_alignment,
            partial,
            coverage,
        )
        self.assertEqual(result.state, EvidenceState.CONTRADICTED)

    def test_irregular_separator_width_preserves_stable_photo_size(self) -> None:
        result = photo_size_consistency_from_gap_edges(
            [
                separator_observation(1, 110.0, start=100.0, end=120.0),
                separator_observation(2, 235.0, start=220.0, end=250.0),
            ],
            0.0,
            350.0 / 3.0,
            3,
        )
        self.assertEqual(result.photo_widths, (100.0, 100.0, 100.0))
        self.assertEqual(result.photo_width_cv, 0.0)
        self.assertGreater(result.separator_width_cv or 0.0, 0.0)

    def test_photo_size_uses_available_edge_bounded_frames(self) -> None:
        result = photo_size_consistency_from_gap_edges(
            [
                separator_observation(1, 105.0, start=100.0, end=110.0),
                separator_observation(3, 335.0, start=330.0, end=340.0),
            ],
            0.0,
            110.0,
            4,
            target_photo_width=100.0,
        )

        self.assertTrue(result.used)
        self.assertEqual(result.photo_widths, (100.0, 100.0))
        self.assertEqual(result.photo_width_cv, 0.0)

    def test_separator_without_cross_axis_continuity_is_not_hard_support(self) -> None:
        candidate = candidate_fixture()
        observation = candidate.geometry.separators[0]
        continuity = SeparatorContinuityEvidence(
            EvidenceState.CONTRADICTED,
            "separator_cross_axis_continuity_weak",
            (
                SeparatorContinuityRecord(
                    observation.index,
                    observation.method,
                    True,
                    EvidenceState.CONTRADICTED,
                    0.2,
                    0.2,
                    3,
                    0.2,
                    "separator_cross_axis_continuity_weak",
                ),
            ),
            (observation,),
            0.62,
            0.55,
        )

        sequence = separator_sequence_evidence(candidate.geometry, continuity)

        self.assertEqual(sequence.hard_count, 0)
        self.assertEqual(sequence.state, EvidenceState.UNAVAILABLE)

    def test_photo_dimensions_ignore_unconfirmed_separator_bands(self) -> None:
        candidate = candidate_fixture()
        policy = get_detection_policy("135", "full")

        dimensions = frame_dimension_evidence(
            candidate.geometry,
            format_spec("135"),
            ScanCalibration(None, None, "unavailable", False),
            separator_observations=(),
            maximum_photo_width_cv=(
                policy.scoring.base_detection.unstable_photo_width_cv
            ),
            maximum_dimension_error_ratio=(
                policy.scoring.geometry_support.aspect_norm
            ),
        )

        self.assertEqual(dimensions.state, EvidenceState.UNAVAILABLE)

    def test_equal_model_only_fills_missing_indexes(self) -> None:
        fmt = format_spec("135")
        hard = separator_observation(2, 200.0, start=195.0, end=205.0)
        result = select_geometry_equal_model_gaps(
            (hard,),
            np.zeros(600, dtype=np.float32),
            fmt,
            fmt.default_count,
            "full",
            0.0,
            100.0,
            None,
        )
        self.assertIs(next(gap for gap in result if gap.index == 2), hard)
        self.assertEqual(len(result), fmt.default_count - 1)

    def test_nearby_refinement_never_moves_measured_band(self) -> None:
        measured = separator_observation(1, 50.0, start=45.0, end=55.0)
        profile = np.zeros(120, dtype=np.float32)
        profile[64:67] = 1.0
        result = apply_nearby_separator_refinement(
            profile,
            [measured],
            100.0,
            2,
            NearbySeparatorRefinementParameters(),
        )
        self.assertIs(result[0], measured)

    def test_edge_pair_refinement_stays_inside_measured_band(self) -> None:
        measured = separator_observation(1, 50.0, start=45.0, end=55.0)
        edge = np.zeros(120, dtype=np.float32)
        edge[70] = 1.0
        edge[80] = 1.0
        background = np.ones(120, dtype=np.float32)
        parameters = EdgePairParameters(
            window_ratio=1.0,
            search_window_max=120,
            min_gutter_ratio=0.01,
            max_gutter_ratio=0.50,
            min_strength=0.10,
            candidate_peak_percentile=0.0,
            min_background=0.10,
            max_hard_shift_ratio=1.0,
            hard_shift_limit_max=120.0,
        )

        refined = refine_gaps_with_edge_profiles(
            edge,
            background,
            [measured],
            2,
            parameters,
        )

        self.assertEqual(refined, [measured])

    def test_one_measured_separator_band_cannot_fill_two_indexes(self) -> None:
        policy = get_detection_policy("135", "full").separator

        def same_band(_profile, _expected, _pitch, index, *_args, **_kwargs):
            return GapSearchResult(
                separator_observation(
                    index,
                    150.0,
                    start=145.0,
                    end=155.0,
                ),
                0.5,
                "detected",
            )

        with patch(
            "x5crop.detection.physical.separator.proposal.find_detected_gap",
            side_effect=same_band,
        ):
            result = propose_separator_gaps(
                Box(0, 0, 300, 100),
                np.zeros(300, dtype=np.float32),
                np.array([], dtype=np.float32),
                0.0,
                100.0,
                3,
                None,
                policy.gap_search,
                policy.width_profile,
                policy.width_profile_search,
                ScanCalibration(None, None, "unavailable", False),
                "x",
            )

        measured = [gap for gap in result if gap.method == "detected"]
        self.assertEqual(len(measured), 1)
        self.assertEqual(len({gap.center for gap in measured}), 1)

    def test_content_guided_separator_keeps_guidance_dependency(self) -> None:
        separator_policy = get_detection_policy("135", "partial").separator
        hints = SeparatorGapHintSet(
            hints=(SeparatorGapHint(1, 80.0, 70.0, 90.0),),
            max_offset_ratio=0.5,
            max_offset_min=1,
            max_offset_max=100,
            provenance=MeasurementProvenance(
                "content_guidance",
                "content_runs",
                ("content_evidence",),
            ),
        )
        with patch(
            "x5crop.detection.physical.separator.proposal.find_detected_gap",
            return_value=GapSearchResult(
                separator_observation(
                    1,
                    80.0,
                    start=75.0,
                    end=85.0,
                ),
                0.0,
                "detected",
            ),
        ):
            result = propose_separator_gaps(
                Box(0, 0, 200, 100),
                np.zeros(200, dtype=np.float32),
                np.array([], dtype=np.float32),
                0.0,
                100.0,
                2,
                None,
                separator_policy.gap_search,
                separator_policy.width_profile,
                separator_policy.width_profile_search,
                ScanCalibration(None, None, "unavailable", False),
                "x",
                hints,
            )

        self.assertIn(
            "content_guidance",
            result[0].provenance.dependencies,
        )

    def test_frame_cuts_use_measured_band_centers(self) -> None:
        frames = frame_boxes_from_gaps(
            Box(0, 0, 360, 100),
            [
                separator_observation(1, 90.0, start=85.0, end=95.0),
                separator_observation(2, 230.0, start=225.0, end=235.0),
            ],
            3,
            360,
            100,
            0,
            0,
            origin=0.0,
            pitch=120.0,
        )
        self.assertEqual(
            [(frame.left, frame.right) for frame in frames],
            [(0, 90), (90, 230), (230, 360)],
        )

    def test_candidate_gate_is_not_execution_budget(self) -> None:
        source = (PROJECT_ROOT / "x5crop/detection/pipeline.py").read_text()
        self.assertNotIn("candidate_gate.passed", source)
        self.assertIn("evaluation.geometry_resolved", source)


if __name__ == "__main__":
    unittest.main()
