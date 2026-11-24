"""The report write view reuses immutable facts without changing the JSON tree."""

import json
import math
import pickle
import unittest
from dataclasses import dataclass
from enum import Enum, IntEnum
from pathlib import Path
from tempfile import TemporaryDirectory

from x5crop.domain import FiniteInterval, PositiveInterval
from x5crop.report.outputs import append_report_jsonl
from x5crop.report.read_models import _report_write_view, typed_read_model


@dataclass(frozen=True)
class _PickleNode:
    value: int
    facts: dict


def _json_text(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=True,
                      separators=(",", ":"))


class ReportWriteViewContractTest(unittest.TestCase):
    def test_public_copies_branches_while_write_view_reuses_frozen_template(self):
        @dataclass(frozen=True)
        class FrozenFacts:
            payload: dict

        model = FrozenFacts({
            "说明": "边界",
            "values": [math.nan, math.inf, -math.inf],
        })
        public = typed_read_model((model, model))
        view = _report_write_view((model, model))

        self.assertIsNot(public[0], public[1])
        self.assertIsNot(public[0]["payload"], public[1]["payload"])
        self.assertEqual(_json_text(public), _json_text(view))
        self.assertIn("边界", _json_text(view))
        self.assertIn("NaN", _json_text(view))
        self.assertIn("Infinity", _json_text(view))
        public[0]["payload"]["values"].append("local")
        self.assertEqual(public[1]["payload"]["values"],
                         [math.nan, math.inf, -math.inf])
        self.assertIs(view[0], view[1])

    def test_public_and_private_calls_do_not_share_returned_mutable_trees(self):
        @dataclass(frozen=True)
        class Facts:
            values: dict

        source = Facts({"items": [1, 2]})
        first_public = typed_read_model(source)
        second_public = typed_read_model(source)
        first_view = _report_write_view(source)
        second_view = _report_write_view(source)

        self.assertIsNot(first_public, second_public)
        self.assertIsNot(first_public["values"], second_public["values"])
        self.assertIsNot(first_view, second_view)
        self.assertIsNot(first_view["values"], second_view["values"])
        first_view["values"]["items"].append(3)
        self.assertEqual(second_view["values"], {"items": [1, 2]})

    def test_write_view_memoizes_only_frozen_dataclasses(self):
        @dataclass(frozen=True)
        class FrozenFacts:
            value: int

        @dataclass
        class MutableFacts:
            value: int

        frozen = FrozenFacts(4)
        mutable = MutableFacts(4)
        result = _report_write_view((frozen, frozen, mutable, mutable))

        self.assertIs(result[0], result[1])
        self.assertIsNot(result[2], result[3])
        self.assertEqual(result[2], result[3])

    def test_bytes_enum_opaque_values_private_fields_and_mapping_precedence(self):
        @dataclass(frozen=True)
        class Nested:
            value: int

        nested = Nested(8)

        class Opaque(Enum):
            VALUE = [nested, {"keep": "as-is"}]

        class Binary(bytes):
            pass

        @dataclass(frozen=True)
        class Model:
            bytes_value: bytes
            enum_value: Opaque
            mapping: dict
            _private: str = "hidden"

        @dataclass
        class MappingModel(dict):
            value: int = 7

        mapping_model = MappingModel()
        mapping_model["ignored_mapping_entry"] = 3
        source = Model(
            Binary(b"abcde"),
            Opaque.VALUE,
            {1: "one", (2, 3): "tuple-key"},
        )
        for convert in (typed_read_model, _report_write_view):
            with self.subTest(convert=convert.__name__):
                result = convert(source)
                self.assertEqual(result["bytes_value"], "<bytes:5>")
                self.assertIs(result["enum_value"], Opaque.VALUE.value)
                self.assertIs(result["enum_value"][0], nested)
                self.assertEqual(result["mapping"],
                                 {"1": "one", "(2, 3)": "tuple-key"})
                self.assertNotIn("_private", result)
                self.assertEqual(convert(mapping_model), {"value": 7})

        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "report.jsonl"
            append_report_jsonl(path, {"ok": "opaque baseline"})
            before = path.read_bytes()
            opaque_record = _report_write_view(source)
            with self.assertRaises(TypeError):
                append_report_jsonl(path, opaque_record)
            self.assertEqual(path.read_bytes(), before)

    def test_mutating_source_containers_does_not_rewrite_view_opaque_leaf_remains_shared(self):
        opaque_items = ["original"]

        class Opaque(Enum):
            VALUE = opaque_items

        @dataclass(frozen=True)
        class Facts:
            payload: dict
            opaque: Opaque

        payload = {"items": [1, 2]}
        view = _report_write_view(Facts(payload, Opaque.VALUE))
        payload["items"].append(3)
        payload["new"] = "not copied back"

        self.assertEqual(view["payload"], {"items": [1, 2]})
        self.assertIs(view["opaque"], opaque_items)
        opaque_items.append("changed in-place")
        self.assertEqual(view["opaque"], ["original", "changed in-place"])

    def test_interval_subclasses_and_non_scalar_endpoints_keep_existing_semantics(self):
        class Limit(IntEnum):
            LOWER = 1
            UPPER = 2

        @dataclass(frozen=True)
        class AnnotatedInterval(FiniteInterval):
            label: str = "retained"

        values = (
            FiniteInterval(Limit.LOWER, Limit.UPPER),
            PositiveInterval(1.0, 2.0),
            AnnotatedInterval(1.0, 2.0),
        )
        for convert in (typed_read_model, _report_write_view):
            with self.subTest(convert=convert.__name__):
                result = convert(values)
                self.assertEqual(result[0], {"minimum": 1, "maximum": 2})
                self.assertNotIsInstance(result[0]["minimum"], IntEnum)
                self.assertEqual(result[1], {"minimum": 1.0, "maximum": 2.0})
                self.assertEqual(result[2], {
                    "minimum": 1.0,
                    "maximum": 2.0,
                    "label": "retained",
                })

    def test_lru_evicts_oldest_but_keeps_recent_hit_and_is_call_local(self):
        value_reads = []

        @dataclass(frozen=True)
        class Model:
            value: int

            def __getattribute__(self, name):
                if name == "value":
                    value_reads.append(object.__getattribute__(self, name))
                return object.__getattribute__(self, name)

        target = Model(-1)
        recent = Model(-2)
        source = (target, recent, *(Model(index) for index in range(4095)),
                  recent, target)
        result = _report_write_view(source)

        self.assertEqual(len(result), 4099)
        self.assertEqual(value_reads.count(-1), 2)
        self.assertEqual(value_reads.count(-2), 1)
        self.assertIsNot(_report_write_view(target), _report_write_view(target))

    def test_shared_frozen_dag_is_pickleable_and_json_value_equivalent(self):
        node = _PickleNode(7, {"说明": "共享事实", "values": [1, 2]})
        view = _report_write_view({"left": node, "right": node})

        self.assertIs(view["left"], view["right"])
        restored = pickle.loads(pickle.dumps(view))
        self.assertEqual(restored, view)
        self.assertIs(restored["left"], restored["right"])
        self.assertEqual(json.loads(_json_text(view)), view)
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "report.jsonl"
            append_report_jsonl(path, view)
            self.assertEqual(path.read_bytes(),
                             (_json_text(view) + "\n").encode("utf-8"))
            self.assertIn("共享事实".encode("utf-8"), path.read_bytes())
            self.assertEqual(json.loads(path.read_bytes()), {
                "left": view["left"],
                "right": view["right"],
            })

    def test_non_encodable_opaque_and_recursive_records_leave_existing_jsonl_unchanged(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "report.jsonl"
            append_report_jsonl(path, {"ok": "已写入"})
            before = path.read_bytes()

            opaque = _report_write_view({"opaque": object()})
            with self.assertRaises(TypeError):
                append_report_jsonl(path, opaque)
            self.assertEqual(path.read_bytes(), before)

            for convert in (typed_read_model, _report_write_view):
                recursive_dict = {"cycle": None}
                recursive_dict["cycle"] = recursive_dict
                with self.assertRaises((RecursionError, ValueError)):
                    convert(recursive_dict)

                recursive_list = []
                recursive_list.append(recursive_list)
                with self.assertRaises((RecursionError, ValueError)):
                    convert(recursive_list)

            recursive = {"cycle": None}
            recursive["cycle"] = recursive
            with self.assertRaises((RecursionError, ValueError)):
                append_report_jsonl(path, recursive)
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
