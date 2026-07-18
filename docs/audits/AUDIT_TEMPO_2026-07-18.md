# Tempo & Frame-Timing Audit — 2026-07-18

## Summary

**Invariant verdict: frame timing stays on the 60Hz grid.** Re-verified empirically
against the current tree (HEAD `b562e1d`). `tracker/tempo_map.py`, `tracker/parser_fast.py`,
`nes/emulator_core.py`, `tracker/loop_manager.py`, and the two `main.py` tempo-map
construction sites are **byte-for-byte unchanged** since the 2026-07-17 audit
(`git diff d5564b8..HEAD -- tracker/tempo_map.py tracker/parser_fast.py
tracker/loop_manager.py nes/emulator_core.py main.py constants.py` is empty), so this is a
delta/re-verify pass per the audit protocol.

Empirical re-check: a synthetic 5-minute, 120 BPM song plus two mid-song tempo changes
(288,000 ticks, `ticks_per_beat=480`) lands the final tick at frame **18000** with **0**
frames of drift versus `total_ms / FRAME_MS`. Sampling `calculate_time_ms(0, tick)` every
137 ticks across the song, the max absolute error between the rounded frame and the exact
`time_ms / FRAME_MS` value is 0.5 — i.e. exactly the quantization bound of `round()`, with
no growth over song length (no accumulating drift). `calculate_time_ms(0, tick)` still
computes via `_cumulative_ms(end) - _cumulative_ms(start)` (`tracker/tempo_map.py:158-190`)
with no running counter.

One **new LOW finding** surfaced this pass, distinct from the previously-closed tick-0/tick>0
`ZeroDivisionError` issues (#208/#209): `EnhancedTempoMap.__init__` itself (as opposed to
`add_tempo_change`) computes `60_000_000 / initial_tempo` before any guard, so
`EnhancedTempoMap(initial_tempo=0)` raises a raw `ZeroDivisionError` instead of the intended
`TempoValidationError`. Confirmed **unreachable on the live MIDI→ROM pipeline** — every
construction site in the repo (`main.py:646`, `main.py:844`, `tracker/parser_fast.py:38`,
`tracker/parser.py:30`, `tracker/pattern_detector_parallel.py:396`) passes a hardcoded
`initial_tempo=500000`, and `initial_tempo` is not exposed through any config file or CLI
flag — so this is a defensive-coding gap in a public constructor, not a live crash.

| Severity | Count | of which NEW |
|----------|-------|--------------|
| CRITICAL | 0     | 0 |
| HIGH     | 0     | 0 |
| MEDIUM   | 0     | 0 |
| LOW      | 1     | 1 |
| **Total**| **1** | **1** |

**Highest-leverage fix:** guard `initial_tempo <= 0` at the top of
`EnhancedTempoMap.__init__` (`tracker/tempo_map.py:228-245`) and raise
`TempoValidationError` before the `60_000_000 / initial_tempo` division, mirroring the
`change.tempo <= 0` guard already in `_validate_basic_tempo` (`:396-399`). Low urgency since
no current call site is affected.

---

## Findings

### TEMPO-14: `EnhancedTempoMap.__init__` divides by `initial_tempo` before any zero/negative guard — raises `ZeroDivisionError` instead of `TempoValidationError`
- **Severity**: LOW
- **Dimension**: 3 (Default / Missing Tempo Fallback)
- **Location**: `tracker/tempo_map.py:228-245` (`EnhancedTempoMap.__init__`), specifically
  `initial_bpm = 60_000_000 / initial_tempo` at `:235`, which runs before
  `super().__init__(initial_tempo, ticks_per_beat)` (`:244`) and before any tempo-specific
  guard.
