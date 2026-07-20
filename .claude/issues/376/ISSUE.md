# Issue #376 — PERF-A-06: Fresh tempo map rebuilt at each detect site + events/frames round-trip; parse-time tempo never threaded forward

**Severity:** LOW · **Domain:** performance · **Source:** AUDIT_PERFORMANCE_2026-07-19.md

## Description
Two residual redundancies remain after #119 removed the expensive per-pattern tempo analysis: (a) each detect site constructs a fresh `EnhancedTempoMap(initial_tempo=500000)` defaulting to `ticks_per_beat=480` rather than the source file's resolution, because the parse stage discards its tempo map (`parse_midi_to_frames` returns empty `metadata`), so tempo is recomputed/redefaulted rather than reused; and (b) events are re-extracted from the frames dict (`frames_to_events`) that was itself derived from events at the frames stage — an events → frames → events round-trip. Both are cheap now (the tempo object is only allocated, not analyzed, and the detectors read only `note`/`volume`), so this is a correctness-neutral efficiency residual, not the costly path #119 addressed.

## Evidence
`main.py:683` `tempo_map = EnhancedTempoMap(initial_tempo=500000)` (default `ticks_per_beat=480`) and `:690` `events = frames_to_events(frames)`; mirrored at `:895`/`:899`. `parse_midi_to_frames` (`tracker/parser_fast.py:186-189`) returns `"metadata": {}`, so nothing tempo-related survives the parse JSON.

## Impact
A redundant object allocation and a full events-list rebuild per run; no output difference (detectors ignore tempo). Negligible cost on common files.

## Dimension
8 — Cross-stage recompute

## Related
#119 (closed — costly half fixed), #261 (shared `frames_to_events` extractor); Dimension 8.

## Suggested Fix
Low priority. If ever addressed, serialize the tempo summary into the parse JSON and pass it forward, and/or have the frames stage retain the event list it derived frames from so the detector need not re-extract it.

## Completeness Checks
- [ ] **CONTRACT**: If the parse JSON shape changes (tempo summary added), the consumer stages were updated in lockstep
- [ ] **SIBLING**: Same pattern checked at both detect sites (`run_detect_patterns` and `run_full_pipeline`)
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
