"""The runtime version must match the packaged version.

It drifted once: pyproject said 0.3.1 while ``__version__`` still said 0.3.0,
so every dataset record produced by 0.3.1 was stamped with the old number.
"""

import pathlib
import re

import launchforensics


def test_version_matches_pyproject():
    text = pathlib.Path("pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match, "pyproject.toml has no version"
    assert launchforensics.__version__ == match.group(1)
