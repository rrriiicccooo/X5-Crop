from __future__ import annotations

import os
from pathlib import Path
import sys


def main() -> int:
    if len(sys.argv) != 3:
        return 2
    target = Path(sys.argv[1])
    previous = Path(sys.argv[2])
    os.rename(target, previous)
    os._exit(91)


if __name__ == "__main__":
    raise SystemExit(main())
