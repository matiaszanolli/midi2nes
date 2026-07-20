# Issue #373 — PERF-A-03: Baseline benchmark input set is machine-dependent

**Severity:** LOW · **Domain:** performance · **Source:** AUDIT_PERFORMANCE_2026-07-19.md

## Description
`run_baseline_benchmark` globs `test_data/`, `examples/`, `samples/` and `.` for `*.mid` and benchmarks whatever it finds (first 5). Traversal order is now sorted (deterministic per machine, #117), but the *set* of files still depends on what happens to be present, so results are not comparable across machines or over time — undermining any future baseline gate (PERF-A-02).

## Evidence
`benchmarks/run_benchmarks.py:70-98` — `test_dirs = ["test_data", "examples", "samples", "."]` then `test_files.extend(find_test_files(test_dir, "*.mid"))`, truncated to `test_files[:5]`. Falls back to a not-implemented synthetic generator (`create_synthetic_midi` returns `False`).

## Impact
Cross-run/cross-machine numbers are incomparable; the harness cannot anchor a stable baseline. Tooling only.

## Dimension
6 — Benchmark validity

## Related
PERF-A-02; Dimension 6.

## Suggested Fix
Commit one or two small fixture `.mid` files under a dedicated `benchmarks/fixtures/` dir and benchmark exactly those by default, independent of the working tree.

## Completeness Checks
- [ ] **TESTS**: A regression test pins this specific fix (deterministic fixture set)
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
