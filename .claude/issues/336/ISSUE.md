# PERF-16
**Filed as:** #336

**Severity:** LOW · **Domain:** performance · **Source:** AUDIT_PERFORMANCE_2026-07-18.md

## Description
`_monitor_loop` appends a sample then sleeps `interval_ms`; if `stop_monitoring` runs before the daemon thread's first loop iteration (work shorter than thread-scheduling latency), `_memory_samples` is empty and `stop_monitoring` returns `{"peak_mb": 0, "average_mb": 0, "samples": 0}` (`utils/profiling.py:102-103`) — a misleading zero rather than the RSS at start. The loop also wraps the body in `except Exception: break` (`:120`), which discards any sampling error (and the final sample) without recording it. This is narrower than the bare `except:` tracked as TD-10/#135 (KeyboardInterrupt now propagates), but still swallows sampling errors silently.

## Evidence
`if not self._memory_samples: return {"peak_mb": 0, ...}` (`:102-103`); loop body `try: … except Exception: break` (`:120`).

## Impact
A profiled stage faster than `interval_ms` reports zero peak memory — a misleading metric in benchmark output, not a crash. Low blast radius (dev tooling only).

## Related
#135 (TD-10), #118 (tracemalloc lifecycle fix).

## Suggested Fix
Seed `_memory_samples` with an immediate RSS read in `start_monitoring` so a peak is always available; log/count swallowed sampling exceptions instead of a bare `break`.

## Completeness Checks
- [ ] **TESTS**: a test asserts a sub-interval profiled block reports non-zero peak_mb
- [ ] **SIBLING**: same seed-with-initial-sample pattern applied to any other monitor loops