- **Status**: NEW
- **Description**: The constructor validates `initial_tempo` by computing
  `initial_bpm = 60_000_000 / initial_tempo` and checking it against
  `[min_tempo_bpm, max_tempo_bpm]`. For `initial_tempo == 0` this division raises a raw
  `ZeroDivisionError` before the BPM-range check ever runs, so the intended
  `TempoValidationError` (with its actionable message) never fires. This is the same failure
  shape as the already-fixed #209 (`_validate_basic_tempo` dividing by `change.tempo` before
  guarding it), but it is a *different, still-unguarded* code path: #208/#209 fixed
  `EnhancedTempoMap.add_tempo_change` (both the `tick == 0` branch and the `tick > 0` branch
  via `_validate_basic_tempo`'s `change.tempo <= 0` guard at `:396-399`); neither fix touched
  the constructor's own `initial_bpm` computation, which has no equivalent guard.
- **Evidence**:
  ```
  >>> from tracker.tempo_map import EnhancedTempoMap
  >>> EnhancedTempoMap(initial_tempo=0, ticks_per_beat=480)
  Traceback (most recent call last):
    ...
    File "tracker/tempo_map.py", line 235, in __init__
      initial_bpm = 60_000_000 / initial_tempo
                    ~~~~~~~~~~~~^~~~~~~~~~~~~~~
  ZeroDivisionError: division by zero
  ```
  A negative `initial_tempo` (e.g. `-500000`) similarly divides cleanly to a negative BPM,
  which *does* correctly fail the `min_tempo_bpm <= initial_bpm` range check and raise
  `TempoValidationError` — only the exact `initial_tempo == 0` case hits the unguarded
  division, mirroring #209's exact failure mode one level up the call stack.
- **Impact**: None on the current live pipeline — grepped every `EnhancedTempoMap(...)`
  construction site in the repo (`main.py:646`, `main.py:844`, `tracker/parser_fast.py:38`,
  `tracker/parser.py:30`, `tracker/pattern_detector_parallel.py:396`, plus test fixtures) and
  all pass a hardcoded `initial_tempo=500000` or rely on the `500000` default; `initial_tempo`
  is not read from `config/default_config.yaml` or any CLI flag (`grep -rn "initial_tempo"
  config/ main.py` returns only the two hardcoded `main.py` sites). If a future call site ever
  derives `initial_tempo` from user/file input (e.g. a config option to set the starting
  tempo, or a library caller embedding `EnhancedTempoMap`), a `0` value would surface as an
  unhandled `ZeroDivisionError` traceback instead of the actionable
  `TempoValidationError` message, and — unlike `parser_fast.py`'s
  `except TempoValidationError: continue` around `add_tempo_change` — there is no
  corresponding guard around any `EnhancedTempoMap(...)` construction call, so it would abort
  the whole run.
- **Related**: Same root-cause class as the closed #209 (`_validate_basic_tempo` dividing by
  `change.tempo` before guarding — fixed at `tracker/tempo_map.py:396-399`) and closed #208
  (tick-0 validation bypass in `add_tempo_change`) — this finding is the *constructor's own*
  analogous gap, untouched by either fix.
- **Suggested Fix**: Add `if initial_tempo <= 0: raise TempoValidationError(...)` at the top
  of `EnhancedTempoMap.__init__`, before computing `initial_bpm`, using the same message
  pattern as `_validate_basic_tempo`'s `change.tempo <= 0` guard.

---

## Confirmed-fixed / verified-in-place (re-verified, not re-reported)

- **#97** — `optimize_tempo_changes`/`_smooth_tempo_transitions`/`_align_to_frames`/
  `_minimize_tempo_changes` remain dead on the live path; WARNING docstrings in place
  (`tracker/tempo_map.py:595-609`, `:682-693`); fast front-end still builds with
  `optimization_strategy=None` (`tracker/parser_fast.py:41`). Inert, documented.
- **#98** — `main.py:646` (`run_detect_patterns`) and `main.py:844` (`run_full_pipeline`)
  still construct default-PPQ `EnhancedTempoMap(initial_tempo=500000)` maps that never
  receive an `add_tempo_change`; analysis-only comments present at both sites. Inert,
  documented.
- **#259 / #260** — unified through `_build_tempo_map` (`tracker/parser_fast.py:26-69`);
  passes real `mid.ticks_per_beat` (`:38`) and counts + warns on dropped tempo changes
  (`:62-64`); both `parse_midi_to_frames` and `parse_midi_to_frames_with_analysis` share it.
