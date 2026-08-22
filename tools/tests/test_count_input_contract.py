from __future__ import annotations

from tools.tests.current_only_support import *


class CountInputContractTest(unittest.TestCase):
    def test_cohort_count_is_explicit_and_filename_independent(self) -> None:
        filename_only = {
            "source_relative_path": "Test/135/partial/pass_X5_99_00001.tif",
            "format_id": "135",
        }
        with self.assertRaisesRegex(ValueError, "explicit positive count"):
            cohort_slot_count(filename_only)
        filename_only["count"] = 3
        self.assertEqual(cohort_slot_count(filename_only), 3)

        def validate(rows: tuple[dict[str, object], ...]) -> None:
            with TemporaryDirectory() as temporary:
                path = Path(temporary) / "cohort.jsonl"
                path.write_text(
                    "".join(json.dumps(row) + "\n" for row in rows),
                    encoding="utf-8",
                )
                validate_cohort_counts((path,))

        validate(({
            "sample_id": "source",
            "source_sha256": "a" * 64,
            "format_id": "135",
            "count": 6,
        },))
        with self.assertRaisesRegex(ValueError, "conflicting format/count"):
            validate((
                {
                    "sample_id": "first",
                    "source_sha256": "c" * 64,
                    "format_id": "135",
                    "count": 6,
                },
                {
                    "sample_id": "alias",
                    "source_sha256": "c" * 64,
                    "format_id": "135",
                    "count": 5,
                },
            ))

    def test_count_request_carries_only_user_intent(self) -> None:
        explicit = SlotCountRequest(3)
        default = SlotCountRequest(None)
        self.assertEqual(explicit.user_count, 3)
        self.assertEqual(explicit.authority.value, "user_explicit_count")
        self.assertIsNone(default.user_count)
        self.assertEqual(default.authority.value, "matched_holder_default_count")
        with self.assertRaises(ValueError):
            SlotCountRequest(0)
        with self.assertRaises(TypeError):
            SlotCountRequest(True)  # type: ignore[arg-type]

        parser = build_parser()
        option_strings = {
            value
            for action in parser._actions
            for value in action.option_strings
        }
        self.assertNotIn("--strip", option_strings)
        self.assertNotIn("--auto-count", option_strings)
        with (
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit),
        ):
            parser.parse_args(["input.tif", "--format", "135", "--count", "auto"])

    def test_noninteractive_matched_holder_count_conflict_exits_two(self) -> None:
        with TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.tif"
            source.touch()
            holder = mock.Mock(
                full_count=2,
                profile=mock.Mock(profile_id="120_wide_188_5"),
            )
            with (
                mock.patch(
                    "x5crop.runtime.bootstrap.read_tiff_profile",
                    return_value=(mock.Mock(shape=(100, 200, 3)), ()),
                ),
                mock.patch(
                    "x5crop.runtime.bootstrap.observe_scan_canvas",
                    return_value=mock.Mock(),
                ),
                mock.patch(
                    "x5crop.runtime.bootstrap.matched_holder_from_evidence",
                    return_value=holder,
                ),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(
                    main([
                        str(source),
                        "--format",
                        "120-67",
                        "--count",
                        "3",
                    ]),
                    2,
                )

    def test_standard_job_default_and_caps_are_distinct(self) -> None:
        self.assertEqual(STANDARD_JOB_DEFAULT, 1)
        self.assertEqual(STANDARD_JOB_LIMIT, 3)
        parser = build_parser()
        default_options = options_from_args(
            parser.parse_args(["input.tif", "--format", "135"])
        )
        explicit_two_options = options_from_args(
            parser.parse_args(["input.tif", "--format", "135", "--jobs", "2"])
        )
        normal_four_options = options_from_args(
            parser.parse_args(["input.tif", "--format", "135", "--jobs", "4"])
        )
        self.assertEqual(default_options.jobs, 1)
        with mock.patch(
            "x5crop.runtime.bootstrap.iter_input_files",
            return_value=[Path("input.tif")],
        ):
            self.assertEqual(runtime_invocation_from_options(default_options).config.jobs, 1)
            self.assertEqual(runtime_invocation_from_options(explicit_two_options).config.jobs, 2)
            self.assertEqual(runtime_invocation_from_options(normal_four_options).config.jobs, 3)

    def test_format_and_interactive_use_one_count_contract(self) -> None:
        for spec in format_spec.__globals__["FORMATS"].values():
            self.assertFalse(hasattr(spec, "partial_mode_supported"))
            self.assertFalse(hasattr(spec, "interactive_partial_counts"))
        with (
            mock.patch("builtins.input", side_effect=("dual", "", "", "n")),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            options = interactive_options()
        self.assertEqual(options.format_id, "135-dual")
        self.assertIsNone(options.requested_count)
        self.assertEqual(options.deskew_mode, DeskewMode.AUTO)
        self.assertFalse(hasattr(options, "strip_mode"))


if __name__ == "__main__":
    unittest.main()
