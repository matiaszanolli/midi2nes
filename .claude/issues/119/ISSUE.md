# PERF-08: Tempo map rebuilt from scratch up to four times; events round-trip through frames

**Severity:** LOW · **Domain:** performance · **Source:** AUDIT_PERFORMANCE_2026-06-29.md

## Description
The tempo map computed at parse time is **not serialized into the parse JSON** (`tracker/parser_fast.py:85` returns `"metadata": {}`), so every downstream consumer rebuilds it:
- `parse_midi_to_frames_with_analysis` re-opens the MIDI and rebuilds the tempo map after `parse_midi_to_frames` already built one (`tracker/parser_fast.py:116-125`) — the inline comment at `:115` admits "this could be cached from first pass". This variant is opt-in, so the cost is bounded.
- The detect-patterns stage constructs a fresh `EnhancedTempoMap(initial_tempo=500000)` (`main.py:453`) **with the default `ticks_per_beat=480`**, not the file's resolution — and then never uses it for timing (the detector only reads `note`/`volume`), so it is a wasted construction.

Separately, events are derived into `frames` at the frames stage and then **re-extracted from `frames` back into an `events` list** for pattern detection (`main.py:456-464`, and again in `run_detect_patterns` at `:281-293`) — an events→frames→events round-trip.

> Note: the inert default-PPQ tempo map at `main.py:453` is also tracked from the *latent-trap* angle in #98 (TEMPO-06). This finding is the **redundant-recomputation / performance** angle (tempo rebuilds not threaded through the parse JSON + events round-trip), which #98 does not cover.

## Location
`tracker/parser_fast.py:24-48` (build #1), `:103-125` (`parse_midi_to_frames_with_analysis` re-opens and rebuilds; comment at `:115`); `main.py:453` (`EnhancedTempoMap(initial_tempo=500000)` fresh, default-tick); events round-trip at `main.py:281-293` and `:456-464`

## Evidence
`parse_midi_to_frames` returns `"metadata": {}` (`parser_fast.py:85`); `parse_midi_to_frames_with_analysis` rebuild loop re-opens `mido.MidiFile` (`:116`); `main.py:453` fresh tempo map; events-rebuild loops at `main.py:281-293` and `:456-464`.

## Impact
Wasted CPU, not incorrect output (the detector ignores tempo). LOW. The `EnhancedTempoMap` at `main.py:453` getting the wrong `ticks_per_beat` is harmless *only because* it is unused — a latent trap if a future change starts reading it.

## Related
PERF-01 (each rebuild repays the O(T) scan cost); #98/TEMPO-06 (same inert map, latent-trap framing); #33/F-14 (`SongBank` uses yet another parser — third tempo path).

## Suggested Fix
Thread the computed tempo data through the parse JSON contract so downstream stages deserialize rather than recompute; drop the unused `EnhancedTempoMap` at `main.py:453` or pass it real parameters.

## Completeness Checks
- [ ] **CONTRACT**: If tempo data is added to the parse JSON, the consumer stages read it in lockstep
- [ ] **SIBLING**: The events round-trip removed at both `main.py:281-293` and `:456-464`
- [ ] **TESTS**: A test pins that threading tempo through the contract yields identical frames
