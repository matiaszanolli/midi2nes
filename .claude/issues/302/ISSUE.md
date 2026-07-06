# #302 — EXP-09: exporter/compression.py CompressionEngine + BaseExporter helpers are dead code

**Severity:** LOW · **Domain:** exporters · **Source:** AUDIT_EXPORTERS_2026-07-06.md · **Status:** Carried from prior audit reports (2026-07-03 / 07-05), never filed as a GitHub issue — filing now.

## Description
`BaseExporter.__init__` (`exporter/base_exporter.py:10`) instantiates a `CompressionEngine` and wraps its RLE+delta `compress_pattern`/`decompress_pattern` as `compress_channel_data` / `decompress_channel_data` (`:12-46`), but none of the three live exporters (`CA65Exporter`, `NSFExporter`, `FamiStudioExporter`), nor `main.py`, nor any production module ever calls them or `CompressionEngine`. The CA65 paths do their own inline compression (`_compress_macro`, direct frame tables); this engine is unused at runtime, exercised only by `tests/test_compression.py`, `tests/test_compression_integration.py`, and `tests/test_exporter_integration.py`.

## Evidence
```
$ grep -rn 'compress_channel_data\|decompress_channel_data\|CompressionEngine' --include='*.py' . | grep -v test
exporter/base_exporter.py:4:  from exporter.compression import CompressionEngine
exporter/base_exporter.py:10:     self.compression_engine = CompressionEngine()
exporter/base_exporter.py:12:     def compress_channel_data(...)
exporter/base_exporter.py:34:     def decompress_channel_data(...)
exporter/compression.py:6:    class CompressionEngine:
```
No exporter or `main.py` call site — only the definition, the `BaseExporter` wrappers, and tests.

## Impact
None functional. Maintenance/confusion cost: a contributor could assume this is the live compression path for exported channel data (it is the only "compression" concept in `exporter/`) and modify it expecting a ROM-output effect. Distinct from `tracker/pattern_detector.py`'s live pattern compression.

## Suggested Fix
Either wire it in (if RLE/delta channel compression is still planned) or remove `CompressionEngine` / `compress_channel_data` / `decompress_channel_data` and their dedicated tests.

## Completeness Checks
- [ ] **SIBLING**: confirm no exporter or `main.py` path depends on `BaseExporter.compress_channel_data`/`decompress_channel_data` before removal
- [ ] **TESTS**: the dedicated compression tests are removed or repointed if the code is deleted
