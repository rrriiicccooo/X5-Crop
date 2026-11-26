from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import tifffile

from tools.regression.phase_output_validation import validate_complete_phase_output
from tools.regression.report_validation import (
    _read_common_proof,
    validate_current_report_record,
)
from tools.tests.test_debug_analysis_contract import _full_135_pixels
from tools.tests.test_source_core_runtime_contract import _run_config
from tools.tests.test_template_runtime_model_contract import _unresolved_result
from x5crop.configuration.registry import get_detection_configuration
from x5crop.detection.pipeline import choose_detection
from x5crop.detection.photo_geometry.template_phase_model import PhaseFitStatus
from x5crop.detection.workspace import prepare_detection_workspace
from x5crop.io.tiff import read_tiff
from x5crop.runtime.invocation import PlannedSource
from x5crop.runtime.outcome import CompletedInput
from x5crop.runtime.workflow import process_one


def _write_source(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    source = root / "135.tif"
    tifffile.imwrite(
        source,
        _full_135_pixels(),
        photometric="rgb",
        planarconfig="contig",
    )
    return source


def _candidate(root: Path, requested: object, requested_count: int = 3):
    source = _write_source(root)
    array, profile, _warnings = read_tiff(source)
    configuration = get_detection_configuration("135", requested_count)
    workspace = prepare_detection_workspace(
        array,
        profile,
        "horizontal",
        configuration,
    )
    return choose_detection(
        workspace,
        configuration,
        complete_phase_validation_requested=requested,
    )


def _runtime_outcome(
    root: Path,
    *,
    debug_analysis: bool = False,
    development_detail: bool = False,
    output_name: str = "output",
    source: Path | None = None,
):
    if source is None:
        source = _write_source(root)
    output = root / output_name
    configuration = get_detection_configuration("135", 3)
    config = _run_config(
        source,
        output,
        debug_analysis=debug_analysis,
    )
    if development_detail:
        config = replace(config, development_detail=True)
    # Keep this explicit: it exercises the workflow's effective
    # (debug_analysis OR development_detail) routing, not only bootstrap.
    if debug_analysis:
        config = replace(config, development_detail=False)
    return process_one(
        PlannedSource(1, source, source.stem),
        config,
        configuration,
        output,
    )


def _without_diagnostic_fields(record: dict) -> dict:
    """Remove only mode markers and complete-proof payloads for comparison."""
    normalized = deepcopy(record)
    normalized.pop("detail_level", None)
    normalized.pop("development", None)
    geometry = normalized["photo_geometry"]
    geometry.pop("complete_phase_validation_requested", None)
    for lane in geometry["lanes"]:
        lane.pop("complete_phase_output", None)
    return normalized


class CompletePhaseDiagnosticModeContractTest(unittest.TestCase):
    def test_normal_mode_skips_complete_builder_and_keeps_consumed_state(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            phase_output = __import__(
                "x5crop.detection.photo_geometry.template_phase_output",
                fromlist=["build_complete_phase_output"],
            )
            with patch.object(
                phase_output,
                "build_complete_phase_output",
                side_effect=AssertionError("normal mode invoked complete builder"),
            ) as builder:
                normal = _candidate(root / "normal", False)
            requested = _candidate(root / "requested", True)

        self.assertEqual(builder.call_count, 0)
        self.assertFalse(normal.geometry.complete_phase_validation_requested)
        self.assertTrue(requested.geometry.complete_phase_validation_requested)
        self.assertEqual(normal.gate, requested.gate)
        self.assertEqual(
            normal.geometry.source_placement_proposal,
            requested.geometry.source_placement_proposal,
        )
        self.assertEqual(
            normal.geometry.source_placement_selection,
            requested.geometry.source_placement_selection,
        )
        self.assertEqual(
            normal.geometry.output_slot_identities,
            requested.geometry.output_slot_identities,
        )
        self.assertEqual(
            normal.geometry.assessment_facts,
            requested.geometry.assessment_facts,
        )
        for normal_lane, requested_lane in zip(
            normal.geometry.lane_reconstructions,
            requested.geometry.lane_reconstructions,
            strict=True,
        ):
            self.assertIsNone(normal_lane.complete_phase_output)
            self.assertIsNotNone(requested_lane.complete_phase_output)
            self.assertEqual(
                normal_lane.independent_phase_review,
                requested_lane.independent_phase_review,
            )
            for field in (
                "placement_competition",
                "placement_proposal",
                "alternative_placement_proposals",
                "selected_placement",
                "output_footprints",
                "calibrated_nominal_grid_authority",
                "enclosing_support_aperture_authority",
                "direct_use_budget_assessments",
                "holder_fill_assessment",
                "content_veto_facts",
            ):
                self.assertEqual(
                    getattr(normal_lane, field),
                    getattr(requested_lane, field),
                    field,
                )

    def test_both_development_routes_request_real_plural_proof_and_keep_members(self) -> None:
        # The first route is an explicit detail request with debug disabled;
        # the second route is debug-only with the detail flag initially false.
        for label, debug_analysis, development_detail in (
            ("detail", False, True),
            ("debug", True, False),
        ):
            with self.subTest(route=label), TemporaryDirectory() as temporary:
                root = Path(temporary)
                phase_output = __import__(
                    "x5crop.detection.photo_geometry.template_phase_output",
                    fromlist=["build_complete_phase_output"],
                )
                real_builder = phase_output.build_complete_phase_output
                with patch.object(
                    phase_output,
                    "build_complete_phase_output",
                    wraps=real_builder,
                ) as builder:
                    outcome = _runtime_outcome(
                        root,
                        debug_analysis=debug_analysis,
                        development_detail=development_detail,
                    )
                self.assertIsInstance(outcome, CompletedInput)
                assert isinstance(outcome, CompletedInput)
                self.assertGreater(builder.call_count, 0)
                self.assertEqual(outcome.result["detail_level"], "development")
                geometry = outcome.result["photo_geometry"]
                self.assertIs(geometry["complete_phase_validation_requested"], True)
                lane = geometry["lanes"][0]
                proof = lane["complete_phase_output"]
                self.assertIsNotNone(proof)
                self.assertEqual(
                    len(proof["scopes"]),
                    len(lane["phase_competition_scopes"]),
                )
                expected_members = [
                    (scope["scope_id"], member["record_ordinal"])
                    for scope in proof["scopes"]
                    for member in scope["members"]
                ]
                actual_members = [
                    (member["scope_id"], member["record_ordinal"])
                    for member in proof["members"]
                ]
                self.assertEqual(actual_members, expected_members)
                self.assertGreater(len(actual_members), 1)
                self.assertEqual(proof["state"], "unavailable")

    def test_source_marker_and_producer_scope_guards_are_strict(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            requested = _candidate(root / "requested", True)
            with self.assertRaises(TypeError):
                _candidate(root / "invalid", 1)
            with self.assertRaises(TypeError):
                replace(requested.geometry, complete_phase_validation_requested=1)
            with self.assertRaises(TypeError):
                replace(requested.geometry, complete_phase_validation_requested=None)

        with self.assertRaises(ValueError):
            replace(
                requested.geometry,
                complete_phase_validation_requested=False,
            )
        broken_plural = replace(
            requested.geometry.lane_reconstructions[0],
            complete_phase_output=None,
        )
        with self.assertRaises(ValueError):
            replace(
                requested.geometry,
                lane_reconstructions=(broken_plural,),
            )

        no_runner = _unresolved_result()
        requested_no_runner = replace(
            no_runner,
            complete_phase_validation_requested=True,
        )
        self.assertTrue(requested_no_runner.complete_phase_validation_requested)
        self.assertIsNone(
            requested_no_runner.lane_reconstructions[0].complete_phase_output
        )
        with self.assertRaises(TypeError):
            replace(no_runner, complete_phase_validation_requested=1)
        with self.assertRaises(TypeError):
            replace(no_runner, complete_phase_validation_requested=None)

        with TemporaryDirectory() as temporary:
            resolved = _candidate(Path(temporary) / "resolved", True, 6)
        lane = resolved.geometry.lane_reconstructions[0]
        self.assertEqual(
            lane.prepared.phase_competition.status,
            PhaseFitStatus.RESOLVED,
        )
        self.assertGreater(
            len(lane.prepared.phase_competition.competition_scopes),
            0,
        )
        self.assertGreater(
            sum(
                len(scope.members)
                for scope in lane.prepared.phase_competition.competition_scopes
            ),
            0,
        )
        self.assertTrue(resolved.geometry.complete_phase_validation_requested)
        self.assertIsNone(lane.complete_phase_output)

    def test_reports_preserve_decision_and_output_and_reject_marker_spoofing(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = _write_source(root)
            normal = _runtime_outcome(root, output_name="normal", source=source)
            development = _runtime_outcome(
                root,
                development_detail=True,
                output_name="development",
                source=source,
            )
            self.assertIsInstance(normal, CompletedInput)
            self.assertIsInstance(development, CompletedInput)
            assert isinstance(normal, CompletedInput)
            assert isinstance(development, CompletedInput)
            validate_current_report_record(normal.result)
            validate_current_report_record(development.result)

            # This exact normalization excludes only mode/diagnostic roots;
            # candidate gate, proposals, decision, output state/report metadata,
            # measurements, and all other report fields must remain equivalent.
            self.assertEqual(
                _without_diagnostic_fields(normal.result),
                _without_diagnostic_fields(development.result),
            )

            missing = deepcopy(development.result)
            del missing["photo_geometry"]["complete_phase_validation_requested"]
            with self.assertRaises(ValueError):
                validate_current_report_record(missing)

            false_marker = deepcopy(development.result)
            false_marker["photo_geometry"]["complete_phase_validation_requested"] = False
            with self.assertRaises(ValueError):
                validate_current_report_record(false_marker)

            integer_marker = deepcopy(development.result)
            integer_marker["photo_geometry"]["complete_phase_validation_requested"] = 1
            with self.assertRaises(ValueError):
                validate_current_report_record(integer_marker)

            production_with_proof = deepcopy(normal.result)
            production_with_proof["photo_geometry"]["lanes"][0][
                "complete_phase_output"
            ] = deepcopy(
                development.result["photo_geometry"]["lanes"][0][
                    "complete_phase_output"
                ]
            )
            with self.assertRaises(ValueError):
                validate_current_report_record(production_with_proof)

    def test_phase_validator_false_request_cannot_bypass_replay_contract(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            outcome = _runtime_outcome(root, development_detail=True)
            self.assertIsInstance(outcome, CompletedInput)
            assert isinstance(outcome, CompletedInput)
            development = outcome.result["development"]
            production_geometry = outcome.result["photo_geometry"]
            with self.assertRaisesRegex(
                ValueError,
                "development phase validation must be explicitly requested",
            ):
                validate_complete_phase_output(
                    development["lanes"][0],
                    production_geometry["lanes"][0],
                    development["measurement"],
                    layout=outcome.result["measurement"]["layout"],
                    read_proof=_read_common_proof,
                    complete_phase_validation_requested=False,
                )


if __name__ == "__main__":
    unittest.main()
