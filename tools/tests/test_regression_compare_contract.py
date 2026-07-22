from __future__ import annotations

from copy import deepcopy
import unittest

from tools.regression.compare import (
    ReportComparisonIdentity,
    compare_report_rows,
    report_key,
)
from tools.tests.test_output_read_model_contract import _record
from x5crop.report.identity import bind_runtime_facts


class RegressionCompareContractTest(unittest.TestCase):
    def test_comparison_identity_includes_page_and_request_configuration(self) -> None:
        first = _record()
        second_page = deepcopy(first)
        second_page["analysis_identity"]["source"]["page"] = 1
        second_page["analysis_identity"]["runtime_configuration"]["page"] = 1
        bind_runtime_facts(second_page)
        requested_count = deepcopy(first)
        requested_count["analysis_identity"]["runtime_configuration"][
            "requested_count"
        ] = 2
        bind_runtime_facts(requested_count)

        identities = {
            report_key(first),
            report_key(second_page),
            report_key(requested_count),
        }
        self.assertEqual(len(identities), 3)
        self.assertTrue(
            all(isinstance(identity, ReportComparisonIdentity) for identity in identities)
        )

    def test_duplicate_comparison_identity_is_rejected(self) -> None:
        row = _record()
        with self.assertRaises(ValueError):
            compare_report_rows((row, deepcopy(row)), (row,))


if __name__ == "__main__":
    unittest.main()
