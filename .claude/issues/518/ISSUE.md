**Severity:** HIGH · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-08-24.md

## Description
`CA65Exporter.export_tables_with_patterns` dispatches on the **actual truthiness of the `patterns` dict**: `if not patterns: return self.export_direct_frames(...)`. The step-by-step `export` subcommand (`run_export`, `main.py:746`) mirrors this exactly: `if not patterns:` — so it resolves the mapper *before* export whenever the exporter is about to take the direct-export branch, for whatever reason (either `--no-patterns` or pattern detection legitimately finding zero patterns).

`export_frames_and_resolve_mapper` (used only by `run_full_pipeline`) instead gates the same up-front resolution on the CLI **mode flag** at `main.py:1316`: `if not use_patterns:` — not the actual `pattern_result['patterns']` dict. When patterns mode is on (the default) but the detector legitimately finds **zero** patterns for a song (short jingles, stingers, highly varied melodies — anything with no repeated ≥3-event sequence), `export_tables_with_patterns` still takes the direct-export branch, but `export_frames_and_resolve_mapper` exports with `mapper=None` and only resolves the mapper **after** export, from the already-written, never-bin-packed `music.asm`.

With `--mapper mmc1` or `--mapper auto` landing on MMC1, this produces a false rejection: `check_mapper_capacity` sees one flat, un-bin-packed `RODATA` segment and raises `MapperError` the instant it exceeds MMC1's 16 KB window — even though the song's real data would fit fine in MMC1's actual 112 KB bank-switched capacity if bin-packing had run, exactly as it would via `midi2nes export --mapper mmc1 ...` on the identical frames/patterns.

## Evidence
```python
# main.py:746 (run_export, correct)
mapper = None
if not patterns:
    ...

# main.py:1316 (export_frames_and_resolve_mapper, buggy)
mapper = None
if not use_patterns:
    ...
```
An existing test locks in the buggy behavior with an inaccurate premise: `tests/test_main_pipeline.py:1709-1745` (`test_patterns_path_resolves_mapper_after_export`) constructs `pattern_result = {'patterns': {}, 'references': {}}` (i.e. exactly the "detector found nothing" case) with `use_patterns=True`, and asserts `mapper is None` — conflating "patterns mode is on" with "the bytecode path was actually taken." No test exercises this function with a real (unmocked) `CA65Exporter` + real `MMC1Mapper` + real `check_mapper_capacity`.

## Impact
Any legitimate MIDI song with (a) patterns mode on (default), (b) no repeated ≥3-event sequence, and (c) a direct-export size in MMC1's 16 KB–112 KB range fails the **entire default build** with a misleading "shorten the song" error — even though the step-by-step `export --mapper mmc1` path on the exact same data succeeds. `run_song_build` is unaffected (always forces MMC3).

## Related
Shares the "mapper resolution timing differs by path" design from #255/MAP-2026-07-05-1; adjacent to but distinct from the already-fixed #379/PIPE-2026-07-19-3 `references`-hardcoding divergence at the same call site.

## Suggested Fix
In `export_frames_and_resolve_mapper` (`main.py:1316`), gate the up-front mapper resolution on `if not pattern_result['patterns']:` (matching `run_export`'s `not patterns` and the exporter's own dispatch predicate) instead of `if not use_patterns:`. `pattern_result` is already computed and passed in before this function is called. Also correct `test_patterns_path_resolves_mapper_after_export`'s premise once fixed — construct the "resolves after" case with a genuinely non-empty `pattern_result['patterns']`.

## Completeness Checks
- [ ] **CONTRACT**: The fix should make `export_frames_and_resolve_mapper`'s mapper-resolution timing match `run_export`'s exactly — same predicate, same dict
- [ ] **SIBLING**: Verify no other call site duplicates the same `use_patterns`-vs-`patterns` conflation
- [ ] **TESTS**: `test_patterns_path_resolves_mapper_after_export`'s premise needs correcting, and a new test should cover the real "patterns mode on, detector finds zero patterns, MMC1 target" case end-to-end (unmocked exporter + real capacity check)
