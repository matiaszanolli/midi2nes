# #98 — TEMPO-06: detect-patterns / pipeline build a default-PPQ tempo map that is inert

**Severity:** LOW · **Domain:** tempo · **Source:** AUDIT_TEMPO_2026-06-29.md

## Description
The pattern-detection stage constructs a fresh `EnhancedTempoMap` with the default `ticks_per_beat=480`, not the file's resolution, and **never adds the file's tempo changes** to it (`main.py:277`, `:453`). It does not affect output: the detector operates on already-framed events keyed by `frame`, and `_analyze_pattern_tempo` calls `get_tempo_at_tick(frame_position)` on a tempo map that has only the constant default tempo — the result (`base_tempo`) is stored as pattern metadata and never feeds frame timing. `get_tempo_at_tick` returns a constant 500000 here regardless of PPQ, so the 480 default is harmless.

## Location
`main.py:277` (`EnhancedTempoMap(initial_tempo=500000)` — no `ticks_per_beat`, defaults to 480) and `main.py:453`; consumed by `tracker/pattern_detector.py:377-411` (`_analyze_pattern_tempo` -> `get_tempo_at_tick`).

## Evidence
`main.py:277`/`:453` construct the map empty; framed events have no `set_tempo` re-applied; `pattern_detector.py:387` indexes by `tick` that is actually a frame position. The PERF audit reached the same conclusion ("harmless only because it is unused — a latent trap").

## Impact
No incorrect output today. Latent trap: if a future change starts deriving timing from this map it would use the wrong PPQ and a constant tempo. LOW (doc / dead-construction).

## Related
PERF-08 (wasted construction, `docs/audits/AUDIT_PERFORMANCE_2026-06-29.md`); TEMPO-05.

## Suggested Fix
Drop the unused `EnhancedTempoMap` construction at `main.py:277`/`:453`, or, if kept, pass the real `ticks_per_beat` and the file's tempo changes and add a comment that it is analysis-only.

## Completeness Checks
- [ ] **CONTRACT**: Pattern-metadata `base_tempo` consumers unaffected by the change
- [ ] **DOC**: If kept, a comment marks the construction analysis-only
