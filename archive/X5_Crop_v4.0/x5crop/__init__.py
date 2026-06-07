"""X5 Crop package.

V4 keeps the public launcher workflow intact while moving the implementation
behind importable package modules. The first V4 step intentionally preserves
the V3.9 behavior and exposes stable module boundaries for future extraction.
"""

from .core import SCRIPT_NAME, VERSION

__all__ = ["SCRIPT_NAME", "VERSION"]
