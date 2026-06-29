# PERF-07: Shared global tracemalloc — nested profilers blind each other

**Severity:** LOW · **Domain:** performance · **Source:** AUDIT_PERFORMANCE_2026-06-29.md

## Description
Every profiler calls the **global** `tracemalloc.start()` and stops it in a `try/except: pass`. If a `@profile_memory_usage`-decorated function runs inside a `PerformanceContext` (or two `PerformanceProfiler.profile` blocks nest), the inner `tracemalloc.stop()` (`utils/profiling.py:195` / `:299`) tears down tracing for the still-running outer profiler, whose later `get_traced_memory()` then hits the bare `except` and reports current RSS instead of the traced peak.

Secondary issues in the same module:
- `cpu_percent()` is sampled with no interval so the first call after process start returns `0.0` and deltas are unreliable; the benchmark suite computes `cpu_after - cpu_before` (`benchmarks/performance_suite.py:96`) from two intervalless calls.
- `MemoryMonitor._monitor_loop` swallows all exceptions with bare `except: break` (`utils/profiling.py:89-90`), so for work shorter than `interval_ms=100` no sample is taken and `stop_monitoring` returns `{"peak_mb": 0}` (`:71-72`) — `max(peak_traced, 0)` masks it, but a pure-`MemoryMonitor` caller would see a 0 peak.

## Location
`utils/profiling.py:171,195` (`profile_memory_usage`), `:285,299` (`PerformanceContext`), `:81-90` (`MemoryMonitor._monitor_loop`); `benchmarks/performance_suite.py:96,102`

## Evidence
Three independent `tracemalloc.start()`/`stop()` pairs over one global; `process.cpu_percent()` called with no `interval=`; `_monitor_loop` `except: break` at `:89-90`.

## Impact
Profiling metrics only — never affects generated ROMs. Misleading numbers, not a crash → LOW.

## Related
PERF-06 (the benchmark suite is the main consumer and double-stops tracemalloc).

## Suggested Fix
Guard `tracemalloc.start()` with `tracemalloc.is_tracing()` and only `stop()` if this profiler started it (reference-count or skip nested starts). Sample `cpu_percent()` with a small interval or document it as advisory.

## Completeness Checks
- [ ] **SIBLING**: All three `tracemalloc.start()`/`stop()` pairs guarded consistently
- [ ] **TESTS**: A nested-profiler test confirms the outer peak survives the inner stop
