"""Optional prefix sharing reserves the original source pool first."""
from dataclasses import replace
import unittest
from unittest.mock import patch

import numpy as np

from tools.tests.test_native_trace_continuity_contract import _case
from tools.tests import test_registered_prefix_reuse_contract as prefix_contract
from x5crop.detection.photo_geometry import registered_transition_measurement as owner
from x5crop.detection.photo_geometry.registered_measurement import _premeasure_registered_windows
from x5crop.detection.photo_geometry.coarse_strip_support import _measure_coarse_short_trace_lattice
from x5crop.detection.photo_geometry.model import QueryPurpose, PHOTO_BOUNDARY_MEASUREMENT_SPEC as SPEC


class ScalarPrefixSourceBudgetContractTest(unittest.TestCase):
    assert_exact = prefix_contract.RegisteredPrefixReuseContractTest.assert_exact

    def test_registered_baseline_reserves_sharing_before_prefix_creation(self):
        field, _base, measured = _case()
        baseline = replace(measured[0].query, purpose=QueryPurpose.SEQUENCE_BASELINE)
        window = replace(measured[-1].query, purpose=QueryPurpose.SEQUENCE_ANCHOR_WINDOW)
        with patch.object(owner, "_WindowPrefix", side_effect=AssertionError("no source capacity for cache")):
            old, retained, peak = _premeasure_registered_windows(field, baseline, (window,), SPEC,
                prefix_cache_budget_bytes=0)
        new, new_retained, new_peak = _premeasure_registered_windows(field, baseline, (window,), SPEC)
        self.assertEqual(new_retained, retained)
        self.assertEqual(new_peak-peak, owner.window_prefix_cache_bytes(field.source_extent.height))
        for key in old:
            self.assert_exact(new[key], old[key])
        required = owner.window_prefix_cache_bytes(field.source_extent.height)
        first_trace_budget = owner.scalar_trace_buffer_reservation(field.source_extent.height,
            field.source_extent.height, prefix_cache_capacity_bytes=required)
        with patch.object(owner, "_WindowPrefix", wraps=owner._WindowPrefix) as prepared:
            _premeasure_registered_windows(field, baseline, (window,), SPEC,
                prefix_cache_budget_bytes=first_trace_budget)
        self.assertEqual(prepared.call_count, 2)  # Earlier traces consume capacity before the next call.

    def test_native_coarse_caller_accounts_live_inputs_and_earlier_traces(self):
        field, _base, measured = _case()
        query = replace(measured[0].query, purpose=QueryPurpose.COARSE_STRIP_SHORT)
        samples = np.stack([field.source_gray[:, trace] for trace in query.trace_positions_px])
        with patch.object(owner, "_WindowPrefix", side_effect=AssertionError("no source capacity for native cache")):
            old, peak = _measure_coarse_short_trace_lattice(samples, query,
                source_rgb=field.source_rgb, prefix_cache_budget_bytes=0)
        new, new_peak = _measure_coarse_short_trace_lattice(samples, query, source_rgb=field.source_rgb)
        self.assert_exact(new, old)
        self.assertEqual(new_peak-peak, owner.window_prefix_cache_bytes(field.source_extent.height))
