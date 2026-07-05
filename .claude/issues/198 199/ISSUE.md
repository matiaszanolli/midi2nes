# EXP-10: Tone-channel note clamps in the exporter have no log/counter — silent pitch change on out-of-range notes

**GitHub Issue:** https://github.com/matiaszanolli/midi2nes/issues/198
**Severity:** MEDIUM
**Domain:** exporters
**Source:** AUDIT_EXPORTERS_2026-07-03.md
**Labels:** medium, exporters, bug

## Description
Per the SKILL's own verification note on the #158/NH-16 fix, a clamped note should be "at
least logged/counted somewhere upstream." It is not. Neither `exporter_ca65.py` nor any
upstream stage (`nes/emulator_core.py`, `arranger/pipeline_integration.py`,
`tracker/track_mapper.py`) counts, logs, or warns when a note gets clamped at either boundary.
A melodic line that goes above MIDI note 95 (B6) or, for tone channels, below 24 (C1) is
silently re-pitched with zero indication to the user.

## Location
`exporter/exporter_ca65.py:987-997` (`elif note > 95: note = 95` /
`elif channel != 'noise' and 0 < note < 24: note = 24`)

**Spec ref:** `docs/AUDIO_BYTECODE_SPEC.md` §3 "Note Range ($00-$5F)" — the note byte is
hard-capped at 95 by the bytecode format itself, so *some* clamp is mandatory and correct; the
gap is the missing diagnostic, not the clamp itself.

## Evidence
```python
elif note > 95:
    note = 95
elif channel != 'noise' and 0 < note < 24:
    note = 24
```
`grep -rn "out of range\|clamped\|clamp_count\|notes_clamped" nes/ exporter/ arranger/
tracker/ main.py` turns up no counter/log tied to this clamp.

## Impact
Any song with content above B6 or below C1 (tone channels) plays wrong, unannounced notes.
MEDIUM, silent, no workaround without inspecting output audio.

## Related
#158/NH-16 (the low-end clamp's *value* was fixed there; lack of diagnostic was out of
scope). #41/NH-11 (a different, unused method's inconsistent range guard).

## Suggested Fix
Have `export_tables_with_patterns` accumulate a per-song count of clamped notes (both
directions) and print a one-line summary (e.g. `"12 notes clamped to NES tone range
(24-95); pitch may differ from the MIDI file"`) at the end of export.

## Completeness Checks
- [ ] **RANGE**: If the fix emits NES values, they are clamped to hardware range (byte / 11-bit timer)
- [ ] **SIBLING**: Same pattern checked in related files
- [ ] **TESTS**: A regression test pins this specific fix

---

# EXP-09: exporter/compression.py's CompressionEngine and BaseExporter compress/decompress helpers are dead code

**GitHub Issue:** https://github.com/matiaszanolli/midi2nes/issues/199
**Severity:** LOW
**Domain:** exporters
**Source:** AUDIT_EXPORTERS_2026-07-03.md
**Labels:** low, exporters, bug

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
which *is* live on the default pipeline via `ParallelPatternDetector`.

## Location
`exporter/compression.py:1-254` (the whole `CompressionEngine` class);
`exporter/base_exporter.py:12-46` (`compress_channel_data`/`decompress_channel_data`)

## Evidence
`grep -rn "compress_channel_data\|decompress_channel_data\|CompressionEngine" --include=*.py .`
matches only `exporter/compression.py`, `exporter/base_exporter.py`, and the three test files
above — no exporter or `main.py` call site.

## Impact
None functionally (dead code, not reachable from any pipeline path). Maintenance/confusion
cost: a future contributor could reasonably assume this is the live compression path.

## Suggested Fix
Either wire it in (if RLE/delta channel-data compression is still a planned feature) or
remove `CompressionEngine`/`compress_channel_data`/`decompress_channel_data` and their
dedicated tests, noting the removal in `docs/ROADMAP.md` if it was ever an advertised feature.

## Completeness Checks
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
