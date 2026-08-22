from __future__ import annotations

import contextlib
import io
import json
from dataclasses import fields
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from tools.release.manifest import RELEASE_FILES, RELEASE_PATHS
from tools.release.standalone import read_sources
from tools.regression.cohort_count import (
    cohort_slot_count,
    validate_cohort_counts,
)
from x5crop.configuration.model import (
    SlotCountRequest,
)
from x5crop.detection.candidate.assessment.candidate_gate import (
    candidate_gate_assessment,
)
from x5crop.detection.decision.decision_gate import apply_decision_gate
from x5crop.detection.candidate.assessment.model import (
    CANDIDATE_GATE_CHECK_CODES,
)
from x5crop.detection.gate_checks import GateGap, TypedAssessment
from x5crop.domain import EvidenceState
from x5crop.entry.cli import build_parser, main, options_from_args
from x5crop.entry.interactive import interactive_options
from x5crop.formats import format_spec
from x5crop.report.identity import (
    REPORT_SCHEMA_ID,
    REPORT_SCHEMA_REVISION,
)
from x5crop.report.read_models import gate_check_read_model
from x5crop.run_config import DESKEW_CHOICES, DeskewMode, RunConfig
from x5crop.runtime.bootstrap import runtime_invocation_from_options
from x5crop.runtime.limits import (
    STANDARD_JOB_DEFAULT,
    STANDARD_JOB_LIMIT,
)
from x5crop.runtime.options import RuntimeOptions


ROOT = Path(__file__).resolve().parents[2]

# Current-only contracts share repository and CLI fixtures.
__all__ = tuple(name for name in globals() if not name.startswith("__"))
