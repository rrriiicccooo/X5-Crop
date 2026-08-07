from __future__ import annotations

import os


THREAD_ENVIRONMENT_KEYS = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)


def configure_numeric_threads() -> None:
    for key in THREAD_ENVIRONMENT_KEYS:
        os.environ[key] = "1"
    try:
        import cv2

        cv2.setNumThreads(1)
    except ImportError:
        pass


def thread_identity() -> dict[str, object]:
    try:
        import cv2

        opencv_threads: int | None = int(cv2.getNumThreads())
    except ImportError:
        opencv_threads = None
    return {
        "x5crop_source_workers": "--jobs",
        "opencv_threads": opencv_threads,
        "environment": {key: os.environ.get(key) for key in THREAD_ENVIRONMENT_KEYS},
    }
