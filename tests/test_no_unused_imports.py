"""Gate against unused imports (F401) re-accumulating (#264 / TD-20).

A one-time sweep removed 56 `imported but unused` sites across the tree; this
test keeps them from creeping back. It runs pyflakes over every tracked non-test
`*.py` and fails if any `imported but unused` remains. It is skipped only when
pyflakes isn't installed, so it actively pins the fix wherever the dev/CI
toolchain has pyflakes (the audit suite relies on it) without adding a hard
runtime dependency to requirements.txt.
"""
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _tracked_source_files():
    out = subprocess.check_output(
        ["git", "ls-files", "*.py"], text=True, cwd=REPO_ROOT)
    # tests/ may legitimately import names only for fixtures/side effects.
    return [f for f in out.split() if not f.startswith("tests/")]


class TestNoUnusedImports:
    def test_no_f401_in_tracked_source(self):
        try:
            import pyflakes  # noqa: F401
        except ImportError:
            pytest.skip("pyflakes not installed")

        files = _tracked_source_files()
        result = subprocess.run(
            [sys.executable, "-m", "pyflakes", *files],
            capture_output=True, text=True, cwd=REPO_ROOT)
        offenders = [ln for ln in result.stdout.splitlines()
                     if "imported but unused" in ln]
        assert not offenders, (
            "Unused imports (F401) re-accumulated — remove them (#264):\n"
            + "\n".join(offenders))
