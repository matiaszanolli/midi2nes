# PERF-15
**Filed as:** #335

**Severity:** LOW · **Domain:** performance · **Source:** AUDIT_PERFORMANCE_2026-07-18.md

## Description
`parse_midi_to_frames` returns `"metadata": {}` and never serializes tempo, so every downstream stage rebuilds a tempo map from scratch: `run_detect_patterns` (`main.py:646`) and `run_full_pipeline` (`main.py:854`) each construct a bare `EnhancedTempoMap(initial_tempo=500000)` (mutually exclusive per run, neither reused), and `parse_midi_to_frames_with_analysis` (`tracker/parser_fast.py:203-204`) re-opens the MIDI file and rebuilds the map after already parsing once. Frames are derived from events at the frames stage, then events are re-extracted from frames at detection (`frames_to_events` at `main.py:653`, `:858`). #119 removed the expensive half (per-pattern tempo analysis skipped via `analyze_tempo=False`), so what remains is cheap redundant allocation + an events↔frames round-trip.

## Evidence
`tempo_map = EnhancedTempoMap(initial_tempo=500000)` at both `main.py:646` and `:854`; `events = frames_to_events(frames)` at `:653` and `:858`.

## Impact
Minor wasted allocation/CPU; the detectors read only `note`/`volume` from events, so the redundant tempo maps are never wrong, just redundant. No output impact.

## Related
#119 (closed — costly half), #261 (shared `frames_to_events`).

## Suggested Fix
Optional — thread tempo/metadata through the parse JSON if a future stage needs it; otherwise leave as-is (remaining cost is negligible). Cache the first-pass tempo map in `parse_midi_to_frames_with_analysis`.

## Completeness Checks
- [ ] **CONTRACT**: if tempo/metadata is threaded through parse JSON, the consumer stages read it consistently
- [ ] **TESTS**: a test pins that detection output is unchanged by any caching