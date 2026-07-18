# Tempo & Frame-Timing Audit — 2026-07-18

## 1. Summary

**Invariant verdict: PASS.** Frame timing stays on the 60Hz grid. The keystone
conversion `get_frame_for_tick(tick) = round(calculate_time_ms(0, tick) / FRAME_MS)`
measures time **absolutely from tick 0** on every call, so rounding error is bounded
(±0.5 frame per note) and **does not accumulate**. Since #113 the lookup is a
bisect-based cumulative-ms index built in `np.float64`; the identity
`calculate_time_ms(0, t) == _cumulative_ms(t)` is exact (`_cumulative_ms(0) == 0.0`),
and segment boundaries are consistent (`bisect_right(ticks, t) - 1` makes a tempo change
effective *at* its tick, no off-by-one). A 5-minute song lands its final note within
±1 frame of `total_ms / FRAME_MS`. No cumulative-drift bug (D1), no mid-song multi-tempo
boundary bug (D2), PPQ guards agree at `< 1` in both places (D5), `_frame_times`/`_frame_cache`
dead state confirmed removed and the three alignment verdict predicates all reference the
single `FRAME_ALIGNMENT_TOLERANCE_MS` constant (D8).

All prior TEMPO-0x/1x findings referenced in the skill are confirmed fixed and in place
(#93, #94, #95, #96, #97, #98, #99, #113, #160, #208, #209, #210, #211, #259, #260). The
dead optimization/loop-alignment code (D7, #97) remains unreachable and is documented in
code with WARNING docstrings — not re-filed.

**Counts:** CRITICAL 0 · HIGH 0 · MEDIUM 0 · LOW 3 (2 NEW + 1 confirmed-existing).

**Highest-leverage fix:** none is a live-path timing-correctness bug. The most worthwhile
cleanup is TEMPO-15 — align the same-frame-collapse tie-break code with its own docstring
(one operator), since it is the only discrepancy that touches the live default pipeline.

## 2. Findings

### TEMPO-15: `_collapse_same_frame_events` keeps the *earlier* note on a velocity tie, contradicting its docstring
- **Severity**: LOW
- **Dimension**: 4 (Extreme Tempo Bounds — same-frame collapse)
- **Location**: `nes/emulator_core.py:24-45` (docstring line 24, comment line 38, logic line 37)
- **Status**: NEW
- **Description**: Both the method docstring ("ties keep the later event", line 24) and the
  inline comment ("equal velocity keeps the later one", line 38) claim that when two note-ons
  quantize to the same 60Hz frame and have equal velocity, the *later* event is retained. The
  code does the opposite. Events are stably sorted by frame only (`key=lambda e: e['frame']`),
  so among same-frame events original input order is preserved and the first-encountered is
  appended to `kept` first. The tie-break is `if vel > prev_vel: kept[-1] = e` — a *strict*
  greater-than, so on equal velocity the already-kept (earlier) event is retained and the
  later one is dropped.
- **Evidence**:
  ```python
  for e in note_ons:                       # note_ons sorted by frame (stable)
      vel = e.get('velocity', e.get('volume', 0))
      if kept and kept[-1]['frame'] == e['frame']:
          dropped += 1
          prev_vel = kept[-1].get('velocity', kept[-1].get('volume', 0))
          if vel > prev_vel:               # strict '>' → tie keeps kept[-1] (earlier)
              kept[-1] = e
      else:
          kept.append(e)
  ```
- **Impact**: Deterministic but incorrect per the documented contract. Blast radius is a single
  note on a monophonic channel when two equal-velocity note-ons collapse to one frame
  (legacy/default non-arranger path; the arranger arpeggiates polyphony and does not hit this).
  Musically the choice between two equal-velocity simultaneous notes is arbitrary, so audible
  impact is minimal — this is a doc/code contradiction, not timing drift. Keeping the *later*
  note (most recently struck) is arguably the more musical choice, which is presumably why the
  docs say so.
- **Related**: Fix of #96/TEMPO-04 (the collapse itself, correct otherwise).
- **Suggested Fix**: Change `if vel > prev_vel` to `if vel >= prev_vel` so a tie keeps the later
  event as documented; or, if the earlier note is intentional, correct the docstring/comment
  instead. Add a test asserting the tie outcome.

### TEMPO-16: `EnhancedLoopManager` passes pattern event-indices to `get_tempo_at_tick` as ticks (unit mismatch)
- **Severity**: LOW
- **Dimension**: 6 (Loop-Point Frame Alignment)
- **Location**: `tracker/loop_manager.py:127-128` (and `156`); positions originate in
  `tracker/pattern_detector.py:324` (`_find_pattern_matches` → `exact_matches` → `positions`)
- **Status**: NEW
- **Description**: `LoopManager.detect_loops` builds each loop's `start`/`end` from pattern
  `positions` + `length`. Those `positions` are **indices into the note-on event list**
  (returned by `_find_pattern_matches`, which enumerates the event sequence), not MIDI ticks
  and not frame numbers. `EnhancedLoopManager.detect_loops` then calls
  `self.tempo_map.get_tempo_at_tick(loop_info['start'])` and `...['end'])` — feeding an event
  index into a function whose parameter is a MIDI tick. For a single-tempo song this is harmless
  (the lookup returns the one constant tempo regardless of the argument), but for a multi-tempo
  song the tempo stamped onto a loop boundary is read at the wrong position and can be wrong.
- **Evidence**:
  ```python
  # loop_manager.py — loop_info['start']/['end'] are event indices…
  start_tempo = self.tempo_map.get_tempo_at_tick(loop_info['start'])   # …used as a tick
  end_tempo   = self.tempo_map.get_tempo_at_tick(loop_info['end'])
  ```
  ```python
  # pattern_detector.py:324 — positions are sequence indices, not ticks/frames
  def _find_pattern_matches(self, sequence, pattern, start_pos) -> List[int]:
  ```
- **Impact**: Latent only. `EnhancedLoopManager` is **not on the default pipeline**; it is reached
  solely via `parse_midi_to_frames_with_analysis` (opt-in `--with-analysis`) and the older
  `tracker/parser.py`. The resulting `loop_points`/`jump_table` `tempo_state` is analysis metadata
  that no exporter consumes to build a ROM today, so no shipped ROM loops at the wrong tempo. It
  becomes a real bug the moment loop metadata is wired into ROM generation.
- **Related**: Sibling to the D3 default-PPQ "analysis-only tempo map" inertness (#98).
- **Suggested Fix**: Convert `positions` to ticks/frames before the tempo lookup (the note-on
  events carry a `frame` field; map index → `events[idx]['frame']` and query by the time domain
  the tempo map actually indexes), or document the boundary values as event indices and drop the
  tempo-at-tick lookup until loops feed real timing.

### TEMPO-14: `EnhancedTempoMap.__init__` divides by `initial_tempo` before any zero/negative guard
- **Severity**: LOW
- **Dimension**: 3 (Default / Missing Tempo Fallback)
- **Location**: `tracker/tempo_map.py:235`
- **Status**: Existing: #317 (OPEN) — confirmed still present, not re-filed
- **Description**: `initial_bpm = 60_000_000 / initial_tempo` runs before `super().__init__` (and
  before any tempo-value guard). For `initial_tempo == 0` this raises a bare `ZeroDivisionError`
  instead of the intended `TempoValidationError`. Negative `initial_tempo` is handled correctly
  (negative BPM fails the range check → `TempoValidationError`); only the zero case escapes as the
  wrong exception type.
- **Evidence**:
  ```python
  self.validation_config = validation_config or TempoValidationConfig()
  initial_bpm = 60_000_000 / initial_tempo   # ZeroDivisionError when initial_tempo == 0
  if not (min_bpm <= initial_bpm <= max_bpm):
      raise TempoValidationError(...)
  super().__init__(initial_tempo, ticks_per_beat)
  ```
- **Impact**: Robustness only. No live caller passes `initial_tempo=0` — `parser_fast` and both
  `main.py` sites hardcode `500000`, and per-tick `set_tempo` zeros are already rejected by
  `_validate_basic_tempo` (#209). Affects only a programmatic caller constructing the map with a
  zero initial tempo, which gets an unhelpful exception type.
- **Related**: #209 (TEMPO-09, per-tick zero tempo), #208 (TEMPO-08, tick-0 validation).
- **Suggested Fix** (already tracked in #317): guard `initial_tempo <= 0` and raise
  `TempoValidationError` before the division.

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_TEMPO_2026-07-18.md
```
