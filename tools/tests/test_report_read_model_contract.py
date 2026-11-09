"""Read-model acceleration preserves values and independent report branches."""

from dataclasses import dataclass,make_dataclass
from enum import Enum, IntEnum
import unittest

from x5crop.report.read_models import typed_read_model,_model_layout


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

    def test_type_metadata_does_not_cache_mutable_values_or_override_conversion_precedence(self):
        @dataclass
        class Model:
            value: int

        @dataclass
        class MappingModel(dict):
            value: int=7

        class NamedString(str):pass
        class Binary(bytes):pass
        model=Model(1)
        self.assertEqual(typed_read_model(model),{'value':1})
        model.value=9
        self.assertEqual(typed_read_model(model),{'value':9})
        mapping=MappingModel();mapping['ignored_mapping_entry']=3
        self.assertEqual(typed_read_model(mapping),{'value':7})
        text=NamedString('fact')
        self.assertIs(typed_read_model(text),text)
        self.assertEqual(typed_read_model(Binary(b'abc')),'<bytes:3>')

    def test_type_cache_is_bounded_and_model_classes_stay_opaque_even_with_model_metaclasses(self):
        @dataclass
        class Meta(type):
            marker: int=5

        model=type.__new__(Meta,'Model',(),{})
        self.assertIs(typed_read_model(model),model)
        for index in range(300):
            cls=make_dataclass(f'Layout{index}',[('value',int)],frozen=True)
            self.assertEqual(typed_read_model(cls(index)),{'value':index})
        self.assertLessEqual(_model_layout.cache_info().currsize,256)
