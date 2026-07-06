# TEMPO-12 / #259: parse_midi_to_frames_with_analysis silently drops out-of-range tempo changes (diverges from fixed count-and-warn)

**Severity:** LOW · **Domain:** tempo · **Source:** AUDIT_TEMPO_2026-07-05.md

## Description
The default parser `parse_midi_to_frames` was fixed under #94 (TEMPO-02) to never drop a tempo change silently -- it counts rejections in `dropped_tempo_changes` and prints a warning after the tempo pass. Its sibling `parse_midi_to_frames_with_analysis` rebuilds its own tempo map and still uses the pre-#94 idiom: a bare `except TempoValidationError: continue` with no counter and no user-facing warning.

## Location
`tracker/parser_fast.py:199-202` (`except TempoValidationError: continue`, no counter, no warning), contrasted with the fixed default path at `tracker/parser_fast.py:80-94` (`dropped_tempo_changes += 1` + post-pass `print(...)`).

## Evidence
```python
# parser_fast.py:198-202  (with_analysis path)
if msg.type == 'set_tempo':
    try:
        tempo_map.add_tempo_change(current_tick, msg.tempo, TempoChangeType.IMMEDIATE)
    except TempoValidationError:
        continue        # <- silent; no count, no warning
```

## Impact
Off the live ROM path (--with-analysis only). Consistency/observability gap: analysis run interactively can silently mis-tempo a section.

## Suggested Fix
Mirror the default path: count rejected changes in a local and print a single warning after the loop (or refactor the two tempo-collection passes into one shared helper so they cannot drift again).

## Completeness Checks
- [ ] SIBLING, TESTS (see GitHub issue body)

---

# TEMPO-13 / #260: parse_midi_to_frames_with_analysis builds tempo map without ticks_per_beat, then feeds it real-tick tempo changes (latent PPQ trap)

**Severity:** LOW · **Domain:** tempo · **Source:** AUDIT_TEMPO_2026-07-05.md

## Description
Unlike the default parser (`tracker/parser_fast.py:62-67`), which passes `ticks_per_beat=mid.ticks_per_beat`, the analysis rebuild omits it and takes the constructor default of 480. It then adds real tempo changes keyed on the file's actual tick positions. If the file's PPQ != 480, the tempo map's `ticks_per_beat` (480) disagrees with the ticks it stores.

## Location
`tracker/parser_fast.py:186-190` (`EnhancedTempoMap(initial_tempo=500000, validation_config=config, optimization_strategy=None)` -- no `ticks_per_beat`, so it defaults to 480) combined with `:198-202` (walks the real MIDI and calls `add_tempo_change(current_tick, ...)` at the file's actual ticks).

## Evidence
The map is inert today only because its two consumers (`get_tempo_at_tick` via bisect, used by `EnhancedPatternDetector._analyze_pattern_tempo` and `EnhancedLoopManager`) are PPQ-independent. No `calculate_time_ms`/`get_frame_for_tick` is invoked on this map.

## Impact
No wrong output today. Latent trap: if any future change on this path calls `get_frame_for_tick`/`calculate_time_ms` on this map, the hardcoded 480 would silently diverge from the file's real PPQ.

## Related
#98 (TEMPO-06, open -- inert default-PPQ maps in main.py); TEMPO-12 (same function).

## Suggested Fix
Pass `ticks_per_beat=mid.ticks_per_beat` when constructing the tempo map in `parse_midi_to_frames_with_analysis`. Better, reuse the tempo map already built by the first `parse_midi_to_frames` pass instead of rebuilding it (the code comment at `:192` already notes it "could be cached from first pass").

## Completeness Checks
- [ ] SIBLING, TESTS (see GitHub issue body)
