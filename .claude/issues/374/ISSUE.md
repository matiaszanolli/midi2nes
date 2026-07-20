# Issue #374 — PERF-A-04: cpu_percent reported as a delta of two interval-less psutil calls

**Severity:** MEDIUM · **Domain:** performance · **Source:** AUDIT_PERFORMANCE_2026-07-19.md

## Description
CPU usage is captured as `process.cpu_percent()` at start and end with **no `interval=`**. Per psutil semantics the first non-blocking call returns `0.0` and each later call measures CPU since the *previous* call, so the reported `cpu_percent` (and, in `profile_memory_usage`, `cpu_after - cpu_before`) is advisory noise, not a per-stage figure. It is printed in the benchmark report and per-stage `[PROFILE]` lines as though meaningful. This is a misleading-stat gap (cf. the "reported stat inaccurate (cosmetic but misleading)" MEDIUM row in the severity rubric), not a crash.

## Evidence
`benchmarks/performance_suite.py:106` `self._start_cpu = self.process.cpu_percent()` (unused thereafter) and `:115` `cpu_percent = self.process.cpu_percent()` fed into `BenchmarkResult.cpu_percent`; `utils/profiling.py:270` `cpu_percent=cpu_after - cpu_before`. The code comment at `utils/profiling.py:212-217` acknowledges the reading is advisory-only (an `interval=` would add blocking latency) — the value is retained and displayed anyway.

## Impact
A `cpu_percent` column that looks authoritative but is unreliable can misdirect optimization effort. Benchmark output only; no production effect.

## Dimension
7 — Profiling utilities

## Related
Dimension 7; #118 (the tracemalloc half was fixed there).

## Suggested Fix
Either drop the `cpu_percent` field from reported results, or compute it as `cpu_times()` deltas divided by wall time (no blocking), and label it accordingly.

## Completeness Checks
- [ ] **SIBLING**: Same pattern checked in both call sites (`performance_suite.py` and `utils/profiling.py`)
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
