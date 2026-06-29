"""X5 Crop package.

V4 keeps the public launcher workflow intact while splitting the implementation
into focused importable modules. The architecture changes boldly, while the
validated V3.9 crop results remain the compatibility target.
"""

from .core import SCRIPT_NAME, VERSION

__all__ = ["SCRIPT_NAME", "VERSION"]
