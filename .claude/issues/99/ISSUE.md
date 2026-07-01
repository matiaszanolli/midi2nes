# TEMPO-07: _frame_cache is never read; inconsistent frame-alignment tolerances across methods

**Severity:** LOW · **Domain:** tempo · **Source:** AUDIT_TEMPO_2026-06-29.md

## Description
`_frame_cache` is initialized and cleared in five places but never read — dead state. Separately, the various frame-alignment helpers use mutually inconsistent thresholds: `is_frame_aligned` accepts `< 0.001 ms`, `add_tempo_change` treats `> 1.0 ms` as misaligned and warns only beyond `2.0 ms`, `_validate_frame_boundaries` errors at `> 0.5 ms`, `_check_frame_alignment` errors at `> 1 µs`. A tempo change can be "aligned" by one method and "misaligned" by another. Because all these methods are on the dead optimization path (TEMPO-05), there is no live impact today.

## Location
`tracker/tempo_map.py:201,223,299,604,611` (`_frame_cache` only ever assigned); tolerance constants at `:209` (`< 0.001`), `:252`/`:272` (`> 1.0` / `< 1.0`), `:281` (`> 2.0`), `:322` (`< 0.001`), `:398` (`> 0.5`), `:660` (`> 0.01`), `:762` (`> 1` µs).

## Evidence
`grep -n "_frame_cache" tracker/tempo_map.py` shows assignments only (lines 201, 223, 299, 604, 611), no reads. Threshold literals enumerated above.

## Impact
Code-quality / maintainability; would become a real inconsistency if the alignment methods were wired into the live path. LOW.

## Related
TEMPO-05 (same dead alignment machinery).

## Suggested Fix
Remove `_frame_cache`; consolidate the alignment tolerance into one named constant (e.g. half a frame) referenced by all alignment checks.

## Completeness Checks
- [ ] **TESTS**: A test pins the consolidated alignment tolerance if the methods are retained
- [ ] **DOC**: Alignment tolerance constant documented
