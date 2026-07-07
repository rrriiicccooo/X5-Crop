from __future__ import annotations

from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SourceNamingContractTest(unittest.TestCase):
    def test_active_source_has_no_late_or_auxiliary_outer_terms(self) -> None:
        banned = ("late_outer", "auxiliary_outer", 'phase="late"', 'phase="auxiliary"')
        offenders: list[str] = []
        for path in (PROJECT_ROOT / "x5crop").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for term in banned:
                if term in text:
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {term}")

        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
