# PAT-2026-08-21-1: `--no-patterns` stub counts the `dpcm_sample_map` side table as events, inflating banner stats on drum songs

**Severity:** MEDIUM · **Domain:** patterns · **Source:** AUDIT_PATTERNS_2026-08-21.md
**GitHub Issue:** #435

## Location
`main.py:1084` (`detect_patterns_or_direct_export`, direct-export stub)

## Description
The stub computes `direct_size = sum(len(ch) for ch in frames.values())` and reports it as
`original_size`, `compressed_size`, and `total_events`. But `frames` is not purely a
`{channel: {frame: ...}}` dict: when a song has DPCM drums, `NESEmulatorCore.process_all_tracks`
adds a `dpcm_sample_map` side table (`nes/emulator_core.py:241-247`, a
`{str(dense_id): catalog_id}` map). `len()` of that map (the distinct-sample count) is silently
added to the "event" totals. This is exactly the iteration trap #200/#261 fixed by adding the
`DPCM_SAMPLE_MAP_KEY` skip to the shared `frames_to_events` extractor
(`nes/emulator_core.py:253-267`) — the stub site does its own `frames.values()` sweep and never
got the guard. Both real detector paths go through `frames_to_events` and are unaffected.

## Evidence
`main.py:1084-1096` builds the stats from `direct_size`; the success banner then prints
`Pattern coverage: 0.0% of {total_events:,} events` (`main.py:1411-1413`) — for a drum song in
`--no-patterns` mode, `total_events` over-counts by the number of `dpcm_sample_map` entries.

## Impact
Misleading (cosmetic) stats on every `--no-patterns` build of a song with percussion. No effect
on emitted ROM bytes. Magnitude is small (distinct-sample count, typically < 10), but the stub's
numbers stop matching what the detectors would report for the identical `frames` dict.

## Related
#261 (PERF-10, same trap in benchmark), #200/D-14, #104 (stub schema unification), #17 (banner conventions).

## Suggested Fix
Compute `direct_size = sum(len(ch) for name, ch in frames.items() if name != DPCM_SAMPLE_MAP_KEY)`
(import the constant from `nes/emulator_core.py`), or reuse `len(frames_to_events(frames))`.
