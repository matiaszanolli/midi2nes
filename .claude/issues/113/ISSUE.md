# PERF-01: Parser frame/tempo lookup is O(notes × tempo_changes), not O(1)

**Severity:** MEDIUM · **Domain:** performance · **Source:** AUDIT_PERFORMANCE_2026-06-29.md

## Description
The claim that `get_frame_for_tick` / `get_tempo_at_tick` are "O(1)-ish" does **not** hold. In the per-note loop (`tracker/parser_fast.py:60-76`) each `note_on`/`note_off` calls both:
- `get_tempo_at_tick(current_tick)` — a **linear scan of all tempo changes** (`tracker/tempo_map.py:98`), O(T) per note.
- `get_frame_for_tick(current_tick)` → `calculate_time_ms(0, tick)` (`tracker/tempo_map.py:146`). `calculate_time_ms` walks tick-segment by tick-segment and, **for each segment, does another linear scan** of `self.tempo_changes` to find the next change boundary (`tracker/tempo_map.py:123`) — O(T²) for a tick past every change, only memoised on the exact `(0, tick)` pair via `_time_cache`.

Total parse cost is therefore **O(N·T + D·T²)** where N = note events, T = tempo changes, D = distinct ticks. For the common case T is tiny (1–3), so this is a small constant and the "120x" claim survives. But a MIDI with heavy tempo automation (hundreds of `set_tempo`, e.g. a ritardando-laden orchestral export) makes parse super-linear.

## Location
`tracker/parser_fast.py:60-76`; `tracker/tempo_map.py:95-103` (`get_tempo_at_tick`), `:105-136` (`calculate_time_ms`), `:144-147` (`get_frame_for_tick`)

## Evidence
`get_tempo_at_tick` loops `for change_tick, tempo in self.tempo_changes` (`tempo_map.py:98`, no bisect); `calculate_time_ms` nests `for change_tick, _ in self.tempo_changes` (`:123`) inside its `while current_tick < end_tick` loop.

## Impact
Parse stage only; degrades on tempo-dense MIDI. Not OOM, not a crash → MEDIUM.

## Related
PERF-08 (tempo map rebuilt multiple times); the same O(T) scan recurs everywhere `get_tempo_at_tick` is called.

## Suggested Fix
`self.tempo_changes` is kept sorted (`add_tempo_change` sorts) — replace the linear scans with `bisect.bisect_right` over a precomputed tick array, and precompute cumulative ms-at-each-change so `calculate_time_ms(0, tick)` is one bisect + one multiply.

## Completeness Checks
- [ ] **TESTS**: A regression test pins parse correctness on a tempo-dense MIDI (many `set_tempo`)
- [ ] **SIBLING**: Same O(T) scan fixed at every `get_tempo_at_tick` / `calculate_time_ms` call site
- [ ] **DOC**: If a docstring/SKILL claims O(1), it is corrected
