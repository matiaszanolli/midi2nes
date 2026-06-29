# P-09: Per-chunk except…continue in the parallel pool can silently drop a length candidates with only a transient tqdm note

**Severity:** LOW · **Domain:** patterns · **Source:** AUDIT_PATTERNS_2026-06-29.md

## Description
A failed/timed-out chunk (`future.result(timeout=30)`) is caught, written to the tqdm bar via `pbar.write`, and `continue`d — its candidate patterns are dropped while the run reports success. Unlike the *whole-pool* failure (which falls back to serial), a single-chunk failure has no fallback and no persistent warning. Because patterns are metrics-only in export (#4), this degrades compression quality but does not corrupt frames; still, a transient stderr line is not a durable signal that detection was partial.

## Location
`tracker/pattern_detector_parallel.py:125-139` — per-chunk `except Exception … pbar.write(…) … continue` at `:131-134`; whole-pool fallback to `_detect_patterns_serial` at `:136-139`.

## Evidence
Verified:
```python
except Exception as e:
    pbar.write(f"  ⚠️  Chunk failed: {e}")
    pbar.update(1)
    continue
```
No re-raise, no fallback, no summary count of failed chunks at the per-chunk level.

## Impact
Silent partial pattern detection on chunk failure; LOW today (no byte-level effect), would matter once references drive output.

## Related
P-05, #46 (REG-06 — parallel path untested).

## Suggested Fix
Count failed chunks and surface a single end-of-run warning; if any chunk for a given length fails, consider re-running that length serially.

## Completeness Checks
- [ ] **FALLBACK**: a single-chunk failure surfaces a durable warning (or re-runs that length serially)
- [ ] **TESTS**: a test injects a chunk failure and asserts the warning/count is emitted
