#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Command-line entry point for X5 Crop.

The user-facing ``X5_Crop.py`` launcher stays stable while the implementation
lives in focused modules under :mod:`x5crop`.
"""

from x5crop.entry.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
