# New file: exporter/base_exporter.py

import os
import tempfile


class BaseExporter:
    """Shared base class for all exporters (CA65Exporter, NSFExporter,
    FamiStudioExporter).

    Previously also wrapped a CompressionEngine (RLE+delta channel
    compression) as compress_channel_data/decompress_channel_data, but no
    exporter or main.py call site ever used it -- the CA65 paths do their
    own inline compression (macro-bytecode serializer / direct frame
    tables), and NSF/FamiStudio never compressed channel data at all.
    Removed as dead code (#302/EXP-09); see exporter/compression.py's git
    history if RLE/delta channel compression is ever revisited.
    """
    pass


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
