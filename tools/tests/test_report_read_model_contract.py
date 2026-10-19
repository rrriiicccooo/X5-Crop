"""Read-model acceleration preserves values and independent report branches."""

from dataclasses import dataclass
from enum import Enum, IntEnum
import unittest

from x5crop.report.read_models import typed_read_model


class ReportReadModelContractTest(unittest.TestCase):
    def test_shared_frozen_models_produce_independent_trees_and_calls(self):
        @dataclass(frozen=True)
        class Model:
            facts: tuple
            _internal: int = 7

        model = Model(({1: [2, 3]},))
        result = typed_read_model((model, model))
        self.assertEqual(result, [{"facts": [{"1": [2, 3]}]}] * 2)
        result[0]["facts"][0]["1"][0] = 99
        self.assertEqual(result[1]["facts"][0]["1"], [2, 3])
        self.assertEqual(typed_read_model(model), {"facts": [{"1": [2, 3]}]})

    def test_enum_bytes_private_and_opaque_leaf_semantics_are_preserved(self):
        class Number(IntEnum):
            ONE = 1

        class Container(Enum):
            VALUE = ["opaque"]

        @dataclass(frozen=True)
        class Model:
            values: tuple

        leaf = object()
        model = Model((Number.ONE, Container.VALUE, b"abc", leaf))
        result = typed_read_model((model, model))
        for branch in result:
            self.assertEqual(branch["values"][:3], [1, ["opaque"], "<bytes:3>"])
            self.assertIs(branch["values"][1], Container.VALUE.value)
            self.assertIs(branch["values"][3], leaf)
        self.assertIs(typed_read_model(Model), Model)