- **#113** — bisect-based `_build_tempo_index`/`_cumulative_ms` (`:129-166`);
  `calculate_time_ms(0, tick)` remains an exact from-zero computation. Re-verified 0-frame
  drift on a synthetic 5-minute song with mid-song tempo changes (final frame 18000; max
  quantization error 0.5, no growth with song length).
- **#93 / #95** — SMPTE/zero/negative `ticks_per_beat`: `TempoMap.__init__` raises
  `ValueError` for `ticks_per_beat is None or < 1` (`:101-107`); `parse_midi_to_frames`
  rejects it earlier. Both agree on the `< 1` boundary.
- **#94** — widened 1–2000 BPM band with `max_tempo_change_ratio=float('inf')` and
  count-and-warn (`parser_fast.py:100-107`, `_build_tempo_map:62-64`). In place.
- **#96** — same-frame note collapse in `nes/emulator_core.py:16-46` (louder wins, later
  wins on tie at `:39`, warns with count). In place.
- **#99** — single `FRAME_ALIGNMENT_TOLERANCE_MS = 0.5` (`:23`) referenced by
  `is_frame_aligned` (`:259`), `_validate_frame_boundaries` (`:472`), `_check_frame_alignment`
  (`:863`). In place.
- **#160** — note-off pairing: `compile_channel_to_frames` derives `end_frame` from the
  matching note-off event, falling back to `sustain_frames` only when unpaired
  (`nes/emulator_core.py:54-93`); `range(start_frame, end_frame)` emits up to but not
  including the note-off frame. In place.
- **#208 / #209 / #210 / #211** — tick-0 tempo validation in `add_tempo_change`
  (`tempo_map.py:266-282`), zero/negative tempo guard in `_validate_basic_tempo`/
  `_validate_tempo_change` (`:396-399`/`:426-429`), duplicate-tick stable tie-break (`:125`,
  `:679`), and removal of the dead `_frame_times`/`_frame_cache` arrays — all re-verified in
  place. TEMPO-14 above is a distinct, unguarded sibling of #209 one level up the call stack
  (the constructor rather than `add_tempo_change`).

---

## Dedup notes

- Fetched `/tmp/audit/issues.json` (27 open issues) — no open issue matches
  `zerodivision`/`initial_tempo`/`tempo`/`frame`/`timing`/`drift`/`bpm`/`loop` keywords other
  than #91 (`ARR-08`, an unrelated arpeggiator-speed `ZeroDivisionError` in
  `arranger/voice_allocator.py`) and #300/#136/#112 (DPCM/tech-debt/dead-import, unrelated to
  tempo). No open tempo/frame-timing issue remains.
- `docs/audits/AUDIT_TEMPO_2026-07-17.md` (immediately prior pass) reported 0 findings; this
  pass's code is identical (`git diff` empty for all in-scope files), so all of its
  confirmed-fixed items were re-verified rather than re-derived from scratch.
- `docs/audits/AUDIT_TEMPO_2026-07-03.md` filed TEMPO-08 (`add_tempo_change`'s `tick == 0`
  early return skipping validation) and TEMPO-09 (`_validate_basic_tempo` dividing by
  `change.tempo` before guarding it) — both fixed by #208/#209 and re-verified above.
  TEMPO-14 in this report is a related-but-distinct third gap (the constructor's own
  `initial_bpm` computation) that neither of those fixes touched — reported separately per
  the dedup protocol rather than folded into #209, since it is a different code location with
  independent reachability (constructor arg vs. per-event tempo value).
- No other domain audit (`AUDIT_PIPELINE_*`, `AUDIT_SAFETY_*`, `AUDIT_PERFORMANCE_*`)
  references `EnhancedTempoMap.__init__`'s `initial_tempo` guard specifically.

---

Suggested next step:
```
/audit-publish docs/audits/AUDIT_TEMPO_2026-07-18.md
```
