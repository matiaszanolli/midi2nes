# TEMPO-08: tick==0 tempo changes bypass all validation — zero/negative initial tempo silently corrupts the whole song

**GitHub Issue:** https://github.com/matiaszanolli/midi2nes/issues/208
**Severity:** CRITICAL
**Domain:** tempo
**Source:** docs/audits/AUDIT_TEMPO_2026-07-03.md
**Labels:** critical, tempo, bug

## Description
`EnhancedTempoMap.add_tempo_change` special-cases `tick == 0` to replace the initial tempo
directly (`self.tempo_changes[0] = (0, tempo)`) and returns immediately
(`tracker/tempo_map.py:262-271`) — **before** `_validate_basic_tempo` (BPM-range check) is
ever called. Every other tick goes through `_validate_basic_tempo` (`:277`), which would
reject a 0 or out-of-range BPM. A MIDI file whose very first `set_tempo` meta-event (at tick
0) carries `tempo=0` or a negative value is therefore accepted unconditionally, with no
`TempoValidationError` and no warning.

Same bug class as fixed #93 (negative frame indices) and #95 (`ticks_per_beat==0` → `inf`),
reachable via the tempo value at tick 0 instead.

## Evidence
- `tempo=0` at tick 0 collapses every event before the next real tempo change onto frame 0.
- Negative tempo at tick 0 (`add_tempo_change(0, -500000, ...)`) produces negative frame
  indices for the entire song: `get_frame_for_tick(480) -> -30`.

## Impact
Silent, total corruption of song timing from t=0. No error, no warning — the ROM compiles
"successfully" with scrambled or missing music.

## Suggested Fix
Call `_validate_basic_tempo(change)` (or at minimum a `tempo >= 1` and BPM-range check) before
the `tick == 0` early return in `EnhancedTempoMap.add_tempo_change`.

## Completeness Checks
- [ ] **SIBLING**: Same tick==0-bypasses-validation pattern checked for any other early-return
      branch keyed on tick (base `TempoMap.add_tempo_change`, `_validate_tempo_change`)
- [ ] **TESTS**: A regression test pins `tempo=0` and negative-tempo at tick 0 both raising
      `TempoValidationError`

---

# TEMPO-11: _frame_times numpy array is dead state, missed by the #99 _frame_cache cleanup

**GitHub Issue:** https://github.com/matiaszanolli/midi2nes/issues/211
**Severity:** LOW
**Domain:** tempo
**Source:** docs/audits/AUDIT_TEMPO_2026-07-03.md
**Labels:** low, tempo, bug

## Description
`_frame_times` is assigned once in `EnhancedTempoMap.__init__`
(`tracker/tempo_map.py:242`: `self._frame_times = np.arange(0, 10000) * np.float64(FRAME_MS)`)
and never read anywhere in `tracker/tempo_map.py` (confirmed by grep across the module and the
repo). Looks like it could be a hidden cap (10,000-frame / ~166s limit) but is not consulted by
any frame-calculation path — pure dead memory allocation, not a functional bound.

The prior #99 fix removed the analogous dead `_frame_cache`; this sibling dead array was not
part of that fix's scope.

## Evidence
`grep -n "_frame_times" tracker/*.py nes/*.py exporter/*.py main.py` → only the one assignment
line; no reads anywhere in the codebase.

## Impact
No functional effect; wasted allocation (80KB float64 array) on every `EnhancedTempoMap`
construction, and a misleading reader signal. LOW.

## Suggested Fix
Remove `self._frame_times = ...` from `EnhancedTempoMap.__init__`.

## Completeness Checks
- [ ] **SIBLING**: Checked for other dead numpy/array allocations in `EnhancedTempoMap.__init__`
      alongside `_frame_times`
- [ ] **TESTS**: Existing `tests/test_tempo_map.py` suite still passes after removal
