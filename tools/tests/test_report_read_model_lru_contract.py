"""The bounded read-model memo keeps recently reused proof objects."""

from dataclasses import dataclass
from enum import IntEnum
import unittest

from x5crop.report.read_models import typed_read_model
from x5crop.domain import FiniteInterval, PositiveInterval


class ReportReadModelLruContractTest(unittest.TestCase):
    def test_interval_values_keep_fields_types_and_independent_branches(self):
        class Limit(IntEnum):
            LOWER = 1
            UPPER = 2

        @dataclass(frozen=True)
        class AnnotatedInterval(FiniteInterval):
            label: str = "retained"

        for interval in (FiniteInterval(-1.0, 2.0), PositiveInterval(1.0, 2.0),
                         FiniteInterval(Limit.LOWER, Limit.UPPER)):
            with self.subTest(interval=interval):
                result = typed_read_model((interval, interval))
                self.assertEqual(result, [{"minimum": interval.minimum, "maximum": interval.maximum}] * 2)
                self.assertNotIsInstance(result[0]["minimum"], IntEnum)
                result[0]["minimum"] = 99
                self.assertEqual(result[1]["minimum"], interval.minimum)
        self.assertEqual(typed_read_model(AnnotatedInterval(1.0, 2.0)),
            {"minimum": 1.0, "maximum": 2.0, "label": "retained"})

    def test_recent_frozen_alias_survives_4096_entry_churn(self):
        value_reads = [0]

        @dataclass(frozen=True)
        class Model:
            value: int

            def __getattribute__(self, name):
                if name == "value":
                    value_reads[0] += 1
                return object.__getattribute__(self, name)

        target = Model(-1)
        value = (target, *(Model(index) for index in range(4096)), target, target)
        result = typed_read_model(value)

        self.assertEqual(len(result), 4099)
        self.assertEqual(result[0], {"value": -1})
        self.assertEqual(result[-2:], [{"value": -1}, {"value": -1}])
        # The first target is evicted by the 4096 distinct models. The next
        # target is inserted as the newest entry and the final alias is a hit.
        self.assertEqual(value_reads[0], 4098)

    def test_scalar_dict_copy_stays_independent_between_aliases(self):
        @dataclass(frozen=True)
        class Model:
            values: dict[str, int]

        model = Model({"left": 1, "right": 2})
        result = typed_read_model((model, model))

        result[0]["values"]["left"] = 99
        self.assertEqual(result[1]["values"], {"left": 1, "right": 2})


if __name__ == "__main__":
    unittest.main()
