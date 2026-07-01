# REG-06: ParallelPatternDetector (36% cov) — multi-core path, fallback, and core-count determinism untested

**Severity:** MEDIUM · **Domain:** regression · **Source:** AUDIT_REGRESSION_2026-06-28.md

## Description
The default pattern-detection front-end is only smoke-touched in `test_main_pipeline.py`; the actual `ProcessPoolExecutor` map, the `as_completed` result merge, the score-`sort`+`set`-based selection, and the documented graceful fallback to `EnhancedPatternDetector` are uncovered. Two risks: (a) the worker path could raise on common input without the fallback firing (a HIGH-rated failure mode per `_audit-severity.md`) and no test guards it; (b) `chunk_size = (len - length + 1) // max_workers` and `max_workers = cpu_count() - 1` make chunk boundaries — and therefore which patterns are discovered — **depend on host core count**, with no test asserting result-invariance across worker counts.

## Evidence
`cov` 36% for `tracker/pattern_detector_parallel.py`; worker dispatch + merge lines unexecuted. `self.max_workers = max(1, mp.cpu_count() - 1)`; `chunk_size = max(1, (len(sequence) - length + 1) // self.max_workers)`. No `tests/test_pattern_detector_parallel.py` exists.

## Impact
Compression could differ run-to-run / host-to-host (CI vs local), and a worker-pool crash could silently yield no patterns. Guards a CRITICAL failure mode (round-trip) and a HIGH one (fallback).

## Suggested Fix
Add `tests/test_pattern_detector_parallel.py`:
1. **Determinism**: run detection on `test_midi/short_loops.mid` frames with `max_workers=1`, `2`, `4`; assert identical `patterns`/`references`/`compression_ratio`.
2. **Fallback**: monkeypatch the worker entry to raise; assert it falls back to `EnhancedPatternDetector` and still returns the required keys (`patterns`, `references`, `stats`, `variations`).
3. **Round-trip**: assert compress→decompress reproduces the original sequence (guards the CRITICAL lossless claim).

## Completeness Checks
- [ ] **CONTRACT**: Result keeps `patterns`/`references`/`stats`/`variations` shape
- [ ] **ROUNDTRIP**: Decompressed playback == original sequence (asserted)
- [ ] **FALLBACK**: Worker-path failure still triggers the EnhancedPatternDetector fallback (asserted)
- [ ] **TESTS**: `tests/test_pattern_detector_parallel.py` pins determinism across worker counts
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
