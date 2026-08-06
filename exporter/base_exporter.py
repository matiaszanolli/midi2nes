# New file: exporter/base_exporter.py

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
