# Tempo & Frame-Timing Audit — 2026-06-29

## Summary

**Invariant verdict: the core tick→frame model is sound on the default pipeline path —
it does NOT drift off the 60Hz grid over a song.** `get_frame_for_tick` measures
`calculate_time_ms(0, tick)` from t=0 on every call (absolute, not accumulated), kept in
`np.float64`, so a 5-minute 120 BPM song lands the final note exactly on frame 18000 with
**0 frames** of drift (verified empirically). Dimension 1 is clean.

The real risks are at the **edges of the input space**, not in the steady-state math:

1. **SMPTE / negative MIDI division is passed straight through and produces negative frame
   indices** (HIGH, NEW) — the single highest-leverage fix. `parser_fast.py` forwards
   `mid.ticks_per_beat` unchecked; mido returns it negative for SMPTE-division files, so
   `us_per_tick` goes negative, time goes negative, and every note lands at a negative
   frame. Silent corruption of valid MIDI.
2. **Legitimate out-of-range / large-jump tempo changes are silently dropped** in the fast
   parser (HIGH, NEW) — `except TempoValidationError: continue` discards a 30 BPM, 280 BPM,
   or a 200→60 BPM section change with no warning; the song then plays at the wrong tempo.
3. **`ticks_per_beat == 0` yields `inf` time with only a RuntimeWarning** (MEDIUM, NEW) —
   no guard; produces `inf`/garbage frames instead of failing fast.

Most of the heavy machinery the SKILL flags as risky — `optimize_tempo_changes`,
`_align_to_frames`, `_smooth_tempo_transitions`, the FRAME_ALIGNED binary-search re-snapping
in `add_tempo_change`, and the entire `EnhancedLoopManager` loop-point/jump-table path — is
**dead on the live pipeline**: the default front-end constructs `EnhancedTempoMap(...,
optimization_strategy=None)` and uses `parse_midi_to_frames` (empty metadata), never
`parse_midi_to_frames_with_analysis`. Those paths are reported at reduced severity as latent
traps, not active bugs.

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 2 |
| MEDIUM   | 2 |
| LOW      | 3 |
| **Total**| **7** |

**Highest-leverage fix:** validate/normalize `ticks_per_beat` at the parser boundary
(`parser_fast.py:24-29`) — reject or convert SMPTE/negative/zero division before it reaches
`EnhancedTempoMap`. This closes TEMPO-01 (HIGH) and TEMPO-03 (MEDIUM) at one site.

---

## Findings

### TEMPO-01: SMPTE / negative `ticks_per_beat` produces negative frame indices
- **Severity**: HIGH
- **Dimension**: 5 (PPQ / Division Parsing)
- **Location**: `tracker/parser_fast.py:24-29` (and `:14` where `mid = mido.MidiFile`); consumed in `tracker/tempo_map.py:129` (`us_per_tick = np.float64(current_tempo) / self.ticks_per_beat`) and `:144-147` (`get_frame_for_tick`).
- **Status**: NEW
- **Description**: `parse_midi_to_frames` passes `ticks_per_beat=mid.ticks_per_beat` to `EnhancedTempoMap` with no validation. For SMPTE-division MIDI files (division word with bit 15 set), **mido returns `ticks_per_beat` as a negative integer**. `calculate_time_ms` then computes `us_per_tick = tempo / ticks_per_beat < 0`, so elapsed time is negative and `round(time_ms / FRAME_MS)` yields **negative frame indices**. Nothing downstream guards against a negative `frame`, so events are written at negative JSON keys / negative `range()` bounds and silently corrupt the song.
- **Evidence**: Constructed a raw SMPTE header (`division = -3200`); `mido.MidiFile` parsed it with `ticks_per_beat == -3200`. Then:
  ```
  EnhancedTempoMap(initial_tempo=500000, ticks_per_beat=-3200, optimization_strategy=None)
  tm.calculate_time_ms(0, 6400)  -> -1000.0
  tm.get_frame_for_tick(6400)    -> -60
  ```
  The only other PPQ source in the live path is the `EnhancedTempoMap(initial_tempo=500000)` at `main.py:277`/`main.py:453`, which defaults to `ticks_per_beat=480` but is inert (see TEMPO-06).
- **Impact**: Any SMPTE-timed MIDI (legal, exported by some DAWs/notation tools) compiles to garbage: notes at negative frames, wrong total length, likely silent or scrambled playback. Blast radius is the whole song, at the parse stage, for every channel. No error surfaces.
- **Related**: TEMPO-03 (`ticks_per_beat == 0` from same unvalidated boundary); SAFE-07 in `docs/audits/AUDIT_SAFETY_2026-06-29.md` (per-event drop, different line); does not overlap any open GH issue.
- **Suggested Fix**: In `parse_midi_to_frames`, after opening the file, check `mid.ticks_per_beat > 0`; if mido reports a non-metrical (SMPTE) division, either raise a clear error or convert SMPTE frame/sub-frame timing to a positive PPQ before constructing the tempo map. Add an assertion in `TempoMap.__init__` that `ticks_per_beat >= 1`.

