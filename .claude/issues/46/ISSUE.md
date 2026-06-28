# REG-06: ParallelPatternDetector (36% cov) — multi-core path, fallback, and core-count determinism untested

**Severity:** MEDIUM · **Domain:** regression · **Source:** AUDIT_REGRESSION_2026-06-28.md

GitHub: https://github.com/matiaszanolli/midi2nes/issues/46
Labels: medium, regression, enhancement

## Description
tracker/pattern_detector_parallel.py only smoke-touched. ProcessPoolExecutor map, as_completed merge, score sort+set selection, and EnhancedPatternDetector fallback uncovered. chunk_size depends on cpu_count() so discovered patterns depend on host core count, untested for invariance.

## Evidence
36% cov; no tests/test_pattern_detector_parallel.py. max_workers = cpu_count()-1; chunk_size = (len-length+1)//max_workers.

## Impact
Compression differs CI-vs-local; worker-pool crash could silently yield no patterns. Guards CRITICAL (round-trip) and HIGH (fallback) modes.

## Suggested Fix
Add tests/test_pattern_detector_parallel.py: determinism across max_workers=1/2/4; fallback on worker raise; compress→decompress round-trip.
