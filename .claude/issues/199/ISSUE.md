# EXP-09: exporter/compression.py's CompressionEngine and BaseExporter compress/decompress helpers are dead code

**Severity:** LOW · **Domain:** exporters · **Source:** AUDIT_EXPORTERS_2026-07-03.md

**Status:** NEW

## Description
`BaseExporter.__init__` instantiates a `CompressionEngine`, and
`compress_channel_data`/`decompress_channel_data` wrap its RLE+delta
`compress_pattern`/`decompress_pattern` methods. None of the three live exporters
(`CA65Exporter`, `NSFExporter`, `FamiStudioExporter`) — nor `main.py`, nor any other
production module — ever call `compress_channel_data`, `decompress_channel_data`, or
`CompressionEngine` directly. `export_tables_with_patterns`/`export_direct_frames` do their
own inline compression (`_compress_macro`, the direct frame tables); this RLE/delta engine is
entirely unused at runtime. It is exercised only by `tests/test_compression.py`,
`tests/test_compression_integration.py`, and `tests/test_exporter_integration.py` — tested
code with no caller.

This is distinct from `tracker/pattern_detector.py`'s unrelated `PatternCompressor` class,
which *is* live on the default pipeline via `ParallelPatternDetector` — grepped and confirmed
these are two separate classes with no relationship.

## Location
`exporter/compression.py:1-254` (the whole `CompressionEngine` class);
`exporter/base_exporter.py:12-46` (`compress_channel_data`/`decompress_channel_data`)

## Evidence
`grep -rn "compress_channel_data\|decompress_channel_data\|CompressionEngine"
--include=*.py .` (excluding `venv/`) matches only `exporter/compression.py`,
`exporter/base_exporter.py`, and the three test files above — no exporter or `main.py` call
site. Confirmed via re-run:
```
tests/test_compression.py:4:from exporter.compression import CompressionEngine
tests/test_compression_integration.py:3:from exporter.compression import CompressionEngine
tests/test_exporter_integration.py:8:from exporter.compression import CompressionEngine
exporter/compression.py:6:class CompressionEngine:
exporter/base_exporter.py:4:from exporter.compression import CompressionEngine
exporter/base_exporter.py:10:        self.compression_engine = CompressionEngine()
exporter/base_exporter.py:12:    def compress_channel_data(...)
exporter/base_exporter.py:34:    def decompress_channel_data(...)
```
No `CA65Exporter`/`NSFExporter`/`FamiStudioExporter` method calls `self.compress_channel_data`
or `self.decompress_channel_data` anywhere.

## Impact
None functionally (dead code, not reachable from any pipeline path). Maintenance/confusion
cost: a future contributor could reasonably assume this is the live compression path for
exported channel data (it is the only "compression" concept living in `exporter/`) and modify
it expecting an effect on ROM output.

## Related
none.

## Suggested Fix
Either wire it in (if RLE/delta channel-data compression is still a planned feature) or
remove `CompressionEngine`/`compress_channel_data`/`decompress_channel_data` and their
dedicated tests, noting the removal in `docs/ROADMAP.md` if it was ever an advertised
feature.

## Completeness Checks
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
