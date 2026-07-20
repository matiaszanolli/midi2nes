# TEMPO-18: Base TempoMap.__init__ lacks the non-positive initial_tempo guard that EnhancedTempoMap has

Issue: #383 · https://github.com/matiaszanolli/midi2nes/issues/383
Labels: low, tempo, bug

**Severity:** LOW · **Domain:** tempo · **Source:** AUDIT_TEMPO_2026-07-19.md

## Description
`EnhancedTempoMap.__init__` rejects `initial_tempo <= 0` with a `TempoValidationError` before its BPM division (#317/TEMPO-14). The base `TempoMap.__init__` (`tracker/tempo_map.py:88-114`) guards only `ticks_per_beat` (`:101`), not `initial_tempo`. A base `TempoMap(initial_tempo=0)` constructs silently; `get_tempo_bpm_at_tick` would then `ZeroDivisionError`, and `_build_tempo_index` computes `us_per_tick = 0`, collapsing **every** tick to time 0.0 → frame 0 with no error.

## Evidence
`TempoMap(initial_tempo=0, ticks_per_beat=480).get_frame_for_tick(1000)` returns `0` (all events pile onto frame 0) instead of raising. A grep for `TempoMap(` excluding `Enhanced` and tests returns **no** live construction site, so this is currently unreachable in production.

Confirmed in code: `EnhancedTempoMap.__init__` guard at `tracker/tempo_map.py:238-241`; base `TempoMap.__init__` guards only `ticks_per_beat < 1` at `:101` with no `initial_tempo` check.

## Impact
None today (no live caller constructs the base class with untrusted tempo — the live front-end `tracker/parser_fast.py` uses `EnhancedTempoMap`). It is a defense-in-depth gap: `TempoMap` is a public exported symbol (`__all__`, `tracker/tempo_map.py:880`) whose hardened subclass validates a case the base silently mis-handles.

## Related
- #317/TEMPO-14 (the sibling guard in `EnhancedTempoMap`)
- TD-26/#346 (`tracker/parser.py`, a base-`TempoMap`-adjacent dead path)

## Suggested Fix
Add the same `if initial_tempo <= 0: raise TempoValidationError` (or `ValueError` for the base class, which does not import the tempo exception) at the top of `TempoMap.__init__`, mirroring the existing `ticks_per_beat` guard.

## Completeness Checks
- [ ] **SIBLING**: Same guard present in `EnhancedTempoMap` and any other `TempoMap` subclass/constructor
- [ ] **TESTS**: A regression test pins that `TempoMap(initial_tempo=0)` raises
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
