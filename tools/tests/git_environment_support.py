"""Keep temporary Git repositories independent of the invoking hook."""

from contextlib import contextmanager
import os
import subprocess
from unittest.mock import patch


@contextmanager
def isolated_git_environment():
    local_names = subprocess.run(
        ("git", "rev-parse", "--local-env-vars"),
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    ).stdout.splitlines()
    environment = {key: value for key, value in os.environ.items() if key not in local_names}
    with patch.dict(os.environ, environment, clear=True):
        yield
