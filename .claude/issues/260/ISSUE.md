**Severity:** LOW · **Domain:** tempo · **Source:** AUDIT_TEMPO_2026-07-05.md

## Description
Unlike the default parser (`tracker/parser_fast.py:62-67`), which passes `ticks_per_beat=mid.ticks_per_beat`, the analysis rebuild omits it and takes the constructor default of 480. It then adds real tempo changes keyed on the file's actual tick positions. If the file's PPQ ≠ 480, the tempo map's `ticks_per_beat` (480) disagrees with the ticks it stores. This is a different shape from #98's `main.py` sites: those never call `add_tempo_change` at all (truly inert). Here real tempo changes *are* recorded.

## Location
`tracker/parser_fast.py:186-190` (`EnhancedTempoMap(initial_tempo=500000, validation_config=config, optimization_strategy=None)` — no `ticks_per_beat`, so it defaults to 480) combined with `:198-202` (walks the real MIDI and calls `add_tempo_change(current_tick, ...)` at the file's actual ticks).

## Evidence
The map is inert **today** only because its two consumers are PPQ-independent: `get_tempo_at_tick`/bisect returns a stored tempo value without any tick→time math, and `EnhancedPatternDetector._analyze_pattern_tempo` and `EnhancedLoopManager` only ever call `get_tempo_at_tick`. No `calculate_time_ms`/`get_frame_for_tick` is invoked on this map, so the 480-vs-actual mismatch never reaches a time computation. Confirmed by grep: the only methods called on the analysis `tempo_map` are `add_tempo_change` and `get_tempo_at_tick` (+ `loop_points` dict access).

## Impact
No wrong output today (off the live ROM path, and no time math runs on the map). It is a fragile latent trap: if any future change on this path calls `get_frame_for_tick`/`calculate_time_ms` on this map (e.g. to re-derive frames or align loops), the hardcoded 480 would silently diverge from the file's real PPQ and mis-time everything.

## Related
#98 (TEMPO-06, open — inert default-PPQ maps in `main.py`; this is a third site with the same omission but non-inert tempo data); TEMPO-12 (same function).

## Suggested Fix
Pass `ticks_per_beat=mid.ticks_per_beat` when constructing the tempo map in `parse_midi_to_frames_with_analysis`. Better, reuse the tempo map already built by the first `parse_midi_to_frames` pass instead of rebuilding it (the code comment at `:192` already notes it "could be cached from first pass").

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **SIBLING**: Same pattern checked in related files (the default `parse_midi_to_frames` pass passes `ticks_per_beat`; #98 sites are related but inert)
- [ ] **TESTS**: A regression test pins this specific fix (analysis tempo map carries the file's real PPQ)
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