---

### TEMPO-02: Valid out-of-range and large-jump tempo changes silently dropped in fast parser
- **Severity**: HIGH
- **Dimension**: 4 (Extreme Tempo Bounds)
- **Location**: `tracker/parser_fast.py:39-48` (`except TempoValidationError: continue`); validation thresholds at `:18-23` (40–250 BPM) and ratio gate in `tracker/tempo_map.py:344-353` (`max_tempo_change_ratio = 3.0`, default `TempoValidationConfig` `:27`).
- **Status**: NEW
- **Description**: The fast parser overrides the tempo range to 40–250 BPM and swallows any `TempoValidationError` from `add_tempo_change` with a bare `continue` ("Skip invalid tempo changes silently for performance"). Two classes of **legitimate** MIDI tempo are therefore discarded with no warning: (a) tempos below 40 BPM or above 250 BPM (largo / very fast pieces), and (b) any tempo change whose ratio to the previous tempo exceeds 3.0 — a normal section-boundary jump such as 200→60 BPM. When a change is dropped, the previous (or default 120 BPM) tempo persists, so **the song plays at the wrong tempo from that point on**, silently.
- **Evidence**: With the parser's own config (40–250 BPM):
  ```
  add_tempo_change(480, us(30 BPM))   -> TempoValidationError (REJECTED, then `continue`)
  add_tempo_change(960, us(280 BPM))  -> TempoValidationError (REJECTED)
  add_tempo_change(480, us(200)); add_tempo_change(960, us(60))
                                      -> "Tempo change ratio 3.33 exceeds maximum 3.0" (REJECTED)
  ```
  In `parse_midi_to_frames` each of these is caught at `:46` and the song keeps the prior tempo.
- **Impact**: Wrong global/sectional tempo for any MIDI outside the narrow 40–250 BPM band or with a sharp tempo change — common in classical/film transcriptions. Per the severity table this is "silent wrong output" → HIGH. Distinct from the *note*-drop already filed in SAFE-07 (which explicitly notes this tempo skip is separate and unaddressed).
- **Related**: SAFE-07 (`docs/audits/AUDIT_SAFETY_2026-06-29.md:107`) covers the per-note `except Exception` at `:77` and explicitly scopes itself away from this tempo skip. No open GH issue.
- **Suggested Fix**: Widen the fast-parser `TempoValidationConfig` to the full musically-valid range and relax/remove `max_tempo_change_ratio` for parsing (it is an authoring heuristic, not a hardware limit), or — at minimum — count and warn on dropped tempo changes instead of silently continuing, so a user can see the timing is wrong.

---

### TEMPO-03: `ticks_per_beat == 0` produces `inf` time instead of failing fast
- **Severity**: MEDIUM
- **Dimension**: 5 (PPQ / Division Parsing)
- **Location**: `tracker/tempo_map.py:129` and `:141` (`tempo / self.ticks_per_beat`); unguarded constructor `tracker/tempo_map.py:77-87` / `:175-194`; boundary `tracker/parser_fast.py:24-29`.
- **Status**: NEW
- **Description**: There is no guard against `ticks_per_beat == 0`. `calculate_time_ms` divides by it, yielding `inf` (only a `RuntimeWarning`, no exception), and every `get_frame_for_tick` returns `inf` → all frames collapse to a garbage index. A malformed MIDI header or any caller passing 0 corrupts the whole song without an error.
- **Evidence**:
  ```
  EnhancedTempoMap(initial_tempo=500000, ticks_per_beat=0, optimization_strategy=None)
  tm.calculate_time_ms(0, 480)  -> inf   (RuntimeWarning: divide by zero)
  ```
- **Impact**: Defense-in-depth gap at the same parse boundary as TEMPO-01. Less likely than SMPTE (mido usually rejects a 0-division header) but the class is unguarded; produces `inf` frames rather than a clean failure.
- **Related**: TEMPO-01 (same unvalidated `ticks_per_beat` boundary — fix together).
- **Suggested Fix**: Add `if ticks_per_beat < 1: raise ValueError(...)` (or `TempoValidationError`) in `TempoMap.__init__`, covering both the 0 and negative cases.

---

