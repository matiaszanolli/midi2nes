# Tempo & Frame-Timing Audit — 2026-07-05

## Summary

**Invariant verdict: frame timing stays on the 60Hz grid.** Re-verified empirically
against the current code: a 5-minute, 120 BPM song (`ticks_per_beat=480`, 288,000 ticks)
lands the final frame at exactly frame **18000** with **0 frames** of drift via the
bisect-based `_cumulative_ms`/`_build_tempo_index` path (#113). `calculate_time_ms(0, tick)`
still integrates from tick 0 on every call — `_cumulative_ms(end) - _cumulative_ms(start)`
with no accumulating running counter. Boundary checks pass: tick 0 → frame 0; a mid-song
tempo doubling at beat 1 lands tick 960 at frame 45 (500ms + 250ms = 750ms) exactly.

**Every finding from the prior pass (2026-07-03) is now fixed.** TEMPO-08 (tick-0
validation bypass) is closed by #208 — `add_tempo_change` now calls `_validate_basic_tempo`
before the tick-0 early return (`tracker/tempo_map.py:266-282`). TEMPO-09 (`ZeroDivisionError`
on `tempo=0`) is closed by #209 — both `_validate_basic_tempo` (`:396-399`) and
`_validate_tempo_change` (`:426-429`) now raise `TempoValidationError` on `tempo <= 0`
before dividing. TEMPO-10 (duplicate-tick tie-break) is closed by #210 —
`TempoMap.add_tempo_change` now sorts with `key=lambda c: c[0]` for stable "last event wins"
ordering (`:125`). TEMPO-11 (`_frame_times` dead array) is removed — zero occurrences in the
module. The earlier fixes (#93, #94, #95, #96, #99, #113, #160) all remain in place.

Two **residual LOW inconsistencies** remain, both isolated to
`parse_midi_to_frames_with_analysis` (the opt-in `--with-analysis` path, **not** the default
ROM pipeline): a silent `except TempoValidationError: continue` that diverges from the
fixed default parser's count-and-warn behavior, and a tempo map built **without**
`ticks_per_beat` that is then fed real-tick tempo changes. Both are new relative to the open
issues but are close relatives of #98. The two long-standing dead-code issues (#97, #98)
remain open, unchanged, and still accurately describe the code.

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 0 |
| MEDIUM   | 0 |
| LOW      | 2 |
| **Total**| **2** |

**Highest-leverage fix:** none is load-bearing this pass — the live timing path is clean.
The two LOW items should be folded into the `parse_midi_to_frames_with_analysis` cleanup
already implied by #97/#98: pass `ticks_per_beat=mid.ticks_per_beat` and count/warn on
dropped tempo changes exactly like the default `parse_midi_to_frames` does.

---

## Findings

### TEMPO-12: `parse_midi_to_frames_with_analysis` silently drops out-of-range tempo changes — diverges from the fixed default-path count-and-warn (#94)
- **Severity**: LOW
- **Dimension**: 4 (Extreme Tempo Bounds)
- **Location**: `tracker/parser_fast.py:199-202` (`except TempoValidationError: continue`, no counter, no warning), contrasted with the fixed default path at `tracker/parser_fast.py:85-94` (`dropped_tempo_changes += 1` + post-pass `print(...)`).
- **Status**: NEW
- **Description**: The default parser `parse_midi_to_frames` was fixed under #94 (TEMPO-02) to never drop a tempo change silently — it counts rejections in `dropped_tempo_changes` and prints a warning after the tempo pass. Its sibling `parse_midi_to_frames_with_analysis` rebuilds its own tempo map (`:186-202`) and still uses the pre-#94 idiom: a bare `except TempoValidationError: continue` with no counter and no user-facing warning. A tempo change rejected here (e.g. a tempo outside the widened 1–2000 BPM band, or a `tempo <= 0` now caught by #209) vanishes with no trace, and the affected section is analyzed at the preceding tempo.
- **Evidence**:
  ```python
  # parser_fast.py:198-202  (with_analysis path)
  if msg.type == 'set_tempo':
      try:
          tempo_map.add_tempo_change(current_tick, msg.tempo, TempoChangeType.IMMEDIATE)
      except TempoValidationError:
          continue        # <- silent; no count, no warning
  ```
  vs. the fixed default path:
  ```python
  # parser_fast.py:85-94
  except TempoValidationError:
      dropped_tempo_changes += 1
      continue
  ...
  if dropped_tempo_changes:
      print(f"Warning: dropped {dropped_tempo_changes} out-of-range tempo change(s); ...")
  ```
- **Impact**: Off the live ROM path (`--with-analysis` only; the metadata it produces — patterns/loops/jump_table — is not consumed by the default `parse → map → frames → export → compile` pipeline), so no ROM ships wrong music because of it. It is a consistency/observability gap: analysis run interactively can silently mis-tempo a section. The SKILL's Dimension 4 explicitly calls this out as a "low-severity residual inconsistency ... worth aligning for consistency."
- **Related**: #94 (TEMPO-02, closed — introduced the count-and-warn this path missed); TEMPO-13 (same function, same PPQ-omission cluster).
- **Suggested Fix**: Mirror the default path: count rejected changes in a local and `print` a single warning after the loop (or refactor the two tempo-collection passes into one shared helper so they cannot drift again).

---

### TEMPO-13: `parse_midi_to_frames_with_analysis` builds its tempo map without `ticks_per_beat`, then feeds it real-tick tempo changes — a latent PPQ trap distinct from #98
- **Severity**: LOW
- **Dimension**: 5 (PPQ / Division Parsing) / 3 (Default / Missing Tempo Fallback)
- **Location**: `tracker/parser_fast.py:186-190` (`EnhancedTempoMap(initial_tempo=500000, validation_config=config, optimization_strategy=None)` — no `ticks_per_beat`, so it defaults to 480) combined with `:193-200` (walks the real MIDI and calls `add_tempo_change(current_tick, ...)` at the file's actual ticks).
- **Status**: NEW
- **Description**: Unlike the default parser (`:62-67`), which passes `ticks_per_beat=mid.ticks_per_beat`, the analysis rebuild omits it and takes the constructor default of 480. It then adds real tempo changes keyed on the file's actual tick positions. If the file's PPQ ≠ 480, the tempo map's `ticks_per_beat` (480) disagrees with the ticks it stores. This is a different shape from #98's `main.py` sites: those never call `add_tempo_change` at all (truly inert, `get_tempo_at_tick` always returns the constant 500000). Here real tempo changes *are* recorded.
- **Evidence**: The map is inert **today** only because its two consumers are PPQ-independent: `get_tempo_at_tick`/bisect (`tempo_map.py:168-174`) returns a stored tempo value without any tick→time math, and `EnhancedPatternDetector._analyze_pattern_tempo` (`tracker/pattern_detector.py:434-468`) and `EnhancedLoopManager` (`tracker/loop_manager.py:127-128`) only ever call `get_tempo_at_tick`. No `calculate_time_ms`/`get_frame_for_tick` is invoked on this map, so the 480-vs-actual mismatch never reaches a time computation. Confirmed by grep: the only methods called on the analysis `tempo_map` are `add_tempo_change` and `get_tempo_at_tick` (+ `loop_points` dict access).
- **Impact**: No wrong output today (off the live ROM path, and no time math runs on the map). It is a fragile latent trap: if any future change on this path calls `get_frame_for_tick`/`calculate_time_ms` on this map (e.g. to re-derive frames or align loops), the hardcoded 480 would silently diverge from the file's real PPQ and mis-time everything. Same fragility class the SKILL flags for #98, but reachable through a map that actually holds tempo data.
- **Related**: #98 (TEMPO-06, open — inert default-PPQ maps in `main.py`; this is a third site with the same omission but non-inert tempo data); TEMPO-12 (same function).
- **Suggested Fix**: Pass `ticks_per_beat=mid.ticks_per_beat` when constructing the tempo map in `parse_midi_to_frames_with_analysis`. Better, reuse the tempo map already built by the first `parse_midi_to_frames` pass instead of rebuilding it (the code comment at `:176`/`:192` already notes it "could be cached from first pass").

---

## Confirmed-fixed (re-verified, not re-reported)

- **TEMPO-08 / #208** — tick-0 validation bypass: `EnhancedTempoMap.add_tempo_change` now calls `self._validate_basic_tempo(TempoChange(tick, tempo, ...))` **before** the tick-0 early return that replaces the initial tempo (`tracker/tempo_map.py:266-282`). A `tempo=0`/negative/out-of-range first `set_tempo` at tick 0 is now rejected like any other tick. Verified in place.
- **TEMPO-09 / #209** — `ZeroDivisionError` on `tempo=0`: both `_validate_basic_tempo` (`:396-399`) and `_validate_tempo_change` (`:426-429`) now raise `TempoValidationError` on `change.tempo <= 0` before the `60_000_000 / change.tempo` division, so `parser_fast.py`'s `except TempoValidationError` catches it non-fatally. Verified in place.
- **TEMPO-10 / #210** — duplicate-tick tie-break: `TempoMap.add_tempo_change` sorts with `key=lambda c: c[0]` (`:125`), relying on Python's stable sort so a later same-tick insertion sorts after earlier ones ("last event wins"), instead of the old bare `.sort()` that tie-broke on numeric tempo value. Verified in place.
- **TEMPO-11** — `_frame_times` dead numpy array: removed. `grep -n "_frame_times\|_frame_cache" tracker/tempo_map.py` → zero matches. Verified.
- **#113 (PERF-01)** — O(notes × tempo_changes) lookup: still the bisect-based `_build_tempo_index`/`_cumulative_ms` (`:129-166`); `calculate_time_ms(0, tick)` remains an exact from-zero computation. Re-verified 0-frame drift on a synthetic 5-minute song (final frame 18000, expected 18000).
- **#93/#95 (TEMPO-01/03)** — SMPTE/negative/zero `ticks_per_beat`: `TempoMap.__init__` raises `ValueError` for `ticks_per_beat is None or < 1` (`:101-107`); `parse_midi_to_frames` rejects it earlier (`:41-46`). Both guards agree on the `< 1` boundary. Verified.
- **#94 (TEMPO-02)** — widened 1–2000 BPM band + count-and-warn on drop in the default parser (`:55-94`). Verified (TEMPO-12 above is the *unfixed sibling* of this on the analysis path).
- **#96 (TEMPO-04)** — same-frame note collapse in `nes/emulator_core.py:16-46` (louder wins, later wins on tie, warns with count). Verified in place.
- **#99 (TEMPO-07)** — single `FRAME_ALIGNMENT_TOLERANCE_MS = 0.5` (`:23`) referenced by `is_frame_aligned` (`:259`), `_validate_frame_boundaries` (`:472`), and `_check_frame_alignment`. `_frame_cache` fully removed. Verified.
- **#160 (NH-20)** — note-off pairing: `compile_channel_to_frames` derives `end_frame` from the matching note-off in `all_events_sorted` (captured before same-frame collapse), falling back to `sustain_frames` only when unpaired (`nes/emulator_core.py:54-93`). Verified; `range(start_frame, end_frame)` correctly emits frames up to but not including the note-off frame.

## Confirmed still-open (no regression, no new information — left as filed)

- **#97 (TEMPO-05)** — `optimize_tempo_changes`, `_align_to_frames`, `_minimize_tempo_changes`, `_smooth_tempo_transitions`, and `EnhancedLoopManager` remain dead on the live path. `parse_midi_to_frames` (`:66`) and both `main.py` sites (`:509`, `:714`) pass/default `optimization_strategy=None`; `EnhancedLoopManager` is only instantiated in `parse_midi_to_frames_with_analysis` (`:206`) and the older `tracker/parser.py`. Note: within this dead code, `EnhancedLoopManager.detect_loops` passes loop *frame positions* (`loop_info['start']`/`['end']`) to `get_tempo_at_tick` (`loop_manager.py:127-128`), a frame-vs-tick unit mismatch — but it only affects the discarded loop metadata and is subsumed by #97's dead-code verdict. Still LOW as filed.
- **#98 (TEMPO-06)** — `main.py:509` (`run_detect_patterns`, with `analyze_tempo=False`) and `main.py:714` (`run_full_pipeline`) still construct a default-PPQ (480) `EnhancedTempoMap` that never receives an `add_tempo_change`; `get_tempo_at_tick` returns the constant 500000 regardless of PPQ. Confirmed still inert. Still LOW as filed. (TEMPO-13 above is a *related* third site that, unlike these two, does record real tempo changes.)

---

## Dedup notes

- Pre-fetched `/tmp/audit/issues.json` (32 open issues) contains no open issue matching TEMPO-12 (silent drop in the analysis parser) or TEMPO-13 (analysis-parser PPQ omission). The only open tempo issues are #97 and #98, both re-confirmed above and not describing these two items. TEMPO-08/09/10/11 from the prior pass are absent from the open list because they were filed and fixed (#208/#209/#210 are referenced by name in the current code comments; `_frame_times` was removed).
- `docs/audits/AUDIT_TEMPO_2026-07-03.md` (prior pass) and `AUDIT_TEMPO_2026-06-29.md` cover TEMPO-01…TEMPO-11. Neither describes the `parse_midi_to_frames_with_analysis` silent-drop or PPQ-omission specifically — the prior pass audited the default `parse_midi_to_frames` and the `main.py` sites, not the analysis rebuild's constructor.
- No other domain audit report references these two analysis-path items.

---

Suggested next step:
```
/audit-publish docs/audits/AUDIT_TEMPO_2026-07-05.md
```
