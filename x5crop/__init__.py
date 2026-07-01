"""X5 Crop package.

The public launcher workflow stays simple while the implementation is split
into focused importable modules. Architecture changes should remain regression
compatible with the validated crop behavior.
"""

from .app_info import SCRIPT_NAME, VERSION

__all__ = ["SCRIPT_NAME", "VERSION"]
