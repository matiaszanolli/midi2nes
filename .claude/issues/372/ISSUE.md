# Issue #372 — PERF-A-02: Benchmark harness has no checked-in baseline and no regression gate

**Severity:** LOW · **Domain:** performance · **Source:** AUDIT_PERFORMANCE_2026-07-19.md

## Description
The harness now measures the correct production modules with the correct pattern-length bounds (#262 fixed), but it still only *emits* a JSON report. There is no versioned baseline it compares against and no "fail if slower than baseline by X%" assertion. `benchmark_results/…json` is a run output, not a regression fixture. A benchmark with no comparison cannot catch the regressions this audit exists to prevent — it will greenlight a 2x slowdown silently.

## Evidence
`generate_report` (`benchmarks/performance_suite.py:371`) writes averages/p95 but compares against nothing; `run_baseline_benchmark` prints advisory thresholds (`benchmarks/run_benchmarks.py:149-162`, e.g. `if pattern_avg > 1000: print("… slow")`) that are absolute heuristics, not baseline deltas, and are print-only (no non-zero exit).

## Impact
Performance regressions in the parser or detector pass CI/local runs unnoticed. Blast radius: the entire performance-correctness safety net.

## Dimension
6 — Benchmark validity

## Status note
NEW (surviving half of the now-closed #262/PERF-11 — the param-drift half was fixed; the gate half was never implemented).

## Related
#262 (closed); Dimension 6; PERF-A-03.

## Suggested Fix
Check in a small deterministic baseline (see PERF-A-03) and a comparison step that exits non-zero when a stage's median exceeds baseline by a configurable margin.

## Completeness Checks
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
