# PAT-2026-08-21-4: `_WORKER_EVENTS` is shipped to every worker process but never read — dead initializer payload since #332

**Severity:** LOW · **Domain:** patterns · **Source:** AUDIT_PATTERNS_2026-08-21.md
**GitHub Issue:** #438

## Location
`tracker/pattern_detector_parallel.py:198-202` (`initargs`), `:359-368` (`_WORKER_EVENTS` global +
`_init_pattern_worker`), `:463-472` (worker reads only `_WORKER_SEQUENCE`)

## Description
The pool initializer still stashes both `sequence` and `valid_events` into worker globals, but the
#332/PERF-12 rewrite changed the worker entry point from the old candidate-building
`_detect_patterns_worker` to `_detect_window_groups_worker`, which only buckets window positions —
it reads `_WORKER_SEQUENCE` and nothing else. Candidate selection (the only step that needs
`events`, in `_select_candidates_from_groups`) now runs in the **parent** process (`:244-253`)
with the parent's `valid_events`. `grep -n _WORKER_EVENTS` confirms the global is assigned
(`:360`, `:366-368`) and never read anywhere. So up to `MAX_PATTERN_EVENTS` = 15,000 event dicts
are pickled and unpickled once per spawned worker (up to `cpu_count()-1` processes) purely as dead
weight.

## Evidence
`_detect_window_groups_worker` (`:463-472`) touches only `_WORKER_SEQUENCE`; no other function
references `_WORKER_EVENTS`.

## Impact
Wasted per-worker spawn cost (memory + pickle time, most visible under the `spawn` start method
on macOS/Windows) and a drift trap: the module comment (`:356-358`) and prior audit reports
describe the events as live shared worker data, which no longer matches the code. No correctness
impact.

## Related
#332/PERF-12 (the rewrite that orphaned it), #114 (original initializer design), #218.

## Suggested Fix
Drop `valid_events` from `initargs`, `_init_pattern_worker`'s signature, and the `_WORKER_EVENTS`
global; update the `:356-358` comment.
