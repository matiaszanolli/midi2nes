"""Shared filesystem-write utilities for MIDI2NES.

Lives in core/ (not exporter/, where atomic_write_text originated) so any
module -- exporter, nes, dpcm_sampler, whatever else -- can reach it without
introducing a reverse dependency on exporter/, which itself already imports
from nes/ (#456/SAFE-2026-08-21-2).
"""

import os
import tempfile


def atomic_write_text(output_path, content):
    """Write `content` to `output_path` atomically (#385/SAFE-2026-07-19-3).

    The full output is already assembled in memory before this is called, so
    the only failure window is the write itself (disk full, killed process,
    etc.). Writing straight to `output_path` leaves a truncated file on that
    rare failure -- and for a re-export, overwrites a prior good file with a
    partial one. Instead write to a sibling temp file in the same directory
    and `os.replace()` it into place: `os.replace` is atomic on both POSIX
    and Windows, so readers only ever see the old complete file or the new
    complete file, never a partial one. On failure the temp file is removed
    and `output_path` is left untouched.
    """
    output_path = str(output_path)
    directory = os.path.dirname(output_path) or "."
    fd, tmp_path = tempfile.mkstemp(
        dir=directory, prefix=f".{os.path.basename(output_path)}.", suffix=".tmp")
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(content)
        os.replace(tmp_path, output_path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
