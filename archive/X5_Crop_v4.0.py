#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Command-line entry point for X5 Crop.

V4 keeps the user-facing ``X5_Crop.py`` launcher stable while the real
implementation lives in focused modules under :mod:`x5crop`.
"""

from pathlib import Path
import sys

ARCHIVE_PACKAGE_ROOT = Path(__file__).with_suffix("")
if str(ARCHIVE_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(ARCHIVE_PACKAGE_ROOT))

from x5crop.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
