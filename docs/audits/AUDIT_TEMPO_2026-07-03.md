# Tempo & Frame-Timing Audit — 2026-07-03

## Summary

**Invariant verdict: the steady-state tick→frame model remains sound.** Re-verified
empirically: a 5-minute, 120 BPM song (`ticks_per_beat=480`, 288,000 ticks) lands the
final frame at exactly frame 18000 with **0 frames** of drift via the bisect-based
`_cumulative_ms`/`_build_tempo_index` path (#113). `calculate_time_ms(0, tick)`
still integrates from tick 0 on every call — no running/accumulating counter. All
previously-filed HIGH findings from the 2026-06-29 audit (TEMPO-01 SMPTE/negative
`ticks_per_beat`, TEMPO-02 dropped out-of-range tempo changes, TEMPO-03
`ticks_per_beat==0`, TEMPO-04 same-frame note collapse, TEMPO-07 tolerance
inconsistency/`_frame_cache`) are **confirmed fixed** in the current code (#93, #94,
#95, #96, #99 all closed and verified in place). TEMPO-05 (#97, dead
optimization/loop code) and TEMPO-06 (#98, inert default-PPQ pattern-metadata tempo
map) remain **open and still accurately describe the code** — no regression, no new
information, left as-is.

However, this pass found a **new, previously-unaudited failure class** that the prior
audit's constructor-boundary fixes (#93/#95) did not fully close: **`tick == 0` tempo
changes bypass validation entirely**, and **`tempo == 0` at any tick is unguarded**.
Both are reachable from the live default pipeline (`main.py` → `parse_fast` →
`tracker/parser_fast.py:parse_midi_to_frames` → `EnhancedTempoMap.add_tempo_change`)
on structurally-valid (if degenerate/malformed) MIDI input, and both were verified
by parsing real, saved `.mid` files end-to-end — not just unit-level API calls.

| Severity | Count |
|----------|-------|
| CRITICAL | 1 |
| HIGH     | 2 |
| MEDIUM   | 0 |
| LOW      | 2 |
| **Total**| **5** |

**Highest-leverage fix:** route `tick == 0` tempo changes through the same
`_validate_basic_tempo` check as every other tick in `EnhancedTempoMap.add_tempo_change`
(`tracker/tempo_map.py:262-271`), and add an explicit `tempo >= 1` guard next to the
existing `ticks_per_beat >= 1` guard. This closes TEMPO-08 (CRITICAL) and removes the
crash surface behind TEMPO-09 (HIGH) at the same two sites.

---

## Findings

### TEMPO-08: `tick == 0` tempo changes bypass all validation — zero/negative initial tempo silently corrupts the whole song
- **Severity**: CRITICAL
- **Dimension**: 3 (Default / Missing Tempo Fallback) and 5 (PPQ / Division Parsing)
- **Location**: `tracker/tempo_map.py:262-271` (the `if tick == 0:` early-return branch of `EnhancedTempoMap.add_tempo_change`); contrast with the validated path at `:277` (`self._validate_basic_tempo(change)`) taken for every `tick != 0`.
- **Status**: NEW
- **Description**: `EnhancedTempoMap.add_tempo_change` special-cases `tick == 0` to replace the initial tempo directly (`self.tempo_changes[0] = (0, tempo)`) and returns immediately — **before** `_validate_basic_tempo` (BPM-range check) is ever called. Every other tick goes through `_validate_basic_tempo`, which would reject a 0 or out-of-range BPM. A MIDI file whose very first `set_tempo` meta-event (at tick 0, which is exactly where DAWs conventionally place the initial tempo) carries `tempo=0` or a negative value is therefore accepted unconditionally, with no `TempoValidationError` and no warning. This is the same class of bug as the already-fixed #93 (negative frame indices) and #95 (`ticks_per_beat==0` → `inf`), but reachable through the *tempo* value at tick 0 rather than `ticks_per_beat` — a path those fixes did not close.
- **Evidence**: Built and parsed a real `.mid` file (`ticks_per_beat=480`) whose first event is `MetaMessage('set_tempo', tempo=0, time=0)`, followed by two notes, then a later `set_tempo(500000)` recovery event, through the actual `parse_midi_to_frames`:
  ```
  track_0 {'frame': 0, 'note': 60, 'volume': 100, 'type': 'note_on', ..., 'tempo': 0}
  track_0 {'frame': 0, 'note': 60, 'volume': 0,   'type': 'note_off', ..., 'tempo': 0}
  track_0 {'frame': 0, 'note': 64, 'volume': 100, 'type': 'note_on', ..., 'tempo': 0}
  track_0 {'frame': 0, 'note': 64, 'volume': 0,   'type': 'note_off', ..., 'tempo': 500000}
  track_0 {'frame': 0, 'note': 67, 'volume': 100, 'type': 'note_on', ..., 'tempo': 500000}
  track_0 {'frame': 300,'note': 67, 'volume': 0,  'type': 'note_off', ..., 'tempo': 500000}
  ```
  Every event before the real tempo change (notes 60 and 64, an arbitrarily long musical passage in the source MIDI) collapses onto **frame 0** — `us_per_tick = tempo/ticks_per_beat = 0`, so `calculate_time_ms` never advances no matter how many ticks elapse in that segment. Separately, a **negative** tempo at tick 0 (`add_tempo_change(0, -500000, ...)`) is likewise accepted with no error and produces **negative frame indices for the entire song** — reproducing #93's exact symptom via a different, un-guarded entry point:
  ```
  tm.add_tempo_change(0, -500000, TempoChangeType.IMMEDIATE)
  tm.get_frame_for_tick(480)   -> -30
  tm.get_frame_for_tick(4800)  -> -300
  ```
- **Impact**: Silent, total corruption of song timing from t=0. Every note before the (if any) next valid tempo change either collapses onto one frame (tempo=0, effectively deleting the passage's timing and leaving only the last-processed note's data per frame — the emulator core's same-frame collapse (#96) then drops all but one note) or is written at negative JSON frame keys (negative tempo), which downstream stages (`nes/emulator_core.py`, exporters) do not guard against. No error, no warning — the ROM compiles "successfully" with scrambled or missing music. Meets the severity table's explicit floor: "Pipeline stage emits data a downstream stage parses as valid but means something else" and "silently changes the song" → CRITICAL.
- **Related**: Same symptom class as closed #93 (SMPTE/negative `ticks_per_beat`) and closed #95 (`ticks_per_beat==0`), but via the tempo value at tick 0, which those fixes' guards (in `TempoMap.__init__` and `parser_fast.py`'s `ticks_per_beat` check) do not cover. Distinct root cause from TEMPO-09 below (which is the `tick > 0` counterpart).
- **Suggested Fix**: Call `_validate_basic_tempo(change)` (or at minimum a `tempo >= 1` and BPM-range check) before the `tick == 0` early return in `EnhancedTempoMap.add_tempo_change`, so tick 0 is held to the same standard as every other tick.

---

### TEMPO-09: `set_tempo(tempo=0)` at any tick > 0 raises an unguarded `ZeroDivisionError`, crashing the entire parse
- **Severity**: HIGH
- **Dimension**: 3 (Default / Missing Tempo Fallback)
- **Location**: `tracker/tempo_map.py:382` (`bpm = round(60_000_000 / change.tempo, 6)` in `_validate_basic_tempo`), reached via `add_tempo_change` at `:277`; the call site that fails to catch it is `tracker/parser_fast.py:65-77` (`except TempoValidationError: continue` — does not catch `ZeroDivisionError`).
- **Status**: NEW
- **Description**: `_validate_basic_tempo` computes `bpm = 60_000_000 / change.tempo` with no zero-guard, before the BPM-range check that would otherwise reject an invalid tempo via the intended `TempoValidationError` path. For `tick > 0` (the tick-0 bypass of TEMPO-08 does not apply here — this path *does* reach `_validate_basic_tempo`), a `set_tempo` meta-event with `tempo=0` raises a raw `ZeroDivisionError`, a different exception class than the one `parse_midi_to_frames`'s per-tempo-change handler explicitly guards against (`except TempoValidationError: continue`, added by #94 specifically to make invalid tempo changes non-fatal). The `ZeroDivisionError` therefore propagates uncaught out of `parse_midi_to_frames`, aborting the entire pipeline run for the whole file — not just the offending section.
- **Evidence**: Built and parsed a real `.mid` file with a `set_tempo(tempo=0)` meta-event after an initial valid tempo and one note, through the actual `parse_midi_to_frames`:
  ```
  Traceback (most recent call last):
    File "tracker/parser_fast.py", line 67, in parse_midi_to_frames
      tempo_map.add_tempo_change(
    File "tracker/tempo_map.py", line 277, in add_tempo_change
      self._validate_basic_tempo(change)
    File "tracker/tempo_map.py", line 382, in _validate_basic_tempo
      bpm = round(60_000_000 / change.tempo, 6)
                  ~~~~~~~~~~~~^~~~~~~~~~~~~~~~
  ZeroDivisionError: division by zero
  ```
- **Impact**: Total pipeline failure (no JSON, no ROM, an unhandled Python traceback surfaced to the CLI user) for any MIDI file containing a degenerate/corrupted `tempo=0` event anywhere after tick 0 — precisely the class of malformed input the `except TempoValidationError` guard at `parser_fast.py:72` (added for #94) was written to make non-fatal. A single bad meta-event in one track kills the whole conversion instead of being counted/warned like every other rejected tempo change. There is a workaround (repair the source MIDI), so this is not CRITICAL, but it is a hard crash on realistic (if unusual) input where graceful degradation was clearly the intended design.
- **Related**: TEMPO-08 (same `tempo == 0` degenerate value, but the `tick == 0` counterpart silently corrupts instead of crashing); the `except TempoValidationError` guard this bypasses was introduced for #94 (TEMPO-02, closed).
- **Suggested Fix**: Guard `change.tempo >= 1` at the top of `_validate_basic_tempo` (and `_validate_tempo_change`) and raise `TempoValidationError` instead of dividing, so the existing `except TempoValidationError: continue` in `parser_fast.py` catches it like any other invalid tempo (and increments `dropped_tempo_changes` so the user is warned, per #94's fix).

---

### TEMPO-10: Duplicate tempo changes at the same tick resolve by numeric tempo value, not file/insertion order — violates MIDI "last event wins" semantics
- **Severity**: HIGH
- **Dimension**: 2 (Mid-Song & Multiple Tempo Changes)
- **Location**: `tracker/tempo_map.py:118-119` (`TempoMap.add_tempo_change`: `self.tempo_changes.append((tick, tempo)); self.tempo_changes.sort()`) combined with `:162-168`/`:154-160` (`get_tempo_at_tick`/`_cumulative_ms`'s `bisect.bisect_right(ticks, tick) - 1`, which selects the **last** entry in the sorted list for ties).
- **Status**: NEW
- **Description**: `tempo_changes` is a list of `(tick, tempo)` tuples. `sort()` on tuples orders first by `tick`, then — for equal ticks — by `tempo` **ascending**, not by insertion order. `get_tempo_at_tick`/`_cumulative_ms` then pick the *last* entry at or before the query tick via `bisect_right`, which for a tied tick means "the numerically largest tempo value wins," not "the tempo change that was added last." Standard MIDI semantics (and the SKILL's own question for this dimension) require that when two `set_tempo` events land on the same tick (plausible in multi-track files, or two meta-events with a 0 delta-time between them), the one that appears **later in processing order** is authoritative. This code silently substitutes "larger tempo value" for "later in order," which are unrelated.
- **Evidence**: Built and parsed a real `.mid` file with tempo events in file order `500000 → 600000 → 250000`, all with the second and third at the identical tick (480, delta-time 0 between them). Per standard MIDI order, 250000 (240 BPM) should be the active tempo from tick 480 onward. The actual parsed output:
  ```
  track_0 {'frame': 30, 'note': 60, ..., 'tempo': 600000}   # should be 250000
  track_0 {'frame': 66, 'note': 60, ..., 'tempo': 600000}
  track_0 {'frame': 66, 'note': 64, ..., 'tempo': 600000}
  track_0 {'frame': 138,'note': 64, ..., 'tempo': 600000}
  ```
  600000 (100 BPM) won — not because it was processed last (it wasn't; 250000 was), but because it is numerically larger and `sort()` places it after `(480, 250000)` in the tuple ordering. Confirmed at the `TempoMap` level directly as well:
  ```
  tm.add_tempo_change(1000, 600000)   # added first
  tm.add_tempo_change(1000, 400000)   # added second, should win
  tm.tempo_changes -> [(0, 500000), (1000, 400000), (1000, 600000)]
  tm.get_tempo_at_tick(1000) -> 600000   # wrong: the first-added value wins because it sorts last
  ```
- **Impact**: Wrong tempo for the remainder of the song (or section) from the tied tick onward, silently — same impact class as the already-fixed #94 (dropped tempo changes), just via a different root cause (tie-break order instead of validation rejection). Reachable on the live default pipeline (`parse_midi_to_frames` calls `EnhancedTempoMap.add_tempo_change` per `set_tempo` event in file order, with `optimization_strategy=None` so no re-snapping intervenes). Rated HIGH per the severity table's "wrong tempo/timing silently, under realistic input" bar, though the precise trigger (two distinct tempo values landing on the exact same tick) is a narrower authoring pattern than #94's (which affected any largo/presto tempo or big jump).
- **Related**: Distinct root cause from #94 (TEMPO-02, validation-rejection based) and from TEMPO-08/09 above (zero/negative tempo value based) — this is a tie-break/ordering bug, not a validation gap.
- **Suggested Fix**: Track insertion order explicitly (e.g. append `(tick, tempo, seq)` with a monotonic `seq` counter, or use a stable structure keyed by tick that always overwrites on re-insertion) so that for duplicate ticks the most-recently-added tempo is authoritative, matching MIDI event order rather than numeric tempo value.

---

### TEMPO-11: `_frame_times` numpy array is dead state — same class as the already-removed `_frame_cache` (#99), but missed by that fix
- **Severity**: LOW
- **Dimension**: 4 (Extreme Tempo Bounds) / 8
- **Location**: `tracker/tempo_map.py:242` (`self._frame_times = np.arange(0, 10000) * np.float64(FRAME_MS)` in `EnhancedTempoMap.__init__`).
- **Status**: NEW
- **Description**: `_frame_times` is assigned once in the constructor and never read anywhere in `tracker/tempo_map.py` (confirmed by grep across the module and the repo). It looks like it could be a hidden cap (`np.arange(0, 10000)` suggests a 10,000-frame / ~166s limit), but it is not consulted by any frame-calculation path — `get_frame_for_tick`, `calculate_time_ms`, `is_frame_aligned`, etc. all compute directly, so this is purely dead memory allocation, not a functional bound. The prior audit's #99 fix removed the analogous dead `_frame_cache` but this sibling dead array was not part of that fix's scope.
- **Evidence**: `grep -n "_frame_times" tracker/*.py` → only the one assignment line; no reads anywhere in the codebase.
- **Impact**: No functional effect (confirmed not a hidden 10,000-frame cap); wasted allocation (80KB float64 array) on every `EnhancedTempoMap` construction, and a misleading reader signal (looks load-bearing, isn't). LOW.
- **Related**: Same category as the fixed `_frame_cache` (#99); could be cleaned up in the same pass as #97 (TEMPO-05, still open) since both are dead state in the same class.
- **Suggested Fix**: Remove `self._frame_times = ...` from `EnhancedTempoMap.__init__`.

---

## Confirmed-fixed (re-verified, not re-reported)

- **#93 (TEMPO-01)** — SMPTE/negative `ticks_per_beat`: `TempoMap.__init__` now raises `ValueError` for `ticks_per_beat is None or ticks_per_beat < 1` (`tracker/tempo_map.py:101-107`), and `parser_fast.py:28-33` rejects it even earlier with an actionable message. Verified via code read; the *tempo*-value counterpart at tick 0 is the new TEMPO-08 above, which this fix does not cover.
- **#94 (TEMPO-02)** — Out-of-range/large-jump tempo changes: `parser_fast.py`'s `TempoValidationConfig` is now 1-2000 BPM with `max_tempo_change_ratio=float('inf')` (`:42-48`), and drops are counted and warned (`:59-81`) instead of silently continuing. Verified in place. TEMPO-10 above is a *different* bug (tie-break order) that this fix does not address.
- **#95 (TEMPO-03)** — `ticks_per_beat == 0`: covered by the same `ValueError` guard as #93 in `TempoMap.__init__`. Verified.
- **#96 (TEMPO-04)** — Same-frame note collapse: `nes/emulator_core.py:16-46` (`_collapse_same_frame_events`) now keeps the louder note and warns with a count; called from `compile_channel_to_frames` (`:64`) and the noise/dpcm branches (`:156`, `:196`). Verified in place, including deterministic tie-break (later event wins on equal velocity, `:39`).
- **#99 (TEMPO-07)** — Frame-alignment tolerance consolidation: `FRAME_ALIGNMENT_TOLERANCE_MS = 0.5` (`:23`) is now referenced by `is_frame_aligned` (`:256`), `_validate_frame_boundaries` (`:445`), and `_check_frame_alignment` (`:809`). `_frame_cache` is fully removed (zero occurrences). Verified. (See TEMPO-11 above for a sibling dead-state item this fix did not include.)
- **#113 (PERF-01)** — O(notes × tempo_changes) lookup: replaced by the bisect-based `_build_tempo_index`/`_cumulative_ms` (`:123-160`). Verified `calculate_time_ms(0, tick)` is still an exact from-zero computation (no accumulating counter) and re-verified 0-frame drift on a synthetic 5-minute song.
- **#160 (NH-20)** — Fixed-`sustain_frames`-only note duration: `compile_channel_to_frames` now derives `end_frame` from the matching note-off event where available (`nes/emulator_core.py:76-86`), falling back to `sustain_frames` only for unpaired notes. Verified in place.

## Confirmed still-open (no regression, no new information — left as filed)

- **#97 (TEMPO-05)** — `optimize_tempo_changes`, `_align_to_frames`, `_smooth_tempo_transitions`, `EnhancedLoopManager` remain dead on the live path (`optimization_strategy=None` at every live construction site; `grep` confirms zero call sites for `optimize_tempo_changes` outside `tempo_map.py` and its tests). Still LOW/dead-code as filed.
- **#98 (TEMPO-06)** — `main.py:357`/`:536` still construct a default-PPQ (`ticks_per_beat=480`) `EnhancedTempoMap` that never receives `add_tempo_change` calls; confirmed still inert (`get_tempo_at_tick` returns the constant 500000 regardless). Still LOW as filed.

---

## Dedup notes

- `gh issue list --repo matiaszanolli/midi2nes --limit 200` (47 open/closed issues, saved to `/tmp/audit/issues.json`) contains no open issue matching TEMPO-08/09/10/11's specific root causes (tick-0 validation bypass, mid-song `ZeroDivisionError` on `tempo=0`, duplicate-tick tie-break order, `_frame_times` dead state). All four are genuinely NEW.
- `docs/audits/AUDIT_TEMPO_2026-06-29.md` (the only prior tempo audit) covers TEMPO-01 through TEMPO-07 (#93-99); none of them describe this pass's findings — the closest, TEMPO-01/#93, addresses `ticks_per_beat` validity, not `tempo` validity at tick 0, and TEMPO-02/#94 addresses validation-rejected tempos, not tie-break ordering among tempos that both pass validation.
- No other domain audit (`AUDIT_SAFETY_2026-06-29.md`, `AUDIT_PIPELINE_*`, `AUDIT_PERFORMANCE_2026-06-29.md`) mentions tick-0 validation bypass, tempo=0 crashes, or duplicate-tick ordering.
- `tests/test_tempo_map.py` (43 tests, all passing) has no coverage for `tempo=0`, negative tempo at tick 0, or duplicate-tick insertion order — consistent with these being genuinely unexercised edge cases rather than a known-and-accepted behavior.

---

Suggested next step:
```
/audit-publish docs/audits/AUDIT_TEMPO_2026-07-03.md
```
