#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Command-line entry point for X5 Crop.

The implementation lives in :mod:`x5crop.core`. Keeping this file thin lets
the user keep launching ``X5_Crop.py`` while V4 moves the internals into a
package that can be tested and refactored more safely.
"""

from x5crop.core import main


if __name__ == "__main__":
    raise SystemExit(main())
