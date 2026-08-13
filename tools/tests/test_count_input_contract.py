from __future__ import annotations

from tools.tests.current_only_support import *


class CountInputContractTest(unittest.TestCase):
    def test_cohort_count_authority_is_explicit_and_filename_independent(
        self,
    ) -> None:
        filename_only = {
            "source_relative_path": "Test/135/partial/pass_X5_99_00001.tif",
            "strip_mode": "partial",
        }
        self.assertIsNone(confirmed_slot_count(filename_only))
        with self.assertRaisesRegex(ValueError, "removed requested_count"):
            confirmed_slot_count({**filename_only, "requested_count": 3})
        filename_only["confirmed_slot_count"] = 3
        self.assertEqual(confirmed_slot_count(filename_only), 3)

        def validate(rows: tuple[dict[str, object], ...]) -> None:
            with TemporaryDirectory() as temporary:
                path = Path(temporary) / "cohort.jsonl"
                path.write_text(
                    "".join(json.dumps(row) + "\n" for row in rows),
                    encoding="utf-8",
                )
                validate_count_authority((path,))

        validate(
            (
                {
                    "sample_id": "full",
                    "source_sha256": "a" * 64,
                    "strip_mode": "full",
                    "count_authority": "matched_holder_full_count",
                },
                {
                    "sample_id": "partial",
                    "source_sha256": "b" * 64,
                    "strip_mode": "partial",
                    "confirmed_slot_count": 3,
                    "count_authority": "user_explicit_partial_count",
                },
            )
        )
        with self.assertRaisesRegex(ValueError, "full cohort"):
            validate(
                (
                    {
                        "sample_id": "invalid-full",
                        "source_sha256": "c" * 64,
                        "strip_mode": "full",
                        "confirmed_slot_count": 6,
                        "count_authority": "matched_holder_full_count",
                    },
                )
            )
        with self.assertRaisesRegex(ValueError, "conflicting mode/count"):
            validate(
                (
                    {
                        "sample_id": "first",
                        "source_sha256": "d" * 64,
                        "strip_mode": "full",
                        "count_authority": "matched_holder_full_count",
                    },
                    {
                        "sample_id": "alias",
                        "source_sha256": "d" * 64,
                        "strip_mode": "partial",
                        "confirmed_slot_count": 5,
                        "count_authority": "user_explicit_partial_count",
                    },
                )
            )

    def test_count_request_carries_only_user_intent(self) -> None:
        explicit = SlotCountRequest.from_user_input("partial", 3)
        full = SlotCountRequest.from_user_input("full", None)
        self.assertEqual(explicit.strip_mode, "partial")
        self.assertEqual(explicit.user_count, 3)
        self.assertEqual(full.strip_mode, "full")
        self.assertIsNone(full.user_count)
        with self.assertRaises(ValueError):
            SlotCountRequest.from_user_input("partial", None)
        with self.assertRaises(ValueError):
            SlotCountRequest.from_user_input("full", 6)
        parser = build_parser()
        option_strings = {
            value
            for action in parser._actions
            for value in action.option_strings
        }
        self.assertNotIn("--auto-count", option_strings)
        with (
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit),
        ):
            parser.parse_args(
                ["input.tif", "--format", "135", "--strip", "partial", "--count", "auto"]
            )
        with (
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit),
        ):
            parser.parse_args(
                ["input.tif", "--format", "135", "--auto-count"]
            )

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
                    main(
                        [
                            str(source),
                            "--format",
                            "120-67",
                            "--strip",
                            "partial",
                            "--count",
                            "3",
                        ]
                    ),
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
            parser.parse_args(
                ["input.tif", "--format", "135", "--jobs", "2"]
            )
        )
        normal_four_options = options_from_args(
            parser.parse_args(
                ["input.tif", "--format", "135", "--jobs", "4"]
            )
        )
        self.assertEqual(default_options.jobs, 1)

        with (
            mock.patch(
                "x5crop.runtime.bootstrap.iter_input_files",
                return_value=[Path("input.tif")],
            ),
        ):
            self.assertEqual(
                runtime_invocation_from_options(default_options).config.jobs,
                1,
            )
            self.assertEqual(
                runtime_invocation_from_options(explicit_two_options).config.jobs,
                2,
            )
            self.assertEqual(
                runtime_invocation_from_options(normal_four_options).config.jobs,
                3,
            )

    def test_strip_handling_has_one_current_contract(self) -> None:
        for format_id in ("135", "half", "xpan", "120-645", "120-66", "120-67"):
            self.assertEqual(
                format_spec(format_id).interactive_partial_counts,
                tuple(range(1, format_spec(format_id).maximum_full_count + 1)),
            )
        self.assertFalse(
            format_spec("135-dual").partial_mode_supported
        )
        self.assertEqual(
            format_spec("135-dual").interactive_partial_counts,
            (),
        )

    def test_interactive_dual_format_never_enters_partial_count_prompt(
        self,
    ) -> None:
        with (
            mock.patch("builtins.input", side_effect=("dual", "n")),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            options = interactive_options()
        self.assertEqual(options.format_id, "135-dual")
        self.assertEqual(options.strip_mode, "full")
        self.assertIsNone(options.requested_count)


if __name__ == "__main__":
    unittest.main()
