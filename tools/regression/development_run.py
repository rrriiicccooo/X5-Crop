"""Run the current detector with development report detail enabled."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from x5crop.runtime.bootstrap import run_options
from x5crop.runtime.options import RuntimeOptions


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--format", required=True)
    parser.add_argument("--count", type=int)
    parser.add_argument("--layout", default="auto")
    args = parser.parse_args(argv)
    return run_options(
        RuntimeOptions(
            input_path=args.input.resolve(),
            output_dir=args.output.resolve(),
            format_id=args.format,
            layout=args.layout,
            requested_count=args.count,
            debug_analysis=False,
            jobs=1,
            development_detail=True,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
