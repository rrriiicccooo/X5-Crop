#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compatibility exports for X5 Crop V4.

The implementation is split across package modules. Importing from
``x5crop.core`` remains supported for archived scripts and older tooling.
"""

from .common import *
from .evidence import *
from .io import *
from .geometry import *
from .detection.pipeline import *
from .deskew import *
from .debug.render import *
from .reports import *
from .cli import *


if __name__ == "__main__":
    raise SystemExit(main())
