# New file: exporter/base_exporter.py

# Re-exported for existing `from exporter.base_exporter import
# atomic_write_text` call sites -- the implementation moved to core/io_utils
# (#456/SAFE-2026-08-21-2) so nes/song_bank.py (and any other module) can use
# it without a reverse dependency on exporter/, which already imports from
# nes/. Listed in __all__ (matching arranger/__init__.py's re-export
# convention) so the repo-hygiene F401 check (#264) recognizes it as used.
from core.io_utils import atomic_write_text

__all__ = ["BaseExporter", "atomic_write_text"]


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
