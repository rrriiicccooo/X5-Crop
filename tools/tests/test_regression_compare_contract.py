from __future__ import annotations

from copy import deepcopy
import unittest

from tools.regression.compare import (
    ReportComparisonIdentity,
    compare_report_rows,
    report_key,
)
from tools.tests.test_output_read_model_contract import _record


class RegressionCompareContractTest(unittest.TestCase):
    def test_comparison_identity_includes_page_and_request_configuration(self) -> None:
        first = _record()
        second_page = deepcopy(first)
        second_page["analysis_reuse_signature"]["source"]["page"] = 1
        second_page["analysis_reuse_signature"]["config"]["page"] = 1
        second_deskew = deepcopy(first)
        second_deskew["analysis_reuse_signature"]["config"]["deskew"] = "on"

        identities = {
            report_key(first),
            report_key(second_page),
            report_key(second_deskew),
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
