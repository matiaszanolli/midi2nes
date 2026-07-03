# TEMPO-11: _frame_times numpy array is dead state — same class as the already-removed _frame_cache (#99), but missed by that fix

Issue: #211

**Severity:** LOW · **Domain:** tempo · **Source:** AUDIT_TEMPO_2026-07-03.md

## Description
`_frame_times` is assigned once in the constructor and never read anywhere in `tracker/tempo_map.py` (confirmed by grep across the module and the repo). It looks like it could be a hidden cap (`np.arange(0, 10000)` suggests a 10,000-frame / ~166s limit), but it is not consulted by any frame-calculation path — `get_frame_for_tick`, `calculate_time_ms`, `is_frame_aligned`, etc. all compute directly, so this is purely dead memory allocation, not a functional bound. The prior audit's #99 fix removed the analogous dead `_frame_cache` but this sibling dead array was not part of that fix's scope.

## Location
`tracker/tempo_map.py:242` (`self._frame_times = np.arange(0, 10000) * np.float64(FRAME_MS)` in `EnhancedTempoMap.__init__`).

## Evidence
`grep -n "_frame_times" tracker/*.py` -> only the one assignment line; no reads anywhere in the codebase. Re-verified on 2026-07-03.

## Impact
No functional effect (confirmed not a hidden 10,000-frame cap); wasted allocation (80KB float64 array) on every `EnhancedTempoMap` construction, and a misleading reader signal (looks load-bearing, isn't). LOW.

## Related
Same category as the fixed `_frame_cache` (#99); could be cleaned up in the same pass as #97 (TEMPO-05, still open) since both are dead state in the same class.

## Suggested Fix
Remove `self._frame_times = ...` from `EnhancedTempoMap.__init__`.

## Completeness Checks
- [ ] **SIBLING**: Checked for other dead numpy/array allocations in `EnhancedTempoMap.__init__` alongside `_frame_times` (e.g. as part of the #97 cleanup)
- [ ] **TESTS**: Existing `tests/test_tempo_map.py` suite still passes after removal (no hidden dependency)