### TEMPO-04: Two notes that round to the same frame collapse — the first is lost
- **Severity**: MEDIUM
- **Dimension**: 4 (Extreme Tempo Bounds)
- **Location**: `nes/emulator_core.py:32-41` (`end_frame = start_frame + sustain_frames`; truncation only when `next_event['frame'] > start_frame`) and `:54`/`:48-60` (frame dict keyed on `f`, last write wins); root quantization at `tracker/tempo_map.py:144-147`.
- **Status**: NEW
- **Description**: At very fast tempo (or fine sequencing), two distinct note-on ticks can `round()` to the **same** 60Hz frame. In `compile_channel_to_frames` the truncation guard requires `next_event['frame'] > start_frame`, so a same-frame successor does not shorten the prior note; instead both notes write the same `frames[f]` key and the **second silently overwrites the first** for every shared frame. The first note is dropped entirely.
- **Evidence**:
  ```
  compile_channel_to_frames([{'frame':10,'note':60,'volume':100},
                             {'frame':10,'note':67,'volume':100}], 'pulse')
  -> {10:67, 11:67, 12:67, 13:67}   # note 60 gone
  ```
- **Impact**: At high tempo / dense passages a note is silently lost on a channel (data loss, but bounded — it is inherent to 60Hz quantization, and a workaround exists via slower tempo / arranger arpeggiation). MEDIUM. Note the same overwrite happens for any two same-frame events regardless of tempo; tempo just makes it reachable from legal MIDI.
- **Related**: Inherent to the 60 FPS model (`docs/APU_FRAME_COUNTER_REFERENCE.md` — one frame = 1/60s); NH-08 (#34) is a different emulator_core issue (pulse volume), not this collapse.
- **Suggested Fix**: When two note-ons land on the same frame on one channel, either keep the higher-priority/last note deliberately (documented) or nudge the second to `start_frame+1`; at minimum count collapsed notes so the loss is visible.

---

### TEMPO-05: Dead optimization & loop-alignment code on the live path (`optimize_tempo_changes`, `EnhancedLoopManager`)
- **Severity**: LOW
- **Dimension**: 7 (Validation / Optimization Fidelity) and 6 (Loop-Point Frame Alignment)
- **Location**: `tracker/tempo_map.py:507-611` (`_minimize_tempo_changes`, `_smooth_tempo_transitions`, `_align_to_frames`, `optimize_tempo_changes`); `add_tempo_change` FRAME_ALIGNED re-snap `:243-285`; `tracker/loop_manager.py:115-159` (`EnhancedLoopManager`).
- **Status**: NEW
- **Description**: The SKILL flags several timing-mutating routines as risky (e.g. `_smooth_tempo_transitions` adds intermediate tempos via **linear interpolation of µs/quarter**, which is not linear in elapsed time and would change segment duration; the FRAME_ALIGNED branch of `add_tempo_change` re-snaps `change.tick` via binary search and could in principle reorder events; `_minimize_tempo_changes` drops sub-5% changes). I confirmed these are **not reachable on the default pipeline**: `optimize_tempo_changes` has **zero call sites** anywhere in the repo, and the live front-end builds the tempo map with `optimization_strategy=None` (`tracker/parser_fast.py:29`), so the FRAME_ALIGNED re-snap and gradual-step paths in `add_tempo_change` are never taken. Likewise `EnhancedLoopManager.detect_loops`/`generate_jump_table` only run inside `parse_midi_to_frames_with_analysis` and `tracker/parser.py`, neither of which is on the default MIDI→ROM path (`main.py:421` uses `parse_fast`, whose metadata is empty and whose jump tables are never consumed by the exporter/builder).
- **Evidence**: `grep -rn "optimize_tempo_changes"` → only the definition in `tempo_map.py`. `grep -rn "EnhancedLoopManager"` → only `parser_fast.py:99/129` (inside the unused `_with_analysis`) and `parser.py:72` (legacy). `main.py:421` calls `parse_midi_to_frames` (fast), which returns `"metadata": {}`.
- **Impact**: No active timing bug, but this is a maintenance/latent-trap hazard: if a future change wires `optimize_tempo_changes` or the analysis parser into the live path, the duration-changing `_smooth_tempo_transitions` and the reorder-capable FRAME_ALIGNED re-snap become real HIGH bugs. LOW today (dead code / hardening).
- **Related**: PERF-08 / PERF-01 in `docs/audits/AUDIT_PERFORMANCE_2026-06-29.md` (tempo map rebuilt / O(T) scans); TEMPO-06.
- **Suggested Fix**: Either delete the unused optimization/loop-analysis paths or add tests pinning their timing-preservation invariants *before* any future wiring; document that `_smooth_tempo_transitions` linearly interpolates µs/quarter (not elapsed time) and must not be used to preserve note timing.

---

### TEMPO-06: `detect-patterns` / pipeline build a default-PPQ tempo map that is inert
- **Severity**: LOW
- **Dimension**: 3 (Default / Missing Tempo Fallback)
- **Location**: `main.py:277` (`EnhancedTempoMap(initial_tempo=500000)` — no `ticks_per_beat`, defaults to 480) and `main.py:453`; consumed by `tracker/pattern_detector.py:387-411` (`_analyze_pattern_tempo` → `get_tempo_at_tick`).
- **Status**: NEW (overlaps the analysis in PERF-08, `docs/audits/AUDIT_PERFORMANCE_2026-06-29.md:125-132`; no open GH issue)
- **Description**: The pattern-detection stage constructs a fresh `EnhancedTempoMap` with the default `ticks_per_beat=480`, not the file's resolution, and **never adds the file's tempo changes** to it. The SKILL asks whether this PPQ mismatch affects output. It does not: the detector operates on already-framed events keyed by `frame`, and `_analyze_pattern_tempo` calls `get_tempo_at_tick(frame_position)` on a tempo map that has only the constant default tempo — the result (`base_tempo`) is stored as pattern metadata and never feeds frame timing. I confirmed `get_tempo_at_tick` returns a constant 500000 here regardless of PPQ, so the 480 default is harmless.
- **Evidence**: `main.py:277`/`:453` construct the map empty; the framed events have no `set_tempo` re-applied; `pattern_detector.py:387` indexes by `tick` that is actually a frame position. The PERF audit reached the same conclusion ("harmless only because it is unused — a latent trap").
- **Impact**: No incorrect output today. Latent trap: if a future change starts deriving timing from this map it would use the wrong PPQ and a constant tempo. LOW (doc / dead-construction).
- **Related**: PERF-08 (wasted construction); TEMPO-05 (other dead tempo path).
- **Suggested Fix**: Drop the unused `EnhancedTempoMap` construction at `main.py:277`/`:453`, or, if kept, pass the real `ticks_per_beat` and the file's tempo changes and add a comment that it is analysis-only.

---

### TEMPO-07: `_frame_cache` is never read; inconsistent frame-alignment tolerances across methods
- **Severity**: LOW
- **Dimension**: 8 (Frame-Edge Off-By-One) / 7
- **Location**: `tracker/tempo_map.py:201,223,299,604,611` (`_frame_cache` only ever assigned); tolerance constants at `:209` (`< 0.001`), `:252`/`:272` (`> 1.0` / `< 1.0`), `:281` (`> 2.0`), `:322` (`< 0.001`), `:398` (`> 0.5`), `:660` (`> 0.01`), `:762` (`> 1` µs).
- **Status**: NEW
- **Description**: `_frame_cache` is initialized and cleared in five places but never read — dead state. Separately, the various frame-alignment helpers use mutually inconsistent thresholds: `is_frame_aligned` accepts `< 0.001 ms`, `add_tempo_change` treats `> 1.0 ms` as misaligned and warns only beyond `2.0 ms`, `_validate_frame_boundaries` errors at `> 0.5 ms`, `_check_frame_alignment` errors at `> 1 µs`. A tempo change can be "aligned" by one method and "misaligned" by another. Because all these methods are on the dead optimization path (TEMPO-05), there is no live impact today.
- **Evidence**: `grep -n "_frame_cache" tracker/tempo_map.py` shows assignments only, no reads. Threshold literals enumerated above.
- **Impact**: Code-quality / maintainability; would become a real inconsistency if the alignment methods were wired into the live path. LOW.
- **Related**: TEMPO-05 (same dead alignment machinery).
- **Suggested Fix**: Remove `_frame_cache`; consolidate the alignment tolerance into one named constant (e.g. half a frame) referenced by all alignment checks.

---

## Dedup notes

- Open-issue list (`/tmp/audit/issues.json`, 22 issues) contains **no tempo/frame-timing
  finding** — all seven here are NEW.
- `docs/audits/`: no prior tempo audit. **SAFE-07** (`AUDIT_SAFETY_2026-06-29.md`) covers the
  per-*note* `except Exception` drop at `parser_fast.py:77` and explicitly excludes the
  tempo-change skip at `:46` — so TEMPO-02 is genuinely new. **PERF-08/PERF-01**
  (`AUDIT_PERFORMANCE_2026-06-29.md`) independently noted the wasted `EnhancedTempoMap` at
  `main.py:453` with the wrong PPQ and confirmed it is inert; TEMPO-06 cross-references that
  and stays LOW.

---

Suggested next step:
```
/audit-publish docs/audits/AUDIT_TEMPO_2026-06-29.md
```
