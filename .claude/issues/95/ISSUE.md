# TEMPO-03: ticks_per_beat == 0 produces inf time instead of failing fast

Issue: #95

**Severity:** MEDIUM · **Domain:** tempo · **Source:** AUDIT_TEMPO_2026-06-29.md

## Description
There is no guard against `ticks_per_beat == 0`. `calculate_time_ms` divides by it (`tracker/tempo_map.py:129`, `:141`), yielding `inf` (only a `RuntimeWarning`, no exception), and every `get_frame_for_tick` returns `inf` -> all frames collapse to a garbage index. A malformed MIDI header or any caller passing 0 corrupts the whole song without an error.

## Location
`tracker/tempo_map.py:129` and `:141` (`tempo / self.ticks_per_beat`); unguarded constructor `tracker/tempo_map.py:77-87` / `:175-194`; boundary `tracker/parser_fast.py:24-29`.

## Evidence
```
EnhancedTempoMap(initial_tempo=500000, ticks_per_beat=0, optimization_strategy=None)
tm.calculate_time_ms(0, 480)  -> inf   (RuntimeWarning: divide by zero)
```

## Impact
Defense-in-depth gap at the same parse boundary as TEMPO-01. Less likely than SMPTE (mido usually rejects a 0-division header) but the class is unguarded; produces `inf` frames rather than a clean failure.

## Related
TEMPO-01 (same unvalidated `ticks_per_beat` boundary — fix together).

## Suggested Fix
Add `if ticks_per_beat < 1: raise ValueError(...)` (or `TempoValidationError`) in `TempoMap.__init__`, covering both the 0 and negative cases.

## Completeness Checks
- [ ] **SIBLING**: Fix covers both 0 and negative cases (shared with TEMPO-01) in `TempoMap.__init__`
- [ ] **TESTS**: A regression test pins the `ticks_per_beat < 1` rejection
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
