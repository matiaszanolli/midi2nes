# Issue #375 — PERF-A-05: MemoryMonitor sampling loop terminates permanently on the first transient error

**Severity:** LOW · **Domain:** performance · **Source:** AUDIT_PERFORMANCE_2026-07-19.md

## Description
The daemon sampling loop catches `Exception`, increments `_sampling_errors`, and **`break`s** — one sampling hiccup ends all further sampling for the run, so `peak_mb`/`average_mb` are computed from a truncated sample set. The error is now counted and surfaced via `sampling_errors` (#336), which is the mitigation; but a single transient read failure (not process death) still blinds the rest of the monitored window rather than skipping one sample and continuing.

## Evidence
`utils/profiling.py:129-137` — `except Exception: self._sampling_errors += 1; break`. The comment documents this as intentional ("self.process may no longer be readable"), which holds for process death but not for a transient read.

## Impact
Under-reported peak memory if a sample fails mid-run. Profiling output only. Caller can now detect it via `sampling_errors > 0`.

## Dimension
7 — Profiling utilities

## Related
#336 (seed-sample fix); Dimension 7.

## Suggested Fix
`continue` past a transient sampling error (keeping the counter), and only `break` after a small consecutive-failure threshold or on a specific process-gone exception (`psutil.NoSuchProcess`).

## Completeness Checks
- [ ] **TESTS**: A regression test pins this specific fix (transient error → sampling continues)
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
