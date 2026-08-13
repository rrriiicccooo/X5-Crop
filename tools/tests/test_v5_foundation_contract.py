from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

import numpy as np

from x5crop.io.orientation import (
    canonicalize_orientation,
    orientation_mapping,
)
from x5crop.output.naming import (
    MAX_COMPONENT_UTF16_UNITS,
    PortableNameError,
    is_windows_reserved_name,
    portable_component,
    utf16_units,
    validate_portable_component,
)
from x5crop.output.publication import FreshOutputDirectory, FreshOutputError


class OrientationFoundationContractTests(unittest.TestCase):
    def test_all_orientation_tags_bake_the_expected_visual_raster(self) -> None:
        raw = np.asarray([[1, 2, 3], [4, 5, 6]], dtype=np.uint16)
        expected = {
            1: [[1, 2, 3], [4, 5, 6]],
            2: [[3, 2, 1], [6, 5, 4]],
            3: [[6, 5, 4], [3, 2, 1]],
            4: [[4, 5, 6], [1, 2, 3]],
            5: [[1, 4], [2, 5], [3, 6]],
            6: [[4, 1], [5, 2], [6, 3]],
            7: [[6, 3], [5, 2], [4, 1]],
            8: [[3, 6], [2, 5], [1, 4]],
        }
        for tag, visual in expected.items():
            with self.subTest(orientation=tag):
                canonical, mapping = canonicalize_orientation(raw, "YX", tag)
                self.assertEqual(canonical.tolist(), visual)
                self.assertTrue(canonical.flags.c_contiguous)
                for y in range(raw.shape[0]):
                    for x in range(raw.shape[1]):
                        cx, cy = mapping.map_raw_point(float(x), float(y))
                        rx, ry = mapping.map_canonical_point(cx, cy)
                        self.assertEqual((rx, ry), (float(x), float(y)))
                        self.assertEqual(canonical[int(cy), int(cx)], raw[y, x])

    def test_invalid_orientation_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            orientation_mapping(9, 10, 20)


class PortableOutputNameContractTests(unittest.TestCase):
    def test_windows_reserved_names_include_console_aliases(self) -> None:
        for value in (
            "CON",
            "NUL.txt",
            "CONIN$",
            "CONOUT$.tif",
            "COM1.jpg",
            "COM¹.jpg",
            "LPT9",
            "LPT³.dat",
        ):
            with self.subTest(value=value):
                self.assertTrue(is_windows_reserved_name(value))

    def test_python_313_windows_reserved_rules_cross_check_frozen_table(
        self,
    ) -> None:
        if os.name != "nt" or not hasattr(os.path, "isreserved"):
            self.skipTest("requires Windows Python 3.13+")
        for value in (
            "CON",
            "NUL.txt",
            "CONIN$",
            "CONOUT$.tif",
            "COM1.jpg",
            "COM¹.jpg",
            "LPT9",
            "LPT³.dat",
            "bad<name.tif",
            "trailing. ",
        ):
            with self.subTest(value=value):
                self.assertTrue(os.path.isreserved(value))
                with self.assertRaises(PortableNameError):
                    validate_portable_component(value)

    def test_generated_names_are_portable_and_bounded(self) -> None:
        name = portable_component(
            "CON:<bad>?" + "照片" * 100,
            input_ordinal=7,
            suffix="_02.tif",
        )
        self.assertLessEqual(utf16_units(name.value), MAX_COMPONENT_UTF16_UNITS)
        self.assertTrue(name.value.endswith("_02.tif"))
        self.assertIn("~0007", name.value)
        self.assertNotIn(":", name.value)
        self.assertNotIn("?", name.value)

    def test_explicit_output_leaf_is_never_silently_rewritten(self) -> None:
        with self.assertRaises(PortableNameError):
            validate_portable_component("NUL")
        with self.assertRaises(PortableNameError):
            validate_portable_component("trailing. ")

    def test_casefold_collision_is_detectable_before_decode(self) -> None:
        first = portable_component("Photo", input_ordinal=1, suffix="_01.tif")
        second = portable_component("photo", input_ordinal=2, suffix="_01.tif")
        self.assertEqual(first.collision_key, second.collision_key)


class FreshOutputFoundationContractTests(unittest.TestCase):
    def test_existing_output_is_never_traversed_or_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "output"
            target.mkdir()
            keep = target / "unknown.txt"
            keep.write_text("keep", encoding="utf-8")
            with self.assertRaises(FreshOutputError):
                with FreshOutputDirectory(target):
                    pass
            self.assertEqual(keep.read_text(encoding="utf-8"), "keep")

    def test_only_completed_staging_is_published(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "output"
            with FreshOutputDirectory(target) as publication:
                assert publication.staging is not None
                (publication.staging / "crop.tif").write_bytes(b"complete")
                self.assertFalse(target.exists())
                publication.publish()
            self.assertEqual((target / "crop.tif").read_bytes(), b"complete")


if __name__ == "__main__":
    unittest.main()
