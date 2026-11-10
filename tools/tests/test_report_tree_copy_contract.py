"""Report copies preserve opaque leaves and encoding never appends a prefix."""
from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from x5crop.report.outputs import append_report_jsonl
from x5crop.report.read_models import typed_read_model


class ReportTreeCopyContractTest(unittest.TestCase):
    def test_nested_aliases_keep_independent_containers_and_original_opaque_enum_values(self):
        class Opaque(Enum):
            VALUE = {'keep': ['identity']}

        @dataclass(frozen=True)
        class Model:
            values: tuple

        leaf = Model(({'nested': [{'value': 2}, [3, 4]]}, Opaque.VALUE))
        branches = typed_read_model((leaf, leaf, leaf))
        branches[0]['values'][0]['nested'][0]['value'] = 99
        branches[1]['values'][0]['nested'][1].append(5)
        self.assertEqual(branches[2]['values'][0], {'nested': [{'value': 2}, [3, 4]]})
        for branch in branches:
            self.assertIs(branch['values'][1], Opaque.VALUE.value)

    def test_encoding_retains_unicode_and_alias_values_and_rejects_recursive_records_before_append(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary)/'report.jsonl'
            shared = {'text': '原始边界', 'values': [1, 2., None]}
            record = {'first': shared, 'second': shared}
            append_report_jsonl(path, record)
            before = path.read_bytes()
            self.assertEqual(json.loads(before), record)
            self.assertIn('原始边界'.encode(), before)
            recursive = {'cycle': None}
            recursive['cycle'] = recursive
            with self.assertRaises((RecursionError, ValueError)):
                append_report_jsonl(path, recursive)
            self.assertEqual(path.read_bytes(), before)
