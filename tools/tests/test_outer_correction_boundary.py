from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
import unittest

from tools.tests.physical_gate_support import candidate_fixture
from x5crop.detection.candidate.extension.outer_correction import (
    _correction_provenance,
    _eligible_families,
)
from x5crop.detection.physical.outer.correction.types import (
    OuterCorrectionProposal,
)
from x5crop.detection.physical.spans import FilmSpan
from x5crop.detection.physical.outer.correction.content_containment import (
    content_containment_correction_proposal,
)
from x5crop.detection.evidence.state import EvidenceState
from x5crop.domain import Box
from x5crop.policies.registry import get_detection_policy


def _context(mode: str, requested_count: int | None):
    return SimpleNamespace(
        request=SimpleNamespace(requested_count=requested_count),
        policy=get_detection_policy("120-66", mode),
    )


def _candidate(mode: str, source: str = "separator"):
    candidate = candidate_fixture()
    return replace(
        candidate,
        geometry=replace(
            candidate.geometry,
            format_id="120-66",
            strip_mode=mode,
            source=source,
        ),
    )


class OuterCorrectionBoundaryTest(unittest.TestCase):
    def test_full_separator_candidate_can_enter_all_families(self) -> None:
        self.assertEqual(
            _eligible_families(_candidate("full"), _context("full", 3)),
            frozenset(
                {"long_axis_geometry", "short_axis_geometry", "content_containment"}
            ),
        )

    def test_partial_explicit_count_can_enter_all_families(self) -> None:
        self.assertEqual(
            _eligible_families(_candidate("partial"), _context("partial", 3)),
            frozenset(
                {"long_axis_geometry", "short_axis_geometry", "content_containment"}
            ),
        )

    def test_partial_auto_count_blocks_correction_extension(self) -> None:
        self.assertEqual(
            _eligible_families(_candidate("partial"), _context("partial", None)),
            frozenset(),
        )

    def test_non_separator_candidate_is_not_sent_to_physical_correction(self) -> None:
        self.assertEqual(
            _eligible_families(
                _candidate("full", source="hard_safety"),
                _context("full", 3),
            ),
            frozenset(),
        )

    def test_content_containment_correction_only_expands(self) -> None:
        candidate = _candidate("full")
        alignment = replace(
            candidate.assessment.evidence.outer_alignment,
            state=EvidenceState.CONTRADICTED,
            content_span=Box(-10, 0, 210, 100),
            confirmed_undercrop_sides=("left", "right"),
        )
        proposal = content_containment_correction_proposal(
            candidate.geometry,
            alignment,
            240,
            120,
            get_detection_policy("120-66", "full").outer.correction.content_containment,
        )
        self.assertIsNotNone(proposal)
        assert proposal is not None
        self.assertGreaterEqual(proposal.box.width, candidate.geometry.film_span.box.width)
        self.assertGreaterEqual(proposal.box.height, candidate.geometry.film_span.box.height)

    def test_geometry_correction_preserves_root_measurement_dependencies(self) -> None:
        candidate = _candidate("full")
        proposal = OuterCorrectionProposal(
            FilmSpan(candidate.geometry.film_span.box),
            "long_axis_geometry",
            "test",
        )

        provenance = _correction_provenance(candidate, proposal)

        self.assertEqual(
            provenance.root_measurement,
            candidate.geometry.outer_provenance.root_measurement,
        )
        self.assertIn("separator_profile", provenance.dependencies)


if __name__ == "__main__":
    unittest.main()
